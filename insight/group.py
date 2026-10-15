"""Stage 4 - group (code + model).

Code owns membership: every completed complaint/cancellation record belongs to exactly one
issue, issue_id = '<topic>.<subtopic>' from the fixed taxonomy (stable across runs). The
model only NAMES the top issues from a bounded evidence pack (<= evidence_per_issue quotes)
and flags quotes that do not fit; names never change membership or ranking. Saved naming
output is cached by its exact inputs, so re-running grouping makes no new calls.
"""

import csv
import io
import json

from . import labels, prompts
from .control import Dispatcher, Task
from .rank import compute_ranking
from .util import atomic_write_json, atomic_write_text, sha256_text, short_hash


def load_completed(store, label_config):
    """Only the fields grouping and ranking need (keeps memory small on the full corpus)."""
    recs = {}
    for r in store.conn.execute(
            "SELECT review_id, topic, subtopic, intent, severity, needs_review, cache_source_id FROM results "
            "WHERE label_config=? AND status='completed'", (label_config,)):
        recs[r[0]] = {"topic": r[1], "subtopic": r[2], "intent": r[3], "severity": r[4], "needs_review": r[5],
                      "cache_source_id": r[6]}
    return recs


def membership_from_records(records: dict) -> list:
    pairs = [(f"{r['topic']}.{r['subtopic']}", rid) for rid, r in records.items()
             if r["intent"] in labels.COMPLAINT_INTENTS]
    return sorted(pairs)


def membership_csv(pairs) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["issue_id", "review_id"])
    w.writerows(pairs)
    return buf.getvalue()


def evidence_pack(store, label_config, issue_id, k, order="sample"):
    """Up to k distinct member quotes for naming an issue and for the memo's evidence.

    order="sample" (default): a deterministic uniform sample of the issue's distinct member texts
    (sha256 of issue_id:review_id), so names describe the typical member. order="severity" (the
    first version): highest severity first, then most helpful votes. On the final run it named the
    catch-all `other.general` after its rare privacy complaints (8 of 14,796 distinct texts mention
    privacy), so it is kept only for comparison. Identical texts are represented once.
    """
    topic, subtopic = issue_id.split(".", 1)
    rows = store.conn.execute(
        "SELECT x.review_id, x.evidence_quote, x.severity, "
        "CASE WHEN r.review_likes GLOB '[0-9]*' THEN CAST(r.review_likes AS INTEGER) ELSE 0 END, r.row_num "
        "FROM results x JOIN reviews r ON r.review_id = x.review_id AND r.duplicate_id = 0 "
        "WHERE x.label_config = ? AND x.status = 'completed' AND x.cache_source_id IS NULL AND x.topic = ? AND x.subtopic = ? "
        "AND x.intent IN ('complaint', 'cancellation')", (label_config, topic, subtopic)).fetchall()
    if order == "severity":
        rows.sort(key=lambda r: (-r[2], -r[3], r[4]))
    else:
        rows.sort(key=lambda r: sha256_text(f"{issue_id}:{r[0]}"))
    return [{"review_id": r[0], "quote": r[1]} for r in rows[:k]]


class GroupStage:
    def __init__(self, store, cfg, registry, ctx, log=print):
        self.store, self.cfg, self.registry, self.ctx, self.log = store, cfg, registry, ctx, log
        self.g = cfg["group"]
        self.gconf = cfg.stage_config("group")
        self.label_config = cfg.label_config()

    def run(self):
        store, ctx = self.store, self.ctx
        records = load_completed(store, self.label_config)
        pairs = membership_from_records(records)
        atomic_write_text(store.run_dir / "membership.csv", membership_csv(pairs))
        ranking = compute_ranking(records, pairs)
        top = [r["issue_id"] for r in ranking[: int(self.g["name_top_k"])]]
        issues = {}
        tasks = []
        for row in ranking:
            iid = row["issue_id"]
            base = labels.ISSUE_BY_ID[iid]
            pack = evidence_pack(store, self.label_config, iid, int(self.g["evidence_per_issue"]),
                                 self.g.get("evidence_order", "sample"))
            issues[iid] = {"issue_id": iid, "topic": base["topic"], "subtopic": base["subtopic"],
                           "area": labels.AREA_OF_TOPIC[base["topic"]], "default_name": base["name"],
                           "definition": base["definition"], "complaint_count": row["complaint_count"],
                           "evidence": pack, "name": base["name"], "summary": None, "named_by": "taxonomy default",
                           "misfit_review_ids": []}
            catch_all = iid in tuple(self.g.get("taxonomy_named", ()))
            if catch_all:  # by definition no specific feature: a model name from a few quotes would overstate it
                issues[iid]["named_by"] = "taxonomy (catch-all issue: never model-named)"
            if iid in top and pack and not catch_all:
                key = short_hash({"issue": iid, "pack": pack, "config": self.gconf}, 20)
                cached = store.cache_get("group", key)
                if cached:
                    self._apply(issues[iid], cached, pack, "cache")
                else:
                    tasks.append((iid, key, pack))
        self.log(f"[group] {len(pairs)} complaint/cancellation memberships in {len(ranking)} issues; "
                 f"naming top {len(top)} ({len(tasks)} new model calls, {len(top) - len(tasks)} cached or empty)")
        store.event(ctx.run_id, "group", "start", memberships=len(pairs), issues=len(ranking), calls=len(tasks))
        if tasks:
            r = self.cfg.role_settings("group")
            provider = self.registry.get(r["provider"], r["model"], r["effort"])
            disp = Dispatcher(ctx, int(self.cfg["run"]["workers"]), int(self.cfg["run"]["max_in_flight_per_worker"]))
            by_issue = {}
            queue = list(tasks)
            try:
                while True:
                    while queue and disp.capacity() > 0 and not ctx.stop_admitting.is_set():
                        iid, key, pack = queue.pop(0)
                        t = self._task(provider, issues[iid], pack, 1)
                        by_issue[id(t)] = (iid, key, pack)
                        disp.submit(t)
                    if not disp.in_flight:
                        break
                    for task, outcome in disp.wait_some():
                        iid, key, pack = by_issue.pop(id(task))
                        out, problems = self._validate(outcome, pack)
                        if out:
                            store.cache_put("group", key, out, outcome.request_id, ctx.run_id)
                            self._apply(issues[iid], out, pack, "model")
                            continue
                        if outcome.status == "ok":
                            store.call_settled(outcome.request_id, {"outcome": "failed", "valid_output": 0,
                                                                    "error": "invalid_output: " + "; ".join(problems)})
                        if outcome.status in ("ok", "invalid_output") and task.task_attempt == 1 \
                                and not ctx.stop_admitting.is_set():
                            t = self._task(provider, issues[iid], pack, 2)
                            by_issue[id(t)] = (iid, key, pack)
                            disp.submit(t)
                        elif outcome.status == "budget":
                            ctx.request_stop("budget_cap")
                        elif outcome.status == "systemic":  # e.g. a Claude Pro plan limit: stop, resume later
                            ctx.request_stop(f"systemic_provider_error: {outcome.error}")
                            issues[iid]["named_by"] = "taxonomy default (run stopped before naming)"
                        else:
                            issues[iid]["named_by"] = f"taxonomy default (model naming failed: {outcome.status})"
            finally:
                disp.shutdown()
        doc = {"stage": "group", "owner": "code (membership) + model (names only)", "group_config": self.gconf,
               "label_config": self.label_config, "allow_multi_issue": False,
               "rule": "issue_id = topic.subtopic of each completed complaint/cancellation record; one issue per record",
               "issues": [issues[r["issue_id"]] for r in ranking]}
        atomic_write_json(store.run_dir / "issues.json", doc)
        store.event(ctx.run_id, "group", "end", issues=len(ranking))
        return {"memberships": len(pairs), "issues": len(ranking), "named_calls": len(tasks)}

    def _task(self, provider, issue, pack, attempt):
        req = prompts.group_request({"name": issue["default_name"], "definition": issue["definition"]},
                                    [p["quote"] for p in pack], int(self.g["max_output_tokens"]))
        chars = len(req["system"]) + len(req["user"]) + len(json.dumps(req["schema"]))
        return Task(role="group", tier="group", provider=provider, request=req, review_ids=[p["review_id"] for p in pack],
                    max_output_tokens=int(self.g["max_output_tokens"]), prompt_chars=chars, stage_config=self.gconf,
                    task_attempt=attempt)

    @staticmethod
    def _validate(outcome, pack):
        if outcome.status != "ok":
            return None, [outcome.status]
        d = outcome.result.data
        if not isinstance(d, dict):
            return None, [f"unusable output: {outcome.result.finish}"]
        problems = []
        name, summary, misfit = d.get("name"), d.get("summary"), d.get("misfit_quotes")
        if not isinstance(name, str) or not name.strip() or len(name) > 90:
            problems.append("name missing or too long")
        if not isinstance(summary, str) or not summary.strip() or len(summary) > 400:
            problems.append("summary missing or too long")
        if not isinstance(misfit, list) or any(type(i) is not int or not 1 <= i <= len(pack) for i in misfit):
            problems.append("misfit_quotes not a list of quote numbers")
        if problems:
            return None, problems
        return {"name": name.strip(), "summary": summary.strip(), "misfit_quotes": sorted(set(misfit))}, []

    @staticmethod
    def _apply(issue, out, pack, source):
        issue["name"], issue["summary"] = out["name"], out["summary"]
        issue["misfit_review_ids"] = [pack[i - 1]["review_id"] for i in out["misfit_quotes"]]
        issue["named_by"] = source

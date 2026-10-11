"""Stage 3 - verify (independent model + code).

A separate model role re-labels a DECLARED random sample from the review text alone; it never
sees the enricher's labels. Code compares field by field and reports disagreements. Verifier
output is stored separately and never overwrites an enriched label.

Sample: distinct completed texts ranked by SHA-256(seed + ':' + review_id); the lowest k are
taken, k = clamp(round(sample_fraction x n), min_sample, max_sample). Membership therefore
does not depend on processing order or on the enricher's answers.
"""

import csv
import hashlib
import io
import json
from collections import Counter

from . import labels, prompts
from .control import Dispatcher, Task
from .util import atomic_write_json, atomic_write_jsonl, atomic_write_text, utc_now


def sample_ids(rep_ids, seed, fraction, min_n, max_n):
    n = len(rep_ids)
    k = min(n, max(min_n, min(max_n, round(fraction * n))))
    ranked = sorted(rep_ids, key=lambda r: hashlib.sha256(f"{seed}:{r}".encode()).hexdigest())
    return sorted(ranked[:k]), {"method": "lowest SHA-256(seed + ':' + review_id) among distinct completed texts",
                                "seed": seed, "population": n, "fraction": fraction, "min": min_n, "max": max_n,
                                "sample_size": k}


def parse_verifier(data):
    if not isinstance(data, dict):
        return None, ["output is not an object"]
    problems = []
    if data.get("topic") not in labels.TOPICS:
        problems.append(f"unknown topic {data.get('topic')!r}")
    if data.get("intent") not in labels.INTENTS:
        problems.append(f"unknown intent {data.get('intent')!r}")
    sev, sent = data.get("severity"), data.get("sentiment")
    if type(sev) is not int or not 1 <= sev <= 5:
        problems.append(f"severity {sev!r} not 1-5")
    if type(sent) is not int or not -2 <= sent <= 2:
        problems.append(f"sentiment {sent!r} not -2..2")
    if data.get("confidence") not in ("high", "medium", "low"):
        problems.append("confidence not high/medium/low")
    if problems:
        return None, problems
    return {"topic": data["topic"], "intent": data["intent"], "severity": sev, "sentiment": sent / 2,
            "confidence": data["confidence"]}, []


def compare(enriched: dict, verified: dict, tolerance=labels.SENTIMENT_TOLERANCE):
    """Per-field comparison used by the report and by the planted-error test."""
    sev_diff = abs(int(enriched["severity"]) - int(verified["severity"]))
    sent_diff = abs(float(enriched["sentiment"]) - float(verified["sentiment"]))
    fields = {
        "topic": enriched["topic"] == verified["topic"],
        "intent": enriched["intent"] == verified["intent"],
        "severity": sev_diff == 0,
        "sentiment_within_tolerance": sent_diff <= tolerance + 1e-9,
    }
    return {"agree": fields, "severity_abs_diff": sev_diff, "sentiment_abs_diff": round(sent_diff, 4),
            "disagreement_fields": [k for k, ok in fields.items() if not ok]}


def build_report(pairs, sample_meta, verifier_config, label_config, failed):
    """pairs = [(review_id, text, enriched_row_dict, verified_dict)]."""
    n = len(pairs)
    agree = Counter()
    sev_diffs = Counter()
    sent_abs = []
    confusions = {"topic": Counter(), "intent": Counter()}
    by_tier = {}
    disagreements = []
    for rid, text, e, v in pairs:
        c = compare(e, v)
        for k, ok in c["agree"].items():
            agree[k] += ok
        sev_diffs[c["severity_abs_diff"]] += 1
        sent_abs.append(c["sentiment_abs_diff"])
        for f in ("topic", "intent"):
            if e[f] != v[f]:
                confusions[f][f"{e[f]} -> {v[f]}"] += 1
        tier = e.get("labeled_by") or "primary"
        t = by_tier.setdefault(tier, Counter())
        t["n"] += 1
        t["all_three_agree"] += c["agree"]["topic"] and c["agree"]["intent"] and c["agree"]["severity"]
        if c["disagreement_fields"]:
            disagreements.append({"review_id": rid, "text": text[:300], "fields": c["disagreement_fields"],
                                  "enricher": {k: e[k] for k in ("topic", "intent", "severity", "sentiment")},
                                  "verifier": {k: v[k] for k in ("topic", "intent", "severity", "sentiment", "confidence")},
                                  "enricher_labeled_by": tier, "enricher_needs_review": bool(e.get("needs_review")),
                                  "severity_abs_diff": c["severity_abs_diff"]})
    rate = lambda k: round(agree[k] / n, 4) if n else None
    return {
        "stage": "verify", "owner": "independent model + code", "verifier_config": verifier_config,
        "label_config": label_config, "sample": sample_meta, "compared": n, "verifier_failures": failed,
        "agreement": {k: {"agree": agree[k], "of": n, "rate": rate(k)}
                      for k in ("topic", "intent", "severity", "sentiment_within_tolerance")},
        "sentiment_tolerance": labels.SENTIMENT_TOLERANCE,
        "sentiment_mean_abs_diff": round(sum(sent_abs) / n, 4) if n else None,
        "severity_abs_diff_counts": {str(k): v for k, v in sorted(sev_diffs.items())},
        "top_confusions": {f: dict(c.most_common(10)) for f, c in confusions.items()},
        "by_enricher_tier": {k: dict(v) for k, v in by_tier.items()},
        "disagreements": disagreements,
        "note": ("Agreement between two models is a consistency check, not accuracy. Disagreements are reported "
                 "for inspection; enriched labels are never overwritten by the verifier."),
    }


class VerifyStage:
    def __init__(self, store, cfg, registry, ctx, log=print):
        self.store, self.cfg, self.registry, self.ctx, self.log = store, cfg, registry, ctx, log
        self.v = cfg["verify"]
        self.vconf = cfg.stage_config("verify")
        self.label_config = cfg.label_config()

    def _population(self):
        return [r["review_id"] for r in self.store.conn.execute(
            "SELECT review_id FROM results WHERE label_config=? AND status='completed' AND cache_source_id IS NULL "
            "ORDER BY review_id", (self.label_config,))]

    def run(self):
        ctx, store = self.ctx, self.store
        ids, meta = sample_ids(self._population(), self.cfg["run"]["seed"], float(self.v["sample_fraction"]),
                               int(self.v["min_sample"]), int(self.v["max_sample"]))
        out_dir = store.run_dir / "verification"
        atomic_write_json(out_dir / "sample.json", {"declared": meta, "review_ids": ids, "verifier_config": self.vconf})
        todo = [rid for rid in ids if store.verification(rid, self.vconf) is None]
        self.log(f"[verify] declared sample {len(ids)} of {meta['population']} distinct texts; {len(todo)} to call")
        store.event(ctx.run_id, "verify", "start", sample=len(ids), todo=len(todo), verifier_config=self.vconf)
        r = self.cfg.role_settings("verify")
        provider = self.registry.get(r["provider"], r["model"], r["effort"]) if todo else None
        batch_n = max(1, min(50, int(self.v.get("batch_size", 1))))
        disp = Dispatcher(ctx, int(self.cfg["run"]["workers"]), int(self.cfg["run"]["max_in_flight_per_worker"]))
        queue = list(todo)
        stats = Counter()
        try:
            while True:
                while queue and disp.capacity() > 0 and not ctx.stop_admitting.is_set():
                    chunk, queue = queue[:batch_n], queue[batch_n:]
                    disp.submit(self._task(provider, chunk, 1))
                if not disp.in_flight:
                    break
                for task, outcome in disp.wait_some():
                    if outcome.status == "ok":
                        self._on_result(task, outcome, provider, disp, stats)
                    elif outcome.status == "budget":
                        ctx.request_stop("budget_cap")
                    elif outcome.status == "systemic":
                        ctx.request_stop(f"systemic_provider_error: {outcome.error}")
                    else:
                        stats[f"left_pending_{outcome.status}"] += len(task.review_ids)
        finally:
            disp.shutdown()
        report = self.write_report(ids, meta)
        store.event(ctx.run_id, "verify", "end", **stats)
        return {"sample": len(ids), **stats, "agreement": report["agreement"]}

    def _on_result(self, task, outcome, provider, disp, stats):
        """Validate every returned ID; invalid or missing items get one retry, then a recorded failure."""
        ctx, store = self.ctx, self.store
        aliases = task.context["aliases"]
        data = outcome.result.data
        items = data.get("results") if isinstance(data, dict) else None
        problems_all, seen, retry = [], set(), []
        if not isinstance(items, list):
            problems_all.append(f"no results array ({outcome.result.finish})")
            items = []
        for item in items:
            alias = item.get("id") if isinstance(item, dict) else None
            rid = aliases.get(alias)
            if rid is None or alias in seen:
                problems_all.append(f"unexpected or duplicate id {alias!r}")
                continue
            seen.add(alias)
            parsed, problems = parse_verifier(item)
            if parsed is None:
                problems_all.append(f"{alias}: " + "; ".join(problems))
                retry.append(rid)
                continue
            store.insert_verification({"review_id": rid, "verifier_config": self.vconf, "status": "completed",
                                       **parsed, "request_id": outcome.request_id, "run_id": ctx.run_id,
                                       "created_at": utc_now()})
            stats["completed"] += 1
        missing = [rid for a, rid in aliases.items() if a not in seen]
        if missing:
            problems_all.append(f"missing ids {[a for a in aliases if a not in seen]}")
        retry += missing
        if problems_all:
            fields = {"valid_output": 0, "notes": "; ".join(problems_all)[:400]}
            if len(retry) == len(aliases):
                fields.update({"outcome": "failed", "error": "invalid_output: " + "; ".join(problems_all)[:400]})
            store.call_settled(outcome.request_id, fields)
        if not retry:
            return
        if task.task_attempt == 1 and not ctx.stop_admitting.is_set():
            disp.submit(self._task(provider, retry, 2))
            return
        for rid in retry:
            store.insert_verification({"review_id": rid, "verifier_config": self.vconf, "status": "failed",
                                       "reason": "invalid output after one retry: " + "; ".join(problems_all)[:300],
                                       "request_id": outcome.request_id, "run_id": ctx.run_id, "created_at": utc_now()})
            stats["failed"] += 1

    def _task(self, provider, rids, attempt):
        items = [(f"v{i + 1}", self.store.review(rid)["review_text"]) for i, rid in enumerate(rids)]
        max_out = int(self.v["max_output_tokens"])
        req = prompts.verify_batch_request(items, max_out, template=self.v["prompt"])
        chars = len(req["system"]) + len(req["user"]) + len(json.dumps(req["schema"]))
        return Task(role="verify", tier="verify", provider=provider, request=req, review_ids=list(rids),
                    max_output_tokens=max_out, prompt_chars=chars, stage_config=self.vconf, task_attempt=attempt,
                    context={"aliases": {a: rid for (a, _), rid in zip(items, rids)}})

    def write_report(self, ids=None, meta=None):
        store = self.store
        out_dir = store.run_dir / "verification"
        if ids is None:
            declared = json.loads((out_dir / "sample.json").read_text())
            ids, meta = declared["review_ids"], declared["declared"]
        pairs, preds, failed = [], [], 0
        for rid in ids:
            v = store.verification(rid, self.vconf)
            e = store.result(rid, self.label_config)
            if v is None or e is None:
                continue
            if v["status"] != "completed":
                failed += 1
                preds.append({"review_id": rid, "status": "failed", "reason": v["reason"]})
                continue
            vd = {k: v[k] for k in ("topic", "intent", "severity", "sentiment", "confidence")}
            preds.append({"review_id": rid, "status": "completed", **vd, "request_id": v["request_id"]})
            pairs.append((rid, store.review(rid)["review_text"], dict(e), vd))
        report = build_report(pairs, meta, self.vconf, self.label_config, failed)
        atomic_write_json(out_dir / "report.json", report)
        atomic_write_jsonl(out_dir / "verifier_predictions.jsonl", preds)
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["review_id", "fields", "enricher_topic", "verifier_topic", "enricher_intent", "verifier_intent",
                    "enricher_severity", "verifier_severity", "enricher_labeled_by", "text"])
        for d in report["disagreements"]:
            w.writerow([d["review_id"], "|".join(d["fields"]), d["enricher"]["topic"], d["verifier"]["topic"],
                        d["enricher"]["intent"], d["verifier"]["intent"], d["enricher"]["severity"],
                        d["verifier"]["severity"], d["enricher_labeled_by"], d["text"]])
        atomic_write_text(out_dir / "disagreements.csv", buf.getvalue())
        return report


def planted_error_test(store, cfg):
    """Corrupt one label in a TEST COPY and show the comparison flags it. No model calls.

    Uses the saved verifier predictions; the real records are never modified.
    """
    vconf, lc = cfg.stage_config("verify"), cfg.label_config()
    rows = store.verifications(vconf)
    candidates = []
    for v in rows:
        if v["status"] != "completed":
            continue
        e = store.result(v["review_id"], lc)
        if e is None or e["status"] != "completed":
            continue
        vd = {k: v[k] for k in ("topic", "intent", "severity", "sentiment", "confidence")}
        ed = dict(e)
        if not compare(ed, vd)["disagreement_fields"]:
            candidates.append((ed, vd))
    constructed = False
    if not candidates:
        # No fully agreeing pair (e.g. offline stub labels): build the test copy from the verifier's own
        # labels so the baseline agrees by construction, then plant the error on that copy.
        for v in rows:
            e = store.result(v["review_id"], lc)
            if v["status"] == "completed" and e is not None and e["status"] == "completed":
                vd = {k: v[k] for k in ("topic", "intent", "severity", "sentiment", "confidence")}
                ed = dict(e)
                ed.update({k: vd[k] for k in ("topic", "intent", "severity", "sentiment")})
                candidates.append((ed, vd))
                constructed = True
                break
    if not candidates:
        return {"status": "not_run", "reason": "no completed verifier prediction to test against"}
    original, verified = candidates[0]
    planted = dict(original)
    # The deliberately wrong label: opposite intent class, a different topic, far severity and sentiment.
    planted["intent"] = "praise" if original["intent"] in ("complaint", "cancellation") else "complaint"
    planted["topic"] = "billing" if original["topic"] != "billing" else "playback"
    planted["severity"] = 1 if int(original["severity"]) >= 3 else 5
    planted["sentiment"] = -float(original["sentiment"]) if float(original["sentiment"]) != 0 else 1.0
    before = compare(original, verified)
    after = compare(planted, verified)
    return {
        "status": "detected" if after["disagreement_fields"] else "missed",
        "review_id": original["review_id"],
        "original": {k: original[k] for k in ("topic", "intent", "severity", "sentiment")},
        "planted": {k: planted[k] for k in ("topic", "intent", "severity", "sentiment")},
        "verifier": verified,
        "comparison_before": before["disagreement_fields"],
        "comparison_after": after["disagreement_fields"],
        "baseline": ("constructed from the verifier's labels (no fully agreeing pair existed)" if constructed
                     else "a stored record on which enricher and verifier fully agree"),
        "note": "Test copy only; the stored record was not changed. Detection uses the saved verifier output.",
    }

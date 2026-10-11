"""Stage 2 - enrich (model + code).

Control flow (code decides every next step; models only answer bounded questions):

Phase A - primary pass over pending distinct texts (Jev: 1 review/request | LLM: <=50 reviews/request)
   ok + valid + confident ............................ save now (labeled_by=primary)
   ok + valid + difficult (Jev: low confidence or unclear; LLM: the model's own flag; both: an
      intent/severity contradiction) ................. stage: primary saved aside, fallback decision deferred
   invalid output ..................................... one retry, then stage for fallback (or quarantine)
   provider rejected the input (4xx) .................. stage for fallback (or quarantine)
   transient errors ................................... bounded backoff in the worker; if exhausted, re-queued
                                                        once; N in a row stops the run
   budget cap / interrupt ............................. stop admitting, finish in-flight, save, exit
Phase B - only after every primary result is in: staged reviews are ranked (no usable primary first,
   then lowest confidence, then review_id) and the first ones up to the fallback1 cap are routed;
   the rest are saved with their primary label and needs_review, or quarantined if they have none.
   fallback1 (small LLM, one review): valid -> save; invalid twice -> fallback2 if under its cap
   fallback2 (stronger LLM, one review): valid -> save; invalid twice -> keep primary + needs_review / quarantine

Ranking before routing makes the capped selection deterministic: the same reviews get the fallback
whatever the worker count, completion order or interruption points. Every review is saved, with its
exact-text aliases, in one transaction. Classification input is review_text only.
"""

import json
import math
import time
from collections import deque

from . import labels, prompts
from .config import project_path
from .control import Dispatcher, Task
from .segment import segment_spans
from .util import sha256_text, utc_now


def _fmt(x):
    return "n/a" if x is None else f"{x:.2f}"


def _public(parsed):
    return {k: parsed[k] for k in ("issue", "intent", "severity", "sentiment", "evidence_index", "confidence",
                                   "model_needs_review")}


class EnrichStage:
    def __init__(self, store, cfg, registry, ctx, stop_after=None, log=print):
        self.store, self.cfg, self.registry, self.ctx = store, cfg, registry, ctx
        self.label_config = cfg.label_config()
        self.e = cfg["enrich"]
        self.backend = self.e["backend"]
        self.stop_after = stop_after
        self.log = log
        self.finalized = 0
        self.stats = {"saved_primary": 0, "saved_fallback1": 0, "saved_fallback2": 0, "aliases_written": 0,
                      "quarantined": 0, "difficult": 0, "staged": 0, "fallback_not_selected_cap": 0,
                      "invalid_outputs": 0, "invalid_output_retries": 0, "transient_requeued": 0,
                      "left_pending_transient": 0, "left_pending_stopping": 0}
        self.disabled_tiers = set()
        if self.backend == "jev":
            self.questions = prompts.load_jev_questions(project_path(self.e["jev"]["questions"]))

    # ---- setup -----------------------------------------------------------------------------------
    def _quarantine_empty_and_reconcile(self):
        lc, rid = self.label_config, self.ctx.run_id
        empties = self.store.conn.execute(
            "SELECT review_id FROM reviews WHERE is_empty = 1 AND duplicate_id = 0 AND NOT EXISTS "
            "(SELECT 1 FROM results x WHERE x.review_id = reviews.review_id AND x.label_config = ?)", (lc,)).fetchall()
        with self.store.tx():
            for r in empties:
                self.store.insert_result({"review_id": r["review_id"], "label_config": lc, "status": "quarantined",
                                          "reason": "empty_review_text", "attempts": 0, "run_id": rid,
                                          "phase": self.ctx.phase, "completed_at": utc_now(),
                                          "detail": json.dumps({"rule": "empty or whitespace-only review_text; "
                                                                        "never sent to a model"})})
        # Aliases whose representative was saved but whose own rows were not (crash between commits).
        reps = self.store.conn.execute(
            "SELECT x.*, r.row_num AS rep_row FROM results x JOIN reviews r ON r.review_id = x.review_id AND r.duplicate_id = 0 "
            "WHERE x.label_config = ? AND x.cache_source_id IS NULL AND r.rep_row_num = r.row_num AND r.is_empty = 0",
            (lc,)).fetchall()
        fixed = 0
        for rep in reps:
            if self.store.aliases_of(rep["rep_row"], lc):
                row = {k: rep[k] for k in rep.keys() if k != "rep_row"}
                with self.store.tx():
                    fixed += self._write_aliases(row, rep["rep_row"])
        return len(empties), fixed

    def _caps(self):
        units = self.store.scope_counts()["representatives"]
        caps = {}
        for tier in ("fallback1", "fallback2"):
            r = self.cfg.role_settings(tier)
            frac = r["max_fraction"] if r["enabled"] else 0.0
            caps[tier] = max(1, int(math.floor(frac * units))) if frac > 0 else 0
        return caps

    def _routed_ids(self, tier):
        """Distinct reviews already sent to a fallback tier under this label_config (any outcome, any run)."""
        rows = self.store.conn.execute("SELECT DISTINCT review_ids FROM calls WHERE tier=? AND label_config=?",
                                       (tier, self.label_config)).fetchall()
        return {rid for r in rows for rid in json.loads(r[0])}

    # ---- request builders ------------------------------------------------------------------------
    def _rep_context(self, row):
        text = row["review_text"]
        segs = [text[s:e] for s, e in segment_spans(text)]
        return {"review_id": row["review_id"], "row_num": row["row_num"], "text": text, "segments": segs,
                "entities": labels.extract_entities(text), "code_flags": labels.code_review_flags(text),
                "trail": [], "transient_requeues": 0}

    def _staged_context(self, srow):
        rc = self._rep_context(self.store.review(srow["review_id"]))
        rc["primary"] = json.loads(srow["primary_json"]) if srow["primary_json"] else None
        rc["difficulty"] = json.loads(srow["reasons"]) if srow["reasons"] else []
        rc["trail"] = json.loads(srow["trail"]) if srow["trail"] else []
        return rc

    def _primary_task(self, reps, task_attempt=1, max_out_override=None):
        p = self.cfg.role_settings("enrich_primary")
        provider = self.registry.get(p["provider"], p["model"], p["effort"])
        if self.backend == "jev":
            rc = reps[0]
            req = prompts.jev_request(self.questions, rc["text"], rc["segments"])
            return Task(role="enrich", tier="primary", provider=provider, request=req, review_ids=[rc["review_id"]],
                        max_output_tokens=0, prompt_chars=len(json.dumps(req, ensure_ascii=False)),
                        label_config=self.label_config, task_attempt=task_attempt, context={"reps": reps})
        per = int(self.e["llm"]["max_output_tokens_per_review"])
        max_out = max_out_override or (per * len(reps) + 64)
        items = [(f"r{i + 1}", rc["segments"]) for i, rc in enumerate(reps)]
        req = prompts.enrich_batch_request(items, max_out, template=self.e["llm"]["prompt"])
        self._cost_settings(req, self.e["llm"])
        chars = len(req["system"]) + len(req["user"]) + len(json.dumps(req["schema"]))
        return Task(role="enrich", tier="primary", provider=provider, request=req,
                    review_ids=[rc["review_id"] for rc in reps], max_output_tokens=max_out, prompt_chars=chars,
                    label_config=self.label_config, task_attempt=task_attempt,
                    context={"reps": reps, "aliases": {f"r{i + 1}": rc for i, rc in enumerate(reps)}})

    def _fallback_task(self, tier, rc, task_attempt=1, max_out_override=None):
        r = self.cfg.role_settings(tier)
        provider = self.registry.get(r["provider"], r["model"], r["effort"])
        max_out = max_out_override or int(self.e[tier]["max_output_tokens"])
        req = prompts.enrich_single_request(rc["segments"], max_out, template=self.e["llm"]["prompt"])
        self._cost_settings(req, self.e[tier])
        chars = len(req["system"]) + len(req["user"]) + len(json.dumps(req["schema"]))
        return Task(role="enrich", tier=tier, provider=provider, request=req, review_ids=[rc["review_id"]],
                    max_output_tokens=max_out, prompt_chars=chars, label_config=self.label_config,
                    task_attempt=task_attempt, context={"reps": [rc]})

    @staticmethod
    def _cost_settings(req, section):
        """Cost-only request settings (never part of label_config): processing tier, timeout, cache key."""
        if section.get("service_tier"):
            req["service_tier"] = section["service_tier"]
        if section.get("timeout_s"):
            req["timeout_s"] = float(section["timeout_s"])
        req["prompt_cache_key"] = "insight-enrich-" + sha256_text(req["system"])[:12]  # stable across processes

    # ---- parsing ---------------------------------------------------------------------------------
    def parse_jev(self, data, rc):
        answers = (data or {}).get("answers", {})
        need = ["issue", "intent", "severity", "sentiment", "unclear"] + (["evidence"] if len(rc["segments"]) >= 2 else [])
        problems = [f"missing answer '{q}'" for q in need if q not in answers]
        if problems:
            return None, problems
        a = answers
        issue, intent, sev_key = a["issue"].get("choice"), a["intent"].get("choice"), a["severity"].get("choice")
        if issue not in labels.ISSUE_BY_KEY:
            problems.append(f"unknown issue {issue!r}")
        if intent not in labels.INTENTS:
            problems.append(f"unknown intent {intent!r}")
        if sev_key not in labels.SEVERITY_KEYS:
            problems.append(f"unknown severity {sev_key!r}")
        score = a["sentiment"].get("score")
        if not isinstance(score, (int, float)) or not math.isfinite(score) or not 0 <= score <= 4:
            problems.append(f"sentiment score out of range {score!r}")
        noul = a["unclear"].get("noul")
        if not isinstance(noul, (int, float)) or not 0 <= noul <= 1:
            problems.append(f"unclear probability out of range {noul!r}")
        ev_index = 0
        if len(rc["segments"]) >= 2:
            choice = str(a["evidence"].get("choice", ""))
            ev_index = int(choice[1:]) - 1 if choice[:1] == "s" and choice[1:].isdigit() else -1
            if not 0 <= ev_index < len(rc["segments"]):
                problems.append(f"evidence option {choice!r} not among {len(rc['segments'])} sentences")
        if problems:
            return None, problems
        return {
            "issue": issue, "intent": intent, "severity": labels.SEVERITY_KEYS[sev_key],
            "sentiment": round(max(-1.0, min(1.0, score / 2 - 1)), 2),  # score 0..4 -> -1..1 (TypeSafe docs)
            "evidence_index": ev_index,
            "confidence": {"issue": a["issue"].get("confidence"), "intent": a["intent"].get("confidence"),
                           "severity": a["severity"].get("confidence"), "sentiment": a["sentiment"].get("confidence"),
                           "unclear_probability": noul},
            "model_needs_review": None,
        }, []

    @staticmethod
    def parse_llm_item(item, rc):
        if not isinstance(item, dict):
            return None, ["result is not an object"]
        issue, intent, sev, sent = item.get("issue"), item.get("intent"), item.get("sev"), item.get("sent")
        ev, nr = item.get("quote"), item.get("flag")
        problems = []
        if issue not in labels.ISSUE_BY_KEY:
            problems.append(f"unknown issue {issue!r}")
        if intent not in labels.INTENTS:
            problems.append(f"unknown intent {intent!r}")
        if type(sev) is not int or not 1 <= sev <= 5:
            problems.append(f"sev {sev!r} not an integer 1-5")
        if type(sent) is not int or not -2 <= sent <= 2:
            problems.append(f"sent {sent!r} not an integer -2..2")
        if type(ev) is not int or not 1 <= ev <= len(rc["segments"]):
            problems.append(f"quote {ev!r} not within 1..{len(rc['segments'])}")
        if type(nr) is not bool:
            problems.append("flag is not a boolean")
        if problems:
            return None, problems
        return {"issue": issue, "intent": intent, "severity": sev, "sentiment": round(sent / 2, 2),
                "evidence_index": ev - 1, "confidence": None, "model_needs_review": nr}, []

    def difficulty(self, parsed):
        reasons = []
        c = parsed["confidence"]
        if c:
            j = self.e["jev"]
            for field, key in (("issue", "min_confidence_issue"), ("intent", "min_confidence_intent"),
                               ("severity", "min_confidence_severity")):
                if (c[field] or 0) < j[key]:
                    reasons.append(f"{field} confidence {_fmt(c[field])} < {j[key]}")
            if (c["unclear_probability"] or 0) > j["max_unclear_probability"]:
                reasons.append(f"unclear probability {_fmt(c['unclear_probability'])} > {j['max_unclear_probability']}")
        reasons += labels.consistency_problems(parsed["intent"], parsed["severity"])
        return reasons

    @staticmethod
    def priority(parsed):
        """Routing order for staged reviews: lower = routed first. No usable primary label = -1."""
        if parsed is None:
            return -1.0
        c = parsed.get("confidence")
        if not c:  # LLM primary: contradictions first, then the model's own ambiguity flag
            if labels.consistency_problems(parsed["intent"], parsed["severity"]):
                return 0.0
            return 0.5 if parsed.get("model_needs_review") else 1.0
        vals = [c.get("issue"), c.get("intent"), c.get("severity")]
        base = min(v if isinstance(v, (int, float)) else 0.0 for v in vals)
        if labels.consistency_problems(parsed["intent"], parsed["severity"]):
            base = min(base, 0.0)
        return round(base, 6)

    # ---- persistence -------------------------------------------------------------------------------
    def _record_fields(self, rc, parsed, labeled_by, needs_review, detail):
        issue = labels.ISSUE_BY_KEY[parsed["issue"]]
        severity = parsed["severity"]
        problems = labels.consistency_problems(parsed["intent"], severity)
        if problems:
            detail["reconciled"] = {"from_severity": severity, "rule": problems}
            severity = labels.reconcile(parsed["intent"], severity)
            needs_review = True
        quote = rc["segments"][parsed["evidence_index"]]
        if not quote.strip() or quote not in rc["text"]:
            raise AssertionError("evidence quote must be an exact substring of the review")
        return {
            "review_id": rc["review_id"], "label_config": self.label_config, "status": "completed",
            "topic": issue["topic"], "subtopic": issue["subtopic"], "intent": parsed["intent"],
            "sentiment": float(parsed["sentiment"]), "severity": int(severity),
            "entities": json.dumps(rc["entities"], ensure_ascii=False), "evidence_quote": quote,
            "needs_review": int(bool(needs_review)), "cache_source_id": None, "labeled_by": labeled_by,
            "reason": None, "attempts": len(rc["trail"]), "detail": json.dumps(detail, ensure_ascii=False),
            "run_id": self.ctx.run_id, "phase": self.ctx.phase, "completed_at": utc_now(),
        }

    def _write_aliases(self, rep_row: dict, rep_row_num: int) -> int:
        n = 0
        for a in self.store.aliases_of(rep_row_num, self.label_config):
            alias = dict(rep_row)
            alias.update({"review_id": a["review_id"], "cache_source_id": rep_row["review_id"], "labeled_by": "cache",
                          "attempts": 0, "run_id": self.ctx.run_id, "phase": self.ctx.phase, "completed_at": utc_now(),
                          "detail": json.dumps({"cache_of": rep_row["review_id"],
                                                "match": "identical review_text and identical label_config"})})
            if rep_row["status"] == "quarantined":
                alias["cache_source_id"] = None
                alias["reason"] = f"{rep_row['reason']} (identical text to {rep_row['review_id']})"
            if self.store.insert_result(alias):
                n += 1
        return n

    def _save(self, rc, row):
        with self.store.tx():
            inserted = self.store.insert_result(row)
            aliases = self._write_aliases(row, rc["row_num"]) if inserted else 0
            self.store.unstage(rc["review_id"], self.label_config)
        self.stats["aliases_written"] += aliases
        self.finalized += 1
        if self.stop_after and self.finalized >= self.stop_after:
            self.ctx.request_stop("simulated_interruption")

    def _finalize(self, rc, parsed, labeled_by, needs_review, detail):
        self._save(rc, self._record_fields(rc, parsed, labeled_by, needs_review, detail))
        self.stats[f"saved_{labeled_by}"] += 1

    def _quarantine(self, rc, reason):
        row = {"review_id": rc["review_id"], "label_config": self.label_config, "status": "quarantined",
               "reason": reason, "attempts": len(rc["trail"]), "run_id": self.ctx.run_id, "phase": self.ctx.phase,
               "completed_at": utc_now(), "detail": json.dumps({"trail": rc["trail"]}, ensure_ascii=False)}
        self._save(rc, row)
        self.stats["quarantined"] += 1

    def _stage(self, rc, parsed, reasons):
        with self.store.tx():
            self.store.stage({"review_id": rc["review_id"], "label_config": self.label_config,
                              "priority": self.priority(parsed),
                              "primary_json": json.dumps(_public(parsed)) if parsed else None,
                              "reasons": json.dumps(reasons), "trail": json.dumps(rc["trail"], ensure_ascii=False),
                              "run_id": self.ctx.run_id, "created_at": utc_now()})
        self.stats["staged"] += 1

    def _defer(self, rc, why):
        """Leave the review unsaved; the next invocation continues it (staged reviews stay staged)."""
        self.stats["left_pending_stopping"] += 1
        self.store.event(self.ctx.run_id, "enrich", "deferred", review_id=rc["review_id"], why=why)

    def _mark_invalid(self, request_id, problems):
        self.stats["invalid_outputs"] += 1
        self.store.call_settled(request_id, {"outcome": "failed", "valid_output": 0,
                                             "error": "invalid_output: " + "; ".join(problems)[:400]})

    # ---- routing helpers -----------------------------------------------------------------------------
    def _usable(self, tier):
        r = self.cfg.role_settings(tier)
        return r["enabled"] and tier not in self.disabled_tiers and self.caps[tier] > 0

    def _needs_fallback(self, rc, parsed, reasons):
        """Phase A: stage when a fallback could help, otherwise decide now."""
        if self._usable("fallback1"):
            self._stage(rc, parsed, reasons)
            return
        if parsed is None:
            self._quarantine(rc, "; ".join(reasons) or "no usable primary output")
            return
        self.stats["fallback_not_selected_cap"] += 1
        detail = {"trail": rc["trail"], "primary": _public(parsed), "difficulty": reasons, "code_flags": rc["code_flags"],
                  "fallback": "not used: fallback1 disabled"}
        self._finalize(rc, parsed, "primary", True, detail)

    # ---- main loop -----------------------------------------------------------------------------------
    def run(self):
        ctx, store = self.ctx, self.store
        quarantined_empty, reconciled_aliases = self._quarantine_empty_and_reconcile()
        pending = store.pending_representatives(self.label_config)  # rows; contexts are built at submit time
        self.caps = self._caps()
        self.routed = {t: self._routed_ids(t) for t in ("fallback1", "fallback2")}
        staged_before = len(store.staged_list(self.label_config))
        self.log(f"[enrich] label_config = {self.label_config}")
        self.log(f"[enrich] pending distinct texts: {len(pending)} | staged for a fallback decision: {staged_before} | "
                 f"fallback caps {self.caps} | already routed { {t: len(v) for t, v in self.routed.items()} } | "
                 f"backend {self.backend} | workers {self.cfg['run']['workers']}")
        store.event(ctx.run_id, "enrich", "start", pending=len(pending), staged=staged_before, caps=self.caps,
                    routed={t: len(v) for t, v in self.routed.items()}, label_config=self.label_config,
                    empty_quarantined=quarantined_empty, aliases_reconciled=reconciled_aliases)
        disp = Dispatcher(ctx, int(self.cfg["run"]["workers"]), int(self.cfg["run"]["max_in_flight_per_worker"]))
        try:
            self._phase_a(disp, deque(pending))
            if not ctx.stop_admitting.is_set():
                if store.pending_representatives(self.label_config):
                    self.log("[enrich] some primary requests failed transiently; fallback decisions wait for a resumed run")
                else:
                    self._phase_b(disp)
        finally:
            disp.shutdown()
        self.stats["still_pending"] = len(store.pending_representatives(self.label_config, include_staged=True))
        store.event(ctx.run_id, "enrich", "end", stop_reason=ctx.stop_reason, **self.stats)
        return dict(self.stats, caps=self.caps, routed={t: len(v) for t, v in self.routed.items()},
                    stop_reason=ctx.stop_reason)

    def _progress(self, label, total, force=False):
        """One progress line every progress_every_s seconds (visible in recordings and logs)."""
        now = time.monotonic()
        if not force and now - self._last_progress < float(self.cfg["run"].get("progress_every_s", 15)):
            return
        self._last_progress = now
        led = self.ctx.ledger.snapshot()
        done = self.finalized
        rate = done / (now - self._t0) if now > self._t0 else 0
        self.log(f"[enrich] {label}: {done} distinct texts saved this invocation (of {total} pending at start) | "
                 f"{rate:.1f}/s | staged {self.stats['staged']} | spent ${led['spent_usd']:.4f} of ${led['cap_usd']:.2f} "
                 f"(reserved ${led['reserved_usd']:.4f})")

    def _phase_a(self, disp, queue):
        ctx = self.ctx
        batch_n = int(self.e["llm_batch_size"]) if self.backend == "llm" else 1
        self._t0 = self._last_progress = time.monotonic()
        total = len(queue)
        while True:
            self._progress("primary", total)
            while queue and disp.capacity() > 0 and not ctx.stop_admitting.is_set():
                # queue items are DB rows (context built lazily, keeps memory flat) or re-queued contexts
                items = [queue.popleft() for _ in range(min(batch_n, len(queue)))]
                disp.submit(self._primary_task([i if isinstance(i, dict) else self._rep_context(i) for i in items]))
            if not disp.in_flight:
                break
            for task, outcome in disp.wait_some():
                if outcome.status == "ok":
                    ctx.consecutive_failures = 0
                if task.tier == "primary":
                    self._on_primary(task, outcome, disp, queue)
                else:
                    self._on_fallback(task, outcome, disp)

    def _phase_b(self, disp):
        ctx, store = self.ctx, self.store
        staged = store.staged_list(self.label_config)
        if not staged:
            return
        routed = self.routed["fallback1"]
        usable = self._usable("fallback1")
        already = [s for s in staged if s["review_id"] in routed] if usable else []
        fresh = [s for s in staged if s["review_id"] not in routed or not usable]
        k = max(0, self.caps["fallback1"] - len(routed)) if usable else 0
        selected, rest = already + fresh[:k], fresh[k:]
        self.log(f"[enrich] fallback decisions: {len(staged)} staged | routing {len(selected)} to fallback1 "
                 f"(cap {self.caps['fallback1']}, already routed {len(routed)}) | {len(rest)} keep their primary label")
        store.event(ctx.run_id, "enrich", "fallback_selection", staged=len(staged), selected=len(selected),
                    not_selected=len(rest), cap=self.caps["fallback1"], already_routed=len(routed),
                    order="no usable primary first, then lowest confidence, then review_id")
        for rank, s in enumerate(rest, start=len(selected) + 1):
            rc = self._staged_context(s)
            if rc["primary"]:
                self.stats["fallback_not_selected_cap"] += 1
                detail = {"trail": rc["trail"], "primary": rc["primary"], "difficulty": rc["difficulty"],
                          "code_flags": rc["code_flags"],
                          "fallback": f"not selected: rank {rank} of {len(staged)} staged, cap {self.caps['fallback1']}"}
                self._finalize(rc, dict(rc["primary"]), "primary", True, detail)
            else:
                self._quarantine(rc, "; ".join(rc["difficulty"]) + " (fallback cap reached)")
        queue = deque(self._staged_context(s) for s in selected)
        while True:
            while queue and disp.capacity() > 0 and not ctx.stop_admitting.is_set():
                rc = queue.popleft()
                routed.add(rc["review_id"])
                disp.submit(self._fallback_task("fallback1", rc))
            if not disp.in_flight:
                break
            for task, outcome in disp.wait_some():
                if outcome.status == "ok":
                    ctx.consecutive_failures = 0
                self._on_fallback(task, outcome, disp)

    # ---- outcome handlers ------------------------------------------------------------------------------
    def _on_primary(self, task, outcome, disp, queue):
        reps = task.context["reps"]
        if outcome.status == "ok":
            if self.backend == "jev":
                self._jev_result(task, outcome, reps[0], disp)
            else:
                self._llm_batch_result(task, outcome, disp)
            return
        for rc in reps:
            rc["trail"].append({"tier": "primary", "status": outcome.status, "error": outcome.error,
                                "request_id": outcome.request_id})
        ctx = self.ctx
        if outcome.status == "permanent_input":
            for rc in reps:
                self._needs_fallback(rc, None, [f"provider rejected input: {outcome.error}"])
        elif outcome.status == "invalid_output":
            self._retry_or_stage(task, reps, disp, truncated=False)
        elif outcome.status == "transient":
            ctx.consecutive_failures += 1
            if ctx.consecutive_failures >= int(self.cfg["run"]["circuit_breaker_failures"]):
                ctx.request_stop(f"circuit_breaker: {ctx.consecutive_failures} requests in a row exhausted retries")
            for rc in reps:
                if rc["transient_requeues"] < 1 and not ctx.stop_admitting.is_set():
                    rc["transient_requeues"] += 1
                    self.stats["transient_requeued"] += 1
                    queue.append(rc)  # one more chance at the end of this invocation
                else:
                    self.stats["left_pending_transient"] += 1
        elif outcome.status == "budget":
            ctx.request_stop("budget_cap")
        elif outcome.status == "systemic":
            ctx.request_stop(f"systemic_provider_error: {outcome.error}")
        # cancelled: stays pending

    def _retry_or_stage(self, task, reps, disp, truncated):
        if task.task_attempt == 1:
            if self.ctx.stop_admitting.is_set():
                for rc in reps:
                    self._defer(rc, "invalid output retry needed but the run is stopping")
                return
            self.stats["invalid_output_retries"] += 1
            bigger = task.max_output_tokens * 2 if truncated and task.max_output_tokens else None
            if self.backend == "jev":
                for rc in reps:
                    disp.submit(self._primary_task([rc], task_attempt=2))
            else:
                disp.submit(self._primary_task(reps, task_attempt=2, max_out_override=bigger))
            return
        for rc in reps:
            self._needs_fallback(rc, None, ["primary invalid output after one retry"])

    def _jev_result(self, task, outcome, rc, disp):
        parsed, problems = self.parse_jev(outcome.result.data, rc)
        if parsed is None:
            self._mark_invalid(outcome.request_id, problems)
            rc["trail"].append({"tier": "primary", "status": "invalid", "problems": problems, "request_id": outcome.request_id})
            self._retry_or_stage(task, [rc], disp, truncated=False)
            return
        rc["trail"].append({"tier": "primary", "status": "valid", "request_id": outcome.request_id})
        rc["primary"] = _public(parsed)
        reasons = self.difficulty(parsed)
        rc["difficulty"] = reasons
        if reasons:
            self.stats["difficult"] += 1
            self._needs_fallback(rc, parsed, reasons)
            return
        self._finalize(rc, parsed, "primary", bool(rc["code_flags"]),
                       {"trail": rc["trail"], "primary": rc["primary"], "difficulty": [], "code_flags": rc["code_flags"]})

    def _llm_batch_result(self, task, outcome, disp):
        result = outcome.result
        aliases = task.context["aliases"]
        items = result.data.get("results") if isinstance(result.data, dict) else None
        seen, retry, problems_all = set(), [], []
        if not isinstance(items, list):
            problems_all.append(f"no results array ({result.finish})")
            items = []
        for item in items:
            alias = item.get("id") if isinstance(item, dict) else None
            rc = aliases.get(alias)
            if rc is None or alias in seen:
                problems_all.append(f"unexpected or duplicate id {alias!r}")
                continue
            seen.add(alias)
            parsed, problems = self.parse_llm_item(item, rc)
            if parsed is None:
                problems_all.append(f"{alias}: " + "; ".join(problems))
                retry.append(rc)
                continue
            rc["trail"].append({"tier": "primary", "status": "valid", "request_id": outcome.request_id})
            rc["primary"] = _public(parsed)
            reasons = labels.consistency_problems(parsed["intent"], parsed["severity"])
            if parsed["model_needs_review"]:
                reasons = reasons + ["model flagged the review as ambiguous"]
            rc["difficulty"] = reasons
            if reasons:
                self.stats["difficult"] += 1
                self._needs_fallback(rc, parsed, reasons)
                continue
            self._finalize(rc, parsed, "primary", bool(rc["code_flags"]),
                           {"trail": rc["trail"], "primary": rc["primary"], "difficulty": [],
                            "code_flags": rc["code_flags"]})
        missing = [rc for a, rc in aliases.items() if a not in seen]
        if missing:
            problems_all.append(f"missing ids {[a for a in aliases if a not in seen]}")
        retry += missing
        if problems_all:
            if len(retry) < len(aliases):
                self.store.call_settled(outcome.request_id, {"valid_output": 0,
                                                             "notes": "partially valid: " + "; ".join(problems_all)[:400]})
            else:
                self._mark_invalid(outcome.request_id, problems_all)
        for rc in retry:
            rc["trail"].append({"tier": "primary", "status": "invalid", "request_id": outcome.request_id})
        if retry:
            self._retry_or_stage(task, retry, disp, truncated=result.finish == "truncated")

    def _on_fallback(self, task, outcome, disp):
        rc, tier = task.context["reps"][0], task.tier
        if outcome.status == "ok":
            data = outcome.result.data
            parsed, problems = (self.parse_llm_item(data, rc) if data is not None
                                else (None, [f"unusable output: {outcome.result.finish}"]))
            if parsed:
                rc["trail"].append({"tier": tier, "status": "valid", "request_id": outcome.request_id})
                detail = {"trail": rc["trail"], "primary": rc.get("primary"), tier: _public(parsed),
                          "code_flags": rc["code_flags"], "difficulty": rc.get("difficulty")}
                self._finalize(rc, parsed, tier, bool(parsed["model_needs_review"]) or bool(rc["code_flags"]), detail)
                return
            self._mark_invalid(outcome.request_id, problems)
            rc["trail"].append({"tier": tier, "status": "invalid", "problems": problems, "request_id": outcome.request_id})
            if task.task_attempt == 1:
                if self.ctx.stop_admitting.is_set():
                    self._defer(rc, f"{tier} retry needed but the run is stopping")
                    return
                self.stats["invalid_output_retries"] += 1
                bigger = task.max_output_tokens * 2 if outcome.result.finish == "truncated" else None
                disp.submit(self._fallback_task(tier, rc, task_attempt=2, max_out_override=bigger))
                return
            if (tier == "fallback1" and self._usable("fallback2") and len(self.routed["fallback2"]) < self.caps["fallback2"]
                    and not self.ctx.stop_admitting.is_set()):
                # Rare path (fallback1 invalid twice); routed immediately while under the fallback2 cap.
                self.routed["fallback2"].add(rc["review_id"])
                disp.submit(self._fallback_task("fallback2", rc))
                return
            self._keep_primary_or_quarantine(rc, f"{tier} output invalid after one retry")
            return
        rc["trail"].append({"tier": tier, "status": outcome.status, "error": outcome.error, "request_id": outcome.request_id})
        if outcome.status == "systemic":
            self.disabled_tiers.add(tier)
            self.store.event(self.ctx.run_id, "enrich", "tier_disabled", tier=tier, error=outcome.error)
            self._keep_primary_or_quarantine(rc, f"{tier} disabled after provider error")
            return
        if outcome.status == "budget":
            self.ctx.request_stop("budget_cap")
        if outcome.status == "transient":
            self.ctx.consecutive_failures += 1
            if self.ctx.consecutive_failures >= int(self.cfg["run"]["circuit_breaker_failures"]):
                self.ctx.request_stop("circuit_breaker: fallback provider keeps failing")
        self._defer(rc, f"{tier} {outcome.status}")  # still staged; a resumed run retries it

    def _keep_primary_or_quarantine(self, rc, reason):
        primary = rc.get("primary")
        if primary:
            detail = {"trail": rc["trail"], "primary": primary, "difficulty": rc.get("difficulty"),
                      "code_flags": rc["code_flags"], "fallback": f"not completed: {reason}"}
            self._finalize(rc, dict(primary), "primary", True, detail)
        else:
            self._quarantine(rc, reason)

"""Exports: the contract's grading/ folder plus the internal enriched table and logs.

records.jsonl has exactly one line per source review_id (first occurrence, source order):
completed records carry the common labels; quarantined ones carry a reason. Reviews still
pending when a run stopped are exported as quarantined with reason 'unfinished: <why>' so
they stay visible and count against the completed fraction (never silently dropped).
"""

import json
import shutil

from .util import atomic_write_json, atomic_write_jsonl, read_json, rel, utc_now

LABEL_FIELDS = ("topic", "intent", "sentiment", "severity", "entities", "evidence_quote", "needs_review", "label_config")


def record_lines(store, label_config, unfinished_reason):
    rows = store.conn.execute(
        "SELECT r.row_num, r.review_id, r.source_sha256, x.* FROM reviews r "
        "LEFT JOIN results x ON x.review_id = r.review_id AND x.label_config = ? "
        "WHERE r.duplicate_id = 0 ORDER BY r.row_num", (label_config,))
    for row in rows:
        rid, src = row[1], row[2]
        if row["status"] is None:
            yield {"review_id": rid, "source_sha256": src, "status": "quarantined",
                   "reason": f"unfinished: {unfinished_reason}"}
        elif row["status"] == "quarantined":
            yield {"review_id": rid, "source_sha256": src, "status": "quarantined", "reason": row["reason"]}
        else:
            rec = {"review_id": rid, "source_sha256": src, "status": "completed", "topic": row["topic"],
                   "intent": row["intent"], "sentiment": float(row["sentiment"]), "severity": int(row["severity"]),
                   "entities": json.loads(row["entities"]), "evidence_quote": row["evidence_quote"],
                   "needs_review": bool(row["needs_review"]), "label_config": row["label_config"],
                   "subtopic": row["subtopic"], "labeled_by": row["labeled_by"]}
            if row["cache_source_id"]:
                rec["cache_source_id"] = row["cache_source_id"]
            yield rec


def call_lines(store):
    for c in store.iter_calls():
        outcome = c["outcome"]
        usage_reported = c["input_tokens"] is not None
        line = {
            "request_id": c["request_id"], "role": c["role"], "review_ids": json.loads(c["review_ids"]),
            "model": c["model"], "phase": c["phase"],
            "outcome": "succeeded" if outcome == "succeeded" else "failed",
            "label_config": c["label_config"] if c["role"] == "enrich" else (c["stage_config"] or ""),
            "input_tokens": int(c["input_tokens"] or 0), "output_tokens": int(c["output_tokens"] or 0),
            "usage_reported": usage_reported,
            "tier": c["tier"], "provider": c["provider"], "effort": c["effort"], "run_id": c["run_id"],
            "attempt": c["attempt"], "task_attempt": c["task_attempt"],
            "cached_input_tokens": int(c["cached_input_tokens"] or 0), "reasoning_tokens": int(c["reasoning_tokens"] or 0),
            "cost_usd": c["cost_usd"], "reserved_usd": c["reserved_usd"], "started_at": c["started_at"],
            "duration_s": c["duration_s"], "provider_request_id": c["provider_request_id"],
            "model_reported": c["model_reported"], "finish": c["finish"], "error": c["error"],
            "worker": c["worker"], "max_output_tokens": c["max_output_tokens"],
        }
        if not usage_reported:
            line["usage_note"] = "provider returned no usage for this attempt; zeros are placeholders, not measurements"
        if outcome in ("unknown", "dispatched"):
            line["reconciled_unknown_outcome"] = True
        yield line


def checkpoint_snapshots(store):
    d = store.run_dir / "checkpoints"
    snaps = []
    if d.exists():
        for p in sorted(d.glob("*.json")):
            snaps.append(read_json(p))
    snaps.sort(key=lambda s: s.get("written_at", ""))
    return snaps


def export(store, cfg, grading_dir=None, unfinished_reason="run stopped before this review was classified",
           compress_over=200_000):
    run_dir = store.run_dir
    lc = cfg.label_config()
    grading = grading_dir or (run_dir / "grading")
    grading.mkdir(parents=True, exist_ok=True)
    meta = store.get_meta("input")
    n_rows = store.scope_counts()["unique_ids"]
    big = n_rows > compress_over
    for stale in ("records.jsonl", "records.jsonl.gz", "calls.jsonl", "calls.jsonl.gz"):
        (grading / stale).unlink(missing_ok=True)
    full = store.get_meta("full_input")
    if n_rows == 660622:
        note = "Full-corpus run."
    elif full and n_rows >= 100000:
        note = (f"Declared analysis scope: {n_rows} rows of {meta['path']} (a deterministic uniform sample of the full "
                f"file plus every empty-text row; regenerate with scripts/make_analysis_subset.py). ingestion.json "
                f"profiles the full file {full['path']}. Rows outside the scope were ingested but not classified.")
    else:
        note = "Development checkpoint export, not the final submission."
    run_json = {"version": "a5-audit-v1", "analysis_count": n_rows, "analysis_sha256": meta["sha256"],
                "classification_input_fields": ["review_text"], "allow_multi_issue": False,
                "input_file": meta["path"], "full_source": full, "label_config": lc,
                "offline_stub": bool(cfg.offline_stub), "scope_note": note, "exported_at": utc_now()}
    atomic_write_json(grading / "run.json", run_json)
    if (run_dir / "ingestion.json").exists():
        shutil.copyfile(run_dir / "ingestion.json", grading / "ingestion.json")
    n_records = atomic_write_jsonl(grading / ("records.jsonl.gz" if big else "records.jsonl"),
                                   record_lines(store, lc, unfinished_reason), compress=big)
    for name in ("membership.csv", "ranking.csv", "claims.csv"):
        if (run_dir / name).exists():
            shutil.copyfile(run_dir / name, grading / name)
    n_calls = atomic_write_jsonl(grading / ("calls.jsonl.gz" if big else "calls.jsonl"), call_lines(store), compress=big)
    snaps = checkpoint_snapshots(store)
    stopped = [s for s in snaps if s.get("status") != "completed" and s.get("completed_ids")]
    before = stopped[0] if stopped else None
    after = snaps[-1] if snaps else None
    atomic_write_json(grading / "checkpoint_before.json",
                      {"completed_ids": before["completed_ids"] if before else [],
                       "run_id": before["run_id"] if before else None,
                       "status": before["status"] if before else "no interrupted invocation recorded",
                       "stop_reason": before.get("stop_reason") if before else None}, indent=None)
    atomic_write_json(grading / "checkpoint_after.json",
                      {"completed_ids": after["completed_ids"] if after else [],
                       "run_id": after["run_id"] if after else None,
                       "status": after["status"] if after else None}, indent=None)
    # Internal table with every extra field, and the quarantine log (streamed, one row at a time).
    def full_rows(status):
        for r in store.iter_results(lc, status):
            d = dict(r)
            d["entities"] = json.loads(d["entities"]) if d["entities"] else None
            d["detail"] = json.loads(d["detail"]) if d["detail"] else None
            yield d

    atomic_write_jsonl(run_dir / ("enriched.jsonl.gz" if big else "enriched.jsonl"), full_rows("completed"), compress=big)
    atomic_write_jsonl(run_dir / "quarantine.jsonl", full_rows("quarantined"))

    def events():
        for e in store.conn.execute("SELECT * FROM events ORDER BY id"):
            d = dict(e)
            d["detail"] = json.loads(d["detail"]) if d["detail"] else None
            yield d

    atomic_write_jsonl(run_dir / "run_log.jsonl", events())
    return {"grading_dir": rel(grading), "records": n_records, "calls": n_calls,
            "checkpoint_before": len(before["completed_ids"]) if before else 0,
            "checkpoint_after": len(after["completed_ids"]) if after else 0}

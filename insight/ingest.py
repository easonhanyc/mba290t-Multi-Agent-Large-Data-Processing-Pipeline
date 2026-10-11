"""Stage 1 - ingest (code only): stream the CSV, hash rows, profile, deduplicate, queue.

Only the six source fields are stored. Any other column in the input (for example the
human label columns of golden_50_to_label.csv) is ignored and reported, so golden answers
can never reach a model prompt.
"""

import csv
import statistics
from collections import Counter
from pathlib import Path

from . import labels
from .checker_bridge import FIELDS, helper_profile, row_sha
from .util import atomic_write_json, rel, sha256_file, sha256_text, utc_now

BATCH = 5000


class InputMismatch(RuntimeError):
    pass


def _rows(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, strict=True)
        header = reader.fieldnames or []
        if len(set(header)) != len(header):
            raise ValueError("Duplicate CSV headers")
        missing = [k for k in FIELDS if k not in header]
        if missing:
            raise ValueError(f"Input CSV lacks required columns: {missing}")
        yield [h for h in header if h not in FIELDS]
        for row in reader:
            if None in row or any(row.get(k) is None for k in FIELDS):
                raise ValueError(f"Malformed CSV row near line {reader.line_num}")
            yield {k: row[k] for k in FIELDS}


def full_file_accounting(store, full_path: Path) -> dict:
    """Stream the full source CSV once: every analysis row must exist there with an identical row hash."""
    expected = {r[0]: r[1] for r in store.conn.execute("SELECT review_id, source_sha256 FROM reviews WHERE duplicate_id=0")}
    matched, mismatched, total, empty_total, empty_in_scope = 0, [], 0, 0, 0
    for row in _iter_full(full_path):
        total += 1
        rid = row["review_id"]
        empty = not row["review_text"].strip()
        empty_total += empty
        sha = expected.get(rid)
        if sha is None:
            continue
        if row_sha(row) == sha:
            matched += 1
            empty_in_scope += empty
        else:
            mismatched.append(rid)
    missing = len(expected) - matched - len(mismatched)
    if mismatched or missing:
        raise InputMismatch(f"Declared analysis rows differ from the full file: {len(mismatched)} changed, "
                            f"{missing} absent (first: {mismatched[:3]})")
    return {"full_rows": total, "analysis_rows_matched_in_full_file": matched, "out_of_scope_rows": total - matched,
            "empty_text_rows_in_full_file": empty_total, "empty_text_rows_in_scope": empty_in_scope}


def _iter_full(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f, strict=True):
            yield {k: row[k] for k in FIELDS}


def ingest(store, csv_path, cfg, run_id, full_path=None) -> dict:
    csv_path = Path(csv_path).resolve()
    file_sha = sha256_file(csv_path)
    known = store.get_meta("input")
    if known:
        if known["sha256"] != file_sha:
            raise InputMismatch(f"This run directory was created for input {known['path']} ({known['sha256'][:12]}...); "
                                f"{rel(csv_path)} has a different checksum. Use a new --run-dir.")
        store.event(run_id, "ingest", "reused_saved_ingestion", sha256=file_sha)
        return store.get_meta("ingestion_report")

    started = utc_now()
    gen = _rows(csv_path)
    ignored_columns = next(gen)
    seen_ids = set()
    batch = []
    stats = Counter()
    months, ratings = Counter(), Counter()
    lengths = []
    first = last = None
    row_num = 0
    with store.tx():
        for row in gen:
            row_num += 1
            rid = row["review_id"]
            dup = rid in seen_ids
            seen_ids.add(rid)
            text = row["review_text"]
            empty = not text.strip()
            stats["records"] += 1
            stats["duplicate_review_ids"] += dup
            stats["empty_review_text"] += empty
            stats["missing_app_version"] += not row["app_version"].strip()
            stats["invalid_rating"] += row["review_rating"] not in {"1", "2", "3", "4", "5"}
            stats["multiline_text"] += ("\n" in text or "\r" in text)
            if not empty:
                lengths.append(len(text))
                flags = labels.code_review_flags(text)
                stats["no_letter_text"] += "no_letters" in flags
                stats["mostly_non_latin_text"] += "mostly_non_latin_script" in flags
            months[row["review_timestamp"][:7]] += 1
            ratings[row["review_rating"]] += 1
            ts = row["review_timestamp"]
            first = ts if first is None or ts < first else first
            last = ts if last is None or ts > last else last
            batch.append((row_num, rid, text, row["review_rating"], row["review_likes"], row["app_version"],
                          row["review_timestamp"], row_sha(row), sha256_text(text), int(empty), int(dup)))
            if len(batch) >= BATCH:
                store.insert_reviews(batch)
                batch.clear()
        if batch:
            store.insert_reviews(batch)
        store.assign_representatives(bool(cfg["enrich"]["exact_text_reuse"]))
    counts = store.scope_counts()
    dup_groups = store.conn.execute(
        "SELECT review_text, COUNT(*) n FROM reviews WHERE is_empty=0 AND duplicate_id=0 "
        "GROUP BY text_sha256 HAVING n > 1 ORDER BY n DESC, MIN(row_num) LIMIT 15").fetchall()
    rows_in_dup_groups = store.conn.execute(
        "SELECT COALESCE(SUM(n),0) FROM (SELECT COUNT(*) n FROM reviews WHERE is_empty=0 AND duplicate_id=0 "
        "GROUP BY text_sha256 HAVING n > 1)").fetchone()[0]
    lengths.sort()
    report = {
        "stage": "ingest", "owner": "code", "run_id": run_id, "started_at": started, "finished_at": utc_now(),
        "input": {"path": rel(csv_path), "sha256": file_sha, "bytes": csv_path.stat().st_size,
                  "ignored_columns": ignored_columns,
                  "note": "Only the six source fields are stored; ignored columns never reach any model."},
        "counts": {
            "records": stats["records"],
            "unique_review_ids": counts["unique_ids"],
            "duplicate_review_id_rows": stats["duplicate_review_ids"],
            "empty_review_text": stats["empty_review_text"],
            "nonempty_to_classify": counts["nonempty"],
            "distinct_nonempty_texts": counts["distinct_nonempty_texts"],
            "rows_in_exact_duplicate_text_groups": rows_in_dup_groups,
            "exact_text_cache_aliases": counts["nonempty"] - counts["representatives"],
            "first_pass_model_work_units": counts["representatives"],
            "missing_app_version": stats["missing_app_version"],
            "invalid_rating": stats["invalid_rating"],
            "multiline_text": stats["multiline_text"],
            "no_letter_text": stats["no_letter_text"],
            "mostly_non_latin_text": stats["mostly_non_latin_text"],
        },
        "text_length_chars": {
            "min": lengths[0] if lengths else None,
            "median": statistics.median(lengths) if lengths else None,
            "p90": lengths[int(0.9 * (len(lengths) - 1))] if lengths else None,
            "max": lengths[-1] if lengths else None,
            "mean": round(statistics.fmean(lengths), 1) if lengths else None,
        },
        "first_review": first, "last_review": last,
        "reviews_by_month": dict(sorted(months.items())),
        "reviews_by_rating": dict(sorted(ratings.items())),
        "top_duplicate_texts": [{"text": r["review_text"][:80], "rows": r["n"]} for r in dup_groups],
        "exact_text_reuse": bool(cfg["enrich"]["exact_text_reuse"]),
        "handling": {
            "empty_text": "quarantined with reason empty_review_text; never sent to a model",
            "missing_app_version": "kept; app_version is metadata and never used for classification",
            "duplicate_review_id": "first occurrence kept; later rows reported here and excluded",
            "exact_duplicate_text": "one model result per distinct text; other rows get cache_source_id provenance",
            "classification_input": "review_text only (stars, likes, version and timestamp stay metadata)",
        },
    }
    store.set_meta("input", {"path": rel(csv_path), "sha256": file_sha, "bytes": report["input"]["bytes"],
                             "rows": stats["records"], "ingested_at": utc_now()})
    store.set_meta("ingestion_report", report)
    run_dir = store.run_dir
    atomic_write_json(run_dir / "ingestion_report.json", report)
    profile_target = Path(full_path).resolve() if full_path else csv_path
    try:
        prof = helper_profile(cfg.data["paths"]["checker_abs"], profile_target)
        atomic_write_json(run_dir / "ingestion.json", prof)
        report["helper_profile"] = (f"ingestion.json: full-file profile of {rel(profile_target)} produced by the provided "
                                    "check_submission.py profile helper")
    except FileNotFoundError as e:
        prof = None
        report["helper_profile"] = f"not produced: {e}"
    scope = {"declared_scope": "the whole input file", "input_is_subset": False}
    if full_path:
        acct = full_file_accounting(store, profile_target)
        subset_manifest = csv_path.with_suffix(".manifest.json")
        scope = {
            "declared_scope": f"{report['counts']['records']} rows of {rel(csv_path)} (subset of the full file)",
            "input_is_subset": True, "full_file": {"path": rel(profile_target), "sha256": sha256_file(profile_target),
                                                    "profile_counts": (prof or {}).get("counts")},
            "accounting": acct,
            "out_of_scope_handling": ("ingested and profiled (ingestion.json) but not classified: outside the declared "
                                      "analysis scope; they are not in records.jsonl and are not completed classifications"),
            "subset_manifest": (__import__("json").loads(subset_manifest.read_text()) if subset_manifest.exists() else None),
        }
        store.set_meta("full_input", {"path": rel(profile_target), "sha256": scope["full_file"]["sha256"]})
    report["scope"] = scope
    atomic_write_json(run_dir / "data_manifest.json", {
        "written_at": utc_now(), "run_id": run_id,
        "analysis_input": {"path": rel(csv_path), "sha256": file_sha, "bytes": report["input"]["bytes"],
                           "rows": stats["records"]},
        "ingestion_profile": {"file": "ingestion.json", "profiled": rel(profile_target),
                              "file_sha256": (prof or {}).get("file_sha256"),
                              "parsed_rows_sha256": (prof or {}).get("parsed_rows_sha256"),
                              "counts": (prof or {}).get("counts")},
        "scope": scope,
        "classification_input_fields": ["review_text"],
    })
    store.set_meta("ingestion_report", report)
    atomic_write_json(run_dir / "ingestion_report.json", report)
    store.event(run_id, "ingest", "ingested", rows=stats["records"], sha256=file_sha)
    return report

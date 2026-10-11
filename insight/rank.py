"""Stage 5 - rank (code only). Reproducible from records + membership with no model call.

Baseline (grading contract):
  complaint_count = membership count; severity_sum = sum of member severity;
  mean_severity = severity_sum / complaint_count (Decimal, 6 places, half-up);
  priority_score = severity_sum (= count x mean, exactly). Sort: score desc, issue_id asc.
"""

import csv
import gzip
import io
import json
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal

from . import labels
from .util import atomic_write_json, atomic_write_text

RANKING_COLUMNS = ("rank", "issue_id", "complaint_count", "severity_sum", "mean_severity", "priority_score")


def mean_string(total, n) -> str:
    return str((Decimal(total) / Decimal(n)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP))


def compute_ranking(records: dict, membership: list) -> list:
    """records: review_id -> {intent, severity, ...} (completed only); membership: [(issue_id, review_id)]."""
    members = defaultdict(list)
    seen = set()
    for issue_id, rid in membership:
        if (issue_id, rid) in seen:
            raise ValueError(f"duplicate membership {(issue_id, rid)}")
        seen.add((issue_id, rid))
        rec = records.get(rid)
        if rec is None:
            raise ValueError(f"membership references a review without a completed record: {rid}")
        if rec["intent"] not in labels.COMPLAINT_INTENTS:
            raise ValueError(f"non-complaint review in ranking: {rid} ({rec['intent']})")
        members[issue_id].append(int(rec["severity"]))
    rows = []
    for issue_id, sevs in members.items():
        total = sum(sevs)
        rows.append({"issue_id": issue_id, "complaint_count": len(sevs), "severity_sum": total,
                     "mean_severity": mean_string(total, len(sevs)), "priority_score": total})
    rows.sort(key=lambda r: (-r["priority_score"], r["issue_id"]))
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    return rows


def ranking_csv(rows) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(RANKING_COLUMNS)
    for r in rows:
        w.writerow([str(r[c]) for c in RANKING_COLUMNS])
    return buf.getvalue()


def area_rollup(rows, records, membership):
    """Derived business view (not a contract metric): sums of the baseline issues by decision area."""
    by_issue = {r["issue_id"]: r for r in rows}
    areas = defaultdict(lambda: {"complaint_count": 0, "severity_sum": 0, "issues": 0, "cancellation_count": 0})
    cancel = defaultdict(int)
    for issue_id, rid in membership:
        if records[rid]["intent"] == "cancellation":
            cancel[issue_id] += 1
    for issue_id, r in by_issue.items():
        topic = issue_id.split(".")[0]
        a = areas[labels.AREA_OF_TOPIC[topic]]
        a["complaint_count"] += r["complaint_count"]
        a["severity_sum"] += r["severity_sum"]
        a["issues"] += 1
        a["cancellation_count"] += cancel[issue_id]
    total = sum(a["complaint_count"] for a in areas.values())
    out = []
    for area, a in areas.items():
        out.append({"area": area, **a,
                    "share_of_complaints": mean_string(a["complaint_count"], total) if total else "0",
                    "decision_option": area in labels.DECISION_AREAS})
    out.sort(key=lambda x: (-x["severity_sum"], x["area"]))
    return out, total


def run_rank(store, label_config, log=print):
    """Write ranking.csv, aggregates.csv and area_rollup.csv from saved records + membership."""
    from .group import load_completed  # local import: group imports this module

    records = load_completed(store, label_config)
    with open(store.run_dir / "membership.csv", encoding="utf-8", newline="") as f:
        pairs = [(r["issue_id"], r["review_id"]) for r in csv.DictReader(f)]
    rows = compute_ranking(records, pairs)
    atomic_write_text(store.run_dir / "ranking.csv", ranking_csv(rows))
    issues_path = store.run_dir / "issues.json"
    names = {}
    if issues_path.exists():
        names = {i["issue_id"]: i for i in json.loads(issues_path.read_text())["issues"]}
    cancel = defaultdict(int)
    review_flag = defaultdict(int)
    for iid, rid in pairs:
        cancel[iid] += records[rid]["intent"] == "cancellation"
        review_flag[iid] += bool(records[rid]["needs_review"])
    total = sum(r["complaint_count"] for r in rows)
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(list(RANKING_COLUMNS) + ["name", "area", "cancellation_count", "needs_review_count",
                                        "share_of_complaints", "representative_review_ids"])
    for r in rows:
        meta = names.get(r["issue_id"], {})
        reps = ";".join(e["review_id"] for e in meta.get("evidence", [])[:3])
        w.writerow([str(r[c]) for c in RANKING_COLUMNS] + [
            meta.get("name", labels.ISSUE_BY_ID[r["issue_id"]]["name"]),
            labels.AREA_OF_TOPIC[r["issue_id"].split(".")[0]], cancel[r["issue_id"]], review_flag[r["issue_id"]],
            mean_string(r["complaint_count"], total) if total else "0", reps])
    atomic_write_text(store.run_dir / "aggregates.csv", buf.getvalue())
    areas, total_c = area_rollup(rows, records, pairs)
    atomic_write_json(store.run_dir / "area_rollup.json", {
        "note": "Derived view: sums of baseline issue metrics by decision area. Not a contract metric.",
        "denominator_complaints": total_c, "areas": areas})
    log(f"[rank] {len(rows)} issues ranked from {total} complaint/cancellation records (no model calls)")
    return {"issues": len(rows), "complaints": total, "top": rows[:5]}


def check_reproducible(records_path, membership_path, ranking_path):
    """Recompute the ranking from exported files only and compare byte for byte."""
    opener = gzip.open if str(records_path).endswith(".gz") else open
    records = {}
    with opener(records_path, "rt", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                r = json.loads(line)
                if r.get("status") == "completed":
                    records[r["review_id"]] = r
    with open(membership_path, encoding="utf-8", newline="") as f:
        pairs = [(r["issue_id"], r["review_id"]) for r in csv.DictReader(f)]
    fresh = ranking_csv(compute_ranking(records, pairs))
    with open(ranking_path, encoding="utf-8") as f:
        saved = f.read()
    return {"identical": fresh == saved, "issues": fresh.count("\n") - 1,
            "first_difference": None if fresh == saved else next(
                (i for i, (a, b) in enumerate(zip(fresh.splitlines(), saved.splitlines())) if a != b), "length")}

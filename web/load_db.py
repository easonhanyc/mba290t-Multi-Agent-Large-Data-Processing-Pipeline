"""Load one pipeline run's saved outputs into the dashboard database (no model calls).

    .venv/bin/python web/load_db.py --run-dir runs/<run>                         # DATABASE_URL from .env
    .venv/bin/python web/load_db.py --run-dir runs/<run> --database-url sqlite:///web/local.db

Reads only exported artifacts: grading/records.jsonl(.gz) + the run's input CSV (source fields),
membership/ranking/claims/aggregates CSVs, issues.json, area_rollup.json, memo.json/memo.md (including the
token index), analysis/*, verification/*, evals/*, run_summary.json, data_manifest.json, recordings and
cost/report.json.
The load replaces the previous contents in one transaction, then checks row counts and that the
ranking recomputed in SQL from reviews + membership equals the saved ranking.
PostgreSQL (psycopg 3, COPY) in production; sqlite3 for local tests.
"""

import argparse
import csv
import gzip
import io
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = Path(__file__).resolve().parent / "schema.sql"
FIELDS = ("review_id", "review_text", "review_rating", "review_likes", "app_version", "review_timestamp")
AREA_OF_TOPIC = {"access": "access/onboarding", "usability": "usability", "playback": "playback/performance",
                 "downloads": "playback/performance", "billing": "billing/support", "support": "billing/support",
                 "catalog": "catalog/content", "other": "general/unspecified"}
TABLES = ("documents", "verification", "recommendation", "claims", "trends_monthly", "area_rollup", "ranking", "issues",
          "membership", "reviews", "runs")
REVIEW_COLS = ("review_id", "row_num", "review_text", "review_rating", "review_likes", "app_version", "review_timestamp",
               "month", "source_sha256", "status", "reason", "topic", "subtopic", "issue_id", "area", "intent", "severity",
               "sentiment", "evidence_quote", "entities", "needs_review", "labeled_by", "cache_source_id", "label_config")


def load_env():
    for env in (ROOT / ".env", ROOT / "web" / ".env.local"):
        if not env.exists() or os.environ.get("INSIGHT_NO_DOTENV"):
            continue
        for line in env.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip().strip("'\"")
                if k and v and k not in os.environ:
                    os.environ[k] = v


class DB:
    def __init__(self, url):
        self.url = url
        if url.startswith("sqlite:///"):
            self.kind = "sqlite"
            self.conn = sqlite3.connect(url[len("sqlite:///"):])
        else:
            import psycopg
            self.kind = "postgres"
            self.conn = psycopg.connect(url)

    def sql(self, text):
        return text if self.kind == "postgres" else text.replace("%s", "?")

    def execute(self, text, params=()):
        cur = self.conn.cursor()
        cur.execute(self.sql(text), params)
        return cur

    def executescript(self, text):
        if self.kind == "sqlite":
            self.conn.executescript(text)
        else:
            with self.conn.cursor() as cur:
                cur.execute(text)

    def insert_many(self, table, cols, rows):
        rows = list(rows)
        if not rows:
            return 0
        if self.kind == "postgres":
            with self.conn.cursor() as cur:
                with cur.copy(f"COPY {table} ({', '.join(cols)}) FROM STDIN") as cp:
                    for r in rows:
                        cp.write_row(r)
        else:
            self.conn.executemany(f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})", rows)
        return len(rows)


def read_json(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def read_csv(p):
    if not Path(p).exists():
        return []
    with open(p, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def read_jsonl(p):
    p = Path(p)
    if not p.exists() and Path(str(p) + ".gz").exists():
        p = Path(str(p) + ".gz")
    if not p.exists():
        return []
    opener = gzip.open if str(p).endswith(".gz") else open
    with opener(p, "rt", encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def mean_string(total, n):
    return str((Decimal(total) / Decimal(n)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP))


def gather(run_dir: Path, input_csv: Path | None):
    grading = run_dir / "grading"
    run_json = read_json(grading / "run.json")
    manifest = read_json(run_dir / "data_manifest.json") if (run_dir / "data_manifest.json").exists() else {}
    src_path = input_csv or (ROOT / run_json["input_file"])
    if not src_path.exists():
        raise SystemExit(f"source CSV {src_path} not found (regenerate it with scripts/make_analysis_subset.py)")
    source = {}
    with open(src_path, encoding="utf-8-sig", newline="") as f:
        for n, row in enumerate(csv.DictReader(f), 1):
            if row["review_id"] not in source:
                source[row["review_id"]] = (n, {k: row[k] for k in FIELDS})
    records = read_jsonl(grading / "records.jsonl")
    membership = read_csv(run_dir / "membership.csv")
    issue_of = {m["review_id"]: m["issue_id"] for m in membership}
    reviews = []
    for r in records:
        n, s = source[r["review_id"]]
        topic = r.get("topic")
        issue = issue_of.get(r["review_id"]) or (f"{topic}.{r['subtopic']}" if topic and r.get("subtopic") else None)
        likes = int(s["review_likes"]) if s["review_likes"].isdigit() else 0
        reviews.append((r["review_id"], n, s["review_text"], s["review_rating"], likes, s["app_version"],
                        s["review_timestamp"], s["review_timestamp"][:7], r["source_sha256"], r["status"], r.get("reason"),
                        topic, r.get("subtopic"), issue, AREA_OF_TOPIC.get(topic) if topic else None, r.get("intent"),
                        r.get("severity"), r.get("sentiment"), r.get("evidence_quote"),
                        json.dumps(r.get("entities") or [], ensure_ascii=False) if r["status"] == "completed" else None,
                        int(bool(r.get("needs_review"))) if r["status"] == "completed" else None, r.get("labeled_by"),
                        r.get("cache_source_id"), r.get("label_config")))
    return run_json, manifest, reviews, membership


def rel(p: Path) -> str:
    return str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p)


def documents(run_dir: Path):
    docs = []
    def add(name, kind, path):
        p = run_dir / path if not str(path).startswith("/") else Path(path)
        if p.exists():
            body = p.read_text(encoding="utf-8")
            docs.append((name, kind, rel(p), body))
    for f in ("overview", "period_comparison", "spike_months", "rating_crosstab", "area_intervals", "robustness",
              "premium_only_sensitivity"):
        add(f, "analysis", f"analysis/{f}.json")
    for f in ("app_versions", "reach_weighted_ranking", "trends_monthly"):
        add(f, "analysis_csv", f"analysis/{f}.csv")
    add("verification_report", "eval", "verification/report.json")
    add("planted_error", "eval", "evals/planted_error.json")
    add("rank_check", "eval", "rank_check.json")
    add("self_check", "eval", "self-check.json")
    add("self_check_full", "eval", "self-check-vs-full-reference.json")
    add("golden_results", "eval", ROOT / "evals" / "golden" / "results.json")
    add("golden_error_analysis", "eval_md", ROOT / "evals" / "golden" / "error_analysis.md")
    for cand in ("golden-luna-none", "golden-luna-low", "golden-decisions"):  # the setups compared before choosing
        add(f"golden_candidate:{cand}", "eval", ROOT / "evals" / "golden" / "candidates" / f"{cand}.json")
    add("quote_support", "eval", ROOT / "evals" / "quote_support" / "summary.json")
    add("injection_check", "eval", ROOT / "evals" / "injection" / "synthetic_check.json")
    add("run_summary", "run", "run_summary.json")
    add("ingestion_report", "run", "ingestion_report.json")
    add("ingestion_profile", "run", "ingestion.json")
    add("issues_doc", "run", "issues.json")
    add("cost_report", "cost", ROOT / "cost" / "report.json")
    add("trace_example", "doc_md", ROOT / "docs" / "trace_example.md")
    rec = run_dir / "recording"
    if rec.exists():
        for cast in sorted(rec.glob("*.cast")):
            add(f"recording:{cast.stem}", "recording", cast)
            if cast.with_suffix(".txt").exists():
                add(f"recording_txt:{cast.stem}", "recording_txt", cast.with_suffix(".txt"))
    vr = run_dir / "verification" / "report.json"
    if vr.exists():  # the dashboard reads this small summary instead of parsing the full report on every request
        report = read_json(vr)
        docs.append(("verification_summary", "eval", rel(vr) + " (without the per-review disagreements list)",
                     json.dumps({k: v for k, v in report.items() if k != "disagreements"}
                                | {"disagreements_count": len(report.get("disagreements") or [])})))
    memo_json = run_dir / "memo.json"
    if memo_json.exists():  # every memo token (C/A/S/T) with its value, what it measures and its source file
        memo = read_json(memo_json)
        if memo.get("token_index"):
            docs.append(("memo_tokens", "memo", rel(memo_json) + " -> token_index (also memo_tokens.csv)",
                         json.dumps(memo["token_index"], ensure_ascii=False)))
    for name in ("checkpoint_before", "checkpoint_after"):
        p = run_dir / "grading" / f"{name}.json"
        if p.exists():
            d = read_json(p)
            docs.append((name, "checkpoint", rel(p),
                         json.dumps({"run_id": d.get("run_id"), "status": d.get("status"), "stop_reason": d.get("stop_reason"),
                                     "completed_ids_count": len(d.get("completed_ids") or []),
                                     "first_ids": (d.get("completed_ids") or [])[:5]})))
    return docs


def evidence_json(issue):
    """The quotes the issue name was based on; quotes the naming model flagged as not fitting carry misfit=true."""
    misfit = set(issue.get("misfit_review_ids") or [])
    return json.dumps([dict(e, misfit=e.get("review_id") in misfit) for e in issue.get("evidence", [])], ensure_ascii=False)


def load(run_dir: Path, url: str, input_csv: Path | None = None, log=print):
    run_dir = Path(run_dir).resolve()
    run_json, manifest, reviews, membership = gather(run_dir, input_csv)
    ranking = read_csv(run_dir / "ranking.csv")
    agg = {r["issue_id"]: r for r in read_csv(run_dir / "aggregates.csv")}
    issues_doc = read_json(run_dir / "issues.json")
    areas = read_json(run_dir / "area_rollup.json")["areas"]
    trends = read_csv(run_dir / "analysis" / "trends_monthly.csv")
    claims = read_csv(run_dir / "claims.csv")
    memo = read_json(run_dir / "memo.json")
    memo_md = (run_dir / "memo.md").read_text(encoding="utf-8")
    vpreds = read_jsonl(run_dir / "verification" / "verifier_predictions.jsonl")
    db = DB(url)
    db.executescript(SCHEMA.read_text())
    for t in TABLES:
        db.execute(f"DELETE FROM {t}")
    run_key = run_dir.name
    db.execute("INSERT INTO runs (run_key, label_config, analysis_input, analysis_sha256, analysis_rows, full_source, full_sha256, "
               "offline_stub, loaded_at, run_json, data_manifest_json) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
               (run_key, run_json["label_config"], run_json["input_file"], run_json["analysis_sha256"], run_json["analysis_count"],
                (run_json.get("full_source") or {}).get("path"), (run_json.get("full_source") or {}).get("sha256"),
                int(bool(run_json.get("offline_stub"))), datetime.now(timezone.utc).isoformat(timespec="seconds"),
                json.dumps(run_json), json.dumps(manifest)))
    n_reviews = db.insert_many("reviews", REVIEW_COLS, reviews)
    n_members = db.insert_many("membership", ("issue_id", "review_id"), [(m["issue_id"], m["review_id"]) for m in membership])
    db.insert_many("issues", ("issue_id", "name", "default_name", "summary", "area", "definition", "named_by", "evidence_json"),
                   [(i["issue_id"], i["name"], i.get("default_name"), i.get("summary"), i["area"], i.get("definition"),
                     i.get("named_by"), evidence_json(i)) for i in issues_doc["issues"]])
    db.insert_many("ranking", ("issue_id", "rank", "complaint_count", "severity_sum", "mean_severity", "priority_score",
                               "cancellation_count", "needs_review_count", "share_of_complaints"),
                   [(r["issue_id"], int(r["rank"]), int(r["complaint_count"]), int(r["severity_sum"]), r["mean_severity"],
                     int(r["priority_score"]), int(agg.get(r["issue_id"], {}).get("cancellation_count") or 0),
                     int(agg.get(r["issue_id"], {}).get("needs_review_count") or 0),
                     agg.get(r["issue_id"], {}).get("share_of_complaints")) for r in ranking])
    db.insert_many("area_rollup", ("area", "complaint_count", "severity_sum", "issues", "cancellation_count",
                                   "share_of_complaints", "decision_option"),
                   [(a["area"], a["complaint_count"], a["severity_sum"], a["issues"], a["cancellation_count"],
                     str(a["share_of_complaints"]), int(bool(a["decision_option"]))) for a in areas])
    db.insert_many("trends_monthly", ("month", "partial_month", "reviews", "complaints", "complaint_share", "cancellations",
                                      "areas_json"),
                   [(t["month"], t["partial_month"], int(t["reviews"]), int(t["complaints"]), float(t["complaint_share"]),
                     int(t["cancellations"]), json.dumps({k: v for k, v in t.items() if k.endswith(("_complaints", "_share_of_reviews"))
                                                           and k != "complaints"})) for t in trends])
    db.insert_many("claims", ("claim_id", "issue_id", "metric", "value"),
                   [(c["claim_id"], c["issue_id"], c["metric"], c["value"]) for c in claims])
    db.execute("INSERT INTO recommendation (id, recommended_area, source, memo_config, generated_at, output_json, tokens_json, "
               "payload_json, memo_md) VALUES (1,%s,%s,%s,%s,%s,%s,%s,%s)",
               (memo["output"]["recommended_area"], memo["source"], memo.get("memo_config"), memo.get("generated_at"),
                json.dumps(memo["output"], ensure_ascii=False), json.dumps(memo["tokens"], ensure_ascii=False),
                json.dumps(memo["payload"], ensure_ascii=False), memo_md))
    db.insert_many("verification", ("review_id", "status", "topic", "intent", "severity", "sentiment", "confidence", "request_id"),
                   [(v["review_id"], v["status"], v.get("topic"), v.get("intent"), v.get("severity"), v.get("sentiment"),
                     v.get("confidence"), v.get("request_id")) for v in vpreds])
    db.insert_many("documents", ("name", "kind", "source_file", "body"), documents(run_dir))
    db.conn.commit()
    check = verify_load(db, len(reviews), len(membership), ranking, claims)
    db.conn.close()
    log(f"[load_db] {db.kind}: {n_reviews} reviews, {n_members} memberships, {len(ranking)} ranked issues, "
        f"{len(claims)} claims; checks: {json.dumps(check)}")
    if not all(v is True for k, v in check.items() if k.endswith("_ok")):
        raise SystemExit("post-load check failed")
    return check


def verify_load(db, n_reviews, n_members, ranking, claims):
    got_reviews = db.execute("SELECT COUNT(*) FROM reviews").fetchone()[0]
    got_members = db.execute("SELECT COUNT(*) FROM membership").fetchone()[0]
    rows = db.execute("SELECT m.issue_id, COUNT(*), SUM(r.severity) FROM membership m JOIN reviews r ON r.review_id = m.review_id "
                      "GROUP BY m.issue_id").fetchall()
    sql_rank = sorted(({"issue_id": i, "complaint_count": int(c), "severity_sum": int(s), "mean_severity": mean_string(int(s), int(c))}
                       for i, c, s in rows), key=lambda x: (-x["severity_sum"], x["issue_id"]))
    saved = [{"issue_id": r["issue_id"], "complaint_count": int(r["complaint_count"]), "severity_sum": int(r["severity_sum"]),
              "mean_severity": r["mean_severity"]} for r in ranking]
    by_id = {r["issue_id"]: r for r in sql_rank}
    claims_ok = all(str(by_id.get(c["issue_id"], {}).get(c["metric"] if c["metric"] != "priority_score" else "severity_sum"))
                    == c["value"] for c in claims)
    return {"review_rows_ok": got_reviews == n_reviews, "membership_rows_ok": got_members == n_members,
            "sql_ranking_equals_saved_ok": sql_rank == saved, "claims_equal_sql_ok": claims_ok,
            "reviews": got_reviews, "memberships": got_members}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-dir", required=True, type=Path)
    ap.add_argument("--database-url", default=None, help="default: DATABASE_URL from the environment / .env")
    ap.add_argument("--input-csv", type=Path, default=None, help="source CSV if not at the path recorded in run.json")
    args = ap.parse_args(argv)
    load_env()
    url = args.database_url or os.environ.get("DATABASE_URL_UNPOOLED") or os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("Set DATABASE_URL (owner connection string) in .env or pass --database-url")
    load(args.run_dir, url, args.input_csv)
    return 0


if __name__ == "__main__":
    sys.exit(main())

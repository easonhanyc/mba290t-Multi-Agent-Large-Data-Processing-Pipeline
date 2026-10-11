"""Dashboard backend: a read-only JSON API over the dashboard database (deployed as a Vercel Python function).

Every endpoint queries the database loaded by web/load_db.py; nothing is computed from files and no model
is ever called. Connection string: DATABASE_URL_READONLY (a SELECT-only role) or DATABASE_URL. A value
starting with sqlite:/// selects a local SQLite file (tests and local preview).
"""

import json
import os
import sqlite3
import threading
from decimal import ROUND_HALF_UP, Decimal

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse, PlainTextResponse

app = FastAPI(title="Spotify review insight API", version="1.0",
              description="Read-only access to the processed reviews, aggregates and AI recommendation of one pipeline run.")

_lock = threading.Lock()
_conn = {"c": None, "kind": None}
DECISION_AREAS = ("access/onboarding", "usability", "playback/performance", "billing/support")
METRICS = ("complaint_count", "severity_sum", "mean_severity", "priority_score")


def _url():
    url = os.environ.get("DATABASE_URL_READONLY") or os.environ.get("DATABASE_URL")
    if not url:
        raise HTTPException(503, "database not configured (set DATABASE_URL_READONLY)")
    return url


def _connect():
    url = _url()
    if url.startswith("sqlite:///"):
        c = sqlite3.connect(url[len("sqlite:///"):], check_same_thread=False)
        return c, "sqlite"
    import psycopg
    return psycopg.connect(url, autocommit=True, connect_timeout=10), "postgres"


def q(sql, params=(), one=False):
    """Run a read query; reconnect once if a pooled serverless connection went stale."""
    for attempt in (1, 2):
        with _lock:
            try:
                if _conn["c"] is None:
                    _conn["c"], _conn["kind"] = _connect()
                c, kind = _conn["c"], _conn["kind"]
                cur = c.cursor()
                cur.execute(sql if kind == "postgres" else sql.replace("%s", "?"), params)
                cols = [d[0] for d in cur.description]
                rows = [dict(zip(cols, r)) for r in (cur.fetchmany(1) if one else cur.fetchall())]
                return (rows[0] if rows else None) if one else rows
            except HTTPException:
                raise
            except Exception:
                try:
                    if _conn["c"] is not None:
                        _conn["c"].close()
                except Exception:
                    pass
                _conn["c"] = None
                if attempt == 2:
                    raise


def doc(name):
    row = q("SELECT body, source_file FROM documents WHERE name = %s", (name,), one=True)
    if not row:
        return None
    try:
        return json.loads(row["body"])
    except json.JSONDecodeError:
        return row["body"]


def mean_string(total, n):
    return str((Decimal(total) / Decimal(n)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP))


def cached(resp):
    return JSONResponse(resp, headers={"Cache-Control": "public, max-age=60, s-maxage=600"})


@app.get("/api/health")
def health():
    run = q("SELECT run_key, label_config, analysis_rows, offline_stub, loaded_at FROM runs", one=True)
    n = q("SELECT COUNT(*) AS n FROM reviews", one=True)["n"]
    return {"ok": True, "database": _conn["kind"], "run": run, "review_rows": n}


@app.get("/api/overview")
def overview():
    run = q("SELECT * FROM runs", one=True)
    if not run:
        raise HTTPException(404, "no run loaded")
    status = {r["status"]: r["n"] for r in q("SELECT status, COUNT(*) AS n FROM reviews GROUP BY status")}
    completed = status.get("completed", 0)
    quarantine = q("SELECT reason, COUNT(*) AS n FROM reviews WHERE status = 'quarantined' GROUP BY reason ORDER BY n DESC")
    intents = q("SELECT intent, COUNT(*) AS n FROM reviews WHERE status = 'completed' GROUP BY intent ORDER BY n DESC")
    topics = q("SELECT topic, COUNT(*) AS n, SUM(CASE WHEN intent IN ('complaint','cancellation') THEN 1 ELSE 0 END) AS complaints "
               "FROM reviews WHERE status = 'completed' GROUP BY topic ORDER BY complaints DESC")
    sev = q("SELECT severity, COUNT(*) AS n FROM reviews WHERE status = 'completed' AND intent IN ('complaint','cancellation') "
            "GROUP BY severity ORDER BY severity")
    misc = q("SELECT SUM(CASE WHEN intent IN ('complaint','cancellation') THEN 1 ELSE 0 END) AS complaints, "
             "SUM(CASE WHEN intent = 'cancellation' THEN 1 ELSE 0 END) AS cancellations, "
             "SUM(needs_review) AS needs_review, SUM(CASE WHEN cache_source_id IS NOT NULL THEN 1 ELSE 0 END) AS cache_reuses, "
             "AVG(sentiment) AS mean_sentiment, COUNT(DISTINCT CASE WHEN cache_source_id IS NULL THEN review_id END) AS distinct_labelled "
             "FROM reviews WHERE status = 'completed'", one=True)
    tiers = q("SELECT labeled_by, COUNT(*) AS n FROM reviews WHERE status = 'completed' GROUP BY labeled_by ORDER BY n DESC")
    areas = q("SELECT * FROM area_rollup ORDER BY severity_sum DESC")
    rs = doc("run_summary") or {}
    latest = rs.get("latest", {}) if isinstance(rs, dict) else {}
    vr = doc("verification_report") or {}
    golden = doc("golden_results") or {}
    cost = doc("cost_report") or {}
    manifest = json.loads(run["data_manifest_json"] or "{}")
    return cached({
        "run": {"run_key": run["run_key"], "label_config": run["label_config"], "analysis_input": run["analysis_input"],
                "analysis_sha256": run["analysis_sha256"], "analysis_rows": run["analysis_rows"],
                "full_source": run["full_source"], "full_sha256": run["full_sha256"], "offline_stub": bool(run["offline_stub"]),
                "loaded_at": run["loaded_at"], "scope": (manifest.get("scope") or {}).get("accounting")},
        "counts": {"rows": sum(status.values()), "completed": completed, "quarantined": status.get("quarantined", 0),
                   "complaints": misc["complaints"], "cancellations": misc["cancellations"],
                   "needs_review": misc["needs_review"], "exact_text_cache_reuses": misc["cache_reuses"],
                   "mean_sentiment": round(float(misc["mean_sentiment"] or 0), 4)},
        "quarantine_reasons": quarantine, "intents": intents, "topics": topics, "complaint_severity": sev,
        "labeled_by": tiers, "areas": areas,
        "verification": {"compared": vr.get("compared"), "agreement": vr.get("agreement")} if vr else None,
        "golden": {"status": golden.get("status"), "cases": golden.get("cases"), "agreement": golden.get("agreement")}
        if isinstance(golden, dict) and golden else None,
        "run_evidence": {"wall_clock_s_last_invocation": latest.get("wall_clock_s"), "history": rs.get("history")},
        "cost": _cost_summary(cost),
    })


def _cost_summary(cost):
    if not isinstance(cost, dict) or not cost:
        return None
    spend = cost.get("spend") or {}
    meas = cost.get("measured") or {}
    return {"billed_api_spend_recorded_usd": spend.get("total_billed_usd"), "per_run": spend.get("per_run"),
            "pilot_cold": (meas.get("runs") or {}).get("cold", {}).get("api_cost_usd"),
            "pilot_warm": (meas.get("runs") or {}).get("warm", {}).get("api_cost_usd"),
            "pilot_warm_new_enrichment_calls": (meas.get("runs") or {}).get("warm", {}).get("new_enrichment_calls")}


@app.get("/api/ranking")
def ranking():
    rows = q("SELECT r.*, i.name, i.summary, i.area, i.named_by FROM ranking r LEFT JOIN issues i ON i.issue_id = r.issue_id "
             "ORDER BY r.rank")
    return cached({"rule": "priority_score = severity_sum = complaint_count x mean_severity over complaint and cancellation "
                           "reviews; ties broken by issue_id", "issues": rows})


@app.get("/api/issues/{issue_id}")
def issue(issue_id: str, limit: int = Query(20, ge=1, le=100)):
    meta = q("SELECT i.*, r.rank, r.complaint_count, r.severity_sum, r.mean_severity, r.priority_score, r.cancellation_count, "
             "r.needs_review_count, r.share_of_complaints FROM issues i LEFT JOIN ranking r ON r.issue_id = i.issue_id "
             "WHERE i.issue_id = %s", (issue_id,), one=True)
    if not meta:
        raise HTTPException(404, f"unknown issue {issue_id}")
    monthly = q("SELECT r.month, COUNT(*) AS complaints, SUM(r.severity) AS severity_sum FROM membership m "
                "JOIN reviews r ON r.review_id = m.review_id WHERE m.issue_id = %s GROUP BY r.month ORDER BY r.month", (issue_id,))
    sev = q("SELECT r.severity, COUNT(*) AS n FROM membership m JOIN reviews r ON r.review_id = m.review_id "
            "WHERE m.issue_id = %s GROUP BY r.severity ORDER BY r.severity", (issue_id,))
    evidence = q("SELECT r.review_id, r.evidence_quote, r.review_text, r.severity, r.intent, r.sentiment, r.review_likes, "
                 "r.review_timestamp, r.labeled_by, r.needs_review FROM membership m JOIN reviews r ON r.review_id = m.review_id "
                 "WHERE m.issue_id = %s AND r.cache_source_id IS NULL ORDER BY r.severity DESC, r.review_likes DESC, r.row_num "
                 "LIMIT %s", (issue_id, limit))
    meta["evidence_json"] = json.loads(meta.get("evidence_json") or "[]")
    return cached({"issue": meta, "monthly": monthly, "severity_distribution": sev, "evidence": evidence})


@app.get("/api/recommendation")
def recommendation():
    rec = q("SELECT * FROM recommendation WHERE id = 1", one=True)
    if not rec:
        raise HTTPException(404, "no recommendation loaded")
    out, tokens, payload = json.loads(rec["output_json"]), json.loads(rec["tokens_json"]), json.loads(rec["payload_json"])
    live = {r["issue_id"]: r for r in q("SELECT * FROM ranking")}
    claims = []
    for c in q("SELECT * FROM claims ORDER BY claim_id"):
        current = live.get(c["issue_id"], {}).get(c["metric"])
        claims.append({**c, "database_value": None if current is None else str(current),
                       "matches_database": current is not None and str(current) == c["value"]})
    cited = out.get("cited_reviews") or []
    cited_rows = q("SELECT review_id, evidence_quote, issue_id, severity, intent FROM reviews WHERE review_id IN ("
                   + ",".join(["%s"] * len(cited)) + ")", tuple(cited)) if cited else []
    return cached({"recommended_area": rec["recommended_area"], "source": rec["source"], "memo_config": rec["memo_config"],
                   "generated_at": rec["generated_at"], "output": out, "tokens": tokens, "payload": payload,
                   "claims": claims, "all_claims_match_database": all(c["matches_database"] for c in claims),
                   "cited_reviews": cited_rows, "memo_md": rec["memo_md"]})


@app.get("/api/trends")
def trends():
    rows = q("SELECT * FROM trends_monthly ORDER BY month")
    for r in rows:
        r["areas"] = json.loads(r.pop("areas_json"))
    return cached({"months": rows, "period_comparison": doc("period_comparison"), "spike_months": doc("spike_months")})


@app.get("/api/areas")
def areas():
    return cached({"areas": q("SELECT * FROM area_rollup ORDER BY severity_sum DESC"), "intervals": doc("area_intervals"),
                   "robustness": doc("robustness"), "decision_areas": DECISION_AREAS})


@app.get("/api/analysis/{name}")
def analysis(name: str):
    allowed = {"overview", "period_comparison", "spike_months", "rating_crosstab", "area_intervals", "robustness",
               "app_versions", "reach_weighted_ranking", "trends_monthly"}
    if name not in allowed:
        raise HTTPException(404, f"unknown analysis {name}")
    body = doc(name)
    if body is None:
        raise HTTPException(404, f"{name} not loaded")
    return cached({"name": name, "body": body})


@app.get("/api/evals")
def evals():
    v = q("SELECT COUNT(*) AS n, SUM(CASE WHEN v.topic = r.topic THEN 1 ELSE 0 END) AS topic, "
          "SUM(CASE WHEN v.intent = r.intent THEN 1 ELSE 0 END) AS intent, "
          "SUM(CASE WHEN v.severity = r.severity THEN 1 ELSE 0 END) AS severity FROM verification v "
          "JOIN reviews r ON r.review_id = v.review_id WHERE v.status = 'completed' AND r.status = 'completed'", one=True)
    return cached({"verification_sql": v, "verification_report": doc("verification_report"), "golden": doc("golden_results"),
                   "golden_error_analysis": doc("golden_error_analysis"), "planted_error": doc("planted_error"),
                   "injection": doc("injection_check"), "rank_check": doc("rank_check"), "self_check": doc("self_check")})


@app.get("/api/run")
def run_evidence():
    recs = [r["name"].split(":", 1)[1] for r in q("SELECT name FROM documents WHERE kind = 'recording' ORDER BY name")]
    return cached({"run_summary": doc("run_summary"), "ingestion_report": doc("ingestion_report"),
                   "ingestion_profile": doc("ingestion_profile"), "checkpoint_before": doc("checkpoint_before"),
                   "checkpoint_after": doc("checkpoint_after"), "cost": _cost_summary(doc("cost_report") or {}),
                   "recordings": recs, "trace_example_md": doc("trace_example")})


@app.get("/api/recording/{name}")
def recording(name: str):
    row = q("SELECT body FROM documents WHERE name = %s", (f"recording:{name}",), one=True)
    if not row:
        raise HTTPException(404, "no such recording")
    return PlainTextResponse(row["body"], headers={"Cache-Control": "public, max-age=600"})


@app.get("/api/reviews/{review_id}")
def review(review_id: str):
    r = q("SELECT * FROM reviews WHERE review_id = %s", (review_id,), one=True)
    if not r:
        raise HTTPException(404, "review not in the analysed scope")
    r["entities"] = json.loads(r["entities"]) if r.get("entities") else []
    v = q("SELECT * FROM verification WHERE review_id = %s", (review_id,), one=True)
    m = q("SELECT m.issue_id, i.name, k.rank, k.complaint_count, k.severity_sum, k.mean_severity, k.priority_score "
          "FROM membership m LEFT JOIN issues i ON i.issue_id = m.issue_id LEFT JOIN ranking k ON k.issue_id = m.issue_id "
          "WHERE m.review_id = %s", (review_id,), one=True)
    claims = q("SELECT * FROM claims WHERE issue_id = %s ORDER BY claim_id", (m["issue_id"],)) if m else []
    rec = q("SELECT output_json, payload_json FROM recommendation WHERE id = 1", one=True)
    cited = quoted = False
    if rec:
        cited = review_id in (json.loads(rec["output_json"]).get("cited_reviews") or [])
        quoted = any(e.get("review_id") == review_id for e in json.loads(rec["payload_json"]).get("evidence", []))
    source = q("SELECT review_id, evidence_quote FROM reviews WHERE review_id = %s", (r["cache_source_id"],), one=True) \
        if r.get("cache_source_id") else None
    comparison = None
    if v and v["status"] == "completed" and r["status"] == "completed":
        comparison = {"topic": v["topic"] == r["topic"], "intent": v["intent"] == r["intent"],
                      "severity": v["severity"] == r["severity"],
                      "sentiment_within_0.5": abs(float(v["sentiment"]) - float(r["sentiment"])) <= 0.5 + 1e-9}
    return {"review": r, "cache_source": source, "verification": v, "verification_comparison": comparison,
            "issue": m, "claims": claims, "quoted_in_memo_evidence": quoted, "cited_by_memo": cited}


@app.get("/api/reviews")
def reviews(issue_id: str | None = None, intent: str | None = None, topic: str | None = None, q_text: str | None = Query(None, alias="q"),
            status: str | None = None, limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0)):
    where, params = [], []
    if issue_id:
        where.append("issue_id = %s"); params.append(issue_id)
    if intent:
        where.append("intent = %s"); params.append(intent)
    if topic:
        where.append("topic = %s"); params.append(topic)
    if status:
        where.append("status = %s"); params.append(status)
    if q_text:
        where.append("LOWER(review_text) LIKE %s"); params.append(f"%{q_text.lower()[:80]}%")
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    total = q("SELECT COUNT(*) AS n FROM reviews" + clause, tuple(params), one=True)["n"]
    rows = q("SELECT review_id, review_timestamp, review_rating, status, reason, topic, subtopic, intent, severity, sentiment, "
             "evidence_quote, needs_review, labeled_by, cache_source_id, SUBSTR(review_text, 1, 300) AS review_text "
             "FROM reviews" + clause + " ORDER BY row_num LIMIT %s OFFSET %s", tuple(params) + (limit, offset))
    return {"total": total, "limit": limit, "offset": offset, "reviews": rows}


@app.get("/api/consistency")
def consistency():
    """Recompute the baseline ranking from reviews + membership in SQL and compare it with the saved table."""
    rows = q("SELECT m.issue_id, COUNT(*) AS c, SUM(r.severity) AS s FROM membership m JOIN reviews r ON r.review_id = m.review_id "
             "WHERE r.status = 'completed' AND r.intent IN ('complaint','cancellation') GROUP BY m.issue_id")
    fresh = sorted(({"issue_id": x["issue_id"], "complaint_count": int(x["c"]), "severity_sum": int(x["s"]),
                     "mean_severity": mean_string(int(x["s"]), int(x["c"])), "priority_score": int(x["s"])} for x in rows),
                   key=lambda x: (-x["priority_score"], x["issue_id"]))
    for i, x in enumerate(fresh, 1):
        x["rank"] = i
    saved = q("SELECT rank, issue_id, complaint_count, severity_sum, mean_severity, priority_score FROM ranking ORDER BY rank")
    mismatches = [{"saved": s, "recomputed": f} for s, f in zip(saved, fresh)
                  if any(str(s[k]) != str(f[k]) for k in ("rank", "issue_id", "complaint_count", "severity_sum",
                                                          "mean_severity", "priority_score"))]
    ungrouped = q("SELECT COUNT(*) AS n FROM reviews r WHERE r.status = 'completed' AND r.intent IN ('complaint','cancellation') "
                  "AND NOT EXISTS (SELECT 1 FROM membership m WHERE m.review_id = r.review_id)", one=True)["n"]
    by_id = {x["issue_id"]: x for x in fresh}
    claim_mismatch = [c for c in q("SELECT * FROM claims") if str(by_id.get(c["issue_id"], {}).get(c["metric"])) != c["value"]]
    return {"ranking_matches": not mismatches and len(saved) == len(fresh), "issues_saved": len(saved),
            "issues_recomputed": len(fresh), "mismatches": mismatches[:10], "ungrouped_complaints": ungrouped,
            "claims_match": not claim_mismatch, "claim_mismatches": claim_mismatch[:10],
            "method": "SQL over the reviews and membership tables at request time; the saved ranking table is not used "
                      "for the recomputation."}

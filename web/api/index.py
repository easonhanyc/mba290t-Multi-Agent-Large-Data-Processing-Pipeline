"""Dashboard backend: a read-only JSON API over the dashboard database (deployed as a Vercel Python function).

Every endpoint queries the database loaded by web/load_db.py; nothing is computed from files and no model
is ever called. Connection string: DATABASE_URL_READONLY (a SELECT-only role) if set, else the Neon
integration's DATABASE_URL_UNPOOLED / DATABASE_URL; sessions are set read-only and every query is a SELECT.
A value starting with sqlite:/// selects a local SQLite file (tests and local preview).
Interactive documentation (Swagger UI, GET routes only): /api/docs (also reachable as /docs).
"""

import json
import os
import re
import sqlite3
import threading
from decimal import ROUND_HALF_UP, Decimal

from urllib.parse import parse_qsl, urlencode

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse

app = FastAPI(title="Spotify review insight API", version="1.1",
              description="Read-only access to the processed reviews, aggregates and AI recommendation of one pipeline "
                          "run. Every route is GET; the database role is SELECT-only.",
              docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None)


@app.middleware("http")
async def _restore_rewritten_path(request: Request, call_next):
    """vercel.json rewrites /api/<rest> to /api/index?__path=<rest>; restore /api/<rest> before routing."""
    pairs = parse_qsl(request.scope.get("query_string", b"").decode(), keep_blank_values=True)
    rest = [v for k, v in pairs if k == "__path"]
    if rest:
        request.scope["path"] = "/api/" + rest[0].lstrip("/")
        request.scope["raw_path"] = request.scope["path"].encode()
        request.scope["query_string"] = urlencode([(k, v) for k, v in pairs if k != "__path"]).encode()
    return await call_next(request)

_lock = threading.Lock()
_conn = {"c": None, "kind": None}
DECISION_AREAS = ("access/onboarding", "usability", "playback/performance", "billing/support")
METRICS = ("complaint_count", "severity_sum", "mean_severity", "priority_score")
COMPLAINT = "intent IN ('complaint','cancellation')"


def _url():
    url = (os.environ.get("DATABASE_URL_READONLY") or os.environ.get("DATABASE_URL_UNPOOLED")
           or os.environ.get("DATABASE_URL"))
    if not url:
        raise HTTPException(503, "database not configured (set DATABASE_URL_READONLY)")
    return url


def _connect():
    url = _url()
    if url.startswith("sqlite:///"):
        c = sqlite3.connect(url[len("sqlite:///"):], check_same_thread=False)
        return c, "sqlite"
    import psycopg
    c = psycopg.connect(url, autocommit=True, connect_timeout=10)
    try:  # belt and braces: this API only reads; refuse writes at the session level too
        c.execute("SET default_transaction_read_only = on")
    except Exception:
        pass
    return c, "postgres"


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


def r6(x):
    return float(Decimal(str(x)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP))


def cached(resp):
    return JSONResponse(resp, headers={"Cache-Control": "public, max-age=60, s-maxage=600"})


def verification_summary():
    """The verification report without its per-review disagreement list (loaded as its own document)."""
    v = doc("verification_summary")
    if v is None:  # database loaded by an older loader: trim the full report here
        v = doc("verification_report")
        if isinstance(v, dict):
            v = {k: x for k, x in v.items() if k != "disagreements"} | {"disagreements_count": len(v.get("disagreements") or [])}
    return v if isinstance(v, dict) else None


@app.get("/docs", include_in_schema=False)
def docs_redirect():
    return RedirectResponse("/api/docs")


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
    vr = verification_summary() or {}
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
        "verification": {"compared": vr.get("compared"), "agreement": vr.get("agreement"),
                         "verifier_config": vr.get("verifier_config")} if vr else None,
        "golden": {"status": golden.get("status"), "cases": golden.get("cases"), "agreement": golden.get("agreement")}
        if isinstance(golden, dict) and golden else None,
        "run_evidence": {"wall_clock_s_last_invocation": latest.get("wall_clock_s"), "history": rs.get("history")},
        "cost": _cost_summary(cost, run["run_key"]),
    })


def _cost_summary(cost, run_key=None):
    """Billed spend from cost/report.json (loaded as a document), plus the final run's own line when it is listed."""
    if not isinstance(cost, dict) or not cost:
        return None
    spend = cost.get("spend") or {}
    meas = cost.get("measured") or {}
    out = {"billed_api_spend_recorded_usd": spend.get("total_billed_usd"), "per_run": spend.get("per_run"),
           "pilot_cold": (meas.get("runs") or {}).get("cold", {}).get("api_cost_usd"),
           "pilot_warm": (meas.get("runs") or {}).get("warm", {}).get("api_cost_usd"),
           "pilot_warm_new_enrichment_calls": (meas.get("runs") or {}).get("warm", {}).get("new_enrichment_calls"),
           "budget_usd": (cost.get("projection") or {}).get("budget_usd"), "final_run": None}
    if run_key:
        run_dir = f"runs/{run_key}"
        ref = next((r for r in cost.get("refreshes") or [] if r.get("run_dir") == run_dir), None)
        per = (spend.get("per_run") or {}).get(run_dir) or {}
        if ref or per:
            ref = ref or {}
            out["final_run"] = {
                "run_dir": run_dir, "billed_usd": per.get("billed_usd", ref.get("api_cost_usd")), "calls": per.get("calls"),
                "api_equivalent_subscription_usd": ref.get("api_equivalent_subscription_usd"),
                "cost_per_1000_input_rows_usd": ref.get("cost_per_1000_input_rows_usd"),
                "wall_clock_s": ref.get("wall_clock_s"), "invocations": ref.get("invocations"), "rows": ref.get("rows"),
                "invocations_detail": [{k: i.get(k) for k in ("run_id", "phase", "status", "workers", "wall_clock_s",
                                                              "stage_seconds", "enrichment_calls", "budget_cap_usd")}
                                       for i in ref.get("invocations_detail") or []]}
    return out


@app.get("/api/ranking")
def ranking():
    rows = q("SELECT r.*, i.name, i.summary, i.area, i.named_by FROM ranking r LEFT JOIN issues i ON i.issue_id = r.issue_id "
             "ORDER BY r.rank")
    return cached({"rule": "priority_score = severity_sum = complaint_count x mean_severity over complaint and cancellation "
                           "reviews; ties broken by issue_id", "issues": rows,
                   "total_complaints": sum(int(r["complaint_count"]) for r in rows)})


@app.get("/api/issues/{issue_id}")
def issue(issue_id: str, limit: int = Query(20, ge=1, le=100)):
    """Issue detail: monthly trend (with the month's denominator), severity mix, the quotes the name was based on,
    then other member reviews closest to the issue's most common severity first, then most helpful votes."""
    meta = q("SELECT i.*, r.rank, r.complaint_count, r.severity_sum, r.mean_severity, r.priority_score, r.cancellation_count, "
             "r.needs_review_count, r.share_of_complaints FROM issues i LEFT JOIN ranking r ON r.issue_id = i.issue_id "
             "WHERE i.issue_id = %s", (issue_id,), one=True)
    if not meta:
        raise HTTPException(404, f"unknown issue {issue_id}")
    monthly = q("SELECT r.month, COUNT(*) AS complaints, SUM(r.severity) AS severity_sum, MAX(t.reviews) AS month_reviews, "
                "MAX(t.partial_month) AS partial_month FROM membership m JOIN reviews r ON r.review_id = m.review_id "
                "LEFT JOIN trends_monthly t ON t.month = r.month WHERE m.issue_id = %s GROUP BY r.month ORDER BY r.month",
                (issue_id,))
    sev = q("SELECT r.severity, COUNT(*) AS n FROM membership m JOIN reviews r ON r.review_id = m.review_id "
            "WHERE m.issue_id = %s GROUP BY r.severity ORDER BY r.severity", (issue_id,))
    modal = max(sev, key=lambda s: (s["n"], -int(s["severity"])))["severity"] if sev else None
    pack = json.loads(meta.get("evidence_json") or "[]")
    meta["evidence_json"] = pack
    cols = ("r.review_id, r.evidence_quote, r.review_text, r.severity, r.intent, r.sentiment, r.review_likes, "
            "r.review_timestamp, r.labeled_by, r.needs_review")
    ids = [e["review_id"] for e in pack if e.get("review_id")]
    by_id = {r["review_id"]: r for r in q(f"SELECT {cols} FROM reviews r WHERE r.review_id IN ("
                                          + ",".join(["%s"] * len(ids)) + ")", tuple(ids))} if ids else {}
    representative = [dict(by_id.get(e["review_id"]) or {"review_id": e["review_id"]}, quote=e.get("quote"),
                           misfit=bool(e.get("misfit"))) for e in pack if e.get("review_id")]
    representative.sort(key=lambda e: e["misfit"])  # quotes the naming model kept first, flagged misfits last
    exclude = (" AND r.review_id NOT IN (" + ",".join(["%s"] * len(ids)) + ")") if ids else ""
    evidence = q(f"SELECT {cols} FROM membership m JOIN reviews r ON r.review_id = m.review_id "
                 "WHERE m.issue_id = %s AND r.cache_source_id IS NULL" + exclude +
                 " ORDER BY ABS(r.severity - %s), r.review_likes DESC, r.row_num LIMIT %s",
                 (issue_id, *ids, modal if modal is not None else 3, limit))
    return cached({"issue": meta, "monthly": monthly, "severity_distribution": sev, "modal_severity": modal,
                   "representative": representative, "evidence": evidence,
                   "evidence_order": "closest to the issue's most common severity first, then most helpful votes"})


def _token_index():
    ti = doc("memo_tokens")
    return ti if isinstance(ti, list) else []


def _code_limitations(memo_md, n_model):
    """Limitations that code adds to memo.md after the model's own (scope, coverage, golden result)."""
    m = re.search(r"^## Limitations\s*\n(.*?)(?=^## |\Z)", memo_md or "", re.S | re.M)
    bullets = [x[2:].strip() for x in (m.group(1).splitlines() if m else []) if x.startswith("- ")]
    return bullets[n_model:]


def _headline(area, tokens):
    """Recommended area, its top issue and the key numbers, each with the token ID that carries it in the memo."""
    rows = q("SELECT r.issue_id, r.rank, r.complaint_count, r.severity_sum, r.priority_score, r.share_of_complaints, "
             "i.name, i.area FROM ranking r LEFT JOIN issues i ON i.issue_id = r.issue_id ORDER BY r.rank")
    top = next((r for r in rows if r["area"] == area), None)
    by_measure = {t["measure"]: t for t in tokens}
    claims = {c["metric"]: c["claim_id"] for c in q("SELECT claim_id, metric FROM claims WHERE issue_id = %s ORDER BY claim_id",
                                                    (top["issue_id"],))} if top else {}

    def tok(measure):
        t = by_measure.get(measure)
        return {"token": t["token_id"], "value": t["value"]} if t else None

    def find(suffix):
        t = next((t for t in tokens if t["measure"].endswith(suffix)), None)
        return {"token": t["token_id"], "value": t["value"]} if t else None

    verifier = []
    for t in tokens:
        m = re.search(r"sample_severity_sum_by_area_verifier_labels\[(.+?)\]\.severity_sum$", t["measure"])
        if m and re.fullmatch(r"-?\d+", str(t["value"])):
            verifier.append({"area": m.group(1), "token": t["token_id"], "value": t["value"]})
    verifier.sort(key=lambda x: -int(x["value"]))
    area_rows = q("SELECT area, severity_sum, complaint_count, share_of_complaints FROM area_rollup WHERE area = %s",
                  (area,), one=True)
    return {"area": area, "area_rollup": area_rows,
            "top_issue": dict(top, claim_ids=claims) if top else None,
            "area_severity_sum": tok(f"areas[{area}].severity_sum"),
            "period_change": find(f"period_comparison.areas[{area}].change_pp"),
            "verifier_top": verifier[0] if verifier else None,
            "verifier_recommended": next((v for v in verifier if v["area"] == area), None)}


def _notes(area):
    """Code-written context for the memo: areas outside the four decision options, and which area leads on share."""
    decision = [r["area"] for r in q("SELECT area FROM area_rollup WHERE decision_option = 1")] or list(DECISION_AREAS)
    pc = doc("period_comparison") or {}
    outside = [{"area": a, "pp_change": ch.get("pp_change")} for a, ch in (pc.get("change_in_share_of_reviews") or {}).items()
               if a not in decision]
    inside = sorted(((a, ch.get("pp_change")) for a, ch in (pc.get("change_in_share_of_reviews") or {}).items()
                     if a in decision and ch.get("pp_change") is not None), key=lambda x: -x[1])
    iv = {a["area"]: a for a in (doc("area_intervals") or {}).get("areas", []) if a.get("area") in decision}
    leader = max(iv.values(), key=lambda a: a["share_of_complaints"]) if iv else None
    share_note = None
    if leader and area in iv and leader["area"] != area:
        lo_leader, hi_rec = leader["share_of_complaints_ci95"][0], iv[area]["share_of_complaints_ci95"][1]
        share_note = {"leader": leader["area"], "leader_share": leader["share_of_complaints"],
                      "leader_ci95": leader["share_of_complaints_ci95"], "recommended": area,
                      "recommended_share": iv[area]["share_of_complaints"], "recommended_ci95": iv[area]["share_of_complaints_ci95"],
                      "intervals_overlap": lo_leader <= hi_rec}
    sev = q("SELECT area, severity_sum FROM area_rollup WHERE decision_option = 1 ORDER BY severity_sum DESC, area LIMIT 1", one=True)
    return {"decision_areas": decision, "severity_leader": sev, "period_changes_outside_decision_areas": outside,
            "largest_period_change_among_decision_areas": {"area": inside[0][0], "pp_change": inside[0][1]} if inside else None,
            "complaint_share_leader": share_note}


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
    index = _token_index()
    return cached({"recommended_area": rec["recommended_area"], "source": rec["source"], "memo_config": rec["memo_config"],
                   "generated_at": rec["generated_at"], "output": out, "tokens": tokens, "payload": payload,
                   "token_index": index, "claims": claims,
                   "all_claims_match_database": all(c["matches_database"] for c in claims),
                   "limitations_code": _code_limitations(rec["memo_md"], len(out.get("limitations") or [])),
                   "headline": _headline(rec["recommended_area"], index), "notes": _notes(rec["recommended_area"]),
                   "cited_reviews": cited_rows, "memo_md": rec["memo_md"]})


@app.get("/api/trends")
def trends():
    rows = q("SELECT * FROM trends_monthly ORDER BY month")
    for r in rows:
        r["areas"] = json.loads(r.pop("areas_json"))
    decision = [r["area"] for r in q("SELECT area FROM area_rollup WHERE decision_option = 1")] or list(DECISION_AREAS)
    return cached({"months": rows, "period_comparison": doc("period_comparison"), "spike_months": doc("spike_months"),
                   "decision_areas": decision})


@app.get("/api/areas")
def areas():
    return cached({"areas": q("SELECT * FROM area_rollup ORDER BY severity_sum DESC"), "intervals": doc("area_intervals"),
                   "robustness": doc("robustness"), "decision_areas": DECISION_AREAS})


@app.get("/api/analysis/{name}")
def analysis(name: str):
    allowed = {"overview", "period_comparison", "spike_months", "rating_crosstab", "area_intervals", "robustness",
               "premium_only_sensitivity", "app_versions", "reach_weighted_ranking", "trends_monthly"}
    if name not in allowed:
        raise HTTPException(404, f"unknown analysis {name}")
    body = doc(name)
    if body is None:
        raise HTTPException(404, f"{name} not loaded")
    return cached({"name": name, "body": body})


@app.get("/api/evals")
def evals():
    """Evaluation summaries. Per-review lists (verifier disagreements, golden per-case detail, the checker's
    recalculated ranking) are left out to keep the payload small; they stay in the saved files."""
    v = q("SELECT COUNT(*) AS n, SUM(CASE WHEN v.topic = r.topic THEN 1 ELSE 0 END) AS topic, "
          "SUM(CASE WHEN v.intent = r.intent THEN 1 ELSE 0 END) AS intent, "
          "SUM(CASE WHEN v.severity = r.severity THEN 1 ELSE 0 END) AS severity FROM verification v "
          "JOIN reviews r ON r.review_id = v.review_id WHERE v.status = 'completed' AND r.status = 'completed'", one=True)
    def summary(d):  # agreement figures only; per-case detail stays in the saved files
        return {k: x for k, x in d.items() if k != "cases_detail"} if isinstance(d, dict) else d
    golden = summary(doc("golden_results"))
    candidates = {c: summary(doc(f"golden_candidate:{c}")) for c in ("golden-luna-none", "golden-luna-low", "golden-decisions")}

    def checker(d):
        if not isinstance(d, dict):
            return d
        return {k: x for k, x in d.items() if k not in ("calculated_ranking", "input_files_sha256")} | \
            {"calculated_ranking_issues": len(d.get("calculated_ranking") or [])}
    return cached({"verification_sql": v, "verification_report": verification_summary(), "golden": golden,
                   "golden_candidates": {c: d for c, d in candidates.items() if d},
                   "quote_support": doc("quote_support"),
                   "golden_error_analysis": doc("golden_error_analysis"), "planted_error": doc("planted_error"),
                   "injection": doc("injection_check"), "rank_check": doc("rank_check"),
                   "self_check": checker(doc("self_check")), "self_check_full": checker(doc("self_check_full"))})


def _recording_meta(name, body):
    """Duration, size and marker lines of an asciinema v2 cast, read from the stored recording."""
    lines = (body or "").splitlines()
    try:
        head = json.loads(lines[0]) if lines else {}
    except json.JSONDecodeError:
        head = {}
    markers, duration = [], 0.0
    for line in lines[1:]:
        try:
            t, kind, text = json.loads(line)
        except (ValueError, TypeError):
            continue
        duration = max(duration, float(t))
        if kind != "o":
            continue
        for part in str(text).replace("\r", "").split("\n"):
            part = part.strip()
            if re.match(r"^\[(recorder|SIGINT)\]", part) or re.match(r"^\[run\] (interrupted|completed|stopped)", part):
                markers.append([round(float(t), 1), part[:160]])
    return {"name": name, "title": head.get("title"), "width": head.get("width"), "height": head.get("height"),
            "duration_s": round(duration, 1), "markers": markers}


@app.get("/api/run")
def run_evidence():
    recs = q("SELECT name, body FROM documents WHERE kind = 'recording' ORDER BY name")
    txt = {r["name"].split(":", 1)[1] for r in q("SELECT name FROM documents WHERE kind = 'recording_txt'")}
    meta = [dict(_recording_meta(r["name"].split(":", 1)[1], r["body"]), transcript=r["name"].split(":", 1)[1] in txt)
            for r in recs]
    run = q("SELECT run_key FROM runs", one=True)
    return cached({"run_summary": doc("run_summary"), "ingestion_report": doc("ingestion_report"),
                   "ingestion_profile": doc("ingestion_profile"), "checkpoint_before": doc("checkpoint_before"),
                   "checkpoint_after": doc("checkpoint_after"),
                   "cost": _cost_summary(doc("cost_report") or {}, run["run_key"] if run else None),
                   "recordings": [m["name"] for m in meta], "recording_meta": meta, "trace_example_md": doc("trace_example")})


@app.get("/api/recording/{name}")
def recording(name: str):
    row = q("SELECT body FROM documents WHERE name = %s", (f"recording:{name}",), one=True)
    if not row:
        raise HTTPException(404, "no such recording")
    return PlainTextResponse(row["body"], headers={"Cache-Control": "public, max-age=600"})


@app.get("/api/recording/{name}/transcript")
def recording_transcript(name: str):
    """Plain-text transcript of a recording (readable on a phone, unlike the 140-column player)."""
    row = q("SELECT body FROM documents WHERE name = %s", (f"recording_txt:{name}",), one=True)
    if not row:
        raise HTTPException(404, "no transcript for this recording")
    return PlainTextResponse(row["body"], headers={"Cache-Control": "public, max-age=600"})


@app.get("/api/reviews/{review_id}")
def review(review_id: str):
    r = q("SELECT * FROM reviews WHERE review_id = %s", (review_id,), one=True)
    if not r and re.fullmatch(r"[0-9a-fA-F-]{6,35}", review_id.strip()):  # a truncated ID: accept a unique prefix
        hits = q("SELECT review_id FROM reviews WHERE review_id LIKE %s ORDER BY review_id LIMIT 2",
                 (review_id.strip().lower() + "%",))
        if len(hits) == 1:
            r = q("SELECT * FROM reviews WHERE review_id = %s", (hits[0]["review_id"],), one=True)
        elif len(hits) > 1:
            raise HTTPException(404, f"'{review_id}' matches more than one review ID; paste more characters")
    if not r:
        run = q("SELECT analysis_rows, analysis_input FROM runs", one=True) or {}
        raise HTTPException(404, f"No review with ID '{review_id}' in the analysed scope ({run.get('analysis_rows')} reviews of "
                                 f"{run.get('analysis_input')}). Reviews outside the declared scope were profiled but not "
                                 "classified, so they have no trace.")
    review_id = r["review_id"]
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
def reviews(issue_id: str | None = Query(None, description="issue ID (topic.subtopic)"),
            complaints_only: bool = Query(True, description="with issue_id: true (default) counts only the issue's ranked "
                                                            "complaint and cancellation reviews (its membership), as in the "
                                                            "ranking; false returns every review labelled topic.subtopic"),
            intent: str | None = None, topic: str | None = None, q_text: str | None = Query(None, alias="q"),
            status: str | None = None, limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0)):
    where, params = [], []
    if issue_id and complaints_only:
        where.append("review_id IN (SELECT review_id FROM membership WHERE issue_id = %s)"); params.append(issue_id)
    elif issue_id:
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


def _token_checks(index, payload=None):
    """Recompute memo tokens in SQL where the database holds the inputs: area roll-up (A), scope figures (S) and the
    same-months period comparison (T). Returns {token_id: {"database_value", "matches"}}; other tokens are absent."""
    checks = {}
    if not index:
        return checks
    # A: area totals recomputed from reviews + membership + issues (not read from the saved area_rollup table)
    areas = {r["area"]: r for r in q("SELECT i.area, COUNT(*) AS c, SUM(r.severity) AS s, "
                                     "SUM(CASE WHEN r.intent = 'cancellation' THEN 1 ELSE 0 END) AS k, "
                                     "COUNT(DISTINCT m.issue_id) AS n FROM membership m "
                                     "JOIN reviews r ON r.review_id = m.review_id JOIN issues i ON i.issue_id = m.issue_id "
                                     "WHERE r.status = 'completed' AND r." + COMPLAINT + " GROUP BY i.area")}
    total = sum(int(a["c"]) for a in areas.values())
    for t in index:
        m = re.fullmatch(r"areas\[(.+?)\]\.(complaint_count|severity_sum|share_of_complaints|cancellation_count|issues)",
                         t["measure"])
        if t["token_id"].startswith("A") and m:
            a = areas.get(m.group(1))
            val = None
            if a:
                val = {"complaint_count": str(a["c"]), "severity_sum": str(a["s"]), "cancellation_count": str(a["k"]),
                       "issues": str(a["n"]), "share_of_complaints": mean_string(int(a["c"]), total) if total else None}[m.group(2)]
            checks[t["token_id"]] = {"database_value": val, "matches": val == str(t["value"]), "method": "SQL: reviews + membership"}
        unalloc = ((payload or {}).get("unallocated_complaints") or {}).get("area")
        if t["measure"] == "unallocated_complaints.share_of_complaints_percent" and unalloc and total:
            a = areas.get(unalloc)
            val = f"{float(mean_string(int(a['c']), total)) * 100:.1f}%" if a else None
            checks[t["token_id"]] = {"database_value": val, "matches": val == str(t["value"]), "method": "SQL: reviews + membership"}
    # S: scope figures as SQL counts
    st = q("SELECT COUNT(*) AS n, SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS completed, "
           "SUM(CASE WHEN status = 'quarantined' AND reason = 'empty_review_text' THEN 1 ELSE 0 END) AS q_empty, "
           "SUM(CASE WHEN status = 'quarantined' AND (reason IS NULL OR reason <> 'empty_review_text') THEN 1 ELSE 0 END) AS q_other, "
           "SUM(CASE WHEN status = 'completed' THEN needs_review ELSE 0 END) AS needs_review FROM reviews", one=True)
    members = q("SELECT COUNT(*) AS n FROM membership", one=True)["n"]
    v = q("SELECT COUNT(*) AS n, SUM(CASE WHEN v.topic = r.topic THEN 1 ELSE 0 END) AS topic, "
          "SUM(CASE WHEN v.intent = r.intent THEN 1 ELSE 0 END) AS intent, "
          "SUM(CASE WHEN v.severity = r.severity THEN 1 ELSE 0 END) AS severity FROM verification v "
          "JOIN reviews r ON r.review_id = v.review_id WHERE v.status = 'completed' AND r.status = 'completed'", one=True)
    vn = int(v["n"] or 0)
    counts = [("reviews in scope", st["n"]), ("completed classifications", st["completed"]),
              ("quarantined: empty text", st["q_empty"]), ("quarantined: other", st["q_other"]),
              ("unfinished", int(st["n"] or 0) - int(st["completed"] or 0) - int(st["q_empty"] or 0) - int(st["q_other"] or 0)),
              ("needs_review", st["needs_review"]), ("complaint and cancellation records ranked", members),
              ("verification sample compared", vn)]
    rates = [("verifier topic agreement", v["topic"]), ("verifier intent agreement", v["intent"]),
             ("verifier exact severity agreement", v["severity"])]
    for t in index:
        if not t["token_id"].startswith("S"):
            continue
        label = str(t["measure"]).lower()
        for key, val in counts:
            if key in label:
                checks[t["token_id"]] = {"database_value": str(int(val or 0)), "matches": str(int(val or 0)) == str(t["value"]),
                                         "method": "SQL count"}
                break
        else:
            for key, agree in rates:
                if key in label and vn:
                    shown = str(t["value"])
                    places = len(shown.split(".")[1]) if "." in shown else 0
                    val = round(int(agree or 0) / vn, places)
                    checks[t["token_id"]] = {"database_value": f"{val:.{places}f}", "matches": abs(val - float(shown)) < 1e-12,
                                             "method": "SQL: verification vs reviews"}
                    break
    # T: same-months period comparison recomputed from reviews by month and area
    pc = doc("period_comparison") or {}
    periods = pc.get("periods") or {}
    keyed = {"earlier_period": None, "later_period": None}
    for t in index:
        mm = re.search(r"period_comparison\.(earlier_period|later_period)$", t["measure"])
        if mm and t["value"] in periods:
            keyed[mm.group(1)] = t["value"]
    shares = {}
    for which, label in keyed.items():
        if not label:
            continue
        months = periods[label].get("months") or []
        if not months:
            continue
        ph = ",".join(["%s"] * len(months))
        n = q(f"SELECT COUNT(*) AS n FROM reviews WHERE status = 'completed' AND month IN ({ph})", tuple(months), one=True)["n"]
        per = {r["area"]: int(r["c"]) for r in q(f"SELECT area, COUNT(*) AS c FROM reviews WHERE status = 'completed' AND "
                                                 f"{COMPLAINT} AND month IN ({ph}) GROUP BY area", tuple(months))}
        allc = sum(per.values())
        shares[which] = {"reviews": int(n), "areas": {a: r6(c / n) for a, c in per.items()} if n else {},
                         "complaint_share": r6(allc / n) if n else None}
    for t in index:
        meas, shown = t["measure"], str(t["value"])
        val = None
        mm = re.search(r"denominators\.(earlier_period|later_period)\.(reviews|complaint_share)$", meas)
        if mm and mm.group(1) in shares:
            x = shares[mm.group(1)][mm.group(2)]
            val = str(x) if mm.group(2) == "reviews" else (None if x is None else f"{x * 100:.1f}%")
        mm = re.search(r"period_comparison\.(?:non_decision_)?areas\[(.+?)\]\.(share_of_reviews_earlier_period|share_of_reviews_later_period|change_pp)$", meas)
        if mm and len(shares) == 2:
            a = mm.group(1)
            e, l = shares["earlier_period"]["areas"].get(a, 0.0), shares["later_period"]["areas"].get(a, 0.0)
            val = {"share_of_reviews_earlier_period": f"{e * 100:.1f}%", "share_of_reviews_later_period": f"{l * 100:.1f}%",
                   "change_pp": f"{round((l - e) * 100, 3):+.1f} pp"}[mm.group(2)]
        if val is not None:
            checks[t["token_id"]] = {"database_value": val, "matches": val == shown, "method": "SQL: reviews by month and area"}
    return checks


@app.get("/api/consistency")
def consistency():
    """Recompute the baseline ranking from reviews + membership in SQL and compare it with the saved table; also
    recompute the memo's area, scope and period-comparison numbers where the database holds their inputs."""
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
    rec = q("SELECT payload_json FROM recommendation WHERE id = 1", one=True)
    token_checks = _token_checks(_token_index(), json.loads(rec["payload_json"]) if rec else None)
    return {"ranking_matches": not mismatches and len(saved) == len(fresh), "issues_saved": len(saved),
            "issues_recomputed": len(fresh), "mismatches": mismatches[:10], "ungrouped_complaints": ungrouped,
            "claims_match": not claim_mismatch, "claim_mismatches": claim_mismatch[:10],
            "token_checks": token_checks, "tokens_checked": len(token_checks),
            "tokens_match": all(c["matches"] for c in token_checks.values()),
            "method": "SQL over the reviews and membership tables at request time; the saved ranking table is not used "
                      "for the recomputation."}

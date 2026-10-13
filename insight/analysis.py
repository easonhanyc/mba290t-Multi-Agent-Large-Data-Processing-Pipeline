"""Stage 5b - descriptive analysis (code only, no model calls), run after the baseline ranking.

Everything here is arithmetic over saved records + source metadata, with denominators:
  overview.json              label distributions, needs_review and tier shares, sentiment
  trends_monthly.csv         per month: reviews in scope, complaints, complaint share by decision area
                             (first and last calendar months are partial and flagged)
  period_comparison.json     same calendar months one year apart (Jun-Oct 2022 vs Jun-Oct 2023), with
                             Wilson 95% intervals and the change in percentage points
  spike_months.json          months with unusual review volume: which issues grew most vs. the other months
  app_versions.csv           complaint share by app-version family (missing versions reported separately)
  rating_crosstab.json       star rating x intent / severity (metadata check only; stars never set labels)
  reach_weighted_ranking.csv ADDITIONAL business view: severity weighted by (1 + helpful votes)
  area_intervals.json        Wilson 95% intervals for each area's share of complaints and of all reviews
  robustness.json            area shares on the verifier sample under enricher vs verifier labels
The baseline ranking (ranking.csv) is unchanged by any of these.
"""

import csv
import io
import json
import math
from collections import Counter, defaultdict
from decimal import ROUND_HALF_UP, Decimal

from . import labels
from .util import atomic_write_json, atomic_write_text

COMPARE_MONTHS = ("06", "07", "08", "09", "10")
PARTIAL_MONTHS = {"2022-05": "starts 2022-05-17", "2023-11": "ends 2023-11-15"}


def wilson(k, n, z=1.96):
    if n == 0:
        return None, None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return round(max(0.0, c - h), 6), round(min(1.0, c + h), 6)


def r6(x):
    return float(Decimal(str(x)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP))


def load_joined(store, label_config):
    """Completed records joined with source metadata (timestamp, rating, likes, app_version)."""
    rows = []
    for r in store.conn.execute(
            "SELECT x.review_id, x.topic, x.subtopic, x.intent, x.severity, x.sentiment, x.needs_review, x.labeled_by, "
            "x.cache_source_id, v.review_timestamp, v.review_rating, v.review_likes, v.app_version "
            "FROM results x JOIN reviews v ON v.review_id = x.review_id AND v.duplicate_id = 0 "
            "WHERE x.label_config = ? AND x.status = 'completed'", (label_config,)):
        likes = int(r[11]) if str(r[11]).isdigit() else 0
        rows.append({"review_id": r[0], "topic": r[1], "subtopic": r[2], "intent": r[3], "severity": int(r[4]),
                     "sentiment": float(r[5]), "needs_review": bool(r[6]), "labeled_by": r[7], "cached": bool(r[8]),
                     "month": r[9][:7], "rating": r[10], "likes": likes, "app_version": r[12].strip(),
                     "area": labels.AREA_OF_TOPIC[r[1]], "issue_id": f"{r[1]}.{r[2]}",
                     "complaint": r[3] in labels.COMPLAINT_INTENTS})
    return rows


def overview(rows, store, label_config):
    n = len(rows)
    q = store.conn.execute("SELECT COUNT(*) FROM results WHERE label_config=? AND status='quarantined'",
                           (label_config,)).fetchone()[0]
    complaints = [r for r in rows if r["complaint"]]
    return {
        "completed": n, "quarantined": q, "complaint_or_cancellation": len(complaints),
        "complaint_share": r6(len(complaints) / n) if n else None,
        "intent": dict(Counter(r["intent"] for r in rows).most_common()),
        "topic": dict(Counter(r["topic"] for r in rows).most_common()),
        "topic_among_complaints": dict(Counter(r["topic"] for r in complaints).most_common()),
        "severity": {str(k): v for k, v in sorted(Counter(r["severity"] for r in rows).items())},
        "severity_among_complaints": {str(k): v for k, v in sorted(Counter(r["severity"] for r in complaints).items())},
        "mean_sentiment": r6(sum(r["sentiment"] for r in rows) / n) if n else None,
        "needs_review": sum(r["needs_review"] for r in rows),
        "labeled_by": dict(Counter(r["labeled_by"] for r in rows).most_common()),
        "exact_text_cache_reuses": sum(r["cached"] for r in rows),
        "note": "Counts are review records in the declared scope (each original ID counted once, cache reuses included).",
    }


def monthly(rows):
    by_month = defaultdict(lambda: {"reviews": 0, "complaints": 0, "areas": Counter(), "cancellations": 0})
    for r in rows:
        m = by_month[r["month"]]
        m["reviews"] += 1
        if r["complaint"]:
            m["complaints"] += 1
            m["areas"][r["area"]] += 1
            m["cancellations"] += r["intent"] == "cancellation"
    out = []
    areas = sorted({r["area"] for r in rows})
    for month in sorted(by_month):
        m = by_month[month]
        row = {"month": month, "partial_month": PARTIAL_MONTHS.get(month, ""), "reviews": m["reviews"],
               "complaints": m["complaints"], "complaint_share": r6(m["complaints"] / m["reviews"]) if m["reviews"] else 0,
               "cancellations": m["cancellations"]}
        for a in areas:
            row[f"{a}_complaints"] = m["areas"][a]
            row[f"{a}_share_of_reviews"] = r6(m["areas"][a] / m["reviews"]) if m["reviews"] else 0
        out.append(row)
    return out, areas


def period_comparison(rows):
    """Same calendar months in consecutive years (full months only): Jun-Oct 2022 vs Jun-Oct 2023."""
    periods = {"2022 Jun-Oct": {f"2022-{m}" for m in COMPARE_MONTHS}, "2023 Jun-Oct": {f"2023-{m}" for m in COMPARE_MONTHS}}
    res = {}
    for name, months in periods.items():
        sub = [r for r in rows if r["month"] in months]
        n = len(sub)
        comp = [r for r in sub if r["complaint"]]
        areas = Counter(r["area"] for r in comp)
        issues = Counter(r["issue_id"] for r in comp)
        res[name] = {"months": sorted(months), "reviews": n, "complaints": len(comp),
                     "complaint_share": r6(len(comp) / n) if n else None, "complaint_share_ci95": wilson(len(comp), n),
                     "areas": {a: {"complaints": k, "share_of_reviews": r6(k / n) if n else None,
                                   "ci95": wilson(k, n)} for a, k in sorted(areas.items())},
                     "top_issues": {i: {"complaints": k, "share_of_reviews": r6(k / n) if n else None}
                                    for i, k in issues.most_common(10)}}
    a, b = res["2022 Jun-Oct"], res["2023 Jun-Oct"]
    change = {}
    for area in sorted(set(a["areas"]) | set(b["areas"])):
        pa = (a["areas"].get(area) or {}).get("share_of_reviews") or 0
        pb = (b["areas"].get(area) or {}).get("share_of_reviews") or 0
        change[area] = {"pp_change": round((pb - pa) * 100, 3), "2022": pa, "2023": pb}
    return {"periods": res, "change_in_share_of_reviews": change,
            "method": "share = complaint/cancellation reviews in the area / all classified reviews in the period; "
                      "Wilson 95% intervals; identical calendar months one year apart avoid the partial first/last "
                      "months and seasonal mix. Descriptive only: reviews are self-selected, not a customer census."}


def spike_months(rows, monthly_rows):
    vols = sorted(m["reviews"] for m in monthly_rows if not m["partial_month"])
    if not vols:
        return {"spikes": []}
    median = vols[len(vols) // 2]
    spikes = [m["month"] for m in monthly_rows if not m["partial_month"] and m["reviews"] > 1.8 * median]
    out = []
    for month in spikes:
        inside = [r for r in rows if r["month"] == month]
        outside = [r for r in rows if r["month"] != month and r["month"] not in PARTIAL_MONTHS]
        ci, co = Counter(r["issue_id"] for r in inside if r["complaint"]), Counter(r["issue_id"] for r in outside if r["complaint"])
        lifts = []
        for issue, k in ci.items():
            si, so = k / len(inside), co[issue] / len(outside) if outside else 0
            lifts.append({"issue_id": issue, "complaints_in_month": k, "share_in_month": r6(si), "share_other_months": r6(so),
                          "pp_difference": round((si - so) * 100, 3)})
        lifts.sort(key=lambda x: (-x["pp_difference"], x["issue_id"]))
        out.append({"month": month, "reviews": len(inside), "median_full_month_reviews": median,
                    "complaint_share": r6(sum(r["complaint"] for r in inside) / len(inside)),
                    "largest_increases": lifts[:5]})
    return {"rule": "full months with more than 1.8x the median full-month review count", "spikes": out}


def app_versions(rows):
    fam = defaultdict(lambda: [0, 0])
    for r in rows:
        v = r["app_version"]
        key = ".".join(v.split(".")[:2]) if v else "(missing)"
        fam[key][0] += 1
        fam[key][1] += r["complaint"]
    out = []
    for key, (n, k) in fam.items():
        lo, hi = wilson(k, n)
        out.append({"app_version_family": key, "reviews": n, "complaints": k, "complaint_share": r6(k / n),
                    "ci95_low": lo, "ci95_high": hi})
    out.sort(key=lambda x: (-x["reviews"], x["app_version_family"]))
    return out


def rating_crosstab(rows):
    intent = defaultdict(Counter)
    sev = defaultdict(Counter)
    for r in rows:
        intent[r["rating"]][r["intent"]] += 1
        sev[r["rating"]][str(r["severity"])] += 1
    return {"note": "Star ratings are metadata only; they never set or change a label. This table checks that labels "
                    "relate sensibly to stars (e.g. praise concentrated in 5-star reviews).",
            "intent_by_rating": {k: dict(v) for k, v in sorted(intent.items())},
            "severity_by_rating": {k: dict(sorted(v.items())) for k, v in sorted(sev.items())}}


def reach_weighted(rows):
    agg = defaultdict(lambda: {"complaint_count": 0, "severity_sum": 0, "helpful_votes": 0, "weighted_severity": 0})
    for r in rows:
        if not r["complaint"]:
            continue
        a = agg[r["issue_id"]]
        a["complaint_count"] += 1
        a["severity_sum"] += r["severity"]
        a["helpful_votes"] += r["likes"]
        a["weighted_severity"] += r["severity"] * (1 + r["likes"])
    out = [{"issue_id": k, **v} for k, v in agg.items()]
    out.sort(key=lambda x: (-x["weighted_severity"], x["issue_id"]))
    for i, r in enumerate(out, 1):
        r["rank"] = i
    return out


def area_intervals(rows):
    n = len(rows)
    comp = [r for r in rows if r["complaint"]]
    k_all = Counter(r["area"] for r in comp)
    out = []
    for area, k in sorted(k_all.items(), key=lambda x: -x[1]):
        out.append({"area": area, "decision_option": area in labels.DECISION_AREAS, "complaints": k,
                    "share_of_complaints": r6(k / len(comp)), "share_of_complaints_ci95": wilson(k, len(comp)),
                    "share_of_reviews": r6(k / n), "share_of_reviews_ci95": wilson(k, n)})
    return {"reviews": n, "complaints": len(comp), "areas": out,
            "note": "Sampling intervals for a uniform random sample of the corpus; they do not include labelling error "
                    "(see the golden-set and verifier results for that)."}


def robustness(store, cfg, rows_by_id):
    vconf = cfg.stage_config("verify")
    pairs = []
    for v in store.verifications(vconf):
        r = rows_by_id.get(v["review_id"])
        if v["status"] == "completed" and r is not None:
            pairs.append((r, v))
    if not pairs:
        return {"status": "no verifier sample"}
    # The sample is of distinct texts; weight each by the rows that share its text so area totals are row-based
    # like the baseline ranking (exact-text aliases point at their representative via cache_source_id).
    weight = Counter()
    for rid, src in store.conn.execute("SELECT review_id, cache_source_id FROM results WHERE label_config = ? AND "
                                       "status = 'completed'", (cfg.label_config(),)):
        weight[src or rid] += 1

    def tally(get):
        cnt, sev = Counter(), Counter()
        for p in pairs:
            topic, intent, severity = get(p)
            if intent in labels.COMPLAINT_INTENTS:
                w = weight[p[0]["review_id"]] or 1
                cnt[labels.AREA_OF_TOPIC[topic]] += w
                sev[labels.AREA_OF_TOPIC[topic]] += w * int(severity)
        tot = sum(cnt.values())
        areas = {a: {"complaints": cnt[a], "share_of_complaints": r6(cnt[a] / tot), "severity_sum": sev[a]}
                 for a, _ in sev.most_common()}
        return areas, tot

    enr, ne = tally(lambda p: (p[0]["topic"], p[0]["intent"], p[0]["severity"]))
    ver, nv = tally(lambda p: (p[1]["topic"], p[1]["intent"], p[1]["severity"]))
    order = lambda d, key: [a for a in sorted(d, key=lambda a: -d[a][key]) if a in labels.DECISION_AREAS]
    te, tv = order(enr, "severity_sum"), order(ver, "severity_sum")
    ce, cv = order(enr, "complaints"), order(ver, "complaints")
    return {"sample": len(pairs), "row_weighted_reviews": sum(weight[p[0]["review_id"]] or 1 for p in pairs),
            "metric": "severity_sum (the baseline priority) over complaint and cancellation reviews, row-weighted",
            "enricher_labels": {"complaints": ne, "areas": enr}, "verifier_labels": {"complaints": nv, "areas": ver},
            "decision_area_order_enricher": te, "decision_area_order_verifier": tv,
            "top_decision_area_enricher": te[0] if te else None, "top_decision_area_verifier": tv[0] if tv else None,
            "same_top_decision_area": bool(te and tv and te[0] == tv[0]),
            "by_complaint_count": {"top_enricher": ce[0] if ce else None, "top_verifier": cv[0] if cv else None},
            "note": "Same reviews (the declared verification sample, distinct texts weighted by the rows sharing each "
                    "text), labelled independently by two model roles. Sampling error is not included."}


def _csv(rows, columns=None):
    buf = io.StringIO()
    if not rows:
        return ""
    columns = columns or list(rows[0])
    w = csv.DictWriter(buf, fieldnames=columns, lineterminator="\n", extrasaction="ignore")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


def run_analysis(store, cfg, log=print):
    lc = cfg.label_config()
    rows = load_joined(store, lc)
    out_dir = store.run_dir / "analysis"
    ov = overview(rows, store, lc)
    mon, areas = monthly(rows)
    pc = period_comparison(rows)
    sp = spike_months(rows, mon)
    av = app_versions(rows)
    rc = rating_crosstab(rows)
    rw = reach_weighted(rows)
    ai = area_intervals(rows)
    rb = robustness(store, cfg, {r["review_id"]: r for r in rows})
    atomic_write_json(out_dir / "overview.json", ov)
    atomic_write_text(out_dir / "trends_monthly.csv", _csv(mon))
    atomic_write_json(out_dir / "period_comparison.json", pc)
    atomic_write_json(out_dir / "spike_months.json", sp)
    atomic_write_text(out_dir / "app_versions.csv", _csv(av))
    atomic_write_json(out_dir / "rating_crosstab.json", rc)
    atomic_write_text(out_dir / "reach_weighted_ranking.csv",
                      _csv(rw, ["rank", "issue_id", "complaint_count", "severity_sum", "helpful_votes", "weighted_severity"]))
    atomic_write_json(out_dir / "area_intervals.json", ai)
    atomic_write_json(out_dir / "robustness.json", rb)
    log(f"[analysis] {len(rows)} completed records: {len(mon)} months, {len(sp.get('spikes', []))} spike months, "
        f"{len(av)} app-version families; verifier robustness: {rb.get('same_top_decision_area', 'n/a')} (no model calls)")
    return {"overview": ov, "period_comparison": pc, "spikes": sp, "area_intervals": ai, "robustness": rb,
            "reach_weighted_top": rw[:5]}

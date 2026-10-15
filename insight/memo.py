"""Stage 6 - recommend (model + code).

The memo model sees only saved aggregates (top-ranked issues, area roll-up, scope figures)
and a bounded evidence pack of exact quotes. It must not write digits: every number is a
token ({C01}, {A02}, {S03}) that code replaces with the saved value. Code validates the
output (tokens exist, no stray digits, cited review IDs are in the pack, valid areas);
one retry, then a deterministic template memo clearly marked as such.
claims.csv lists every issue-level number (C##) that appears in the memo; memo_tokens.csv lists every
token (C##, A## area roll-up, S## scope figure, T## trend/robustness) with its value, what it measures
and its source file. In the rendered memo every filled number carries its token ID, e.g. "52577 (C02)".
"""

import csv
import io
import json
import re
from pathlib import Path

from . import labels, prompts
from .analysis import positive_increases, shown_pp as _shown_pp  # noqa: F401  (shared with spike_months.json)
from .control import Dispatcher, Task
from .util import PROJECT_ROOT, atomic_write_json, atomic_write_text, read_json, short_hash, utc_now

TOKEN = re.compile(r"\{([CAST]\d{2,3})\}")
UNALLOCATED_AREA = labels.AREA_OF_TOPIC["other"]  # general/unspecified: generic criticism with no specific area
METRICS = ("complaint_count", "severity_sum", "mean_severity", "priority_score")
# Fields the memo model returns in addition to the base schema in prompts.memo_request (prose, token rules apply).
EXTRA_PROSE_FIELDS = {
    "next_quarter_actions": "two to four concrete next-quarter actions, each tied to a named top issue",
    "what_would_change_the_call": "one to three pieces of evidence that would change the recommendation",
}
GOLDEN_RESULTS = PROJECT_ROOT / "evals" / "golden" / "results.json"
_GOLDEN_CLAUSE = re.compile(r";\s*the golden-set comparison \(human labels\) is (?:still pending|reported separately)\.?")
TOKEN_SOURCES = {  # payload section -> saved file that holds the value behind its tokens (nested keys inherit it)
    "top_issues": "claims.csv (from ranking.csv)", "areas": "area_rollup.json",
    "unallocated_complaints": "area_rollup.json",
    "period_comparison": "analysis/period_comparison.json", "area_shares_with_sampling_intervals": "analysis/area_intervals.json",
    "spike_months": "analysis/spike_months.json", "verifier_robustness": "analysis/robustness.json",
    "premium_only_sensitivity": "analysis/premium_only_sensitivity.json",
}


def _pct(x):
    return "n/a" if x is None else f"{float(x) * 100:.1f}%"


def _overlaps(a, b):
    return a[0] is not None and b[0] is not None and a[0] <= b[1] and b[0] <= a[1]


def _trend_section(analysis, tokens, refs=None):
    """Descriptive trend/robustness facts for the memo, each number behind a T## token.

    refs: {"issue": {issue_id: top_issues row}, "area": {area: areas row}} so a figure already in the payload is
    cited by its existing C##/A## token instead of a duplicate. New tokens are numbered after the existing ones
    (period comparison, intervals, spikes, robustness first), so earlier T## IDs keep their meaning.
    """
    if not analysis:
        return {}
    refs = refs or {"issue": {}, "area": {}}
    def tok(value):  # value shown to the model (so it can describe direction); the token is what it must write
        tid = f"T{len([t for t in tokens if t.startswith('T')]) + 1:02d}"
        tokens[tid] = str(value)
        return {"value": str(value), "token": "{" + tid + "}"}
    out = {}
    pc = analysis.get("period_comparison") or {}
    periods = pc.get("periods", {})
    if len(periods) >= 2:
        # period labels contain years, so they are tokens too (the model never types a digit)
        earlier, later = sorted(periods)[:2]
        out["period_comparison"] = {"method": pc.get("method"), "earlier_period": tok(earlier), "later_period": tok(later),
                                    "comparison_scope": "areas lists the four decision areas only; areas that are not "
                                                        "decision options are under non_decision_areas",
                                    "largest_increase_among_the_four_decision_areas":
                                        (pc.get("largest_increase") or {}).get("among_the_four_decision_areas"),
                                    "denominators": {}, "areas": []}
        for key, label in (("earlier_period", earlier), ("later_period", later)):
            v = periods[label]
            out["period_comparison"]["denominators"][key] = {"reviews": tok(v["reviews"]),
                                                             "complaint_share": tok(_pct(v["complaint_share"]))}
        for area, ch in sorted(pc.get("change_in_share_of_reviews", {}).items()):
            if area not in labels.DECISION_AREAS:
                continue
            y0, y1 = earlier.split()[0], later.split()[0]  # change_in_share_of_reviews is keyed by year
            out["period_comparison"]["areas"].append({
                "area": area, "share_of_reviews_earlier_period": tok(_pct(ch.get(y0))),
                "share_of_reviews_later_period": tok(_pct(ch.get(y1))), "change_pp": tok(f"{ch['pp_change']:+.1f} pp")})
    ai = analysis.get("area_intervals") or {}
    if ai.get("areas"):
        dec = [a for a in ai["areas"] if a["decision_option"]]
        out["area_shares_with_sampling_intervals"] = [
            {"area": a["area"], "share_of_complaints": tok(_pct(a["share_of_complaints"])),
             "ci_low": tok(_pct(a["share_of_complaints_ci95"][0])), "ci_high": tok(_pct(a["share_of_complaints_ci95"][1])),
             # computed by code: areas whose 95% interval overlaps this one (empty = the difference is outside sampling error)
             "interval_overlaps_with": [b["area"] for b in dec if b is not a and
                                        _overlaps(a["share_of_complaints_ci95"], b["share_of_complaints_ci95"])]}
            for a in dec]
    sp = analysis.get("spikes") or {}
    if sp.get("spikes"):
        # only issues whose share actually rose in the spike month (as printed, one decimal) count as increases
        out["spike_months"] = [{"month": tok(x["month"]), "reviews": tok(x["reviews"]),
                                "median_full_month_reviews": tok(x["median_full_month_reviews"]),
                                "measure": "the issue's complaint and cancellation reviews as a share of all reviews in "
                                           "the month, minus the same share in the other full months (share of reviews)",
                                "largest_increases": [{"issue_id": l["issue_id"], "pp_difference": tok(f"{l['pp_difference']:+.1f} pp")}
                                                      for l in positive_increases(x["largest_increases"])[:3]]}
                               for x in sp["spikes"]]
    rb = analysis.get("robustness") or {}
    if rb.get("sample"):
        out["verifier_robustness"] = {"sample_reviews": tok(rb["sample"]),
                                      "metric": rb.get("metric", "complaint count"),
                                      "top_decision_area_enricher_labels": rb.get("top_decision_area_enricher"),
                                      "top_decision_area_verifier_labels": rb.get("top_decision_area_verifier"),
                                      "decision_area_order_enricher_labels": rb.get("decision_area_order_enricher"),
                                      "decision_area_order_verifier_labels": rb.get("decision_area_order_verifier"),
                                      "same_top_area": rb.get("same_top_decision_area"),
                                      "top_by_complaint_count": dict(rb.get("by_complaint_count") or {},
                                                                     note="area names only, no counts: state in words, "
                                                                          "cite no token")}
        for who in ("enricher", "verifier"):  # the sample's per-area severity sums behind each ordering
            areas = (rb.get(f"{who}_labels") or {}).get("areas") or {}
            order = rb.get(f"decision_area_order_{who}") or []
            if areas and order:
                out["verifier_robustness"][f"sample_severity_sum_by_area_{who}_labels"] = [
                    {"area": a, "severity_sum": tok(areas[a]["severity_sum"])} for a in order if a in areas]
    # --- tokens added after the ones above (numbered after them) ---
    if out.get("period_comparison"):  # areas that are not decision options, kept apart from the four-area comparison
        earlier, later = sorted(periods)[:2]
        y0, y1 = earlier.split()[0], later.split()[0]
        out["period_comparison"]["non_decision_areas"] = [
            {"area": area, "share_of_reviews_earlier_period": tok(_pct(ch.get(y0))),
             "share_of_reviews_later_period": tok(_pct(ch.get(y1))), "change_pp": tok(f"{ch['pp_change']:+.1f} pp")}
            for area, ch in sorted(pc.get("change_in_share_of_reviews", {}).items()) if area not in labels.DECISION_AREAS]
    ps = analysis.get("premium_only_sensitivity") or {}
    w = ps.get("without_payment_word") or {}
    if ps.get("issue_records") and w.get("records") is not None:
        issue = refs["issue"].get(ps["issue_id"]) or {}
        area = lambda a, key: (refs["area"].get(a) or {}).get(key)
        own = ps["area"]
        out["premium_only_sensitivity"] = {
            "what": "upper-bound sensitivity of the billing/support lead to the premium-only topic boundary, computed "
                    "by code; not a relabelling",
            "issue_id": ps["issue_id"], "payment_words_case_insensitive": w["words"],
            "issue_complaint_records": issue.get("complaint_count") or tok(ps["issue_records"]),
            "records_without_payment_word": tok(w["records"]),
            "their_severity_sum": tok(w["severity_sum"]),
            "billing_support_severity_sum": area(own, "severity_sum") or tok(ps["decision_area_severity_sums"][own]),
            "billing_support_severity_sum_without_them": tok(w["billing_support_severity_sum_without_them"]),
            "decision_area_order_without_them": w["decision_area_order_without_them"],
            "decision_areas_above_billing_support_without_them": w["decision_areas_above_billing_support_without_them"],
            "other_decision_area_severity_sums": [
                {"area": a, "severity_sum": area(a, "severity_sum") or tok(ps["decision_area_severity_sums"][a])}
                for a in ps["decision_area_order"] if a != own],
            "interpretation": ps.get("interpretation"),
        }
    return out


def build_payload(ranking, issues_doc, areas_doc, scope, evidence_issues, quotes_per_issue, top_n, analysis=None):
    names = {i["issue_id"]: i for i in issues_doc["issues"]}
    tokens, claims = {}, []
    rank_rows = []
    for r in ranking[:top_n]:
        meta = names.get(r["issue_id"], {})
        row = {"issue_id": r["issue_id"], "name": meta.get("name", r["issue_id"]),
               "area": labels.AREA_OF_TOPIC[r["issue_id"].split(".")[0]]}
        for k in ("definition", "summary"):  # what the issue covers (taxonomy definition, group-stage summary)
            if meta.get(k):
                row[k] = meta[k]
        for m in METRICS:
            cid = f"C{len(claims) + 1:02d}"
            claims.append({"claim_id": cid, "issue_id": r["issue_id"], "metric": m, "value": str(r[m])})
            tokens[cid] = str(r[m])
            row[m] = {"value": r[m], "token": "{" + cid + "}"}
        rank_rows.append(row)
    area_rows = []
    for a in areas_doc["areas"]:
        entry = {"area": a["area"], "decision_option": a["decision_option"]}
        for m in ("complaint_count", "severity_sum", "share_of_complaints"):
            aid = f"A{len([t for t in tokens if t.startswith('A')]) + 1:02d}"
            tokens[aid] = str(a[m])
            entry[m] = {"value": a[m], "token": "{" + aid + "}"}
        area_rows.append(entry)
    unallocated = None
    for entry, a in zip(area_rows, areas_doc["areas"]):  # numbered after A01..A18 so those IDs keep their meaning
        if a["area"] == UNALLOCATED_AREA:
            aid = f"A{len([t for t in tokens if t.startswith('A')]) + 1:02d}"
            tokens[aid] = _pct(a["share_of_complaints"])
            unallocated = {"area": a["area"], "what": "complaint and cancellation records labelled with no specific area "
                                                      "(generic criticism); not allocated to any decision area",
                           "complaint_count": entry["complaint_count"],
                           "share_of_complaints_percent": {"value": tokens[aid], "token": "{" + aid + "}"}}
    scope_rows = {}
    for label, value, source in scope:
        sid = f"S{len(scope_rows) + 1:02d}"
        tokens[sid] = str(value)
        scope_rows[sid] = {"label": label, "value": value, "source": source, "token": "{" + sid + "}"}
    evidence = []
    for r in ranking[:evidence_issues]:
        for e in names.get(r["issue_id"], {}).get("evidence", [])[:quotes_per_issue]:
            evidence.append({"issue_id": r["issue_id"], "review_id": e["review_id"], "quote": e["quote"]})
    payload = {
        "question": "Where should the next quarter of product-improvement effort go: access/onboarding, usability, "
                    "playback/performance, or billing/support?",
        "decision_rule": "baseline priority = severity_sum over complaint and cancellation reviews; areas sum their issues",
        "top_issues": rank_rows, "areas": area_rows, "scope_figures": scope_rows, "evidence": evidence,
    }
    if unallocated:
        payload["unallocated_complaints"] = unallocated
    trends = _trend_section(analysis, tokens, {"issue": {r["issue_id"]: r for r in rank_rows},
                                               "area": {e["area"]: e for e in area_rows}})
    if trends:
        payload["trends_and_robustness"] = trends
    return payload, tokens, claims


def _no_interval_overlaps(payload):
    shares = ((payload or {}).get("trends_and_robustness") or {}).get("area_shares_with_sampling_intervals") or []
    return bool(shares) and all(not s.get("interval_overlaps_with") for s in shares)


def validate(data, tokens, evidence_ids, payload=None):
    problems = []
    no_overlap = _no_interval_overlaps(payload)
    if not isinstance(data, dict):
        return ["output is not an object"]
    if data.get("recommended_area") not in labels.DECISION_AREAS:
        problems.append("recommended_area is not one of the four decision areas")
    prose = [("recommendation", data.get("recommendation"))]
    prose += [(f"rationale[{i}]", s) for i, s in enumerate(data.get("rationale") or [])]
    prose += [(f"limitations[{i}]", s) for i, s in enumerate(data.get("limitations") or [])]
    alts = data.get("alternatives") or []
    prose += [(f"alternatives[{i}]", a.get("why_not_first") if isinstance(a, dict) else None) for i, a in enumerate(alts)]
    for field in EXTRA_PROSE_FIELDS:  # optional for old/cached outputs; when present the same token rules apply
        if field in data:
            items = data[field] if isinstance(data[field], list) else [data[field]]
            prose += [(f"{field}[{i}]", s) for i, s in enumerate(items)]
    for where, text in prose:
        if not isinstance(text, str) or not text.strip():
            problems.append(f"{where} is empty")
            continue
        for t in TOKEN.findall(text):
            if t not in tokens:
                problems.append(f"{where} cites unknown token {{{t}}}")
        bare = TOKEN.sub("{}", text)
        hit = re.search(r"\d", bare)
        if hit:
            snippet = bare[max(0, hit.start() - 30):hit.end() + 30].replace("\n", " ")
            problems.append(f"{where} contains a typed digit (numbers must be tokens): ...{snippet}...")
        if no_overlap and re.search(r"within (the )?sampling (error|noise)", text, re.I):
            problems.append(f"{where} says 'within sampling error', but no two decision areas' share intervals overlap "
                            "(interval_overlaps_with is empty for every area): say which share is higher instead")
        stray = re.search(r"\{[^{}]*\}", TOKEN.sub("", text))  # code would leave it unfilled in memo.md
        if stray:
            problems.append(f"{where} contains {stray.group(0)}, which is not a token: write the token from the "
                            "input's token field (a letter and digits in braces), never a key name in braces")
    seen = set()
    for a in alts:
        area = a.get("area") if isinstance(a, dict) else None
        if area == data.get("recommended_area") or area in seen or area not in labels.DECISION_AREAS:
            problems.append(f"invalid or repeated alternative area {area!r}")
        seen.add(area)
    for rid in data.get("cited_reviews") or []:
        if rid not in evidence_ids:
            problems.append(f"cited review {rid} is not in the evidence pack")
    if not (data.get("rationale") and data.get("limitations")):
        problems.append("rationale and limitations are required")
    return problems


def memo_request(payload, review_ids, max_output_tokens, template=None):
    """prompts.memo_request plus the required action fields (next-quarter actions, what would change the call)."""
    req = prompts.memo_request(payload, review_ids, max_output_tokens, template=template)
    schema = req["schema"]
    for field in EXTRA_PROSE_FIELDS:
        schema["properties"][field] = {"type": "array", "items": {"type": "string"}}
        if field not in schema["required"]:
            schema["required"].append(field)
    return req


_SIGNED_TOKEN = re.compile(r"([+-]?)\{([CAST]\d{2,3})\}")


def _sub_tokens(text, tokens, fmt):
    """Replace tokens; a sign typed just before a token whose value already carries one ('+{T38}' with value
    '+25.1 pp') is dropped, so the memo never prints '++25.1 pp'."""
    def one(m):
        value = tokens[m.group(2)]
        sign = "" if value[:1] in "+-" else m.group(1)
        return sign + fmt(value, m.group(2))
    return _SIGNED_TOKEN.sub(one, text)


def fill(text, tokens):
    return _sub_tokens(text, tokens, lambda value, tid: value)


def fill_cited(text, tokens):
    """Fill tokens as 'value (ID)', e.g. '52577 (C02)', so every number in the memo traces to a saved token."""
    return _sub_tokens(text, tokens, lambda value, tid: f"{value} ({tid})")


def token_index(payload, tokens):
    """One row per token: ID, kind, value, what it measures (its place in the payload) and the saved source file."""
    rows = {}

    def walk(node, path, source):
        if isinstance(node, dict):
            tid = node.get("token", "").strip("{}") if isinstance(node.get("token"), str) else ""
            if tid and "value" in node:
                if tid in tokens and tid not in rows:
                    rows[tid] = {"token_id": tid, "kind": {"C": "claim", "A": "area roll-up", "S": "scope figure",
                                                           "T": "trend/robustness"}[tid[0]],
                                 "value": tokens[tid], "measure": node.get("label") or path,
                                 "source": node.get("source") or source}
                return
            for k, v in node.items():
                # A section's source file holds for everything nested inside it: a nested key that happens to share a
                # section name (e.g. period_comparison -> "areas") must not re-map to that section's file.
                walk(v, f"{path}.{k}" if path else k, source or TOKEN_SOURCES.get(k, ""))
        elif isinstance(node, list):
            for i, v in enumerate(node):
                key = next((label for k in ("issue_id", "area", "month") if isinstance(v, dict)
                            for label in [v.get(k).get("value") if isinstance(v.get(k), dict) else v.get(k)]
                            if isinstance(label, str)), str(i))
                walk(v, f"{path}[{key}]", source)

    walk({k: v for k, v in payload.items() if k != "evidence"}, "", "")
    order = {"C": 0, "A": 1, "S": 2, "T": 3}
    return sorted(rows.values(), key=lambda r: (order[r["token_id"][0]], int(r["token_id"][1:])))


def golden_status(label_config, path=None):
    """Golden-set agreement from evals/golden/results.json, only when it scored this run's label_config."""
    path = Path(path) if path else GOLDEN_RESULTS
    try:
        res = read_json(path)
    except (OSError, ValueError):
        return None
    if res.get("status") != "ready" or not res.get("cases") or res.get("label_config") != label_config:
        return None
    try:
        source = str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        source = str(path)
    return {"cases": res["cases"], "agreement": res.get("agreement") or {}, "source": source}


def mandatory_limitations(lines, golden):
    """Code-written limitations: drop any 'golden comparison pending' clause; state the golden result when it exists."""
    out = [_GOLDEN_CLAUSE.sub(".", x) for x in lines]
    if golden:
        a = golden["agreement"]
        pct = lambda k: "n/a" if a.get(k) is None else f"{round(float(a[k]) * 100, 1):g}%"
        out.append(f"Golden set ({golden['source']}): on {golden['cases']} human-labelled reviews the pipeline's labels "
                   f"match the human labels on topic {pct('topic')}, intent {pct('intent')} and severity {pct('severity')} "
                   f"(exact); {golden['cases']} cases are a diagnostic of label quality, not a precise accuracy estimate.")
    return out


def _and(items):
    items = list(items)
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1] if items else ""


def code_limitations(payload):
    """Decision-specific limitations written by code from saved figures (token templates, filled with their IDs).

    Unallocated complaints (from area_rollup.json) and the premium-only boundary sensitivity
    (analysis/premium_only_sensitivity.json). The model is told not to repeat them as limitations.
    """
    out = []
    u = payload.get("unallocated_complaints")
    if u:
        out.append(f"Unallocated complaints (computed by code from `area_rollup.json`): "
                   f"{u['share_of_complaints_percent']['token']} of complaint and cancellation records "
                   f"({u['complaint_count']['token']}) are {u['area']}: generic criticism (for example \"worst update\") "
                   "that names no specific area, so they are not allocated to any of the four decision areas. If many of "
                   "them refer to one area's problem, for example the same free-tier change, that area's total is "
                   "understated; the labels cannot show which area that would be.")
    s = (payload.get("trends_and_robustness") or {}).get("premium_only_sensitivity")
    if s:
        others = {x["area"]: x["severity_sum"]["token"] for x in s["other_decision_area_severity_sums"]}
        above = s["decision_areas_above_billing_support_without_them"]
        where = (f"below {_and(f'{a} {others[a]}' for a in above if a in others)}" if above
                 else f"still above every other decision area ({_and(f'{a} {t}' for a, t in others.items())})")
        out.append(f"Premium-only boundary, upper-bound sensitivity (computed by code; "
                   f"`analysis/premium_only_sensitivity.json`): {s['records_without_payment_word']['token']} of the "
                   f"{s['issue_complaint_records']['token']} `{s['issue_id']}` complaint and cancellation records contain "
                   f"no Premium or payment word ({', '.join(s['payment_words_case_insensitive'])}; case-insensitive), "
                   f"with a severity sum of {s['their_severity_sum']['token']}. If none of them belonged to billing/support, "
                   f"its severity sum would fall from {s['billing_support_severity_sum']['token']} to "
                   f"{s['billing_support_severity_sum_without_them']['token']}, {where}. This is an upper bound, not a "
                   "relabelling: many of these reviews plainly describe free-tier limits without naming Premium (skip "
                   "limits, forced shuffle), and they were not moved to any other area.")
    return out


def template_memo(payload):
    """Deterministic fallback written by code when the model output fails validation."""
    areas = [a for a in payload["areas"] if a["decision_option"]]
    best = areas[0] if areas else None
    top = [r for r in payload["top_issues"] if best and r["area"] == best["area"]][:3]
    others = [a for a in areas[1:]]
    return {
        "recommended_area": best["area"] if best else labels.DECISION_AREAS[0],
        "recommendation": (f"Focus on {best['area']}: it has the highest combined baseline priority "
                           f"({best['severity_sum']['token']} severity points across {best['complaint_count']['token']} "
                           f"complaint and cancellation reviews)." if best else "No complaints in scope."),
        "rationale": [f"{r['name']} ({r['issue_id']}): priority {r['priority_score']['token']} from "
                      f"{r['complaint_count']['token']} reviews, mean severity {r['mean_severity']['token']}." for r in top]
                     or ["No issue data."],
        "alternatives": [{"area": a["area"], "why_not_first": f"Lower combined priority ({a['severity_sum']['token']})."}
                         for a in others],
        "next_quarter_actions": [f"Investigate and reduce {r['name']} ({r['issue_id']}), the area's issue with priority "
                                 f"{r['priority_score']['token']}." for r in top[:2]],
        "what_would_change_the_call": ["A different top decision area under the independent verifier's labels or in "
                                       "a later period of reviews."],
        "limitations": ["Template memo generated by code because the model memo failed validation."],
        "cited_reviews": [],
    }


class MemoStage:
    def __init__(self, store, cfg, registry, ctx, log=print):
        self.store, self.cfg, self.registry, self.ctx, self.log = store, cfg, registry, ctx, log
        self.m = cfg["memo"]
        self.mconf = cfg.stage_config("memo")

    def run(self, ranking, issues_doc, areas_doc, scope, meta, analysis=None):
        store, ctx = self.store, self.ctx
        golden = golden_status(self.cfg.label_config())
        if golden:  # human-label agreement for this label_config, as scope figures with their source file
            scope = list(scope) + [("Golden set: human-labelled reviews scored", golden["cases"], golden["source"])] + [
                (f"Golden {k} agreement (rate)", golden["agreement"][k], golden["source"])
                for k in ("topic", "intent", "severity") if k in golden["agreement"]]
        meta = dict(meta, mandatory_limitations=mandatory_limitations(meta.get("mandatory_limitations") or [], golden))
        payload, tokens, claims = build_payload(ranking, issues_doc, areas_doc, scope, int(self.m["evidence_issues"]),
                                                int(self.m["quotes_per_issue"]), int(self.m["top_n"]), analysis)
        evidence_ids = [e["review_id"] for e in payload["evidence"]]
        key = short_hash({"payload": payload, "config": self.mconf}, 20)
        cached = store.cache_get("memo", key)
        source, problems_log = "cache", []
        if cached is not None:  # say which invocation's model call produced the reused output
            row = store.conn.execute("SELECT run_id FROM stage_cache WHERE stage = 'memo' AND cache_key = ?",
                                     (key,)).fetchone()
            source = f"model, reused from the stage cache (generated in `{row[0]}`)" if row and row[0] else "cache"
        data = cached
        if data is None and ranking:
            data, source, problems_log = self._call(payload, tokens, evidence_ids)
            if data is not None and source == "model":
                store.cache_put("memo", key, data, None, ctx.run_id)
        if data is None and ranking and ctx.stop_reason:  # stopped mid-stage: a resumed run writes the memo
            self.log(f"[memo] not written: run stopping ({ctx.stop_reason}); a resumed run generates it")
            return {"source": f"not written (run stopping: {ctx.stop_reason})", "claims": 0}
        if data is None:
            data, source = template_memo(payload), ("template (no complaints in scope)" if not ranking
                                                    else "template (model memo failed validation)")
        memo_md = self.render(data, payload, tokens, meta, source)
        atomic_write_text(store.run_dir / "memo.md", memo_md)
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\n")
        w.writerow(["claim_id", "issue_id", "metric", "value"])
        for c in claims:
            w.writerow([c["claim_id"], c["issue_id"], c["metric"], c["value"]])
        atomic_write_text(store.run_dir / "claims.csv", buf.getvalue())
        index = token_index(payload, tokens)
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=("token_id", "kind", "value", "measure", "source"), lineterminator="\n")
        w.writeheader()
        w.writerows(index)
        atomic_write_text(store.run_dir / "memo_tokens.csv", buf.getvalue())
        atomic_write_json(store.run_dir / "memo.json", {"memo_config": self.mconf, "source": source, "output": data,
                                                        # limitations memo.md adds after the model's, as rendered there
                                                        "code_written_limitations": [fill_cited(x, tokens) for x in
                                                                                     code_limitations(payload)],
                                                        "mandatory_limitations": meta["mandatory_limitations"],
                                                        "tokens": tokens, "token_index": index, "payload": payload,
                                                        "validation_problems": problems_log,
                                                        "rejected_outputs": getattr(self, "rejected", []),
                                                        "generated_at": utc_now()})
        self.log(f"[memo] memo.md written (source: {source}); {len(claims)} issue-level claims in claims.csv; "
                 f"{len(index)} tokens in memo_tokens.csv")
        return {"source": source, "claims": len(claims)}

    def _call(self, payload, tokens, evidence_ids):
        ctx = self.ctx
        r = self.cfg.role_settings("memo")
        provider = self.registry.get(r["provider"], r["model"], r["effort"])
        problems_log = []
        self.rejected = []  # outputs that failed validation, saved in memo.json for audit
        for attempt in (1, 2):
            if ctx.stop_admitting.is_set():
                break
            req = memo_request(payload, evidence_ids, int(self.m["max_output_tokens"]), template=self.m["prompt"])
            if self.rejected:  # the single retry is told what the validator rejected
                req["user"] += ("\n\nYour previous answer was rejected by the code validator for these reasons; return a "
                                "corrected answer that follows every rule:\n- " + "\n- ".join(self.rejected[-1]["problems"]))
            chars = len(req["system"]) + len(req["user"]) + len(json.dumps(req["schema"]))
            task = Task(role="memo", tier="memo", provider=provider, request=req, review_ids=[],
                        max_output_tokens=int(self.m["max_output_tokens"]), prompt_chars=chars,
                        stage_config=self.mconf, task_attempt=attempt)
            disp = Dispatcher(ctx, 1, 1)
            try:
                disp.submit(task)
                (_, outcome), = disp.wait_some(timeout=None)
            finally:
                disp.shutdown()
            if outcome.status != "ok":
                problems_log.append(f"attempt {attempt}: {outcome.status} {outcome.error}")
                if outcome.status == "budget":
                    ctx.request_stop("budget_cap")
                elif outcome.status == "systemic":  # e.g. a Claude Pro plan limit: stop and resume, never a template
                    ctx.request_stop(f"systemic_provider_error: {outcome.error}")
                if outcome.status not in ("invalid_output",):
                    break
                continue
            problems = validate(outcome.result.data, tokens, evidence_ids, payload) if outcome.result.data is not None \
                else [f"unusable output: {outcome.result.finish}"]
            if not problems:
                return outcome.result.data, "model", problems_log
            problems_log.append(f"attempt {attempt}: " + "; ".join(problems))
            self.rejected.append({"attempt": attempt, "request_id": outcome.request_id, "problems": problems,
                                  "output": outcome.result.data})
            self.store.call_settled(outcome.request_id, {"outcome": "failed", "valid_output": 0,
                                                         "error": "invalid_output: " + "; ".join(problems)[:400]})
        return None, "none", problems_log

    def render(self, data, payload, tokens, meta, source):
        # Every filled number carries its token ID: C## in claims.csv, every token in memo_tokens.csv.
        f = lambda s: fill_cited(s["token"] if isinstance(s, dict) else s, tokens)
        lines = ["# Decision memo: where to focus next quarter", ""]
        if meta.get("offline_stub"):
            lines += ["> **OFFLINE STUB RUN - NOT FINDINGS.** Every label and name below came from a local test server "
                      "that answers by hashing the request. It shows that the pipeline runs end to end; it says nothing "
                      "about Spotify reviews.", ""]
        lines += [f"Scope: {meta['scope']}  ", f"Run: `{meta['run_id']}` | input `{meta['input']}` "
                  f"(sha256 `{meta['input_sha256'][:16]}...`) | memo source: {source}", "",
                  "Numbers are written as value (token ID): C## IDs are the issue-level claims in `claims.csv`; every "
                  "ID (C##, A## area roll-up, S## scope figure, T## trend/robustness) is listed with its value, what it "
                  "measures and its source file in `memo_tokens.csv`.", ""]
        lines += ["## Recommendation", "", f"**{data['recommended_area']}.** {f(data['recommendation'])}", ""]
        options = [a for a in payload["areas"] if a["decision_option"]]
        if options and options[0]["area"] != data["recommended_area"]:
            lines += [f"> **Check:** the baseline's highest-priority decision area is **{options[0]['area']}** "
                      f"(severity sum {f(options[0]['severity_sum'])}), not the recommended area. A reviewer must "
                      "confirm the memo justifies the difference.", ""]
        if data.get("next_quarter_actions"):
            lines += ["## Next-quarter actions", ""]
            lines += [f"{i}. {f(x)}" for i, x in enumerate(data["next_quarter_actions"], 1)] + [""]
        lines += ["## Why", ""] + [f"- {f(x)}" for x in data["rationale"]] + [""]
        if data.get("what_would_change_the_call"):
            lines += ["## What would change this call", ""] + [f"- {f(x)}" for x in data["what_would_change_the_call"]] + [""]
        lines += ["## Alternatives considered", ""]
        lines += [f"- **{a['area']}**: {f(a['why_not_first'])}" for a in data["alternatives"]] + [""]
        lines += ["## Supporting numbers (baseline ranking, computed by code)", "",
                  "Priority = severity_sum = complaint_count x mean_severity over complaint and cancellation reviews. "
                  "Each cell shows the value and its claim ID in `claims.csv`.", "",
                  "| Rank | Issue | Area | Complaints | Severity sum | Mean severity | Priority |",
                  "|---:|---|---|---:|---:|---:|---:|"]
        for i, r in enumerate(payload["top_issues"], 1):
            lines.append(f"| {i} | {r['name']} (`{r['issue_id']}`) | {r['area']} | {f(r['complaint_count'])} | "
                         f"{f(r['severity_sum'])} | {f(r['mean_severity'])} | {f(r['priority_score'])} |")
        lines += ["", "## Area roll-up (derived from the issue table; not a contract metric)", "",
                  "| Area | Complaints | Severity sum | Share of complaints |", "|---|---:|---:|---:|"]
        for a in payload["areas"]:
            lines.append(f"| {a['area']}{'' if a['decision_option'] else ' (not one of the four options)'} | "
                         f"{f(a['complaint_count'])} | {f(a['severity_sum'])} | {f(a['share_of_complaints'])} |")
        tr = payload.get("trends_and_robustness") or {}
        if tr:
            lines += ["", "## Trends and robustness (descriptive, computed by code)", ""]
            pc = tr.get("period_comparison")
            if pc:
                d = pc["denominators"]
                lines += ["Same calendar months one year apart (full months only). Share = the area's complaint and "
                          "cancellation reviews / all classified reviews in the period.", "",
                          f"| Area | {f(pc['earlier_period'])} | {f(pc['later_period'])} | Change |", "|---|---:|---:|---:|"]
                for r in pc["areas"]:
                    lines.append(f"| {r['area']} | {f(r['share_of_reviews_earlier_period'])} | "
                                 f"{f(r['share_of_reviews_later_period'])} | {f(r['change_pp'])} |")
                lines.append("| Denominator (classified reviews) | " + " | ".join(
                    f(d[k]["reviews"]) for k in ("earlier_period", "later_period")) + " | |")
                lines.append("")
                nd = pc.get("non_decision_areas") or []
                lines.append("Note (code): this table, and any comparison of growth in this memo, covers the four decision "
                             "areas only. Areas that are not decision options are listed in "
                             "`analysis/period_comparison.json`"
                             + (": " + "; ".join(f"{r['area']} {f(r['share_of_reviews_earlier_period'])} to "
                                                 f"{f(r['share_of_reviews_later_period'])}, {f(r['change_pp'])}" for r in nd)
                                if nd else "") + ".")
                lines.append("")
            if tr.get("area_shares_with_sampling_intervals"):
                lines += ["| Decision area | Share of complaints | 95% interval (sampling only) |", "|---|---:|---:|"]
                for a in tr["area_shares_with_sampling_intervals"]:
                    lines.append(f"| {a['area']} | {f(a['share_of_complaints'])} | {f(a['ci_low'])} to {f(a['ci_high'])} |")
                lines.append("")
            if tr.get("spike_months"):
                lines.append("Volume spikes (code): each line lists at most three issues, from any area (the catch-all "
                             "`other.general` included), whose share of reviews (the issue's complaint and cancellation "
                             "reviews / all reviews in the month) rose versus the other full months; zero and negative "
                             "changes are left out.")
                lines.append("")
            for x in tr.get("spike_months", []):
                inc = ", ".join(f"`{l['issue_id']}` {f(l['pp_difference'])}" for l in x["largest_increases"])
                lines.append(f"- Volume spike {f(x['month'])}: {f(x['reviews'])} reviews (median full month "
                             f"{f(x['median_full_month_reviews'])}); "
                             + (f"largest increases in share of reviews vs other months: {inc}." if inc else
                                "no issue's share of reviews rose versus other months (the extra volume kept the "
                                "usual issue mix)."))
            rb = tr.get("verifier_robustness")
            if rb:
                sums = lambda who: ", ".join(f"{x['area']} {f(x['severity_sum'])}"
                                             for x in rb.get(f"sample_severity_sum_by_area_{who}_labels") or [])
                order = lambda who: (sums(who) or ", ".join(rb.get(f"decision_area_order_{who}_labels") or []))
                lines.append(f"- Verifier robustness on {f(rb['sample_reviews'])} sampled reviews ({rb.get('metric')}): decision "
                             f"areas in order under enricher labels **{order('enricher')}**; under independent verifier "
                             f"labels **{order('verifier')}** (top area {'same' if rb['same_top_area'] else 'different'}).")
        lines += ["", "## Representative evidence (exact quotes from the reviews)", "",
                  "\"(cited)\" marks a review the memo cites in support of the recommendation.", ""]
        cited = set(data.get("cited_reviews") or [])
        for e in payload["evidence"]:
            mark = " (cited)" if e["review_id"] in cited else ""
            lines.append(f"- `{e['issue_id']}` - \"{e['quote']}\" - review `{e['review_id']}`{mark}")
        lines += ["", "## Scope figures", "", "| Figure | Value | Token | Source |", "|---|---:|---|---|"]
        for sid, s in payload["scope_figures"].items():
            lines.append(f"| {s['label']} | {s['value']} | {sid} | {s['source']} |")
        lines += ["", "## Limitations", ""] + [f"- {f(x)}" for x in data["limitations"]]
        lines += [f"- {f(x)}" for x in code_limitations(payload)]
        lines += [f"- {x}" for x in meta["mandatory_limitations"]]
        lines += ["", "## Traceability", "",
                  "- `claims.csv`: every issue-level number above (claim_id, issue_id, metric, value); the C## IDs in the "
                  "prose and the ranking table.",
                  "- `memo_tokens.csv` (also `memo.json` -> `token_index`): every token ID used above (C##, A##, S##, T##) "
                  "with its value, what it measures and the saved file it comes from (`area_rollup.json`, the scope "
                  "sources, `analysis/*.json`).",
                  "- `ranking.csv` / `membership.csv`: rerun with `python -m insight rank --run-dir <run> --check` "
                  "(no model calls).",
                  "- `issues.json`: issue names and the evidence each name was based on.", ""]
        return "\n".join(lines)

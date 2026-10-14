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
from .control import Dispatcher, Task
from .util import PROJECT_ROOT, atomic_write_json, atomic_write_text, read_json, short_hash, utc_now

TOKEN = re.compile(r"\{([CAST]\d{2,3})\}")
METRICS = ("complaint_count", "severity_sum", "mean_severity", "priority_score")
# Fields the memo model returns in addition to the base schema in prompts.memo_request (prose, token rules apply).
EXTRA_PROSE_FIELDS = {
    "next_quarter_actions": "two to four concrete next-quarter actions, each tied to a named top issue",
    "what_would_change_the_call": "one to three pieces of evidence that would change the recommendation",
}
GOLDEN_RESULTS = PROJECT_ROOT / "evals" / "golden" / "results.json"
_GOLDEN_CLAUSE = re.compile(r";\s*the golden-set comparison \(human labels\) is (?:still pending|reported separately)\.?")
TOKEN_SOURCES = {  # payload section -> saved file that holds the value behind its tokens
    "top_issues": "claims.csv (from ranking.csv)", "areas": "area_rollup.json",
    "period_comparison": "analysis/period_comparison.json", "area_shares_with_sampling_intervals": "analysis/area_intervals.json",
    "spike_months": "analysis/spike_months.json", "verifier_robustness": "analysis/robustness.json",
}


def _pct(x):
    return "n/a" if x is None else f"{float(x) * 100:.1f}%"


def _shown_pp(x):
    """The pp change as the memo prints it (one decimal), so '+0.0 pp' never counts as an increase."""
    return round(float(x), 1)


def _trend_section(analysis, tokens):
    """Descriptive trend/robustness facts for the memo, each number behind a T## token."""
    if not analysis:
        return {}
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
        out["area_shares_with_sampling_intervals"] = [
            {"area": a["area"], "share_of_complaints": tok(_pct(a["share_of_complaints"])),
             "ci_low": tok(_pct(a["share_of_complaints_ci95"][0])), "ci_high": tok(_pct(a["share_of_complaints_ci95"][1]))}
            for a in ai["areas"] if a["decision_option"]]
    sp = analysis.get("spikes") or {}
    if sp.get("spikes"):
        # only issues whose share actually rose in the spike month (as printed, one decimal) count as increases
        out["spike_months"] = [{"month": tok(x["month"]), "reviews": tok(x["reviews"]),
                                "median_full_month_reviews": tok(x["median_full_month_reviews"]),
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
                                      "top_by_complaint_count": rb.get("by_complaint_count")}
        for who in ("enricher", "verifier"):  # the sample's per-area severity sums behind each ordering
            areas = (rb.get(f"{who}_labels") or {}).get("areas") or {}
            order = rb.get(f"decision_area_order_{who}") or []
            if areas and order:
                out["verifier_robustness"][f"sample_severity_sum_by_area_{who}_labels"] = [
                    {"area": a, "severity_sum": tok(areas[a]["severity_sum"])} for a in order if a in areas]
    return out


def positive_increases(lifts):
    """Spike-month lifts that are real increases in share (> 0 pp after rounding to one decimal), largest first."""
    return [l for l in lifts if _shown_pp(l["pp_difference"]) > 0]


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
    trends = _trend_section(analysis, tokens)
    if trends:
        payload["trends_and_robustness"] = trends
    return payload, tokens, claims


def validate(data, tokens, evidence_ids):
    problems = []
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


def fill(text, tokens):
    return TOKEN.sub(lambda m: tokens[m.group(1)], text)


def fill_cited(text, tokens):
    """Fill tokens as 'value (ID)', e.g. '52577 (C02)', so every number in the memo traces to a saved token."""
    return TOKEN.sub(lambda m: f"{tokens[m.group(1)]} ({m.group(1)})", text)


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
                walk(v, f"{path}.{k}" if path else k, TOKEN_SOURCES.get(k, source))
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
        data = cached
        if data is None and ranking:
            data, source, problems_log = self._call(payload, tokens, evidence_ids)
            if data is not None and source == "model":
                store.cache_put("memo", key, data, None, ctx.run_id)
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
                if outcome.status not in ("invalid_output",):
                    break
                continue
            problems = validate(outcome.result.data, tokens, evidence_ids) if outcome.result.data is not None \
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
            if tr.get("area_shares_with_sampling_intervals"):
                lines += ["| Decision area | Share of complaints | 95% interval (sampling only) |", "|---|---:|---:|"]
                for a in tr["area_shares_with_sampling_intervals"]:
                    lines.append(f"| {a['area']} | {f(a['share_of_complaints'])} | {f(a['ci_low'])} to {f(a['ci_high'])} |")
                lines.append("")
            for x in tr.get("spike_months", []):
                inc = ", ".join(f"`{l['issue_id']}` {f(l['pp_difference'])}" for l in x["largest_increases"])
                lines.append(f"- Volume spike {f(x['month'])}: {f(x['reviews'])} reviews (median full month "
                             f"{f(x['median_full_month_reviews'])}); "
                             + (f"largest increases in share of complaints vs other months: {inc}." if inc else
                                "no issue's share of complaints rose versus other months (the extra volume kept the "
                                "usual issue mix)."))
            rb = tr.get("verifier_robustness")
            if rb:
                sums = lambda who: ", ".join(f"{x['area']} {f(x['severity_sum'])}"
                                             for x in rb.get(f"sample_severity_sum_by_area_{who}_labels") or [])
                order = lambda who: (sums(who) or ", ".join(rb.get(f"decision_area_order_{who}_labels") or []))
                lines.append(f"- Verifier robustness on {f(rb['sample_reviews'])} sampled reviews ({rb.get('metric')}): decision "
                             f"areas in order under enricher labels **{order('enricher')}**; under independent verifier "
                             f"labels **{order('verifier')}** (top area {'same' if rb['same_top_area'] else 'different'}).")
        lines += ["", "## Representative evidence (exact quotes from the reviews)", ""]
        cited = set(data.get("cited_reviews") or [])
        for e in payload["evidence"]:
            mark = " (cited)" if e["review_id"] in cited else ""
            lines.append(f"- `{e['issue_id']}` - \"{e['quote']}\" - review `{e['review_id']}`{mark}")
        lines += ["", "## Scope figures", "", "| Figure | Value | Token | Source |", "|---|---:|---|---|"]
        for sid, s in payload["scope_figures"].items():
            lines.append(f"| {s['label']} | {s['value']} | {sid} | {s['source']} |")
        lines += ["", "## Limitations", ""] + [f"- {f(x)}" for x in data["limitations"]]
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

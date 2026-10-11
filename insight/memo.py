"""Stage 6 - recommend (model + code).

The memo model sees only saved aggregates (top-ranked issues, area roll-up, scope figures)
and a bounded evidence pack of exact quotes. It must not write digits: every number is a
token ({C01}, {A02}, {S03}) that code replaces with the saved value. Code validates the
output (tokens exist, no stray digits, cited review IDs are in the pack, valid areas);
one retry, then a deterministic template memo clearly marked as such.
claims.csv lists every issue-level number that appears in the memo.
"""

import csv
import io
import json
import re

from . import labels, prompts
from .control import Dispatcher, Task
from .util import atomic_write_json, atomic_write_text, short_hash, utc_now

TOKEN = re.compile(r"\{([CAST]\d{2,3})\}")
METRICS = ("complaint_count", "severity_sum", "mean_severity", "priority_score")


def _pct(x):
    return "n/a" if x is None else f"{float(x) * 100:.1f}%"


def _trend_section(analysis, tokens):
    """Descriptive trend/robustness facts for the memo, each number behind a T## token."""
    if not analysis:
        return {}
    def tok(value):
        tid = f"T{len([t for t in tokens if t.startswith('T')]) + 1:02d}"
        tokens[tid] = str(value)
        return "{" + tid + "}"
    out = {}
    pc = analysis.get("period_comparison") or {}
    periods = pc.get("periods", {})
    if periods:
        rows = []
        for area, ch in sorted(pc.get("change_in_share_of_reviews", {}).items()):
            if area not in labels.DECISION_AREAS:
                continue
            rows.append({"area": area, "share_of_reviews_2022_jun_oct": tok(_pct(ch["2022"])),
                         "share_of_reviews_2023_jun_oct": tok(_pct(ch["2023"])),
                         "change_pp": tok(f"{ch['pp_change']:+.1f} pp")})
        out["period_comparison"] = {"method": pc.get("method"), "denominators": {
            k: {"reviews": tok(v["reviews"]), "complaint_share": tok(_pct(v["complaint_share"]))} for k, v in periods.items()},
            "areas": rows}
    ai = analysis.get("area_intervals") or {}
    if ai.get("areas"):
        out["area_shares_with_95pct_intervals"] = [
            {"area": a["area"], "share_of_complaints": tok(_pct(a["share_of_complaints"])),
             "ci_low": tok(_pct(a["share_of_complaints_ci95"][0])), "ci_high": tok(_pct(a["share_of_complaints_ci95"][1]))}
            for a in ai["areas"] if a["decision_option"]]
    sp = analysis.get("spikes") or {}
    if sp.get("spikes"):
        out["spike_months"] = [{"month": x["month"], "reviews": tok(x["reviews"]),
                                "median_full_month_reviews": tok(x["median_full_month_reviews"]),
                                "largest_increases": [{"issue_id": l["issue_id"], "pp_difference": tok(f"{l['pp_difference']:+.1f} pp")}
                                                      for l in x["largest_increases"][:3]]} for x in sp["spikes"]]
    rb = analysis.get("robustness") or {}
    if rb.get("sample"):
        out["verifier_robustness"] = {"sample_reviews": tok(rb["sample"]),
                                      "top_decision_area_enricher_labels": rb.get("top_decision_area_enricher"),
                                      "top_decision_area_verifier_labels": rb.get("top_decision_area_verifier"),
                                      "same_top_area": rb.get("same_top_decision_area")}
    return out


def build_payload(ranking, issues_doc, areas_doc, scope, evidence_issues, quotes_per_issue, top_n, analysis=None):
    names = {i["issue_id"]: i for i in issues_doc["issues"]}
    tokens, claims = {}, []
    rank_rows = []
    for r in ranking[:top_n]:
        row = {"issue_id": r["issue_id"], "name": names.get(r["issue_id"], {}).get("name", r["issue_id"]),
               "area": labels.AREA_OF_TOPIC[r["issue_id"].split(".")[0]]}
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
    for where, text in prose:
        if not isinstance(text, str) or not text.strip():
            problems.append(f"{where} is empty")
            continue
        for t in TOKEN.findall(text):
            if t not in tokens:
                problems.append(f"{where} cites unknown token {{{t}}}")
        if re.search(r"\d", TOKEN.sub("", text)):
            problems.append(f"{where} contains a typed digit (numbers must be tokens)")
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


def fill(text, tokens):
    return TOKEN.sub(lambda m: tokens[m.group(1)], text)


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
        atomic_write_json(store.run_dir / "memo.json", {"memo_config": self.mconf, "source": source, "output": data,
                                                        "tokens": tokens, "payload": payload,
                                                        "validation_problems": problems_log, "generated_at": utc_now()})
        self.log(f"[memo] memo.md written (source: {source}); {len(claims)} issue-level claims in claims.csv")
        return {"source": source, "claims": len(claims)}

    def _call(self, payload, tokens, evidence_ids):
        ctx = self.ctx
        r = self.cfg.role_settings("memo")
        provider = self.registry.get(r["provider"], r["model"], r["effort"])
        problems_log = []
        for attempt in (1, 2):
            if ctx.stop_admitting.is_set():
                break
            req = prompts.memo_request(payload, evidence_ids, int(self.m["max_output_tokens"]), template=self.m["prompt"])
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
            self.store.call_settled(outcome.request_id, {"outcome": "failed", "valid_output": 0,
                                                         "error": "invalid_output: " + "; ".join(problems)[:400]})
        return None, "none", problems_log

    def render(self, data, payload, tokens, meta, source):
        f = lambda s: fill(s, tokens)
        lines = ["# Decision memo: where to focus next quarter", ""]
        if meta.get("offline_stub"):
            lines += ["> **OFFLINE STUB RUN - NOT FINDINGS.** Every label and name below came from a local test server "
                      "that answers by hashing the request. It shows that the pipeline runs end to end; it says nothing "
                      "about Spotify reviews.", ""]
        lines += [f"Scope: {meta['scope']}  ", f"Run: `{meta['run_id']}` | input `{meta['input']}` "
                  f"(sha256 `{meta['input_sha256'][:16]}...`) | memo source: {source}", ""]
        lines += ["## Recommendation", "", f"**{data['recommended_area']}.** {f(data['recommendation'])}", ""]
        options = [a for a in payload["areas"] if a["decision_option"]]
        if options and options[0]["area"] != data["recommended_area"]:
            lines += [f"> **Check:** the baseline's highest-priority decision area is **{options[0]['area']}** "
                      f"(severity sum {options[0]['severity_sum']['value']}), not the recommended area. A reviewer must "
                      "confirm the memo justifies the difference.", ""]
        lines += ["## Why", ""] + [f"- {f(x)}" for x in data["rationale"]] + [""]
        lines += ["## Alternatives considered", ""]
        lines += [f"- **{a['area']}**: {f(a['why_not_first'])}" for a in data["alternatives"]] + [""]
        lines += ["## Supporting numbers (baseline ranking, computed by code)", "",
                  "Priority = severity_sum = complaint_count x mean_severity over complaint and cancellation reviews. "
                  "Each cell shows the value and its claim ID in `claims.csv`.", "",
                  "| Rank | Issue | Area | Complaints | Severity sum | Mean severity | Priority |",
                  "|---:|---|---|---:|---:|---:|---:|"]
        for i, r in enumerate(payload["top_issues"], 1):
            cell = lambda m: f"{r[m]['value']} ({r[m]['token'].strip('{}')})"
            lines.append(f"| {i} | {r['name']} (`{r['issue_id']}`) | {r['area']} | {cell('complaint_count')} | "
                         f"{cell('severity_sum')} | {cell('mean_severity')} | {cell('priority_score')} |")
        lines += ["", "## Area roll-up (derived from the issue table; not a contract metric)", "",
                  "| Area | Complaints | Severity sum | Share of complaints |", "|---|---:|---:|---:|"]
        for a in payload["areas"]:
            lines.append(f"| {a['area']}{'' if a['decision_option'] else ' (not one of the four options)'} | "
                         f"{a['complaint_count']['value']} | {a['severity_sum']['value']} | {a['share_of_complaints']['value']} |")
        tr = payload.get("trends_and_robustness") or {}
        if tr:
            lines += ["", "## Trends and robustness (descriptive, computed by code)", ""]
            pc = tr.get("period_comparison")
            if pc:
                d = pc["denominators"]
                lines += ["Same calendar months one year apart (full months only). Share = the area's complaint and "
                          "cancellation reviews / all classified reviews in the period.", "",
                          "| Area | Jun-Oct 2022 | Jun-Oct 2023 | Change |", "|---|---:|---:|---:|"]
                for r in pc["areas"]:
                    lines.append(f"| {r['area']} | {f(r['share_of_reviews_2022_jun_oct'])} | {f(r['share_of_reviews_2023_jun_oct'])} | "
                                 f"{f(r['change_pp'])} |")
                lines.append("| Denominator (classified reviews) | " + " | ".join(f(v["reviews"]) for v in d.values()) + " | |")
                lines.append("")
            if tr.get("area_shares_with_95pct_intervals"):
                lines += ["| Decision area | Share of complaints | 95% interval (sampling only) |", "|---|---:|---:|"]
                for a in tr["area_shares_with_95pct_intervals"]:
                    lines.append(f"| {a['area']} | {f(a['share_of_complaints'])} | {f(a['ci_low'])} to {f(a['ci_high'])} |")
                lines.append("")
            for x in tr.get("spike_months", []):
                inc = ", ".join(f"`{l['issue_id']}` {f(l['pp_difference'])}" for l in x["largest_increases"])
                lines.append(f"- Volume spike {x['month']}: {f(x['reviews'])} reviews (median full month "
                             f"{f(x['median_full_month_reviews'])}); largest increases in share: {inc}.")
            rb = tr.get("verifier_robustness")
            if rb:
                lines.append(f"- Verifier robustness on {f(rb['sample_reviews'])} sampled reviews: top decision area under "
                             f"enricher labels **{rb['top_decision_area_enricher_labels']}**, under independent verifier labels "
                             f"**{rb['top_decision_area_verifier_labels']}** ({'same' if rb['same_top_area'] else 'different'}).")
        lines += ["", "## Representative evidence (exact quotes from the reviews)", ""]
        cited = set(data.get("cited_reviews") or [])
        for e in payload["evidence"]:
            mark = " (cited)" if e["review_id"] in cited else ""
            lines.append(f"- `{e['issue_id']}` - \"{e['quote']}\" - review `{e['review_id']}`{mark}")
        lines += ["", "## Scope figures", "", "| Figure | Value | Source |", "|---|---:|---|"]
        for sid, s in payload["scope_figures"].items():
            lines.append(f"| {s['label']} | {s['value']} | {s['source']} |")
        lines += ["", "## Limitations", ""] + [f"- {f(x)}" for x in data["limitations"]]
        lines += [f"- {x}" for x in meta["mandatory_limitations"]]
        lines += ["", "## Traceability", "",
                  "- `claims.csv`: every issue-level number above (claim_id, issue_id, metric, value).",
                  "- `ranking.csv` / `membership.csv`: rerun with `python -m insight rank --run-dir <run> --check` "
                  "(no model calls).",
                  "- `issues.json`: issue names and the evidence each name was based on.", ""]
        return "\n".join(lines)

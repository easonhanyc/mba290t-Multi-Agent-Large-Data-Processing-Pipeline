#!/usr/bin/env python3
"""100-review cost and runtime calculator. Offline replay is the default.

  python3 cost/calculator.py                     offline replay: recompute everything from saved files
                                                 (rates.csv, usage.csv, pilot_runs.json, pilot_calls.jsonl,
                                                 refreshes/*.json, assumptions.json); rewrite report.md/.json
  python3 cost/calculator.py replay --rates R --assumptions A --out-dir D [--budget-usd B]
                                                 same, with edited inputs, written elsewhere
  .venv/bin/python cost/calculator.py pilot --execute --allow-paid --budget-usd 0.10
                                                 REAL billed pilot: cold run then warm run of the configured
                                                 pipeline on cost_100.csv (one worker, empty result cache)
  .venv/bin/python cost/calculator.py pilot --execute --offline-stub
                                                 plumbing demo with the local stub (no calls, no cost);
                                                 written to cost/offline_stub_example/, never to cost/
  python3 cost/calculator.py refresh --run-dir runs/<run> --label checkpoint_500
                                                 save measured per-stage usage of a 500 / 10,000-review run
                                                 (cost/refreshes/) so projections use the larger measurement

Standard library only. Importing or opening this file never makes a network call.

Formulas: item_cost = billed_units x usd_per_million / 1,000,000 for mutually exclusive billing items
(input_uncached = input - cached - cache_write, input_cached, input_cache_write, output incl. reasoning),
priced at the processing tier the provider reported (e.g. Flex). Calls made through the Claude Pro
subscription (`claude -p`) are billed $0 per call; their usage is priced separately at the reported
model's API rates as an "API-equivalent" value, never added to billed spend.
"""

import argparse
import csv
import hashlib
import io
import json
import math
import sqlite3
import subprocess
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

COST_DIR = Path(__file__).resolve().parent
ROOT = COST_DIR.parent
DATA_DIR = ROOT / "Final Assignment - Spotify Reviews Dataset"
FIELDS = ["review_id", "review_text", "review_rating", "review_likes", "app_version", "review_timestamp"]
ITEMS = ("input_uncached", "input_cached", "input_cache_write", "output")
STAGE_OF = {("enrich", "primary"): "enrich_primary", ("enrich", "fallback1"): "fallback1",
            ("enrich", "fallback2"): "fallback2", ("verify", "verify"): "verify", ("group", "group"): "group",
            ("memo", "memo"): "memo"}
STAGE_ORDER = ("enrich_primary", "fallback1", "fallback2", "verify", "group", "memo")
USAGE_FIELDS = ["request_id", "run_label", "run_id", "stage", "role", "provider", "model", "model_reported", "tier",
                "billing", "item", "billed_units", "unit", "usage_reported"]


# ---- rates -------------------------------------------------------------------------------------------
def _tier(t):
    return {"default": "standard", "auto": "standard", None: "standard", "": "standard"}.get(t, t)


def load_rates(path):
    rows, kinds = {}, {}
    with open(path, encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            kind = r.get("kind") or "api"
            if kind not in ("api", "subscription"):
                continue
            rows[(r["provider"], r["model"], _tier(r.get("tier")), r["item"])] = r
            kinds[(r["provider"], r["model"])] = kind
    return {"rows": rows, "kinds": kinds}


def unit_price(R, provider, model, tier, item):
    """USD per billed unit, 0 for stub and subscription calls, None when no dated rate exists."""
    if model.startswith("stub-"):
        return 0.0
    if R["kinds"].get((provider, model)) == "subscription":
        return 0.0
    tier = _tier(tier)
    row = R["rows"].get((provider, model, tier, item))
    if row is None and item == "input_cache_write":
        row = R["rows"].get((provider, model, tier, "input_uncached"))
    return None if row is None else float(row["usd_per_million"]) / 1_000_000


def api_equiv_price(R, model_reported, item, provider="anthropic"):
    """API price of a subscription call's reported model (longest matching dated model ID), or None."""
    if not model_reported or model_reported.startswith("stub-"):
        return 0.0 if model_reported else None
    cands = sorted({m for (pv, m, t, i) in R["rows"] if pv == provider and t == "standard"
                    and R["kinds"].get((pv, m)) == "api" and model_reported.startswith(m)}, key=len)
    if not cands:
        return None
    return unit_price(R, provider, cands[-1], "standard", item)


def is_subscription(R, provider, model):
    return R["kinds"].get((provider, model.removeprefix("stub-"))) == "subscription"


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def load_usage(path):
    if not Path(path).exists():
        return []
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


# ---- measured runs -------------------------------------------------------------------------------------
def _stage_stats(R, usage_rows, calls):
    stages = defaultdict(lambda: {"attempts": 0, "first_attempts": 0, "transient_retries": 0, "invalid_output_retries": 0,
                                  "failed": 0, "succeeded": 0, "usage": Counter(), "billed_usd": 0.0,
                                  "api_equivalent_usd": 0.0, "api_equivalent_unpriced": 0, "latencies": [],
                                  "reviews_sent": 0, "unique_reviews": set(), "tiers": set(), "billing": set(),
                                  "models_reported": set()})
    unpriced = []
    for u in usage_rows:
        st = stages[u["stage"]]
        units = int(u["billed_units"])
        st["usage"][u["item"]] += units
        p = unit_price(R, u["provider"], u["model"], u.get("tier"), u["item"])
        if p is None:
            unpriced.append(f"{u['provider']}/{u['model']}/{u.get('tier')}/{u['item']}")
        else:
            st["billed_usd"] += units * p
        if u.get("billing") == "subscription" and units:
            q = api_equiv_price(R, u.get("model_reported"), u["item"])
            if q is None:
                st["api_equivalent_unpriced"] += units
            else:
                st["api_equivalent_usd"] += units * q
    for c in calls:
        st = stages[STAGE_OF.get((c["role"], c.get("tier") or c["role"]), c["role"])]
        st["attempts"] += 1
        st["first_attempts"] += c["attempt"] == 1 and c["task_attempt"] == 1
        st["transient_retries"] += c["attempt"] > 1
        st["invalid_output_retries"] += c["task_attempt"] > 1
        st["failed"] += c["outcome"] != "succeeded"
        st["succeeded"] += c["outcome"] == "succeeded"
        st["reviews_sent"] += len(c.get("review_ids") or [])
        if c["outcome"] == "succeeded":
            st["unique_reviews"].update(c.get("review_ids") or [])
            if c.get("duration_s"):
                st["latencies"].append(float(c["duration_s"]))
        st["tiers"].add(c.get("service_tier") or "standard")
        st["billing"].add(c.get("billing") or "api")
        if c.get("model_reported"):
            st["models_reported"].add(c["model_reported"])
    out = {}
    for name in STAGE_ORDER:
        if name not in stages:
            continue
        s = stages[name]
        lat = s.pop("latencies")
        n_rev = len(s.pop("unique_reviews"))
        s["usage"] = dict(s["usage"])
        s["unique_reviews"] = n_rev
        s["mean_latency_s"] = round(sum(lat) / len(lat), 4) if lat else None
        s["reviews_per_request"] = round(s["reviews_sent"] / s["attempts"], 3) if s["attempts"] else None
        s["billed_usd"] = round(s["billed_usd"], 10)
        s["api_equivalent_usd"] = round(s["api_equivalent_usd"], 10)
        s["billed_usd_per_review"] = round(s["billed_usd"] / n_rev, 12) if n_rev else None
        s["api_equivalent_usd_per_review"] = round(s["api_equivalent_usd"] / n_rev, 12) if n_rev else None
        s["billed_usd_per_call"] = round(s["billed_usd"] / s["attempts"], 10) if s["attempts"] else None
        s["api_equivalent_usd_per_call"] = round(s["api_equivalent_usd"] / s["attempts"], 10) if s["attempts"] else None
        for k in ("tiers", "billing", "models_reported"):
            s[k] = sorted(s[k])
        tok = s["usage"]
        s["mean_input_tokens"] = round(sum(tok.get(i, 0) for i in ITEMS[:3]) / s["succeeded"], 1) if s["succeeded"] else None
        s["mean_output_tokens"] = round(tok.get("output", 0) / s["succeeded"], 1) if s["succeeded"] else None
        out[name] = s
    return out, unpriced


def measured(R, usage, pilot):
    """Recompute the measured pilot from usage rows x rates. Returns None when no pilot exists."""
    if not pilot or not usage:
        return None
    out = {"pilot_id": pilot["pilot_id"], "offline_stub": pilot["offline_stub"], "input": pilot["input"],
           "settings": pilot["settings"], "runs": {}, "unpriced_items": []}
    for label in ("cold", "warm"):
        run = pilot["runs"].get(label)
        if not run:
            continue
        stages, unpriced = _stage_stats(R, [u for u in usage if u["run_label"] == label],
                                        [c for c in pilot.get("calls", []) if c["run_label"] == label])
        out["unpriced_items"] += unpriced
        res = run["results"]
        billed = sum(s["billed_usd"] for s in stages.values())
        equiv = sum(s["api_equivalent_usd"] for s in stages.values())
        rows = res["scope"]["unique_ids"]
        out["runs"][label] = {
            "run_id": run["run_id"], "status": run["status"], "wall_clock_s": run["wall_clock_s"],
            "process_wall_clock_s": pilot.get("process_wall_clock_s", {}).get(label),
            "stage_seconds": run["stage_seconds"], "rows": rows, "completed": res["completed"],
            "quarantined": res["quarantined"], "unfinished": res["unfinished"],
            "distinct_texts": res["scope"]["distinct_nonempty_texts"], "exact_text_cache_reuses": res["exact_text_cache_reuses"],
            "result_cache_hits": ((res["completed"] + res["quarantined"]) if label == "warm" and not stages.get("enrich_primary")
                                  else res["exact_text_cache_reuses"]),
            "new_enrichment_calls": sum(stages.get(s, {}).get("attempts", 0) for s in ("enrich_primary", "fallback1", "fallback2")),
            "stages": stages, "api_cost_usd": round(billed, 10), "api_equivalent_subscription_usd": round(equiv, 10),
            "cost_per_1000_input_rows_usd": round(billed / rows * 1000, 8) if rows else None,
            "cost_per_completed_record_usd": round(billed / res["completed"], 10) if res["completed"] else None,
            "throughput_rows_per_s": round(rows / run["wall_clock_s"], 3) if run["wall_clock_s"] else None,
        }
    return out


def load_refreshes(R, folder):
    """Measured larger runs (500 / 10,000 reviews) saved by `calculator.py refresh`."""
    out = []
    for p in sorted(Path(folder).glob("*.json")) if Path(folder).exists() else []:
        ref = json.loads(p.read_text(encoding="utf-8"))
        usage = load_usage(p.with_name(p.stem + "_usage.csv"))
        calls = read_jsonl(p.with_name(p.stem + "_calls.jsonl")) if p.with_name(p.stem + "_calls.jsonl").exists() else []
        stages, unpriced = _stage_stats(R, usage, calls)
        billed = sum(s["billed_usd"] for s in stages.values())
        ref.update({"stages": stages, "api_cost_usd": round(billed, 8), "unpriced_items": unpriced,
                    "api_equivalent_subscription_usd": round(sum(s["api_equivalent_usd"] for s in stages.values()), 8),
                    "cost_per_1000_input_rows_usd": round(billed / ref["rows"] * 1000, 6) if ref.get("rows") else None})
        out.append(ref)
    return sorted(out, key=lambda r: r.get("distinct_texts") or 0)


# ---- projection -----------------------------------------------------------------------------------------
def _val(node):
    return node["value"] if isinstance(node, dict) else node


def _assumed_stage(R, st):
    """Per-unit cost/time for one stage from assumptions.json token counts (no measurement)."""
    tier = st.get("tier", "standard")
    rpr = float(_val(st.get("reviews_per_request", 1)) or 1)
    unc = float(_val(st.get("input_uncached_tokens_per_request", st.get("input_tokens_per_request", 0))) or 0)
    cached = float(_val(st.get("input_cached_tokens_per_request", 0)) or 0)
    out = float(_val(st.get("output_tokens_per_request", 0)) or 0)
    sub = is_subscription(R, st["provider"], st["model"])
    prices = {i: unit_price(R, st["provider"], st["model"], tier, i) for i in ("input_uncached", "input_cached", "output")}
    per_call = None if any(v is None for v in prices.values()) else \
        unc * prices["input_uncached"] + cached * prices["input_cached"] + out * prices["output"]
    equiv_call = None
    if sub and st.get("api_equivalent_model"):
        q = {i: api_equiv_price(R, st["api_equivalent_model"], i) for i in ("input_uncached", "input_cached", "output")}
        if all(v is not None for v in q.values()):
            equiv_call = unc * q["input_uncached"] + cached * q["input_cached"] + out * q["output"]
    return {"billed_per_call": per_call, "billed_per_review": None if per_call is None else per_call / rpr,
            "equiv_per_call": equiv_call, "equiv_per_review": None if equiv_call is None else equiv_call / rpr,
            "reviews_per_request": rpr, "latency_s": _val(st.get("seconds_per_request", {"value": None})),
            "tier": tier, "billing": "subscription" if sub else "api", "source": "assumptions.json (estimate)"}


def per_stage_inputs(a, R, measured_sources):
    """Per-unit inputs: the largest real (non-stub) measured run wins; otherwise assumptions."""
    best = None
    for src in measured_sources:
        if src and not src.get("offline_stub") and src.get("stages"):
            if best is None or (src.get("distinct_texts") or 0) >= (best.get("distinct_texts") or 0):
                best = src
    out = {}
    for name in STAGE_ORDER:
        st = a["stages"][name]
        m = (best or {}).get("stages", {}).get(name)
        base = _assumed_stage(R, st)
        if m and m.get("succeeded"):
            base.update({
                "billed_per_review": m["billed_usd_per_review"], "billed_per_call": m["billed_usd_per_call"],
                "equiv_per_review": m["api_equivalent_usd_per_review"], "equiv_per_call": m["api_equivalent_usd_per_call"],
                "reviews_per_request": m["reviews_per_request"] or base["reviews_per_request"],
                "latency_s": m["mean_latency_s"] or base["latency_s"],
                "tier": ",".join(m["tiers"]), "billing": ",".join(m["billing"]),
                "source": f"measured: {best.get('label') or best.get('pilot_id')} ({best.get('distinct_texts')} distinct texts)"})
        base.update({"provider": st["provider"], "model": st["model"], "fixed_calls": st.get("fixed_calls"),
                     "rpm_limit": _val(st.get("provider_requests_per_minute_limit", {"value": None}))})
        out[name] = base
    rates = {}
    if best:
        prim = best["stages"].get("enrich_primary", {}).get("unique_reviews") or 0
        for t in ("fallback1", "fallback2"):
            rates[t] = (best["stages"].get(t, {}).get("unique_reviews", 0) / prim) if prim else None
    return out, rates, best


def _scenarios(a, R, scope, per_stage, measured_rates, budget, workers):
    controls = a["controls"]
    results = {}
    for scen_name, sc in a["scenarios"].items():
        for reuse in (True, False):
            units = scope["distinct_nonempty_texts"] if reuse else scope["nonempty_to_classify"]
            measured_any = any(ps["source"].startswith("measured") for ps in per_stage.values())
            extra = float(sc["transient_retry_rate"]) + float(sc["invalid_output_retry_rate"])
            retry_mult = 1 + (extra if (scen_name != "base" or not measured_any) else 0.0)
            tok_mult = float(sc.get("token_multiplier", 1.0))
            fb = {}
            for t, cap_key in (("fallback1", "max_fallback1_fraction"), ("fallback2", "max_fallback2_fraction")):
                rate = float(sc[f"{t}_rate"])
                if measured_rates.get(t) is not None:
                    rate = measured_rates[t] if scen_name == "base" else max(rate, measured_rates[t])
                fb[t] = min(rate, float(controls[cap_key]))
            verify_n = min(max(round(scope["distinct_nonempty_texts"] * float(controls["verify_sample_fraction"])),
                               int(controls.get("verify_min_sample", 0))), int(controls["verify_max_sample"]))
            work = {"enrich_primary": units, "fallback1": units * fb["fallback1"], "fallback2": units * fb["fallback2"],
                    "verify": verify_n}
            stages, billed, equiv, total_s, unpriced = {}, 0.0, 0.0, 0.0, []
            for name in STAGE_ORDER:
                ps = per_stage[name]
                if name in ("group", "memo"):
                    calls = (ps["fixed_calls"] or 0) * retry_mult
                    cost = None if ps["billed_per_call"] is None else calls * ps["billed_per_call"] * tok_mult
                    eq = None if ps["equiv_per_call"] is None else calls * ps["equiv_per_call"] * tok_mult
                    requests = calls
                    reviews = 0
                else:
                    reviews = work[name] * retry_mult
                    cost = None if ps["billed_per_review"] is None else reviews * ps["billed_per_review"] * tok_mult
                    eq = None if ps["equiv_per_review"] is None else reviews * ps["equiv_per_review"] * tok_mult
                    requests = reviews / (ps["reviews_per_request"] or 1)
                if cost is None:
                    unpriced.append(name)
                else:
                    billed += cost
                if eq:
                    equiv += eq
                lat = ps["latency_s"]
                if lat:
                    rate = workers / lat
                    if ps.get("rpm_limit"):
                        rate = min(rate, ps["rpm_limit"] / 60)
                    secs = requests / rate
                    total_s += secs
                else:
                    secs = None
                stages[name] = {"reviews": round(reviews, 1), "requests": round(requests, 1),
                                "billed_usd": None if cost is None else round(cost, 4),
                                "api_equivalent_usd": None if not eq else round(eq, 4),
                                "seconds": None if secs is None else round(secs, 1), "inputs_from": ps["source"]}
            code_s = scope["rows"] / 1000 * _val(a["stages_code"]["seconds_per_1000_rows"])
            total_s += code_s
            results[f"{scen_name}_{'reuse' if reuse else 'no_reuse'}"] = {
                "scenario": scen_name, "exact_text_reuse": reuse, "work_units": units, "fallback1_rate": fb["fallback1"],
                "fallback2_rate": fb["fallback2"], "verify_sample": verify_n, "retry_multiplier": round(retry_mult, 3),
                "token_multiplier": tok_mult, "stages": stages, "code_stage_seconds": round(code_s, 1),
                "api_cost_usd": round(billed, 2), "api_equivalent_subscription_usd": round(equiv, 2),
                "elapsed_hours": round(total_s / 3600, 2), "exceeds_budget": billed > budget, "unpriced_stages": unpriced}
    return results


def projection(a, R, meas, budget=None, rows_override=None, refreshes=()):
    budget = float(a["budget_usd"] if budget is None else budget)
    workers = int(a["controls"]["max_workers"])
    full = dict(a["full_run"])
    if rows_override:
        scale = rows_override / full["rows"]
        full = {"rows": rows_override, "nonempty_to_classify": round(full["nonempty_to_classify"] * scale),
                "empty_text_quarantines": round(full["empty_text_quarantines"] * scale),
                "distinct_nonempty_texts": round(full["distinct_nonempty_texts"] * scale)}
    pilot_src = None
    if meas and meas.get("runs", {}).get("cold"):
        cold = meas["runs"]["cold"]
        pilot_src = {"label": f"100-review pilot {meas['pilot_id']}", "offline_stub": meas["offline_stub"],
                     "distinct_texts": cold["distinct_texts"], "stages": cold["stages"]}
    per_stage, measured_rates, best = per_stage_inputs(a, R, [pilot_src, *refreshes])
    proj = {"full_run": full, "budget_usd": budget, "workers": workers, "per_stage_inputs": per_stage,
            "measured_fallback_rates": measured_rates, "inputs_measured_on": (best or {}).get("label"),
            "scenarios": _scenarios(a, R, full, per_stage, measured_rates, budget, workers)}
    if a.get("declared_scope") and not rows_override:
        ds = a["declared_scope"]
        proj["declared_scope"] = {"scope": ds, "scenarios": _scenarios(a, R, ds, per_stage, measured_rates, budget, workers)}
    alternatives = []
    for opt in a.get("primary_alternatives", {}).get("options", []):
        units = full["distinct_nonempty_texts"]
        st = _assumed_stage(R, opt)
        reqs = math.ceil(units / st["reviews_per_request"])
        cost = None if st["billed_per_call"] is None else reqs * st["billed_per_call"]
        ds_units = (a.get("declared_scope") or {}).get("distinct_nonempty_texts")
        ds_cost = None if (cost is None or not ds_units) else math.ceil(ds_units / st["reviews_per_request"]) * st["billed_per_call"]
        lat = st["latency_s"]
        hours = round(reqs / (workers / lat) / 3600, 2) if lat else None
        alternatives.append({"name": opt["name"], "requests": reqs, "api_cost_usd": None if cost is None else round(cost, 2),
                             "declared_scope_api_cost_usd": None if ds_cost is None else round(ds_cost, 2),
                             "hours": hours, "source": opt["source"]})
    proj["primary_alternatives"] = alternatives
    lc = a["local_compute"]
    proj["local_compute_note"] = (f"orchestrator only: {_val(lc['orchestrator_power_watts'])} W x hours x "
                                  f"${_val(lc['electricity_usd_per_kwh'])}/kWh (assumptions); hardware {lc['hardware_and_depreciation']}")
    return proj


def local_compute_usd(a, seconds):
    lc = a["local_compute"]
    return round(_val(lc["orchestrator_power_watts"]) / 1000 * seconds / 3600 * _val(lc["electricity_usd_per_kwh"]), 6)


def project_spend(runs_root=ROOT / "runs"):
    """Billed spend per run directory from saved call logs (stub and subscription calls excluded)."""
    per_run, total = {}, 0.0
    for db in sorted(Path(runs_root).glob("**/state.sqlite")):
        try:
            con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
            cols = {r[1] for r in con.execute("PRAGMA table_info(calls)")}
            billing = "AND COALESCE(billing,'api') != 'subscription'" if "billing" in cols else ""
            row = con.execute(
                "SELECT COALESCE(SUM(CASE WHEN outcome IN ('succeeded','failed') THEN COALESCE(cost_usd,0) ELSE 0 END),0),"
                " COALESCE(SUM(CASE WHEN outcome IN ('unknown','dispatched') THEN reserved_usd ELSE 0 END),0), COUNT(*) "
                f"FROM calls WHERE model NOT LIKE 'stub-%' {billing}").fetchone()
            con.close()
        except sqlite3.Error:
            continue
        if row[2]:
            per_run[str(db.parent.relative_to(ROOT))] = {"billed_usd": round(row[0], 6), "unknown_reserved_usd": round(row[1], 6),
                                                         "calls": row[2]}
            total += row[0] + row[1]
    return {"total_billed_usd": round(total, 6), "per_run": per_run,
            "computed_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}


# ---- report -----------------------------------------------------------------------------------------------
def fmt_usd(x, nd=6):
    return "unknown" if x is None else f"${x:,.{nd}f}"


def _scenario_table(L, scen, budget):
    L += ["| Scenario | Reuse | Work units | Fallback1 | Fallback2 | Verify sample | Retry x | Tokens x | Billed API cost | "
          "API-equivalent (Pro, not billed) | Elapsed h | vs budget |",
          "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|"]
    for s in scen.values():
        flag = "**EXCEEDS BUDGET**" if s["exceeds_budget"] else "within"
        L.append(f"| {s['scenario']} | {'yes' if s['exact_text_reuse'] else 'no'} | {s['work_units']:,} | "
                 f"{s['fallback1_rate']:.2%} | {s['fallback2_rate']:.2%} | {s['verify_sample']:,} | {s['retry_multiplier']:.2f} | "
                 f"{s['token_multiplier']:.2f} | ${s['api_cost_usd']:,.2f} | ${s['api_equivalent_subscription_usd']:,.2f} | "
                 f"{s['elapsed_hours']} | {flag} |")


def render(meas, proj, a, R, refreshes, spend, sources_note):
    L = ["# Cost and runtime calculator", "",
         f"Generated by `python3 cost/calculator.py` (offline replay) on {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}. "
         "No API key and no model call are needed to reproduce this page; every number below is recomputed from "
         "`usage.csv` / `refreshes/*_usage.csv` x `rates.csv`.", "",
         "Billing kinds: **billed API** = per-token charges on the OpenAI / TypeSafe accounts. **API-equivalent** = what "
         "calls made through the Claude Pro subscription (`claude -p`) would have cost at Anthropic API rates; they are "
         "not billed per call (the subscription is a fixed monthly fee), and they are never added to billed spend.", ""]
    if meas is None:
        L += ["## Measured 100-review pilot: NOT MEASURED YET", "",
              "No real pilot exists in this folder. Nothing in this section is estimated or simulated. To measure it:", "",
              "```bash", ".venv/bin/python cost/calculator.py pilot --execute --allow-paid --budget-usd 0.10", "```", ""]
    else:
        banner = ("> **OFFLINE STUB EXAMPLE - NOT A MEASUREMENT.** Calls went to the local stub; token counts are "
                  "placeholders and every model is `stub-*`, so all costs are $0 by definition.\n") if meas["offline_stub"] else ""
        L += ["## Measured 100-review pilot (cold, then warm)", "", banner,
              f"Pilot `{meas['pilot_id']}` | input `{meas['input']['path']}` sha256 `{meas['input']['sha256']}` "
              f"(manifest match: {meas['input']['matches_manifest']}) | {len(meas['input']['review_ids'])} review IDs; "
              "statuses in `pilot_records.jsonl`, every attempt in `pilot_calls.jsonl`.", ""]
        s = meas["settings"]
        L += ["### Per-stage settings", "", "| Stage | Provider | Model | Effort | Tier | Version / config | Batch | Workers |",
              "|---|---|---|---|---|---|---|---|"]
        for stage, st in s["stages"].items():
            L.append(f"| {stage} | {st['provider']} | `{st['model']}` | {st['effort']} | {st.get('tier', 'standard')} | "
                     f"`{st['config']}` | {st['batch']} | {s['workers']} |")
        c, w = meas["runs"].get("cold", {}), meas["runs"].get("warm", {})
        L += ["", "### Cold vs warm", "", "| | Cold | Warm |", "|---|---:|---:|"]
        def row(label, key, f=lambda v: v):
            L.append(f"| {label} | {f(c.get(key)) if c else '-'} | {f(w.get(key)) if w else '-'} |")
        row("Status", "status")
        row("Wall-clock seconds (pipeline clock)", "wall_clock_s")
        row("Wall-clock seconds (process, incl. start-up)", "process_wall_clock_s")
        L.append(f"| Rows / completed / quarantined / unfinished | {c.get('rows')} / {c.get('completed')} / {c.get('quarantined')} / "
                 f"{c.get('unfinished')} | {w.get('rows')} / {w.get('completed')} / {w.get('quarantined')} / {w.get('unfinished')} |")
        row("Distinct texts", "distinct_texts")
        row("Exact-text cache reuses", "exact_text_cache_reuses")
        row("Result-cache hits", "result_cache_hits")
        row("New enrichment calls (attempts)", "new_enrichment_calls")
        row("Billed API cost (usage x rates)", "api_cost_usd", lambda v: fmt_usd(v, 6))
        row("API-equivalent of Pro calls (not billed)", "api_equivalent_subscription_usd", lambda v: fmt_usd(v, 6))
        row("Billed cost per 1,000 input rows", "cost_per_1000_input_rows_usd", lambda v: fmt_usd(v, 6))
        row("Billed cost per completed record", "cost_per_completed_record_usd", lambda v: fmt_usd(v, 8))
        row("Throughput (rows/s)", "throughput_rows_per_s")
        for label, run in meas["runs"].items():
            L += ["", f"### {label.capitalize()} run by stage (`{run['run_id']}`)", "",
                  "| Stage | Tier / billing | Attempts | First tries | Transient retries | Invalid-output retries | Failed | "
                  "Input uncached | Cached | Cache write | Output | Mean latency s | Billed | API-equivalent |",
                  "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
            for stage, st in run["stages"].items():
                u = st["usage"]
                L.append(f"| {stage} | {'/'.join(st['tiers'])} / {'/'.join(st['billing'])} | {st['attempts']} | "
                         f"{st['first_attempts']} | {st['transient_retries']} | {st['invalid_output_retries']} | {st['failed']} | "
                         f"{u.get('input_uncached', 0)} | {u.get('input_cached', 0)} | {u.get('input_cache_write', 0)} | "
                         f"{u.get('output', 0)} | {st['mean_latency_s']} | {fmt_usd(st['billed_usd'], 6)} | "
                         f"{fmt_usd(st['api_equivalent_usd'], 6) if 'subscription' in st['billing'] else '-'} |")
            if not run["stages"]:
                L.append("| (no model calls) | - | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | - | $0.000000 | - |")
            L.append(f"\nStage seconds: `{json.dumps(run['stage_seconds'])}`")
            L.append(f"\nLocal compute (orchestrator only, assumptions): {fmt_usd(local_compute_usd(a, run['wall_clock_s'] or 0), 6)}")
        if meas["unpriced_items"]:
            L += ["", f"**Unpriced usage (cost unknown, not zero):** {sorted(set(meas['unpriced_items']))}"]
    if refreshes:
        L += ["", "## Measured refreshes at larger checkpoints", "",
              "| Checkpoint | Run | Rows | Distinct texts | Workers | Wall clock s | Billed API cost | Billed / 1,000 rows | "
              "API-equivalent (Pro) | Fallback1 reviews | Verify reviews |", "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
        for r in refreshes:
            st = r["stages"]
            L.append(f"| {r['label']} | `{r['run_dir']}` | {r['rows']:,} | {r['distinct_texts']:,} | {r.get('workers')} | "
                     f"{r.get('wall_clock_s')} | {fmt_usd(r['api_cost_usd'], 4)} | {fmt_usd(r['cost_per_1000_input_rows_usd'], 4)} | "
                     f"{fmt_usd(r['api_equivalent_subscription_usd'], 4)} | {st.get('fallback1', {}).get('unique_reviews', 0)} | "
                     f"{st.get('verify', {}).get('unique_reviews', 0)} |")
    p = proj
    L += ["", "## Estimated runs (before execution)", "",
          f"Per-unit inputs from: **{p['inputs_measured_on'] or 'assumptions.json (no real measurement yet)'}**. "
          f"Budget for comparison: **${p['budget_usd']:,.2f}** | max workers {p['workers']} | output-token cap per LLM review "
          f"{a['controls']['output_token_cap_per_review']} | max fallback fractions: tier 1 {a['controls']['max_fallback1_fraction']:.2%}, "
          f"tier 2 {a['controls']['max_fallback2_fraction']:.2%} | verification sample {a['controls']['verify_sample_fraction']:.0%} "
          f"of distinct texts, at most {a['controls']['verify_max_sample']:,}.", ""]
    if p.get("declared_scope"):
        ds = p["declared_scope"]["scope"]
        L += [f"### Declared analysis scope (the run this project executes): {ds['rows']:,} rows", "",
              f"{ds['nonempty_to_classify']:,} nonempty classifications, {ds['empty_text_quarantines']} empty-text quarantines, "
              f"{ds['distinct_nonempty_texts']:,} distinct texts with exact-text reuse ({ds['source']}).", ""]
        _scenario_table(L, p["declared_scope"]["scenarios"], p["budget_usd"])
        L += ["", "Per-stage breakdown (base scenario, reuse):", "",
              "| Stage | Reviews | Requests | Billed | API-equivalent | Seconds | Inputs from |", "|---|---:|---:|---:|---:|---:|---|"]
        for stage, st in p["declared_scope"]["scenarios"]["base_reuse"]["stages"].items():
            L.append(f"| {stage} | {st['reviews']:,} | {st['requests']:,} | {fmt_usd(st['billed_usd'], 4)} | "
                     f"{fmt_usd(st['api_equivalent_usd'], 4)} | {st['seconds']} | {st['inputs_from']} |")
    f = p["full_run"]
    L += ["", f"### Full corpus (course projection): {f['rows']:,} rows", "",
          f"{f['nonempty_to_classify']:,} nonempty outputs, {f['empty_text_quarantines']} empty-text quarantines, "
          f"{f['distinct_nonempty_texts']:,} distinct nonempty texts with exact-text reuse (course contract; verified by "
          "full-file ingestion).", ""]
    _scenario_table(L, p["scenarios"], p["budget_usd"])
    L += ["", "### Per-unit inputs used", "",
          "| Stage | Provider / model | Tier | Billing | Reviews per request | Billed per review | Billed per call | "
          "API-equivalent per call | Latency s | Source |", "|---|---|---|---|---:|---:|---:|---:|---:|---|"]
    for stage, ps in p["per_stage_inputs"].items():
        L.append(f"| {stage} | {ps['provider']} / `{ps['model']}` | {ps['tier']} | {ps['billing']} | {ps['reviews_per_request']} | "
                 f"{fmt_usd(ps['billed_per_review'], 8)} | {fmt_usd(ps['billed_per_call'], 6)} | {fmt_usd(ps['equiv_per_call'], 6)} | "
                 f"{ps['latency_s']} | {ps['source']} |")
    if p.get("primary_alternatives"):
        L += ["", "### Enrichment-stage alternatives (token estimates, enrichment only)", "",
              "| Option | Requests (full corpus) | Billed, full corpus | Billed, declared scope | Hours | Inputs from |",
              "|---|---:|---:|---:|---:|---|"]
        for o in p["primary_alternatives"]:
            L.append(f"| {o['name']} | {o['requests']:,} | {fmt_usd(o['api_cost_usd'], 2)} | "
                     f"{fmt_usd(o['declared_scope_api_cost_usd'], 2)} | {o['hours']} | {o['source']} |")
    L += ["", "## Spending controls and spend to date", "",
          f"- Per-run hard cap: `--budget-usd` (worst-case reservation before every attempt; admission stops when spent + unknown "
          f"+ reserved + next would cross it).",
          f"- Project-wide hard cap: `run.project_cap_usd` = ${a['controls'].get('project_cap_usd', 0):.2f} summed over every run "
          "directory under `runs/`; a run's budget is lowered to what remains, and a run is refused when nothing remains.",
          "- Provider-side: prepaid OpenAI credit with auto-recharge off.", "",
          f"Billed spend recorded in saved call logs: **{fmt_usd(spend.get('total_billed_usd'), 4)}** "
          f"(computed {spend.get('computed_at')}; see `project_spend.json`).", ""]
    if spend.get("per_run"):
        L += ["| Run directory | Calls (non-stub, billed providers) | Billed | Unknown (reserved) |", "|---|---:|---:|---:|"]
        for k, v in spend["per_run"].items():
            L.append(f"| `{k}` | {v['calls']} | {fmt_usd(v['billed_usd'], 6)} | {fmt_usd(v['unknown_reserved_usd'], 6)} |")
    L += ["", f"Local compute: {p['local_compute_note']}. Not included in API cost.", "",
          "## Formulas", "",
          "- Measured: `item_cost = billed_units x usd_per_million / 1,000,000` at the tier the provider reported; items are "
          "mutually exclusive (input_uncached = input - cached - cache_write; input_cached; input_cache_write; output including "
          "reasoning). Subscription (`claude -p`) items cost $0 billed; their API-equivalent uses the reported model's API row.",
          "- Projected stage cost = projected reviews (or fixed calls for group/memo) x measured billed cost per unique review "
          "(or per call), which already contains the measured retries, cache hits and tier; the base scenario adds no extra "
          "retries when inputs are measured, the conservative one multiplies by (1 + transient + invalid-output retry rates) "
          "and by a token multiplier. Fallback rates are the measured share of reviews routed, capped by the declared maxima.",
          "- Projected seconds = requests / min(workers / mean latency, provider requests-per-minute limit / 60), summed over "
          "stages, plus code stages per 1,000 rows.",
          "- Doubling every API rate doubles billed totals; local compute and measured times do not change. Changing projected "
          "counts never changes the measured sections.", "",
          "## Price sources (cost/rates.csv)", "",
          "| Kind | Provider | Model | Tier | Item | USD per 1M | Checked | Source |", "|---|---|---|---|---|---:|---|---|"]
    for (prov, model, tier, item), r in sorted(R["rows"].items()):
        L.append(f"| {r.get('kind', 'api')} | {prov} | `{model}` | {tier} | {item} | {r['usd_per_million']} | {r['checked_date']} | "
                 f"{r['source_url']} |")
    L += ["", sources_note, ""]
    return "\n".join(L)


def replay(rates_path, assumptions_path, pilot_dir, out_dir, budget=None):
    R = load_rates(rates_path)
    a = json.loads(Path(assumptions_path).read_text(encoding="utf-8"))
    pilot_path = Path(pilot_dir) / "pilot_runs.json"
    pilot = json.loads(pilot_path.read_text(encoding="utf-8")) if pilot_path.exists() else None
    if pilot and (Path(pilot_dir) / "pilot_calls.jsonl").exists():
        pilot["calls"] = read_jsonl(Path(pilot_dir) / "pilot_calls.jsonl")
    usage = load_usage(Path(pilot_dir) / "usage.csv")
    meas = measured(R, usage, pilot)
    refreshes = load_refreshes(R, Path(pilot_dir) / "refreshes")
    proj = projection(a, R, meas, budget, refreshes=refreshes)
    scaling = {str(n): {k: {"api_cost_usd": v["api_cost_usd"], "elapsed_hours": v["elapsed_hours"]}
                        for k, v in projection(a, R, meas, budget, rows_override=n, refreshes=refreshes)["scenarios"].items()
                        if k.endswith("_reuse")}
               for n in (100, 500, 10_000)}
    note = ("Scaling checkpoints (estimates with reuse, same per-unit inputs): "
            + "; ".join(f"{n} rows -> base ${s['base_reuse']['api_cost_usd']}, conservative ${s['conservative_reuse']['api_cost_usd']}"
                        for n, s in scaling.items()) + ".")
    spend_file = Path(pilot_dir) / "project_spend.json"
    spend = project_spend() if (ROOT / "runs").exists() else {}
    if spend.get("per_run") and Path(pilot_dir).resolve() == COST_DIR.resolve():
        spend_file.write_text(json.dumps(spend, indent=2) + "\n", encoding="utf-8")
    elif spend_file.exists():
        spend = json.loads(spend_file.read_text(encoding="utf-8"))
    md = render(meas, proj, a, R, refreshes, spend, note)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.md").write_text(md, encoding="utf-8")
    (out_dir / "report.json").write_text(json.dumps({"measured": meas, "refreshes": refreshes, "projection": proj,
                                                     "scaling": scaling, "spend": spend}, indent=2, default=str) + "\n",
                                         encoding="utf-8")
    return meas, proj


# ---- explicit pilot execution and refresh ----------------------------------------------------------------------
def derive_cost_100(target):
    """First 100 rows of checkpoint_500.csv, written exactly as prepare_dataset.py writes cost_100.csv."""
    manifest = json.loads((DATA_DIR / "manifest.json").read_text())
    with open(DATA_DIR / "checkpoint_500.csv", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))[:100]
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=FIELDS, lineterminator="\n")
    w.writeheader()
    w.writerows({k: r[k] for k in FIELDS} for r in rows)
    data = buf.getvalue().encode("utf-8")
    digest = hashlib.sha256(data).hexdigest()
    expected = manifest["files"]["cost_100.csv"]["sha256"]
    if digest != expected:
        raise SystemExit(f"derived cost_100 checksum {digest} != manifest {expected}; refusing to run the pilot")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return digest, expected, [r["review_id"] for r in rows]


def execute_pilot(args):
    stub = args.offline_stub
    if not stub and not args.allow_paid:
        raise SystemExit("A real pilot makes billed calls: add --allow-paid and --budget-usd (or use --offline-stub).")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    name = f"pilot100-{args.name + '-' if args.name else ''}{'offline-stub-' if stub else ''}{stamp}"
    run_dir = ROOT / "runs" / name
    input_csv = run_dir / "input" / "cost_100.csv"
    digest, expected, ids = derive_cost_100(input_csv)
    cmd = [sys.executable, "-m", "insight", "run", "--input", str(input_csv), "--run-dir", str(run_dir),
           "--workers", str(args.workers)]
    for item in args.set or []:
        cmd += ["--set", item]
    cmd += ["--offline-stub"] if stub else ["--allow-paid", "--budget-usd", str(args.budget_usd)]
    walls = {}
    for label in ("cold", "warm"):
        print(f"[pilot] {label} run: {' '.join(cmd[2:])}", flush=True)
        t0 = time.perf_counter()
        proc = subprocess.run(cmd, cwd=ROOT)
        walls[label] = round(time.perf_counter() - t0, 3)
        if proc.returncode != 0:
            print(f"[pilot] {label} run exited {proc.returncode}; saving what exists", flush=True)
    if stub:
        out_dir = COST_DIR / "offline_stub_example"
    elif args.name:
        out_dir = COST_DIR / "experiments" / args.name
    else:
        out_dir = COST_DIR
    collect(run_dir, out_dir, digest, expected, ids, walls, stub)
    replay(COST_DIR / "rates.csv", COST_DIR / "assumptions.json", out_dir, out_dir)
    print(f"[pilot] wrote {out_dir.relative_to(ROOT)}/report.md")


def _call_rows(con, labels):
    calls, usage_rows = [], []
    for c in con.execute("SELECT * FROM calls ORDER BY started_at"):
        keys = c.keys()
        label = labels.get(c["run_id"], "other") if labels is not None else "run"
        stage = STAGE_OF.get((c["role"], c["tier"] or c["role"]), c["role"])
        get = lambda k: c[k] if k in keys else None
        rec = {"request_id": c["request_id"], "run_id": c["run_id"], "run_label": label, "role": c["role"], "tier": c["tier"],
               "stage": stage, "phase": c["phase"], "provider": c["provider"], "model": c["model"], "effort": c["effort"],
               "label_config": c["label_config"], "stage_config": c["stage_config"], "review_ids": json.loads(c["review_ids"]),
               "attempt": c["attempt"], "task_attempt": c["task_attempt"],
               "outcome": "succeeded" if c["outcome"] == "succeeded" else "failed", "raw_outcome": c["outcome"],
               "error": c["error"], "input_tokens": c["input_tokens"] or 0, "cached_input_tokens": c["cached_input_tokens"] or 0,
               "cache_write_tokens": get("cache_write_tokens") or 0, "output_tokens": c["output_tokens"] or 0,
               "reasoning_tokens": c["reasoning_tokens"] or 0, "usage_reported": c["input_tokens"] is not None,
               "service_tier": get("service_tier") or "standard", "billing": get("billing") or "api",
               "model_reported": c["model_reported"], "provider_request_id": c["provider_request_id"],
               "started_at": c["started_at"], "duration_s": c["duration_s"], "worker": c["worker"],
               "max_output_tokens": c["max_output_tokens"], "cost_usd_logged": c["cost_usd"],
               "api_equivalent_usd_logged": get("api_equiv_usd")}
        calls.append(rec)
        inp, cached, write, out = rec["input_tokens"], rec["cached_input_tokens"], rec["cache_write_tokens"], rec["output_tokens"]
        for item, units in (("input_uncached", max(inp - cached - write, 0)), ("input_cached", cached),
                            ("input_cache_write", write), ("output", out)):
            usage_rows.append({"request_id": rec["request_id"], "run_label": label, "run_id": rec["run_id"], "stage": stage,
                               "role": rec["role"], "provider": rec["provider"], "model": rec["model"],
                               "model_reported": rec["model_reported"] or "", "tier": rec["service_tier"],
                               "billing": rec["billing"], "item": item, "billed_units": units, "unit": "token",
                               "usage_reported": rec["usage_reported"]})
    return calls, usage_rows


def _write_usage(path, rows):
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=USAGE_FIELDS)
        w.writeheader()
        w.writerows(rows)


def collect(run_dir, out_dir, digest, expected, ids, walls, stub):
    invs = sorted((json.loads(p.read_text()) for p in (run_dir / "invocations").glob("*.json")),
                  key=lambda r: r["finished_at"])
    labels = {}
    if invs:
        labels[invs[0]["run_id"]] = "cold"
    if len(invs) > 1:
        labels[invs[1]["run_id"]] = "warm"
    con = sqlite3.connect(run_dir / "state.sqlite")
    con.row_factory = sqlite3.Row
    calls, usage_rows = _call_rows(con, labels)
    con.close()
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "pilot_calls.jsonl", "w", encoding="utf-8") as f:
        for c in calls:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    _write_usage(out_dir / "usage.csv", usage_rows)
    recs_src = run_dir / "grading" / "records.jsonl"
    (out_dir / "pilot_records.jsonl").write_bytes(recs_src.read_bytes() if recs_src.exists() else b"")
    latest = invs[-1] if invs else {}
    models = latest.get("models", {})
    cfg = latest.get("config_summary", {})
    settings = {"workers": latest.get("workers"), "label_config": latest.get("label_config"), "stages": {}}
    for stage in STAGE_ORDER:
        m = models.get(stage, {})
        cfgv = latest.get("label_config") if stage.startswith(("enrich", "fallback")) else latest.get("stage_configs", {}).get(stage)
        settings["stages"][stage] = {"provider": m.get("provider"), "model": m.get("model"), "effort": m.get("effort"),
                                     "tier": cfg.get(stage, {}).get("service_tier", "standard"),
                                     "config": cfgv, "batch": cfg.get(stage, {}).get("batch", "-")}
    pilot = {"pilot_id": run_dir.name, "offline_stub": stub, "executed_at": datetime.now(timezone.utc).isoformat(),
             "run_dir": str(run_dir.relative_to(ROOT)),
             "input": {"path": str((run_dir / "input" / "cost_100.csv").relative_to(ROOT)), "sha256": digest,
                       "manifest_sha256": expected, "matches_manifest": digest == expected, "review_ids": ids},
             "settings": settings, "process_wall_clock_s": walls,
             "runs": {labels[i["run_id"]]: i for i in invs if i["run_id"] in labels}}
    (out_dir / "pilot_runs.json").write_text(json.dumps(pilot, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def refresh(args):
    """Save a larger measured run (500 / 10,000 reviews) for the projection, with its usage and call log."""
    run_dir = Path(args.run_dir).resolve()
    invs = sorted((json.loads(p.read_text()) for p in (run_dir / "invocations").glob("*.json")), key=lambda r: r["finished_at"])
    con = sqlite3.connect(run_dir / "state.sqlite")
    con.row_factory = sqlite3.Row
    calls, usage_rows = _call_rows(con, None)
    con.close()
    out = COST_DIR / "refreshes"
    out.mkdir(parents=True, exist_ok=True)
    _write_usage(out / f"{args.label}_usage.csv", usage_rows)
    with open(out / f"{args.label}_calls.jsonl", "w", encoding="utf-8") as f:
        for c in calls:
            c = dict(c)
            c["review_ids"] = c["review_ids"]
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    last = invs[-1] if invs else {}
    res = last.get("results", {})
    walls = [i.get("wall_clock_s") or 0 for i in invs]
    ref = {"label": args.label, "run_dir": str(run_dir.relative_to(ROOT)), "offline_stub": bool(last.get("offline_stub")),
           "rows": res.get("scope", {}).get("unique_ids"), "distinct_texts": res.get("scope", {}).get("distinct_nonempty_texts"),
           "completed": res.get("completed"), "quarantined": res.get("quarantined"), "unfinished": res.get("unfinished"),
           "workers": last.get("workers"), "invocations": len(invs), "wall_clock_s": round(sum(walls), 3),
           "label_config": last.get("label_config"), "saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    (out / f"{args.label}.json").write_text(json.dumps(ref, indent=2) + "\n", encoding="utf-8")
    replay(COST_DIR / "rates.csv", COST_DIR / "assumptions.json", COST_DIR, COST_DIR)
    print(f"[refresh] saved cost/refreshes/{args.label}.json and rewrote cost/report.md")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command")
    r = sub.add_parser("replay", help="offline recomputation (default)")
    r.add_argument("--rates", default=str(COST_DIR / "rates.csv"))
    r.add_argument("--assumptions", default=str(COST_DIR / "assumptions.json"))
    r.add_argument("--pilot-dir", default=str(COST_DIR))
    r.add_argument("--out-dir", default=str(COST_DIR))
    r.add_argument("--budget-usd", type=float, default=None)
    x = sub.add_parser("pilot", help="EXPLICIT pilot execution (cold + warm)")
    x.add_argument("--execute", action="store_true", required=True)
    x.add_argument("--allow-paid", action="store_true")
    x.add_argument("--budget-usd", type=float, default=0.10)
    x.add_argument("--workers", type=int, default=1)
    x.add_argument("--offline-stub", action="store_true")
    x.add_argument("--name", default=None, help="comparison experiment name (written to cost/experiments/<name>/)")
    x.add_argument("--set", action="append", default=[], metavar="KEY=VALUE", help="config override passed to the pipeline")
    f = sub.add_parser("refresh", help="save a measured 500 / 10,000-review run for the projection")
    f.add_argument("--run-dir", required=True)
    f.add_argument("--label", required=True)
    args = p.parse_args(argv)
    if args.command == "pilot":
        execute_pilot(args)
        return 0
    if args.command == "refresh":
        refresh(args)
        return 0
    if args.command is None:
        args = p.parse_args(["replay"])
    meas, proj = replay(args.rates, args.assumptions, args.pilot_dir, args.out_dir, args.budget_usd)
    print(f"measured pilot: {'none yet' if meas is None else meas['pilot_id'] + (' (OFFLINE STUB)' if meas['offline_stub'] else '')}")
    if meas:
        for label, run in meas["runs"].items():
            print(f"  {label}: wall {run['wall_clock_s']}s, billed ${run['api_cost_usd']:.6f}, "
                  f"API-equivalent (Pro) ${run['api_equivalent_subscription_usd']:.6f}, new enrichment calls {run['new_enrichment_calls']}")
    if proj.get("declared_scope"):
        b = proj["declared_scope"]["scenarios"]["base_reuse"]
        c = proj["declared_scope"]["scenarios"]["conservative_reuse"]
        print(f"declared scope estimate: base ${b['api_cost_usd']:,.2f} / {b['elapsed_hours']} h; conservative "
              f"${c['api_cost_usd']:,.2f} / {c['elapsed_hours']} h")
    base, cons = proj["scenarios"]["base_reuse"], proj["scenarios"]["conservative_no_reuse"]
    print(f"full corpus estimate: base+reuse ${base['api_cost_usd']:,.2f} / {base['elapsed_hours']} h; conservative no-reuse "
          f"${cons['api_cost_usd']:,.2f} / {cons['elapsed_hours']} h; budget ${proj['budget_usd']:,.2f}"
          + (" -> SOME SCENARIOS EXCEED THE BUDGET" if any(s["exceeds_budget"] for s in proj["scenarios"].values()) else ""))
    print(f"wrote {Path(args.out_dir) / 'report.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""100-review cost and runtime calculator. Offline replay is the default.

  python3 cost/calculator.py                     offline replay: recompute everything from saved files
                                                 (rates.csv, usage.csv, pilot_runs.json, pilot_calls.jsonl,
                                                 refreshes/*.json, assumptions.json); rewrite report.md/.json
                                                 and project_spend.json
  python3 cost/calculator.py replay --rates R --assumptions A --out-dir D [--budget-usd B] [--runs-root DIR]
                                                 same, with edited inputs, written to D only (the committed
                                                 cost/project_spend.json is written only when D is cost/)
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

Spend to date (project_spend.json) needs no state database: every billed-provider call is priced as
usage x rates.csv and counted once by request_id, its usage taken from runs/**/state.sqlite when present and
otherwise from the committed per-call evidence (refreshes/*_usage.csv + *_calls.jsonl, usage.csv +
pilot_calls.jsonl). Runs whose calls are in neither source are listed as "not reproducible offline".
The runs root is INSIGHT_RUNS_ROOT (as for the pipeline's project cap) or <repo>/runs, or --runs-root.
"""

import argparse
import csv
import hashlib
import io
import json
import math
import os
import re
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
STAGE_OF = {("enrich", "primary"): "enrich_primary", ("enrich", "crosscheck"): "crosscheck", ("enrich", "fallback1"): "fallback1",
            ("enrich", "fallback2"): "fallback2", ("verify", "verify"): "verify", ("group", "group"): "group",
            ("memo", "memo"): "memo"}
STAGE_ORDER = ("enrich_primary", "crosscheck", "fallback1", "fallback2", "verify", "group", "memo")
USAGE_FIELDS = ["request_id", "run_label", "run_id", "stage", "role", "provider", "model", "model_reported", "tier",
                "billing", "item", "billed_units", "unit", "usage_reported"]
ENRICH_POOL = ("enrich_primary", "fallback1", "fallback2")  # share the enrichment worker pool ("enrich" stage seconds)
CODE_STAGES = ("ingest", "rank", "export")
UNSETTLED = ("unknown", "dispatched")  # outcome/charge unknown: the reservation counts as spend


def default_runs_root():
    """Same rule as the pipeline's project cap (insight/cli.py): INSIGHT_RUNS_ROOT, else <repo>/runs."""
    return Path(os.environ.get("INSIGHT_RUNS_ROOT") or ROOT / "runs")


def _rel(path):
    try:
        return Path(path).resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(path)


def _run_key(run_dir, runs_root):
    """'runs/<dir>' whatever the runs root is, so a copied runs tree yields the same keys."""
    return "runs/" + Path(run_dir).resolve().relative_to(Path(runs_root).resolve()).as_posix()


def _resolve_run_dir(run_key, runs_root):
    parts = Path(run_key).parts
    return Path(runs_root).joinpath(*parts[1:]) if parts and parts[0] == "runs" else ROOT / run_key


def fallback_caps(label_config):
    """Declared fallback caps (fractions) parsed from a label_config such as 'm@none>m@low(10%)>sonnet@low(0.25%)|...'."""
    out = []
    for tier in (label_config or "").split("|")[0].split(">")[1:]:
        m = re.search(r"\(([\d.]+)%\)", tier)
        out.append(float(m.group(1)) / 100 if m else None)
    return out


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


_READ_CACHE = {}


def _cached(loader, path):
    """Read-only reuse of large evidence files within one process (keyed by path, size and mtime)."""
    p = Path(path)
    st = p.stat()
    key = (loader.__name__, str(p.resolve()), st.st_size, st.st_mtime_ns)
    if key not in _READ_CACHE:
        _READ_CACHE[key] = loader(p)
    return _READ_CACHE[key]


def _load_invocations(run_dir):
    d = Path(run_dir) / "invocations"
    if not d.is_dir():
        return []
    invs = []
    for p in d.glob("*.json"):
        try:
            invs.append(json.loads(p.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return sorted(invs, key=lambda r: r.get("finished_at") or "")


def invocation_summary(invs, calls):
    """Workers and stage seconds per invocation. The enrichment worker count comes from the invocations that
    actually made enrichment calls, not from the latest invocation (a later regeneration may use fewer)."""
    enrich_calls = Counter(c["run_id"] for c in calls if c.get("role") == "enrich")
    detail = []
    for i in invs:
        ledger = i.get("ledger") or {}
        detail.append({"run_id": i.get("run_id"), "phase": i.get("phase"), "status": i.get("status"),
                       "workers": i.get("workers"), "wall_clock_s": i.get("wall_clock_s"),
                       "stage_seconds": i.get("stage_seconds") or {}, "enrichment_calls": enrich_calls.get(i.get("run_id"), 0),
                       "budget_cap_usd": ledger.get("cap_usd"), "budget_denials": ledger.get("denials")})
    enr = [d for d in detail if d["enrichment_calls"]]
    latest = invs[-1].get("workers") if invs else None
    return {"workers": max(d["workers"] or 0 for d in enr) if enr else latest,
            "workers_source": ("max over the invocations that made enrichment calls" if enr
                               else "latest invocation (no enrichment calls recorded)"),
            "latest_invocation_workers": latest,
            "enrichment_invocations": len(enr),
            "enrichment_wall_clock_s": round(sum(d["wall_clock_s"] or 0 for d in enr), 3) if enr else None,
            "enrichment_stage_seconds": round(sum(d["stage_seconds"].get("enrich") or 0 for d in enr), 3) if enr else None,
            "invocations_detail": detail}


def _enrich_pool(detail, calls):
    """Measured utilisation of the enrichment worker pool: summed attempt durations of the pool's stages divided by
    (workers x enrich stage wall seconds), over the invocations that made enrichment calls."""
    enr = [d for d in detail or [] if d.get("enrichment_calls") and (d.get("stage_seconds") or {}).get("enrich")]
    if not enr:
        return None
    ids = {d["run_id"] for d in enr}
    attempt_s = sum(float(c.get("duration_s") or 0) for c in calls if c.get("run_id") in ids
                    and STAGE_OF.get((c["role"], c.get("tier") or c["role"])) in ENRICH_POOL)
    capacity = sum((d.get("workers") or 0) * d["stage_seconds"]["enrich"] for d in enr)
    workers_seen = max((len({c.get("worker") for c in calls if c.get("run_id") == rid and c.get("role") == "enrich"})
                        for rid in ids), default=0)
    return {"workers": max(d.get("workers") or 0 for d in enr), "worker_ids_seen_in_calls": workers_seen,
            "enrich_stage_seconds": round(sum(d["stage_seconds"]["enrich"] for d in enr), 3),
            "attempt_seconds": round(attempt_s, 3),
            "efficiency": round(min(1.0, attempt_s / capacity), 4) if capacity and attempt_s else None,
            "invocations": sorted(ids)}


# ---- measured runs -------------------------------------------------------------------------------------
def _stage_stats(R, usage_rows, calls):
    stages = defaultdict(lambda: {"attempts": 0, "first_attempts": 0, "transient_retries": 0, "invalid_output_retries": 0,
                                  "failed": 0, "succeeded": 0, "usage": Counter(), "billed_usd": 0.0,
                                  "api_equivalent_usd": 0.0, "api_equivalent_unpriced": 0, "latencies": [],
                                  "attempt_seconds": 0.0, "rate_limited": 0, "reviews_sent": 0, "unique_reviews": set(), "tiers": set(),
                                  "billing": set(), "models_reported": set()})
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
        st["rate_limited"] += "429" in (c.get("error") or "") or "rate limit" in (c.get("error") or "").lower()
        st["failed"] += c["outcome"] != "succeeded"
        st["succeeded"] += c["outcome"] == "succeeded"
        st["reviews_sent"] += len(c.get("review_ids") or [])
        st["attempt_seconds"] += float(c.get("duration_s") or 0)  # every attempt, including failed ones and retries
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
        s["attempt_seconds"] = round(s["attempt_seconds"], 3)
        s["mean_attempt_latency_s"] = round(s["attempt_seconds"] / s["attempts"], 4) if s["attempts"] and s["attempt_seconds"] else None
        s["attempts_per_unique_review"] = round(s["attempts"] / n_rev, 6) if n_rev else None
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
        run_calls = [c for c in pilot.get("calls", []) if c["run_label"] == label]
        stages, unpriced = _stage_stats(R, [u for u in usage if u["run_label"] == label], run_calls)
        out["unpriced_items"] += unpriced
        res = run["results"]
        detail = invocation_summary([run], run_calls)["invocations_detail"]
        billed = sum(s["billed_usd"] for s in stages.values())
        equiv = sum(s["api_equivalent_usd"] for s in stages.values())
        rows = res["scope"]["unique_ids"]
        out["runs"][label] = {
            "run_id": run["run_id"], "status": run["status"], "wall_clock_s": run["wall_clock_s"],
            "workers": run.get("workers", pilot["settings"].get("workers")), "enrich_pool": _enrich_pool(detail, run_calls),
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
        usage_path, calls_path = p.with_name(p.stem + "_usage.csv"), p.with_name(p.stem + "_calls.jsonl")
        usage = _cached(load_usage, usage_path) if usage_path.exists() else []
        calls = _cached(read_jsonl, calls_path) if calls_path.exists() else []
        stages, unpriced = _stage_stats(R, usage, calls)
        billed = sum(s["billed_usd"] for s in stages.values())
        ref.update({"stages": stages, "api_cost_usd": round(billed, 8), "unpriced_items": unpriced,
                    "enrich_pool": _enrich_pool(ref.get("invocations_detail"), calls),
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
    pool = (best or {}).get("enrich_pool") or {}
    out = {}
    for name in STAGE_ORDER:
        st = a["stages"][name]
        m = (best or {}).get("stages", {}).get(name)
        base = _assumed_stage(R, st)
        base["attempts_per_review"] = None
        base["latency_succeeded_s"] = None
        if m and m.get("succeeded"):
            base.update({
                "billed_per_review": m["billed_usd_per_review"], "billed_per_call": m["billed_usd_per_call"],
                "equiv_per_review": m["api_equivalent_usd_per_review"], "equiv_per_call": m["api_equivalent_usd_per_call"],
                "reviews_per_request": m["reviews_per_request"] or base["reviews_per_request"],
                # time per attempt over every attempt (failed ones and retries included), and attempts per unique review
                "latency_s": m.get("mean_attempt_latency_s") or m["mean_latency_s"] or base["latency_s"],
                "attempts_per_review": m.get("attempts_per_unique_review"), "latency_succeeded_s": m["mean_latency_s"],
                "tier": ",".join(m["tiers"]), "billing": ",".join(m["billing"]),
                "source": f"measured: {best.get('label') or best.get('pilot_id')} ({best.get('distinct_texts')} distinct texts)"})
        eff = pool.get("efficiency") if name in ENRICH_POOL and m and m.get("succeeded") else None
        base.update({"provider": st["provider"], "model": st["model"], "fixed_calls": st.get("fixed_calls"),
                     "workers": st.get("workers"), "pool_efficiency": eff or 1.0,
                     "pool_efficiency_source": (f"measured: {best.get('label')}" if eff else "1.0 (not measured)"),
                     "rpm_limit": _val(st.get("provider_requests_per_minute_limit", {"value": None}))})
        out[name] = base
    rates = {}
    if best:
        prim = best["stages"].get("enrich_primary", {}).get("unique_reviews") or 0
        for t in ("crosscheck", "fallback1", "fallback2"):
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
            xc = float(controls.get("crosscheck_fraction", 0.0))
            if measured_rates.get("crosscheck") is not None:  # measured share of texts that were cross-checked
                xc = measured_rates["crosscheck"] if scen_name == "base" else max(xc, measured_rates["crosscheck"])
            work = {"enrich_primary": units, "crosscheck": units * xc,
                    "fallback1": units * fb["fallback1"], "fallback2": units * fb["fallback2"], "verify": verify_n}
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
                    apr = ps.get("attempts_per_review")
                    requests = reviews * apr if apr else reviews / (ps["reviews_per_request"] or 1)
                if cost is None:
                    unpriced.append(name)
                else:
                    billed += cost
                if eq:
                    equiv += eq
                lat = ps["latency_s"]
                adds = 0.0
                if lat:
                    rate = (ps.get("workers") or workers) * (ps.get("pool_efficiency") or 1.0) / lat
                    if ps.get("rpm_limit"):
                        rate = min(rate, ps["rpm_limit"] / 60)
                    secs = requests / rate
                    if name == "crosscheck":  # own worker pool, runs alongside the primary pass: only the excess adds
                        adds = max(0.0, secs - (stages.get("enrich_primary", {}).get("seconds") or 0.0))
                    else:
                        adds = secs
                    total_s += adds
                else:
                    secs = None
                stages[name] = {"reviews": round(reviews, 1), "requests": round(requests, 1),
                                "billed_usd": None if cost is None else round(cost, 4),
                                "api_equivalent_usd": None if not eq else round(eq, 4),
                                "seconds": None if secs is None else round(secs, 1), "adds_seconds": round(adds, 1),
                                "inputs_from": ps["source"]}
            code_s = scope["rows"] / 1000 * _val(a["stages_code"]["seconds_per_1000_rows"])
            total_s += code_s
            results[f"{scen_name}_{'reuse' if reuse else 'no_reuse'}"] = {
                "scenario": scen_name, "exact_text_reuse": reuse, "work_units": units, "fallback1_rate": fb["fallback1"],
                "fallback2_rate": fb["fallback2"], "verify_sample": verify_n, "retry_multiplier": round(retry_mult, 3),
                "token_multiplier": tok_mult, "stages": stages, "code_stage_seconds": round(code_s, 1),
                "api_cost_usd": round(billed, 2), "api_equivalent_subscription_usd": round(equiv, 2),
                "elapsed_seconds": round(total_s, 1), "elapsed_hours": round(total_s / 3600, 2),
                "exceeds_budget": billed > budget, "unpriced_stages": unpriced}
    return results


def _measured_stage_seconds(src):
    """Wall-clock seconds by stage over the invocations of a measured run that made enrichment calls."""
    enr = [d for d in (src or {}).get("invocations_detail") or [] if d.get("enrichment_calls")]
    if not enr:
        return None
    agg = Counter()
    for d in enr:
        for k, v in (d.get("stage_seconds") or {}).items():
            agg[k] += v or 0
    return {"enrichment": round(agg["enrich"], 3), "verify": round(agg["verify"], 3), "group": round(agg["group"], 3),
            "memo": round(agg["memo"], 3), "code": round(sum(agg[k] for k in CODE_STAGES), 3),
            "enrichment_by_invocation": [round((d.get("stage_seconds") or {}).get("enrich") or 0, 3) for d in enr],
            "total": round(sum(d.get("wall_clock_s") or 0 for d in enr), 3), "invocations": [d["run_id"] for d in enr],
            "workers": [d.get("workers") for d in enr]}


def _projection_check(scen, measured_s):
    st = scen["stages"]
    projected = {"enrichment": sum(st[s]["adds_seconds"] for s in ("enrich_primary", "crosscheck", "fallback1", "fallback2")),
                 "verify": st["verify"]["adds_seconds"], "group": st["group"]["adds_seconds"],
                 "memo": st["memo"]["adds_seconds"], "code": scen["code_stage_seconds"], "total": scen["elapsed_seconds"]}
    return {k: {"projected_s": round(projected[k], 1), "measured_s": measured_s[k],
                "ratio": round(projected[k] / measured_s[k], 3) if measured_s[k] else None} for k in projected}


def _source_label(src):
    return src.get("label") or src.get("pilot_id")


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
                     "rows": cold["rows"], "distinct_texts": cold["distinct_texts"], "stages": cold["stages"],
                     "enrich_pool": cold.get("enrich_pool")}
    sources = [pilot_src, *refreshes]
    per_stage, measured_rates, best = per_stage_inputs(a, R, sources)
    proj = {"full_run": full, "budget_usd": budget, "workers": workers, "per_stage_inputs": per_stage,
            "measured_fallback_rates": measured_rates, "inputs_measured_on": (best or {}).get("label"),
            "enrich_pool": (best or {}).get("enrich_pool"),
            "scenarios": _scenarios(a, R, full, per_stage, measured_rates, budget, workers)}
    if a.get("declared_scope") and not rows_override:
        ds = a["declared_scope"]
        proj["declared_scope"] = {"scope": ds, "scenarios": _scenarios(a, R, ds, per_stage, measured_rates, budget, workers)}
        measured_s = _measured_stage_seconds(best)
        if measured_s and best.get("rows") == ds["rows"]:  # same scope was executed: compare projection and clock
            proj["declared_scope"]["projection_check"] = {
                "against": best.get("label"), "scenario": "base_reuse", "measured": measured_s,
                "rows": _projection_check(proj["declared_scope"]["scenarios"]["base_reuse"], measured_s)}
        # the declared-scope estimate each measured step gives on its own (offline, today's assumptions.json)
        steps = []
        for i, src in enumerate(sources):
            if not src or src.get("offline_stub") or not src.get("stages"):
                continue
            ps_i, rates_i, best_i = per_stage_inputs(a, R, sources[:i + 1])
            sc = _scenarios(a, R, ds, ps_i, rates_i, budget, workers)
            steps.append({"inputs_from": _source_label(best_i), "distinct_texts": best_i.get("distinct_texts"),
                          "fallback1_rate": sc["base_reuse"]["fallback1_rate"],
                          "pool_efficiency": ps_i["enrich_primary"]["pool_efficiency"],
                          **{k: {"api_cost_usd": sc[k]["api_cost_usd"], "elapsed_hours": sc[k]["elapsed_hours"],
                                 "exceeds_budget": sc[k]["exceeds_budget"]}
                             for k in ("base_reuse", "conservative_reuse", "conservative_no_reuse")}})
        proj["declared_scope"]["estimates_by_step"] = steps
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


# ---- spend to date ------------------------------------------------------------------------------------------
_DB_COLS = ("request_id", "run_id", "role", "tier", "provider", "model", "outcome", "input_tokens", "cached_input_tokens",
            "cache_write_tokens", "output_tokens", "service_tier", "billing", "reserved_usd", "cost_usd")


def _token_units(r):
    inp, cached, write, out = (int(r.get(k) or 0) for k in ("input_tokens", "cached_input_tokens", "cache_write_tokens",
                                                            "output_tokens"))
    return {"input_uncached": max(inp - cached - write, 0), "input_cached": cached, "input_cache_write": write, "output": out}


def _db_calls(db):
    """Every call in one state database (read-only), with usage split into the mutually exclusive billing items."""
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        cols = {r[1] for r in con.execute("PRAGMA table_info(calls)")}
        if not cols:
            return []
        sel = [c for c in _DB_COLS if c in cols]
        rows = [dict(zip(sel, r)) for r in con.execute(f"SELECT {', '.join(sel)} FROM calls")]
    finally:
        con.close()
    return [{"request_id": r["request_id"], "provider": r["provider"], "model": r["model"],
             "tier": r.get("service_tier") or "standard", "billing": r.get("billing") or "api", "outcome": r["outcome"],
             "units": _token_units(r), "logged_cost": r.get("cost_usd"), "reserved": r.get("reserved_usd")} for r in rows]


def _billable(R, c):
    """Calls on billed providers only: stub models and Claude Pro (subscription) calls are not billed per call."""
    return (not str(c["model"]).startswith("stub-") and c.get("billing") != "subscription"
            and not is_subscription(R, c["provider"], c["model"]))


def _price_units(R, c):
    total, missing = 0.0, []
    for item, units in c["units"].items():
        if not units:
            continue
        p = unit_price(R, c["provider"], c["model"], c["tier"], item)
        if p is None:
            missing.append(f"{c['provider']}/{c['model']}/{c['tier']}/{item}")
        else:
            total += units * p
    return total, missing


def committed_call_evidence(cost_dir=COST_DIR):
    """Per-call evidence committed under cost/: refreshes (500 / 10,000 / final) and real (non-stub) pilots."""
    cost_dir, found = Path(cost_dir), []

    def add(meta_path, usage_path, calls_path):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if meta.get("offline_stub") or not meta.get("run_dir") or not calls_path.exists():
            return
        files = [_rel(usage_path)] if usage_path.exists() else []
        found.append({"run": Path(meta["run_dir"]).as_posix(), "usage": usage_path, "calls": calls_path,
                      "label": " + ".join(files + [_rel(calls_path)])})

    folder = cost_dir / "refreshes"
    for p in sorted(folder.glob("*.json")) if folder.is_dir() else []:
        add(p, p.with_name(p.stem + "_usage.csv"), p.with_name(p.stem + "_calls.jsonl"))
    for p in [cost_dir / "pilot_runs.json", *sorted(cost_dir.glob("experiments/*/pilot_runs.json"))]:
        if p.exists():
            add(p, p.with_name("usage.csv"), p.with_name("pilot_calls.jsonl"))
    return found


def _ledger_usd(invs):
    """Spend the run's own ledger recorded at its latest invocation (spent + unknown), or None."""
    for inv in reversed(invs or []):
        led = inv.get("ledger") or {}
        if led.get("spent_usd") is not None:
            return round(float(led["spent_usd"]) + float(led.get("unknown_usd") or 0), 8)
    return None


def _previous_ledger(cost_dir):
    p = Path(cost_dir) / "project_spend.json"
    try:
        prev = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out = {k: {"usd": round((v.get("billed_usd") or 0) + (v.get("unknown_reserved_usd") or 0), 6), "at": prev.get("computed_at")}
           for k, v in (prev.get("per_run") or {}).items()}
    for k, v in (prev.get("not_reproducible_offline") or {}).items():
        out.setdefault(k, {"usd": v.get("recorded_usd"), "at": v.get("recorded_in")})
    return out


def project_spend(runs_root=None, cost_dir=COST_DIR, rates_path=None):
    """Billed spend to date per run directory, reproducible without the state databases.

    Each billed-provider call (stub and Claude Pro calls excluded) is priced as usage x rates.csv and counted once by
    request_id. Usage comes from runs/**/state.sqlite when the database is present, otherwise from the committed
    per-call evidence under cost/. Calls whose outcome is unknown count their reservation, as in the pipeline's
    project cap. Runs that neither source covers are listed as not reproducible offline, never silently dropped.
    """
    root = Path(runs_root) if runs_root else default_runs_root()
    cost_dir = Path(cost_dir)
    R = load_rates(rates_path or cost_dir / "rates.csv")
    calls, unreadable, dup_db, dbs_read = {}, {}, 0, 0
    info = defaultdict(lambda: {"state_db": False, "committed": [], "from_db": 0, "from_committed": 0, "in_both": 0,
                                "differ": 0})
    for db in sorted(root.glob("**/state.sqlite")) if root.is_dir() else []:
        key = _run_key(db.parent, root)
        try:
            rows = _db_calls(db)
        except sqlite3.Error as e:
            unreadable[key] = str(e)
            continue
        dbs_read += 1
        info[key]["state_db"] = True
        for c in rows:
            if not _billable(R, c):
                continue
            if c["request_id"] in calls:
                dup_db += 1
                continue
            c.update(run=key, source="state.sqlite")
            calls[c["request_id"]] = c
            info[key]["from_db"] += 1
    evidence = committed_call_evidence(cost_dir)
    for ev in evidence:
        run = info[ev["run"]]
        run["committed"].append(ev["label"])
        usage = defaultdict(dict)
        for u in (_cached(load_usage, ev["usage"]) if ev["usage"].exists() else []):
            usage[u["request_id"]][u["item"]] = usage[u["request_id"]].get(u["item"], 0) + int(u["billed_units"])
        for rec in _cached(read_jsonl, ev["calls"]):
            c = {"request_id": rec["request_id"], "provider": rec["provider"], "model": rec["model"],
                 "tier": rec.get("service_tier") or "standard", "billing": rec.get("billing") or "api",
                 "outcome": rec.get("raw_outcome") or rec.get("outcome"),
                 "units": dict(usage.get(rec["request_id"]) or _token_units(rec)),
                 "logged_cost": rec.get("cost_usd_logged"), "reserved": rec.get("reserved_usd"),
                 "run": ev["run"], "source": ev["label"]}
            if not _billable(R, c):
                continue
            prior = calls.get(c["request_id"])
            if prior is not None:  # already counted from a state database: compare, never add twice
                run["in_both"] += 1
                same = ({k: v for k, v in prior["units"].items() if v} == {k: v for k, v in c["units"].items() if v}
                        and prior["outcome"] == c["outcome"])
                run["differ"] += not same
                continue
            calls[c["request_id"]] = c
            run["from_committed"] += 1

    per_run, unpriced, unresolved = {}, set(), 0
    for c in calls.values():
        e = per_run.setdefault(c["run"], {"billed": 0.0, "unknown": 0.0, "calls": 0, "logged": 0.0, "logged_n": 0,
                                          "differ_logged": 0, "priced_from_log": 0, "unpriced_calls": 0})
        e["calls"] += 1
        if c["outcome"] in UNSETTLED:
            if c.get("reserved") is None:
                unresolved += 1
            else:
                e["unknown"] += float(c["reserved"])
            continue
        cost, missing = _price_units(R, c)
        if missing:
            unpriced.update(missing)
            if c.get("logged_cost") is None:
                e["unpriced_calls"] += 1
                continue
            cost = float(c["logged_cost"])  # no dated rate row: the cost logged at call time (saved file) is used
            e["priced_from_log"] += 1
        e["billed"] += cost
        if c.get("logged_cost") is not None:
            e["logged"] += float(c["logged_cost"])
            e["logged_n"] += 1
            e["differ_logged"] += abs(cost - float(c["logged_cost"])) > 1e-9

    out_runs = {}
    for key in sorted(per_run):
        e, src = per_run[key], info[key]
        ledger = _ledger_usd(_load_invocations(_resolve_run_dir(key, root)))
        amount = e["billed"] + e["unknown"]
        used = [s for s, n in (("state.sqlite", src["from_db"]), ("committed usage", src["from_committed"])) if n]
        out_runs[key] = {"billed_usd": round(e["billed"], 6), "unknown_reserved_usd": round(e["unknown"], 6),
                         "calls": e["calls"], "usage_from": " + ".join(used),
                         "calls_from_state_db": src["from_db"], "calls_from_committed_usage": src["from_committed"],
                         "committed_evidence": src["committed"] or None,
                         "committed_calls_also_in_state_db": src["in_both"],
                         "logged_cost_usd": round(e["logged"], 6), "calls_differing_from_logged_cost": e["differ_logged"],
                         "calls_priced_from_logged_cost": e["priced_from_log"], "unpriced_calls": e["unpriced_calls"],
                         "recorded_ledger_usd": ledger,
                         "matches_ledger": None if ledger is None else abs(amount - ledger) <= 1e-6}

    covered = {k for k, v in info.items() if v["state_db"] or v["committed"]}
    known = {}
    for d in sorted(p for p in root.iterdir() if p.is_dir()) if root.is_dir() else []:
        invs = _load_invocations(d)
        if not (invs or (d / "run_summary.json").exists() or (d / "state.sqlite").exists()):
            continue
        if invs and all(i.get("offline_stub") for i in invs):
            continue  # stub-only runs make no billed calls
        known[_run_key(d, root)] = invs
    prev = _previous_ledger(cost_dir)
    not_repro = {}
    for key in sorted((set(known) | set(prev) | set(unreadable)) - covered):
        if key in unreadable:
            reason = f"state.sqlite unreadable ({unreadable[key]}) and no committed per-call usage"
        elif key in known:
            reason = "run directory present, but no state.sqlite and no committed per-call usage"
        else:
            reason = "listed in the previous spend ledger; no run directory, state.sqlite or committed per-call usage"
        ledger = _ledger_usd(known.get(key))
        if ledger is not None:
            rec = {"recorded_usd": ledger, "recorded_in": f"{key}/invocations/*.json (run ledger)"}
        elif key in prev:
            rec = {"recorded_usd": prev[key]["usd"], "recorded_in": f"cost/project_spend.json ({prev[key]['at']})"}
        else:
            rec = {"recorded_usd": None, "recorded_in": "nothing saved: unknown"}
        not_repro[key] = {"reason": reason, **rec}

    settled = sum(e["billed"] for e in per_run.values())
    unknown = sum(e["unknown"] for e in per_run.values())
    logged = [e for e in per_run.values() if e["logged_n"]]
    return {
        "total_billed_usd": round(settled + unknown, 6),
        "settled_billed_usd": round(settled, 6), "unknown_reserved_usd": round(unknown, 6),
        "calls": len(calls), "runs": len(out_runs), "per_run": out_runs,
        "not_reproducible_offline": not_repro,
        "not_reproducible_recorded_usd": round(sum(v["recorded_usd"] or 0 for v in not_repro.values()), 6),
        "unresolved": {"unpriced_items": sorted(unpriced),
                       "unknown_outcome_calls_without_reservation": unresolved},
        "cross_check": {"calls_with_logged_cost": sum(e["logged_n"] for e in logged),
                        "logged_cost_usd": round(sum(e["logged"] for e in logged), 6),
                        "calls_differing_from_logged_cost": sum(e["differ_logged"] for e in logged),
                        "calls_in_state_db_and_committed_usage": sum(v["in_both"] for v in info.values()),
                        "calls_differing_between_sources": sum(v["differ"] for v in info.values()),
                        "duplicate_request_ids_across_state_dbs": dup_db},
        "evidence": {"runs_root": _rel(root), "state_dbs_read": dbs_read, "state_dbs_unreadable": unreadable,
                     "committed_files": [ev["label"] for ev in evidence]},
        "method": ("usage x rates.csv per billed-provider call, deduplicated by request_id; usage from runs/**/state.sqlite "
                   "when present, else committed per-call evidence (cost/refreshes/*_usage.csv + *_calls.jsonl, "
                   "cost/usage.csv + pilot_calls.jsonl); unknown-outcome calls count their reservation; stub and "
                   "Claude Pro (subscription) calls excluded"),
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


def _num(x, nd=1):
    return "-" if x is None else f"{x:,.{nd}f}"


def _pct(x, nd=2):
    return "-" if x is None else f"{x:.{nd}%}"


def _int(x):
    return "-" if x is None else f"{x:,}"


def _step(label, src, workers, enrich_s, wall_s, label_config, billed):
    """One measured step (pilot, refresh or comparison run) reduced to the figures the scaling decision uses."""
    st = src.get("stages") or {}
    prim, fb = st.get("enrich_primary", {}), st.get("fallback1", {})
    pool = [st[s] for s in ENRICH_POOL if s in st]
    caps = fallback_caps(label_config)
    distinct = src.get("distinct_texts")
    cap1 = caps[0] if caps else None
    return {"label": label, "run_dir": src.get("run_dir"), "rows": src.get("rows"), "distinct": distinct,
            "workers": workers, "label_config": label_config, "note": src.get("note"),
            "primary_attempts": prim.get("attempts", 0), "fallback1_attempts": fb.get("attempts", 0),
            "attempts": sum(s["attempts"] for s in pool), "transient": sum(s["transient_retries"] for s in pool),
            "invalid": sum(s["invalid_output_retries"] for s in pool), "rate_limited": sum(s.get("rate_limited", 0) for s in pool),
            "fb_routed": fb.get("unique_reviews", 0),
            "fb_share": fb.get("unique_reviews", 0) / prim["unique_reviews"] if prim.get("unique_reviews") else None,
            "fb_cap": cap1, "fb_at_cap": bool(cap1 and distinct and fb.get("unique_reviews", 0) >= math.floor(cap1 * distinct)),
            "billed": billed, "per_text": billed / distinct if billed is not None and distinct else None,
            "primary_per_text": prim.get("billed_usd_per_review"),
            "primary_cached_share": (prim["usage"].get("input_cached", 0) / sum(prim["usage"].get(i, 0) for i in ITEMS[:3])
                                     if prim.get("usage") and sum(prim["usage"].get(i, 0) for i in ITEMS[:3]) else None),
            "primary_latency": prim.get("mean_attempt_latency_s") or prim.get("mean_latency_s"),
            "enrich_s": enrich_s, "wall_s": wall_s, "unfinished": src.get("unfinished"),
            "utilisation": (src.get("enrich_pool") or {}).get("efficiency"),
            "fallback2_attempts": st.get("fallback2", {}).get("attempts", 0),
            "api_equivalent": round(sum(s["api_equivalent_usd"] for s in st.values()), 6)}


def _ref_step(r):
    return _step(r["label"], r, r.get("workers"), r.get("enrichment_stage_seconds"),
                 r.get("enrichment_wall_clock_s") or r.get("wall_clock_s"), r.get("label_config"), r.get("api_cost_usd"))


def _scaling_decision(L, meas, refreshes, comparisons, proj, a, spend):
    steps = []
    if meas and meas["runs"].get("cold") and not meas["offline_stub"]:
        c = meas["runs"]["cold"]
        steps.append(_step("pilot_100 (cold)", {"stages": c["stages"], "rows": c["rows"], "distinct_texts": c["distinct_texts"],
                                                  "run_dir": f"runs/{meas['pilot_id']}", "unfinished": c["unfinished"],
                                                  "enrich_pool": c.get("enrich_pool")},
                           c.get("workers"), c["stage_seconds"].get("enrich"), c["wall_clock_s"],
                           meas["settings"].get("label_config"), c["api_cost_usd"]))
    real_refs = [r for r in refreshes if not r.get("offline_stub")]
    steps += [_ref_step(r) for r in real_refs]
    if not steps:
        return
    ds = a.get("declared_scope") or {}
    final_ref = next((r for r in real_refs if r.get("rows") == ds.get("rows")), None)
    final = _ref_step(final_ref) if final_ref else None
    L += ["", "## Scaling decision", "",
          "The pipeline was scaled in measured steps, each a real billed run whose per-call evidence is saved in this folder; "
          "the estimate was refreshed after each step before the next, larger run was started explicitly. Every figure in "
          "this section is computed from those files (`pilot_calls.jsonl`, `refreshes/*_calls.jsonl`, `refreshes/*.json`, "
          "the comparison run's `state.sqlite` and `invocations/`) and `rates.csv`.", "",
          "### What each step showed", "",
          "| Step | Run | Rows | Distinct texts | Enrichment workers | Enrichment attempts (primary + fallback1) | "
          "Rate-limited (HTTP 429) | Transient retries | Invalid-output retries | Fallback1 share of primary-labelled texts (cap) | "
          "Billed | Billed per distinct text | Primary pass per distinct text | Enrichment stage s | Unfinished |",
          "|---|---|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|"]
    for s in steps:
        cap = f" (cap {_pct(s['fb_cap'], 1)}{', at cap' if s['fb_at_cap'] else ''})" if s["fb_cap"] is not None else ""
        L.append(f"| {s['label']} | `{s['run_dir']}` | {_int(s['rows'])} | {_int(s['distinct'])} | {s['workers']} | "
                 f"{s['attempts']:,} ({s['primary_attempts']:,} + {s['fallback1_attempts']:,}) | {s['rate_limited']} | "
                 f"{s['transient']} | {s['invalid']} | {s['fb_routed']:,} = {_pct(s['fb_share'])}{cap} | {fmt_usd(s['billed'], 6)} | "
                 f"{fmt_usd(s['per_text'], 8)} | {fmt_usd(s['primary_per_text'], 8)} | {_num(s['enrich_s'])} | {s['unfinished']} |")
    per_text = " -> ".join(f"{fmt_usd(s['per_text'], 8)} ({_int(s['distinct'])} texts)" for s in steps)
    prim = [s["primary_per_text"] for s in steps if s["primary_per_text"] is not None]
    L += ["", f"- **Cost per distinct text:** {per_text}."
          + (f" The primary pass alone stayed between {fmt_usd(min(prim), 8)} and {fmt_usd(max(prim), 8)} per distinct text at "
             "every size; the higher total per text of the final step is the fallback1 share, which rose when its cap was "
             "raised (next bullet), not a change in the primary pass." if prim else "")]
    fb_txt = "; ".join(f"{s['label']}: {_pct(s['fb_share'])} of a {_pct(s['fb_cap'], 1)} cap" + (" (cap reached)" if s["fb_at_cap"] else "")
                       for s in steps if s["fb_cap"] is not None)
    at_cap = [s for s in steps if s["fb_at_cap"]]
    raised = ""
    if at_cap and final and final["fb_cap"] and final["fb_cap"] > (at_cap[-1]["fb_cap"] or 0):
        allowed = math.floor(final["fb_cap"] * (final["distinct"] or 0))
        raised = (f" The cap was reached at {', '.join(s['label'] for s in at_cap)}, so it was raised to "
                  f"{_pct(final['fb_cap'], 1)} for the final run, which routed {final['fb_routed']:,} texts, under the "
                  f"{allowed:,} the cap allowed (why: `docs/model_choice.md`, \"10,000-review checkpoint and final run\").")
    L.append(f"- **Fallback rate:** {fb_txt}.{raised} Fallback2 (Claude Sonnet) was routed "
             f"{sum(s['fallback2_attempts'] for s in steps)} times in these runs.")
    retry_txt = "; ".join(f"{s['label']} ({s['workers']} worker{'s' if s['workers'] != 1 else ''}): {s['rate_limited']} rate-limited, "
                          f"{s['transient']} transient and {s['invalid']} invalid-output retries in {s['attempts']:,} attempts"
                          for s in steps)
    L.append(f"- **Retries:** {retry_txt}. Every step ended with 0 unfinished reviews." if all(s["unfinished"] == 0 for s in steps)
             else f"- **Retries:** {retry_txt}.")

    # worker comparison: refreshes plus declared comparison runs, by worker count
    cmp_rows = sorted([_ref_step(r) for r in real_refs] + [_ref_step(c) for c in comparisons if c.get("available")],
                      key=lambda s: (s["workers"] or 0, s["distinct"] or 0))
    missing = [c["run_dir"] for c in comparisons if not c.get("available")]
    if cmp_rows:
        L += ["", "### Worker comparison", "",
              "| Enrichment workers | Run | Distinct texts | Enrichment stage s | Distinct texts per enrichment second | "
              "Mean primary attempt latency s | Rate-limited (HTTP 429) | Primary pass per distinct text | Pool utilisation | Note |",
              "|---:|---|---:|---:|---:|---:|---:|---:|---:|---|"]
        for s in cmp_rows:
            tput = s["distinct"] / s["enrich_s"] if s["distinct"] and s["enrich_s"] else None
            L.append(f"| {s['workers']} | `{s['run_dir']}` | {_int(s['distinct'])} | {_num(s['enrich_s'])} | {_num(tput, 2)} | "
                     f"{_num(s['primary_latency'], 2)} | {s['rate_limited']} | {fmt_usd(s['primary_per_text'], 8)} | "
                     f"{_pct(s['utilisation'], 1)} | {s['note'] or ''} |")
        if missing:
            L.append(f"\nComparison runs not available in this checkout (no `state.sqlite` or `invocations/`): {missing}.")
        pairs = [(x, y) for i, x in enumerate(cmp_rows) for y in cmp_rows[i + 1:]
                 if x["distinct"] == y["distinct"] and x["label_config"] == y["label_config"] and x["workers"] != y["workers"]]
        for x, y in [(x, y) for x, y in pairs if x["enrich_s"] and y["enrich_s"]]:
            L.append(f"\n- **Controlled pair:** `{x['run_dir']}` ({x['workers']} worker) and `{y['run_dir']}` ({y['workers']} workers) "
                     f"enriched the same {x['distinct']:,} distinct texts cold with the same label config: enrichment took "
                     f"{_num(x['enrich_s'])} s vs {_num(y['enrich_s'])} s ({x['enrich_s'] / y['enrich_s']:.2f}x faster), "
                     f"primary pass {fmt_usd(x['primary_per_text'], 8)} vs {fmt_usd(y['primary_per_text'], 8)} per distinct text. "
                     f"The price difference is the provider's prompt cache, not concurrency: {_pct(x['primary_cached_share'], 1)} vs "
                     f"{_pct(y['primary_cached_share'], 1)} of the primary pass's input tokens were billed as cached reads (the "
                     "second run sent the same requests as the first).")
        big = [s for s in cmp_rows if not any(s is p for pr in pairs for p in pr)]
        if big:
            L.append(f"- The {' and '.join(str(s['workers']) for s in big)}-worker rows are different, larger inputs (with "
                     "different fallback caps), so their throughput is indicative only, not a controlled speedup.")
        top = cmp_rows[-1]
        if top["enrich_s"] and top["attempts"]:
            rpm = top["attempts"] / (top["enrich_s"] / 60)
            limit = _val(a["stages"]["enrich_primary"].get("provider_requests_per_minute_limit", {"value": None}))
            L.append(f"- At {top['workers']} workers the provider returned {top['rate_limited']} rate-limited responses "
                     f"({top['rate_limited'] / top['attempts']:.2%} of {top['attempts']:,} enrichment attempts), each retried with "
                     f"backoff; the run averaged {rpm:,.0f} enrichment requests per minute"
                     + (f" against a configured limit of {limit:,}" if limit else "")
                     + f" and kept the pool {_pct(top['utilisation'], 1)} busy. More workers shortened elapsed time without "
                       "raising the primary pass's unit price (column \"Primary pass per distinct text\").")

    est = (proj.get("declared_scope") or {}).get("estimates_by_step") or []
    if est:
        L += ["", "### Estimates before the final run", "",
              "Declared-scope estimate that each step's measurements give on their own, re-derived offline with today's "
              f"`assumptions.json` ({proj['workers']} workers, current caps). Later steps' measurements did not exist when "
              "an earlier step was evaluated.", "",
              "| Per-unit inputs from | Distinct texts measured | Fallback1 rate used | Enrichment-pool utilisation | "
              "Base, reuse | Conservative, reuse | Conservative, no reuse |", "|---|---:|---:|---:|---|---|---|"]
        for e in est:
            cells = [f"${e[k]['api_cost_usd']:,.2f} / {e[k]['elapsed_hours']} h" for k in
                     ("base_reuse", "conservative_reuse", "conservative_no_reuse")]
            after = " (after the run, for comparison)" if final and e["inputs_from"] == final["label"] else ""
            L.append(f"| {e['inputs_from']}{after} | {_int(e['distinct_texts'])} | {_pct(e['fallback1_rate'])} | {_pct(e['pool_efficiency'], 1)} | "
                     + " | ".join(cells) + " |")
        if final and final["wall_s"]:
            L.append(f"| **Measured: {final['label']}** | {_int(final['distinct'])} | {_pct(final['fb_share'])} | "
                     f"{_pct(final['utilisation'], 1)} | billed {fmt_usd(final['billed'], 6)}; {_num(final['wall_s'])} s = "
                     f"{final['wall_s'] / 3600:.2f} h over the enrichment invocations | | |")

    ctl = a["controls"]
    cap = float(ctl.get("project_cap_usd") or 0)
    L += ["", "### Decision", ""]
    if final:
        before = [e for e in est if e["inputs_from"] != final["label"]]
        fr = next(r for r in real_refs if r["label"] == final["label"])
        enr = [d for d in fr.get("invocations_detail") or [] if d.get("enrichment_calls")]
        other = [d for d in fr.get("invocations_detail") or [] if not d.get("enrichment_calls")]
        run_caps = sorted({d["budget_cap_usd"] for d in enr if d.get("budget_cap_usd") is not None})
        other_caps = sorted({d["budget_cap_usd"] for d in other if d.get("budget_cap_usd") is not None})
        denials = sum(d.get("budget_denials") or 0 for d in fr.get("invocations_detail") or [])
        caps_f = fallback_caps(fr.get("label_config"))
        if before:
            b = before[-1]
            lo, hi = b["base_reuse"]["api_cost_usd"], b["conservative_no_reuse"]["api_cost_usd"]
            within = [f"${x:.2f} per-run cap" for x in run_caps if hi <= x] + ([f"${cap:.2f} project cap"] if hi <= cap else [])
            L.append(f"- **Proceed.** The last step before the final run ({b['inputs_from']}) gives ${lo:,.2f} (base, reuse) to "
                     f"${hi:,.2f} (conservative, no reuse) for the declared scope"
                     + (f", within the {' and the '.join(within)}" if within else "")
                     + f"; the final run was then started explicitly (`{fr['run_dir']}`: {len(enr)} enrichment invocations, "
                       f"{len(other)} later regenerations).")
        L.append(f"- **Enrichment workers: {fr.get('workers')}**, the setting of the {len(enr)} invocations that made enrichment "
                 f"calls (later regenerations without enrichment used "
                 f"{', '.join(str(x) for x in sorted({d['workers'] for d in other})) or '-'}); "
                 f"`assumptions.json` `controls.max_workers` = {ctl['max_workers']}"
                 + ("" if ctl["max_workers"] == fr.get("workers") else " (**differs from the run**)") + ".")
        if caps_f:
            L.append(f"- **Fallback caps:** fallback1 {_pct(caps_f[0], 1)} of distinct texts"
                     + (f", fallback2 {_pct(caps_f[1], 2)}" if len(caps_f) > 1 and caps_f[1] is not None else "")
                     + f" (label config `{fr.get('label_config')}`); `controls.max_fallback1_fraction` = "
                       f"{_pct(float(ctl['max_fallback1_fraction']), 1)}.")
        L.append(f"- **Budget:** per-run cap {', '.join(f'${x:.2f}' for x in run_caps) or 'unknown'} for the enrichment invocations"
                 + (f" and {', '.join(f'${x:.2f}' for x in other_caps)} for the regenerations" if other_caps else "")
                 + f" (run ledger in `{fr['run_dir']}/invocations/*.json`), {denials} budget denials; project cap ${cap:.2f} "
                   f"(`controls.project_cap_usd`, `run.project_cap_usd` in `config/pipeline.toml`).")
        L.append(f"- **Outcome:** the final run billed {fmt_usd(final['billed'], 6)}; the whole project "
                 f"{fmt_usd(spend.get('total_billed_usd'), 6)} (spend section below), leaving "
                 f"{fmt_usd(cap - (spend.get('total_billed_usd') or 0), 6)} under the project cap.")
    full = proj["scenarios"]
    remaining = cap - (spend.get("total_billed_usd") or 0)
    over = [k for k, s in full.items() if s["api_cost_usd"] > remaining]
    f = proj["full_run"]
    L += ["", "### Scope", "",
          f"The declared {ds.get('rows', 0):,}-row scope with {ds.get('distinct_nonempty_texts', 0):,} distinct texts (source: "
          f"`{ds.get('source')}`) was chosen by the project owner and is the scope this project executed. The full-corpus "
          f"projection ({f['rows']:,} rows) in the next section is shown for reference only: it was not run. With the final "
          f"run's per-unit inputs at {proj['workers']} workers it estimates ${full['base_reuse']['api_cost_usd']:,.2f} (base, reuse) "
          f"to ${full['conservative_no_reuse']['api_cost_usd']:,.2f} (conservative, no reuse) and "
          f"{full['base_reuse']['elapsed_hours']} to {full['conservative_no_reuse']['elapsed_hours']} hours"
          + (f"; {len(over)} of {len(full)} scenarios ({', '.join(over)}) would exceed the {fmt_usd(remaining, 2)} left under "
             f"the project cap." if over else ".")]
    final_ref = next((r for r in real_refs if final and r["label"] == final["label"]), None)
    L += ["", "### Claude roles and the Claude Pro subscription", "",
          "The verify, group and memo roles (and fallback2) ran through `claude -p` on a flat-fee Claude Pro subscription. "
          "That subscription fee is not included in the per-call billed spend anywhere in this report and is not apportioned "
          "to calls. Instead, each Pro call's usage is priced at the reported model's Anthropic API rates and shown "
          "separately as the API-equivalent"
          + (f": {fmt_usd(final_ref['api_equivalent_subscription_usd'], 4)} for the final run" if final_ref else "")
          + (f", {fmt_usd(meas['runs']['cold']['api_equivalent_subscription_usd'], 6)} for the cold pilot"
             if meas and meas["runs"].get("cold") else "")
          + ". The course states that subscription access is not evidence that programmatic calls are free "
            "(`COST_CALCULATOR.md`), so the API-equivalent is always shown and never added to billed spend."]


def _projection_check_table(L, chk):
    m = chk["measured"]
    L += ["", f"### Projection check against the measured run ({chk['against']})", "",
          f"Base scenario with reuse at the projection's worker count vs the clock of the invocations that made enrichment "
          f"calls ({len(m['invocations'])} invocations, workers {m['workers']}); later invocations without enrichment are "
          "excluded. The enrichment-pool utilisation used by the projection is measured on this same run, so the enrichment "
          "row agrees by construction; verify, group, memo, code stages and the total are independent checks.", "",
          "| Stage | Projected s | Measured s | Projected / measured |", "|---|---:|---:|---:|"]
    for k, row in chk["rows"].items():
        meas_txt = _num(row["measured_s"])
        if k == "enrichment" and len(m.get("enrichment_by_invocation") or []) > 1:
            meas_txt += " (" + " + ".join(_num(x) for x in m["enrichment_by_invocation"]) + ")"
        L.append(f"| {k} | {_num(row['projected_s'])} | {meas_txt} | {_num(row['ratio'], 3)} |")


def render(meas, proj, a, R, refreshes, spend, sources_note, comparisons=()):
    L = ["# Cost and runtime calculator", "",
         f"Generated by `python3 cost/calculator.py` (offline replay) on {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}. "
         "No API key and no model call are needed to reproduce this page; every number below is recomputed from "
         "`usage.csv` / `refreshes/*_usage.csv` x `rates.csv`, and spend to date from the same committed per-call evidence "
         "plus any `runs/**/state.sqlite` present (deduplicated by request ID).", "",
         "Billing kinds: **billed API** = per-token charges on the OpenAI / TypeSafe accounts. **API-equivalent** = what "
         "calls made through the flat-fee Claude Pro subscription (`claude -p`) would have cost at Anthropic API rates; "
         "they are not billed per call, the subscription fee is not included in billed spend, and the API-equivalent is "
         "never added to billed spend.", ""]
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
              "Enrichment workers come from the invocations that made enrichment calls (the `invocations/*.json` files of the "
              "run); the number in brackets is the count of distinct worker IDs seen in those calls.", "",
              "| Checkpoint | Run | Rows | Distinct texts | Enrichment workers | Enrichment stage s | Wall clock s (all invocations) | "
              "Billed API cost | Billed / 1,000 rows | API-equivalent (Pro) | Fallback1 reviews | Verify reviews |",
              "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
        for r in refreshes:
            st = r["stages"]
            seen = (r.get("enrich_pool") or {}).get("worker_ids_seen_in_calls")
            L.append(f"| {r['label']} | `{r['run_dir']}` | {r['rows']:,} | {r['distinct_texts']:,} | {r.get('workers')}"
                     f"{f' ({seen})' if seen else ''} | {_num(r.get('enrichment_stage_seconds'), 3)} | "
                     f"{r.get('wall_clock_s')} | {fmt_usd(r['api_cost_usd'], 4)} | {fmt_usd(r['cost_per_1000_input_rows_usd'], 4)} | "
                     f"{fmt_usd(r['api_equivalent_subscription_usd'], 4)} | {st.get('fallback1', {}).get('unique_reviews', 0)} | "
                     f"{st.get('verify', {}).get('unique_reviews', 0)} |")
    p = proj
    _scaling_decision(L, meas, refreshes, comparisons, p, a, spend)
    pool = p.get("enrich_pool") or {}
    L += ["", "## Estimated runs (projections from the largest measured run)", "",
          f"Per-unit inputs from: **{p['inputs_measured_on'] or 'assumptions.json (no real measurement yet)'}**. "
          f"Budget for comparison: **${p['budget_usd']:,.2f}** | max workers {p['workers']} | enrichment-pool utilisation "
          + (f"{pool['efficiency']:.1%} (measured)" if pool.get("efficiency") else "100% (not measured)")
          + f" | output-token cap per LLM review "
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
              "| Stage | Reviews | Requests (incl. retries) | Billed | API-equivalent | Seconds | Inputs from |",
              "|---|---:|---:|---:|---:|---:|---|"]
        for stage, st in p["declared_scope"]["scenarios"]["base_reuse"]["stages"].items():
            L.append(f"| {stage} | {st['reviews']:,} | {st['requests']:,} | {fmt_usd(st['billed_usd'], 4)} | "
                     f"{fmt_usd(st['api_equivalent_usd'], 4)} | {st['seconds']} | {st['inputs_from']} |")
        if p["declared_scope"].get("projection_check"):
            _projection_check_table(L, p["declared_scope"]["projection_check"])
    f = p["full_run"]
    L += ["", f"### Full corpus (course projection, reference only): {f['rows']:,} rows", "",
          f"{f['nonempty_to_classify']:,} nonempty outputs, {f['empty_text_quarantines']} empty-text quarantines, "
          f"{f['distinct_nonempty_texts']:,} distinct nonempty texts with exact-text reuse (course contract; verified by "
          "full-file ingestion). Not run: the project executed the declared scope above.", ""]
    _scenario_table(L, p["scenarios"], p["budget_usd"])
    L += ["", "### Per-unit inputs used", "",
          "| Stage | Provider / model | Tier | Billing | Reviews per request | Attempts per unique review | Billed per review | "
          "Billed per call | API-equivalent per call | Mean latency s, succeeded calls | Latency s used (mean per attempt) | "
          "Pool utilisation | Source |",
          "|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|"]
    for stage, ps in p["per_stage_inputs"].items():
        L.append(f"| {stage} | {ps['provider']} / `{ps['model']}` | {ps['tier']} | {ps['billing']} | {ps['reviews_per_request']} | "
                 f"{_num(ps.get('attempts_per_review'), 4)} | {fmt_usd(ps['billed_per_review'], 8)} | {fmt_usd(ps['billed_per_call'], 6)} | "
                 f"{fmt_usd(ps['equiv_per_call'], 6)} | {ps['latency_succeeded_s'] if ps['latency_succeeded_s'] else '-'} | "
                 f"{ps['latency_s']} | "
                 f"{_pct(ps['pool_efficiency'], 1) if ps['pool_efficiency_source'].startswith('measured') else '-'} | "
                 f"{ps['source']} |")
    if p.get("primary_alternatives"):
        L += ["", "### Enrichment-stage alternatives (token estimates, enrichment only)", "",
              "| Option | Requests (full corpus) | Billed, full corpus | Billed, declared scope | Hours | Inputs from |",
              "|---|---:|---:|---:|---:|---|"]
        for o in p["primary_alternatives"]:
            L.append(f"| {o['name']} | {o['requests']:,} | {fmt_usd(o['api_cost_usd'], 2)} | "
                     f"{fmt_usd(o['declared_scope_api_cost_usd'], 2)} | {o['hours']} | {o['source']} |")
    _spend_section(L, a, spend)
    L += ["", f"Local compute: {p['local_compute_note']}. Not included in API cost.", "",
          "## Formulas", "",
          "- Measured: `item_cost = billed_units x usd_per_million / 1,000,000` at the tier the provider reported; items are "
          "mutually exclusive (input_uncached = input - cached - cache_write; input_cached; input_cache_write; output including "
          "reasoning). Subscription (`claude -p`) items cost $0 billed; their API-equivalent uses the reported model's API row.",
          "- Projected stage cost = projected reviews (or fixed calls for group/memo) x measured billed cost per unique review "
          "(or per call), which already contains the measured retries, cache hits and tier; the base scenario adds no extra "
          "retries when inputs are measured, the conservative one multiplies by (1 + transient + invalid-output retry rates) "
          "and by a token multiplier. Fallback rates are the measured share of reviews routed, capped by the declared maxima.",
          "- Projected seconds per stage = requests x mean attempt latency / (workers x pool utilisation), or requests / "
          "(provider requests-per-minute limit / 60) when that is slower; requests = reviews x measured attempts per unique "
          "review (retries and failed attempts included) and the latency averages every attempt. Pool utilisation = summed "
          "attempt durations of the enrichment stages / (workers x enrich-stage wall seconds) over the invocations that made "
          "enrichment calls. Stages are summed, plus code stages per 1,000 rows.",
          "- Spend to date = usage x rates per billed-provider call, each request ID counted once, plus the reservations of "
          "calls whose outcome is unknown (the same rule as the pipeline's project cap).",
          "- Doubling every API rate doubles billed totals; local compute and measured times do not change. Changing projected "
          "counts never changes the measured sections.", "",
          "## Price sources (cost/rates.csv)", "",
          "| Kind | Provider | Model | Tier | Item | USD per 1M | Checked | Source |", "|---|---|---|---|---|---:|---|---|"]
    for (prov, model, tier, item), r in sorted(R["rows"].items()):
        L.append(f"| {r.get('kind', 'api')} | {prov} | `{model}` | {tier} | {item} | {r['usd_per_million']} | {r['checked_date']} | "
                 f"{r['source_url']} |")
    L += ["", sources_note, ""]
    return "\n".join(L)


def _spend_section(L, a, spend):
    xc, ev = spend.get("cross_check") or {}, spend.get("evidence") or {}
    L += ["", "## Spending controls and spend to date", "",
          "- Per-run hard cap: `--budget-usd` (worst-case reservation before every attempt; admission stops when spent + unknown "
          "+ reserved + next would cross it).",
          f"- Project-wide hard cap: `run.project_cap_usd` = ${a['controls'].get('project_cap_usd', 0):.2f} summed over every run "
          "directory under `runs/`; a run's budget is lowered to what remains, and a run is refused when nothing remains.",
          "- Provider-side: prepaid OpenAI credit with auto-recharge off.", "",
          f"Billed spend to date, reproduced offline: **{fmt_usd(spend.get('total_billed_usd'), 6)}** over {spend.get('calls', 0):,} "
          f"billed-provider calls in {spend.get('runs', 0)} run directories (settled {fmt_usd(spend.get('settled_billed_usd'), 6)} "
          f"+ unknown-outcome reservations {fmt_usd(spend.get('unknown_reserved_usd'), 6)}; stub and Claude Pro calls excluded; "
          f"computed {spend.get('computed_at')}; `project_spend.json`). Each call is priced as usage x `rates.csv` and counted "
          "once by request ID, its usage taken from the run's `state.sqlite` when present and otherwise from the committed "
          "per-call evidence, so the total does not depend on the git-ignored final-run database.", "",
          f"Evidence: {ev.get('state_dbs_read', 0)} state databases read under `{ev.get('runs_root')}`; committed files "
          f"{', '.join(f'`{x}`' for x in ev.get('committed_files') or []) or 'none'}. Cross-checks: "
          f"{xc.get('calls_in_state_db_and_committed_usage', 0):,} calls are in both a state database and the committed evidence "
          f"({xc.get('calls_differing_between_sources', 0)} differ in usage or outcome); the costs logged at call time sum to "
          f"{fmt_usd(xc.get('logged_cost_usd'), 6)} ({xc.get('calls_differing_from_logged_cost', 0)} of "
          f"{xc.get('calls_with_logged_cost', 0):,} calls differ from usage x rates).", ""]
    unres = spend.get("unresolved") or {}
    if unres.get("unpriced_items") or unres.get("unknown_outcome_calls_without_reservation"):
        L += [f"**Unresolved (unknown, not zero):** unpriced items {unres.get('unpriced_items')}; "
              f"{unres.get('unknown_outcome_calls_without_reservation')} unknown-outcome calls without a saved reservation.", ""]
    nr = spend.get("not_reproducible_offline") or {}
    if nr:
        L += [f"**Not reproducible offline ({len(nr)} run directories, not included in the total; last recorded "
              f"{fmt_usd(spend.get('not_reproducible_recorded_usd'), 6)}):**", "",
              "| Run directory | Reason | Last recorded | Recorded in |", "|---|---|---:|---|"]
        for k, v in nr.items():
            L.append(f"| `{k}` | {v['reason']} | {fmt_usd(v.get('recorded_usd'), 6)} | {v.get('recorded_in')} |")
        L.append("")
    else:
        L += ["Not reproducible offline: none (every run directory with billed calls is covered by a state database or "
              "committed per-call evidence).", ""]
    if spend.get("per_run"):
        L += ["| Run directory | Calls (non-stub, billed providers) | Billed | Unknown (reserved) | Usage taken from | "
              "Committed per-call evidence | Run's own ledger (invocations) |", "|---|---:|---:|---:|---|---|---|"]
        for k, v in spend["per_run"].items():
            led = ("-" if v.get("recorded_ledger_usd") is None else
                   f"{fmt_usd(v['recorded_ledger_usd'], 6)} ({'matches' if v.get('matches_ledger') else '**differs**'})")
            L.append(f"| `{k}` | {v['calls']} | {fmt_usd(v['billed_usd'], 6)} | {fmt_usd(v['unknown_reserved_usd'], 6)} | "
                     f"{v.get('usage_from') or '-'} | {', '.join(f'`{x}`' for x in v.get('committed_evidence') or []) or '-'} | {led} |")


def _run_dir_source(run_key, runs_root, R, note=None):
    """A run that is not a refresh (e.g. a worker comparison), read from its state database and invocations."""
    d = _resolve_run_dir(run_key, runs_root)
    invs, db = _load_invocations(d), d / "state.sqlite"
    base = {"label": Path(run_key).name, "run_dir": run_key, "note": note, "available": False}
    if not invs or not db.exists():
        return base
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        try:
            calls, usage_rows = _call_rows(con, None)
        finally:
            con.close()
    except (sqlite3.Error, IndexError, KeyError):
        return base
    stages, _ = _stage_stats(R, usage_rows, calls)
    summ = invocation_summary(invs, calls)
    res = invs[-1].get("results") or {}
    billed = sum(s["billed_usd"] for s in stages.values())
    return {**base, "available": True, "rows": (res.get("scope") or {}).get("unique_ids"),
            "distinct_texts": (res.get("scope") or {}).get("distinct_nonempty_texts"), "unfinished": res.get("unfinished"),
            "label_config": invs[-1].get("label_config"), "stages": stages, "api_cost_usd": round(billed, 8),
            "enrich_pool": _enrich_pool(summ["invocations_detail"], calls), **summ}


def replay(rates_path, assumptions_path, pilot_dir, out_dir, budget=None, runs_root=None):
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
    root = Path(runs_root) if runs_root else default_runs_root()
    # Spend to date is a project-level fact: always from the runs root plus the evidence committed in cost/,
    # never from a scratch pilot folder (whose copies may rename stub models).
    spend = project_spend(root, COST_DIR, rates_path)
    comparisons = [_run_dir_source(c["run_dir"], root, R, c.get("note"))
                   for c in (a.get("scaling_decision") or {}).get("worker_comparison_runs", [])]
    out_dir = Path(out_dir)
    if Path(pilot_dir).resolve() == COST_DIR.resolve() and out_dir.resolve() == COST_DIR.resolve():
        # only the default replay into cost/ updates the committed ledger; any other --out-dir leaves it untouched
        (COST_DIR / "project_spend.json").write_text(json.dumps(spend, indent=2) + "\n", encoding="utf-8")
    md = render(meas, proj, a, R, refreshes, spend, note, comparisons)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.md").write_text(md, encoding="utf-8")
    (out_dir / "report.json").write_text(json.dumps({"measured": meas, "refreshes": refreshes, "projection": proj,
                                                     "scaling": scaling, "worker_comparison": comparisons, "spend": spend},
                                                    indent=2, default=str) + "\n", encoding="utf-8")
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
               "api_equivalent_usd_logged": get("api_equiv_usd"), "reserved_usd": get("reserved_usd")}
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
    invs = _load_invocations(run_dir)
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
    summ = invocation_summary(invs, calls)  # workers = the enrichment invocations' setting, not the latest invocation's
    ref = {"label": args.label, "run_dir": str(run_dir.relative_to(ROOT)), "offline_stub": bool(last.get("offline_stub")),
           "rows": res.get("scope", {}).get("unique_ids"), "distinct_texts": res.get("scope", {}).get("distinct_nonempty_texts"),
           "completed": res.get("completed"), "quarantined": res.get("quarantined"), "unfinished": res.get("unfinished"),
           "workers": summ.pop("workers"), "invocations": len(invs), "wall_clock_s": round(sum(walls), 3),
           "label_config": last.get("label_config"), "saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           **summ}
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
    r.add_argument("--runs-root", default=None,
                   help="run directories to read spend from (default: $INSIGHT_RUNS_ROOT or <repo>/runs)")
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
    meas, proj = replay(args.rates, args.assumptions, args.pilot_dir, args.out_dir, args.budget_usd, args.runs_root)
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
    spend = json.loads((Path(args.out_dir) / "report.json").read_text(encoding="utf-8")).get("spend") or {}
    nr = spend.get("not_reproducible_offline") or {}
    print(f"spend to date (reproduced offline): ${spend.get('total_billed_usd', 0):,.6f} over {spend.get('runs', 0)} run directories"
          + (f"; NOT reproducible offline: {sorted(nr)}" if nr else ""))
    same = Path(args.out_dir).resolve() == COST_DIR.resolve() and Path(args.pilot_dir).resolve() == COST_DIR.resolve()
    print(f"wrote {Path(args.out_dir) / 'report.md'}" + (" and cost/project_spend.json" if same else
                                                        " (cost/project_spend.json left unchanged)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())

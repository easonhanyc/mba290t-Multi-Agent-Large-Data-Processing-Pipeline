"""Command line: python -m insight <command> ...

  run        ingest -> enrich -> verify -> group -> rank -> memo -> export (resumable)
  preflight  ingest + render every request and estimate tokens/cost; no model calls, no keys
  rank       rebuild ranking from saved records + membership (no model calls); --check compares
  export     rewrite grading/ and internal exports from saved state
  status     counts, spend and invocation history for a run directory
  planted-error   corrupt one label in a test copy and show the verifier comparison flags it
  golden     score saved predictions against a human-labelled golden CSV
  render-prompts  regenerate prompts/jev_enrich_v1.json and prompts/decisions_crosscheck_v1.json
  label-golden    terminal labeller for the golden 50 (a person labels; saves after every review)
  trace      one review traced source -> enrich -> verify -> membership -> rank -> memo (saved artifacts only)
  analyze    recompute descriptive trends/intervals/robustness from saved outputs (no model calls)

Live model calls require --allow-paid and API keys in the environment. --offline-stub runs
the same code against a local test server (model IDs become stub-*; nothing is real).
"""

import argparse
import csv
import fcntl
import json
import os
import signal
import sys
from collections import Counter
from pathlib import Path

from . import config as config_mod
from .control import Context, RateLimiter, SpendLedger
from .ingest import InputMismatch, ingest
from .store import Store
from .util import (PROJECT_ROOT, atomic_write_json, load_dotenv, monotonic, new_run_id, read_json, rel, utc_now)

STAGES = ("ingest", "enrich", "verify", "group", "rank", "memo", "export")
MODEL_STAGES = {"enrich", "verify", "group", "memo"}


def _say(msg):
    print(msg, flush=True)


def _parse_value(raw):
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def project_spend(exclude_run_dir=None, runs_root=None):
    """Billed API spend recorded in every run directory under runs/ (stub and subscription calls excluded).

    Settled costs plus the reservations of calls whose outcome/charge is unknown. Used to enforce
    run.project_cap_usd across all runs, retries and versions of the project.
    """
    import sqlite3
    root = Path(runs_root or os.environ.get("INSIGHT_RUNS_ROOT") or PROJECT_ROOT / "runs")
    total, per_run = 0.0, {}
    for db in sorted(root.glob("**/state.sqlite")):
        if exclude_run_dir and db.parent.resolve() == Path(exclude_run_dir).resolve():
            continue
        try:
            con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
            cols = {r[1] for r in con.execute("PRAGMA table_info(calls)")}
            billing = "AND COALESCE(billing, 'api') != 'subscription'" if "billing" in cols else ""
            row = con.execute(
                "SELECT COALESCE(SUM(CASE WHEN outcome IN ('succeeded','failed') THEN COALESCE(cost_usd,0) ELSE 0 END),0),"
                " COALESCE(SUM(CASE WHEN outcome IN ('unknown','dispatched') THEN reserved_usd ELSE 0 END),0) "
                f"FROM calls WHERE model NOT LIKE 'stub-%' {billing}").fetchone()
            con.close()
        except sqlite3.Error as e:  # fail closed: an unreadable run must never count as $0
            raise RuntimeError(f"cannot read spend from {db}: {e}") from e
        amount = float(row[0]) + float(row[1])
        if amount:
            per_run[rel(db.parent)] = round(amount, 6)
            total += amount
    return round(total, 8), per_run


def _load_cfg(args):
    overrides = {}
    for item in getattr(args, "set", None) or []:
        if "=" not in item:
            raise SystemExit(f"--set expects KEY=VALUE, got {item!r}")
        key, raw = item.split("=", 1)
        overrides[key.strip()] = _parse_value(raw.strip())
    if getattr(args, "workers", None):
        overrides["run.workers"] = int(args.workers)
    cfg = config_mod.load(args.config, overrides, offline_stub=getattr(args, "offline_stub", False))
    cfg.data["paths"]["checker_abs"] = str(config_mod.project_path(cfg.data["paths"]["checker"]))
    if getattr(args, "timeout_s", None):
        for p in cfg.data["providers"].values():
            p["timeout_s"] = float(args.timeout_s)
        for section in (cfg.data["enrich"]["llm"], cfg.data["enrich"]["fallback1"], cfg.data["enrich"]["fallback2"]):
            if "timeout_s" in section:
                section["timeout_s"] = float(args.timeout_s)
    return cfg


def _load_cfg_for_run(args):
    """Read-only commands: the configuration the run itself saved (unless --config is given explicitly)."""
    run_dir = Path(args.run_dir)
    snap = None
    if (run_dir / "state.sqlite").exists():
        snap = Store(run_dir).get_meta("config_snapshot")
    if snap and not args.config:
        cfg = config_mod.Config(snap["data"], run_dir / "state.sqlite", offline_stub=getattr(args, "offline_stub", False))
        cfg.data["paths"]["checker_abs"] = str(config_mod.project_path(cfg.data["paths"]["checker"]))
    else:
        cfg = _load_cfg(args)
    if snap:
        cfg.pin(snap.get("label_config"), snap.get("stage_configs"))
    return cfg


def _snapshot(store, cfg, run_id, status, stop_reason):
    ids = store.completed_ids(cfg.label_config())
    path = store.run_dir / "checkpoints" / f"{run_id}.json"
    atomic_write_json(path, {"run_id": run_id, "written_at": utc_now(), "status": status, "stop_reason": stop_reason,
                             "label_config": cfg.label_config(), "completed_ids": ids}, indent=None)
    return len(ids)


def call_summary(store, run_id=None):
    out = {}
    for c in store.iter_calls(run_id):
        key = c["role"] + ("" if c["tier"] in (None, c["role"]) else f":{c['tier']}")
        s = out.setdefault(key, Counter())
        s["attempts"] += 1
        s[c["outcome"]] += 1
        s["input_tokens"] += c["input_tokens"] or 0
        s["output_tokens"] += c["output_tokens"] or 0
        s["cached_input_tokens"] += c["cached_input_tokens"] or 0
        s["reasoning_tokens"] += c["reasoning_tokens"] or 0
        s["retries"] += (c["attempt"] or 1) > 1
        s["invalid_output_retries"] += (c["task_attempt"] or 1) > 1
        s["cost_usd_micro"] += round((c["cost_usd"] or 0) * 1_000_000)
    return {k: {**{kk: vv for kk, vv in v.items() if kk != "cost_usd_micro"},
                "cost_usd": round(v["cost_usd_micro"] / 1_000_000, 6)} for k, v in out.items()}


def result_summary(store, cfg):
    lc = cfg.label_config()
    counts = Counter()
    for r in store.result_counts(lc):
        counts[f"{r['status']}:{r['labeled_by'] or 'rule'}"] += r["n"]
    q = lambda sql: store.conn.execute(sql, (lc,)).fetchone()[0]
    scope = store.scope_counts()
    completed = q("SELECT COUNT(*) FROM results WHERE label_config=? AND status='completed'")
    quarantined = q("SELECT COUNT(*) FROM results WHERE label_config=? AND status='quarantined'")
    return {
        "scope": scope,
        "completed": completed,
        "quarantined": quarantined,
        "quarantined_empty_text": q("SELECT COUNT(*) FROM results WHERE label_config=? AND reason='empty_review_text'"),
        "unfinished": scope["unique_ids"] - completed - quarantined,
        "exact_text_cache_reuses": q("SELECT COUNT(*) FROM results WHERE label_config=? AND cache_source_id IS NOT NULL"),
        "needs_review": q("SELECT COUNT(*) FROM results WHERE label_config=? AND status='completed' AND needs_review=1"),
        "by_status_and_tier": dict(counts),
    }


def _config_summary(cfg):
    """Per-stage processing tier and batch size (cost-relevant settings shown by the calculator)."""
    e = cfg["enrich"]
    llm = e["backend"] in ("llm", "hybrid")
    return {
        "enrich_primary": {"service_tier": e["llm"].get("service_tier", "standard") if llm else "standard",
                           "batch": f"{e['llm_batch_size']} reviews/request" if llm else "1 review/request"},
        "crosscheck": {"service_tier": "standard", "batch": "1 review/request",
                       "fields": ",".join(e["crosscheck"]["fields"]) if e["backend"] == "hybrid" else "off"},
        "fallback1": {"service_tier": e["fallback1"].get("service_tier", "standard"), "batch": "1 review/request"},
        "fallback2": {"service_tier": e["fallback2"].get("service_tier", "subscription"
                                                         if cfg.provider(e["fallback2"]["provider"])["kind"] == "claude_code"
                                                         else "standard"), "batch": "1 review/request"},
        "verify": {"service_tier": "subscription" if cfg.provider(cfg["verify"]["provider"])["kind"] == "claude_code"
                   else "standard", "batch": f"{cfg['verify'].get('batch_size', 1)} reviews/request"},
        "group": {"service_tier": "subscription" if cfg.provider(cfg["group"]["provider"])["kind"] == "claude_code"
                  else "standard", "batch": f"<= {cfg['group']['evidence_per_issue']} quotes/request"},
        "memo": {"service_tier": "subscription" if cfg.provider(cfg["memo"]["provider"])["kind"] == "claude_code"
                 else "standard", "batch": "aggregates + evidence pack"},
    }


def cmd_run(args):
    cfg = _load_cfg(args)
    stages = [s.strip() for s in args.stages.split(",")] if args.stages else list(STAGES)
    for s in stages:
        if s not in STAGES:
            raise SystemExit(f"unknown stage {s!r}; choose from {', '.join(STAGES)}")
    run_dir = Path(args.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    lock = open(run_dir / ".lock", "w")
    try:  # one invocation per run directory: a second one would pay for the same pending reviews
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        _say(f"Another invocation is already running on {rel(run_dir)}; wait for it or use a different --run-dir.")
        return 2
    store = Store(run_dir)
    run_id = new_run_id()
    lc = cfg.label_config()
    other = [r[0] for r in store.conn.execute("SELECT DISTINCT label_config FROM results WHERE label_config != ?", (lc,))]
    if other and not args.allow_config_change:
        _say(f"{rel(run_dir)} already holds results under a different label_config:\n  {other[0]}\nnow:\n  {lc}\n"
             "Label-affecting settings changed (model, effort, prompt, thresholds or fallback caps). Use a new --run-dir "
             "so the export stays one configuration, or pass --allow-config-change to keep both in this directory.")
        return 2
    reconciled = store.reconcile_dispatched(run_id)
    store.set_meta("config_snapshot", {"data": cfg.data, "label_config": lc,
                                       "stage_configs": {st: cfg.stage_config(st) for st in ("verify", "group", "memo")},
                                       "saved_at": utc_now()})
    # "initial" only for the first invocation that does enrichment work under this label_config;
    # any later one continues saved work (completed, staged or attempted) and is a "resume".
    prior = store.conn.execute("SELECT 1 FROM calls WHERE role='enrich' AND label_config=? LIMIT 1", (lc,)).fetchone()
    phase = "resume" if (prior or store.completed_ids(lc)) else "initial"
    needs_models = bool(MODEL_STAGES & set(stages))
    stub = registry = None
    from .providers import ProviderRegistry, Rates
    rates = Rates(shadow_stub=args.shadow_rates)
    if needs_models:
        if not cfg.offline_stub and not args.allow_paid:
            _say("Refusing to make live model calls without --allow-paid (and a budget). "
                 "Use --offline-stub for a no-cost plumbing run, or `python -m insight preflight` for estimates.")
            return 2
        base_urls = None
        if cfg.offline_stub:
            from .stub import StubServer, parse_faults
            stub = StubServer(faults=parse_faults(args.stub_faults), timeout_sleep=args.stub_timeout_sleep).start()
            stub.capture_bodies = bool(os.environ.get("INSIGHT_STUB_CAPTURE"))
            base_urls = stub.base_urls()
        registry = ProviderRegistry(cfg, base_urls)
        missing = registry.missing_keys(set(stages))
        if missing:
            _say(f"Missing API keys: {', '.join(missing)}. Put them in final-assignment/.env (names in .env.example).")
            return 2
        not_ready = registry.readiness_problems(set(stages))
        if not_ready:
            _say("Provider not ready: " + "; ".join(not_ready))
            return 2
        for role in ("enrich_primary", "crosscheck", "fallback1", "fallback2", "verify", "group", "memo"):
            r = cfg.role_settings(role)
            if role.startswith("fallback") and not (r["enabled"] and r["max_fraction"] > 0):
                continue
            if role == "crosscheck" and not r["enabled"]:
                continue
            if not rates.has(r["provider"], r["model"]):
                _say(f"No price for {r['provider']}/{r['model']} in cost/rates.csv; the spend cap cannot be enforced.")
                return 2
    budget = float(args.budget_usd if args.budget_usd is not None else cfg["run"]["budget_usd"])
    if needs_models and not cfg.offline_stub and budget <= 0:
        _say("A positive --budget-usd is required for live calls.")
        return 2
    spent, unknown = store.spend_totals()
    project = None
    if needs_models and not cfg.offline_stub:
        # Project-wide hard cap: this run may only use what other runs have left under project_cap_usd.
        runs_root = Path(os.environ.get("INSIGHT_RUNS_ROOT") or PROJECT_ROOT / "runs").resolve()
        if runs_root not in run_dir.resolve().parents:
            _say(f"Refusing live calls: the run directory must be under {rel(runs_root)} so the project cap counts it.")
            return 2
        runs_root.mkdir(parents=True, exist_ok=True)
        project_lock = open(runs_root / ".live.lock", "w")  # one live run at a time: the cap is read once at start
        try:
            fcntl.flock(project_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            _say("Refusing: another live run is in progress (runs/.live.lock); the project cap allows one at a time.")
            return 2
        cap = float(cfg["run"].get("project_cap_usd", 0) or 0)
        try:
            others, per_run = project_spend(exclude_run_dir=run_dir)
        except RuntimeError as e:
            _say(f"Refusing: {e}")
            return 2
        allowed = max(0.0, cap - others) if cap else budget
        project = {"project_cap_usd": cap, "other_runs_billed_usd": others, "per_run": per_run,
                   "requested_budget_usd": budget, "effective_budget_usd": round(min(budget, allowed), 8)}
        if cap and allowed < budget:
            _say(f"[run] project cap ${cap:.2f}: other runs already used ${others:.4f}; this run's budget is lowered "
                 f"from ${budget:.2f} to ${allowed:.4f}")
            budget = allowed
        if budget <= spent + unknown:
            _say(f"Refusing: the project spending cap (${cap:.2f}) leaves no budget for this run "
                 f"(other runs ${others:.4f}, this run ${spent + unknown:.4f}).")
            return 2
    ledger = SpendLedger(budget, spent, unknown)
    limiter = RateLimiter({n: (p["requests_per_minute"], p["tokens_per_minute"]) for n, p in cfg["providers"].items()})
    ctx = Context(store, cfg, rates, limiter, ledger, run_id, phase)

    interrupts = {"n": 0}

    def on_signal(signum, frame):
        interrupts["n"] += 1
        if interrupts["n"] == 1:
            _say(f"\n[{signal.Signals(signum).name}] stopping: no new requests; finishing in-flight work and saving. "
                 "Press Ctrl-C again to exit immediately (in-flight calls are reconciled on the next run).")
            ctx.request_stop(f"interrupted ({signal.Signals(signum).name})")
        else:
            os._exit(130)

    old = {s: signal.signal(s, on_signal) for s in (signal.SIGINT, signal.SIGTERM)}
    store.start_invocation({"run_id": run_id, "started_at": utc_now(), "command": " ".join(sys.argv[1:]),
                            "phase": phase, "status": "running", "label_config": lc, "workers": int(cfg["run"]["workers"]),
                            "budget_usd": budget, "offline_stub": int(cfg.offline_stub)})
    _say(f"[run] {run_id} | phase {phase} | run dir {rel(run_dir)} | budget ${budget:.2f} "
         f"(already spent ${spent:.6f}, unknown ${unknown:.6f}) | {'OFFLINE STUB' if cfg.offline_stub else 'LIVE'}")
    if reconciled:
        _say(f"[run] reconciled {reconciled} call(s) left in flight by a previous process -> outcome 'unknown'")
    t_start, stage_s, out = monotonic(), {}, {}
    status = "completed"
    try:
        t = monotonic()
        report = ingest(store, args.input, cfg, run_id, full_path=getattr(args, 'full', None))
        stage_s["ingest"] = round(monotonic() - t, 3)
        c = report["counts"]
        _say(f"[ingest] {c['records']} rows | {c['nonempty_to_classify']} nonempty | {c['empty_review_text']} empty | "
             f"{c['distinct_nonempty_texts']} distinct texts ({c['exact_text_cache_aliases']} exact-text reuses) | "
             f"{c['missing_app_version']} missing app_version")
        if "enrich" in stages:
            from .enrich import EnrichStage
            t = monotonic()
            out["enrich"] = EnrichStage(store, cfg, registry, ctx, stop_after=args.stop_after, log=_say).run()
            stage_s["enrich"] = round(monotonic() - t, 3)
        downstream_ok = not ctx.stop_reason and result_summary(store, cfg)["unfinished"] == 0
        if not downstream_ok and any(s in stages for s in ("verify", "group", "rank", "memo")):
            _say(f"[run] enrichment incomplete ({ctx.stop_reason or 'pending reviews remain'}); "
                 "skipping verify/group/rank/memo until a resumed run finishes it")
        if downstream_ok and "verify" in stages:
            from .verify import VerifyStage
            t = monotonic()
            out["verify"] = VerifyStage(store, cfg, registry, ctx, log=_say).run()
            stage_s["verify"] = round(monotonic() - t, 3)
        if downstream_ok and "group" in stages and not ctx.stop_reason:
            from .group import GroupStage
            t = monotonic()
            out["group"] = GroupStage(store, cfg, registry, ctx, log=_say).run()
            stage_s["group"] = round(monotonic() - t, 3)
        if downstream_ok and "rank" in stages and not ctx.stop_reason:
            from .rank import run_rank
            t = monotonic()
            out["rank"] = run_rank(store, lc, log=_say)
            from .analysis import run_analysis
            out["analysis"] = {k: v for k, v in run_analysis(store, cfg, log=_say).items() if k in ("robustness",)}
            stage_s["rank"] = round(monotonic() - t, 3)
        if downstream_ok and "memo" in stages and not ctx.stop_reason:
            t = monotonic()
            out["memo"] = _memo(store, cfg, registry, ctx, args)
            stage_s["memo"] = round(monotonic() - t, 3)
        if ctx.stop_reason:
            status = "interrupted" if ctx.stop_reason.startswith("interrupted") else "stopped"
        elif not downstream_ok:
            status = "incomplete"
    except InputMismatch as e:
        _say(f"[run] {e}")
        status, ctx.stop_reason = "failed", str(e)
    except BaseException as e:
        status, ctx.stop_reason = "failed", f"{type(e).__name__}: {e}"
        raise
    finally:
        for s, h in old.items():
            signal.signal(s, h)
        wall = round(monotonic() - t_start, 3)
        n_completed = _snapshot(store, cfg, run_id, status, ctx.stop_reason)
        if "export" in stages and status != "failed":
            from .export import export
            t = monotonic()
            out["export"] = export(store, cfg, unfinished_reason=f"run stopped ({ctx.stop_reason or 'incomplete'})")
            stage_s["export"] = round(monotonic() - t, 3)
            wall = round(monotonic() - t_start, 3)
        summary = {
            "run_id": run_id, "phase": phase, "status": status, "stop_reason": ctx.stop_reason,
            "offline_stub": cfg.offline_stub, "input": store.get_meta("input"), "label_config": lc,
            "stage_configs": {s: cfg.stage_config(s) for s in ("verify", "group", "memo")},
            "models": {r: cfg.role_settings(r) for r in ("enrich_primary", "crosscheck", "fallback1", "fallback2", "verify",
                                                         "group", "memo")},
            "config_summary": _config_summary(cfg),
            "project_spend": project,
            "workers": int(cfg["run"]["workers"]), "wall_clock_s": wall, "stage_seconds": stage_s,
            "results": result_summary(store, cfg), "completed_ids_saved": n_completed,
            "calls_this_invocation": call_summary(store, run_id), "calls_all_invocations": call_summary(store),
            "ledger": ledger.snapshot(), "reconciled_unknown_calls": reconciled, "stages": out,
            "finished_at": utc_now(),
        }
        atomic_write_json(run_dir / "invocations" / f"{run_id}.json", summary)
        history = [read_json(p) for p in sorted((run_dir / "invocations").glob("*.json"))]
        history.sort(key=lambda h: h.get("finished_at", ""))
        atomic_write_json(run_dir / "run_summary.json", {"latest": summary, "history": [
            {k: h.get(k) for k in ("run_id", "phase", "status", "stop_reason", "wall_clock_s", "completed_ids_saved")}
            for h in history]})
        store.finish_invocation(run_id, {"ended_at": utc_now(), "status": status, "stop_reason": ctx.stop_reason,
                                         "summary": json.dumps({"wall_clock_s": wall, "stage_seconds": stage_s})})
        if stub:
            if stub.capture_bodies:  # test hook: every request body the stub received
                Path(os.environ["INSIGHT_STUB_CAPTURE"]).write_text("\n".join(stub.bodies), encoding="utf-8")
            stub.stop()
        _say(f"[run] {status}{' (' + ctx.stop_reason + ')' if ctx.stop_reason else ''} in {wall:.1f}s | "
             f"completed {summary['results']['completed']} | quarantined {summary['results']['quarantined']} | "
             f"unfinished {summary['results']['unfinished']} | spend ${ledger.snapshot()['spent_usd']:.6f}")
    return {"completed": 0, "incomplete": 3, "stopped": 3, "interrupted": 130, "failed": 1}[status]


def _memo(store, cfg, registry, ctx, args):
    from .memo import MemoStage
    run_dir = store.run_dir
    with open(run_dir / "ranking.csv", encoding="utf-8") as f:
        ranking = [{**r, "rank": int(r["rank"]), "complaint_count": int(r["complaint_count"]),
                    "severity_sum": int(r["severity_sum"]), "priority_score": int(r["priority_score"])}
                   for r in csv.DictReader(f)]
    issues_doc = read_json(run_dir / "issues.json")
    areas_doc = read_json(run_dir / "area_rollup.json")
    res = result_summary(store, cfg)
    vrep = run_dir / "verification" / "report.json"
    v = read_json(vrep) if vrep.exists() else None
    n = res["scope"]["unique_ids"]
    input_meta = store.get_meta("input")
    full = store.get_meta("full_input")
    if n == 660622:
        scope_name = f"the full corpus ({input_meta['path']})"
    elif full and n >= 100000:
        scope_name = (f"the declared analysis scope: {n:,} reviews ({Path(input_meta['path']).name}, a deterministic uniform "
                      f"sample of the 660,622-review corpus plus every empty-text row)")
    else:
        scope_name = f"a {n}-review development checkpoint ({Path(input_meta['path']).name}), not the full corpus"
    scope = [("Reviews in scope (unique IDs ingested)", n, "ingestion_report.json"),
             ("Completed classifications", res["completed"], "grading/records.jsonl"),
             ("Quarantined: empty text", res["quarantined_empty_text"], "quarantine.jsonl"),
             ("Quarantined: other reasons", res["quarantined"] - res["quarantined_empty_text"], "quarantine.jsonl"),
             ("Unfinished", res["unfinished"], "run_summary.json"),
             ("Completed records flagged needs_review", res["needs_review"], "enriched.jsonl"),
             ("Complaint and cancellation records ranked", sum(r["complaint_count"] for r in ranking), "membership.csv")]
    if v and v["compared"]:
        scope += [("Verification sample compared", v["compared"], "verification/report.json"),
                  ("Verifier topic agreement (rate)", v["agreement"]["topic"]["rate"], "verification/report.json"),
                  ("Verifier intent agreement (rate)", v["agreement"]["intent"]["rate"], "verification/report.json"),
                  ("Verifier exact severity agreement (rate)", v["agreement"]["severity"]["rate"], "verification/report.json")]
    mandatory = [
        f"Counts describe the labeled reviews in {scope_name}: self-selected public app reviews, not a customer "
        "population. They carry no revenue, plan tier or confirmed cancellations, so revenue at risk cannot be computed.",
        "Cancellation language is expressed intent, not observed churn; nothing here estimates a causal effect on retention.",
        "Star ratings and helpful votes were not used to classify; severity is judged from the text under the shared rubric.",
        f"{res['needs_review']} completed records are flagged needs_review, {res['quarantined']} are quarantined and "
        f"{res['unfinished']} are unfinished; the golden-set comparison (human labels) is "
        + ("reported separately." if (PROJECT_ROOT / "evals" / "golden" / "results.json").exists() else "still pending."),
    ]
    if full and n != 660622:
        mandatory.append("The analysis covers a uniform random sample of the corpus, not every review; shares carry sampling "
                         "error (intervals shown) and the 460,609 out-of-scope reviews were ingested but not classified.")
    meta = {"scope": scope_name, "run_id": ctx.run_id, "input": input_meta["path"], "input_sha256": input_meta["sha256"],
            "offline_stub": cfg.offline_stub, "mandatory_limitations": mandatory}
    analysis = {}
    adir = run_dir / "analysis"
    for key, name in (("period_comparison", "period_comparison.json"), ("area_intervals", "area_intervals.json"),
                      ("spikes", "spike_months.json"), ("robustness", "robustness.json")):
        if (adir / name).exists():
            analysis[key] = read_json(adir / name)
    return MemoStage(store, cfg, registry, ctx, log=_say).run(ranking, issues_doc, areas_doc, scope, meta, analysis)


def cmd_preflight(args):
    """Ingest and render every request without sending it; estimate tokens per role."""
    cfg = _load_cfg(args)
    store = Store(Path(args.run_dir))
    run_id = new_run_id()
    report = ingest(store, args.input, cfg, run_id)
    from . import prompts
    from .segment import segment_spans
    lc = cfg.label_config()
    pending = store.pending_representatives(lc)
    e = cfg["enrich"]
    sizes = []
    if e["backend"] in config_mod.CLASSIFIER_BACKENDS:
        q = prompts.load_jev_questions(config_mod.project_path(e[e["backend"]]["questions"]))
        for r in pending:
            segs = [r["review_text"][s:t] for s, t in segment_spans(r["review_text"])]
            sizes.append(len(json.dumps(prompts.jev_request(q, r["review_text"], segs), ensure_ascii=False)))
        primary_requests = len(pending)
    else:
        n = int(e["llm_batch_size"])
        chunks = [pending[i:i + n] for i in range(0, len(pending), n)]
        for ch in chunks:
            items = [(f"r{i + 1}", [x["review_text"][s:t] for s, t in segment_spans(x["review_text"])]) for i, x in enumerate(ch)]
            req = prompts.enrich_batch_request(items, 64, template=e["llm"]["prompt"])
            sizes.append(len(req["system"]) + len(req["user"]) + len(json.dumps(req["schema"])))
        primary_requests = len(chunks)
    single = prompts.enrich_single_request(["Example sentence one.", "Example two."], 600, template=e["llm"]["prompt"])
    fallback_chars = len(single["system"]) + len(single["user"]) + len(json.dumps(single["schema"]))
    vb = int(cfg["verify"].get("batch_size", 1))
    vitems = [(f"v{i + 1}", r["review_text"]) for i, r in enumerate(pending[:vb])]
    vreq = prompts.verify_batch_request(vitems, 400, template=cfg["verify"]["prompt"]) if vitems else None
    verify_chars = (len(vreq["system"]) + len(vreq["user"]) + len(json.dumps(vreq["schema"]))) if vreq else 0
    sizes.sort()
    mean = sum(sizes) / len(sizes) if sizes else 0
    est = {
        "method": "characters / 4 = typical token estimate; characters / 3 = conservative (used for spend reservations). "
                  "Estimates only: providers tokenize differently; the pilot measures real usage.",
        "primary_backend": e["backend"], "primary_requests": primary_requests,
        "primary_request_chars": {"mean": round(mean, 1), "median": sizes[len(sizes) // 2] if sizes else 0,
                                  "p90": sizes[int(0.9 * (len(sizes) - 1))] if sizes else 0, "max": sizes[-1] if sizes else 0},
        "primary_tokens_per_request_estimate": round(mean / 4, 1),
        "fallback_request_chars_example": fallback_chars,
        "verify_request_chars_example": verify_chars, "verify_reviews_per_request": vb,
        "system_prompt_chars": len(prompts.render_template(Path(e["llm"]["prompt"]).name)),
        "reviews_ingested": report["counts"]["records"],
        "distinct_texts_pending": len(pending),
    }
    atomic_write_json(Path(args.run_dir) / "preflight.json", est)
    _say(json.dumps(est, indent=2))
    return 0


def cmd_rank(args):
    cfg = _load_cfg_for_run(args)
    store = Store(Path(args.run_dir))
    from .rank import check_reproducible, run_rank
    run_dir = Path(args.run_dir)
    if args.check:
        g = run_dir / "grading"
        records = g / "records.jsonl" if (g / "records.jsonl").exists() else g / "records.jsonl.gz"
        res = check_reproducible(records, g / "membership.csv", g / "ranking.csv")
        _say(json.dumps({"check": "ranking recomputed from grading/records + membership (no model calls)", **res}, indent=2))
        atomic_write_json(run_dir / "rank_check.json", {**res, "checked_at": utc_now()})
        return 0 if res["identical"] else 1
    run_rank(store, cfg.label_config(), log=_say)
    return 0


def cmd_export(args):
    cfg = _load_cfg_for_run(args)
    store = Store(Path(args.run_dir))
    from .export import export
    _say(json.dumps(export(store, cfg, Path(args.grading_dir) if args.grading_dir else None), indent=2))
    return 0


def cmd_status(args):
    cfg = _load_cfg_for_run(args)
    store = Store(Path(args.run_dir))
    spent, unknown = store.spend_totals()
    out = {"input": store.get_meta("input"), "label_config": cfg.label_config(), "results": result_summary(store, cfg),
           "spend_usd": round(spent, 6), "unknown_charge_reservations_usd": round(unknown, 6),
           "calls": call_summary(store),
           "invocations": [{k: r[k] for k in ("run_id", "phase", "status", "stop_reason", "started_at")}
                           for r in store.invocations()]}
    _say(json.dumps(out, indent=2))
    return 0


def cmd_planted(args):
    cfg = _load_cfg_for_run(args)
    store = Store(Path(args.run_dir))
    from .verify import planted_error_test
    res = planted_error_test(store, cfg)
    res["offline_stub_labels"] = cfg.offline_stub
    atomic_write_json(Path(args.run_dir) / "evals" / "planted_error.json", res)
    _say(json.dumps(res, indent=2))
    return 0 if res["status"] in ("detected", "not_run") else 1


def cmd_golden(args):
    cfg = _load_cfg_for_run(args)
    store = Store(Path(args.run_dir))
    from .golden import score_golden
    res = score_golden(Path(args.labels), store, cfg)
    out = Path(args.out) if args.out else Path(args.run_dir) / "evals" / "golden_results.json"
    atomic_write_json(out, res)
    if res["status"] == "ready" and res["cases"]:
        from .golden import error_analysis_md
        from .util import atomic_write_text
        atomic_write_text(out.with_name(out.stem + "_disagreements.md"), error_analysis_md(res))
    _say(json.dumps({k: res[k] for k in ("status", "cases", "agreement", "severity", "sentiment")}, indent=2))
    return 0


def cmd_trace(args):
    cfg = _load_cfg_for_run(args)
    store = Store(Path(args.run_dir))
    from .trace import run_trace
    md = run_trace(store, cfg, Path(args.run_dir), review_id=args.review_id, auto=args.auto or not args.review_id)
    if args.out:
        from .util import atomic_write_text
        atomic_write_text(Path(args.out), md)
        _say(f"wrote {args.out}")
    else:
        _say(md)
    return 0


def cmd_analyze(args):
    cfg = _load_cfg_for_run(args)
    store = Store(Path(args.run_dir))
    from .analysis import run_analysis
    run_analysis(store, cfg, log=_say)
    return 0


def cmd_label_golden(args):
    from .label_tool import main as label_main
    label_main(args.source)
    return 0


def cmd_render_prompts(args):
    from . import prompts
    prompts.render_jev_questions_file()
    _say(f"wrote {rel(prompts.JEV_QUESTIONS_FILE)}")
    prompts.render_decisions_questions_file()
    _say(f"wrote {rel(prompts.DECISIONS_QUESTIONS_FILE)}")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="python -m insight", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--config", default=None, help="config TOML (default config/pipeline.toml)")
    sub = p.add_subparsers(dest="command", required=True)

    r = sub.add_parser("run", help="run the pipeline (resumable)")
    r.add_argument("--input", required=True, help="input CSV path")
    r.add_argument("--run-dir", required=True, help="state + outputs folder (reuse it to resume)")
    r.add_argument("--stages", default=None, help=f"comma list from {','.join(STAGES)} (default: all)")
    r.add_argument("--allow-paid", action="store_true", help="permit live (billed) model calls")
    r.add_argument("--budget-usd", type=float, default=None, help="hard spend cap for this run directory")
    r.add_argument("--workers", type=int, default=None)
    r.add_argument("--stop-after", type=int, default=None, help="simulate an interruption after N saved reviews")
    r.add_argument("--offline-stub", action="store_true", help="use the local stub server (no real models, no cost)")
    r.add_argument("--stub-faults", default="", help="e.g. 'typesafe:3=429,openai:2=malformed' (offline stub only)")
    r.add_argument("--stub-timeout-sleep", type=float, default=3.0)
    r.add_argument("--shadow-rates", action="store_true", help="price stub calls at real model rates (budget demos)")
    r.add_argument("--timeout-s", type=float, default=None, help="override every provider timeout")
    r.add_argument("--allow-config-change", action="store_true",
                   help="allow a new label_config in a run directory that has results under another one")
    r.add_argument("--full", default=None,
                   help="full source CSV when --input is a declared subset: profiled for ingestion.json and accounting")

    pf = sub.add_parser("preflight", help="ingest and estimate requests/tokens; no model calls")
    pf.add_argument("--input", required=True)
    pf.add_argument("--run-dir", required=True)

    rk = sub.add_parser("rank", help="rebuild ranking from saved outputs (no model calls)")
    rk.add_argument("--run-dir", required=True)
    rk.add_argument("--check", action="store_true", help="recompute from grading/ files and compare")

    ex = sub.add_parser("export", help="rewrite exports from saved state")
    ex.add_argument("--run-dir", required=True)
    ex.add_argument("--grading-dir", default=None)

    st = sub.add_parser("status", help="show counts, spend and history")
    st.add_argument("--run-dir", required=True)

    pe = sub.add_parser("planted-error", help="planted wrong-label test using saved verifier output")
    pe.add_argument("--run-dir", required=True)

    gd = sub.add_parser("golden", help="score predictions against human golden labels")
    gd.add_argument("--labels", required=True, help="hand-labelled golden CSV")
    gd.add_argument("--run-dir", required=True, help="run whose input included the golden reviews")
    gd.add_argument("--out", default=None)

    sub.add_parser("render-prompts", help="regenerate the typed-question files in prompts/")

    tr = sub.add_parser("trace", help="trace one review through every stage from saved artifacts (no model calls)")
    tr.add_argument("--run-dir", required=True)
    tr.add_argument("--review-id", default=None)
    tr.add_argument("--auto", action="store_true", help="pick a traced review and an ambiguous/failed case")
    tr.add_argument("--out", default=None)

    an = sub.add_parser("analyze", help="recompute descriptive analysis from saved outputs (no model calls)")
    an.add_argument("--run-dir", required=True)

    lg = sub.add_parser("label-golden", help="terminal labeller for the golden 50 (a person labels; resumable)")
    lg.add_argument("--source", default=None, help="CSV to continue from (default: saved progress or the blank file)")

    for sp in (pf, rk, ex, st, pe, gd, tr, an):
        sp.add_argument("--offline-stub", action="store_true", help="read a run made with --offline-stub")
    for sp in (r, pf, rk, ex, st, pe, gd, tr, an):
        sp.add_argument("--set", action="append", default=[], metavar="KEY=VALUE",
                        help="override a config value, e.g. --set enrich.backend=jev (repeatable)")
    args = p.parse_args(argv)
    load_dotenv()  # keys from final-assignment/.env (git-ignored); existing environment variables win
    handler = {"run": cmd_run, "preflight": cmd_preflight, "rank": cmd_rank, "export": cmd_export, "status": cmd_status,
               "planted-error": cmd_planted, "golden": cmd_golden, "render-prompts": cmd_render_prompts,
               "label-golden": cmd_label_golden, "trace": cmd_trace, "analyze": cmd_analyze}[args.command]
    return handler(args)

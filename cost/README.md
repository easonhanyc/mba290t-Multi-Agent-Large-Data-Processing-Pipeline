# Cost and runtime calculator

`calculator.py` uses only the Python standard library. Opening or importing it never makes a call.

## Files (as of 2026-10-15 UTC, after the final run)

| File | Contents |
|---|---|
| `calculator.py` | `replay` (default, offline), `pilot` (explicit, billed), `refresh` (save a larger measured run) |
| `rates.csv` | Dated prices with source links, one row per provider / model / tier / billing item. The `subscription` rows price `claude -p` calls at $0 per call |
| `assumptions.json` | Editable inputs: budget ($9.00), max workers, output cap, fallback caps, verifier sample, scope counts (full file and declared subset), scenario rates. Values marked estimate or assumption are replaced by measurements when a pilot or refresh exists |
| `usage.csv`, `pilot_calls.jsonl`, `pilot_records.jsonl`, `pilot_runs.json` | The real pilot of the final setup (`runs/pilot100-20261014T213535Z`, executed 2026-10-14): one row per call and billing item, every attempt, the 100 review statuses, settings and timings |
| `experiments/pilot-effort-none/` | The same files for the first pilot (`runs/pilot100-20261012T224901Z`, superseded effort-none setup); still counted in project spend |
| `refreshes/<label>.json`, `<label>_calls.jsonl`, `<label>_usage.csv` | Larger measured runs. Final setup: `checkpoint_500_low` (1 worker), `analysis_10000_low` (8 workers), `final_200k_v2` (the final run, 4 invocations, per-invocation workers, seconds and budget in `invocations_detail`). Superseded effort-none setup: `checkpoint_500`, `analysis_10000`, `final_200k` |
| `project_spend.json` | Billed spend per run directory, summed over `runs/`; reproduced offline from each run's `state.sqlite` when present, otherwise from the committed per-call evidence above, so it does not need the git-ignored run databases |
| `report.md`, `report.json` | Written by the replay; not edited by hand. Projections use the measurements of the pilot's setup only; the superseded setup's steps are listed in their own table |
| `offline_stub_example/` | The same file set from a stub pilot. Models are `stub-*`, cost is $0 by definition; never a measurement |

## Offline replay (default, no API key)

```bash
python3 cost/calculator.py
```

Recomputes every number from saved files and rewrites `report.md`, `report.json` and `project_spend.json`:
`rates.csv` x `usage.csv` for the measured pilot, `refreshes/*_usage.csv` for larger checkpoints, and
`assumptions.json` for the projections. The report's sections are the measured pilot, the measured refreshes,
"Scaling decision" (what each measured step showed, the worker comparison, the estimate each step gave before
the final run, and the decision), "Estimated runs" (with a projection check against the measured final run),
and "Spending controls and spend to date". Try edits without touching the saved report:

```bash
python3 cost/calculator.py replay --rates my_rates.csv --assumptions my_assumptions.json --out-dir /tmp/calc
```

`--runs-root DIR` sets the run directories that spend to date is read from (default `$INSIGHT_RUNS_ROOT`, as
for the pipeline's project cap, or `runs/`). A replay to any other `--out-dir` never rewrites the committed
`cost/project_spend.json`. Spend to date is priced call by call as usage x `rates.csv` and counted once by
request ID; a run directory whose calls are in neither a state database nor the committed evidence is listed
as "not reproducible offline" rather than dropped.

## Explicit pilot execution (billed)

```bash
.venv/bin/python cost/calculator.py pilot --execute --allow-paid --budget-usd 0.10
```

Derives `cost_100.csv` as the first 100 rows of `checkpoint_500.csv` and refuses to run unless its SHA-256
equals the manifest's `cost_100.csv` checksum. Runs the configured pipeline cold (new run directory, empty
result cache, one worker), then warm (same directory), writes the pilot files here and replays. The
`--offline-stub` variant writes to `offline_stub_example/` instead.

After a 500 or 10,000-review run, save its measured usage so projections use it:

```bash
python3 cost/calculator.py refresh --run-dir runs/<run> --label checkpoint_500
```

## Status (2026-10-15 UTC, after the final run)

- **Measured pilot (final setup): done.** Cold: 100 of 100 completed, 3 enrichment attempts, billed $0.001698,
  API-equivalent of the Pro calls $0.172108, 177.3 s. Warm: 0 new enrichment calls, 100 result-cache hits, $0,
  0.044 s. Input SHA-256 matches the manifest (`report.md`, "Measured 100-review pilot"). The superseded effort-none
  pilot (billed $0.001339, 159.5 s) is in `experiments/pilot-effort-none/`.
- **checkpoint_500_low refresh: done.** 500 rows, 479 distinct texts, 1 worker, 462.06 s, billed $0.006952
  (`refreshes/checkpoint_500_low.json`). The 1-vs-2 worker comparison ran on the superseded setup
  (`runs/live-checkpoint500` and the cold 2-worker rerun `runs/live-checkpoint500-w2`, $0.004250): enrichment
  266.8 s with 1 worker vs 154.3 s with 2 (the report's "Worker comparison").
- **analysis_10000_low refresh: done.** 10,000 rows, 8,448 distinct texts, 8 workers, billed $0.128644, 126 fallback1
  reviews (cap 1.5%), 845 verified (`refreshes/analysis_10000_low.json`). Its first invocation hit the Claude Pro
  session limit during verify, group and memo; the same command was rerun and redid them with no enrichment calls,
  so the refresh covers 2 invocations, 1,606.41 s.
- **Live budget drill: done** (`runs/live-budget-drill`, `./scripts/live.sh budget-drill`). Under
  `--budget-usd 0.005` the run stopped with `stop_reason budget_cap` after $0.002979, with 353 of 500 IDs
  saved; a resume under `--budget-usd 0.05` completed all 500 for $0.004306 in total.
- **final_200k_v2 refresh: done.** 200,013 rows, 152,363 distinct texts, 200,000 completed, 13 quarantined, 0
  unfinished, 9,389.902 s over 4 invocations (9,212.494 s in the 2 enrichment invocations), billed $2.323945 plus
  $0.097098 reserved for 17 unknown-outcome calls, API-equivalent $1.9607, 2,285 fallback1 reviews, 2,000 verified
  (`refreshes/final_200k_v2.json`). The projections use its per-unit inputs at 16 workers and its measured 99.1%
  enrichment-pool utilisation; because that utilisation comes from the same run, the projection check against it
  (8,755.5 s projected vs 8,755.8 s measured for enrichment) is a consistency check, not an independent forecast.
  The estimate before the run, from analysis_10000_low, was $2.32 (base, reuse) to $4.55 (conservative, no reuse).
- **Billed spend: $4.702001** over 17 run directories and 22,977 billed-provider calls in `project_spend.json`
  (settled $4.604903 plus the $0.097098 reservation), of which $2.421043 is the final run and $2.019246 the superseded
  first final run, against the $9.00 project cap. No run directory is "not reproducible offline", and the costs logged
  at call time sum to the same total (`report.md`, "Spending controls and spend to date"). A clean-clone replay without
  the git-ignored run databases gives the same total.
- **Invalid outputs, reconciled** (final run; footnote under "Retries" in `report.md`): 0 enrichment outputs failed
  validation as a whole and 14 were partly valid; their 14 retry tasks made 14 attempts. The memo stage had 1 output
  rejected by its validator.
- **Reconciliation with the provider**: billed OpenAI spend is computed from the usage each call reported and can
  be checked against the OpenAI account's usage page; no reconciliation figure is recorded in this folder.

## Billing kinds

- **Billed API**: per-token charges on the OpenAI account (and TypeSafe, which was not used).
- **API-equivalent**: what the `claude -p` calls (Claude Pro subscription) would cost at Anthropic API
  rates for the model the CLI reported. They are $0 per call under a flat monthly fee, which is not included in
  billed spend or apportioned to calls, and the API-equivalent is never added to billed spend. The course says subscription access is not evidence that calls are free
  (`COST_CALCULATOR.md`), so this column is always shown.
- **Local compute**: the orchestrating laptop only, from stated assumptions in `assumptions.json`;
  hardware cost is unknown and not estimated.

## Spend controls

Per-run `--budget-usd` with worst-case reservations; project cap `run.project_cap_usd = 9.00` summed over
`runs/**/state.sqlite` (an unreadable database fails closed; one live run at a time); prepaid OpenAI credit
with auto-recharge off; insufficient-credit errors stop the run; unknown charges keep their reservation.
Details: `docs/architecture.md`, "Concurrency, rate limits and spend".

## Formulas and checks

- `item_cost = billed_units x usd_per_million / 1,000,000` per mutually exclusive item:
  `input_uncached = input - cached - cache_write`, `input_cached`, `input_cache_write`, `output` (reasoning
  included), priced at the tier the provider reported (for example Flex). Totals are sums.
- Unpriced usage is reported as unknown, never as zero.
- Projected stage cost = projected reviews (or fixed calls for group and memo) x measured billed cost per
  unique review (or per call). The base scenario adds no retries beyond the measured ones; the conservative
  one multiplies by (1 + transient + invalid-output retry rates) and a token multiplier. Fallback rates are
  the measured share of reviews routed, capped by the declared maxima.
- Projected seconds per stage = requests x mean attempt latency / (workers x pool utilisation), or
  requests / (provider requests-per-minute limit / 60) when that is slower. Requests = reviews x measured
  attempts per unique review (retries and failed attempts included), and the latency averages every attempt.
  Pool utilisation = summed attempt durations of the enrichment stages / (workers x enrich-stage wall
  seconds) over the invocations that made enrichment calls. Stages are summed, plus code stages per 1,000
  rows.
- Spend to date = usage x rates per billed-provider call, each request ID counted once, plus the
  reservations of calls whose outcome is unknown (the same rule as the pipeline's project cap).
- `tests/test_calculator.py` checks that doubling every rate doubles API cost (and recomputed spend) while
  measured time and local compute stay the same, that changing projected rows never changes the measured
  section, the budget warning, a by-hand recomputation of measured cost, that subscription calls are $0
  billed but carry an API-equivalent, that opening the calculator makes no calls, that project spend is
  reproduced from the committed evidence without the final-run database, that runs without call evidence
  are listed rather than dropped, that a replay to another folder never writes `project_spend.json`, that
  enrichment workers come from the enrichment invocations, and that the declared-scope time projection
  matches the measured final run.

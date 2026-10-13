# Cost and runtime calculator

`calculator.py` uses only the Python standard library. Opening or importing it never makes a call.

## Files (as of 2026-10-12, after the final run)

| File | Contents |
|---|---|
| `calculator.py` | `replay` (default, offline), `pilot` (explicit, billed), `refresh` (save a larger measured run) |
| `rates.csv` | Dated prices with source links, one row per provider / model / tier / billing item. The `subscription` rows price `claude -p` calls at $0 per call |
| `assumptions.json` | Editable inputs: budget ($9.00), max workers, output cap, fallback caps, verifier sample, scope counts (full file and declared subset), scenario rates. Values marked estimate or assumption are replaced by measurements when a pilot or refresh exists |
| `usage.csv` | One row per pilot call and billing item (68 rows) |
| `pilot_calls.jsonl`, `pilot_records.jsonl`, `pilot_runs.json` | The real pilot (`runs/pilot100-20261012T224901Z`, executed 2026-10-12): every attempt, the 100 review statuses, settings and timings |
| `refreshes/checkpoint_500.json`, `checkpoint_500_calls.jsonl`, `checkpoint_500_usage.csv` | The live 500-review checkpoint (`runs/live-checkpoint500`, 1 worker) |
| `refreshes/analysis_10000.json`, `analysis_10000_calls.jsonl`, `analysis_10000_usage.csv` | The live 10,000-review checkpoint (`runs/live-analysis10000`, 8 workers) |
| `refreshes/final_200k.json`, `final_200k_calls.jsonl`, `final_200k_usage.csv` | The final run on the declared 200,013-row scope (`runs/final-200k`, all five invocations) |
| `project_spend.json` | Billed spend per run directory, summed over `runs/` |
| `report.md`, `report.json` | Written by the replay; not edited by hand |
| `offline_stub_example/` | The same file set from a stub pilot. Models are `stub-*`, cost is $0 by definition; never a measurement |

## Offline replay (default, no API key)

```bash
python3 cost/calculator.py
```

Recomputes every number from saved files and rewrites `report.md` / `report.json`: `rates.csv` x
`usage.csv` for the measured pilot, `refreshes/*_usage.csv` for larger checkpoints, and `assumptions.json`
for the projections. Try edits without touching the saved report:

```bash
python3 cost/calculator.py replay --rates my_rates.csv --assumptions my_assumptions.json --out-dir /tmp/calc
```

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

## Status (2026-10-12, after the final run)

- **Measured pilot: done.** Cold: 100 of 100 completed, 3 enrichment attempts, billed $0.001339,
  API-equivalent of the Pro calls $0.127723, 159.5 s. Warm: 0 new enrichment calls, 100 result-cache hits,
  $0, 0.038 s. Input SHA-256 matches the manifest (`report.md`, "Measured 100-review pilot").
- **checkpoint_500 refresh: done.** 500 rows, 479 distinct texts, 1 worker, 396.63 s, billed $0.0052,
  API-equivalent $0.1698 (`report.md`, "Measured refreshes"; `refreshes/checkpoint_500.json`). Projections
  used these per-unit inputs until the final_200k refresh. The 2-worker cold rerun (`runs/live-checkpoint500-w2`, $0.004250) counts
  toward project spend but is not a refresh.
- **Live budget drill: done** (`runs/live-budget-drill`, `./scripts/live.sh budget-drill`). Under
  `--budget-usd 0.005` the run stopped with `stop_reason budget_cap` after $0.002979, with 353 of 500 IDs
  saved; a resume under `--budget-usd 0.05` completed all 500 for $0.004306 in total
  (`runs/live-budget-drill/run_summary.json`).
- **analysis_10000 refresh: done.** 10,000 rows, 8,448 distinct texts, 8 workers, 931.56 s, billed
  $0.0963, API-equivalent $0.7680, 126 fallback1 reviews (cap 1.5%), 845 verified (`report.md`, "Measured
  refreshes"; `refreshes/analysis_10000.json`).
- **final_200k refresh: done.** 200,013 rows, 152,363 distinct texts, 200,000 completed, 13 quarantined, 0
  unfinished, 9,156.131 s over 5 invocations, billed $2.0192, API-equivalent $1.8228, 13,639 fallback1
  reviews, 2,000 verified (`report.md`, "Measured refreshes"; `refreshes/final_200k.json`). The workers
  column shows 4, the setting of the last invocation (a group/rank/memo/export regeneration); both
  enrichment invocations ran with 16 workers (`invocations` table of `runs/final-200k/state.sqlite`). The
  projections in `report.md` now use the final_200k per-unit inputs.
- Billed spend: $2.142643 over twelve run directories in `project_spend.json` (computed 2026-10-13 02:10
  UTC), of which $2.019246 is the final run, against the $9.00 project cap.

## Billing kinds

- **Billed API**: per-token charges on the OpenAI account (and TypeSafe, which was not used).
- **API-equivalent**: what the `claude -p` calls (Claude Pro subscription) would cost at Anthropic API
  rates for the model the CLI reported. They are $0 per call under a fixed monthly fee and are never added to
  billed spend. The course says subscription access is not evidence that calls are free
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
- Projected seconds = requests / min(workers / mean latency, provider requests-per-minute limit / 60),
  summed over stages, plus code stages per 1,000 rows.
- `tests/test_calculator.py` checks that doubling every rate doubles API cost while measured time and local
  compute stay the same, that changing projected rows never changes the measured section, the budget
  warning, a by-hand recomputation of measured cost, that subscription calls are $0 billed but carry an
  API-equivalent, and that opening the calculator makes no calls.

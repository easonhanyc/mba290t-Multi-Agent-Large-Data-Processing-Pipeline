# Cost and runtime calculator

`calculator.py` uses only the Python standard library. Opening or importing it never makes a call.

## Offline replay (default, no API key)

```bash
python3 cost/calculator.py
```

Recomputes every number from saved files and rewrites `report.md` / `report.json`:
`rates.csv` (dated prices with source links) x `usage.csv` (one row per call and billing item) for the
measured pilot, and `assumptions.json` (editable budget, workers, output cap, fallback fractions,
scenario rates, per-request token sizes) for the full-run projection. Try edits with:

```bash
python3 cost/calculator.py replay --rates my_rates.csv --assumptions my_assumptions.json --out-dir /tmp/calc
```

## Explicit pilot execution (billed)

```bash
.venv/bin/python cost/calculator.py pilot --execute --allow-paid --budget-usd 0.50
```

Derives `cost_100.csv` as the first 100 rows of `checkpoint_500.csv` and refuses to run unless its SHA-256
equals the manifest's `cost_100.csv` checksum. Runs the configured pipeline cold (new run directory, empty
result cache, one worker) and then warm (same directory), and writes `pilot_records.jsonl`,
`pilot_calls.jsonl`, `usage.csv` and `pilot_runs.json` here before replaying. Needs the API keys listed in
`.env.example`. The `--offline-stub` variant writes to `offline_stub_example/` instead and is never a
measurement.

## Status (2026-10-01)

- **Measured pilot: not yet run.** No API keys were configured in this build, so `report.md` says so
  instead of showing invented numbers. `pilot_*.jsonl` and `usage.csv` will appear here after the command above.
- `offline_stub_example/` shows the full file set and arithmetic from a stub run (all models `stub-*`,
  token counts are character placeholders, cost $0 by definition).
- Full-run projection uses pre-pilot estimates (rendered prompt sizes / 4 characters per token; latency
  assumptions). After a real pilot, measured per-request usage and latency replace them automatically.

## Formulas and checks

- `item_cost = billed_units x usd_per_million / 1,000,000` per mutually exclusive item:
  `input_uncached = input - cached`, `input_cached`, `output` (reasoning already included). Totals are sums.
- Unpriced usage is reported as unknown, never as zero. Local compute (the orchestrating laptop) is shown
  separately from API spend and is based on stated assumptions; hardware cost is unknown.
- Projection per stage: attempts = work units x stage rate x (1 + transient retry rate + invalid-output
  retry rate), with fallback rates capped; cost = attempts x (input tokens x input price + output tokens x
  output price); seconds = attempts / min(workers x per-worker rate, provider limit). Group and memo are
  fixed overhead counted once.
- `tests/test_calculator.py` checks that doubling every rate doubles API cost while measured time and local
  compute stay the same, that changing projected rows never changes the measured section, the budget
  warning, and a by-hand recomputation of measured cost.

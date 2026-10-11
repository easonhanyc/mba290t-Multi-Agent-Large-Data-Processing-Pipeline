# Evaluations

Status on 2026-10-01: every evaluation below is built and tested, but the ones that judge **model
behaviour** need a live run, which has not happened yet (no API keys). Offline-stub results only prove
the plumbing; stub labels are hash-based and meaningless.

| Check | How | Status |
|---|---|---|
| Golden set (50 human labels) | Hand-label `golden_50_to_label.csv`; run the pipeline on it; `python -m insight golden --labels <labelled csv> --run-dir <run>` | Scorer built and tested on synthetic labels. **Pending: Eason's labels + a live run.** |
| Independent verification | Stage 3 (`verification/report.json`, `disagreements.csv`) | Runs offline; agreement numbers need a live run. |
| Planted wrong label | `python -m insight planted-error --run-dir <run>` (test copy only, saved verifier output, no calls) | Detected in the offline 500-row run; repeat on the live run. |
| Prompt injection | `evals/synthetic/injection_cases.csv` (clearly marked synthetic) + `evals/check_synthetic.py` | Plumbing passes offline (empty texts quarantined; markup cannot break requests). **Label checks pending a live run.** |
| Reproducibility | `python -m insight rank --run-dir <run> --check` | Identical ranking from saved files (offline run). |
| Recovery | real Ctrl-C then resume (`scripts/offline_demo.sh`, `tests/test_pipeline.py`) | Demonstrated offline: checker `pass`, no completed ID re-sent. |
| Awkward paths | 429, 500, timeout, malformed and truncated output, budget cap, circuit breaker | `tests/test_pipeline.py` and the fault drill in `runs/offline-demo-transcript.txt`. |

## Golden labelling format

Fill the blank columns of `golden_50_to_label.csv` (keep the six source columns unchanged):

- `topic`, `intent`, `severity`: one label, or several accepted labels separated by `|` for genuinely
  ambiguous cases (e.g. `playback|downloads`). Ambiguous cases are counted and reported.
- `sentiment`: a number in [-1, 1] (anchors in `docs/labels.md`).
- `entities`: terms separated by `;` (may be blank); `evidence_quote`: the exact supporting substring.
- `needs_review`: `true` or `false`.

Label before looking at model output, using `docs/labels.md`. The pipeline's ingest stores only the six
source fields, so these answer columns can never reach a prompt. If the rubric changes after looking at
golden failures, disclose it and add fresh held-out cases for the final check.

## Live commands (next week)

```bash
python -m insight run --input evals/synthetic/injection_cases.csv --run-dir runs/synthetic-injection --stages ingest,enrich,export --allow-paid --budget-usd 0.05
python3 evals/check_synthetic.py runs/synthetic-injection
python -m insight run --input "Final Assignment - Spotify Reviews Dataset/golden_50_to_label.csv" --run-dir runs/golden50 --stages ingest,enrich,export --allow-paid --budget-usd 0.10
python -m insight golden --labels path/to/golden_50_labelled.csv --run-dir runs/golden50
```

Synthetic cases live in their own run directories and are never merged into business results.

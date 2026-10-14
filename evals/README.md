# Evaluations

Status on 2026-10-13, after the final run (`runs/final-200k`). These checks have run on real model output:
the verifier, the run-to-run comparison, the prompt-injection test and the budget drill, plus the
planted-error, rank-reproducibility and recovery checks on the final run. The golden-50 evaluation has also
been run on real model output: Eason's hand labels were scored against the final run and three candidate
setups. The labels were finished after the final run, as disclosed in `docs/model_choice.md`. The verifier's
762 disagreements on the final run are counted and a sample is inspected in
[verification/disagreement_analysis.md](verification/disagreement_analysis.md). Offline-stub results only prove
plumbing; stub labels are hash-based and meaningless. `runs/final-200k/state.sqlite`, cited below, is not in
git. It is a release asset; the download, restore and checksum steps are in the README under [Where to find
everything](../README.md#where-to-find-everything).

## Files

| Path | Contents |
|---|---|
| `synthetic/injection_cases.csv` | 8 clearly marked synthetic reviews: 6 with injected instructions, markup or JSON fragments (one in Spanish), 2 empty or whitespace-only |
| `synthetic/expected.json` | The constraint each case must meet (status, allowed or forbidden topic/intent, severity bounds) |
| `check_synthetic.py` | Scores a run on those cases against `expected.json` (no model calls) |
| `injection/synthetic_check.json` | Copy of the live result (`runs/live-synthetic-injection/evals/synthetic_check.json`) |
| `ensemble_golden.py` | Offline: scores Luna alone, Decisions alone, the cases where they agree, and a rule fixed before seeing results (on disagreement take Decisions when its confidence is at least 0.80, else Luna) on the golden 50 |
| `verification/disagreement_analysis.md` | The final run's 762 verifier disagreements: counts by field and direction, the AI assistant's reading of 38 inspected cases (not human labels), and what they imply for the ranking |
| `golden/` | `golden_50_labeled.numbers` (Eason's hand labels), `golden_50_labeled_workbook_export.csv` (its CSV export), `convert_labels.py` -> `golden_50_labeled.csv`, `candidates/<run>.json`, `results.json` + `results_disagreements.md` (final run), `ensemble.json`, `make_error_analysis.py` -> `error_analysis.md` |

## Checks

| Check | How | Status and result |
|---|---|---|
| Golden set (50 human labels) | `python -m insight label-golden`, then `./scripts/live.sh golden-candidates`, then `python -m insight golden --labels evals/golden/golden_50_labeled.csv --run-dir <run>` | Final run: topic 76%, intent 74%, severity exact 76%, MAE 0.24, sentiment within 0.5 86%, 0 ambiguous cases, 50/50 exact quotes, needs_review agrees on 43/50 (`golden/results.json`) |
| Candidate comparison on the golden 50 | `runs/golden-luna-none` (production setting), `runs/golden-luna-low`, `runs/golden-decisions` (Decisions allows 50 requests per day); `evals/ensemble_golden.py` | The three enrichment runs finished on 2026-10-12 with predictions for all 50 texts (`run_summary.json` in each); scored 2026-10-13: effort none 74/70/72%, effort low 80/76/76%, Decisions 76/74/68%, Luna + Decisions rule 74/74/70% (topic/intent/severity; `golden/candidates/`, `golden/ensemble.json`) |
| Error analysis | `cases_detail` in the golden output lists every disagreement with the text and both labels | [golden/error_analysis.md](golden/error_analysis.md): request-vs-complaint convention (7), praise naming a feature (4), blocked vs degraded severity (5), non-English or name-only texts |
| Independent verification | Stage 3: Claude Haiku labels a declared random sample (10% of distinct texts, at least 10, at most 2,000) without seeing the enricher's answer (`verification/report.json`, `disagreements.csv`) | Pilot, 10 reviews: topic 9/10, intent 10/10, severity 7/10, sentiment within tolerance 10/10 (`runs/pilot100-20261012T224901Z/verification/report.json`). Checkpoint 500, 48 reviews: topic 41/48, intent 45/48, severity 39/48, sentiment 48/48 (`runs/live-checkpoint500/verification/report.json`). analysis_10000, 845 reviews: topic 678/845, intent 763/845, severity 655/845, sentiment 835/845 (`runs/live-analysis10000/verification/report.json`). **Final run, 2,000 reviews**: topic 1,618/2,000, intent 1,841/2,000, severity 1,583/2,000 (1,967 within one point), sentiment 1,980/2,000; 762 reviews differ on at least one field and are listed with text and both labels in `runs/final-200k/verification/disagreements.csv`; 0 verifier failures (`runs/final-200k/verification/report.json`). Investigated in [verification/disagreement_analysis.md](verification/disagreement_analysis.md): most disagreements are one-field boundary calls (582 of 762). The decision-relevant one is `billing.premium_only` vs usability/playback (71 of 235 sampled premium-only texts; 47 of those 71 contain no Premium or payment word, by a keyword check) |
| Run-to-run reproducibility | Same 500 reviews and `label_config`, 1 worker (`runs/live-checkpoint500`) vs a cold 2-worker rerun (`runs/live-checkpoint500-w2`); read-only SQL join of `results` by `review_id` | Same topic 482/500, intent 489/500, severity 484/500, all three 466/500. The routing code gives identical labels for identical answers (`tests/test_pipeline.py::test_two_workers_give_identical_labels`), so the differences come from the model |
| Planted wrong label | `python -m insight planted-error --run-dir <run>`: corrupts one label in a test copy and checks the saved verifier output flags it (no calls) | Detected on the offline stub run (`runs/offline-stub-checkpoint500/evals/planted_error.json`). **Detected on the final run**: the test copy of review `00015590-a6ef-4883-970e-6b48b6aad68c` was changed from catalog / praise / severity 1 / sentiment 1.0 to billing / complaint / 5 / -1.0; the saved verifier label (catalog / praise / 1 / 1.0) disagrees on all four fields; the stored record was not changed (`runs/final-200k/evals/planted_error.json`) |
| Prompt injection | `./scripts/live.sh injection` (own run directory, never in business results), then `python3 evals/check_synthetic.py runs/live-synthetic-injection` | **8 of 8 passed with the live enricher**: injected instructions were labelled as review content, markup and JSON did not break requests or output, the Spanish double-charge review stayed a billing complaint, and both empty texts were quarantined by code (`runs/live-synthetic-injection/evals/synthetic_check.json`; billed $0.000234, `runs/live-synthetic-injection/run_summary.json`) |
| Reproducible ranking | `python -m insight rank --run-dir <run> --check` (rebuilds the ranking from `grading/` files) | Identical on the offline stub run (`runs/offline-stub-checkpoint500/rank_check.json`). **Identical on the final run**: 22 issues, no first difference (`runs/final-200k/rank_check.json`, checked 2026-10-13 23:42 UTC, after the last memo regeneration) |
| Recovery and spend controls | Real SIGINT (`kill -INT`) then resume (`scripts/offline_demo.sh`, `tests/test_pipeline.py`); live budget drill (`./scripts/live.sh budget-drill`) | Offline demo, rerun after its fix ([`runs/offline-demo-transcript.txt`](../runs/offline-demo-transcript.txt)), every step passed: a SIGINT mid-enrichment stopped the run (exit code 130, 75 of 500 completed, 425 unfinished); the resume with the same command completed all 500; a warm rerun made zero model calls (0 pending, 0 to verify, 0 new naming calls, memo from cache); the course checker returned `pass` (`runs/offline-stub-checkpoint500/self-check.json`); the rank check was identical (22 issues); the planted error was detected; the fault drill and the stub budget drill (a $0.005 cap stopped the run with 57 of 500 completed, and a resume under a larger cap completed all 500) both finished with 0 unfinished. Live drill: a $0.005 cap stopped the run with 353 of 500 IDs saved; a resume under $0.05 completed all 500 (`runs/live-budget-drill/run_summary.json`). **Final run, recorded**: the recorder sent a real SIGINT after 180 s of saved progress (`scripts/record_session.py`); the run finished in-flight work and stopped at 208.4 s with 34,638 of 200,000 IDs saved and $0.058568 spent. The resume (phase `resume`) started with 146,763 pending distinct texts and completed all 200,000 (`runs/final-200k/recording/1-initial-interrupted.txt` and `2-resume.txt`, with `.cast` files that play in the dashboard's Run & cost tab or with `asciinema play -i 2 <file>.cast`; `grading/checkpoint_before.json` 34,638 IDs, `grading/checkpoint_after.json` 200,000 IDs; every enrich call after the interruption has phase `resume` in the `calls` table of `runs/final-200k/state.sqlite`). The course checker passed this export against the declared-scope reference (`runs/final-200k/self-check.json`) |
| Awkward paths | 429, 500, timeout, malformed and truncated output, circuit breaker, insufficient credit | `tests/test_pipeline.py`, `tests/test_extensions.py` and the offline fault drill (`runs/offline-stub-fault-drill-500`; in the demo transcript, 6 failed attempts, malformed and truncated output, two 429s, a 500 and a timeout, were retried and all 500 reviews completed). Live, final run: 172 HTTP 429 responses (Flex capacity) were retried with backoff and 10 invalid batch outputs (6 truncated, 4 malformed JSON) were retried; 0 reviews unfinished (`calls` table of `runs/final-200k/state.sqlite`) |

## Golden labelling format

How the golden labels were made (done; the result is `golden/golden_50_labeled.csv`). Fill the blank columns of `golden_50_to_label.csv` (keep the six source columns unchanged), or use
`python -m insight label-golden`, which shows only the review text, saves after every review and writes
`evals/golden/golden_50_labeled.csv`:

- `topic`, `intent`, `severity`: one label, or several accepted labels separated by `|` for genuinely
  ambiguous cases (e.g. `playback|downloads`). Ambiguous cases are counted and reported.
- `sentiment`: a number in [-1, 1] (anchors in `docs/labels.md`).
- `entities`: terms separated by `;` (may be blank); `evidence_quote`: the exact supporting substring.
- `needs_review`: `true` or `false`.

Label before looking at model output on these texts, using `docs/labels.md`. Ingest stores only the six
source fields, so the answer columns can never reach a prompt. Do not infer severity or sentiment from the
star rating. If the labels or prompts change after looking at golden failures, disclose it and add fresh
held-out cases for the final check. Fifty cases are a diagnostic, not a precise accuracy estimate.

## Commands

```bash
.venv/bin/python -m insight label-golden                 # a person labels; resumable
./scripts/live.sh golden-candidates                      # billed: enrich the 50 texts with each candidate, then score
python3 evals/ensemble_golden.py --labels evals/golden/golden_50_labeled.csv \
    --luna runs/golden-luna-none --decisions runs/golden-decisions --out evals/golden/ensemble.json
python3 evals/check_synthetic.py runs/live-synthetic-injection
./scripts/offline_demo.sh                                # offline: SIGINT, resume, warm rerun, checker, rank check, planted error, drills
.venv/bin/python -m insight planted-error --run-dir <run>
.venv/bin/python -m insight rank --run-dir <run> --check
```

Synthetic cases live in their own run directories and are never merged into business results.

# Evaluations

Status on 2026-10-15, after the final run (`runs/final-200k-v2`, 4 invocations: initial, interrupted by SIGINT;
resume; two memo regenerations from saved labels, see [docs/post_run_corrections.md](../docs/post_run_corrections.md)).
Every check below ran on real model output unless it says offline stub; stub labels are hash-based and meaningless.
The final run uses the setup that won the golden-50 comparison of three candidates; the first final run made earlier
with effort none (`runs/final-200k`) is kept as superseded evidence. `runs/final-200k-v2/state.sqlite`, cited below,
is not in git: it is a release asset (download, restore and checksum steps in the README, [Where to find
everything](../README.md#where-to-find-everything)).

## Files

| Path | Contents |
|---|---|
| `golden/` | `golden_50_labeled.numbers` (Eason's hand labels), `golden_50_labeled_workbook_export.csv` (its CSV export), `convert_labels.py` -> `golden_50_labeled.csv`, `candidates/<run>.json` (the three candidate setups and the superseded final run), `results.json` + `results_disagreements.md` (final run), `ensemble.json`, `make_error_analysis.py` -> `error_analysis.md` |
| `quote_support.py`, `quote_support/` | Does each evidence quote support its labels? Code checks plus a blind judge (Claude Haiku via Claude Pro) on the final run's own quotes and labels for the golden 50 and a declared random sample of 500 final-run texts; Eason's golden labels are compared by code only and never reach the judge: `report.md`, `summary.json`, `items.jsonl`, `judgments.jsonl`, `calls.jsonl` |
| `verification/disagreement_analysis.md`, `disagreement_counts.py`, `disagreement_counts.json` | The final run's 762 verifier disagreements: counts by field and direction (computed), the AI assistant's reading of 39 sampled cases (not human labels), and what they imply. The superseded run's analysis: `disagreement_analysis_superseded_effort_none.md` |
| `synthetic/injection_cases.csv`, `synthetic/expected.json`, `check_synthetic.py` | 8 clearly marked synthetic reviews (6 with injected instructions, markup or JSON fragments, one in Spanish; 2 empty or whitespace-only), the constraint each must meet, and the scorer |
| `injection/synthetic_check.json` | Copy of the live result (`runs/live-synthetic-injection/evals/synthetic_check.json`) |
| `ensemble_golden.py` | Offline: scores Luna alone, Decisions alone, the cases where they agree, and a rule fixed before seeing results on the golden 50 |
| `fresh_input/rehearsal_60.csv` | 60 real reviews outside the declared scope, never labelled by any run, used to rehearse `scripts/fresh_input_demo.sh` (two source columns left out on purpose) |

## Checks

| Check | How | Status and result |
|---|---|---|
| Golden set (50 human labels) | `python -m insight label-golden` (Eason labelled in a Numbers workbook, converted by `golden/convert_labels.py`), then `python -m insight golden --labels evals/golden/golden_50_labeled.csv --run-dir <run>` | Final run: topic 78%, intent 76%, severity exact 74%, all three 48%, MAE 0.26, sentiment within 0.5 88%; 0 multi-label cases; 6 flagged `needs_review` by the human, the model's flag agrees on 45/50; 50/50 exact quotes (`golden/results.json`) |
| Choosing the setup on the golden 50 | `./scripts/live.sh golden-candidates`: `runs/golden-luna-none`, `runs/golden-luna-low`, `runs/golden-decisions`; `evals/ensemble_golden.py` | All three answered all 50 texts. All three correct: effort low 54%, Decisions 48%, effort none 46%; the Luna + Decisions rule does not beat Luna alone (`golden/candidates/`, `golden/ensemble.json`). The predeclared rule picked effort low; the final run uses its exact `label_config` (`cfg-52c5333247`). No prompt, label or threshold was changed because of golden results |
| Error analysis | `golden/make_error_analysis.py` from the saved scores | [golden/error_analysis.md](golden/error_analysis.md): the candidate scored 54% and the final run 48% with the same configuration (answers vary; the candidate sent the 50 texts in one request, the final run across 39), the superseded run 48%; misses are the request-vs-complaint convention (7), praise naming a feature (5), blocked vs degraded severity (5), and non-English or name-only texts. Because the golden set chose the setup, its final-run scores carry a small selection bias; no fresh human-labelled set was added |
| Evidence quotes support the labels | `./scripts/live.sh quote-support` (Claude Pro, $0 billed, API-equivalent $0.6588 for 11 requests) | Exact substring 550/550. Blind judge on the final run's own labels, share of quotes that alone support all three: random final-run sample 89% (topic 92%, intent 97%, severity 97%), golden 50 98% (no label rejected). Code compared the golden quotes with Eason's evidence sentences: the same sentence in 47 of 50 reviews (9 of 12 multi-sentence ones). Of the 21 sampled final-run quotes with a label the judge did not accept, the disagreement sits at the boundaries the verifier analysis found: premium-only vs playback/usability (8), topic among catalog/playback/usability/other (4), intent (4), praise naming a feature (3), severity of "removed basic features" (2) ([quote_support/report.md](quote_support/report.md); grouping is the AI assistant's reading). Eason's golden labels never reach the judge: a first version (2026-10-15) also sent them as calibration items and was withdrawn on 2026-10-17 and re-run without them |
| Independent verification | Stage 3: Claude Haiku labels a declared random sample (10% of distinct texts, at least 10, at most 2,000) without seeing the enricher's answer | Final setup: pilot 10 reviews, topic 8 / intent 8 / severity 6; checkpoint_500, 48: 41 / 46 / 35; analysis_10000, 845: 708 / 775 / 669. **Final run, 2,000 reviews**: topic 1,635, intent 1,830, severity exact 1,565 (1,962 within one point), sentiment 1,980; 762 differ on at least one field (`runs/final-200k-v2/verification/disagreements.csv`); 0 verifier failures. [Disagreement analysis](verification/disagreement_analysis.md): 570 of 762 differ on one field; the verifier moves 41 of 203 sampled premium-only texts to another topic (71 of 235 in the superseded run) |
| Run-to-run reproducibility | Same 500 reviews and `label_config`, 1 worker (`runs/live-checkpoint500`) vs a cold 2-worker rerun (`runs/live-checkpoint500-w2`), effort-none setup; read-only SQL join of `results` by `review_id` | Same topic 482/500, intent 489/500, severity 484/500, all three 466/500. The routing code gives identical labels for identical answers (`tests/test_pipeline.py::test_two_workers_give_identical_labels`), so the differences come from the model. The golden candidate vs final run comparison above shows the same variability at effort low |
| Planted wrong label | `python -m insight planted-error --run-dir <run>`: corrupts one label in a test copy and checks the saved verifier output flags it (no calls) | **Detected on the final run**: the test copy of review `00015590-a6ef-4883-970e-6b48b6aad68c` was changed from catalog / praise / 1 / 1.0 to billing / complaint / 5 / -1.0; the saved verifier label (catalog / praise / 1 / 1.0) disagrees on all four fields; the stored record was not changed (`runs/final-200k-v2/evals/planted_error.json`) |
| Prompt injection | `./scripts/live.sh injection` (own run directory, never in business results), then `python3 evals/check_synthetic.py runs/live-synthetic-injection` | **8 of 8 passed with the live enricher** (effort-none setup): injected instructions were labelled as review content, markup and JSON did not break requests or output, the Spanish double-charge review stayed a billing complaint, and both empty texts were quarantined by code (billed $0.000234) |
| Reproducible ranking | `python -m insight rank --run-dir <run> --check` (rebuilds the ranking from `grading/` files) | **Identical on the final run**: 22 issues, no first difference (`runs/final-200k-v2/rank_check.json`) |
| Recovery and spend controls | Real SIGINT then resume; live budget drill (`./scripts/live.sh budget-drill`); offline demo (`scripts/offline_demo.sh`) | **Final run, recorded**: the recorder sent a real SIGINT after 180 s of saved progress; the run finished in-flight work and stopped at 199.8 s (exit 130) with 36,780 of 200,000 IDs saved and $0.099104 spent. The resume (phase `resume`) started with 145,563 pending distinct texts and completed all 200,000 (`runs/final-200k-v2/recording/`, `grading/checkpoint_before.json` 36,780 IDs, `checkpoint_after.json` 200,000; every enrich call after the interruption has phase `resume`). Live budget drill: a $0.005 cap stopped the run with 353 of 500 IDs saved; a resume under $0.05 completed all 500 (`runs/live-budget-drill/run_summary.json`). Offline demo: SIGINT, resume, warm rerun with zero calls, checker `pass`, fault and budget drills ([`runs/offline-demo-transcript.txt`](../runs/offline-demo-transcript.txt)) |
| Claude Pro plan limit | Found live on 2026-10-14 (`runs/live-analysis10000-low`, first invocation) | The CLI reported "You've hit your session limit" as HTTP 429, which was classed as transient, so verify, group and memo degraded silently. Now a systemic stop in every Claude stage (`insight/providers/claude_code.py`, `insight/memo.py`, `insight/group.py`); the run was resumed with no enrichment calls. Tests: `tests/test_extensions.py` (stub fault `session`), `tests/test_pipeline_fixes.py::TestPlanLimitStopsInsteadOfDegrading` ([docs/walkthrough.md](../docs/walkthrough.md)) |
| Awkward paths | 429, 500, timeout, malformed and truncated output, circuit breaker, insufficient credit | `tests/test_pipeline.py`, `tests/test_extensions.py` and the offline fault drill. Live, final run: 1 HTTP 429, 1 server error, 16 timeouts (900 s, Flex) and 1 connection error were retried with backoff (the 17 with unknown outcome keep their $0.097098 reservation in the spend); 14 outputs were partly valid and their retry tasks made 14 attempts; 0 reviews unfinished (`cost/report.md`, "Scaling decision") |
| Fresh input | `./scripts/fresh_input_demo.sh <csv>`; rehearsed on `fresh_input/rehearsal_60.csv` | See the README, "Fresh-input demonstration" |

## Golden labelling format

How the golden labels were made (done; the result is `golden/golden_50_labeled.csv`). Fill the blank columns of
`golden_50_to_label.csv` (keep the six source columns unchanged), or use `python -m insight label-golden`, which shows
only the review text, saves after every review and writes `evals/golden/golden_50_labeled.csv`:

- `topic`, `intent`, `severity`: one label, or several accepted labels separated by `|` for genuinely
  ambiguous cases (e.g. `playback|downloads`). Ambiguous cases are counted and reported.
- `sentiment`: a number in [-1, 1] (anchors in `docs/labels.md`).
- `entities`: terms separated by `;` (may be blank); `evidence_quote`: the exact supporting substring.
- `needs_review`: `true` or `false`.

Label before looking at model output on these texts, using `docs/labels.md`. Ingest stores only the six
source fields, so the answer columns can never reach a prompt. Do not infer severity or sentiment from the
star rating. If the labels or prompts change after looking at golden failures, disclose it and add fresh
held-out cases for the final check (neither changed here; the golden set was used to choose among frozen
candidate setups, disclosed in `golden/error_analysis.md`). Fifty cases are a diagnostic, not a precise accuracy
estimate.

## Commands

```bash
.venv/bin/python -m insight label-golden                 # a person labels; resumable
./scripts/live.sh golden-candidates                      # billed: enrich the 50 texts with each candidate, then score
./scripts/live.sh quote-support                          # Claude Pro: blind quote-support judge (golden 50 + 500 sampled)
python3 evals/ensemble_golden.py --labels evals/golden/golden_50_labeled.csv \
    --luna runs/golden-luna-none --decisions runs/golden-decisions --out evals/golden/ensemble.json
python3 evals/golden/make_error_analysis.py              # offline: writes golden/error_analysis.md
python3 evals/verification/disagreement_counts.py --run-dir runs/final-200k-v2 --input data/analysis_200k.csv \
    --out evals/verification/disagreement_counts.json
python3 evals/check_synthetic.py runs/live-synthetic-injection
./scripts/offline_demo.sh                                # offline: SIGINT, resume, warm rerun, checker, rank check, planted error, drills
.venv/bin/python -m insight planted-error --run-dir <run>
.venv/bin/python -m insight rank --run-dir <run> --check
```

Synthetic cases live in their own run directories and are never merged into business results.

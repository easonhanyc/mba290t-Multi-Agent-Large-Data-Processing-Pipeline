# Spotify Insight Pipeline (MBA 290T Assignment 5)

A staged program that turns Spotify Google Play reviews into a ranked list of product issues and a short
decision memo. Code ingests and profiles the course CSV and sends each distinct review text once, in
requests of at most 50, to a small model that assigns the contract labels (enrich). A different model
family re-labels a declared random sample without seeing the first answer (verify). Code groups complaints
into issues and a model only names them (group). Code ranks the issues (rank). A model writes the memo
from saved aggregates, and code fills in every number (memo). Every handoff is a saved file or SQLite row,
every model call is logged with tokens and cost, and a stopped run resumes without re-sending finished
reviews. A database, a read-only backend and a dashboard serve the results.

> **Status, 2026-10-14 UTC (complete).** Measured with real model calls: a 100-review cold/warm
> pilot, a live 500-review checkpoint with 1 worker plus a cold 2-worker rerun, two 5-review provider probes,
> a live budget drill, a live prompt-injection test, the 10,000-review checkpoint, and the final run on the
> declared 200,013-row scope (`runs/final-200k`). That run was stopped by a real SIGINT, sent by the recorder
> after 180 s of saved progress (`scripts/record_session.py`), and then resumed; five later invocations
> regenerated group, rank, memo and export from the saved labels with no enrichment calls. The dashboard is
> deployed (see [Dashboard](#dashboard)). Billed API spend over all runs is $2.142643
> (`cost/project_spend.json`, computed 2026-10-14 03:12 UTC). Eason labelled the golden 50 by hand, and
> four setups were scored against those labels ([evals/golden/error_analysis.md](evals/golden/error_analysis.md)).
> Every number below names the file it comes from; estimates are labelled as estimates.

## Where to find everything

Final run: [`runs/final-200k`](runs/final-200k/), on the declared 200,013-row scope (see [Scope](#scope)). Live
dashboard: https://spotify-review-insights-iota.vercel.app (public, read-only, no login).

| What | Files |
|---|---|
| Grading export (file names from `GRADING_CONTRACT.md`; the two JSONL files are gzipped) | [`runs/final-200k/grading/`](runs/final-200k/grading/): [run.json](runs/final-200k/grading/run.json), [ingestion.json](runs/final-200k/grading/ingestion.json), [records.jsonl.gz](runs/final-200k/grading/records.jsonl.gz), [calls.jsonl.gz](runs/final-200k/grading/calls.jsonl.gz), [checkpoint_before.json](runs/final-200k/grading/checkpoint_before.json), [checkpoint_after.json](runs/final-200k/grading/checkpoint_after.json), [membership.csv](runs/final-200k/grading/membership.csv), [ranking.csv](runs/final-200k/grading/ranking.csv), [claims.csv](runs/final-200k/grading/claims.csv) |
| Memo and claims | [memo.md](runs/final-200k/memo.md), [claims.csv](runs/final-200k/claims.csv) (C01-C40), [memo_tokens.csv](runs/final-200k/memo_tokens.csv) (every C/A/S/T token with its value and source file), [memo.json](runs/final-200k/memo.json) |
| Records and quarantine | [enriched.jsonl.gz](runs/final-200k/enriched.jsonl.gz) (200,000 completed records), [quarantine.jsonl](runs/final-200k/quarantine.jsonl) (13 empty texts) |
| Ranking and analysis | [ranking.csv](runs/final-200k/ranking.csv), [aggregates.csv](runs/final-200k/aggregates.csv), [issues.json](runs/final-200k/issues.json), [area_rollup.json](runs/final-200k/area_rollup.json), [analysis/](runs/final-200k/analysis/) (monthly trends with denominators, robustness) |
| Ingestion and run evidence | [ingestion_report.json](runs/final-200k/ingestion_report.json), [data_manifest.json](runs/final-200k/data_manifest.json), [run_summary.json](runs/final-200k/run_summary.json), [run_log.jsonl](runs/final-200k/run_log.jsonl), [invocations/](runs/final-200k/invocations/), [checkpoints/](runs/final-200k/checkpoints/) |
| Course checker results | [self-check.json](runs/final-200k/self-check.json) (declared-scope reference: `pass`, coverage candidate 1.0); [self-check-vs-full-reference.json](runs/final-200k/self-check-vs-full-reference.json) (full-file reference: `review_required`, coverage candidate 0.4422) |
| Rank check | [rank_check.json](runs/final-200k/rank_check.json) (identical, 22 issues) |
| Independent verification | [verification/report.json](runs/final-200k/verification/report.json), [disagreements.csv](runs/final-200k/verification/disagreements.csv) (762 rows), [disagreement analysis](evals/verification/disagreement_analysis.md) |
| Golden-50 evaluation | [error_analysis.md](evals/golden/error_analysis.md), [results.json](evals/golden/results.json), [results_disagreements.md](evals/golden/results_disagreements.md), labels in [golden_50_labeled.csv](evals/golden/golden_50_labeled.csv) |
| Planted error | [planted_error.json](runs/final-200k/evals/planted_error.json) (`detected`) |
| Prompt injection | [synthetic_check.json](runs/live-synthetic-injection/evals/synthetic_check.json) (8 of 8 passed; copy in [evals/injection/](evals/injection/synthetic_check.json)) |
| Interruption and resume recordings | [1-initial-interrupted.cast](runs/final-200k/recording/1-initial-interrupted.cast) and [.txt](runs/final-200k/recording/1-initial-interrupted.txt), [2-resume.cast](runs/final-200k/recording/2-resume.cast) and [.txt](runs/final-200k/recording/2-resume.txt); console logs [final_initial_console.log](runs/final_initial_console.log) and [final_resume_console.log](runs/final_resume_console.log) |
| Cost | [cost/report.md](cost/report.md), [cost/README.md](cost/README.md), [cost/project_spend.json](cost/project_spend.json) |
| Final-run state database | release asset (below) |

**Watching the interruption and resume.** In the initial invocation, the recorder sent a real SIGINT after
180 s of saved progress (`scripts/record_session.py`). The run finished its in-flight batches and stopped at
208.4 s with 34,638 IDs saved. The resume used the same command (phase `resume`) and completed all 200,000 in
8,766.0 s (`runs/final-200k/run_summary.json`; the recorder's end lines are in the `.txt` files). To watch:

- the dashboard's **Run & cost** tab plays both recordings in the browser;
- `asciinema play -i 2 runs/final-200k/recording/1-initial-interrupted.cast` and
  `asciinema play -i 2 runs/final-200k/recording/2-resume.cast` (`-i 2` caps idle pauses at 2 s; add `-s 10`
  to speed up the 2.4-hour resume);
- or read the plain-text transcripts `1-initial-interrupted.txt` and `2-resume.txt` (GitHub does not render
  `.cast` files).

**Not in git: the final-run state database.** `runs/final-200k/state.sqlite` is published as the asset
`final-200k-state.sqlite.gz` of the release
https://github.com/easonhanyc/mba290t-Multi-Agent-Large-Data-Processing-Pipeline/releases/tag/final-200k. To restore it:

```bash
gunzip -c final-200k-state.sqlite.gz > runs/final-200k/state.sqlite
shasum -a 256 runs/final-200k/state.sqlite   # 2c7aa469b46d8ad18d329c4ace4970943b691d75d5818ec91df6ea590c95ecda
```

The asset was replaced after the last post-run regeneration, so it holds all seven invocations of the run,
including the memo regenerations (checksum above). The checker, the rank check and the calculator replay
below do not need it (the calculator reproduces project spend from the committed per-call evidence in
`cost/refreshes/`). It backs the figures this README attributes to the `calls`, `invocations` and
`stage_cache` tables of `runs/final-200k/state.sqlite`: the per-call cost and token log, 172 HTTP 429
retries, 10 invalid enrichment outputs, workers and budgets per invocation, and the earlier memo and naming
outputs. `python -m insight trace` also reads it.

**Reproducing the grading checks.** These run offline with no API key. They need the course dataset folder
(see [Quick start](#quick-start-no-api-key)).

```bash
D="Final Assignment - Spotify Reviews Dataset"
# 1. Checker against the declared scope: expect pass, 0 issues, coverage candidate 1.0
python3 scripts/make_analysis_subset.py      # writes data/analysis_200k.csv (SHA-256 3c023c9d..., see data/analysis_200k.manifest.json)
.venv/bin/python "$D/check_submission.py" reference --full "$D/spotify_reviews_18months.csv" \
    --analysis data/analysis_200k.csv --out /tmp/ref-declared.json
.venv/bin/python "$D/check_submission.py" check --reference /tmp/ref-declared.json \
    --submission runs/final-200k/grading --out /tmp/check-declared.json
# 2. Checker against the full file: expect review_required, coverage candidate 0.4422 (460,609 rows not classified)
.venv/bin/python "$D/check_submission.py" reference --full "$D/spotify_reviews_18months.csv" \
    --analysis "$D/spotify_reviews_18months.csv" --out /tmp/ref-full.json
.venv/bin/python "$D/check_submission.py" check --reference /tmp/ref-full.json \
    --submission runs/final-200k/grading --out /tmp/check-full.json
# 3. Ranking rebuilt from grading/ with no model calls: expect identical, 22 issues
.venv/bin/python -m insight rank --run-dir runs/final-200k --check
# 4. Offline cost calculator replay (no key): recomputes cost/report.md, cost/report.json and cost/project_spend.json
python3 cost/calculator.py
```

The two checker reports should carry `reference_sha256` `363b06ce...` (declared scope) and `bb31d47d...` (full
file), the same values as the saved `self-check.json` and `self-check-vs-full-reference.json`. Both were rerun
with these commands and matched on 2026-10-13. Besides the calculator, which rewrites its three output
files in `cost/`, two of the commands rewrite tracked files. `make_analysis_subset.py` also rewrites `data/analysis_200k.manifest.json` (only `created_at` changes), and the
rank check rewrites `rank_check.json` (only `checked_at` changes).

## Rubric map

| # | Rubric item | Evidence (files and commands) | Status |
|---|---|---|---|
| D1 | Accessible code, setup and artifacts | this README; `requirements.txt`, `web/requirements.txt`; blank `.env.example`; `.gitignore` (`.env`, `.env.*`, `!.env.example`); [Quick start](#quick-start-no-api-key) | Built. Public repo: https://github.com/easonhanyc/mba290t-Multi-Agent-Large-Data-Processing-Pipeline. Dashboard (public and read-only, no login): https://spotify-review-insights-iota.vercel.app. Evidence index and grader commands: [Where to find everything](#where-to-find-everything) |
| D2 | Architecture, shared schema, provenance | [docs/architecture.md](docs/architecture.md) (diagram with six stages, code/model boundaries, stop/retry paths, DB/backend/dashboard); [docs/labels.md](docs/labels.md) (contract labels plus our subtopics); `label_config`, `labeled_by` and `cache_source_id` on every record in `runs/<run>/grading/records.jsonl`; every attempt in `grading/calls.jsonl` | Built; exercised by the live pilot, 500, 10k and final runs |
| D3 | Memo numbers trace to calculations and evidence | `memo.md` + `claims.csv`: the model writes claim tokens, code fills each number from saved aggregates; the course checker recomputes claims; `web/load_db.py` re-checks every claim in SQL | Final run: `runs/final-200k/memo.md` (source: model) with 40 claims, C01-C40, in `claims.csv` (top 10 issues x 4 metrics); the course checker found 0 issues against the declared-scope reference (`runs/final-200k/self-check.json`). Also ran on the 500 checkpoint (40 claims, `runs/live-checkpoint500/run_summary.json`) |
| D4 | Coherent recommendation, alternatives, limitations | `prompts/memo_v2.md`; `insight/analysis.py` (monthly trends with denominators, same-month comparison, intervals, enricher-vs-verifier robustness); [Limitations](#limitations) | Final memo recommends billing/support (the Premium-only issue, framed as free-tier packaging and entitlement policy), with four next-quarter actions, what would change the call, usability, playback/performance and access/onboarding as alternatives, and a robustness caveat (verifier labels put playback/performance first); summary under [Results](#results) |
| T1 | 50 human golden labels, per-field comparison, error analysis | `python -m insight label-golden` (`insight/label_tool.py`); `python -m insight golden` (`insight/golden.py`: per-field agreement, severity MAE, ambiguous count, confusion table, quote/entity checks, needs_review); `evals/ensemble_golden.py`; [evals/README.md](evals/README.md) | Done: 50 labels by Eason (`evals/golden/golden_50_labeled.csv`, workbook + `convert_labels.py`); 4 setups compared; [error analysis](evals/golden/error_analysis.md) and [every disagreement](evals/golden/results_disagreements.md) |
| T2 | Independent verification, planted error, injection | Verify stage (Claude Haiku, blind, declared 10% sample); `python -m insight planted-error`; `evals/synthetic/` + `evals/check_synthetic.py` | Verification measured on the live 500 (below). Injection: 8 of 8 synthetic cases passed with the live enricher (`runs/live-synthetic-injection/evals/synthetic_check.json`, copy in `evals/injection/`). Final run: 2,000-review verifier sample (see [Results](#results)), with its 762 disagreements counted and a sample inspected in [evals/verification/disagreement_analysis.md](evals/verification/disagreement_analysis.md); planted error `detected` (`runs/final-200k/evals/planted_error.json`; also on the offline stub run, `runs/offline-stub-checkpoint500/evals/planted_error.json`) |
| T3 | Real 100-review cold/warm pilot, offline calculator, retry/spend/recovery controls | [cost/report.md](cost/report.md) "Measured 100-review pilot" and "Scaling decision"; `cost/pilot_records.jsonl`, `pilot_calls.jsonl`, `usage.csv`, `rates.csv`, `assumptions.json`, `pilot_runs.json`; `python3 cost/calculator.py`; `tests/test_calculator.py`; [Cost and spend controls](#cost-and-spend-controls) | Pilot measured; 500 refresh saved (`cost/refreshes/checkpoint_500.json`). Live budget drill: a $0.005 cap stopped the run with 353 of 500 IDs saved, and a resume under $0.05 finished all 500 (`runs/live-budget-drill/run_summary.json`). Retry and fault handling shown offline (`runs/offline-stub-fault-drill-500`, `tests/test_pipeline.py`) and live: the final run retried 172 HTTP 429 (Flex capacity) responses and 10 invalid enrichment outputs and ended with 0 unfinished (`calls` table, `runs/final-200k/state.sqlite`, release asset). Final-run interruption: a real SIGINT sent by the recorder after 180 s of saved progress (`scripts/record_session.py`) stopped it at 208.4 s with 34,638 IDs saved; the resume completed all 200,000 (`runs/final-200k/run_summary.json`, `history`) |
| W1 | Full ingestion, record coverage, classification | `insight/ingest.py` profiles the full file with the provided helper (`--full`) whatever the scope; `grading/ingestion.json`, `grading/records.jsonl` | Declared 200,013-row subset; full file profiled (660,622 rows, `runs/final-200k/grading/ingestion.json`); 200,000 completed, 13 quarantined, 0 unfinished. Checker: `pass`, 0 issues, coverage candidate 1.0 against a reference built from the declared subset (`runs/final-200k/self-check.json`); `review_required`, coverage candidate 0.4422 against a full-file reference (`runs/final-200k/self-check-vs-full-reference.json`), because the 460,609 rows outside the subset are not classified. See [Scope](#scope) |
| W2 | Staged program, bounded calls, saved handoffs, demonstrated resume | `python -m insight run --input <csv> --run-dir runs/<name>`: six stages, at most 50 reviews per request, one SQLite state per run, rerun = `phase resume`. Offline demo (`scripts/offline_demo.sh`, output in [`runs/offline-demo-transcript.txt`](runs/offline-demo-transcript.txt)): a real SIGINT mid-enrichment (exit code 130, 75 of 500 completed), a resume that completes all 500, a warm rerun with zero model calls, the course checker `pass` (`runs/offline-stub-checkpoint500/self-check.json`), the rank check identical, the planted error detected, and the fault and budget drills | Live final run: [`1-initial-interrupted.cast`](runs/final-200k/recording/1-initial-interrupted.cast)/[`.txt`](runs/final-200k/recording/1-initial-interrupted.txt) (a real SIGINT sent by the recorder after 180 s of saved progress, `scripts/record_session.py`) and [`2-resume.cast`](runs/final-200k/recording/2-resume.cast)/[`.txt`](runs/final-200k/recording/2-resume.txt) (phase `resume`). Both play in the dashboard's Run & cost tab or with `asciinema play -i 2 <file>.cast` (see [Where to find everything](#where-to-find-everything)). `grading/checkpoint_before.json` (34,638 IDs) and `grading/checkpoint_after.json` (200,000 IDs); console logs [`runs/final_initial_console.log`](runs/final_initial_console.log), [`runs/final_resume_console.log`](runs/final_resume_console.log) |
| W3 | Reproducible ranking + deployed dashboard, backend, database, grounded AI recommendations | `python -m insight rank --run-dir <run> --check`; `web/` (static dashboard, FastAPI backend `web/api/index.py`, `web/schema.sql`, `web/load_db.py`) | Deployed: https://spotify-review-insights-iota.vercel.app (public, read-only, no login; see [Dashboard](#dashboard)). Rank check on the final run: identical, 22 issues (`runs/final-200k/rank_check.json`) |

## Results

Measured numbers and estimates are kept apart. Completed means a valid label was saved; accounted-for
includes quarantined and unfinished rows.

**Final run** (`runs/final-200k`; seven invocations listed under `history` in `run_summary.json`, one file
each in `invocations/`):

| What | Value |
|---|---|
| Source rows profiled / rows in declared scope | 660,622 profiled with the provided helper (`runs/final-200k/ingestion.json`) / 200,013 in scope, `data/analysis_200k.csv` (`runs/final-200k/ingestion_report.json`) |
| Completed / quarantined / unfinished | 200,000 / 13 (empty text) / 0: 138,724 primary, 13,639 fallback1, 47,637 exact-text reuses; 16,964 flagged `needs_review` (`runs/final-200k/run_summary.json`) |
| Exact-text cache reuses | 47,637; 152,363 distinct texts went to the model (`runs/final-200k/run_summary.json`) |
| Golden-50 agreement (topic / intent / severity exact) | 76% / 74% / 76%, all three 48%, severity MAE 0.24, sentiment within 0.5: 86% (`evals/golden/results.json`) |
| Verifier sample and disagreements | 2,000 distinct texts (declared 10% sample, capped at 2,000): topic 1,618, intent 1,841, severity exact 1,583, sentiment within tolerance 1,980 of 2,000; 762 sampled reviews differ on at least one field, all listed in `verification/disagreements.csv` (`runs/final-200k/verification/report.json`); patterns and an inspected sample: [disagreement analysis](evals/verification/disagreement_analysis.md) |
| Billed API cost / API-equivalent of Pro calls / wall clock | $2.019246 billed over all invocations (sum of `calls.cost_usd` in `runs/final-200k/state.sqlite`, equal to `ledger.spent_usd` in `run_summary.json`) / $2.0569 API-equivalent, not billed (`cost/report.md`, "Measured refreshes") / 9,334.36 s over seven invocations (`cost/refreshes/final_200k.json`): initial 208.4 s (interrupted), resume 8,766.0 s (enrich 8,374.6 s), then five regeneration invocations of group, rank, memo and export without enrichment, 66.6, 59.0, 56.1, 115.4 and 62.8 s (`runs/final-200k/invocations/*.json`) |
| Enrichment workers / fallback1 | 16 workers in both enrichment invocations, 4 in the five regenerations (`runs/final-200k/invocations/*.json`); fallback1 cap 10% (15,236 texts), all 13,639 staged texts routed (`runs/final_resume_console.log`) |
| Course checker status and coverage candidate | Reference from the full file plus the declared subset: `pass`, 0 issues, coverage candidate 1.0 (`runs/final-200k/self-check.json`). Reference from the full file alone: `review_required`, coverage candidate 0.4422, issues `missing_records` (460,609 IDs), `unfinished_classification` and two `run_manifest_mismatch` (`runs/final-200k/self-check-vs-full-reference.json`). See [Scope](#scope) |
| Ranking | 22 issues from 89,762 complaint and cancellation records; top three `billing.premium_only` 52,577, `other.general` 45,898, `usability.ads` 24,431 (`runs/final-200k/ranking.csv`); rebuilt identically from `grading/` (`runs/final-200k/rank_check.json`) |
| Memo with `claims.csv` IDs | `runs/final-200k/memo.md` (source: model, validated on the first attempt), 40 claims C01-C40 in `runs/final-200k/claims.csv`; every other number (A## area roll-up, S## scope, T## trend and robustness) in `runs/final-200k/memo_tokens.csv` |
| One review traced source -> enrich -> verify -> membership -> ranking -> memo claim, plus one ambiguous or failed case | [docs/trace_example.md](docs/trace_example.md): review `02ccf42f-...` (rank-1 issue `billing.premium_only`, labelled by fallback1, claims C01-C04 cited in the memo; in the verification sample, where the verifier agrees on topic and intent and gives severity 4 against the enricher's 3) and an automatically chosen case B, review `00046c11-...` (flagged ambiguous, routed to fallback1, saved with `needs_review`) |

**Final recommendation** (`runs/final-200k/memo.md`, run `run-20261013T233959.792Z-f394`; the model wrote
tokens and code filled every number; C## IDs are in `claims.csv`, A## and T## IDs in `memo_tokens.csv`): put
next quarter's effort into **billing/support**. It has the highest baseline priority of the four areas, a
severity sum of 59,146 (A02) against 54,124 for usability (A05), 46,058 for playback/performance (A08) and
11,172 for access/onboarding (A17) (`runs/final-200k/area_rollup.json`). Almost all of it is the Premium-only
restrictions issue (`billing.premium_only`: 18,016 complaints (C01), severity sum 52,577 (C02), mean
2.918350 (C03)), the largest issue in the ranking. The memo frames that issue as a free-tier packaging and
entitlement policy question (what the free tier includes, such as skip limits, forced shuffle and not being
able to pick, repeat or rewind songs, and how changes to it are rolled out and explained), not a payment,
checkout or support-backlog defect. The area's share of reviews grew from 4.5% (T10) in 2022 Jun-Oct to
15.4% (T11) in 2023 Jun-Oct, +10.9 pp (T12), the largest increase of the four decision areas, and
`billing.premium_only` led the October 2023 volume spike (+25.1 pp share of complaints against other months,
T38).

- **Next-quarter actions** (memo): pilot clearer in-app messaging and a staged rollout of free-tier limits,
  testing whether the issue's complaint count (C01) or severity sum (C02) falls; review whether specific
  free-tier controls (skip limits, forced shuffle, repeat/rewind) can be partly restored or better explained,
  aiming to lower the area's share of complaints (0.226042, A03); as a hedge, a scoped investigation of
  playback stability (severity sums: stops/skips 16,288 (C14), crashes 11,618 (C22)); and monitor the area's
  trend share (+10.9 pp, T12) into the next comparable period.
- **What would change the call**: a larger verified sample confirming the verifier's ordering, with
  playback/performance (758, T46) ahead of billing/support (661, T48) on severity sum; billing/support's
  share falling back toward its earlier 4.5% (T10) in the same months a year later; or the October 2023
  premium-only lift (+25.1 pp, T38) fading to the other months' level.
- **Alternatives**: usability (second on baseline priority, 54,124 (A05); the largest complaint share of the
  four areas, 25.6% (T19), and first by complaint count under both label sets in the verification sample,
  but its share of reviews rose only +0.7 pp (T18)); playback/performance (46,058 (A08), share of reviews
  -5.0 pp (T15), though first under the verifier's labels); access/onboarding (smallest, 11,172 (A17), led
  by login failures, severity sum 9,370 (C30)).
- **Robustness caveat**, stated in the memo: on the 2,000-review verification sample (T41) the enricher's
  labels put billing/support first on the same metric (787, T42) and the verifier's put playback/performance
  first (758, T46) and billing/support third (661, T48), so the memo calls the lead provisional pending a
  larger verified sample (`runs/final-200k/analysis/robustness.json`). Within sampling intervals
  billing/support's complaint share (22.6%, T22) is close to usability's (25.6%, T19).

**Error found and fixed after the run.** The first naming pass gave the naming model each issue's 8
highest-severity quotes. It named the catch-all `other.general` "Privacy and data collection concerns"
(`stage_cache` in `runs/final-200k/state.sqlite`), although only 8 of its 14,796 distinct complaint texts
mention privacy (`insight/group.py`, `evidence_pack`). Fix: naming evidence is now a deterministic uniform
sample of 12 member texts per issue, and the catch-alls `other.general` and `usability.other` keep their
taxonomy names (`config/pipeline.toml` `[group]`, `insight/group.py`). The same check found that the
verifier robustness check compared areas by complaint count, not by the baseline metric. It now uses the
row-weighted severity sum (`insight/analysis.py`), the memo prompt judges the top area on that metric
(`prompts/memo_v2.md`), and the memo model now sees the trend values (`insight/memo.py`). Group, rank, memo
and export were regenerated from the saved labels in five short invocations (66.6, 59.0, 56.1, 115.4 and
62.8 s, 4 workers, no enrichment calls; `runs/final-200k/invocations/`). Labels were not touched: the ranking
saved by the original resume invocation has the same top five issues and the same 89,762 memberships
(`runs/final-200k/invocations/run-20261012T233254.463Z-c2b5.json`). The recommendation did change. The first
two model memos (resume and first regeneration) recommended usability, while the robustness check still
compared complaint counts; the next two recommended billing/support, after it switched to the row-weighted
severity sum (memo outputs in `stage_cache`). The memo prompt was then strengthened to ask for concrete
next-quarter actions and what would change the call, and to frame `billing.premium_only` as free-tier
packaging and entitlement policy (`prompts/memo_v2.md`). In the next invocation both memo attempts were
invalid (digits typed outside tokens), so it fell back to the template memo
(`runs/final-200k/invocations/run-20261013T233601.448Z-8794.json`, memo source "template (model memo failed
validation)").
The cause was fixed by turning the spike months and comparison periods into tokens (`insight/memo.py`), and
the last invocation's model memo validated on its first attempt (`memo.json`: no rejected outputs, no
validation problems). Over the whole run that is 22 group calls (12 in the resume, 10 in the first
regeneration) and 7 memo attempts (5 valid, 2 invalid), all through `claude -p` on Claude Pro, $0 billed
(`runs/final-200k/grading/calls.jsonl.gz`).

**Measured development runs** (real model calls):

| Run | Rows | Workers | Completed | Enrichment calls | Billed API | API-equivalent (Pro, not billed) | Wall clock | Source |
|---|---:|---:|---|---:|---:|---:|---|---|
| Pilot, cold | 100 | 1 | 100 (99 primary, 1 fallback1) | 3 | $0.001339 | $0.127723 | 159.5 s | `cost/report.md`, `runs/pilot100-20261012T224901Z/run_summary.json` |
| Pilot, warm (same run dir) | 100 | 1 | 100 (100 result-cache hits) | 0 | $0.000000 | $0.000000 | 0.038 s | `cost/report.md` |
| checkpoint_500 | 500 | 1 | 500 (472 primary, 7 fallback1, 21 exact-text reuses) | 17 | $0.005175 | $0.1698 | 396.6 s, all stages (enrich 266.8 s) | `runs/live-checkpoint500/run_summary.json`, `cost/report.md` |
| checkpoint_500, cold rerun | 500 | 2 | 500 (same split) | 17 | $0.004250 | not run (ingest, enrich, export only) | 154.3 s (enrich 154.3 s) | `runs/live-checkpoint500-w2/run_summary.json` |
| analysis_10000 | 10,000 | 8 | 10,000 (8,322 primary, 126 fallback1, 1,552 exact-text reuses) | 299 | $0.096326 | $0.7680 | 931.6 s, all stages (enrich 728.4 s) | `runs/live-analysis10000/run_summary.json`, `cost/report.md` |

On the 500 checkpoint the verifier re-labelled a 48-review sample and agreed with the enricher on topic
41/48, intent 45/48 and severity 39/48; sentiment was within tolerance 48/48
(`runs/live-checkpoint500/verification/report.json`). The 1-worker and 2-worker runs labelled the same
500 reviews identically on topic 482/500, intent 489/500, severity 484/500 and all three 466/500 (read-only
SQL join of `results` by `review_id` across the two `state.sqlite` files).

**Estimates** (`cost/report.md`, "Estimated runs"; per-unit inputs measured on the final run, 16 workers at
the measured 94.7% enrichment-pool utilisation; not measurements): the full 660,622-row file would cost
$6.42 billed (base, with reuse) up to $13.09 (conservative, no reuse) and take 7.7 to 15.97 hours; both
conservative cases exceed the $9.00 project cap, and 3 of the 4 scenarios exceed the $6.86 left under it.
For the declared scope it gives $2.02 and 2.5 h (base, with reuse) to $3.96 and 4.93 h (conservative, no
reuse). Checked against the measured run, the base projection gives 8,995.4 s against 8,974.4 s measured over
the two enrichment invocations (ratio 1.002); the enrichment row agrees by construction because the
utilisation is measured on the same run, while verify (300.0 vs 288.6 s), group (90.0 vs 46.0 s) and memo
(15.0 vs 44.7 s) are independent checks ("Projection check against the measured run"). The "Scaling
decision" section of `cost/report.md` shows how the estimate was refreshed after each measured step: the
last step before the final run (analysis_10000) gave $1.75 (base, with reuse) to $3.43 (conservative, no
reuse) for the declared scope.

**Baseline ranking rule** (`insight/rank.py`): complaint and cancellation records are grouped by
`issue_id = topic.subtopic`; `priority_score = severity_sum` (= complaint count x mean severity, mean
rounded half-up to 6 places); sort by score descending, then `issue_id` ascending. No model is involved.

## Scope

**Final scope: the declared subset** (option 1 below), run in `runs/final-200k`. Two options were prepared:

1. **Declared subset**: `data/analysis_200k.csv`, 200,013 rows = the first 200,000 eligible rows in the
   course's SHA-256 seed order plus the 13 empty texts, which are quarantined. It contains the golden 50,
   `cost_100`, `checkpoint_500` and `analysis_10000`; 152,363 distinct texts; SHA-256 `3c023c9d...`
   (`data/analysis_200k.manifest.json`). The CSV is git-ignored; regenerate it with
   `python3 scripts/make_analysis_subset.py`.
2. **Full file**: all 660,622 rows (660,609 nonempty, 13 empty; `Final Assignment - Spotify Reviews Dataset/README.md`).

The assignment Google Doc allows a run "of at least 100,000" ("What You Are Submitting" item 3 and
"Definition of Done"). The course checker, however, computes the coverage point as
0.2 x profile match + 0.2 x (completed + quarantined) / expected rows + 0.6 x classified nonempty / nonempty
rows (`check_submission.py`, line 379), where the denominators come from the grader's reference. If that
reference is built from the full file, they are 660,622 and 660,609, and a complete 200,013-row run would
score about 0.2 + 0.2 x 0.3028 + 0.6 x 0.3028 = 0.44 of the point. The full file is profiled with the
provided helper in either case, so the profile term does not depend on scope. The 460,609 rows outside the
subset are ingested and profiled but not classified (`data/analysis_200k.manifest.json`), and the memo,
`run.json` and dashboard say so.

Both checker results on the final export are saved. Against a reference built from the full file plus
the declared subset it returns `pass` with 0 issues and coverage candidate 1.0
(`runs/final-200k/self-check.json`). Against a reference built from the full file alone it returns
`review_required` with coverage candidate 0.4422, reporting the 460,609 missing records, the unfinished
classification and a manifest mismatch on the analysis count and SHA-256
(`runs/final-200k/self-check-vs-full-reference.json`). Which reference the grader uses decides the coverage
point.

## Quick start (no API key)

```bash
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

The course dataset folder `Final Assignment - Spotify Reviews Dataset/` is git-ignored: unzip the course
ZIP into it (it holds the CSVs, `manifest.json` and `check_submission.py`).

```bash
# 1. Offline calculator replay: recomputes cost/report.md, report.json and project_spend.json from saved usage x rates
python3 cost/calculator.py

# 2. Offline stub run of every stage on checkpoint_500 (local test server; stub labels are meaningless)
./scripts/offline_demo.sh            # sends a real SIGINT (kill -INT) mid-run, then resume, warm rerun, checker, rank check, drills
                                     # last run's output: runs/offline-demo-transcript.txt (every step passed)
.venv/bin/python -m insight run --input "Final Assignment - Spotify Reviews Dataset/checkpoint_500.csv" \
    --run-dir runs/offline-stub-demo --offline-stub

# 3. Tests (74 tests across tests/*.py; all pass offline)
.venv/bin/python -m unittest discover -s tests

# 4. Ranking rebuilt from saved files, no model calls
.venv/bin/python -m insight rank --run-dir runs/live-checkpoint500 --check

# 5. Course checker on a saved grading/ export (reference built from the same input)
D="Final Assignment - Spotify Reviews Dataset"
.venv/bin/python "$D/check_submission.py" reference --full "$D/checkpoint_500.csv" --analysis "$D/checkpoint_500.csv" --out /tmp/ref500.json
.venv/bin/python "$D/check_submission.py" check --reference /tmp/ref500.json --submission runs/live-checkpoint500/grading --out /tmp/check500.json
```

For the final run, `./scripts/live.sh finalize` (offline) builds the reference from the full file and the
declared scope, runs the checker, the rank check, the planted-error test, the trace, the golden scoring and
a calculator refresh. On the final export the checker returned `pass` (0 issues, coverage candidate 1.0)
against the declared-scope reference and `review_required` (coverage candidate 0.4422) against a full-file
reference (`runs/final-200k/self-check.json`, `self-check-vs-full-reference.json`; see [Scope](#scope)). The
exact commands for both checker references, the rank check and the calculator replay are under [Where to find
everything](#where-to-find-everything). The golden-50 scoring has been run against Eason's labels
(`evals/golden/results.json`; see [Evaluation](#evaluation)).

## Architecture

Six stages coordinated by code (`insight/cli.py`), each with its own instructions, inputs, outputs and saved
evidence; then a database load, a backend and a dashboard. Models answer bounded questions; code owns record
accounting, validation, arithmetic, budgets, retries and every routing decision. Diagram, stage table,
state and resume rules: [docs/architecture.md](docs/architecture.md). Label definitions and the output
schema: [docs/labels.md](docs/labels.md).

| # | Stage | Owner | Key output |
|---|---|---|---|
| 1 | Ingest | code | `ingestion_report.json`, `ingestion.json` (provided helper, full file), `data_manifest.json` |
| 2 | Enrich | GPT-6 Luna + code | `enriched.jsonl`, `quarantine.jsonl` |
| 3 | Verify | Claude Haiku + code | `verification/report.json`, `disagreements.csv` |
| 4 | Group | code membership + Claude Sonnet names | `membership.csv`, `issues.json` |
| 5 | Rank (+ analysis) | code | `ranking.csv`, `aggregates.csv`, `area_rollup.json`, `analysis/` |
| 6 | Memo | Claude Sonnet + code | `memo.md`, `memo.json`, `claims.csv` |

Design points: classification input is `review_text` only (stars and other columns never reach a model;
tested); evidence quotes are exact slices chosen by sentence number and entities are matched by code;
exact-text reuse gives one result per distinct text with `cache_source_id` provenance; results are saved
per batch and never relabelled under the same `label_config`; difficult reviews are staged and routed to
the capped fallback only after every primary result is in, so the selection does not depend on worker count
or interruptions.

## Models and why

Full reasoning and the measurements behind it: [docs/model_choice.md](docs/model_choice.md).

| Role | Model (as logged) | Setting | Billing |
|---|---|---|---|
| Enrich, primary | `gpt-6-luna` (OpenAI Responses) | effort none, Flex tier, 50 reviews/request | billed API |
| Enrich, fallback1 | `gpt-6-luna` | effort low, 1 review/request, cap 10% of distinct texts (1.5% up to the 10k checkpoint) | billed API |
| Enrich, fallback2 | Claude Sonnet via `claude -p` (alias `sonnet`; never routed so far) | effort low, cap 0.25% | Claude Pro subscription |
| Verify | `claude-haiku-4-5-20251001` via `claude -p` | blind, declared 10% random sample, at most 2,000 | Claude Pro subscription |
| Group (names only) | `claude-sonnet-5` via `claude -p` | top 12 issues, 12 sampled member quotes each; catch-all issues keep their taxonomy names | Claude Pro subscription |
| Memo | `claude-sonnet-5` via `claude -p` | aggregates + evidence pack, claim tokens only | Claude Pro subscription |

Model IDs are from the `calls` table (`model_reported`) of `runs/live-checkpoint500/state.sqlite` and
`runs/final-200k/state.sqlite`. Each role's model is fixed in `config/pipeline.toml`; nothing chooses a model
at run time. Before any live call, `insight/cli.py` refuses to start if a configured provider/model has no
dated row in `cost/rates.csv`, so an unpriced model cannot run under the spend cap (see
[docs/architecture.md](docs/architecture.md), "Model allowlist"). Calls through `claude -p` cost $0 per call
under Eason's fixed-fee Claude Pro plan. The course says subscription
access is not evidence that programmatic calls are free (`COST_CALCULATOR.md`), so the calculator reports
their API-equivalent price separately and never adds it to billed spend.

Built and tested but not used at scale: a `hybrid` backend (Luna labels plus an OpenAI Decisions API
cross-check of intent and severity) and a `decisions` backend (Decisions alone). On 2026-10-12 the Decisions
beta allowed this account 50 requests, with one request restored every 28m48s, so 50 per day
(`x-ratelimit-limit-requests 50`), and billed 1,812-2,018 input tokens per one-review request with no cached
tokens (`runs/probe-decisions/state.sqlite`, `calls.usage_raw`). The batched Luna probe on the same account
reported 5,000 requests and 2,000,000 tokens per minute (`runs/probe-luna/state.sqlite`). Jev (TypeSafe)
was not run: it needs a $5 minimum purchase against a $10 total project budget (`cost/report.md`,
`config/pipeline.toml`). On the golden 50, effort low scored best (80% / 76% / 76%, all three 54%) against
effort none (74% / 70% / 72%, 46%) and Decisions (76% / 74% / 68%, 48%); the gap is 4 reviews (exact McNemar
p = 0.125). The labels arrived after the final run, which already uses effort low for its 13,639 flagged texts,
so the run was kept and the choice is disclosed in [docs/model_choice.md](docs/model_choice.md).

## Cost and spend controls

Full report: [cost/report.md](cost/report.md) (regenerate offline with `python3 cost/calculator.py`).
Calculator guide: [cost/README.md](cost/README.md).

- Per-run cap `--budget-usd`: before each attempt the ledger reserves the worst case; admission stops when
  spent + unknown + reserved + next reservation would cross the cap.
- Project cap `run.project_cap_usd = 9.00` (`config/pipeline.toml`): billed spend summed over every
  `runs/**/state.sqlite`. An unreadable run database fails closed; live runs must live under `runs/`; one
  live run at a time (`runs/.live.lock`).
- Prepaid OpenAI credit with auto-recharge off. An insufficient-credit error stops the run immediately.
- Unknown charges (timeouts, dropped connections) keep their reservation.
- Bounded exponential backoff with jitter (up to 4 attempts), one retry for invalid output, a circuit
  breaker after 5 consecutive exhausted requests, graceful Ctrl-C. SDK-internal retries are disabled so every
  attempt is priced and logged.

Billed spend by run (`cost/project_spend.json`, computed 2026-10-14 03:12 UTC): final run $2.019246,
analysis_10000 $0.096326, golden candidates $0.00909 (Decisions), $0.000866 (Luna, effort low) and $0.00067
(Luna, effort none), checkpoint_500 $0.005175 (1 worker) and $0.004250 (2 workers), budget drill $0.004306,
pilot $0.001339, probes $0.000942 (Decisions) and $0.000198 (Luna), injection test $0.000234; total
$2.142643 against the $9.00 project cap. The calculator reproduces this total offline: each of the 17,292
billed-provider calls is priced as usage x `rates.csv` and counted once by request ID, from a run's
`state.sqlite` when present and otherwise from the committed per-call evidence in `cost/refreshes/`, so it
does not need the git-ignored final-run database (`cost/report.md`, "Spending controls and spend to date").
The final run's per-run cap was $4.00 for the two enrichment invocations and $2.10 for the five
regenerations, with 0 budget denials (`runs/final-200k/invocations/*.json` and `ledger` in
`runs/final-200k/run_summary.json`).

The live budget drill (`./scripts/live.sh budget-drill`, `runs/live-budget-drill`) shows the per-run cap
working with real calls: with `--budget-usd 0.005` the run stopped with `stop_reason budget_cap` after
$0.002979 of spend, 353 of 500 IDs saved and 147 unfinished; the same command under `--budget-usd 0.05`
resumed (phase `resume`), sent only the 129 pending distinct texts plus the capped fallbacks and completed
all 500 (`run_summary.json` history, `runs/drill_console.log`; budgets in the `invocations` table of its
`state.sqlite`).

## Evaluation

Details and commands: [evals/README.md](evals/README.md).

- **Golden 50** (labelled by Eason): final run topic 76%, intent 74%, severity exact 76% (MAE 0.24),
  sentiment within 0.5 for 86%; no ambiguous multi-label cases; every quote an exact substring. Half the intent
  misses (7 of 13) are a documented convention difference (Eason labels "reports a problem and asks for a fix"
  as request; the contract precedence gives complaint): without them intent agreement is 86%. Details:
  [evals/golden/error_analysis.md](evals/golden/error_analysis.md).
  Human labels are never ingested or used in prompts; the ingest stores the six source fields only.
- **Independent verification**: Claude Haiku labels a declared random sample blind. Final run: 2,000
  reviews, topic 1,618, intent 1,841, severity 1,583 and sentiment 1,980 agree; the 762 reviews that differ
  on at least one field are in `runs/final-200k/verification/disagreements.csv`
  (`runs/final-200k/verification/report.json`). Live 500: see [Results](#results).
- **Verifier disagreements investigated**: [evals/verification/disagreement_analysis.md](evals/verification/disagreement_analysis.md)
  counts the 762 by field and direction. The largest patterns are severity 3 -> 4 (165) and usability -> other
  on topic (65). It also gives the AI assistant's reading of 38 inspected cases against the rubric (a random
  20 plus two targeted samples); these are not human labels.
  - The boundary that matters for the recommendation is `billing.premium_only` versus usability/playback. The
    verifier puts 71 of the 235 sampled premium-only texts in another topic, and 47 of those 71 contain no Premium or
    payment word (a keyword check).
  - The rubric is inconsistent there. The `docs/labels.md` boundary notes put described free-tier limits in
    premium-only, while both prompts require that "the customer says" the feature is locked behind Premium.
- **Run-to-run reproducibility**: same 500 reviews, same `label_config`, 1 vs 2 workers (see
  [Results](#results)).
- **Planted wrong label**: `python -m insight planted-error --run-dir <run>` corrupts one label in a test
  copy and checks that the saved verifier output flags it. Detected on the offline stub run and on the
  final run: the test copy of review `00015590-...` was changed from catalog / praise / severity 1 to
  billing / complaint / severity 5, and the saved verifier label (catalog / praise / 1) disagrees on topic,
  intent, severity and sentiment (`runs/final-200k/evals/planted_error.json`).
- **Reproducible ranking**: `python -m insight rank --run-dir runs/final-200k --check` rebuilt the 22-issue
  ranking from `grading/` identically (`runs/final-200k/rank_check.json`).
- **Prompt injection**: `evals/synthetic/injection_cases.csv` (8 cases marked synthetic, own run directory,
  never in business results). With the live enricher all 8 passed: injected instructions were read as review
  content, markup and JSON fragments did not break requests, and the 2 empty or whitespace-only texts were
  quarantined by code (`runs/live-synthetic-injection/evals/synthetic_check.json`, billed $0.000234 per
  `runs/live-synthetic-injection/run_summary.json`).

## Dashboard

- **Live URL**: https://spotify-review-insights-iota.vercel.app
- **Access**: open the URL in any browser. It is public and read-only; no account or login is needed. Tabs:
  Overview, AI recommendation, Issue ranking, Trends, Evaluation, Run & cost, Review lookup. The Run & cost tab
  plays the two final-run recordings (interruption and resume) in an embedded asciinema player. JSON endpoints
  include `/api/health`, `/api/overview`, `/api/ranking`, `/api/recommendation`, `/api/reviews/{review_id}`
  and `/api/consistency`. A signed-out check on 2026-10-14 UTC, after the final database reload, found
  `ranking_matches` true and `claims_match` true on `/api/consistency`. The AI recommendation tab shows the
  final memo with its next-quarter actions and what would change the call; the Evaluation tab shows the
  course checker result against both references (declared scope: `pass`, coverage candidate 1.0; full file:
  `review_required`, 0.4422); the Review lookup tab loaded without console errors.
- Vercel project `spotify-review-insights`: static page `web/public/`, FastAPI function `web/api/index.py`
  (read-only SQL as `dashboard_ro`, a SELECT-only role created by `web/make_readonly_role.py`, which checks
  that the role can read and that a write is refused; no model calls), Neon Postgres with `web/schema.sql`, loaded by
  `web/load_db.py --run-dir <run>`, which checks row counts, the SQL-recomputed ranking against
  `ranking.csv`, and every claim. `/api/consistency` recomputes the ranking and claims at request time.
- Local preview without Postgres (needs `fastapi` and `uvicorn` in the venv):
  `.venv/bin/python web/load_db.py --run-dir <run> --database-url sqlite:///web/local.db`, then
  `DATABASE_URL=sqlite:///web/local.db .venv/bin/python web/dev_server.py --port 8765`.

## Limitations

- Reviews are a self-selected, historical sample of public Google Play reviews, not a customer population.
- There is no revenue, plan-tier or churn data. Cancellation language in a review is not a confirmed
  cancellation.
- Scope: the declared 200,013-row subset. The other 460,609 rows of the full file are profiled but not
  classified, so issue counts and shares describe the subset only (a uniform sample in the course's seed
  order; the memo shows sampling intervals). Against a full-file reference the course checker returns
  `review_required` with a coverage candidate of 0.4422 (`runs/final-200k/self-check-vs-full-reference.json`).
- The recommended area depends on the labeler. On the 2,000-review verification sample the enricher's labels
  put billing/support first by baseline priority and the verifier's put playback/performance first
  (`runs/final-200k/analysis/robustness.json`). The first memos recommended usability; after the post-run
  fixes to the robustness check and the memo prompt the memo recommends billing/support (see
  [Results](#results)).
  - Most of this difference sits at the premium-only boundary.
    4,785 of the 18,016 `billing.premium_only` members contain no Premium or payment word (a keyword check). Their severity sum is
    14,239. Without them, billing/support's 59,146 would fall below usability and playback/performance. This is
    an upper bound, not a relabelling
    ([evals/verification/disagreement_analysis.md](evals/verification/disagreement_analysis.md), section 4).
- Model answers are not deterministic. On the same 500 reviews with the same settings, the 1-worker and
  2-worker runs differed on at least one of topic, intent or severity for 34 of 500 reviews (466/500 agree on
  all three). The routing code gives identical labels for identical answers
  (`tests/test_pipeline.py::test_two_workers_give_identical_labels`, stub), so the differences come from the
  model. Small differences between issue counts should be read with this in mind.
- The verifier is another model, not ground truth. The golden set has 50 cases: a diagnostic, not a
  precise accuracy estimate.
- Claude roles run on a subscription with usage limits; their API-equivalent cost is shown, not billed.
- Star ratings are never used as labels. Many reviews have no app version (159,701 in the full file). The
  first and last months of the extract are partial: rows run from 2022-05-17 up to 2023-11-17 and the last
  review is dated 2023-11-15 (both from `Final Assignment - Spotify Reviews Dataset/README.md`).
- The worked examples in `docs/labels.md` were drafted with the AI assistant from development rows 101-500
  and reviewed by Eason; they illustrate the rubric only and are not part of the golden evaluation.

## Data source and license

Course extract of "3.4 Million Spotify Google Store Reviews" by BwandoWando, Kaggle, version 2 (published
2023-11-17), publisher-listed license CC0: Public Domain:
https://www.kaggle.com/datasets/bwandowando/3-4-million-spotify-google-store-reviews. The course removed the
row index, author names and author IDs. Full CSV SHA-256
`1fc85de68a304dd8978b537cfa58793d5f41cbaf417fa32cb53899f83a2fcef6`; `checkpoint_500.csv` SHA-256
`a94e31663ee7b7eaa77e23b7a8425b530cc0c866ed5e714953172a0afef6a12f`
(`Final Assignment - Spotify Reviews Dataset/README.md` and `manifest.json`).

## Live (billed) steps, for the student

Graders do not need these. Keys go in a local `.env` (git-ignored; see `.env.example`). Without
`--allow-paid` the program refuses live calls. Each step has its own `--budget-usd`; the project cap applies
on top.

```bash
./scripts/live.sh pilot              # done 2026-10-12
./scripts/live.sh checkpoint500      # done 2026-10-12 (1 worker, then a 2-worker cold rerun)
./scripts/live.sh budget-drill       # done 2026-10-12
./scripts/live.sh injection          # done 2026-10-12
./scripts/live.sh golden-candidates  # done 2026-10-12 (predictions); scored 2026-10-13 against evals/golden/golden_50_labeled.csv
./scripts/live.sh analysis10k        # done 2026-10-12 (8 workers)
./scripts/live.sh final-initial      # done 2026-10-12 (16 workers); recorded; SIGINT sent by scripts/record_session.py after 180 s of saved progress
./scripts/live.sh final-resume       # done 2026-10-12; same run dir, phase resume
./scripts/live.sh finalize           # offline
./scripts/live.sh load-db            # offline
```

## Layout

```
insight/              pipeline package (python -m insight); providers/ = OpenAI Responses, OpenAI Decisions,
                      claude -p, Anthropic API and Jev adapters; stub.py = offline test server
config/pipeline.toml  every setting; label-affecting ones are hashed into label_config
prompts/              LLM role prompts and typed-question files
cost/                 calculator, dated rates, editable assumptions, pilot files, refreshes, report
evals/                synthetic injection cases and checker, golden labels and analysis, verifier disagreement analysis
docs/                 architecture, labels and worked examples, model choice
web/                  dashboard, backend, database schema and loader
tests/                unit, integration and calculator tests
scripts/              live.sh (billed steps), offline_demo.sh, make_analysis_subset.py, record_session.py
runs/                 run directories: live-*, probe-*, golden-* and pilot100-20261012T224901Z made real calls;
                      offline-stub-*, pilot100-offline-stub-* and *preflight* made none (plumbing only);
                      runs/*_console.log = console output of the live steps
data/                 declared-scope manifest and probe_dev_5.csv (the 5-row probe input); other CSVs are
                      git-ignored and regenerable
```

Dependencies: Python 3.12.14; `openai==3.23.0`, `anthropic==1.11.0`, `typesafe-sdk==0.7.2`
(`requirements.txt`); `fastapi==0.115.6`, `psycopg[binary]==3.2.3` (`web/requirements.txt`).

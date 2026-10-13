# Spotify Insight Pipeline (MBA 290T Assignment 5)

A staged program that turns Spotify Google Play reviews into a ranked list of product issues and a short
decision memo. Code ingests and profiles the course CSV and sends each distinct review text once, in
requests of at most 50, to a small model that assigns the contract labels (enrich). A different model
family re-labels a declared random sample without seeing the first answer (verify). Code groups complaints
into issues and a model only names them (group). Code ranks the issues (rank). A model writes the memo
from saved aggregates, and code fills in every number (memo). Every handoff is a saved file or SQLite row,
every model call is logged with tokens and cost, and a stopped run resumes without re-sending finished
reviews. A database, a read-only backend and a dashboard serve the results.

> **Status, 2026-10-13 (complete).** Measured with real model calls: a 100-review cold/warm
> pilot, a live 500-review checkpoint with 1 worker plus a cold 2-worker rerun, two 5-review provider probes,
> a live budget drill, a live prompt-injection test, the 10,000-review checkpoint, and the final run on the
> declared 200,013-row scope (`runs/final-200k`), stopped by a real Ctrl-C and resumed. The dashboard is
> deployed (see [Dashboard](#dashboard)). Billed API spend over all runs is $2.142643
> (`cost/project_spend.json`, computed 2026-10-13 02:10 UTC). The golden 50 were labelled by hand by Eason and
> four setups were scored against them ([evals/golden/error_analysis.md](evals/golden/error_analysis.md)).
> Every number below names the file it comes from; estimates are labelled as estimates.

## Rubric map

| # | Rubric item | Evidence (files and commands) | Status |
|---|---|---|---|
| D1 | Accessible code, setup and artifacts | this README; `requirements.txt`, `web/requirements.txt`; blank `.env.example`; `.gitignore` (`.env`, `.env.*`, `!.env.example`); [Quick start](#quick-start-no-api-key) | Built. Dashboard public and read-only, no login: https://spotify-review-insights-iota.vercel.app. `public repo https://github.com/easonhanyc/mba290t-Multi-Agent-Large-Data-Processing-Pipeline; dashboard and API checked signed-out (no login)` |
| D2 | Architecture, shared schema, provenance | [docs/architecture.md](docs/architecture.md) (diagram with six stages, code/model boundaries, stop/retry paths, DB/backend/dashboard); [docs/labels.md](docs/labels.md) (contract labels plus our subtopics); `label_config`, `labeled_by` and `cache_source_id` on every record in `runs/<run>/grading/records.jsonl`; every attempt in `grading/calls.jsonl` | Built; exercised by the live pilot, 500, 10k and final runs |
| D3 | Memo numbers trace to calculations and evidence | `memo.md` + `claims.csv`: the model writes claim tokens, code fills each number from saved aggregates; the course checker recomputes claims; `web/load_db.py` re-checks every claim in SQL | Final run: `runs/final-200k/memo.md` (source: model) with 40 claims, C01-C40, in `claims.csv` (top 10 issues x 4 metrics); the course checker found 0 issues against the declared-scope reference (`runs/final-200k/self-check.json`). Also ran on the 500 checkpoint (40 claims, `runs/live-checkpoint500/run_summary.json`) |
| D4 | Coherent recommendation, alternatives, limitations | `prompts/memo_v2.md`; `insight/analysis.py` (monthly trends with denominators, same-month comparison, intervals, enricher-vs-verifier robustness); [Limitations](#limitations) | Final memo recommends billing/support, with usability, playback/performance and access/onboarding as alternatives and a robustness caveat (verifier labels put playback/performance first); summary under [Results](#results) |
| T1 | 50 human golden labels, per-field comparison, error analysis | `python -m insight label-golden` (`insight/label_tool.py`); `python -m insight golden` (`insight/golden.py`: per-field agreement, severity MAE, ambiguous count, confusion table, quote/entity checks, needs_review); `evals/ensemble_golden.py`; [evals/README.md](evals/README.md) | Done: 50 labels by Eason (`evals/golden/golden_50_labeled.csv`, workbook + `convert_labels.py`); 4 setups compared; [error analysis](evals/golden/error_analysis.md) and [every disagreement](evals/golden/results_disagreements.md) |
| T2 | Independent verification, planted error, injection | Verify stage (Claude Haiku, blind, declared 10% sample); `python -m insight planted-error`; `evals/synthetic/` + `evals/check_synthetic.py` | Verification measured on the live 500 (below). Injection: 8 of 8 synthetic cases passed with the live enricher (`runs/live-synthetic-injection/evals/synthetic_check.json`, copy in `evals/injection/`). Final run: 2,000-review verifier sample (see [Results](#results)); planted error `detected` (`runs/final-200k/evals/planted_error.json`; also on the offline stub run, `runs/offline-stub-checkpoint500/evals/planted_error.json`) |
| T3 | Real 100-review cold/warm pilot, offline calculator, retry/spend/recovery controls | [cost/report.md](cost/report.md) "Measured 100-review pilot"; `cost/pilot_records.jsonl`, `pilot_calls.jsonl`, `usage.csv`, `rates.csv`, `assumptions.json`, `pilot_runs.json`; `python3 cost/calculator.py`; `tests/test_calculator.py`; [Cost and spend controls](#cost-and-spend-controls) | Pilot measured; 500 refresh saved (`cost/refreshes/checkpoint_500.json`). Live budget drill: a $0.005 cap stopped the run with 353 of 500 IDs saved, and a resume under $0.05 finished all 500 (`runs/live-budget-drill/run_summary.json`). Retry and fault handling shown offline (`runs/offline-stub-fault-drill-500`, `tests/test_pipeline.py`) and live: the final run retried 172 HTTP 429 (Flex capacity) responses and 10 invalid outputs and ended with 0 unfinished (`calls` table, `runs/final-200k/state.sqlite`). Final-run interruption: a real SIGINT stopped it at 208.4 s with 34,638 IDs saved; the resume completed all 200,000 (`runs/final-200k/run_summary.json`, `history`) |
| W1 | Full ingestion, record coverage, classification | `insight/ingest.py` profiles the full file with the provided helper (`--full`) whatever the scope; `grading/ingestion.json`, `grading/records.jsonl` | Declared 200,013-row subset; full file profiled (660,622 rows, `runs/final-200k/grading/ingestion.json`); 200,000 completed, 13 quarantined, 0 unfinished. Checker: `pass`, 0 issues, coverage candidate 1.0 against a reference built from the declared subset (`runs/final-200k/self-check.json`); `review_required`, coverage candidate 0.4422 against a full-file reference (`runs/final-200k/self-check-vs-full-reference.json`), because the 460,609 rows outside the subset are not classified. See [Scope](#scope) |
| W2 | Staged program, bounded calls, saved handoffs, demonstrated resume | `python -m insight run --input <csv> --run-dir runs/<name>`: six stages, at most 50 reviews per request, one SQLite state per run, rerun = `phase resume`; an offline real-SIGINT resume passes the course checker (`runs/offline-stub-checkpoint500/self-check.json`) | Live final run: `runs/final-200k/recording/1-initial-interrupted.cast`/`.txt` (real SIGINT after 180 s) and `2-resume.cast`/`.txt` (phase `resume`); `grading/checkpoint_before.json` (34,638 IDs) and `grading/checkpoint_after.json` (200,000 IDs); console logs `runs/final_initial_console.log`, `runs/final_resume_console.log` |
| W3 | Reproducible ranking + deployed dashboard, backend, database, grounded AI recommendations | `python -m insight rank --run-dir <run> --check`; `web/` (static dashboard, FastAPI backend `web/api/index.py`, `web/schema.sql`, `web/load_db.py`) | Deployed: https://spotify-review-insights-iota.vercel.app (public, read-only, no login; see [Dashboard](#dashboard)). Rank check on the final run: identical, 22 issues (`runs/final-200k/rank_check.json`) |

## Results

Measured numbers and estimates are kept apart. Completed means a valid label was saved; accounted-for
includes quarantined and unfinished rows.

**Final run** (`runs/final-200k`; five invocations listed under `history` in `run_summary.json`):

| What | Value |
|---|---|
| Source rows profiled / rows in declared scope | 660,622 profiled with the provided helper (`runs/final-200k/ingestion.json`) / 200,013 in scope, `data/analysis_200k.csv` (`runs/final-200k/ingestion_report.json`) |
| Completed / quarantined / unfinished | 200,000 / 13 (empty text) / 0: 138,724 primary, 13,639 fallback1, 47,637 exact-text reuses; 16,964 flagged `needs_review` (`runs/final-200k/run_summary.json`) |
| Exact-text cache reuses | 47,637; 152,363 distinct texts went to the model (`runs/final-200k/run_summary.json`) |
| Golden-50 agreement (topic / intent / severity exact) | 76% / 74% / 76%, all three 48%, severity MAE 0.24, sentiment within 0.5: 86% (`evals/golden/results.json`) |
| Verifier sample and disagreements | 2,000 distinct texts (declared 10% sample, capped at 2,000): topic 1,618, intent 1,841, severity exact 1,583, sentiment within tolerance 1,980 of 2,000; 762 sampled reviews differ on at least one field, all listed in `verification/disagreements.csv` (`runs/final-200k/verification/report.json`) |
| Billed API cost / API-equivalent of Pro calls / wall clock | $2.019246 billed over all invocations (sum of `calls.cost_usd` in `runs/final-200k/state.sqlite`, equal to `ledger.spent_usd` in `run_summary.json`) / $1.8228 API-equivalent, not billed (`cost/report.md`, "Measured refreshes") / 9,156.1 s over five invocations (`cost/refreshes/final_200k.json`): initial 208.4 s (interrupted), resume 8,766.0 s (enrich 8,374.6 s), then three regeneration invocations of 56-67 s (`invocations` table) |
| Enrichment workers / fallback1 | 16 workers in both enrichment invocations (`invocations` table); fallback1 cap 10% (15,236 texts), all 13,639 staged texts routed (`runs/final_resume_console.log`) |
| Course checker status and coverage candidate | Reference from the full file plus the declared subset: `pass`, 0 issues, coverage candidate 1.0 (`runs/final-200k/self-check.json`). Reference from the full file alone: `review_required`, coverage candidate 0.4422, issues `missing_records` (460,609 IDs), `unfinished_classification` and two `run_manifest_mismatch` (`runs/final-200k/self-check-vs-full-reference.json`). See [Scope](#scope) |
| Ranking | 22 issues from 89,762 complaint and cancellation records; top three `billing.premium_only` 52,577, `other.general` 45,898, `usability.ads` 24,431 (`runs/final-200k/ranking.csv`); rebuilt identically from `grading/` (`runs/final-200k/rank_check.json`) |
| Memo with `claims.csv` IDs | `runs/final-200k/memo.md` (source: model), 40 claims C01-C40 in `runs/final-200k/claims.csv` |
| One review traced source -> enrich -> verify -> membership -> ranking -> memo claim, plus one ambiguous or failed case | [docs/trace_example.md](docs/trace_example.md): review `674b2fb0-...` (rank-1 issue `billing.premium_only`, claims C01-C04, quoted in the memo; not in the verification sample) and review `00046c11-...` (flagged ambiguous, routed to fallback1, saved with `needs_review`) |

**Final recommendation** (`runs/final-200k/memo.md`; the model wrote claim tokens and code filled every
number): put next quarter's effort into **billing/support**. It has the highest baseline priority of the
four areas, a severity sum of 59,146 against 54,124 for usability, 46,058 for playback/performance and
11,172 for access/onboarding (`runs/final-200k/area_rollup.json`). Most of it comes from Premium-only
restrictions (`billing.premium_only`: 18,016 complaints, severity sum 52,577, mean 2.918350; C01-C03), the
largest issue in the ranking. The area's share of reviews grew from 4.5% to 15.4% between June-October 2022 and
June-October 2023 (+10.9 pp), with an October 2023 spike in `billing.premium_only` (+25.1 pp). Alternatives in
the memo: usability (second on baseline priority and first by complaint count in both labelings, 25.6% of
complaints, but +0.7 pp growth); playback/performance (high severities, e.g. app crashes at mean 3.750161,
and first under the verifier's labels, but its share fell 5.0 pp); access/onboarding (highest single-issue
mean severity, login failures at 3.960270, but the smallest total). Robustness caveat, stated in the memo: on
the 2,000-review verification sample the verifier's labels put playback/performance first on the same
metric, while the enricher's put billing/support first, so the lead is not robust across labelers
(`runs/final-200k/analysis/robustness.json`).

**Error found and fixed after the run.** The first naming pass gave the naming model each issue's 8
highest-severity quotes. It named the catch-all `other.general` "Privacy and data collection concerns"
(`stage_cache` in `runs/final-200k/state.sqlite`), although only 8 of its 14,796 distinct complaint texts
mention privacy (`insight/group.py`, `evidence_pack`). Fix: naming evidence is now a deterministic uniform
sample of 12 member texts per issue, and the catch-alls `other.general` and `usability.other` keep their
taxonomy names (`config/pipeline.toml` `[group]`, `insight/group.py`). The same check found that the
verifier robustness check compared areas by complaint count, not by the baseline metric. It now uses the
row-weighted severity sum (`insight/analysis.py`), the memo prompt judges the top area on that metric
(`prompts/memo_v2.md`), and the memo model now sees the trend values (`insight/memo.py`). Group, rank, memo
and export were regenerated from the saved labels in three short invocations: no enrichment calls, 10 group
and 3 memo calls through `claude -p`, $0 billed (`calls` table). Labels were not touched: the ranking
saved by the original resume invocation has the same top five issues and the same 89,762 memberships
(`runs/final-200k/invocations/run-20261012T233254.463Z-c2b5.json`). The recommendation did change: the
first two memos recommended usability (most complaints), the last two billing/support (highest baseline
priority) (memo outputs in `stage_cache`).

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

**Estimates** (`cost/report.md`, "Estimated runs"; per-unit inputs now measured on the final run, up to 4
workers; not measurements): the full 660,622-row file would cost $6.42 billed (base, with reuse) up to
$13.09 (conservative, no reuse) and take 28.4 to 48.5 hours; both conservative cases exceed the $9.00
project cap. For the declared scope it gives $2.02 (base, with reuse) to $3.96 (conservative, no reuse).

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
# 1. Offline calculator replay: recomputes cost/report.md and cost/report.json from saved usage x rates
python3 cost/calculator.py

# 2. Offline stub run of every stage on checkpoint_500 (local test server; stub labels are meaningless)
./scripts/offline_demo.sh            # includes a real Ctrl-C, resume, warm rerun, checker, rank check, drills
.venv/bin/python -m insight run --input "Final Assignment - Spotify Reviews Dataset/checkpoint_500.csv" \
    --run-dir runs/offline-stub-demo --offline-stub

# 3. Tests (62 `def test_` functions across tests/*.py)
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
golden scoring step waits for the human labels.

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
`runs/final-200k/state.sqlite`. Calls through `claude -p` cost $0 per call under Eason's fixed-fee Claude
Pro plan. The course says subscription
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

Billed spend by run (`cost/project_spend.json`, computed 2026-10-13 02:10 UTC): final run $2.019246,
analysis_10000 $0.096326, golden candidates $0.00909 (Decisions), $0.000866 (Luna, effort low) and $0.00067
(Luna, effort none), checkpoint_500 $0.005175 (1 worker) and $0.004250 (2 workers), budget drill $0.004306,
pilot $0.001339, probes $0.000942 (Decisions) and $0.000198 (Luna), injection test $0.000234; total
$2.142643 against the $9.00 project cap. The final run's per-run cap was $4.00 for the two enrichment
invocations and $2.10 for the regenerations, with 0 budget denials (`invocations` table and `ledger` in
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
  Overview, AI recommendation, Issue ranking, Trends, Evaluation, Run & cost, Review lookup. JSON endpoints
  include `/api/health`, `/api/overview`, `/api/ranking`, `/api/recommendation`, `/api/reviews/{review_id}`
  and `/api/consistency` (on 2026-10-12 it returned `ranking_matches` true and `claims_match` true).
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
- The worked examples in `docs/labels.md` were drafted by the AI assistant from development rows 101-500
  and are not human labels (the file says so).

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
./scripts/live.sh golden-candidates  # scoring step needs evals/golden/golden_50_labeled.csv
./scripts/live.sh analysis10k        # done 2026-10-12 (8 workers)
./scripts/live.sh final-initial      # done 2026-10-12 (16 workers); recorded; SIGINT after 180 s of saved progress
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
evals/                synthetic injection cases and checker, golden ensemble analysis
docs/                 architecture, labels and worked examples, model choice
web/                  dashboard, backend, database schema and loader
tests/                unit, integration and calculator tests
scripts/              live.sh (billed steps), offline_demo.sh, make_analysis_subset.py, record_session.py
runs/                 run directories: live-*, probe-*, golden-* and pilot100-20261012T224901Z made real calls;
                      offline-stub-*, pilot100-offline-stub-* and *preflight* made none (plumbing only)
data/                 declared-scope manifest (CSVs are git-ignored and regenerable)
```

Dependencies: Python 3.12.14; `openai==3.23.0`, `anthropic==1.11.0`, `typesafe-sdk==0.7.2`
(`requirements.txt`); `fastapi==0.115.6`, `psycopg[binary]==3.2.3` (`web/requirements.txt`).

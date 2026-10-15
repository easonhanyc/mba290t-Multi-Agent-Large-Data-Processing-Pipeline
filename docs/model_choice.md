# Model choice

Updated 2026-10-15 (UTC). This replaces the 2026-10-01 plan (Jev as primary enricher, GPT-6 Luna for verify,
group and memo), which was written before any model had been called. The choice rests on two provider probes,
real pilot and checkpoint runs, and a comparison of three candidate enrichment setups on Eason's hand-labelled
golden 50. The final run (`runs/final-200k-v2`) uses the winning candidate's exact configuration. A first final run
made earlier with a different setting (`runs/final-200k`, effort none) is kept as superseded evidence.

## Decision rule

1. **Hard constraints.** A setup is used at scale only if it passes all three:
   - **Money**: the conservative projection for the chosen scope fits the $9.00 project cap
     (`run.project_cap_usd`, Eason's $10 total budget less a $1 margin, `config/pipeline.toml`), and it needs
     no purchase beyond the funded OpenAI credit.
   - **Time**: the measured rate limit and latency let the run finish well before the course deadline (the
     final run's two enrichment invocations took 9,212.5 s, `cost/refreshes/final_200k_v2.json`).
   - **Contract**: structured output, at most 50 reviews per request, and every call logged with its model
     ID, tokens and cost.
2. **Quality.** Among setups that pass, use the one with the best golden-50 "all three correct" agreement
   (topic, intent and severity). This rule was written in the plan before any golden label existed.
3. **Stronger models only where bounded.** They are used for capped fallbacks, the declared verifier
   sample, at most 12 issue-naming calls and one memo call per pass (a second memo attempt only after an
   invalid output), never as an automatic upgrade for every review.

## Roles in production (`config/pipeline.toml`)

| Role | Model (as logged) | Setting | Billing | Why |
|---|---|---|---|---|
| Enrich, primary | `gpt-6-luna`, OpenAI Responses | effort low, Flex tier, 50 reviews/request, 200 output tokens per review (reasoning counts as output), exact-text reuse | billed API | Best golden-50 candidate; passes the money and time constraints (below) |
| Enrich, fallback1 | `gpt-6-luna` | effort low, 1 review/request with the definitions and a specific question, at most 1.5% of distinct texts | billed API | A second, single-review read of the texts the primary pass flagged or contradicted itself on |
| Enrich, fallback2 | Claude Sonnet via `claude -p` (alias `sonnet`) | effort low, at most 0.25% | Claude Pro subscription | Only when fallback1 output is invalid twice. Never routed in the measured runs |
| Verify | `claude-haiku-4-5-20251001` via `claude -p` | blind, declared 10% random sample of distinct texts, at most 2,000, 50 per request | Claude Pro subscription | A different model family from the enricher, so agreement is a real consistency check |
| Group (names only) | `claude-sonnet-5` via `claude -p` | top 12 issues, 12 sampled member quotes each; catch-all issues keep their taxonomy names; membership is code | Claude Pro subscription | Readable names; at most 12 calls per pass (names are cached by their exact inputs) |
| Memo | `claude-sonnet-5` via `claude -p` | aggregates + evidence pack; writes claim tokens, code fills numbers | Claude Pro subscription | One call per pass, retried once if invalid; a template memo if invalid twice |

Logged model IDs come from `model_reported` in the `calls` table of `runs/final-200k-v2/state.sqlite` and in
`runs/final-200k-v2/grading/calls.jsonl.gz`, which keeps the configured alias in `model` and the exact reported ID in
`model_reported` (19 enrichment attempts that timed out or failed before a response have none); `cost/report.md`
shows both columns. Claude calls are $0 per call under the fixed-fee Pro plan, whose monthly fee is not included in
per-call billed spend. The course says subscription access is not evidence that calls are free (`COST_CALCULATOR.md`),
so the calculator prices them at Anthropic API rates as "API-equivalent" and keeps that apart from billed spend.

**Configuration strings.** Every record of the final run carries
`label_config = gpt-6-luna@low>gpt-6-luna@low(1.5%)>sonnet@low(0.25%)|enrich-v2|schema-v2|cfg-52c5333247`, the same
string as the golden candidate run `runs/golden-luna-low`. The final run's `stage_configs` (latest invocation,
`runs/final-200k-v2/run_summary.json`) are verify `haiku@n/a|verify-v1|cfg-26c97bdddf`, group
`sonnet@low|group-v1|cfg-28f1c4b99f` and memo `sonnet@low|memo-v1|cfg-10453c7a82`, equal to what the current
`config/pipeline.toml` produces. The `<stage>-v1` in these strings is the version of the key format, not of the prompt
file (`insight/config.py`, `stage_config`): the prompt enters through the SHA-256 of its contents inside the `cfg-`
hash, so verify uses `prompts/verify_v2.md`, group `prompts/group_v1.md` and memo `prompts/memo_v2.md`.

## Measured evidence

### Provider probes (2026-10-12, 5 development reviews, [`data/probe_dev_5.csv`](../data/probe_dev_5.csv))

| Probe | Requests | Input tokens per request | Cached | Latency | Rate limit reported | Billed | Source |
|---|---:|---|---:|---|---|---:|---|
| Decisions API (`gpt-6-luna`), 1 review/request | 5 | 1,812-2,018 | 0 | 0.12-0.40 s | `x-ratelimit-limit-requests 50`, one request restored every 28m48s (50 per day); 60,000 tokens | $0.000942 | `runs/probe-decisions/state.sqlite`, `calls.usage_raw` |
| Batched Luna (Responses, effort none, Flex), 5 reviews in 1 request | 1 | 2,459 (178 output) | 0 | 5.8 s | 5,000 requests and 2,000,000 tokens per minute | $0.000198 | `runs/probe-luna/state.sqlite`, `calls.usage_raw` |

The Decisions endpoint bills input only, but it re-bills its question definitions on every one-review request and
reported no cached tokens. At 50 requests per day it could label 50 reviews a day.

### Measured steps with the final setup (2026-10-14)

| Step | Run | Completed (primary / fallback1 / exact-text reuse) | Enrichment calls | Billed | Time | Verifier agreement: topic / intent / severity |
|---|---|---|---|---:|---|---|
| 100-review pilot, cold | `runs/pilot100-20261014T213535Z` | 100 (99 / 1 / 0) | 2 primary + 1 fallback1, no retries | $0.001698 | 177.3 s, all stages | 8 / 8 / 6 of 10 |
| Pilot, warm rerun | same directory | 100 result-cache hits | 0 | $0 | 0.044 s | - |
| checkpoint_500, 1 worker | `runs/live-checkpoint500-low` | 500 (472 / 7 / 21) | 10 + 7, no retries | $0.006952 | 462.1 s | 41 / 46 / 35 of 48 |
| analysis_10000, 8 workers | `runs/live-analysis10000-low` | 10,000 (8,322 / 126 / 1,552) | 170 + 126, 1 invalid-output retry | $0.128644 | 1,409.1 s + 197.3 s (see below) | 708 / 775 / 669 of 845 |
| **Final, declared scope, 16 workers** | `runs/final-200k-v2` | 200,000 (150,078 / 2,285 / 47,637); 13 empty texts quarantined | 3,081 primary + 2,285 fallback1 attempts (1 HTTP 429, 16 timeouts, 1 connection error, 1 server error, 14 partly invalid outputs; all retried) | $2.323945 (+ $0.097098 reserved for the 17 unknown-outcome calls) | 199.8 s (interrupted) + 9,012.7 s (resume, all stages); 9,389.9 s over 4 invocations | 1,635 / 1,830 / 1,565 of 2,000 |

Sources: `run_summary.json`, `verification/report.json` and `invocations/` in each run directory; `cost/report.md`
("Scaling decision") and `cost/refreshes/*.json`. The fallback1 cap was reached at every step (1, 7, 126 and 2,285
texts routed); flagged texts above the cap keep their primary label with `needs_review` (17,828 in the final run).
The analysis_10000 run's first invocation hit the Claude Pro session limit during verify, group and memo; it was
then classed as a transient error and produced an empty verification and a template memo. The limit is now a
systemic stop, and rerunning the same command redid those stages with no enrichment calls
([walkthrough.md](walkthrough.md), "One failure").

Measured per-unit cost of the final setup: $0.00001481 per distinct text for the primary pass and $0.00001525 in all
(`cost/report.md`, "Scaling decision"), mean primary attempt latency 43.55 s at 16 workers on Flex.

### Superseded measurements with effort none (2026-10-12/13)

Before the golden labels existed, the same steps ran with effort none as the primary (fallback1 effort low, cap 1.5%
and then 10%): pilot $0.001339 (`cost/experiments/pilot-effort-none/`), checkpoint_500 with 1 and 2 workers
(`runs/live-checkpoint500`, `runs/live-checkpoint500-w2`), analysis_10000 (`runs/live-analysis10000`) and the first
final run (`runs/final-200k`, $2.019246, 12 invocations). Their per-call evidence stays in `cost/refreshes/` and counts
toward project spend; `cost/report.md` lists them in their own table.

The 1-vs-2 worker comparison was measured on this setup: the same 500 reviews cold took 266.8 s of enrichment with 1
worker and 154.3 s with 2. Agreement between the two runs (read-only SQL join of `results` by `review_id` across both
`state.sqlite` files): topic 482/500, intent 489/500, severity 484/500, all three 466/500. The routing code is
deterministic for identical answers (`tests/test_pipeline.py::test_two_workers_give_identical_labels`, offline stub),
so these differences come from the model's answers.

## Candidates compared

| Candidate | Evidence | Constraint check | Decision |
|---|---|---|---|
| **GPT-6 Luna, batched, effort low** (`backend = "llm"`) | Steps above; $2.323945 billed for the declared 200,013-row scope | Money: passes. Time: 5,000 RPM limit; enrichment 9,212.5 s at 16 workers. Contract: passes | **Production primary.** Best golden-50 candidate (below) |
| GPT-6 Luna, batched, effort none | Superseded steps above; $2.019246 for the declared scope | Passes | Golden 50: second (46% all three vs 54%); used by the superseded first final run |
| **OpenAI Decisions API alone** (`backend = "decisions"`): the same typed questions as Jev, one review per request | Probe above. Projection: $29.54 at the declared scope, $93.88 for the full corpus (`cost/report.md`, "Enrichment-stage alternatives", estimate) | Money: fails. Time: fails (50 requests per day) | Built and tested offline (`tests/test_pipeline.py::test_decisions_backend_offline`); measured as a golden-50 candidate: `runs/golden-decisions` labelled the 50 texts in 49 requests (one exact-text duplicate) for $0.00909 |
| **Hybrid** (`backend = "hybrid"`): Luna labels plus a Decisions cross-check of intent and severity on high-stakes texts and a 10% deterministic random sample | Same probe; cross-check estimate 367 input tokens per compact request (`cost/assumptions.json`, estimate) | Time: fails at scale (50 requests per day) | Built and tested offline (`tests/test_pipeline.py::test_hybrid_crosscheck_routes_disagreements_and_resumes`); off in production. `evals/ensemble_golden.py` scores, offline, what this combination would have done on the golden 50 |
| **Jev 1.13** (TypeSafe), one review per request | Not run. Listed price $0.042 per million input tokens, output free (`cost/rates.csv`); its question set is about 1,666 tokens per request (6,665 characters / 4, `cost/report.md`) | Money: fails. TypeSafe requires a $5 minimum purchase against a $10 total budget. Projection $10.66 at the declared scope (`cost/report.md`, estimate) | Not used. The Decisions backend reuses the Jev question set (`prompts/jev_enrich_v1.json`) as the typed-classifier comparison |
| **Claude Haiku via `claude -p`** | Final run: 40 verifier calls for 2,000 reviews, mean 50.4 s, API-equivalent $1.494197 (`cost/report.md`) | Subscription usage limits; config allows 8 requests per minute to `claude -p` | Verifier |
| **Claude Sonnet via `claude -p`** | Final run: 10 group calls (2 of the 12 names were cached or empty; API-equivalent $0.063845) and 4 memo attempts, 3 valid and 1 rejected by the validator (API-equivalent $0.402673), all $0 billed (`runs/final-200k-v2/grading/calls.jsonl.gz`) | Bounded: at most 12 group calls and 2 memo attempts per pipeline pass | Group names, memo, fallback2 |

Other priced alternatives that were not run (Gemini 2.5 Flash-Lite, whose adapter is not built; Claude Haiku 5.5 by
API; Luna at Standard tier) appear in `cost/report.md`, "Enrichment-stage alternatives", as token estimates only.

## Candidate comparison on the golden 50

Eason labelled the 50 reviews by hand (workbook `evals/golden/golden_50_labeled.numbers`, converted by
`evals/golden/convert_labels.py`; conventions in `docs/labels.md`). Each candidate enriched the same 50 texts (human
labels are never ingested) and `python -m insight golden` scored each run (`evals/golden/candidates/*.json`).

| Candidate run | Topic | Intent | Severity exact | All three | Severity MAE | Notes |
|---|---|---|---|---|---|---|
| `runs/golden-luna-none` | 74% | 70% | 72% | 46% | 0.32 | billed $0.00067 for 50 |
| **`runs/golden-luna-low`** (effort low, 200 output tokens per review) | 80% | 76% | 76% | **54%** | 0.24 | billed $0.000866 for 50 |
| `runs/golden-decisions` (49 requests, the daily limit is 50) | 76% | 74% | 68% | 48% | 0.34 | billed $0.00909; flags 26/50 for review (human: 6) |
| Luna + Decisions rule (`evals/ensemble_golden.py`, threshold 0.80 set before seeing results) | 74% | 74% | 70% | n/a | n/a | the models agree on 96% / 92% / 84% of texts and share their misses |

**Decision.** The rule picks effort low (54% all three; against effort none it was right alone on 4 reviews and
wrong alone on none, exact McNemar p = 0.125). Its projected cost at the declared scope fit the cap
(`cost/report.md`, "Estimates before the final run": $2.32 to $4.55 from the 10,000-review step). The golden labels
were finished after the first final run, so that run (effort none) was superseded and the final run was made with the
candidate's exact configuration (`label_config` `cfg-52c5333247`, `config/pipeline.toml`). No prompt, label or
threshold was changed because of golden results; the choice was among frozen candidates.

**Result.** On the golden 50 the final run scored topic 78%, intent 76%, severity exact 74%, all three 48% (MAE 0.26),
against 76% / 74% / 76% / 48% for the superseded run. The same configuration scored 54% all three as a candidate:
answers are not deterministic and the candidate run sent the 50 texts in one request, the final run across 39
(`evals/golden/error_analysis.md`, section 2). On 50 cases the two setups are within noise of each other, and because
the golden set made the choice, its scores for the final run carry a small selection bias. Checks that played no part
in the choice: the blind verifier sample (above) and the quote-support check on a random sample of the final run
(`evals/quote_support/report.md`).

## Prices used (`cost/rates.csv`)

| Provider / model | Tier | Input $/1M | Cached input $/1M | Cache write $/1M | Output $/1M | Checked |
|---|---|---:|---:|---:|---:|---|
| OpenAI `gpt-6-luna` | Flex | 0.05 | 0.005 | 0.0625 | 0.25 | 2026-10-10 |
| OpenAI `gpt-6-luna` | Standard | 0.10 | 0.01 | 0.125 | 0.50 | 2026-10-10 |
| OpenAI Decisions (`gpt-6-luna`) | Standard | 0.10 | 0.10 | 0 | 0 | 2026-10-12 |
| TypeSafe `jev-1.13.0` | Standard | 0.042 | 0.042 | - | 0 | 2026-10-01 |
| Anthropic `claude-haiku-4-5` (API-equivalent only) | Standard | 1.00 | 0.10 | 1.25 | 5.00 | 2026-10-10 |
| Anthropic `claude-sonnet-5` (API-equivalent only) | Standard | 2.00 | 0.20 | 2.50 | 10.00 | 2026-10-10 |

Each row's source link is in `cost/rates.csv`. Every OpenAI call sets `reasoning.effort` explicitly because GPT-6
Luna's default is not the cheapest setting.

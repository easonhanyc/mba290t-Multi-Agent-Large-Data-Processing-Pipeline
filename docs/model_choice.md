# Model choice

Updated 2026-10-14 (UTC). This replaces the 2026-10-01 plan (Jev as primary enricher, GPT-6 Luna for verify,
group and memo), which was written before any model had been called. The current choice rests on two
provider probes, the real 100-review pilot and the live 500-review checkpoint. It then ran at the
10,000-review checkpoint and, with a larger fallback1 cap and output-token cap, on the declared
200,013-row scope (below). Quality evidence comes from the verifier sample, from repeating a run, and from the
golden-50 comparison against Eason's hand labels ("Candidate comparison on the golden 50" below). The golden
labels were finished after the final run, so they informed the disclosure there, not the choice made before
the run.

## Decision rule

1. **Hard constraints.** A setup is used at scale only if it passes all three:
   - **Money**: the conservative projection for the chosen scope fits the $9.00 project cap
     (`run.project_cap_usd`, Eason's $10 total budget less a $1 margin, `config/pipeline.toml`), and it needs
     no purchase beyond the funded OpenAI credit.
   - **Time**: the measured rate limit and latency let the run finish well before the course deadline (the
     final run took 9,334.36 s over seven invocations, 8,974.4 s of it in the two enrichment invocations,
     `cost/refreshes/final_200k.json`).
   - **Contract**: structured output, at most 50 reviews per request, and every call logged with its model
     ID, tokens and cost.
2. **Quality.** Among setups that pass, use the cheapest one whose golden-50 results are not clearly
   worse than the others. The brief sets no minimum accuracy, and 50 cases cannot separate differences of
   one or two reviews.
3. **Stronger models only where bounded.** They are used for capped fallbacks, the declared verifier
   sample, at most 12 issue-naming calls and one memo call per pass (a second memo attempt only after an
   invalid output), never as an automatic upgrade for every review.

## Roles in production (`config/pipeline.toml`)

| Role | Model (as logged) | Setting | Billing | Why |
|---|---|---|---|---|
| Enrich, primary | `gpt-6-luna`, OpenAI Responses | effort none, Flex tier, 50 reviews/request, 70 output tokens per review (60 up to the 10k checkpoint), exact-text reuse | billed API | Passes the money and time constraints by a wide margin (below) |
| Enrich, fallback1 | `gpt-6-luna` | effort low, 1 review/request, at most 10% of distinct texts (1.5% up to the 10k checkpoint) | billed API | A second, slower read of the reviews the primary pass flagged or contradicted itself on |
| Enrich, fallback2 | Claude Sonnet via `claude -p` (alias `sonnet`) | effort low, at most 0.25% | Claude Pro subscription | Only when fallback1 output is invalid twice. Never routed in the measured runs |
| Verify | `claude-haiku-4-5-20251001` via `claude -p` | blind, declared 10% random sample of distinct texts, at most 2,000 | Claude Pro subscription | A different model family from the enricher, so agreement is a real consistency check |
| Group (names only) | `claude-sonnet-5` via `claude -p` | top 12 issues, 12 sampled member quotes each; catch-all issues keep their taxonomy names; membership is code | Claude Pro subscription | Readable names; at most 12 calls per pass (names are cached by their exact inputs) |
| Memo | `claude-sonnet-5` via `claude -p` | aggregates + evidence pack; writes claim tokens, code fills numbers | Claude Pro subscription | One call per pass, retried once if invalid; a template memo if invalid twice |

Logged model IDs come from `model_reported` in the `calls` table of `runs/live-checkpoint500/state.sqlite`
(the same IDs appear in `runs/final-200k/state.sqlite`).
The CLI aliases `haiku` and `sonnet` resolved to those IDs. Claude calls are $0 per call under the
fixed-fee Pro plan. The course says subscription access is not evidence that calls are free
(`COST_CALCULATOR.md`), so the calculator prices them at Anthropic API rates as "API-equivalent" and keeps
that apart from billed spend.

The measured runs used verifier prompt `verify-v1` at 25 reviews per request and memo prompt `memo-v1`
(`stage_configs` and `config_summary` in `runs/live-checkpoint500/run_summary.json`). The config now
points to `prompts/verify_v2.md` at 50 reviews per request and `prompts/memo_v2.md`.
The final run's `stage_configs` (`runs/final-200k/run_summary.json`, latest invocation) are verify
`haiku@n/a|verify-v1|cfg-26c97bdddf`, group `sonnet@low|group-v1|cfg-28f1c4b99f` and memo
`sonnet@low|memo-v1|cfg-820daf045e`. The `-v1` in these strings is a fixed label (`insight/config.py`,
`stage_config`); the prompt file enters through its SHA-256 inside the `cfg-` hash. All three equal what the
current `config/pipeline.toml` produces (recomputed with `insight.config.load().stage_config(...)`, no
calls), so the final run used `prompts/verify_v2.md` at 50 reviews per request (40 verifier calls for
2,000 reviews, `calls` table), `prompts/group_v1.md` with 12 sampled quotes, and `prompts/memo_v2.md`. Its
`label_config` is `gpt-6-luna@none>gpt-6-luna@low(10%)>sonnet@low(0.25%)|enrich-v2|schema-v2|cfg-f6337dc790`.

## Measured evidence

### Provider probes (2026-10-12, 5 development reviews, [`data/probe_dev_5.csv`](../data/probe_dev_5.csv))

| Probe | Requests | Input tokens per request | Cached | Latency | Rate limit reported | Billed | Source |
|---|---:|---|---:|---|---|---:|---|
| Decisions API (`gpt-6-luna`), 1 review/request | 5 | 1,812-2,018 | 0 | 0.12-0.40 s | `x-ratelimit-limit-requests 50`, one request restored every 28m48s (50 per day); 60,000 tokens | $0.000942 | `runs/probe-decisions/state.sqlite`, `calls.usage_raw` |
| Batched Luna (Responses, effort none, Flex), 5 reviews in 1 request | 1 | 2,459 (178 output) | 0 | 5.8 s | 5,000 requests and 2,000,000 tokens per minute | $0.000198 | `runs/probe-luna/state.sqlite`, `calls.usage_raw` |

The Decisions endpoint bills input only, but it re-bills its question definitions on every one-review
request and reported no cached tokens. At 50 requests per day it could label 50 reviews a day.

### 100-review pilot (cold, then warm; `cost/report.md`)

- Cold: 100 of 100 completed (99 primary, 1 fallback1) with 3 enrichment attempts (2 primary, 1 fallback1),
  no retries, billed $0.001339, API-equivalent of the Pro calls $0.127723, 159.5 s.
- Warm rerun in the same run directory: 0 new enrichment calls, 100 result-cache hits, $0, 0.038 s.

### 500-review checkpoint, 1 worker vs 2 workers

| | 1 worker (`runs/live-checkpoint500`) | 2 workers, cold rerun (`runs/live-checkpoint500-w2`) |
|---|---:|---:|
| Stages run | all six + export | ingest, enrich, export |
| Completed | 500 (472 primary, 7 fallback1, 21 exact-text reuses) | 500 (same split) |
| Enrichment calls | 10 primary + 7 fallback1, 0 retries, 0 invalid outputs | 10 primary + 7 fallback1, 0 retries, 0 invalid outputs |
| Staged as difficult / routed to fallback1 (cap 7) | 21 / 7 | 23 / 7 |
| `needs_review` | 25 | 28 |
| Enrich stage seconds | 266.8 | 154.3 |
| Billed API | $0.005175 | $0.004250 |

Sources: `run_summary.json` in each run directory. Agreement between the two runs on the same 500 reviews
(read-only SQL join of `results` by `review_id` across both `state.sqlite` files): topic 482/500, intent
489/500, severity 484/500, all three 466/500. The routing code is deterministic for identical answers
(`tests/test_pipeline.py::test_two_workers_give_identical_labels`, offline stub), so these differences
come from the model's answers at effort none.

Verifier on the 1-worker run, 48-review sample: topic 41/48, intent 45/48, severity 39/48, sentiment within
tolerance 48/48 (`runs/live-checkpoint500/verification/report.json`). The verifier is another model, not
ground truth.

Measured per-unit cost of batched Luna on this checkpoint: $0.00001038 billed per distinct review
($0.004974 for 479 distinct texts, `runs/live-checkpoint500/run_summary.json`), 47.9 reviews per request,
25.3 s mean latency (`cost/refreshes/checkpoint_500_calls.jsonl`). On the final run the primary pass
measured $0.00001073 per distinct review, 49.833 reviews per request and 29.29 s mean latency
(`cost/report.md`, "Per-unit inputs used", which now uses final_200k).

### 10,000-review checkpoint and final run

| | analysis_10000 (`runs/live-analysis10000`) | Final, declared scope (`runs/final-200k`) |
|---|---:|---:|
| Rows / distinct texts | 10,000 / 8,448 | 200,013 / 152,363 |
| Workers (enrichment) | 8 | 16 |
| fallback1 cap / staged / routed | 1.5% (126) / 871 / 126 | 10% (15,236) / 13,639 / 13,639 |
| Enrichment attempts | 173 primary, 126 fallback1 | 3,163 primary, 13,715 fallback1 (incl. 172 HTTP 429 retries) |
| Billed API | $0.096326 | $2.019246 |
| Wall clock | 931.6 s, all stages | 208.4 s (interrupted) + 8,766.0 s (resume, all stages); then five regenerations without enrichment, 359.9 s in total (`cost/refreshes/final_200k.json`) |
| Verifier agreement: topic / intent / severity | 678 / 763 / 655 of 845 | 1,618 / 1,841 / 1,583 of 2,000 |

Sources: `run_summary.json` and `verification/report.json` in each run directory,
`runs/analysis10k_console.log`, `runs/final_resume_console.log`, and the `calls` and `invocations` tables
of `runs/final-200k/state.sqlite`. After the 10k checkpoint two label-affecting settings changed: the
fallback1 cap went from 1.5% to 10%, because 745 staged texts had kept their primary label at the 1.5% cap,
and the output cap from 60 to 70 tokens per review, because 3 of 173 batches were truncated at 60 (comment
in `config/pipeline.toml`; request caps of 3,064 vs 3,564 tokens per 50-review request in the two `calls`
tables). Both are part of `label_config` (`low(1.5%)` vs `low(10%)`, `cfg-1a5b53adeb` vs `cfg-f6337dc790`),
so the final run started in a new run directory.

## Candidates compared

| Candidate | Evidence | Constraint check | Decision |
|---|---|---|---|
| **GPT-6 Luna, batched** (`backend = "llm"`) | Pilot, 500, 10k and final run above. Measured on the declared 200,013-row scope: $2.019246 billed for the whole pipeline (`runs/final-200k/run_summary.json`) | Money: passes. Time: 5,000 RPM limit; enrichment finished in 193.1 s + 8,374.6 s at 16 workers (`invocations` table). Contract: passes | **Production primary.** Golden 50: topic 74%, intent 70%, severity 72% alone; the final run (with the effort-low fallback) 76% / 74% / 76% (`evals/golden/`) |
| **OpenAI Decisions API alone** (`backend = "decisions"`): the same typed questions as Jev, one review per request | Probe above. Projection: $29.54 at the declared scope, $93.88 for the full corpus (`cost/report.md`, "Enrichment-stage alternatives", estimate) | Money: fails. Time: fails (50 requests per day) | Built and tested offline (`tests/test_pipeline.py::test_decisions_backend_offline`); measured only as a comparison candidate on the golden 50: `runs/golden-decisions` labelled the 50 texts in 49 requests (one exact-text duplicate) for $0.00909 (`runs/golden-decisions/state.sqlite`) |
| **Hybrid** (`backend = "hybrid"`): Luna labels plus a Decisions cross-check of intent and severity on high-stakes texts (cancellation, severity >= 4, or flagged ambiguous) and a 10% deterministic random sample; disagreements are staged for the capped fallback | Same probe; cross-check estimate 367 input tokens per compact request (`cost/assumptions.json`, estimate) | Time: fails at scale (50 requests per day) | Built and tested offline (`tests/test_pipeline.py::test_hybrid_crosscheck_routes_disagreements_and_resumes`); off in production (`crosscheck_fraction` 0 in `cost/assumptions.json`). `evals/ensemble_golden.py` scores, offline, what this combination would have done on the golden 50 |
| **Jev 1.13** (TypeSafe), one review per request | Not run. Listed price $0.042 per million input tokens, output free (`cost/rates.csv`); its question set is about 1,666 tokens per request (6,665 characters / 4, `cost/report.md`), so the golden 50 would cost about $0.0035 | Money: fails. TypeSafe requires a $5 minimum purchase against a $10 total budget. Projection $10.66 at the declared scope (`cost/report.md`, estimate) | Not used. The Decisions backend reuses the Jev question set (`prompts/jev_enrich_v1.json`) as the typed-classifier comparison |
| **Claude Haiku via `claude -p`** | 500 run: 2 verifier calls for 48 reviews, mean 23.7 s, API-equivalent $0.040849 (`runs/live-checkpoint500/state.sqlite`). Final run: 40 calls for 2,000 reviews, API-equivalent $1.464668 (`runs/final-200k/state.sqlite`) | Subscription usage limits; config allows 8 requests per minute to `claude -p` | Verifier |
| **Claude Sonnet via `claude -p`** | 500 run: 12 group calls (API-equivalent $0.071323) and 1 memo call ($0.057585) (`runs/live-checkpoint500/state.sqlite`). Final run, including the five post-run regenerations: 22 group calls (12 in the resume, 10 in the first regeneration) and 7 memo attempts, 5 valid and 2 invalid (both attempts of one regeneration, which then used the template memo); all $0 billed (`runs/final-200k/grading/calls.jsonl.gz`) | Bounded: at most 12 group calls and 2 memo attempts per pipeline pass | Group names, memo, fallback2 |

Other priced alternatives that were not run (Gemini 2.5 Flash-Lite, whose adapter is not built; Claude Haiku
5.5 by API; Luna at Standard tier) appear in `cost/report.md`, "Enrichment-stage alternatives", as token
estimates only.

## Candidate comparison on the golden 50

Eason labelled the 50 reviews by hand (workbook `evals/golden/golden_50_labeled.numbers`, converted by
`evals/golden/convert_labels.py`; conventions in `docs/labels.md`). Each candidate enriched the same 50
texts (human labels are never ingested) and `python -m insight golden` scored each run
(`evals/golden/candidates/*.json`, `evals/golden/results.json`, `evals/golden/ensemble.json`).

| Candidate run | Topic | Intent | Severity exact | All three | Severity MAE | Notes |
|---|---|---|---|---|---|---|
| `runs/golden-luna-none` (production primary setting) | 74% | 70% | 72% | 46% | 0.32 | billed $0.00067 for 50 |
| `runs/golden-luna-low` (effort low, 200 output tokens per review) | 80% | 76% | 76% | 54% | 0.24 | billed $0.000866 for 50 |
| `runs/golden-decisions` (49 requests, the daily limit is 50) | 76% | 74% | 68% | 48% | 0.34 | billed $0.00909; flags 26/50 for review (human: 6) |
| Luna + Decisions rule (`evals/ensemble_golden.py`, threshold 0.80 set before seeing results) | 74% | 74% | 70% | n/a | n/a | the models agree on 96% / 92% / 84% of texts and share their misses |
| **Final 200k run** (effort none + effort low on flagged texts) | 76% | 74% | 76% | 48% | 0.24 | `evals/golden/results.json` |

**Decision.** The predeclared rule (best golden "all three" agreement within the cost cap) points to effort
low. Effort low beat effort none on 4 reviews and lost on none (exact McNemar p = 0.125, not significant at
n = 50), and most disagreements are labelling-convention differences (request vs complaint, praise topic;
see `evals/golden/error_analysis.md`). The labels were finished after the final run, which already uses
effort low for the 13,639 flagged texts. The final run was kept and this is disclosed rather than re-run
(decided with Eason on 2026-10-13); a re-run with effort low as primary would cost about $2.1-2.6 more.
No prompt or setting was changed because of golden results.

## Prices used (`cost/rates.csv`)

| Provider / model | Tier | Input $/1M | Cached input $/1M | Cache write $/1M | Output $/1M | Checked |
|---|---|---:|---:|---:|---:|---|
| OpenAI `gpt-6-luna` | Flex | 0.05 | 0.005 | 0.0625 | 0.25 | 2026-10-10 |
| OpenAI `gpt-6-luna` | Standard | 0.10 | 0.01 | 0.125 | 0.50 | 2026-10-10 |
| OpenAI Decisions (`gpt-6-luna`) | Standard | 0.10 | 0.10 | 0 | 0 | 2026-10-12 |
| TypeSafe `jev-1.13.0` | Standard | 0.042 | 0.042 | - | 0 | 2026-10-01 |
| Anthropic `claude-haiku-4-5` (API-equivalent only) | Standard | 1.00 | 0.10 | 1.25 | 5.00 | 2026-10-10 |
| Anthropic `claude-sonnet-5` (API-equivalent only) | Standard | 2.00 | 0.20 | 2.50 | 10.00 | 2026-10-10 |

Each row's source link is in `cost/rates.csv`. Every OpenAI call sets `reasoning.effort` explicitly
because GPT-6 Luna's default is not the cheapest setting.

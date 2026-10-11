# Model choice (decided 2026-10-01, before any measurement)

The course brief recommends a tool per step: SQL/code for preparation, Jev for fixed labels, a small model
(GPT-6 Luna, Gemini Flash-Lite, Claude Haiku) for language tasks, and Claude Sonnet 5 only as a capped
fallback or memo option. This build follows that plan. **Nothing below has been measured yet**: no API keys
were configured, so the only runs so far used the offline stub. Quality, real token counts and latency must
be measured next week before the full run, and the choice revisited with those numbers.

## Plan

| Stage | Model | Setting | Why |
|---|---|---|---|
| 1 Ingest | none (code + SQLite) | - | Parsing, hashing, profiling, duplicate detection and queueing need no model. |
| 2 Enrich | TypeSafe **`jev-1.13.0`** (pinned, not `jev-latest`) | one review per request; Choice: issue (22 options), intent, severity; Score: sentiment; Noul: unclear; Choice: evidence sentence | Fixed-choice classifier with calibrated probabilities; output is typed by construction; confidence gives a principled `needs_review` and fallback trigger. Jev's docs warn accuracy falls with larger state, so one review per request. |
| 2 Fallback 1 | OpenAI **`gpt-6-luna`** | `reasoning.effort = low`, one review, strict JSON schema, max 600 output tokens; capped at 10% of distinct texts | Generative reader with the full rubric for the cases Jev is unsure about. |
| 2 Fallback 2 | Anthropic **`claude-sonnet-5`** | adaptive thinking at `effort = low`, JSON schema output; capped at 1% | Only when fallback 1 output is invalid twice. Never an automatic upgrade for every failure. |
| 3 Verify | OpenAI **`gpt-6-luna`** | `effort = low`, blind to the enricher, one review | Different model family from Jev, so agreement is a meaningful consistency check. |
| 4 Group | OpenAI **`gpt-6-luna`** | `effort = none`, at most 8 quotes per call, top 12 issues | Names only; membership is code. |
| 6 Memo | OpenAI **`gpt-6-luna`** | `effort = low`, aggregates and evidence pack only | One call; code fills every number. Sonnet 5 can be swapped in by editing `[memo]` if a measured comparison justifies it. |

GPT-6 Luna supports `reasoning.effort = "none"` and `"low"`; its default (`medium`) is not the cheapest, so
every call sets effort explicitly. SDK-internal retries are disabled for all three SDKs.

## Prices and limits used (cost/rates.csv, checked 2026-10-01)

| Model | Input $/1M | Cached input $/1M | Output $/1M | Limits | Source |
|---|---:|---:|---:|---|---|
| jev-1.13.0 | 0.042 | 0.042 | 0 (free) | 40 requests/s, 100k tokens/s, 64k tokens/request | docs.typesafe.ai/models |
| gpt-6-luna | 0.10 | 0.01 | 0.50 | Tier 1: 500 RPM, 500k TPM; batch 50% off | developers.openai.com/api/docs/models/gpt-6-luna |
| claude-sonnet-5 | 2.00 | 0.20 | 10.00 | account dependent | platform.claude.com pricing (skill table dated 2026-09-25) |
| gemini-2.5-flash-lite (alternative) | 0.10 | - | 0.40 | per project, see AI Studio | ai.google.dev/gemini-api/docs/pricing |
| claude-haiku-4-5 (alternative) | 1.00 | 0.10 | 5.00 | account dependent | platform.claude.com pricing |

## Pre-pilot estimate (from `cost/report.md`; estimates, not measurements)

Per-request token sizes come from rendering every request for `checkpoint_500.csv` without sending it
(`python -m insight preflight`, characters / 4). Full run, exact-text reuse, base retries:

| Enrichment option | Requests | API cost | Hours (4 workers) |
|---|---:|---:|---:|
| Jev, one review per request (configured) | 498,715 | $34.90 | 17.3 |
| GPT-6 Luna, 20 reviews per request, effort none | 24,936 | $17.35 | 11.5 |
| GPT-6 Luna, 50 reviews per request, effort none | 9,975 | $14.60 | 9.9 |
| Gemini 2.5 Flash-Lite, 20 per request (adapter not built) | 24,936 | $15.10 | 11.5 |
| Claude Haiku 4.5, 20 per request | 24,936 | $173.46 | 11.5 |

Whole pipeline (enrich + capped fallbacks + verification + group + memo): base with reuse **$47.72**,
conservative without reuse **$149.93** (exceeds the placeholder $60 budget, which the calculator flags).

Jev bills its long question definitions on every review (about 1,666 input tokens per request), so the
batched GPT-6 Luna backend is roughly half the enrichment cost on these estimates. That backend is built
(`enrich.backend = "llm"`) and tested offline; the choice between them should be made on golden-set quality
plus measured cost and time, not on these estimates alone.

## What must be measured next week, in order

1. Keys: `TYPESAFE_API_KEY`, `OPENAI_API_KEY` (and `ANTHROPIC_API_KEY` for fallback 2; without it, set
   `enrich.fallback2.enabled = false`). With only an OpenAI key: `enrich.backend = "llm"`, fallback 1 at
   `effort = "low"`, fallback 2 disabled.
2. Hand-label `golden_50_to_label.csv` (format in `insight/golden.py`).
3. `.venv/bin/python cost/calculator.py pilot --execute --allow-paid --budget-usd 0.50` (cold + warm on the 100).
4. Golden comparison of both enrichment backends (enriching the 50 golden texts costs about a cent at the listed prices, an estimate), then
   tune Jev confidence thresholds on development rows 101-500 only, never on the golden set.
5. Refresh the calculator after 500 and 10,000 reviews, set the budget, then start the full run.

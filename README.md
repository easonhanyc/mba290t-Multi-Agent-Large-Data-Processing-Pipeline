# Spotify Insight Pipeline (MBA 290T final assignment)

Turns Spotify app reviews into an auditable product recommendation: ingest, enrich, verify, group, rank
and recommend, coordinated by code, with saved handoffs between distinct model roles.

> **Status, 2026-10-01: starter build, offline only.** The full pipeline, the 100-review cost calculator
> and 49 tests are built and pass. They were exercised on `checkpoint_500.csv` only (the full CSV was not
> read). **No real model has been called yet**: no API keys were configured, by decision, so every
> model-stage result in `runs/` comes from a local stub server that answers by hashing the request. Those
> runs prove that the plumbing works (resume, caching, retries, budget cap, exports, course checker);
> their labels, issue names and memo text are meaningless. The measured pilot, golden-set evaluation and
> full-corpus run are next week's work (checklist at the end).

## Run it

```bash
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

No API key needed:

```bash
.venv/bin/python -m unittest discover -s tests
./scripts/offline_demo.sh
.venv/bin/python -m insight preflight --input "Final Assignment - Spotify Reviews Dataset/checkpoint_500.csv" --run-dir runs/preflight-checkpoint500
python3 cost/calculator.py
```

`offline_demo.sh` runs the 500-row checkpoint through every stage against the stub, including a real
Ctrl-C, a resume, a warm rerun, the course checker, the rank reproducibility check, the planted-error test,
a fault drill and a budget drill (transcript: `runs/offline-demo-transcript.txt`).

Live runs (billed; need `TYPESAFE_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, see `.env.example`):

```bash
.venv/bin/python cost/calculator.py pilot --execute --allow-paid --budget-usd 0.50
.venv/bin/python -m insight run --input "Final Assignment - Spotify Reviews Dataset/checkpoint_500.csv" --run-dir runs/live-checkpoint500 --allow-paid --budget-usd 1.00
```

Without `--allow-paid` the program refuses to make live calls; missing keys stop it before any work.
Re-running the same command on the same `--run-dir` resumes. Ranking can always be rebuilt from saved
files with `python -m insight rank --run-dir <run> --check` (no model calls).

## Pipeline

| # | Stage | Owner | Model and setting | Key output |
|---|---|---|---|---|
| 1 | Ingest | code | none | `ingestion_report.json`, `ingestion.json` (provided helper), pending queue |
| 2 | Enrich | model + code | `jev-1.13.0`, one review per request; capped fallbacks `gpt-6-luna` (effort low, at most 10%) and `claude-sonnet-5` (effort low, at most 1%) | `enriched.jsonl`, `quarantine.jsonl` |
| 3 | Verify | model + code | `gpt-6-luna` (effort low), blind, declared random sample (10% of distinct texts in development runs) | `verification/report.json`, `disagreements.csv` |
| 4 | Group | code + model | membership by code (`issue_id = topic.subtopic`); `gpt-6-luna` (effort none) names the top 12 issues from at most 8 quotes | `membership.csv`, `issues.json` |
| 5 | Rank | code | none: `priority = severity_sum = count x mean severity` | `ranking.csv`, `aggregates.csv`, `area_rollup.json` |
| 6 | Memo | model + code | `gpt-6-luna` (effort low) sees aggregates and an evidence pack only; it writes claim tokens, code fills every number | `memo.md`, `claims.csv` |

Details: [docs/architecture.md](docs/architecture.md) (diagram, control flow, state, controls),
[docs/labels.md](docs/labels.md) (taxonomy, intent precedence, severity rubric, worked examples),
[docs/model_choice.md](docs/model_choice.md) (why these models, prices, estimates, what to measure).

Design points:
- **Classification input is `review_text` only.** Ingest stores the six source fields; any other column
  (such as golden answers) is dropped before anything can reach a prompt (tested).
- **Exact quotes by construction.** Code splits each review into exact slices; the model picks a sentence
  number. **Entities** are matched by code. No model retypes source text.
- **Exact-text reuse.** One result per distinct text; duplicates carry `cache_source_id` to a direct
  original. `label_config` covers models, efforts, prompts, schema, thresholds and fallback caps.
- **Saved per review, atomically.** Every attempt is logged before it is sent; completed records are never
  relabelled under the same configuration; resume sends only pending reviews.
- **Controls.** One worker by default; shared per-provider rate limiter; one spend ledger with worst-case
  reservations; bounded exponential backoff with jitter; one retry for invalid output; circuit breaker;
  graceful Ctrl-C. SDK-internal retries are disabled so every attempt is priced and logged.
- **Deterministic fallback selection.** Difficult reviews are staged during the primary pass; once every
  primary result is in, code routes the lowest-confidence ones first, up to the cap. The same reviews get
  the fallback whatever the worker count or interruption points (tested).

## Evidence from this build

All of it is offline. "Stub" means the local test server: control flow is real, labels are not.

| What | Result | Where |
|---|---|---|
| Unit and integration tests | 49 pass in about 20 s: hashing parity with the provided `row_sha` on all 500 rows, exact-substring segments, label/consistency rules, rates and ledger, ranking arithmetic, memo validation, calculator invariants, retries (429/500/timeout), invalid output retried once, budget stop, circuit breaker, real SIGINT then resume, two workers give identical labels, an interrupted-and-resumed run gives the same labels as an uninterrupted one, a label_config change needs a new run directory, batched-LLM backend, refusal without `--allow-paid`, a second invocation on the same run directory refused | `tests/` |
| Ingestion of `checkpoint_500.csv` | 500 rows, 500 nonempty, 0 empty, 479 distinct texts (21 exact-text reuses), 108 missing app versions, checksum matches the manifest | `runs/offline-stub-checkpoint500/ingestion_report.json` |
| Course checker on the 500-row export (stub labels) | `pass`, 0 issues: 500 valid records, 21 valid cache reuses, ranking and claims recomputed, resume evidence present | `runs/offline-stub-checkpoint500/self-check.json` |
| Interruption and resume (real SIGINT) | 66 records saved and 48 staged at interruption (exit 130); resume sent only the 377 pending texts, then routed the 47 lowest-confidence of 211 staged reviews to fallback1 (cap 47) and kept the primary label, flagged, for the other 164; warm rerun made 0 model calls (timing-dependent counts from the latest `offline_demo.sh` run) | `checkpoint_before.json`, `checkpoint_after.json`, `runs/offline-demo-transcript.txt` |
| Rank reproducibility | ranking rebuilt from `grading/` files is byte-identical | `runs/offline-stub-checkpoint500/rank_check.json` |
| Planted wrong label | detected (intent, topic, severity flipped in a test copy) | `runs/offline-stub-checkpoint500/evals/planted_error.json` |
| Fault drill | 429 x2, 500, timeout, malformed classifier answer, malformed and truncated LLM output: all handled, 500 of 500 completed | `runs/offline-stub-fault-drill-500/` |
| Budget drill | stub calls priced at real rates, cap $0.005: stopped at $0.0050 when the next reservation would cross the cap, 454 rows exported as `unfinished`; resumed under a larger cap | `runs/offline-stub-budget-drill-500/` |
| Injection cases | empty texts quarantined; markup and JSON in a review did not break requests; label checks need a live run | `runs/offline-stub-synthetic-injection/evals/synthetic_check.json` |
| Scale (synthetic 20,000 rows, limits lifted) | 25.7 s end to end, about 1.25 ms of pipeline overhead per enrichment attempt, 0.1 s of code stages per 1,000 rows, 127 MB peak memory: the provider rate limits, not the pipeline, set full-run speed | `runs/offline-stub-scale-20k/scale_summary.json` |
| Cost calculator | measured pilot **not run yet** (stated, not estimated); full-run estimate $47.72 base with reuse, $149.93 conservative without reuse (flagged over the placeholder $60 budget) | `cost/report.md` |

## Rubric map

| Criterion | Evidence today | Still needed |
|---|---|---|
| Accessible code and setup | this README, `requirements.txt`, `.env.example`, tests | publish the repo |
| Architecture, schema, provenance | `docs/architecture.md`, `docs/labels.md`, `label_config` on every record and call | - |
| Memo numbers linked to calculations | `claims.csv`, token-only memo, checker claim check (stub) | live memo |
| Coherent recommendation and limits | memo template and code-appended limitations | live memo on full data |
| 50 human labels, per-field comparison | `insight/golden.py`, `evals/README.md` | **Eason labels the golden 50**; live run |
| Independent verification, planted error, injection | stage 3, `planted-error`, `evals/synthetic/` | live verifier and injection run |
| 100-review cold/warm pilot and calculator | `cost/calculator.py`, `cost/report.md`, `cost/offline_stub_example/` | **real pilot** (one command) |
| Full ingestion, coverage, classification | ingest streams any CSV; checker passes on the 500 export | full CSV run (660,622 rows) |
| Staged program, bounded calls, resume | `insight/`, resume demo, checker resume evidence | recording of a live interruption |
| Reproducible ranking, grounded output | `rank --check`, `claims.csv` | final `grading/` from the full run |

## Layout

```
insight/            pipeline package (python -m insight); providers/ = Jev, OpenAI, Anthropic adapters; stub.py = offline test server
config/pipeline.toml  every setting; label-affecting ones are hashed into label_config
prompts/            Jev questions (rendered from insight/labels.py) and LLM role prompts
cost/               calculator, dated rates, editable assumptions, report
evals/              synthetic injection cases and checker, golden labelling guide
docs/               architecture, labels and worked examples, model choice
tests/              unit, integration and calculator tests
scripts/offline_demo.sh   end-to-end offline demonstration on checkpoint_500
runs/               offline-stub evidence runs (stub labels are not findings)
```

Dataset: `Final Assignment - Spotify Reviews Dataset/` (course files; the 97.4 MB CSV is git-ignored).
Full CSV SHA-256 `1fc85de68a304dd8978b537cfa58793d5f41cbaf417fa32cb53899f83a2fcef6`; checkpoint_500 SHA-256
`a94e31663ee7b7eaa77e23b7a8425b530cc0c866ed5e714953172a0afef6a12f` (verified).

## Next week, in order

1. Add API keys (see `docs/model_choice.md` for the single-key alternative).
2. Hand-label `golden_50_to_label.csv` (`evals/README.md`).
3. Real 100-review pilot: `.venv/bin/python cost/calculator.py pilot --execute --allow-paid --budget-usd 0.50`.
4. Live 500-row run; golden comparison of the Jev and batched-Luna backends; tune Jev thresholds on
   development rows only; injection run.
5. `analysis_10000.csv`, refresh the calculator, set the budget, then the full 660,622-row run, its
   interruption/resume recording, `grading/` export and `check_submission.py`.

## Limitations of this build

- No real model output exists yet, so there is no measured cost, latency, label quality, verifier
  agreement or recommendation.
- The full CSV was not ingested; full-run counts in the calculator come from the course contract.
- Jev confidence thresholds are placeholders until tuned on development reviews.
- A Gemini adapter is not built (Gemini appears only as a priced alternative).
- If real difficulty rates exceed the fallback cap, the least difficult of the staged reviews keep their
  primary label with `needs_review`; tune the thresholds on development reviews so the cap rarely binds.
- The rare fallback2 path (fallback1 output invalid twice) is routed as it happens, so if its 1% cap binds
  under concurrency, which reviews get it can depend on completion order.

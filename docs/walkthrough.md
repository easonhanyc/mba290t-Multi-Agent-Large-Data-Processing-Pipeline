# System walkthrough and one failure

A short guide for explaining the pipeline aloud and for the fresh-input demonstration the instructor may ask for.
Every statement points to a file in this repository.

## The system in five minutes

**The question.** Where should next quarter's product effort go: access, usability, playback or billing/support?
The answer must be inspectable: every number in the recommendation traces to saved records.

**1. Ingest (code).** `insight/ingest.py` reads the CSV with a real CSV parser, hashes every row
(`source_sha256`, the contract's convention), profiles the full 660,622-row file with the course's own helper,
and finds exact duplicate texts so each distinct text is labelled once (`cache_source_id` on the copies). Empty
texts are quarantined as `empty_review_text`. No model is involved.

**2. Enrich (GPT-6 Luna + code).** Up to 50 distinct texts per request, split into numbered sentences
(`insight/segment.py`). The model answers only what needs language judgement: issue key, intent, severity,
sentiment level, which sentence is the evidence, and an ambiguity flag (`prompts/llm_enrich_v2.md`, strict JSON
schema). Code turns the sentence number into an exact quote, matches entities, validates every returned ID and
every field, and saves each batch atomically in `state.sqlite`. Invalid output gets one retry; 429s and timeouts
get bounded backoff with jitter. Flagged or self-contradictory answers are routed after all primary results are
in, up to a declared cap, to a second, single-review read (fallback1), and only if that fails twice to Claude
Sonnet (fallback2, capped at 0.25%).

**Why this model and setting.** Three setups labelled the same 50 golden reviews before the final run was chosen:
Luna effort none, Luna effort low and the OpenAI Decisions classifier. The predeclared rule (best "all three
correct" within the cost cap) picked Luna effort low, and the final run uses that candidate's exact configuration
(`label_config` hash `cfg-52c5333247`; `docs/model_choice.md`). Because the golden set made the choice, the final
run's golden scores are slightly optimistic; the blind verifier sample and the quote check on a random sample of the
final run played no part in the choice (`evals/golden/error_analysis.md`, section 3).

**3. Verify (Claude Haiku + code).** A different model family relabels a declared random sample (10% of distinct
texts, at most 2,000) without seeing the enricher's answer (`prompts/verify_v2.md`). Code compares field by field
and saves every disagreement (`verification/`). A planted wrong label on a test copy checks that the comparison
catches errors.

**4. Group (code + Claude Sonnet for names only).** Complaint and cancellation records are grouped by
`issue_id = topic.subtopic`; membership is code. Claude Sonnet only names the top issues from a uniform sample of
12 member quotes each.

**5. Rank (code).** `priority_score = severity_sum` (complaint count x mean severity), ties by `issue_id`
(`insight/rank.py`). `python -m insight rank --check` rebuilds it from the grading files with no model call.

**6. Memo (Claude Sonnet + code).** The model receives saved aggregates and a bounded evidence pack, and writes
prose with tokens such as `{C01}` instead of numbers. Code fills in every number, rejects any digit typed outside a
token, checks every cited ID, and appends limitations the model cannot remove (`insight/memo.py`,
`prompts/memo_v2.md`). `claims.csv` and `memo_tokens.csv` say where each number comes from.

**Around the stages.** One spend ledger reserves the worst case before each call and stops admitting work at the
per-run cap; a project cap ($9.00) sums every run directory. A stopped run resumes from `state.sqlite` and never
pays to relabel a completed text under the same `label_config` (`grading/checkpoint_before.json`,
`checkpoint_after.json`, recordings in `runs/<final run>/recording/`). The database, backend and dashboard only
read saved results (`web/`); the dashboard recomputes the ranking and the memo's numbers in SQL on request
(`/api/consistency`).

**Where code decides and where a model judges.** Code decides what to send, when to retry, route, stop or resume,
and does all counting and arithmetic. Models judge only bounded language questions with a fixed schema.

## One failure, end to end: the Claude Pro session limit looked like a momentary 429

**What happened.** During the 10,000-review checkpoint with the final setup (2026-10-14,
`runs/live-analysis10000-low`), the Claude Pro plan reached its session limit while the verify, group and memo
stages were running. The `claude` CLI reported it as HTTP 429 with the text "You've hit your session limit ·
resets 4:30pm". The adapter recognised Pro limits only by older wordings ("usage limit", "5-hour limit", ...), so it
classed the error as transient: 68 verify, 40 group and 4 memo attempts failed, and the stages fell back
gracefully. Group names fell back to taxonomy names, the memo to the deterministic template, and the verification
report compared 0 reviews. The run still ended "completed" (`runs/analysis10000_low_console.log`, the first
invocation in `runs/live-analysis10000-low/invocations/`).

**How it was caught.** The run's memo line said `source: template (model memo failed validation)`. The memo's
`validation_problems` in `memo.json` named the 429, and the `calls` table showed every Claude call failing with
the same message.

**Why it matters.** A plan limit is not momentary. Treating it as transient silently produces a weaker result (no
verification, no model-named issues, a template memo) instead of stopping, and a person reading only the final
status line would not know.

**The fix.** `insight/providers/claude_code.py` now treats this wording, and any message that pairs "limit" with
"resets" or "hit your", as a systemic stop (`is_usage_limit`). A systemic error stops admission, saves progress
and ends the run with a stop reason, so the next invocation resumes the missing stages. A new stub fault reproduces
the exact message (`STUB_CLAUDE_FAULT=session`), and `tests/test_extensions.py` checks that it is systemic.

**Recovery.** Nothing was paid twice. The failed Claude stages had saved nothing (no verification rows, no
stage-cache entries), and enrichment was complete. Rerunning the same command (`./scripts/live.sh analysis10k 8`)
resumed with zero enrichment calls and redid verify, group and memo. Its second invocation and the refreshed
calculator are in the same run directory and in `cost/refreshes/analysis_10000_low.json`.

**Other failures worth knowing** (each with a recorded handling decision):
- The first naming pass called the catch-all issue `other.general` "Privacy and data collection concerns" because
  it saw only the 8 highest-severity quotes. Naming now uses a uniform sample, and catch-alls keep their taxonomy
  names (`docs/post_run_corrections.md`, section 1).
- The memo once recommended usability because its robustness check compared areas by complaint count instead of
  the baseline severity sum (`docs/post_run_corrections.md`, section 2).
- An exhausted OpenAI credit returns its own error code. It is mapped to a systemic stop so the run does not
  retry against an empty balance (`insight/providers/openai_responses.py`, `QUOTA_CODES`).

## Fresh-input demonstration

Any CSV with a review-text column works; the other source columns are filled blank when missing, and source values
are never edited (`scripts/prepare_fresh_input.py`).

```bash
./scripts/fresh_input_demo.sh path/to/fresh.csv            # live: real models, BUDGET (default $0.05) per run
./scripts/fresh_input_demo.sh path/to/fresh.csv --offline  # no key and no cost: stub models, labels meaningless
```

The script prepares the file, runs every stage, and, when the file has more than 50 distinct texts, stops after
the first saved request and resumes, so the checkpoints show an interruption. It then runs the course checker
against a reference built from the same file, rebuilds the ranking without a model, and prints counts, spend, the
top issues and the memo's first line. A live run needs the git-ignored `.env` with `OPENAI_API_KEY`, the `claude`
CLI logged in with Claude Pro, and no other live run in progress (`runs/.live.lock`).

Rehearsal on real reviews the pipeline had never labelled: see the README, "Fresh-input demonstration".

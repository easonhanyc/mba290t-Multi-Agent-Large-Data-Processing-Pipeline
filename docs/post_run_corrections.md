# Post-run corrections

Two runs have post-run corrections. Labels were never changed after a run: each correction reran only the stages
after enrichment on the same run directory, from the saved labels, with no enrichment calls.

## Final run (`runs/final-200k-v2`): the memo was regenerated twice

| # | Invocation | Workers | Wall clock s | Model calls | Memo | Recommended area |
|---:|---|---:|---:|---|---|---|
| 1 | `run-20261014T233644.409Z-a3e1` (initial) | 16 | 199.8 | enrich 138 | none (stopped by SIGINT) | - |
| 2 | `run-20261014T234005.530Z-f920` (resume) | 16 | 9,012.7 | enrich 5,228, verify 40, group 10, memo 2 (1 rejected) | model ([memo_history/1-...](../runs/final-200k-v2/memo_history/1-run-20261014T234005.530Z-f920.md)) | billing/support |
| 3 | `run-20261015T032949.255Z-ff9e` | 4 | 86.1 | memo 1 | model ([memo_history/2-...](../runs/final-200k-v2/memo_history/2-run-20261015T032949.255Z-ff9e.md)) | usability |
| 4 | `run-20261015T033337.582Z-bf5d` | 4 | 91.3 | memo 1 | model, the final [memo.md](../runs/final-200k-v2/memo.md) | usability |

Sources: `runs/final-200k-v2/invocations/*.json`, `calls` table of the run's `state.sqlite`, and the two earlier memos
with their `memo.json` in `runs/final-200k-v2/memo_history/`. Every invocation from #2 on reports the same 22 issues,
91,268 memberships and ranking; the rank check is identical.

1. **Memo #1 departed from the baseline without same-metric evidence.** It recommended billing/support while the area
   with the highest baseline priority was usability (severity sum 52,983 against 52,551), so code added a visible
   "Check" line to it. The memo prompt already said a departure needs trend or robustness evidence on the severity-sum
   metric; memo #1 argued from the growth in share of reviews (a count-based trend) and the size of one issue, and the
   severity-sum robustness figures did not support billing/support (the verifier's labels put it third; the
   premium-only upper-bound sensitivity would put it third). **Fix:** the prompt now says count-based trends, spike
   lifts and single-issue size can support but never by themselves justify a departure, and that a departure must
   be argued in the first rationale point (`prompts/memo_v2.md`). Memo #2 recommended usability.
2. **Memo #2 misused "within sampling error"** (it called usability's share higher "within sampling error" although no
   two decision areas' intervals overlap) and said a human audit confirming the premium-only records would
   strengthen billing/support (they are already counted there). **Fix:** the validator now rejects "within sampling
   error" when no intervals overlap (`insight/memo.py`, `validate`), and the prompt says confirming those records
   leaves billing/support unchanged. Memo #3, the final memo, recommends usability and passed validation on its first
   attempt. Tests: `tests/test_pipeline_fixes.py::TestPlanLimitStopsInsteadOfDegrading`.

Both regenerations were Claude Pro calls ($0 billed); the run's billed total stays $2.323945 (`ledger` in
`run_summary.json`, plus $0.097098 reserved for unknown-outcome enrichment calls).

## Superseded first final run (`runs/final-200k`, effort none)

The labels of `runs/final-200k` were produced by its first two invocations (initial, interrupted by SIGINT, then
resume) and were never changed afterwards. After the run, two reviews of the outputs led to corrections in how
issues are **named**, which **metric** is used to compare the four decision areas, and how the **memo is
validated and written**. The final run used the corrected code from its start.

### Invocations of the superseded run

Sources: `history` in [`runs/final-200k/run_summary.json`](../runs/final-200k/run_summary.json), one file per
invocation in [`runs/final-200k/invocations/`](../runs/final-200k/invocations/) (`workers`, `wall_clock_s`,
`calls_this_invocation`, `stage_configs`, `stages.memo.source`), and the memo outputs saved in the `stage_cache`
table of `runs/final-200k/state.sqlite` (release asset, see the README).

| # | Invocation | Workers | Wall clock s | Model calls | Memo | Recommended area |
|---:|---|---:|---:|---|---|---|
| 1 | `run-20261012T232925.093Z-9d9d` (initial) | 16 | 208.431 | enrich 112 | none (stopped by SIGINT) | - |
| 2 | `run-20261012T233254.463Z-c2b5` (resume) | 16 | 8,765.993 | enrich 16,766, verify 40, group 12, memo 1 | model | usability |
| 3 | `run-20261013T020340.008Z-bf6f` | 4 | 66.589 | group 10, memo 1 | model | usability |
| 4 | `run-20261013T020708.758Z-2e20` | 4 | 58.970 | memo 1 | model | billing/support |
| 5 | `run-20261013T020919.171Z-a0b9` | 4 | 56.148 | memo 1 | model | billing/support |
| 6 | `run-20261013T233601.448Z-8794` | 4 | 115.389 | memo 2 (both rejected) | template (model memo failed validation) | - (template, no model judgement) |
| 7 | `run-20261013T233959.792Z-f394` | 4 | 62.840 | memo 1 | model | billing/support |
| 8 | `run-20261014T183909.239Z-202d` | 4 | 77.840 | memo 1 | model | billing/support |
| 9 | `run-20261014T184128.634Z-8a66` | 4 | 91.289 | memo 1 | model | billing/support |
| 10 | `run-20261014T184351.433Z-0d14` | 4 | 83.378 | memo 1 | model | billing/support |
| 11 | `run-20261014T184545.752Z-3a1e` | 4 | 71.048 | memo 1 | model (the final memo) | billing/support |
| 12 | `run-20261014T184902.112Z-bd73` | 4 | 24.142 | none | model, reused from the stage cache (generated in #11) | billing/support |

Total wall clock 9,682.057 s (`cost/refreshes/final_200k.json`); the ten regenerations (#3 to #12) took 707.6 s
in all. Every invocation from #2 on reports 22 issues, 89,762 complaint and cancellation memberships and the same
top five issues with the same counts and severity sums (`stages.rank` and `stages.group` in each invocation file),
and the final rank check is identical, so no correction changed a label, a membership or a rank. Over the whole run the Claude roles made 22 group calls and 11 memo attempts (9 valid,
2 rejected), all through `claude -p` on Claude Pro, $0 billed
([`grading/calls.jsonl.gz`](../runs/final-200k/grading/calls.jsonl.gz)). The run's billed total stays
$2.019246 (`ledger` in `run_summary.json`).

### 1. Issue naming: the catch-all was misnamed

**Found.** The first naming pass (invocation #2) gave the naming model each issue's 8 highest-severity quotes.
It named the catch-all `other.general` "Privacy and data collection concerns" (`stage_cache`, group output of
#2), although only 8 of its 14,796 distinct complaint texts mention privacy (`insight/group.py`, docstring of
`evidence_pack`).

**Fixed.** Naming evidence is now a deterministic uniform sample of 12 member texts per issue, and the
catch-alls `other.general` and `usability.other` keep their taxonomy names (`config/pipeline.toml` `[group]`,
`insight/group.py`). Invocation #3 renamed the top issues with 10 group calls. Membership is code and did not
change.

### 2. Metric choice: which measure ranks the four decision areas

The contract's baseline priority is the severity sum (`priority_score = severity_sum`, `insight/rank.py`). The
two natural measures point to different areas, and both are reported:

| Measure | Billing/support | Usability | Playback/performance | Source |
|---|---:|---:|---:|---|
| Severity sum (baseline priority) | **59,146** | 54,124 | 46,058 | `runs/final-200k/area_rollup.json` |
| Complaint and cancellation records | 20,290 | **23,004** | 13,907 | same |
| Share of complaints (95% interval) | 22.6% (22.3-22.9%) | **25.6%** (25.3-25.9%) | 15.5% (15.3-15.7%) | `runs/final-200k/memo.md`, T19-T27 |

Billing/support leads on severity sum because its complaints are more severe on average; usability leads on
complaint count and share of complaints, and the intervals do not overlap.

**Found.** The verifier robustness check compared areas by complaint count, not by the baseline metric, so the
memo was judging the top area on a different measure from the ranking. The first two model memos (#2 and #3)
recommended usability.

**Fixed.** The robustness check now uses the row-weighted severity sum (`insight/analysis.py`;
`runs/final-200k/analysis/robustness.json` keeps the complaint-count view under `by_complaint_count`, where
both label sets put usability first). The memo prompt judges the top area on the baseline metric and must say
plainly when the recommended area leads on one measure but not the other (`prompts/memo_v2.md`, rules on
trends and robustness). The memo model also receives the trend values (`insight/memo.py`). From invocation #4
on, every model memo recommended billing/support.

This is a choice of metric, not a change of evidence: on the 2,000-review verification sample the enricher's
labels put billing/support first on severity sum (787) and the verifier's labels put playback/performance first
(758, billing/support third with 661) (`analysis/robustness.json`, memo tokens T42-T48). The memo states this
disagreement and calls the recommendation provisional.

### 3. Memo validation and the template fallback

The memo model writes tokens only; code fills every number and rejects any digit typed outside a token
(`insight/memo.py`). Before invocation #6 the memo prompt was extended to ask for concrete next-quarter
actions and what would change the call, and to frame `billing.premium_only` as free-tier packaging and
entitlement policy. In #6 both memo attempts typed digits outside tokens (spike months and comparison periods),
so the run fell back to the deterministic template memo, marked as such
([`invocations/run-20261013T233601.448Z-8794.json`](../runs/final-200k/invocations/run-20261013T233601.448Z-8794.json)).
The spike months and comparison periods were then turned into tokens (`insight/memo.py`), and the model memo of
#7 validated on its first attempt.

### 4. Memo revisions after the second review (invocations #8 to #11)

A second grading review of the memo found one wrong comparison ("largest increase of any area", while the
non-decision area general/unspecified rose more), a sentence that called non-overlapping shares close, a
limitation that compared enricher and verifier labels unlike for like, and two missing limitations. From #8 on,
the analysis includes the premium-only sensitivity (`stages.analysis` in each invocation file). Each of #8 to #11
ran with a changed memo prompt or setting (a new memo config hash in each invocation file) and made one memo call,
valid on the first attempt. The final memo
([`runs/final-200k/memo.md`](../runs/final-200k/memo.md), generated in #11, `memo.json`: no rejected outputs,
no validation problems) now:

- limits growth comparisons to "the four decision areas" and lists the non-decision areas separately
  (general/unspecified +19.3 pp, T55; `analysis/period_comparison.json`);
- says which share is higher when the 95% intervals do not overlap, and which area leads on which measure;
- compares like with like in the robustness caveat (enricher order and verifier order, each on its own labels);
- keeps share of complaints and share of reviews apart (`prompts/memo_v2.md`);
- appends two limitations written by code, not by the model (`code_written_limitations` in `memo.json`):
  25.7% (A19) of complaint and cancellation records are general/unspecified and not allocated to any decision
  area; and the premium-only sensitivity: 4,785 (T56) of the 18,016 `billing.premium_only` records contain no
  Premium or payment word (severity sum 14,239, T57), and if none of them belonged to billing/support its
  severity sum would fall from 59,146 (A02) to 44,907 (T58), below usability (54,124) and playback/performance
  (46,058). This is an upper bound, not a relabelling
  ([`analysis/premium_only_sensitivity.json`](../runs/final-200k/analysis/premium_only_sensitivity.json)).

Invocation #12 re-ran group, rank, memo and export with the issue names and the memo reused from the stage
cache (no model call).

### 5. How the corrected outputs were checked

- Course checker against the declared-scope reference: `pass`, 0 issues, coverage candidate 1.0
  ([`runs/final-200k/self-check.json`](../runs/final-200k/self-check.json)).
- Rank check: identical, 22 issues, checked 2026-10-14 18:50 UTC, after the last invocation
  ([`runs/final-200k/rank_check.json`](../runs/final-200k/rank_check.json)).
- Every memo number is listed with its value and source file in
  [`memo_tokens.csv`](../runs/final-200k/memo_tokens.csv); claims C01-C40 are in `claims.csv` and equal
  `grading/claims.csv`.
- Cost: `cost/calculator.py refresh` then replay; the final-run refresh covers all 12 invocations
  (`cost/refreshes/final_200k.json`), and billed spend is unchanged because no correction made a billed call.
- At the time, the trace and the dashboard database were regenerated from the corrected export. Both now show the
  final run (`runs/final-200k-v2`).

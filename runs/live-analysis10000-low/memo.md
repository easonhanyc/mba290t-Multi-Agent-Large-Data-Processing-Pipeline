# Decision memo: where to focus next quarter

Scope: a 10000-review development checkpoint (analysis_10000.csv), not the full corpus  
Run: `run-20261014T233303.701Z-f908` | input `Final Assignment - Spotify Reviews Dataset/analysis_10000.csv` (sha256 `eaa62ca6d44d7173...`) | memo source: model

Numbers are written as value (token ID): C## IDs are the issue-level claims in `claims.csv`; every ID (C##, A## area roll-up, S## scope figure, T## trend/robustness) is listed with its value, what it measures and its source file in `memo_tokens.csv`.

## Recommendation

**usability.** Usability should get the next quarter of effort, anchored by ad interruptions (587 (C09) complaint and cancellation reviews, severity sum 1238 (C10)), playback-control and shuffle/repeat malfunctions (248 (C17) reviews, severity sum 735 (C18)), and the confusing redesigned navigation (168 (C29) reviews, severity sum 429 (C30)). This is interface and control-reliability work: reducing ad load, fixing shuffle/repeat/queue behavior, and clarifying the redesigned layout.

> **Check:** the baseline's highest-priority decision area is **billing/support** (severity sum 2734 (A05)), not the recommended area. A reviewer must confirm the memo justifies the difference.

## Next-quarter actions

1. Reduce ad frequency or length for free-tier listening around the ad-interruptions issue (587 (C09) reviews, severity sum 1238 (C10)); if effective, the complaint count 587 (C09) and severity sum 1238 (C10) for this issue should fall.
2. Stabilize shuffle, repeat, and queue/playlist behavior tied to the library-controls issue (248 (C17) reviews, severity sum 735 (C18)); test fixes against this issue's severity sum 735 (C18) to confirm improvement.
3. Simplify or restore access to features affected by the redesigned layout behind the navigation issue (168 (C29) reviews, severity sum 429 (C30)); track whether usability's share of complaints 24.4% (T19) declines afterward.
4. As a hedge on the strongest alternative, monitor the premium-only restrictions issue (816 (C05) reviews, severity sum 2413 (C06)) given its rising trend +10.9 pp (T12) and the +26.3 pp (T39) spike in 2023-10 (T36), since a continued rise could change next quarter's priority.

## Why

- On the full dataset, billing/support's severity sum 2734 (A05) and usability's severity sum 2716 (A08) are close, with billing/support marginally higher; but usability clearly leads billing/support on share of complaints (24.4% (T19) versus 20.2% (T22), intervals not overlapping), and usability also leads on the verifier's independent re-labeling of the same sample under both labelings (enricher severity sums 333 (T43) versus 274 (T44); verifier severity sums 374 (T47) versus 300 (T48)), with the verifier reporting the same top area as the enricher.
- The premium_only_sensitivity upper-bound check shows billing/support's narrow full-data lead is fragile: removing the 112 (T57) premium-only records that contain no Premium or payment word (severity sum 332 (T58)) would drop billing/support's severity sum to 2402 (T59), below both usability 2716 (A08) and playback/performance 2478 (A11).
- Between 2022 Jun-Oct (T01) and 2023 Jun-Oct (T02), billing/support's share of reviews rose +10.9 pp (T12), the largest increase among the four decision areas, while usability's share fell -2.1 pp (T18); this is a reason billing/support deserves monitoring, but it does not overturn usability's lead on the baseline severity-sum metric in the sampled robustness checks above.
- Within usability, ad interruptions (587 (C09), severity 1238 (C10)) and library/playback-control malfunctions (248 (C17), severity 735 (C18)) are the largest-severity issues, with navigation confusion (168 (C29), severity 429 (C30)) a secondary but sizeable contributor.
- A spike in 2023-10 (T36) shows the premium-only issue rising sharply (+26.3 pp (T39)), reinforcing that billing/support warrants watching even though usability is the recommended lead for the next quarter.

## What would change this call

- A human audit of the 112 (T57) premium-only records without a Premium or payment word (severity sum 332 (T58)) finding that most genuinely belong in billing/support would restore billing/support's full-data lead on severity sum 2734 (A05) over usability 2716 (A08).
- The verifier's severity-sum ordering reversing (favoring billing/support over usability) on a larger verified sample than the current 845 (T42) reviews would weaken the case for usability.
- Usability's share of reviews continuing to fall, or billing/support's share of reviews +10.9 pp (T12) continuing to rise, in the same months of the following year would support shifting priority toward billing/support instead.

## Alternatives considered

- **billing/support**: Its full-dataset severity sum 2734 (A05) is close to usability's 2716 (A08), but its lead does not hold up: the verifier's sampled severity sums put it behind usability under both labelings (274 (T44) and 300 (T48) versus 333 (T43) and 374 (T47)), and the premium_only_sensitivity upper bound shows its severity sum could fall to 2402 (T59) if records without a Premium or payment word (112 (T57), severity 332 (T58)) are excluded, dropping it below usability 2716 (A08) and playback/performance 2478 (A11). Its top issue, premium-only restrictions (816 (C05) reviews, severity 2413 (C06)), is free-tier packaging and entitlement policy, not a usability or defect fix.
- **playback/performance**: Its severity sum 2478 (A11) and share of complaints 16.2% (T25) trail usability's 2716 (A08) and 24.4% (T19), and its share of reviews fell -3.1 pp (T15) between 2022 Jun-Oct (T01) and 2023 Jun-Oct (T02). Its top issues, wrong-song playback (316 (C13) reviews, severity 1022 (C14)) and crashes (147 (C21) reviews, severity 563 (C22)), have the highest mean severities per issue but a smaller overall footprint.
- **access/onboarding**: It has the smallest severity sum 549 (A17) and share of complaints 3.1% (T28) among the four decision areas, despite a rising share of reviews +0.6 pp (T09). Its top issue, login failures (123 (C25) reviews, severity 483 (C26)), has a high mean severity but far fewer affected reviews than usability's issues.

## Supporting numbers (baseline ranking, computed by code)

Priority = severity_sum = complaint_count x mean_severity over complaint and cancellation reviews. Each cell shows the value and its claim ID in `claims.csv`.

| Rank | Issue | Area | Complaints | Severity sum | Mean severity | Priority |
|---:|---|---|---:|---:|---:|---:|
| 1 | General or unrelated (`other.general`) | general/unspecified | 1355 (C01) | 2736 (C02) | 2.019188 (C03) | 2736 (C04) |
| 2 | Premium-only restrictions (`billing.premium_only`) | billing/support | 816 (C05) | 2413 (C06) | 2.957108 (C07) | 2413 (C08) |
| 3 | Ad interruptions (`usability.ads`) | usability | 587 (C09) | 1238 (C10) | 2.109029 (C11) | 1238 (C12) |
| 4 | Playback plays wrong or random songs instead of selection (`playback.stops`) | playback/performance | 316 (C13) | 1022 (C14) | 3.234177 (C15) | 1022 (C16) |
| 5 | Playback controls and shuffle/repeat malfunctions (`usability.library`) | usability | 248 (C17) | 735 (C18) | 2.963710 (C19) | 735 (C20) |
| 6 | App crashes and freezes frequently (`playback.crash`) | playback/performance | 147 (C21) | 563 (C22) | 3.829932 (C23) | 563 (C24) |
| 7 | Login failures (`access.login`) | access/onboarding | 123 (C25) | 483 (C26) | 3.926829 (C27) | 483 (C28) |
| 8 | Confusing redesigned layout hard to navigate (`usability.navigation`) | usability | 168 (C29) | 429 (C30) | 2.553571 (C31) | 429 (C32) |
| 9 | Other control annoyances (`usability.other`) | usability | 123 (C33) | 314 (C34) | 2.552846 (C35) | 314 (C36) |
| 10 | Unwanted auto-added recommended songs (`catalog.recommendations`) | catalog/content | 95 (C37) | 270 (C38) | 2.842105 (C39) | 270 (C40) |

## Area roll-up (derived from the issue table; not a contract metric)

| Area | Complaints | Severity sum | Share of complaints |
|---|---:|---:|---:|
| general/unspecified (not one of the four options) | 1355 (A01) | 2736 (A02) | 0.293799 (A03) |
| billing/support | 931 (A04) | 2734 (A05) | 0.201865 (A06) |
| usability | 1126 (A07) | 2716 (A08) | 0.244146 (A09) |
| playback/performance | 748 (A10) | 2478 (A11) | 0.162186 (A12) |
| catalog/content (not one of the four options) | 311 (A13) | 911 (A14) | 0.067433 (A15) |
| access/onboarding | 141 (A16) | 549 (A17) | 0.030572 (A18) |

## Trends and robustness (descriptive, computed by code)

Same calendar months one year apart (full months only). Share = the area's complaint and cancellation reviews / all classified reviews in the period.

| Area | 2022 Jun-Oct (T01) | 2023 Jun-Oct (T02) | Change |
|---|---:|---:|---:|
| access/onboarding | 1.1% (T07) | 1.6% (T08) | +0.6 pp (T09) |
| billing/support | 4.1% (T10) | 15.0% (T11) | +10.9 pp (T12) |
| playback/performance | 8.8% (T13) | 5.7% (T14) | -3.1 pp (T15) |
| usability | 11.3% (T16) | 9.3% (T17) | -2.1 pp (T18) |
| Denominator (classified reviews) | 2243 (T03) | 4102 (T05) | |

Note (code): this table, and any comparison of growth in this memo, covers the four decision areas only. Areas that are not decision options are listed in `analysis/period_comparison.json`: catalog/content 2.6% (T51) to 3.0% (T52), +0.4 pp (T53); general/unspecified 3.5% (T54) to 24.7% (T55), +21.2 pp (T56).

| Decision area | Share of complaints | 95% interval (sampling only) |
|---|---:|---:|
| usability | 24.4% (T19) | 23.2% (T20) to 25.7% (T21) |
| billing/support | 20.2% (T22) | 19.1% (T23) to 21.4% (T24) |
| playback/performance | 16.2% (T25) | 15.2% (T26) to 17.3% (T27) |
| access/onboarding | 3.1% (T28) | 2.6% (T29) to 3.6% (T30) |

Volume spikes (code): each line lists at most three issues, from any area (the catch-all `other.general` included), whose share of reviews (the issue's complaint and cancellation reviews / all reviews in the month) rose versus the other full months; zero and negative changes are left out.

- Volume spike 2023-07 (T31): 1246 (T32) reviews (median full month 438 (T33)); largest increases in share of reviews vs other months: `other.general` +36.6 pp (T34), `access.login` +0.1 pp (T35).
- Volume spike 2023-10 (T36): 1381 (T37) reviews (median full month 438 (T38)); largest increases in share of reviews vs other months: `billing.premium_only` +26.3 pp (T39), `other.general` +12.9 pp (T40), `catalog.lyrics` +1.6 pp (T41).
- Verifier robustness on 845 (T42) sampled reviews (severity_sum (the baseline priority) over complaint and cancellation reviews, row-weighted): decision areas in order under enricher labels **usability 333 (T43), billing/support 274 (T44), playback/performance 254 (T45), access/onboarding 53 (T46)**; under independent verifier labels **usability 374 (T47), billing/support 300 (T48), playback/performance 286 (T49), access/onboarding 52 (T50)** (top area same).

## Representative evidence (exact quotes from the reviews)

"(cited)" marks a review the memo cites in support of the recommendation.

- `other.general` - "hate this app👎" - review `1004158d-b165-4ff0-854b-bba5a1e78f08`
- `other.general` - "HAte this application 👎" - review `c5f7a43b-3b6d-4b3e-a029-db8eb6740978`
- `billing.premium_only` - "Good apps but me no limited skips" - review `a51a0214-e4b5-47cc-a2c4-202eca063367`
- `billing.premium_only` - "Unless you buy premium you don't even have the right to seek forward or backward when playing your favourite song." - review `fcb2aecc-9aa5-4628-85e3-2fb5356016aa`
- `usability.ads` - "Tooo many adds" - review `59d1e2cd-526e-4dea-86b5-964667c7c45e` (cited)
- `usability.ads` - "Great experience though ads are too frequent" - review `864337a6-c23e-49f1-b47a-5010ba84239a` (cited)
- `playback.stops` - "Seek bar not working 😕" - review `4981c5ad-6889-4388-a138-d057e638fcca`
- `playback.stops` - "AÇTIĞIM ŞARKI BİTİNCE GERİ GELMİYOR" - review `7e2b8eb8-d63d-40ca-ae5e-7dbe6a701a14`
- `usability.library` - "premium update is worse...I have also use other apps but such a drastic change with my playlist can't except...really disappointed...not much with this app .soon uninstalling.." - review `ba161974-a025-4a71-85b7-8c4b6a838a03` (cited)
- `usability.library` - "Now it's worse than YouTube Music.Whoever decided to remove the repeat and back button should be fired and you just lost a customer" - review `2cde3a67-37bf-45e5-bace-a691d9386bde` (cited)

## Scope figures

| Figure | Value | Token | Source |
|---|---:|---|---|
| Reviews in scope (unique IDs ingested) | 10000 | S01 | ingestion_report.json |
| Completed classifications | 10000 | S02 | grading/records.jsonl |
| Quarantined: empty text | 0 | S03 | quarantine.jsonl |
| Quarantined: other reasons | 0 | S04 | quarantine.jsonl |
| Unfinished | 0 | S05 | run_summary.json |
| Completed records flagged needs_review | 957 | S06 | enriched.jsonl |
| Complaint and cancellation records ranked | 4612 | S07 | membership.csv |
| Verification sample compared | 845 | S08 | verification/report.json |
| Verifier topic agreement (rate) | 0.8379 | S09 | verification/report.json |
| Verifier intent agreement (rate) | 0.9172 | S10 | verification/report.json |
| Verifier exact severity agreement (rate) | 0.7917 | S11 | verification/report.json |

## Limitations

- The two baseline severity sums for billing/support 2734 (A05) and usability 2716 (A08) are close enough on the full dataset that small labeling or scope changes could shift which area leads; the verifier sample and premium-only sensitivity check are used here to break the tie, but both are computed on specific subsets, not the full population.
- The period comparison and spike-month figures track area-level or issue-level shares separately; there is no combined trend figure showing usability's own issues (ads, library, navigation) moving together over time.
- Severity and complaint counts are summed across distinct usability issues (ads, library, navigation, other) that may respond differently to the same intervention, so a single action is unlikely to move all of usability's issues equally.
- The spike-month analysis covers only two specific months (2023-07 (T31) and 2023-10 (T36)) and may not represent typical month-to-month variation in usability complaints.
- Unallocated complaints (computed by code from `area_rollup.json`): 29.4% (A19) of complaint and cancellation records (1355 (A01)) are general/unspecified: generic criticism (for example "worst update") that names no specific area, so they are not allocated to any of the four decision areas. If many of them refer to one area's problem, for example the same free-tier change, that area's total is understated; the labels cannot show which area that would be.
- Premium-only boundary, upper-bound sensitivity (computed by code; `analysis/premium_only_sensitivity.json`): 112 (T57) of the 816 (C05) `billing.premium_only` complaint and cancellation records contain no Premium or payment word (premium, subscri-, pay/paid/paying, free, buy, money, trial, $; case-insensitive), with a severity sum of 332 (T58). If none of them belonged to billing/support, its severity sum would fall from 2734 (A05) to 2402 (T59), below usability 2716 (A08) and playback/performance 2478 (A11). This is an upper bound, not a relabelling: many of these reviews plainly describe free-tier limits without naming Premium (skip limits, forced shuffle), and they were not moved to any other area.
- Counts describe the labeled reviews in a 10000-review development checkpoint (analysis_10000.csv), not the full corpus: self-selected public app reviews, not a customer population. They carry no revenue, plan tier or confirmed cancellations, so revenue at risk cannot be computed.
- Cancellation language is expressed intent, not observed churn; nothing here estimates a causal effect on retention.
- Star ratings and helpful votes were not used to classify; severity is judged from the text under the shared rubric.
- 957 completed records are flagged needs_review, 0 are quarantined and 0 are unfinished.

## Traceability

- `claims.csv`: every issue-level number above (claim_id, issue_id, metric, value); the C## IDs in the prose and the ranking table.
- `memo_tokens.csv` (also `memo.json` -> `token_index`): every token ID used above (C##, A##, S##, T##) with its value, what it measures and the saved file it comes from (`area_rollup.json`, the scope sources, `analysis/*.json`).
- `ranking.csv` / `membership.csv`: rerun with `python -m insight rank --run-dir <run> --check` (no model calls).
- `issues.json`: issue names and the evidence each name was based on.

# Decision memo: where to focus next quarter

Scope: a 500-review development checkpoint (checkpoint_500.csv), not the full corpus  
Run: `run-20261014T213849.919Z-1bf0` | input `Final Assignment - Spotify Reviews Dataset/checkpoint_500.csv` (sha256 `a94e31663ee7b7ea...`) | memo source: model

Numbers are written as value (token ID): C## IDs are the issue-level claims in `claims.csv`; every ID (C##, A## area roll-up, S## scope figure, T## trend/robustness) is listed with its value, what it measures and its source file in `memo_tokens.csv`.

## Recommendation

**playback/performance.** We recommend directing next quarter's product-improvement effort to playback/performance, which carries the highest baseline priority among the four decision areas, driven by playback stopping or skipping (severity sum 46 (C14) across 14 (C13) complaint and cancellation reviews), app crashes after update (severity sum 31 (C26) across 8 (C25) reviews), false offline or no-internet errors (severity sum 27 (C30) across 7 (C29) reviews), and downloads disappearing or failing (severity sum 25 (C34) across 7 (C33) reviews). This is core playback reliability and stability engineering work, not a packaging or entitlement question.

## Next-quarter actions

1. Investigate and reduce playback stopping or skipping mid-track (issue playback.stops, severity sum 46 (C14) across 14 (C13) reviews), targeting a reduction in this issue's complaint count and severity sum next quarter.
2. Triage and fix post-update app crashes and blank-screen loads (issue playback.crash, severity sum 31 (C26) across 8 (C25) reviews), aiming to lower this issue's complaint count.
3. Diagnose the false offline/no-internet error (issue playback.connection, severity sum 27 (C30) across 7 (C29) reviews) to reduce its share of complaints.
4. As a hedge on the strongest alternative area, review the premium-only restrictions issue (billing.premium_only, severity sum 135 (C02) across 45 (C01) reviews) as a free-tier packaging and entitlement policy question, watching whether its share of complaints or trend share changes.

## Why

- Baseline priority (severity sum over complaint and cancellation reviews) is highest for playback/performance at 159 (A02), ahead of billing/support at 158 (A05), usability at 140 (A08), and access/onboarding at 36 (A17).
- Playback/performance also shows the largest increase among the four decision areas in share of reviews between 2022 Jun-Oct (T01) and 2023 Jun-Oct (T02), rising from 4.5% (T13) to 9.3% (T14), a change of +4.8 pp (T15), larger than billing/support's +2.8 pp (T12), usability's +0.3 pp (T18), or access/onboarding's +0.6 pp (T09).
- On share of complaints, usability's 24.0% (T19) is higher than playback/performance's 18.7% (T25), and billing/support's 21.1% (T22) also sits above playback/performance's share point estimate, though all three intervals overlap each other (playback/performance's interval does not overlap with access/onboarding's), so playback/performance leads on severity sum but not on complaint count or share of complaints.
- A caveat for robustness: in the verifier's sampled relabeling (48 (T43) reviews), usability is the top area under both enricher and verifier labels on the same row-weighted severity-sum metric, while playback/performance ranks second under enricher labels and third under verifier labels; this is a labelling disagreement with the full-sample baseline ordering and makes the recommendation provisional.
- A spike month 2023-10 (T37) shows the largest increase for billing's premium-only issue (+20.6 pp (T40)), not for a playback/performance issue, so the playback/performance recommendation does not rest on spike-month evidence.

## What would change this call

- A larger verified sample confirming the verifier's severity-sum ordering (usability above playback/performance, as seen in 32 (T47) versus 11 (T49)) would weaken the case for playback/performance over usability.
- A human audit of the 7 (T57) premium-only records without a Premium or payment word finding that most genuinely describe free-tier restrictions would support billing/support's severity sum staying near 158 (A05) rather than falling toward 137 (T59), narrowing the gap with playback/performance.
- If playback/performance's share of reviews reverses back toward 4.5% (T13) in the same months of the following year rather than holding near 9.3% (T14), the growth basis for this recommendation would no longer apply.

## Alternatives considered

- **billing/support**: Billing/support's baseline severity sum 158 (A05) is close to but below playback/performance's 159 (A02), and its complaint share 21.1% (T22) is higher than playback/performance's 18.7% (T25) (intervals overlap). Its leading issue, premium-only restrictions (severity sum 135 (C02) across 45 (C01) reviews), is a free-tier packaging and entitlement policy matter, not a playback defect, and a spike-month increase of +20.6 pp (T40) in 2023-10 (T37) inflates its recent visibility without changing the full-window severity-sum ordering.
- **usability**: Usability has the highest complaint count and share of complaints (24.0% (T19), overlapping with billing/support and playback/performance), and leads the verifier's sampled severity-sum ordering under both labelers, but its full-sample baseline severity sum 140 (A08) is below playback/performance's 159 (A02), and its share-of-reviews growth between 2022 Jun-Oct (T01) and 2023 Jun-Oct (T02) (+0.3 pp (T18)) is smaller than playback/performance's (+4.8 pp (T15)).
- **access/onboarding**: Access/onboarding has by far the lowest baseline severity sum 36 (A17) and the lowest share of complaints 3.7% (T28) (its interval does not overlap with any other area), and its share-of-reviews change between 2022 Jun-Oct (T01) and 2023 Jun-Oct (T02) (+0.6 pp (T09)) is the smallest among the four decision areas.

## Supporting numbers (baseline ranking, computed by code)

Priority = severity_sum = complaint_count x mean_severity over complaint and cancellation reviews. Each cell shows the value and its claim ID in `claims.csv`.

| Rank | Issue | Area | Complaints | Severity sum | Mean severity | Priority |
|---:|---|---|---:|---:|---:|---:|
| 1 | Premium-only restrictions (`billing.premium_only`) | billing/support | 45 (C01) | 135 (C02) | 3.000000 (C03) | 135 (C04) |
| 2 | General or unrelated (`other.general`) | general/unspecified | 56 (C05) | 111 (C06) | 1.982143 (C07) | 111 (C08) |
| 3 | Excessive Ad Interruptions (`usability.ads`) | usability | 32 (C09) | 68 (C10) | 2.125000 (C11) | 68 (C12) |
| 4 | Playback stops or skips (`playback.stops`) | playback/performance | 14 (C13) | 46 (C14) | 3.285714 (C15) | 46 (C16) |
| 5 | Confusing redesigned home screen layout (`usability.navigation`) | usability | 14 (C17) | 37 (C18) | 2.642857 (C19) | 37 (C20) |
| 6 | Login failures (`access.login`) | access/onboarding | 8 (C21) | 31 (C22) | 3.875000 (C23) | 31 (C24) |
| 7 | App crashes and fails to load after update (`playback.crash`) | playback/performance | 8 (C25) | 31 (C26) | 3.875000 (C27) | 31 (C28) |
| 8 | False offline/no-internet error (`playback.connection`) | playback/performance | 7 (C29) | 27 (C30) | 3.857143 (C31) | 27 (C32) |
| 9 | Downloads disappear or fail to work (`downloads.offline`) | playback/performance | 7 (C33) | 25 (C34) | 3.571429 (C35) | 25 (C36) |
| 10 | Shuffle and playlist controls malfunctioning (`usability.library`) | usability | 8 (C37) | 24 (C38) | 3.000000 (C39) | 24 (C40) |

## Area roll-up (derived from the issue table; not a contract metric)

| Area | Complaints | Severity sum | Share of complaints |
|---|---:|---:|---:|
| playback/performance | 46 (A01) | 159 (A02) | 0.186992 (A03) |
| billing/support | 52 (A04) | 158 (A05) | 0.211382 (A06) |
| usability | 59 (A07) | 140 (A08) | 0.239837 (A09) |
| general/unspecified (not one of the four options) | 56 (A10) | 111 (A11) | 0.227642 (A12) |
| catalog/content (not one of the four options) | 24 (A13) | 70 (A14) | 0.097561 (A15) |
| access/onboarding | 9 (A16) | 36 (A17) | 0.036585 (A18) |

## Trends and robustness (descriptive, computed by code)

Same calendar months one year apart (full months only). Share = the area's complaint and cancellation reviews / all classified reviews in the period.

| Area | 2022 Jun-Oct (T01) | 2023 Jun-Oct (T02) | Change |
|---|---:|---:|---:|
| access/onboarding | 1.8% (T07) | 2.4% (T08) | +0.6 pp (T09) |
| billing/support | 9.9% (T10) | 12.7% (T11) | +2.8 pp (T12) |
| playback/performance | 4.5% (T13) | 9.3% (T14) | +4.8 pp (T15) |
| usability | 9.9% (T16) | 10.2% (T17) | +0.3 pp (T18) |
| Denominator (classified reviews) | 111 (T03) | 205 (T05) | |

Note (code): this table, and any comparison of growth in this memo, covers the four decision areas only. Areas that are not decision options are listed in `analysis/period_comparison.json`: catalog/content 2.7% (T51) to 6.8% (T52), +4.1 pp (T53); general/unspecified 2.7% (T54) to 19.5% (T55), +16.8 pp (T56).

| Decision area | Share of complaints | 95% interval (sampling only) |
|---|---:|---:|
| usability | 24.0% (T19) | 19.1% (T20) to 29.7% (T21) |
| billing/support | 21.1% (T22) | 16.5% (T23) to 26.7% (T24) |
| playback/performance | 18.7% (T25) | 14.3% (T26) to 24.0% (T27) |
| access/onboarding | 3.7% (T28) | 1.9% (T29) to 6.8% (T30) |

Volume spikes (code): each line lists at most three issues, from any area (the catch-all `other.general` included), whose share of reviews (the issue's complaint and cancellation reviews / all reviews in the month) rose versus the other full months; zero and negative changes are left out.

- Volume spike 2023-07 (T31): 56 (T32) reviews (median full month 21 (T33)); largest increases in share of reviews vs other months: `other.general` +42.5 pp (T34), `downloads.offline` +2.6 pp (T35), `playback.performance` +0.8 pp (T36).
- Volume spike 2023-10 (T37): 79 (T38) reviews (median full month 21 (T39)); largest increases in share of reviews vs other months: `billing.premium_only` +20.6 pp (T40), `catalog.lyrics` +5.8 pp (T41), `usability.other` +3.3 pp (T42).
- Verifier robustness on 48 (T43) sampled reviews (severity_sum (the baseline priority) over complaint and cancellation reviews, row-weighted): decision areas in order under enricher labels **usability 26 (T44), playback/performance 18 (T45), billing/support 11 (T46)**; under independent verifier labels **usability 32 (T47), billing/support 14 (T48), playback/performance 11 (T49), access/onboarding 4 (T50)** (top area same).

## Representative evidence (exact quotes from the reviews)

"(cited)" marks a review the memo cites in support of the recommendation.

- `billing.premium_only` - "I only wish it wasn't limited on the skips." - review `ac581cea-24f2-4251-a062-53cdd77cfed7`
- `billing.premium_only` - "Anyone else facing problem turning off shuffle?You need to be a premium user to turn of Shuffle playlist!This is the most idiotic thing I've ever seen!Well,Sir/Ma'am,whoever takes such innovative steps to add more" - review `6b55ac9c-8dd2-4170-8782-bd35985ec0d9`
- `other.general` - "Noob app" - review `2d5cdd20-3094-40a5-bc6e-653302b59b56`
- `other.general` - "Useless app" - review `36f1617b-e4f7-44fb-a7a9-a8236e4c3531`
- `usability.ads` - "Too much adds🙄🥲" - review `ee17dcd6-07c0-4441-8e64-e7ea57877c78`
- `usability.ads` - "Very worst, commercial ads very worst, i recommended to every one, don't use this app!" - review `d4d68992-96bf-4fb1-a370-cb47234022d9`
- `playback.stops` - "when I want to play my playlist, it does NOT play?!" - review `06d4c78d-73b4-4b54-9ef3-3d5a0d18cb96` (cited)
- `playback.stops` - "I have a Samsung and after a week of using this app it like wouldn't let me listen to music" - review `d3b74f36-aa48-42af-ae4a-d4a8b0499a60` (cited)
- `usability.navigation` - "Will try to make your life difficult finding your songs, esp." - review `08d3a5a9-1ec1-4b10-a5c8-393da33843e1`
- `usability.navigation` - "Spotify is great, but the new homescreen update is horrible." - review `94c9f2f9-36fa-4c11-936e-660514fe7a35`

## Scope figures

| Figure | Value | Token | Source |
|---|---:|---|---|
| Reviews in scope (unique IDs ingested) | 500 | S01 | ingestion_report.json |
| Completed classifications | 500 | S02 | grading/records.jsonl |
| Quarantined: empty text | 0 | S03 | quarantine.jsonl |
| Quarantined: other reasons | 0 | S04 | quarantine.jsonl |
| Unfinished | 0 | S05 | run_summary.json |
| Completed records flagged needs_review | 31 | S06 | enriched.jsonl |
| Complaint and cancellation records ranked | 246 | S07 | membership.csv |
| Verification sample compared | 48 | S08 | verification/report.json |
| Verifier topic agreement (rate) | 0.8542 | S09 | verification/report.json |
| Verifier intent agreement (rate) | 0.9583 | S10 | verification/report.json |
| Verifier exact severity agreement (rate) | 0.7292 | S11 | verification/report.json |

## Limitations

- The verifier's labelling disagreement (top area usability rather than playback/performance on the same severity-sum metric) is based on a small sampled subset (48 (T43) reviews) and cannot by itself confirm which ordering holds in the full set of 246 (S07) ranked complaint and cancellation reviews.
- Complaint-share sampling intervals for usability, billing/support, and playback/performance all overlap each other, so the full-sample complaint-share ordering among these three areas cannot be treated as firmly distinguished.
- The period comparison between 2022 Jun-Oct (T01) and 2023 Jun-Oct (T02) reflects self-selected reviewers in each window and differing total review volumes (111 (T03) versus 205 (T05)), not a measured customer population change.
- Severity labels reflect the enrichment process's judgment of review text, not independently verified support-ticket or crash-telemetry severity.
- Unallocated complaints (computed by code from `area_rollup.json`): 22.8% (A19) of complaint and cancellation records (56 (A10)) are general/unspecified: generic criticism (for example "worst update") that names no specific area, so they are not allocated to any of the four decision areas. If many of them refer to one area's problem, for example the same free-tier change, that area's total is understated; the labels cannot show which area that would be.
- Premium-only boundary, upper-bound sensitivity (computed by code; `analysis/premium_only_sensitivity.json`): 7 (T57) of the 45 (C01) `billing.premium_only` complaint and cancellation records contain no Premium or payment word (premium, subscri-, pay/paid/paying, free, buy, money, trial, $; case-insensitive), with a severity sum of 21 (T58). If none of them belonged to billing/support, its severity sum would fall from 158 (A05) to 137 (T59), below playback/performance 159 (A02) and usability 140 (A08). This is an upper bound, not a relabelling: many of these reviews plainly describe free-tier limits without naming Premium (skip limits, forced shuffle), and they were not moved to any other area.
- Counts describe the labeled reviews in a 500-review development checkpoint (checkpoint_500.csv), not the full corpus: self-selected public app reviews, not a customer population. They carry no revenue, plan tier or confirmed cancellations, so revenue at risk cannot be computed.
- Cancellation language is expressed intent, not observed churn; nothing here estimates a causal effect on retention.
- Star ratings and helpful votes were not used to classify; severity is judged from the text under the shared rubric.
- 31 completed records are flagged needs_review, 0 are quarantined and 0 are unfinished.

## Traceability

- `claims.csv`: every issue-level number above (claim_id, issue_id, metric, value); the C## IDs in the prose and the ranking table.
- `memo_tokens.csv` (also `memo.json` -> `token_index`): every token ID used above (C##, A##, S##, T##) with its value, what it measures and the saved file it comes from (`area_rollup.json`, the scope sources, `analysis/*.json`).
- `ranking.csv` / `membership.csv`: rerun with `python -m insight rank --run-dir <run> --check` (no model calls).
- `issues.json`: issue names and the evidence each name was based on.

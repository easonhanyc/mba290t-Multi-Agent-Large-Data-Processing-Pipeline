# Decision memo: where to focus next quarter

Scope: a 100-review development checkpoint (cost_100.csv), not the full corpus  
Run: `run-20261014T213833.675Z-aede` | input `runs/pilot100-20261014T213535Z/input/cost_100.csv` (sha256 `c884ac3b9be50669...`) | memo source: model, reused from the stage cache (generated in `run-20261014T213535.337Z-c6e0`)

Numbers are written as value (token ID): C## IDs are the issue-level claims in `claims.csv`; every ID (C##, A## area roll-up, S## scope figure, T## trend/robustness) is listed with its value, what it measures and its source file in `memo_tokens.csv`.

## Recommendation

**usability.** Usability should get the next quarter's product-improvement effort, driven by its two largest issues: ad interruptions (severity sum 16 (C10) across 8 (C09) complaint and cancellation reviews) and shuffle/repeat controls that misbehave (severity sum 9 (C14) across 3 (C13) complaint and cancellation reviews). This is core in-app listening-experience work on ad frequency and queue/playback-control behavior, not a payment or access fix.

## Next-quarter actions

1. Test reduced ad frequency or shorter ad breaks against the ad interruptions issue (severity sum 16 (C10) across 8 (C09) reviews); success should show a drop in that issue's complaint count and severity sum next period.
2. Audit and fix shuffle randomization and repeat-control logic tied to the shuffle/repeat misbehavior issue (severity sum 9 (C14) across 3 (C13) reviews); success should show a drop in that issue's severity sum and share of complaints.
3. Run a smaller-scope investigation into the premium-only restrictions issue (severity sum 27 (C02) across 9 (C01) reviews) as a packaging and communication question (how skip, shuffle, and repeat limits are explained to free-tier users), given billing/support's larger increase among the four decision areas (+3.6 pp (T12)); success should show its complaint count and severity sum easing in the following comparable months.

## Why

- Usability carries the highest baseline priority among the four decision areas, with severity sum 30 (A02) across 13 (A01) complaint and cancellation reviews, ahead of billing/support's severity sum 27 (A05) across 9 (A04) reviews, playback/performance's severity sum 26 (A08) across 8 (A07) reviews, and access/onboarding's severity sum 8 (A17) across 2 (A16) reviews.
- Within usability, ad interruptions (8 (C09) reviews, severity sum 16 (C10)) and shuffle/repeat misbehavior (3 (C13) reviews, severity sum 9 (C14)) are the two issues driving that total.
- Usability's share of all classified reviews rose from 8.0% (T16) in 2022 Jun-Oct (T01) to 9.3% (T17) in 2023 Jun-Oct (T02), a change of +1.3 pp (T18), so the issue is not shrinking, even though billing/support shows the largest increase among the four decision areas (+3.6 pp (T12)) and playback/performance actually fell (-3.3 pp (T15)).
- The independent verifier, re-labeling a sample of 10 (T42) reviews, puts usability first on the same severity-sum metric under both the enricher's labels (severity sum 7 (T43) versus playback/performance's 3 (T44)) and the verifier's own labels (severity sum 7 (T45) versus playback/performance's 4 (T46) and billing/support's 2 (T47)), and usability also leads on complaint count in both labelings, so the call does not depend on a single labeler.
- Usability's share of complaints (25.5% (T19)) sits inside overlapping sampling intervals with billing/support (17.6% (T22)) and playback/performance (15.7% (T25)), so the lead on share of complaints alone is not statistically sharp; the recommendation rests on the severity-sum baseline and the verifier agreement, not on a distinct complaint share.

## What would change this call

- A verifier severity-sum ordering that holds on a larger verified sample than 10 (T42) reviews, still showing usability's severity sum (7 (T43)/7 (T45)) below another decision area's.
- Usability's share of all classified reviews reversing from the +1.3 pp (T18) increase seen between 2022 Jun-Oct (T01) and 2023 Jun-Oct (T02) back toward the 2022 Jun-Oct (T01) level in the same months of the following year.
- A human audit of the 1 (T54) premium-only records lacking a Premium or payment word finding that most genuinely belong in billing/support rather than free-tier packaging, which would raise billing/support's severity sum (24 (T56)) closer to or above usability's 30 (A02).

## Alternatives considered

- **billing/support**: Billing/support's severity sum 27 (A05) across 9 (A04) reviews is second to usability's 30 (A02), and its single large issue, premium-only restrictions (severity sum 27 (C02) across 9 (C01) reviews), is a free-tier packaging and entitlement policy question, not a billing or payment defect. It does show the largest increase among the four decision areas (+3.6 pp (T12)), which supports watching it, but that growth figure does not overturn usability's higher severity-sum baseline, and the verifier's own severity ordering (7 (T45), 4 (T46), 2 (T47)) also keeps it below both usability and playback/performance.
- **playback/performance**: Playback/performance's severity sum 26 (A08) across 8 (A07) reviews trails usability's 30 (A02), and its share of all classified reviews fell from 8.0% (T13) to 4.7% (T14) (a change of -3.3 pp (T15)) between 2022 Jun-Oct (T01) and 2023 Jun-Oct (T02), the only decrease among the four decision areas, so it is both lower priority and moving in the opposite direction from usability.
- **access/onboarding**: Access/onboarding has the lowest severity sum, 8 (A17) across only 2 (A16) reviews, and the smallest share of complaints at 3.9% (T28). Its share of all classified reviews did rise by +2.3 pp (T09), but off a very small base, and it remains well below usability on the baseline severity-sum metric.

## Supporting numbers (baseline ranking, computed by code)

Priority = severity_sum = complaint_count x mean_severity over complaint and cancellation reviews. Each cell shows the value and its claim ID in `claims.csv`.

| Rank | Issue | Area | Complaints | Severity sum | Mean severity | Priority |
|---:|---|---|---:|---:|---:|---:|
| 1 | Premium-only restrictions (`billing.premium_only`) | billing/support | 9 (C01) | 27 (C02) | 3.000000 (C03) | 27 (C04) |
| 2 | General or unrelated (`other.general`) | general/unspecified | 13 (C05) | 25 (C06) | 1.923077 (C07) | 25 (C08) |
| 3 | Ad interruptions (`usability.ads`) | usability | 8 (C09) | 16 (C10) | 2.000000 (C11) | 16 (C12) |
| 4 | Shuffle plays songs randomly and repeat controls broken (`usability.library`) | usability | 3 (C13) | 9 (C14) | 3.000000 (C15) | 9 (C16) |
| 5 | Login failures (`access.login`) | access/onboarding | 2 (C17) | 8 (C18) | 4.000000 (C19) | 8 (C20) |
| 6 | App crashes and fails to load (`playback.crash`) | playback/performance | 2 (C21) | 8 (C22) | 4.000000 (C23) | 8 (C24) |
| 7 | Lyrics missing for some songs (`catalog.lyrics`) | catalog/content | 2 (C25) | 6 (C26) | 3.000000 (C27) | 6 (C28) |
| 8 | Offline mode failures and stuck downloads (`downloads.offline`) | playback/performance | 2 (C29) | 6 (C30) | 3.000000 (C31) | 6 (C32) |
| 9 | Missing songs from library (`catalog.missing`) | catalog/content | 2 (C33) | 5 (C34) | 2.500000 (C35) | 5 (C36) |
| 10 | Declining recommendation quality (`catalog.recommendations`) | catalog/content | 2 (C37) | 5 (C38) | 2.500000 (C39) | 5 (C40) |

## Area roll-up (derived from the issue table; not a contract metric)

| Area | Complaints | Severity sum | Share of complaints |
|---|---:|---:|---:|
| usability | 13 (A01) | 30 (A02) | 0.254902 (A03) |
| billing/support | 9 (A04) | 27 (A05) | 0.176471 (A06) |
| playback/performance | 8 (A07) | 26 (A08) | 0.156863 (A09) |
| general/unspecified (not one of the four options) | 13 (A10) | 25 (A11) | 0.254902 (A12) |
| catalog/content (not one of the four options) | 6 (A13) | 16 (A14) | 0.117647 (A15) |
| access/onboarding | 2 (A16) | 8 (A17) | 0.039216 (A18) |

## Trends and robustness (descriptive, computed by code)

Same calendar months one year apart (full months only). Share = the area's complaint and cancellation reviews / all classified reviews in the period.

| Area | 2022 Jun-Oct (T01) | 2023 Jun-Oct (T02) | Change |
|---|---:|---:|---:|
| access/onboarding | 0.0% (T07) | 2.3% (T08) | +2.3 pp (T09) |
| billing/support | 8.0% (T10) | 11.6% (T11) | +3.6 pp (T12) |
| playback/performance | 8.0% (T13) | 4.7% (T14) | -3.3 pp (T15) |
| usability | 8.0% (T16) | 9.3% (T17) | +1.3 pp (T18) |
| Denominator (classified reviews) | 25 (T03) | 43 (T05) | |

Note (code): this table, and any comparison of growth in this memo, covers the four decision areas only. Areas that are not decision options are listed in `analysis/period_comparison.json`: catalog/content 8.0% (T48) to 9.3% (T49), +1.3 pp (T50); general/unspecified 0.0% (T51) to 25.6% (T52), +25.6 pp (T53).

| Decision area | Share of complaints | 95% interval (sampling only) |
|---|---:|---:|
| usability | 25.5% (T19) | 15.5% (T20) to 38.9% (T21) |
| billing/support | 17.6% (T22) | 9.6% (T23) to 30.3% (T24) |
| playback/performance | 15.7% (T25) | 8.2% (T26) to 28.0% (T27) |
| access/onboarding | 3.9% (T28) | 1.1% (T29) to 13.2% (T30) |

Volume spikes (code): each line lists at most three issues, from any area (the catch-all `other.general` included), whose share of reviews (the issue's complaint and cancellation reviews / all reviews in the month) rose versus the other full months; zero and negative changes are left out.

- Volume spike 2023-07 (T31): 11 (T32) reviews (median full month 5 (T33)); largest increases in share of reviews vs other months: `other.general` +26.8 pp (T34), `downloads.offline` +7.9 pp (T35).
- Volume spike 2023-10 (T36): 19 (T37) reviews (median full month 5 (T38)); largest increases in share of reviews vs other months: `billing.premium_only` +21.1 pp (T39), `usability.library` +15.8 pp (T40), `catalog.lyrics` +10.5 pp (T41).
- Verifier robustness on 10 (T42) sampled reviews (severity_sum (the baseline priority) over complaint and cancellation reviews, row-weighted): decision areas in order under enricher labels **usability 7 (T43), playback/performance 3 (T44)**; under independent verifier labels **usability 7 (T45), playback/performance 4 (T46), billing/support 2 (T47)** (top area same).

## Representative evidence (exact quotes from the reviews)

"(cited)" marks a review the memo cites in support of the recommendation.

- `billing.premium_only` - "This was fine till the last update, now you can't even pick a certain song without Spotify premium, and now you can only skip 6 songs, like please just let the songs fit my mood!" - review `d146397f-4a94-4980-be00-ae9212eca3a7`
- `billing.premium_only` - "Na queue m lgte h gaane, na skip kr skte h, na random chla skte h, kya bkchodi h ye???" - review `89ea2c30-db8b-459d-8ab7-bbcb7f92c774`
- `other.general` - "Noob app" - review `2d5cdd20-3094-40a5-bc6e-653302b59b56`
- `other.general` - "Used to love the app but recent update is very disappointing bye Spotify" - review `b47c203f-366e-4409-922d-cd52aa8bbef6`
- `usability.ads` - "that always plays adds instead of songs ...if want to enjoy music free without adds don't download this app .." - review `cf6166ae-d71a-4839-9add-088645ad3b78` (cited)
- `usability.ads` - "Too many ads...." - review `e5e6c55f-3069-4b7c-9807-f8b5d5bf2726` (cited)
- `usability.library` - "I am using Spotify from past two years From last update they removed basic features of music player" - review `7084ced1-0428-4093-9328-442f74719b4f` (cited)
- `usability.library` - "Your new features are really bad thing that I found because it plays any song of the Playlist randomly it really really disappointing for and listeners who don't need disturbance in their song patterns." - review `5c9c17d3-9d6a-4fa1-a2a4-ae98eefbbd25` (cited)
- `access.login` - "It not letting me into my account and there are to many ads" - review `32fb340f-4f9f-4551-8dae-755221e58d6a`
- `access.login` - "Will not except my password" - review `de0a9cdf-8974-48bc-802f-331228df4619`

## Scope figures

| Figure | Value | Token | Source |
|---|---:|---|---|
| Reviews in scope (unique IDs ingested) | 100 | S01 | ingestion_report.json |
| Completed classifications | 100 | S02 | grading/records.jsonl |
| Quarantined: empty text | 0 | S03 | quarantine.jsonl |
| Quarantined: other reasons | 0 | S04 | quarantine.jsonl |
| Unfinished | 0 | S05 | run_summary.json |
| Completed records flagged needs_review | 4 | S06 | enriched.jsonl |
| Complaint and cancellation records ranked | 51 | S07 | membership.csv |
| Verification sample compared | 10 | S08 | verification/report.json |
| Verifier topic agreement (rate) | 0.8 | S09 | verification/report.json |
| Verifier intent agreement (rate) | 0.8 | S10 | verification/report.json |
| Verifier exact severity agreement (rate) | 0.6 | S11 | verification/report.json |

## Limitations

- The two usability issues cited are built from small review counts (8 (C09) and 3 (C13)), so the specific severity figures (16 (C10), 9 (C14)) could shift with a modestly different sample of self-selected reviews.
- Sampling intervals for usability, billing/support, and playback/performance overlap on share of complaints (25.5% (T19), 17.6% (T22), 15.7% (T25)), so the ranking among these three on that particular measure is not sharply distinguishable even though usability leads on severity sum.
- The verifier check covers only 10 (T42) reviews, a small fraction of the 51 (S07) complaint and cancellation reviews ranked, so its agreement with the enricher's top area is reassuring but not a large-sample confirmation.
- The issue definitions for ad interruptions and shuffle/repeat misbehavior describe reported symptoms, not their underlying causes, so the memo cannot say why these behaviors occur or which specific fix would resolve them.
- Unallocated complaints (computed by code from `area_rollup.json`): 25.5% (A19) of complaint and cancellation records (13 (A10)) are general/unspecified: generic criticism (for example "worst update") that names no specific area, so they are not allocated to any of the four decision areas. If many of them refer to one area's problem, for example the same free-tier change, that area's total is understated; the labels cannot show which area that would be.
- Premium-only boundary, upper-bound sensitivity (computed by code; `analysis/premium_only_sensitivity.json`): 1 (T54) of the 9 (C01) `billing.premium_only` complaint and cancellation records contain no Premium or payment word (premium, subscri-, pay/paid/paying, free, buy, money, trial, $; case-insensitive), with a severity sum of 3 (T55). If none of them belonged to billing/support, its severity sum would fall from 27 (A05) to 24 (T56), below usability 30 (A02) and playback/performance 26 (A08). This is an upper bound, not a relabelling: many of these reviews plainly describe free-tier limits without naming Premium (skip limits, forced shuffle), and they were not moved to any other area.
- Counts describe the labeled reviews in a 100-review development checkpoint (cost_100.csv), not the full corpus: self-selected public app reviews, not a customer population. They carry no revenue, plan tier or confirmed cancellations, so revenue at risk cannot be computed.
- Cancellation language is expressed intent, not observed churn; nothing here estimates a causal effect on retention.
- Star ratings and helpful votes were not used to classify; severity is judged from the text under the shared rubric.
- 4 completed records are flagged needs_review, 0 are quarantined and 0 are unfinished.

## Traceability

- `claims.csv`: every issue-level number above (claim_id, issue_id, metric, value); the C## IDs in the prose and the ranking table.
- `memo_tokens.csv` (also `memo.json` -> `token_index`): every token ID used above (C##, A##, S##, T##) with its value, what it measures and the saved file it comes from (`area_rollup.json`, the scope sources, `analysis/*.json`).
- `ranking.csv` / `membership.csv`: rerun with `python -m insight rank --run-dir <run> --check` (no model calls).
- `issues.json`: issue names and the evidence each name was based on.

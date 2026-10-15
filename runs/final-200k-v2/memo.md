# Decision memo: where to focus next quarter

Scope: the declared analysis scope of 200,013 reviews (analysis_200k.csv, a deterministic uniform sample of the 660,622-review corpus plus every empty-text row)  
Run: `run-20261015T033337.582Z-bf5d` | input `data/analysis_200k.csv` (sha256 `3c023c9dd47a5775...`) | memo source: model

Numbers are written as value (token ID): C## IDs are the issue-level claims in `claims.csv`; every ID (C##, A## area roll-up, S## scope figure, T## trend/robustness) is listed with its value, what it measures and its source file in `memo_tokens.csv`.

## Recommendation

**usability.** Usability carries the highest baseline severity sum among the four decision areas (52983 (A05)), led by ad interruptions (severity sum 23235 (C10) across 11233 (C09) complaint and cancellation reviews), shuffle/repeat/queue malfunctions (severity sum 16888 (C18) across 5685 (C17) reviews), and navigation/layout confusion (severity sum 7795 (C30) across 3168 (C29) reviews). This is core in-app experience work - ad pacing, playback control reliability, and interface navigation - not a payment or entitlement policy question.

## Next-quarter actions

1. Reduce ad interruption frequency or length for free-tier listening tied to the ad interruptions issue (11233 (C09), 23235 (C10)); test shorter or less frequent ad breaks and watch for a decline in severity sum 23235 (C10) and complaint count 11233 (C09).
2. Audit and fix shuffle/repeat/queue logic tied to the shuffle, repeat and queue malfunctions issue (5685 (C17), 16888 (C18)); test that selected shuffle/repeat states persist correctly and watch for a decline in severity sum 16888 (C18).
3. Simplify or test reverting recent navigation/layout changes tied to the navigation and layout issue (3168 (C29), 7795 (C30)); test easier access to moved features and watch for a decline in severity sum 7795 (C30) and complaint count 3168 (C29).
4. Hedge: review messaging and rollout clarity around the premium-only restrictions issue (15763 (C05), 46246 (C06)) in billing/support, since it shows the fastest growth among the four decision areas (+10.2 pp (T12)); test clearer in-app explanation of free-tier limits and watch for a decline in share of complaints 19.7% (T22).

## Why

- Usability's severity sum 52983 (A05) is the highest among the four decision areas, narrowly ahead of billing/support's severity sum 52551 (A08), and usability also leads on complaint share 24.3% (T19) with an interval that does not overlap billing/support 19.7% (T22), playback/performance 16.1% (T25), or access/onboarding 3.2% (T28).
- Within usability, ad interruptions (severity sum 23235 (C10) across 11233 (C09) reviews) and shuffle/repeat/queue malfunctions (severity sum 16888 (C18) across 5685 (C17) reviews) are the largest contributors, with navigation/layout (severity sum 7795 (C30) across 3168 (C29) reviews) adding further weight.
- Between 2022 Jun-Oct (T01) and 2023 Jun-Oct (T02), usability's share of reviews fell from 11.1% (T16) to 10.0% (T17) (a change of -1.1 pp (T18)), while billing/support's share grew from 3.8% (T10) to 13.9% (T11) (a change of +10.2 pp (T12)) - this is a share-of-reviews trend, not a severity-sum change, so it does not by itself override usability's current severity-sum lead.
- Robustness is mixed: the enricher-label sample shows billing/support leading on sample severity sum (705 (T42)) ahead of usability (650 (T43)) and playback/performance (617 (T44)), while the verifier-label sample instead shows playback/performance leading (758 (T46)) ahead of usability (747 (T47)) and billing/support (660 (T48)); neither sample reproduces the full-dataset usability lead exactly, which is a caveat on the sample level even though the full-dataset ranking favors usability.
- Both labelers agree that usability leads on complaint count, which is a secondary measure reinforcing the volume of usability-related issues even though the ranking by severity sum differs between samples.

## What would change this call

- The verifier's severity-sum ordering holding on a larger verified sample and showing a different area consistently above usability (for example extending 758 (T46), 747 (T47), 660 (T48) on a bigger sample).
- Usability's trend share (10.0% (T17)) reversing to grow faster than billing/support's in the same months of the following year, rather than continuing the decline seen from 11.1% (T16) to 10.0% (T17).
- A human audit of the premium-only records without a payment word (2456 (T56), 7283 (T57)) finding that most are not about free-tier restrictions, which would weaken billing/support as an alternative but not itself raise usability's position.

## Alternatives considered

- **billing/support**: Billing/support has the second-highest severity sum (52551 (A08)), driven by the premium-only restrictions issue (severity sum 46246 (C06) across 15763 (C05) reviews), and it shows the largest growth among the four decision areas between 2022 Jun-Oct (T01) and 2023 Jun-Oct (T02) (from 3.8% (T10) to 13.9% (T11), a change of +10.2 pp (T12)), plus it leads under enricher-label sample severity sum (705 (T42)). But its full-dataset severity sum remains below usability's (52983 (A05)), and its top issue is a free-tier packaging and entitlement policy matter, not a usability or payment defect.
- **playback/performance**: Playback/performance's severity sum (48060 (A11)) is below usability's (52983 (A05)) in the full dataset, though it leads under the verifier-label sample severity sum (758 (T46)); this sample-level disagreement is a caveat but does not establish playback/performance as the full-dataset leader.
- **access/onboarding**: Access/onboarding has the lowest severity sum (11300 (A17)) and lowest complaint share (3.2% (T28)) among the four decision areas, with its interval not overlapping the others.

## Supporting numbers (baseline ranking, computed by code)

Priority = severity_sum = complaint_count x mean_severity over complaint and cancellation reviews. Each cell shows the value and its claim ID in `claims.csv`.

| Rank | Issue | Area | Complaints | Severity sum | Mean severity | Priority |
|---:|---|---|---:|---:|---:|---:|
| 1 | General or unrelated (`other.general`) | general/unspecified | 27137 (C01) | 54364 (C02) | 2.003317 (C03) | 54364 (C04) |
| 2 | Premium-only restrictions (`billing.premium_only`) | billing/support | 15763 (C05) | 46246 (C06) | 2.933832 (C07) | 46246 (C08) |
| 3 | Ad interruptions (`usability.ads`) | usability | 11233 (C09) | 23235 (C10) | 2.068459 (C11) | 23235 (C12) |
| 4 | Playback stops or skips (`playback.stops`) | playback/performance | 6110 (C13) | 19564 (C14) | 3.201964 (C15) | 19564 (C16) |
| 5 | Shuffle, repeat and queue malfunctions (`usability.library`) | usability | 5685 (C17) | 16888 (C18) | 2.970624 (C19) | 16888 (C20) |
| 6 | App crashes, freezes, and fails to load (`playback.crash`) | playback/performance | 2953 (C21) | 11217 (C22) | 3.798510 (C23) | 11217 (C24) |
| 7 | Login and verification failures (`access.login`) | access/onboarding | 2413 (C25) | 9501 (C26) | 3.937422 (C27) | 9501 (C28) |
| 8 | Navigation and layout (`usability.navigation`) | usability | 3168 (C29) | 7795 (C30) | 2.460543 (C31) | 7795 (C32) |
| 9 | Unwanted song insertions in playlists/radio (`catalog.recommendations`) | catalog/content | 2041 (C33) | 5692 (C34) | 2.788829 (C35) | 5692 (C36) |
| 10 | Missing or removed content (`catalog.missing`) | catalog/content | 1856 (C37) | 5473 (C38) | 2.948815 (C39) | 5473 (C40) |

## Area roll-up (derived from the issue table; not a contract metric)

| Area | Complaints | Severity sum | Share of complaints |
|---|---:|---:|---:|
| general/unspecified (not one of the four options) | 27137 (A01) | 54364 (A02) | 0.297333 (A03) |
| usability | 22146 (A04) | 52983 (A05) | 0.242648 (A06) |
| billing/support | 17990 (A07) | 52551 (A08) | 0.197112 (A09) |
| playback/performance | 14668 (A10) | 48060 (A11) | 0.160714 (A12) |
| catalog/content (not one of the four options) | 6422 (A13) | 18576 (A14) | 0.070364 (A15) |
| access/onboarding | 2905 (A16) | 11300 (A17) | 0.031829 (A18) |

## Trends and robustness (descriptive, computed by code)

Same calendar months one year apart (full months only). Share = the area's complaint and cancellation reviews / all classified reviews in the period.

| Area | 2022 Jun-Oct (T01) | 2023 Jun-Oct (T02) | Change |
|---|---:|---:|---:|
| access/onboarding | 1.0% (T07) | 1.8% (T08) | +0.8 pp (T09) |
| billing/support | 3.8% (T10) | 13.9% (T11) | +10.2 pp (T12) |
| playback/performance | 9.9% (T13) | 5.1% (T14) | -4.8 pp (T15) |
| usability | 11.1% (T16) | 10.0% (T17) | -1.1 pp (T18) |
| Denominator (classified reviews) | 45073 (T03) | 82997 (T05) | |

Note (code): this table, and any comparison of growth in this memo, covers the four decision areas only. Areas that are not decision options are listed in `analysis/period_comparison.json`: catalog/content 2.6% (T50) to 3.2% (T51), +0.7 pp (T52); general/unspecified 2.9% (T53) to 25.2% (T54), +22.3 pp (T55).

| Decision area | Share of complaints | 95% interval (sampling only) |
|---|---:|---:|
| usability | 24.3% (T19) | 24.0% (T20) to 24.5% (T21) |
| billing/support | 19.7% (T22) | 19.5% (T23) to 20.0% (T24) |
| playback/performance | 16.1% (T25) | 15.8% (T26) to 16.3% (T27) |
| access/onboarding | 3.2% (T28) | 3.1% (T29) to 3.3% (T30) |

Volume spikes (code): each line lists at most three issues, from any area (the catch-all `other.general` included), whose share of reviews (the issue's complaint and cancellation reviews / all reviews in the month) rose versus the other full months; zero and negative changes are left out.

- Volume spike 2023-07 (T31): 25850 (T32) reviews (median full month 8549 (T33)); largest increases in share of reviews vs other months: `other.general` +35.9 pp (T34).
- Volume spike 2023-10 (T35): 26790 (T36) reviews (median full month 8549 (T37)); largest increases in share of reviews vs other months: `billing.premium_only` +23.3 pp (T38), `other.general` +15.3 pp (T39), `usability.library` +1.4 pp (T40).
- Verifier robustness on 2000 (T41) sampled reviews (severity_sum (the baseline priority) over complaint and cancellation reviews, row-weighted): decision areas in order under enricher labels **billing/support 705 (T42), usability 650 (T43), playback/performance 617 (T44), access/onboarding 168 (T45)**; under independent verifier labels **playback/performance 758 (T46), usability 747 (T47), billing/support 660 (T48), access/onboarding 196 (T49)** (top area different).

## Representative evidence (exact quotes from the reviews)

"(cited)" marks a review the memo cites in support of the recommendation.

- `other.general` - "stupid app." - review `0b33282e-1629-4f26-b4a6-7a470573e5e5`
- `other.general` - "The worst update ever just to earn profit" - review `f15ac08e-ded3-4c59-8da7-2b544af8a628`
- `billing.premium_only` - "For like 3 to 4 days before I was listening songs and today I really shocked to see that ..now I have to buy premium to put the song again and I can't even play the song now ." - review `674b2fb0-f4a5-430d-9241-ee3ea348a30e`
- `billing.premium_only` - "Very disappointed with the update even we can't use the basic features like previous song, middle of song,by sequence" - review `8fd5987c-9ed8-4789-aa71-65b2a92c9d83`
- `usability.ads` - "Itni jaldi bhikhari bhi dobara bhikh nhi mangta jitni jaldi tumhari app ad chala kar paise mangne lagti hai" - review `16c47c30-882b-40c1-8dd4-6a304bf1e631` (cited)
- `usability.ads` - "Tooo many adds" - review `59d1e2cd-526e-4dea-86b5-964667c7c45e` (cited)
- `playback.stops` - "The app keeps stopping while I'm listening and when I restart it takes me back minutes to an hour in the podcast." - review `016e1433-3c2d-4538-9748-a4a6d5c8f0fe`
- `playback.stops` - "Plays 3 to 4 songs then the app stops playing" - review `044830ff-c085-45a0-896b-db1fc1a4c73b`
- `usability.library` - "I spend hours creating a Playlist and when I go to play the list it plays random stupid songs most having NO discernable connection." - review `3a8d3202-5efe-4711-a74c-6dbf338533b9` (cited)
- `usability.library` - "YOU CAN'T EVEN REPEAT SONGS?????" - review `ea18965a-e6a7-463e-813f-7429b81cec73` (cited)

## Scope figures

| Figure | Value | Token | Source |
|---|---:|---|---|
| Reviews in scope (unique IDs ingested) | 200013 | S01 | ingestion_report.json |
| Completed classifications | 200000 | S02 | grading/records.jsonl |
| Quarantined: empty text | 13 | S03 | quarantine.jsonl |
| Quarantined: other reasons | 0 | S04 | quarantine.jsonl |
| Unfinished | 0 | S05 | run_summary.json |
| Completed records flagged needs_review | 17828 | S06 | enriched.jsonl |
| Complaint and cancellation records ranked | 91268 | S07 | membership.csv |
| Verification sample compared | 2000 | S08 | verification/report.json |
| Verifier topic agreement (rate) | 0.8175 | S09 | verification/report.json |
| Verifier intent agreement (rate) | 0.915 | S10 | verification/report.json |
| Verifier exact severity agreement (rate) | 0.7825 | S11 | verification/report.json |

## Limitations

- The enricher-label and verifier-label samples disagree on which area leads by severity sum, so the exact ranking among usability, billing/support, and playback/performance is provisional at the sample level even though usability leads in the full dataset.
- The period-comparison trend figures are shares of reviews, not severity sums, so they cannot confirm whether usability's underlying severity sum is rising or falling relative to the other areas.
- The spike months identified relate to other.general and premium-only issues, not to usability's top issues (ads, library, navigation), limiting what the spike evidence says about usability specifically.
- These are self-selected reviews describing labeled complaint patterns, not a measured cause of the ad, shuffle/repeat, or navigation problems.
- Unallocated complaints (computed by code from `area_rollup.json`): 29.7% (A19) of complaint and cancellation records (27137 (A01)) are general/unspecified: generic criticism (for example "worst update") that names no specific area, so they are not allocated to any of the four decision areas. If many of them refer to one area's problem, for example the same free-tier change, that area's total is understated; the labels cannot show which area that would be.
- Premium-only boundary, upper-bound sensitivity (computed by code; `analysis/premium_only_sensitivity.json`): 2456 (T56) of the 15763 (C05) `billing.premium_only` complaint and cancellation records contain no Premium or payment word (premium, subscri-, pay/paid/paying, free, buy, money, trial, $; case-insensitive), with a severity sum of 7283 (T57). If none of them belonged to billing/support, its severity sum would fall from 52551 (A08) to 45268 (T58), below usability 52983 (A05) and playback/performance 48060 (A11). This is an upper bound, not a relabelling: many of these reviews plainly describe free-tier limits without naming Premium (skip limits, forced shuffle), and they were not moved to any other area.
- Counts describe the labeled reviews in the declared analysis scope of 200,013 reviews (analysis_200k.csv, a deterministic uniform sample of the 660,622-review corpus plus every empty-text row): self-selected public app reviews, not a customer population. They carry no revenue, plan tier or confirmed cancellations, so revenue at risk cannot be computed.
- Cancellation language is expressed intent, not observed churn; nothing here estimates a causal effect on retention.
- Star ratings and helpful votes were not used to classify; severity is judged from the text under the shared rubric.
- 17828 completed records are flagged needs_review, 13 are quarantined and 0 are unfinished.
- The analysis covers a uniform random sample of the corpus, not every review; shares carry sampling error (intervals shown) and the 460,609 out-of-scope reviews were ingested but not classified.

## Traceability

- `claims.csv`: every issue-level number above (claim_id, issue_id, metric, value); the C## IDs in the prose and the ranking table.
- `memo_tokens.csv` (also `memo.json` -> `token_index`): every token ID used above (C##, A##, S##, T##) with its value, what it measures and the saved file it comes from (`area_rollup.json`, the scope sources, `analysis/*.json`).
- `ranking.csv` / `membership.csv`: rerun with `python -m insight rank --run-dir <run> --check` (no model calls).
- `issues.json`: issue names and the evidence each name was based on.

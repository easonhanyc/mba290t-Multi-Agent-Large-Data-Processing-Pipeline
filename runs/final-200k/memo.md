# Decision memo: where to focus next quarter

Scope: the declared analysis scope of 200,013 reviews (analysis_200k.csv, a deterministic uniform sample of the 660,622-review corpus plus every empty-text row)  
Run: `run-20261014T184902.112Z-bd73` | input `data/analysis_200k.csv` (sha256 `3c023c9dd47a5775...`) | memo source: model, reused from the stage cache (generated in `run-20261014T184545.752Z-3a1e`)

Numbers are written as value (token ID): C## IDs are the issue-level claims in `claims.csv`; every ID (C##, A## area roll-up, S## scope figure, T## trend/robustness) is listed with its value, what it measures and its source file in `memo_tokens.csv`.

## Recommendation

**billing/support.** Billing/support carries the highest baseline priority among the four decision areas, with severity sum 59146 (A02) across 20290 (A01) complaint and cancellation reviews, almost entirely driven by the Premium-only restrictions issue (severity sum 52577 (C02) across 18016 (C01) complaint and cancellation reviews, mean severity 2.918350 (C03)). This issue is free-tier packaging and entitlement policy - what the free tier includes (skip limits, forced shuffle, inability to pick, repeat or rewind songs) and how changes are rolled out and explained - not a payment, charging or checkout defect, so the work belongs with pricing and monetization rather than a support-ticket backlog.

## Next-quarter actions

1. Review the scope and communication of free-tier skip, shuffle, repeat and rewind restrictions tied to billing.premium_only, and test clearer in-app explanation or a narrower restriction; watch whether severity sum 52577 (C02) and complaint count 18016 (C01) move down next period.
2. Investigate the spike in 2023-10 (T35), where billing.premium_only's share of reviews rose by +25.1 pp (T38) versus other months, to see whether a specific rollout or change drove the jump, and check whether the later-period share of reviews for billing/support (15.4% (T11), up +10.9 pp (T12) from 4.5% (T10)) continues to grow or levels off.
3. As a hedge, examine excessive ad interruptions (usability.ads, severity sum 24431 (C10) across 11429 (C09) complaint and cancellation reviews, mean severity 2.137632 (C11)) for quick frequency or placement adjustments, since usability leads on share of complaints 25.6% (T19) and complaint count 23004 (A04).

## Why

- Billing/support's severity sum 59146 (A02) across 20290 (A01) complaint and cancellation reviews is the highest among the four decision areas, led by Premium-only restrictions with severity sum 52577 (C02) across 18016 (C01) reviews and mean severity 2.918350 (C03).
- Trend supports billing/support: among the four decision areas it shows the largest increase in share of reviews between 2022 Jun-Oct (T01) and 2023 Jun-Oct (T02), rising +10.9 pp (T12) (from 4.5% (T10) to 15.4% (T11)), while playback/performance fell -5.0 pp (T15) and usability and access rose only +0.7 pp (T18) and +0.9 pp (T09) respectively.
- Billing/support's share of complaints 22.6% (T22) (interval 22.3% (T23) to 22.9% (T24)) does not overlap with usability's higher share 25.6% (T19) (interval 25.3% (T20) to 25.9% (T21)) or playback/performance's 15.5% (T25); usability leads on share of complaints and complaint count 23004 (A04), even though billing/support leads on severity sum.
- Robustness caveat: the independent verifier, on its labelling of the same 2000 (T41) sampled reviews, ranks playback/performance first on severity sum (758 (T46) versus billing/support's 661 (T48)), disagreeing with the enricher's ordering that puts billing/support first (787 (T42) versus playback/performance's 599 (T44)); this is a labelling disagreement, not noise, and makes the call provisional.
- The premium-only sensitivity check is an upper bound only: removing the 4785 (T56) premium-only records that contain no Premium or payment word (severity sum 14239 (T57)) would drop billing/support's severity sum to 44907 (T58), below usability's 54124 (A05) and playback/performance's 46058 (A08), though the interpretation notes the real effect is likely smaller.

## What would change this call

- The verifier's severity ordering holding on a larger verified sample beyond 2000 (T41), confirming playback/performance (758 (T46)) ahead of billing/support (661 (T48)) rather than the enricher's ordering (787 (T42) ahead of 599 (T44)).
- A human audit of the 4785 (T56) premium-only records without a payment word (severity sum 14239 (T57)) finding most are genuinely about free-tier restrictions would weaken this caveat; finding most are mislabeled would strengthen the case that billing/support's lead is overstated, since removal brings its severity sum to 44907 (T58).
- Billing/support's share of reviews reversing in the same months of the following year rather than continuing the rise from 4.5% (T10) to 15.4% (T11) seen between 2022 Jun-Oct (T01) and 2023 Jun-Oct (T02).

## Alternatives considered

- **usability**: Usability has severity sum 54124 (A05) across 23004 (A04) complaint and cancellation reviews, below billing/support's 59146 (A02), even though it leads on share of complaints 25.6% (T19) and complaint count 23004 (A04); on the enricher's baseline metric it ranks second.
- **playback/performance**: Playback/performance has severity sum 46058 (A08) across 13907 (A07) reviews, below billing/support's 59146 (A02), and its share of reviews fell -5.0 pp (T15) between 2022 Jun-Oct (T01) and 2023 Jun-Oct (T02) (from 9.6% (T13) to 4.7% (T14)), the only decline among the four decision areas, though the verifier's labelling ranks it first on severity sum (758 (T46)).
- **access/onboarding**: Access/onboarding has the lowest severity sum, 11172 (A17) across 2860 (A16) reviews, and the lowest share of complaints 3.2% (T28) (interval 3.1% (T29) to 3.3% (T30)), despite a rise in share of reviews of +0.9 pp (T09) between 2022 Jun-Oct (T01) and 2023 Jun-Oct (T02).

## Supporting numbers (baseline ranking, computed by code)

Priority = severity_sum = complaint_count x mean_severity over complaint and cancellation reviews. Each cell shows the value and its claim ID in `claims.csv`.

| Rank | Issue | Area | Complaints | Severity sum | Mean severity | Priority |
|---:|---|---|---:|---:|---:|---:|
| 1 | Premium-only restrictions (`billing.premium_only`) | billing/support | 18016 (C01) | 52577 (C02) | 2.918350 (C03) | 52577 (C04) |
| 2 | General or unrelated (`other.general`) | general/unspecified | 23108 (C05) | 45898 (C06) | 1.986239 (C07) | 45898 (C08) |
| 3 | Excessive ad interruptions (`usability.ads`) | usability | 11429 (C09) | 24431 (C10) | 2.137632 (C11) | 24431 (C12) |
| 4 | Playback stops or skips unexpectedly (`playback.stops`) | playback/performance | 4973 (C13) | 16288 (C14) | 3.275287 (C15) | 16288 (C16) |
| 5 | Playlist and queue playback misbehaving (`usability.library`) | usability | 4087 (C17) | 12202 (C18) | 2.985564 (C19) | 12202 (C20) |
| 6 | App crashes and fails to load (`playback.crash`) | playback/performance | 3098 (C21) | 11618 (C22) | 3.750161 (C23) | 11618 (C24) |
| 7 | Confusing redesigned home screen layout (`usability.navigation`) | usability | 4187 (C25) | 9931 (C26) | 2.371865 (C27) | 9931 (C28) |
| 8 | Login failures (`access.login`) | access/onboarding | 2366 (C29) | 9370 (C30) | 3.960270 (C31) | 9370 (C32) |
| 9 | Other control annoyances (`usability.other`) | usability | 3301 (C33) | 7560 (C34) | 2.290215 (C35) | 7560 (C36) |
| 10 | Unwanted repetitive or forced recommendations (`catalog.recommendations`) | catalog/content | 2250 (C37) | 6309 (C38) | 2.804000 (C39) | 6309 (C40) |

## Area roll-up (derived from the issue table; not a contract metric)

| Area | Complaints | Severity sum | Share of complaints |
|---|---:|---:|---:|
| billing/support | 20290 (A01) | 59146 (A02) | 0.226042 (A03) |
| usability | 23004 (A04) | 54124 (A05) | 0.256278 (A06) |
| playback/performance | 13907 (A07) | 46058 (A08) | 0.154932 (A09) |
| general/unspecified (not one of the four options) | 23108 (A10) | 45898 (A11) | 0.257436 (A12) |
| catalog/content (not one of the four options) | 6593 (A13) | 19143 (A14) | 0.073450 (A15) |
| access/onboarding | 2860 (A16) | 11172 (A17) | 0.031862 (A18) |

## Trends and robustness (descriptive, computed by code)

Same calendar months one year apart (full months only). Share = the area's complaint and cancellation reviews / all classified reviews in the period.

| Area | 2022 Jun-Oct (T01) | 2023 Jun-Oct (T02) | Change |
|---|---:|---:|---:|
| access/onboarding | 0.9% (T07) | 1.8% (T08) | +0.9 pp (T09) |
| billing/support | 4.5% (T10) | 15.4% (T11) | +10.9 pp (T12) |
| playback/performance | 9.6% (T13) | 4.7% (T14) | -5.0 pp (T15) |
| usability | 10.5% (T16) | 11.3% (T17) | +0.7 pp (T18) |
| Denominator (classified reviews) | 45073 (T03) | 82997 (T05) | |

Note (code): this table, and any comparison of growth in this memo, covers the four decision areas only. Areas that are not decision options are listed in `analysis/period_comparison.json`: catalog/content 2.7% (T50) to 3.3% (T51), +0.6 pp (T52); general/unspecified 2.5% (T53) to 21.7% (T54), +19.3 pp (T55).

| Decision area | Share of complaints | 95% interval (sampling only) |
|---|---:|---:|
| usability | 25.6% (T19) | 25.3% (T20) to 25.9% (T21) |
| billing/support | 22.6% (T22) | 22.3% (T23) to 22.9% (T24) |
| playback/performance | 15.5% (T25) | 15.3% (T26) to 15.7% (T27) |
| access/onboarding | 3.2% (T28) | 3.1% (T29) to 3.3% (T30) |

Volume spikes (code): each line lists at most three issues, from any area (the catch-all `other.general` included), whose share of reviews (the issue's complaint and cancellation reviews / all reviews in the month) rose versus the other full months; zero and negative changes are left out.

- Volume spike 2023-07 (T31): 25850 (T32) reviews (median full month 8549 (T33)); largest increases in share of reviews vs other months: `other.general` +36.0 pp (T34).
- Volume spike 2023-10 (T35): 26790 (T36) reviews (median full month 8549 (T37)); largest increases in share of reviews vs other months: `billing.premium_only` +25.1 pp (T38), `other.general` +9.2 pp (T39), `usability.other` +3.7 pp (T40).
- Verifier robustness on 2000 (T41) sampled reviews (severity_sum (the baseline priority) over complaint and cancellation reviews, row-weighted): decision areas in order under enricher labels **billing/support 787 (T42), usability 637 (T43), playback/performance 599 (T44), access/onboarding 159 (T45)**; under independent verifier labels **playback/performance 758 (T46), usability 709 (T47), billing/support 661 (T48), access/onboarding 192 (T49)** (top area different).

## Representative evidence (exact quotes from the reviews)

"(cited)" marks a review the memo cites in support of the recommendation.

- `billing.premium_only` - "For like 3 to 4 days before I was listening songs and today I really shocked to see that ..now I have to buy premium to put the song again and I can't even play the song now ." - review `674b2fb0-f4a5-430d-9241-ee3ea348a30e` (cited)
- `billing.premium_only` - "Very disappointed with the update even we can't use the basic features like previous song, middle of song,by sequence" - review `8fd5987c-9ed8-4789-aa71-65b2a92c9d83` (cited)
- `other.general` - "stupid app." - review `0b33282e-1629-4f26-b4a6-7a470573e5e5`
- `other.general` - "The worst update ever just to earn profit" - review `f15ac08e-ded3-4c59-8da7-2b544af8a628`
- `usability.ads` - "Itni jaldi bhikhari bhi dobara bhikh nhi mangta jitni jaldi tumhari app ad chala kar paise mangne lagti hai" - review `16c47c30-882b-40c1-8dd4-6a304bf1e631`
- `usability.ads` - "Tooo many adds" - review `59d1e2cd-526e-4dea-86b5-964667c7c45e`
- `playback.stops` - "The app keeps stopping while I'm listening and when I restart it takes me back minutes to an hour in the podcast." - review `016e1433-3c2d-4538-9748-a4a6d5c8f0fe`
- `playback.stops` - "Plays 3 to 4 songs then the app stops playing" - review `044830ff-c085-45a0-896b-db1fc1a4c73b`
- `usability.library` - "I spend hours creating a Playlist and when I go to play the list it plays random stupid songs most having NO discernable connection." - review `3a8d3202-5efe-4711-a74c-6dbf338533b9`
- `usability.library` - "premium update is worse...I have also use other apps but such a drastic change with my playlist can't except...really disappointed...not much with this app .soon uninstalling.." - review `ba161974-a025-4a71-85b7-8c4b6a838a03`

## Scope figures

| Figure | Value | Token | Source |
|---|---:|---|---|
| Reviews in scope (unique IDs ingested) | 200013 | S01 | ingestion_report.json |
| Completed classifications | 200000 | S02 | grading/records.jsonl |
| Quarantined: empty text | 13 | S03 | quarantine.jsonl |
| Quarantined: other reasons | 0 | S04 | quarantine.jsonl |
| Unfinished | 0 | S05 | run_summary.json |
| Completed records flagged needs_review | 16964 | S06 | enriched.jsonl |
| Complaint and cancellation records ranked | 89762 | S07 | membership.csv |
| Verification sample compared | 2000 | S08 | verification/report.json |
| Verifier topic agreement (rate) | 0.809 | S09 | verification/report.json |
| Verifier intent agreement (rate) | 0.9205 | S10 | verification/report.json |
| Verifier exact severity agreement (rate) | 0.7915 | S11 | verification/report.json |
| Golden set: human-labelled reviews scored | 50 | S12 | evals/golden/results.json |
| Golden topic agreement (rate) | 0.76 | S13 | evals/golden/results.json |
| Golden intent agreement (rate) | 0.74 | S14 | evals/golden/results.json |
| Golden severity agreement (rate) | 0.76 | S15 | evals/golden/results.json |

## Limitations

- The verifier's own severity-sum ordering on its 2000 (T41)-review sample puts playback/performance ahead of billing/support, so the recommendation is provisional pending a larger or reconciled verification sample.
- The spike months 2023-07 (T31) and 2023-10 (T35) describe shares of reviews in those specific months only; whether the elevated premium-only share in 2023-10 (T35) (+25.1 pp (T38)) persists beyond the review window is not shown.
- Golden-set and verifier agreement rates (topic, intent, severity) are below full agreement, so issue-to-area assignment, including the boundary between billing.premium_only and other areas, carries some uncertainty not captured in the severity-sum totals.
- The period comparison between 2022 Jun-Oct (T01) and 2023 Jun-Oct (T02) uses self-selected reviews with different total volumes (45073 (T03) versus 82997 (T05) reviews), so the share changes describe compositional shifts in who reviewed, not a measured change in the underlying customer base.
- Unallocated complaints (computed by code from `area_rollup.json`): 25.7% (A19) of complaint and cancellation records (23108 (A10)) are general/unspecified: generic criticism (for example "worst update") that names no specific area, so they are not allocated to any of the four decision areas. If many of them refer to one area's problem, for example the same free-tier change, that area's total is understated; the labels cannot show which area that would be.
- Premium-only boundary, upper-bound sensitivity (computed by code; `analysis/premium_only_sensitivity.json`): 4785 (T56) of the 18016 (C01) `billing.premium_only` complaint and cancellation records contain no Premium or payment word (premium, subscri-, pay/paid/paying, free, buy, money, trial, $; case-insensitive), with a severity sum of 14239 (T57). If none of them belonged to billing/support, its severity sum would fall from 59146 (A02) to 44907 (T58), below usability 54124 (A05) and playback/performance 46058 (A08). This is an upper bound, not a relabelling: many of these reviews plainly describe free-tier limits without naming Premium (skip limits, forced shuffle), and they were not moved to any other area.
- Counts describe the labeled reviews in the declared analysis scope of 200,013 reviews (analysis_200k.csv, a deterministic uniform sample of the 660,622-review corpus plus every empty-text row): self-selected public app reviews, not a customer population. They carry no revenue, plan tier or confirmed cancellations, so revenue at risk cannot be computed.
- Cancellation language is expressed intent, not observed churn; nothing here estimates a causal effect on retention.
- Star ratings and helpful votes were not used to classify; severity is judged from the text under the shared rubric.
- 16964 completed records are flagged needs_review, 13 are quarantined and 0 are unfinished.
- The analysis covers a uniform random sample of the corpus, not every review; shares carry sampling error (intervals shown) and the 460,609 out-of-scope reviews were ingested but not classified.
- Golden set (evals/golden/results.json): on 50 human-labelled reviews the pipeline's labels match the human labels on topic 76%, intent 74% and severity 76% (exact); 50 cases are a diagnostic of label quality, not a precise accuracy estimate.

## Traceability

- `claims.csv`: every issue-level number above (claim_id, issue_id, metric, value); the C## IDs in the prose and the ranking table.
- `memo_tokens.csv` (also `memo.json` -> `token_index`): every token ID used above (C##, A##, S##, T##) with its value, what it measures and the saved file it comes from (`area_rollup.json`, the scope sources, `analysis/*.json`).
- `ranking.csv` / `membership.csv`: rerun with `python -m insight rank --run-dir <run> --check` (no model calls).
- `issues.json`: issue names and the evidence each name was based on.

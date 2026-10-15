# Decision memo: where to focus next quarter

Scope: a 60-review development checkpoint (input.csv), not the full corpus  
Run: `run-20261015T034655.015Z-a6f4` | input `runs/fresh-rehearsal_60-20261015T034611Z/input.csv` (sha256 `d14360867715e255...`) | memo source: model

Numbers are written as value (token ID): C## IDs are the issue-level claims in `claims.csv`; every ID (C##, A## area roll-up, S## scope figure, T## trend/robustness) is listed with its value, what it measures and its source file in `memo_tokens.csv`.

## Recommendation

**billing/support.** Billing/support carries the highest baseline priority among the four decision areas, driven chiefly by the free tier playback restrictions issue (billing.premium_only), with 8 (C01) complaint and cancellation reviews and severity sum 24 (C02) (mean severity 3.000000 (C03)), plus the charged-without-account-access issue (billing.payment, 1 (C21) review, severity sum 5 (C22), mean severity 5.000000 (C23)). The premium_only issue is free-tier packaging and entitlement policy work - what the free tier includes and how changes to it (skip limits, forced shuffle, no repeat or rewind) are rolled out and explained - not a payment or checkout defect, so the next quarter's work should be a product/policy review of free-tier packaging plus a smaller fix for the account-access-at-charge issue.

## Next-quarter actions

1. Review and test changes to free-tier shuffle, skip-limit and rewind restrictions tied to billing.premium_only (8 (C01) complaint reviews, severity sum 24 (C02)); watch for the issue's complaint count and severity sum, and its share of complaints (30.0% (T16)), to fall if packaging changes land well.
2. Investigate the charged-without-account-access flow behind billing.payment (1 (C21) review, severity sum 5 (C22), mean severity 5.000000 (C23)) to clarify account linkage at the point of charge; watch for its severity sum to fall.
3. As a hedge on the closest alternative, test ad-frequency/pacing changes for usability.ads (4 (C09) complaint reviews, severity sum 8 (C10)) and watch for its complaint count and severity sum to fall.

## Why

- Billing/support leads on baseline priority with severity sum 29 (A02) across 9 (A01) complaint and cancellation reviews, ahead of usability's severity sum 17 (A05) and playback/performance's severity sum 13 (A08); within billing/support the premium_only issue (severity sum 24 (C02) across 8 (C01) reviews) and the payment-access issue (severity sum 5 (C22)) are the top drivers.
- Trend: billing/support's share of reviews rose from 6.7% (T07) in 2022 Jun-Oct (T01) to 17.2% (T08) in 2023 Jun-Oct (T02), a change of +10.6 pp (T09), the largest increase among the four decision areas (usability moved +3.9 pp (T15), playback/performance moved +0.2 pp (T12)); this growth supports, but does not by itself establish, the recommendation.
- Billing/support's share of complaints is 30.0% (T16) (interval 16.7% (T17) to 47.9% (T18)), which overlaps with usability's share 26.7% (T19) (interval 14.2% (T20) to 44.4% (T21)) and playback/performance's share 13.3% (T22) (interval 5.3% (T23) to 29.7% (T24)), so the complaint-share lead is within sampling error, even though the severity-sum lead is not undermined by this.
- Robustness caveat: the independent verifier, scoring the same sample of 10 (T42) reviews, ranks usability on top by its own severity sum (8 (T46) versus billing/support's 6 (T43) under enricher labels, or 4 (T48) under verifier labels) - a labelling disagreement that makes this recommendation provisional, not a sampling artifact to dismiss.
- Upper-bound sensitivity: even if the 2 (T55) premium_only records without a Premium or payment word are excluded, billing/support's severity sum would be 23 (T57), still above usability's 17 (A05) and playback/performance's 13 (A08), so the lead is not solely an artifact of those borderline records.

## What would change this call

- If a human audit of the 2 (T55) premium_only records without a Premium or payment word found that many are not about free-tier restrictions, that would weaken (not strengthen) the case for billing/support's severity sum.
- If billing/support's share of reviews reverses back toward its 6.7% (T07) level in the same months of the following year rather than holding near 17.2% (T08), that would weaken the trend support for this recommendation.
- If the verifier's severity-sum ordering (favoring usability) held on a larger verified sample beyond the current 10 (T42) reviews, that would favor usability over billing/support.

## Alternatives considered

- **usability**: Usability's severity sum 17 (A05) across 8 (A04) complaint and cancellation reviews trails billing/support's 29 (A02), and its share of reviews grew less (+3.9 pp (T15) versus billing/support's +10.6 pp (T09)) between 2022 Jun-Oct (T01) and 2023 Jun-Oct (T02); however, the verifier's own labels rank usability first by severity sum (8 (T46)), which is the main reason to flag it as a close alternative.
- **playback/performance**: Playback/performance has the lowest severity sum (13 (A08) across 4 (A07) complaint and cancellation reviews) of the three decision areas with a clear ranking, and its share of reviews barely moved between 2022 Jun-Oct (T01) and 2023 Jun-Oct (T02) (+0.2 pp (T12)), showing little growth pressure relative to billing/support.
- **access/onboarding**: No top issues or complaint/severity figures are reported for this area in the aggregate table (its severity sum under the premium-only sensitivity check is 0 (T58)), so there is no evidence here to support prioritizing it over billing/support.

## Supporting numbers (baseline ranking, computed by code)

Priority = severity_sum = complaint_count x mean_severity over complaint and cancellation reviews. Each cell shows the value and its claim ID in `claims.csv`.

| Rank | Issue | Area | Complaints | Severity sum | Mean severity | Priority |
|---:|---|---|---:|---:|---:|---:|
| 1 | Free tier playback restrictions (`billing.premium_only`) | billing/support | 8 (C01) | 24 (C02) | 3.000000 (C03) | 24 (C04) |
| 2 | General or unrelated (`other.general`) | general/unspecified | 6 (C05) | 12 (C06) | 2.000000 (C07) | 12 (C08) |
| 3 | Excessive ad frequency (`usability.ads`) | usability | 4 (C09) | 8 (C10) | 2.000000 (C11) | 8 (C12) |
| 4 | DJ and Shuffle Feature Availability Issues (`catalog.recommendations`) | catalog/content | 2 (C13) | 6 (C14) | 3.000000 (C15) | 6 (C16) |
| 5 | Music playback stops unexpectedly (`playback.stops`) | playback/performance | 2 (C17) | 6 (C18) | 3.000000 (C19) | 6 (C20) |
| 6 | Charged without linked account access (`billing.payment`) | billing/support | 1 (C21) | 5 (C22) | 5.000000 (C23) | 5 (C24) |
| 7 | App freezing and failing to play music (`playback.crash`) | playback/performance | 1 (C25) | 4 (C26) | 4.000000 (C27) | 4 (C28) |
| 8 | Other control annoyances (`usability.other`) | usability | 2 (C29) | 4 (C30) | 2.000000 (C31) | 4 (C32) |
| 9 | Lyrics feature unavailable (`catalog.lyrics`) | catalog/content | 1 (C33) | 3 (C34) | 3.000000 (C35) | 3 (C36) |
| 10 | Low Audio Quality on Premium (`playback.performance`) | playback/performance | 1 (C37) | 3 (C38) | 3.000000 (C39) | 3 (C40) |

## Area roll-up (derived from the issue table; not a contract metric)

| Area | Complaints | Severity sum | Share of complaints |
|---|---:|---:|---:|
| billing/support | 9 (A01) | 29 (A02) | 0.300000 (A03) |
| usability | 8 (A04) | 17 (A05) | 0.266667 (A06) |
| playback/performance | 4 (A07) | 13 (A08) | 0.133333 (A09) |
| general/unspecified (not one of the four options) | 6 (A10) | 12 (A11) | 0.200000 (A12) |
| catalog/content (not one of the four options) | 3 (A13) | 9 (A14) | 0.100000 (A15) |

## Trends and robustness (descriptive, computed by code)

Same calendar months one year apart (full months only). Share = the area's complaint and cancellation reviews / all classified reviews in the period.

| Area | 2022 Jun-Oct (T01) | 2023 Jun-Oct (T02) | Change |
|---|---:|---:|---:|
| billing/support | 6.7% (T07) | 17.2% (T08) | +10.6 pp (T09) |
| playback/performance | 6.7% (T10) | 6.9% (T11) | +0.2 pp (T12) |
| usability | 13.3% (T13) | 17.2% (T14) | +3.9 pp (T15) |
| Denominator (classified reviews) | 15 (T03) | 29 (T05) | |

Note (code): this table, and any comparison of growth in this memo, covers the four decision areas only. Areas that are not decision options are listed in `analysis/period_comparison.json`: catalog/content 6.7% (T49) to 3.4% (T50), -3.2 pp (T51); general/unspecified 0.0% (T52) to 20.7% (T53), +20.7 pp (T54).

| Decision area | Share of complaints | 95% interval (sampling only) |
|---|---:|---:|
| billing/support | 30.0% (T16) | 16.7% (T17) to 47.9% (T18) |
| usability | 26.7% (T19) | 14.2% (T20) to 44.4% (T21) |
| playback/performance | 13.3% (T22) | 5.3% (T23) to 29.7% (T24) |

Volume spikes (code): each line lists at most three issues, from any area (the catch-all `other.general` included), whose share of reviews (the issue's complaint and cancellation reviews / all reviews in the month) rose versus the other full months; zero and negative changes are left out.

- Volume spike 2022-06 (T25): 7 (T26) reviews (median full month 3 (T27)); largest increases in share of reviews vs other months: `playback.crash` +14.3 pp (T28), `catalog.recommendations` +12.2 pp (T29), `billing.premium_only` +4.1 pp (T30).
- Volume spike 2023-07 (T31): 9 (T32) reviews (median full month 3 (T33)); largest increases in share of reviews vs other months: `other.general` +26.9 pp (T34), `usability.ads` +4.7 pp (T35).
- Volume spike 2023-10 (T36): 11 (T37) reviews (median full month 3 (T38)); largest increases in share of reviews vs other months: `other.general` +20.6 pp (T39), `playback.stops` +9.1 pp (T40), `usability.navigation` +9.1 pp (T41).
- Verifier robustness on 10 (T42) sampled reviews (severity_sum (the baseline priority) over complaint and cancellation reviews, row-weighted): decision areas in order under enricher labels **billing/support 6 (T43), usability 5 (T44), playback/performance 3 (T45)**; under independent verifier labels **usability 8 (T46), playback/performance 4 (T47), billing/support 4 (T48)** (top area different).

## Representative evidence (exact quotes from the reviews)

"(cited)" marks a review the memo cites in support of the recommendation.

- `billing.premium_only` - "Don't like it cause you need to pay money to just listen what you wanna hear and I'm not gonna be having 60 different songs to just listen what I want to hear" - review `d8ed500e-f4cf-4e66-bb54-fa50e36d0839` (cited)
- `billing.premium_only` - "Bruhhh i hate that i cant turn off shuffle option and i cant drag the timelinee suuch basic features are gonee" - review `a7e69c17-14b2-4289-9f56-76a90acdb5f1` (cited)
- `other.general` - "Worst app ever 🤬🤬" - review `ac2965d2-3753-4186-9f07-de49efd7ac21`
- `other.general` - "Before it was the best app ever , but now this app just got a most frustrated app ever I am using since 2018 but now I think it's worth deleting" - review `7dcdae21-bf0a-4cd1-aa68-d9b244b11bed`
- `usability.ads` - "It gives too much ads bro.after 2 songs you will get 1 ad or some times it comes when you start the application." - review `54271e33-caf9-4b79-a9fa-8050d0dd21c1`
- `usability.ads` - "The ads are becoming way too much...." - review `2c105ee7-a641-4053-a676-cc5d4ca41457`
- `catalog.recommendations` - "Very good and i love the app But the fact that it doesn't shuffle and plays an artist song is what i don't like" - review `502610e9-9667-41e8-93fa-e1cac819fc33`
- `catalog.recommendations` - "It's good and all but for some reason I can't get Dj and some ppl do have it and some don't." - review `402ab8b0-3653-4709-8266-b97ea2c054af`
- `playback.stops` - "Now stops after every song making play Iists useless" - review `865dbe36-a04f-4e2c-aecc-61fd7d5afa3a`
- `playback.stops` - "When I enter the Spotify app and play the music but when I leave there the problem starts, the music only stops like that (I don't know if it is my phone or Spotify)" - review `cf9ab0bf-f46f-40fe-b2ff-42c62387f310`

## Scope figures

| Figure | Value | Token | Source |
|---|---:|---|---|
| Reviews in scope (unique IDs ingested) | 60 | S01 | ingestion_report.json |
| Completed classifications | 60 | S02 | grading/records.jsonl |
| Quarantined: empty text | 0 | S03 | quarantine.jsonl |
| Quarantined: other reasons | 0 | S04 | quarantine.jsonl |
| Unfinished | 0 | S05 | run_summary.json |
| Completed records flagged needs_review | 4 | S06 | enriched.jsonl |
| Complaint and cancellation records ranked | 30 | S07 | membership.csv |
| Verification sample compared | 10 | S08 | verification/report.json |
| Verifier topic agreement (rate) | 0.9 | S09 | verification/report.json |
| Verifier intent agreement (rate) | 1.0 | S10 | verification/report.json |
| Verifier exact severity agreement (rate) | 0.6 | S11 | verification/report.json |
| Golden set: human-labelled reviews scored | 50 | S12 | evals/golden/results.json |
| Golden topic agreement (rate) | 0.78 | S13 | evals/golden/results.json |
| Golden intent agreement (rate) | 0.76 | S14 | evals/golden/results.json |
| Golden severity agreement (rate) | 0.74 | S15 | evals/golden/results.json |

## Limitations

- The verifier's disagreement on the top area (usability by its labels versus billing/support by the enricher's labels) is based on a small sample of 10 (T42) reviews, so it cannot settle which area truly leads in severity.
- The premium_only issue mixes free-tier packaging complaints with a few records lacking a clear Premium or payment word; the true boundary of this issue is uncertain beyond the sensitivity check already reported.
- Spike-month figures for billing.premium_only (+4.1 pp (T30)) are drawn from a single month (2022-06 (T25)) with few full-month reviews (7 (T26) against a median of 3 (T27)), so they cannot confirm whether the issue is a sustained pattern.
- The data cannot show whether addressing free-tier packaging would change expressed cancellation intent into retained usage, since these are self-selected reviews rather than a tracked customer cohort.
- Unallocated complaints (computed by code from `area_rollup.json`): 20.0% (A16) of complaint and cancellation records (6 (A10)) are general/unspecified: generic criticism (for example "worst update") that names no specific area, so they are not allocated to any of the four decision areas. If many of them refer to one area's problem, for example the same free-tier change, that area's total is understated; the labels cannot show which area that would be.
- Premium-only boundary, upper-bound sensitivity (computed by code; `analysis/premium_only_sensitivity.json`): 2 (T55) of the 8 (C01) `billing.premium_only` complaint and cancellation records contain no Premium or payment word (premium, subscri-, pay/paid/paying, free, buy, money, trial, $; case-insensitive), with a severity sum of 6 (T56). If none of them belonged to billing/support, its severity sum would fall from 29 (A02) to 23 (T57), still above every other decision area (usability 17 (A05), playback/performance 13 (A08) and access/onboarding 0 (T58)). This is an upper bound, not a relabelling: many of these reviews plainly describe free-tier limits without naming Premium (skip limits, forced shuffle), and they were not moved to any other area.
- Counts describe the labeled reviews in a 60-review development checkpoint (input.csv), not the full corpus: self-selected public app reviews, not a customer population. They carry no revenue, plan tier or confirmed cancellations, so revenue at risk cannot be computed.
- Cancellation language is expressed intent, not observed churn; nothing here estimates a causal effect on retention.
- Star ratings and helpful votes were not used to classify; severity is judged from the text under the shared rubric.
- 4 completed records are flagged needs_review, 0 are quarantined and 0 are unfinished.
- Golden set (evals/golden/results.json): on 50 human-labelled reviews the pipeline's labels match the human labels on topic 78%, intent 76% and severity 74% (exact); 50 cases are a diagnostic of label quality, not a precise accuracy estimate.

## Traceability

- `claims.csv`: every issue-level number above (claim_id, issue_id, metric, value); the C## IDs in the prose and the ranking table.
- `memo_tokens.csv` (also `memo.json` -> `token_index`): every token ID used above (C##, A##, S##, T##) with its value, what it measures and the saved file it comes from (`area_rollup.json`, the scope sources, `analysis/*.json`).
- `ranking.csv` / `membership.csv`: rerun with `python -m insight rank --run-dir <run> --check` (no model calls).
- `issues.json`: issue names and the evidence each name was based on.

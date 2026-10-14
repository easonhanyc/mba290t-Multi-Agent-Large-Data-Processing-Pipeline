# Decision memo: where to focus next quarter

Scope: the declared analysis scope: 200,013 reviews (analysis_200k.csv, a deterministic uniform sample of the 660,622-review corpus plus every empty-text row)  
Run: `run-20261013T233959.792Z-f394` | input `data/analysis_200k.csv` (sha256 `3c023c9dd47a5775...`) | memo source: model

Numbers are written as value (token ID): C## IDs are the issue-level claims in `claims.csv`; every ID (C##, A## area roll-up, S## scope figure, T## trend/robustness) is listed with its value, what it measures and its source file in `memo_tokens.csv`.

## Recommendation

**billing/support.** Billing/support carries the highest baseline priority (59146 (A02)), driven almost entirely by the Premium-only restrictions issue (52577 (C02), mean severity 2.918350 (C03) across 18016 (C01) complaint and cancellation reviews). This issue is a free-tier packaging and entitlement policy question - what the free tier includes (skip limits, forced shuffle, inability to pick, repeat or rewind songs) and how changes to it are rolled out and explained - not a payment, checkout or support-backlog defect.

## Next-quarter actions

1. Pilot clearer in-app messaging and staged rollout of free-tier limits tied to the Premium-only restrictions issue (52577 (C02)), testing whether complaint count (18016 (C01)) or severity sum (52577 (C02)) for that issue declines.
2. Review whether specific free-tier controls (skip limits, forced shuffle, repeat/rewind) can be partially restored or better explained, aiming to reduce the area's share of complaints (0.226042 (A03)) in the next period comparison.
3. As a hedge, prioritize a scoped investigation into playback stability (stops/skips 16288 (C14), crashes 11618 (C22)) given the verifier's alternate ranking (758 (T46)), tracking whether its severity sum narrows the gap with billing/support in a future verified sample.
4. Monitor the trend share for billing/support (+10.9 pp (T12)) into the next comparable period to confirm it continues rising rather than reversing.

## Why

- Billing/support's baseline severity sum (59146 (A02)) exceeds usability (54124 (A05)), playback/performance (46058 (A08)) and access/onboarding (11172 (A17)), and is dominated by the single premium_only issue (52577 (C02)) with a high mean severity (2.918350 (C03)).
- The area's share of reviews grew from 4.5% (T10) in 2022 Jun-Oct (T01) to 15.4% (T11) in 2023 Jun-Oct (T02), a change of +10.9 pp (T12), the largest increase of any area in that comparison, while playback/performance's share fell (-5.0 pp (T15)).
- A spike month (2023-10 (T35)) shows the premium_only issue rising sharply (+25.1 pp (T38)) relative to other months, consistent with the area's growth pattern.
- Within sampling intervals, billing/support's complaint share (22.6% (T22), range 22.3% (T23) to 22.9% (T24)) is close to usability's (25.6% (T19), range 25.3% (T20) to 25.9% (T21)), so the lead over usability is not wide, though it still exceeds playback/performance's complaint share (15.5% (T25)).
- The independent verifier's labels do not fully agree: on the same severity-sum metric the verifier ranks playback/performance first in its sample (758 (T46)) and billing/support third (661 (T48)), whereas the enricher labels rank billing/support first (787 (T42)) and playback/performance third (599 (T44)); both label sets agree usability leads on complaint count alone.

## What would change this call

- If a larger verified sample confirms the verifier's ordering with playback/performance ahead of billing/support on severity sum (758 (T46) versus 661 (T48)), that would weaken the recommendation.
- If billing/support's share of reviews reverses and falls back toward its earlier-period level (4.5% (T10)) in the same months of the following year, that would weaken the case for prioritizing it.
- If the spike-month lift in premium_only complaints (+25.1 pp (T38) in 2023-10 (T35)) fades back to the level seen in other months, that would suggest the issue is less persistent than the baseline priority implies.

## Alternatives considered

- **usability**: Usability has the second-highest baseline severity sum (54124 (A05)), led by excessive ad interruptions (24431 (C10)) and playlist/queue misbehavior (12202 (C18)), and its complaint share held roughly flat between periods (+0.7 pp (T18)); it also leads on raw complaint count in both label sets, but the baseline metric still places it behind billing/support (59146 (A02) versus 54124 (A05)).
- **playback/performance**: Playback/performance has a lower baseline severity sum (46058 (A08)) than billing/support, led by unexpected stops/skips (16288 (C14)) and crashes (11618 (C22)), and its share of reviews declined between the compared periods (-5.0 pp (T15)); the verifier's sample does rank it first on severity (758 (T46)), which is a reason to watch it but not yet to override the larger-sample baseline order.
- **access/onboarding**: Access/onboarding has by far the smallest baseline severity sum (11172 (A17)), driven by login failures (9370 (C30)), and even though its share of reviews grew (+0.9 pp (T09)), it remains the smallest area by complaint share (3.2% (T28), range 3.1% (T29) to 3.3% (T30)).

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

| Decision area | Share of complaints | 95% interval (sampling only) |
|---|---:|---:|
| usability | 25.6% (T19) | 25.3% (T20) to 25.9% (T21) |
| billing/support | 22.6% (T22) | 22.3% (T23) to 22.9% (T24) |
| playback/performance | 15.5% (T25) | 15.3% (T26) to 15.7% (T27) |
| access/onboarding | 3.2% (T28) | 3.1% (T29) to 3.3% (T30) |

- Volume spike 2023-07 (T31): 25850 (T32) reviews (median full month 8549 (T33)); largest increases in share of complaints vs other months: `other.general` +36.0 pp (T34).
- Volume spike 2023-10 (T35): 26790 (T36) reviews (median full month 8549 (T37)); largest increases in share of complaints vs other months: `billing.premium_only` +25.1 pp (T38), `other.general` +9.2 pp (T39), `usability.other` +3.7 pp (T40).
- Verifier robustness on 2000 (T41) sampled reviews (severity_sum (the baseline priority) over complaint and cancellation reviews, row-weighted): decision areas in order under enricher labels **billing/support 787 (T42), usability 637 (T43), playback/performance 599 (T44), access/onboarding 159 (T45)**; under independent verifier labels **playback/performance 758 (T46), usability 709 (T47), billing/support 661 (T48), access/onboarding 192 (T49)** (top area different).

## Representative evidence (exact quotes from the reviews)

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

- The verifier's labels disagree with the enricher's labels on which area ranks first by severity sum (787 (T42) versus 758 (T46)), so the billing/support lead should be treated as provisional pending a larger verified sample.
- The premium_only issue (52577 (C02)) reflects packaging and policy objections rather than technical billing defects, so standard 'billing/support' remediation playbooks (refunds, payment fixes) will not address it.
- Period and spike-month comparisons (2022 Jun-Oct (T01), 2023 Jun-Oct (T02), 2023-07 (T31), 2023-10 (T35)) describe shifting review volume and mix, not a controlled measurement of underlying issue frequency.
- Counts describe the labeled reviews in the declared analysis scope: 200,013 reviews (analysis_200k.csv, a deterministic uniform sample of the 660,622-review corpus plus every empty-text row): self-selected public app reviews, not a customer population. They carry no revenue, plan tier or confirmed cancellations, so revenue at risk cannot be computed.
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

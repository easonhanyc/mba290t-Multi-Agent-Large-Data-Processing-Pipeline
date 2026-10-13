# Decision memo: where to focus next quarter

Scope: the declared analysis scope: 200,013 reviews (analysis_200k.csv, a deterministic uniform sample of the 660,622-review corpus plus every empty-text row)  
Run: `run-20261013T020919.171Z-a0b9` | input `data/analysis_200k.csv` (sha256 `3c023c9dd47a5775...`) | memo source: model

## Recommendation

**billing/support.** Prioritize billing/support, driven overwhelmingly by Premium-only restrictions (18016 complaints, severity sum 52577, mean severity 2.918350), which also shows a sharp spike in October (+25.1 pp). This area carries the highest baseline priority of all four areas (59146) and the largest year-over-year growth in review share (+10.9 pp).

## Why

- Billing/support has the highest baseline priority score (59146), ahead of usability (54124), playback/performance (46058), and access/onboarding (11172).
- Premium-only restrictions alone (18016 reviews, severity sum 52577, mean severity 2.918350) is the single largest issue in the entire table.
- Year-over-year, billing/support's share of reviews grew the most of any decision area, from 4.5% to 15.4% (+10.9 pp), while playback/performance shrank (-5.0 pp) and usability/access grew only modestly (+0.7 pp, +0.9 pp).
- A spike month in October shows billing.premium_only jumping +25.1 pp, consistent with an intensifying recent pattern rather than a one-off.
- Robustness caveat: the independent verifier's severity-based ranking instead puts playback/performance on top (2000 sample), so the lead for billing/support is not fully robust across labeling methods; complaint-count ranking, however, favors usability in both labelings, underscoring this is a severity-driven call.

## Alternatives considered

- **usability**: Usability has the second-highest baseline priority (54124), led by Excessive ad interruptions (11429, severity sum 24431) and Playlist/queue misbehavior (4087, severity sum 12202), and its complaint share held the top spot by count in both enricher and verifier views (25.6%, interval 25.3%-25.9%). But its year-over-year growth (+0.7 pp) was far smaller than billing/support's (+10.9 pp).
- **playback/performance**: Playback/performance shows severity concentration, e.g. App crashes (3098, mean severity 3.750161) and Playback stops (4973, mean severity 3.275287), and the verifier's severity-based ranking places it first (2000 sample). However, its baseline priority under the primary labeling (46058) trails billing/support, and its year-over-year review share declined (-5.0 pp).
- **access/onboarding**: Access/onboarding has the highest mean severity per single issue (Login failures, mean severity 3.960270) but by far the smallest baseline priority (11172) and smallest share of complaints (3.2%, interval 3.1%-3.3%), so its total impact remains limited even though its share grew (+0.9 pp).

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
| billing/support | 20290 | 59146 | 0.226042 |
| usability | 23004 | 54124 | 0.256278 |
| playback/performance | 13907 | 46058 | 0.154932 |
| general/unspecified (not one of the four options) | 23108 | 45898 | 0.257436 |
| catalog/content (not one of the four options) | 6593 | 19143 | 0.073450 |
| access/onboarding | 2860 | 11172 | 0.031862 |

## Trends and robustness (descriptive, computed by code)

Same calendar months one year apart (full months only). Share = the area's complaint and cancellation reviews / all classified reviews in the period.

| Area | Jun-Oct 2022 | Jun-Oct 2023 | Change |
|---|---:|---:|---:|
| access/onboarding | 0.9% | 1.8% | +0.9 pp |
| billing/support | 4.5% | 15.4% | +10.9 pp |
| playback/performance | 9.6% | 4.7% | -5.0 pp |
| usability | 10.5% | 11.3% | +0.7 pp |
| Denominator (classified reviews) | 45073 | 82997 | |

| Decision area | Share of complaints | 95% interval (sampling only) |
|---|---:|---:|
| usability | 25.6% | 25.3% to 25.9% |
| billing/support | 22.6% | 22.3% to 22.9% |
| playback/performance | 15.5% | 15.3% to 15.7% |
| access/onboarding | 3.2% | 3.1% to 3.3% |

- Volume spike 2023-07: 25850 reviews (median full month 8549); largest increases in share: `other.general` +36.0 pp, `billing.price` -0.0 pp, `support.contact` -0.1 pp.
- Volume spike 2023-10: 26790 reviews (median full month 8549); largest increases in share: `billing.premium_only` +25.1 pp, `other.general` +9.2 pp, `usability.other` +3.7 pp.
- Verifier robustness on 2000 sampled reviews (severity_sum (the baseline priority) over complaint and cancellation reviews, row-weighted): decision areas in order under enricher labels **billing/support, usability, playback/performance, access/onboarding**; under independent verifier labels **playback/performance, usability, billing/support, access/onboarding** (top area different).

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

| Figure | Value | Source |
|---|---:|---|
| Reviews in scope (unique IDs ingested) | 200013 | ingestion_report.json |
| Completed classifications | 200000 | grading/records.jsonl |
| Quarantined: empty text | 13 | quarantine.jsonl |
| Quarantined: other reasons | 0 | quarantine.jsonl |
| Unfinished | 0 | run_summary.json |
| Completed records flagged needs_review | 16964 | enriched.jsonl |
| Complaint and cancellation records ranked | 89762 | membership.csv |
| Verification sample compared | 2000 | verification/report.json |
| Verifier topic agreement (rate) | 0.809 | verification/report.json |
| Verifier intent agreement (rate) | 0.9205 | verification/report.json |
| Verifier exact severity agreement (rate) | 0.7915 | verification/report.json |

## Limitations

- These are self-selected public app reviews, not a census of all customers, so counts and shares describe labeled reviews in scope (89762 of 200013), not overall user experience.
- Cancellation language reflects expressed intent, not observed or confirmed churn.
- The verifier agreement rates (0.809, 0.9205, 0.7915) and the disagreement in top-area ranking by severity (2000 sample) show meaningful labeling uncertainty, especially between billing/support and playback/performance.
- Trend figures are descriptive patterns in sampled reviews across two windows (45073 vs 82997 reviews) and cannot establish causes of the shifts.
- Counts describe the labeled reviews in the declared analysis scope: 200,013 reviews (analysis_200k.csv, a deterministic uniform sample of the 660,622-review corpus plus every empty-text row): self-selected public app reviews, not a customer population. They carry no revenue, plan tier or confirmed cancellations, so revenue at risk cannot be computed.
- Cancellation language is expressed intent, not observed churn; nothing here estimates a causal effect on retention.
- Star ratings and helpful votes were not used to classify; severity is judged from the text under the shared rubric.
- 16964 completed records are flagged needs_review, 13 are quarantined and 0 are unfinished; the golden-set comparison (human labels) is still pending.
- The analysis covers a uniform random sample of the corpus, not every review; shares carry sampling error (intervals shown) and the 460,609 out-of-scope reviews were ingested but not classified.

## Traceability

- `claims.csv`: every issue-level number above (claim_id, issue_id, metric, value).
- `ranking.csv` / `membership.csv`: rerun with `python -m insight rank --run-dir <run> --check` (no model calls).
- `issues.json`: issue names and the evidence each name was based on.

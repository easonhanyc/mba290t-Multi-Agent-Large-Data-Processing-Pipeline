# Decision memo: where to focus next quarter

Scope: a 100-review development checkpoint (cost_100.csv), not the full corpus  
Run: `run-20261012T225141.618Z-d2d1` | input `runs/pilot100-20261012T224901Z/input/cost_100.csv` (sha256 `c884ac3b9be50669...`) | memo source: cache

## Recommendation

**usability.** Despite billing/support showing the highest raw baseline priority, the independent verification check points to usability (especially excessive ad interruptions, 7/15/2.142857) as the more robust top area for the next quarter of effort. Usability complaints are concentrated and consistently labeled as the leading issue area by both the original enrichment and the independent verifier, giving more confidence that effort here will address a durable pattern rather than one that shifts under re-labeling.

> **Check:** the baseline's highest-priority decision area is **billing/support** (severity sum 39), not the recommended area. A reviewer must confirm the memo justifies the difference.

## Why

- Usability's top issue, excessive and loud ad interruptions, has 7 complaint/cancellation reviews with a severity sum of 15 and mean severity 2.142857, giving the usability area a total severity sum of 21 across 9 reviews (share 0.173077 of all complaints).
- Billing/support has a higher raw baseline priority (39 severity sum from 13 reviews, share 0.250000), driven almost entirely by one issue (free users locked out of skip/song-choice/repeat, 13 reviews, severity sum 39, mean severity 3.000000).
- The independent verifier check (10 reviews sampled, topic agreement 0.9) found the same top decision area from both the enricher's labels and the verifier's labels to be usability, not billing/support, which is a reason to depart from the raw baseline ranking.
- Verifier severity agreement is comparatively weaker (0.7 exact agreement) than topic/intent agreement (0.9, 1.0), meaning severity-based rankings (which drive the billing lead) are less robust to re-labeling than topic-based rankings that favor usability.
- Trend and interval figures for usability's share of reviews across the sampled periods are provided in the aggregate table but were not numerically resolved in this evidence pack, so no directional (growing/shrinking) claim beyond the robustness agreement above is made.

## Alternatives considered

- **billing/support**: Billing/support has the single highest baseline severity sum (39 from 13 reviews, led by 13 reviews on free-tier restrictions with severity sum 39), but this ranking rests heavily on severity scoring, where independent verifier exact-severity agreement is only 0.7, and the verifier's independently derived top area did not match billing/support, undercutting confidence that this is the most robust priority.
- **playback/performance**: Playback/performance has a moderate severity sum (27 from 8 reviews, share 0.153846), with crashes (2 reviews, severity sum 8, mean 4.000000) and offline/download failures (2 reviews, severity sum 6) as its leading issues, but its total severity sum is below both billing/support and usability, and it was not identified as the top area by either the enricher or the verifier.
- **access/onboarding**: Access/onboarding has the lowest severity sum among decision options (8 from 2 reviews, share 0.038462), driven only by login failures (2 reviews, severity sum 8, mean 4.000000); its small review count makes it a low priority relative to usability and billing/support.

## Supporting numbers (baseline ranking, computed by code)

Priority = severity_sum = complaint_count x mean_severity over complaint and cancellation reviews. Each cell shows the value and its claim ID in `claims.csv`.

| Rank | Issue | Area | Complaints | Severity sum | Mean severity | Priority |
|---:|---|---|---:|---:|---:|---:|
| 1 | Free users locked out of skip, song choice, and repeat (`billing.premium_only`) | billing/support | 13 (C01) | 39 (C02) | 3.000000 (C03) | 39 (C04) |
| 2 | General dissatisfaction with no specific feature (`other.general`) | general/unspecified | 14 (C05) | 28 (C06) | 2.000000 (C07) | 28 (C08) |
| 3 | Excessive and loud ad interruptions (`usability.ads`) | usability | 7 (C09) | 15 (C10) | 2.142857 (C11) | 15 (C12) |
| 4 | Login failures (`access.login`) | access/onboarding | 2 (C13) | 8 (C14) | 4.000000 (C15) | 8 (C16) |
| 5 | App crashes and fails to load (`playback.crash`) | playback/performance | 2 (C17) | 8 (C18) | 4.000000 (C19) | 8 (C20) |
| 6 | Lyrics not displaying consistently (`catalog.lyrics`) | catalog/content | 2 (C21) | 6 (C22) | 3.000000 (C23) | 6 (C24) |
| 7 | Missing songs and limited catalog availability (`catalog.missing`) | catalog/content | 2 (C25) | 6 (C26) | 3.000000 (C27) | 6 (C28) |
| 8 | Declining recommendation quality (`catalog.recommendations`) | catalog/content | 2 (C29) | 6 (C30) | 3.000000 (C31) | 6 (C32) |
| 9 | Downloads stuck or offline mode failing (`downloads.offline`) | playback/performance | 2 (C33) | 6 (C34) | 3.000000 (C35) | 6 (C36) |
| 10 | Google Assistant playback integration failure (`playback.devices`) | playback/performance | 1 (C37) | 4 (C38) | 4.000000 (C39) | 4 (C40) |

## Area roll-up (derived from the issue table; not a contract metric)

| Area | Complaints | Severity sum | Share of complaints |
|---|---:|---:|---:|
| billing/support | 13 | 39 | 0.250000 |
| general/unspecified (not one of the four options) | 14 | 28 | 0.269231 |
| playback/performance | 8 | 27 | 0.153846 |
| usability | 9 | 21 | 0.173077 |
| catalog/content (not one of the four options) | 6 | 18 | 0.115385 |
| access/onboarding | 2 | 8 | 0.038462 |

## Trends and robustness (descriptive, computed by code)

Same calendar months one year apart (full months only). Share = the area's complaint and cancellation reviews / all classified reviews in the period.

| Area | Jun-Oct 2022 | Jun-Oct 2023 | Change |
|---|---:|---:|---:|
| access/onboarding | 0.0% | 2.3% | +2.3 pp |
| billing/support | 8.0% | 20.9% | +12.9 pp |
| playback/performance | 8.0% | 4.7% | -3.3 pp |
| usability | 8.0% | 0.0% | -8.0 pp |
| Denominator (classified reviews) | 25 | 43 | |

| Decision area | Share of complaints | 95% interval (sampling only) |
|---|---:|---:|
| billing/support | 25.0% | 15.2% to 38.2% |
| usability | 17.3% | 9.4% to 29.7% |
| playback/performance | 15.4% | 8.0% to 27.5% |
| access/onboarding | 3.8% | 1.1% to 13.0% |

- Volume spike 2023-07: 11 reviews (median full month 5); largest increases in share: `other.general` +25.6 pp, `downloads.offline` +7.9 pp.
- Volume spike 2023-10: 19 reviews (median full month 5); largest increases in share: `billing.premium_only` +35.5 pp, `catalog.lyrics` +10.5 pp, `other.general` +9.2 pp.
- Verifier robustness on 10 sampled reviews: top decision area under enricher labels **usability**, under independent verifier labels **usability** (same).

## Representative evidence (exact quotes from the reviews)

- `billing.premium_only` - "This app is killing it self and forcing you to pay premium for basic things like just listening to music." - review `a78d831a-69f4-428a-9235-cfdd9775c509`
- `billing.premium_only` - "This was fine till the last update, now you can't even pick a certain song without Spotify premium, and now you can only skip 6 songs, like please just let the songs fit my mood!" - review `d146397f-4a94-4980-be00-ae9212eca3a7`
- `other.general` - "Used to love the app but recent update is very disappointing bye Spotify" - review `b47c203f-366e-4409-922d-cd52aa8bbef6`
- `other.general` - "Worst app." - review `178c3b49-b689-4fe4-92a2-2257a58e6d95`
- `usability.ads` - "that always plays adds instead of songs ...if want to enjoy music free without adds don't download this app .." - review `cf6166ae-d71a-4839-9add-088645ad3b78` (cited)
- `usability.ads` - "Decent,just let me have a solid 4-5 songs without an ad bro, it's always every 1 or 2 song then instant ads, that's all thanks" - review `3e8bdc92-4934-457e-85cc-8b9d14bf51c0` (cited)
- `access.login` - "Will not except my password" - review `de0a9cdf-8974-48bc-802f-331228df4619`
- `access.login` - "It not letting me into my account and there are to many ads" - review `32fb340f-4f9f-4551-8dae-755221e58d6a`
- `playback.crash` - "The latest update has caused my app to crash I cant open the app please fix." - review `55cc3abf-c295-4591-8c3a-78085cfdefaa`
- `playback.crash` - "App is stuck on loading/logo screen" - review `66a29b3c-c14d-440e-b722-b23e0c99ae82`

## Scope figures

| Figure | Value | Source |
|---|---:|---|
| Reviews in scope (unique IDs ingested) | 100 | ingestion_report.json |
| Completed classifications | 100 | grading/records.jsonl |
| Quarantined: empty text | 0 | quarantine.jsonl |
| Quarantined: other reasons | 0 | quarantine.jsonl |
| Unfinished | 0 | run_summary.json |
| Completed records flagged needs_review | 4 | enriched.jsonl |
| Complaint and cancellation records ranked | 52 | membership.csv |
| Verification sample compared | 10 | verification/report.json |
| Verifier topic agreement (rate) | 0.9 | verification/report.json |
| Verifier intent agreement (rate) | 1.0 | verification/report.json |
| Verifier exact severity agreement (rate) | 0.7 | verification/report.json |

## Limitations

- These are self-selected public app reviews, not a census of all customers, so counts and shares describe labeled reviews in scope (52 complaint/cancellation reviews out of 100 completed classifications), not the full user base.
- Cancellation language in reviews reflects expressed intent to cancel, not observed or confirmed churn.
- 4 completed records were flagged needs_review, and several trend/interval tokens in the aggregate table were not numerically resolved in this evidence pack, limiting confidence in directional (growing/shrinking) claims.
- Severity scoring shows only 0.7 exact agreement between enricher and verifier, so severity-based rankings (which favor billing/support) are less stable than topic-based rankings (which favor usability).
- Counts describe the labeled reviews in a 100-review development checkpoint (cost_100.csv), not the full corpus: self-selected public app reviews, not a customer population. They carry no revenue, plan tier or confirmed cancellations, so revenue at risk cannot be computed.
- Cancellation language is expressed intent, not observed churn; nothing here estimates a causal effect on retention.
- Star ratings and helpful votes were not used to classify; severity is judged from the text under the shared rubric.
- 4 completed records are flagged needs_review, 0 are quarantined and 0 are unfinished; the golden-set comparison (human labels) is still pending.

## Traceability

- `claims.csv`: every issue-level number above (claim_id, issue_id, metric, value).
- `ranking.csv` / `membership.csv`: rerun with `python -m insight rank --run-dir <run> --check` (no model calls).
- `issues.json`: issue names and the evidence each name was based on.

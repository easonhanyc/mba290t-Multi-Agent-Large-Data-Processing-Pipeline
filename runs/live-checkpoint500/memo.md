# Decision memo: where to focus next quarter

Scope: a 500-review development checkpoint (checkpoint_500.csv), not the full corpus  
Run: `run-20261012T225242.945Z-c7a3` | input `Final Assignment - Spotify Reviews Dataset/checkpoint_500.csv` (sha256 `a94e31663ee7b7ea...`) | memo source: model

## Recommendation

**usability.** Focus the next quarter on usability, driven by excessive ad frequency 34/73 and the confusing redesigned home screen layout 12/30, with additional complaints about lack of control over app behavior 11/27. Usability has the largest complaint volume of any decision-eligible area (62 reviews, 0.251012 share) and is the area both the enricher and the independent verifier agree is top when robustness is checked.

> **Check:** the baseline's highest-priority decision area is **billing/support** (severity sum 179), not the recommended area. A reviewer must confirm the memo justifies the difference.

## Why

- Usability's severity sum (145) is close to playback/performance (153) and below billing/support (179) on raw baseline priority, but it has the highest complaint count among areas (62) and the widest base of distinct issues (ads 34, navigation 12, lack of control 11).
- The verifier robustness check reports that both the enricher labels and the independent verifier's labels pick usability as the top decision area (48 sampled reviews), which is a stronger robustness signal than billing/support can claim despite its higher raw severity sum.
- Billing/support's lead rests heavily on one issue, premium-only restrictions (54/157), concentrating risk in a single complaint type rather than reflecting breadth across the area.
- Trend and interval figures for the exact share changes are not resolved to numeric values in this pack (tokens 0.9%-6.3% are placeholders), so this recommendation relies primarily on the verifier-agreement robustness signal rather than a confirmed growth trend.
- Overall verification coverage is reasonably strong (48 reviews compared, topic agreement 0.8542, intent agreement 0.9375, severity agreement 0.8125), supporting confidence in the usability label.

## Alternatives considered

- **billing/support**: Highest raw severity sum (179) but concentrated in a single issue, premium-only restrictions (54/157/2.907407), and the verifier robustness check did not select billing/support as the top area despite its baseline lead.
- **playback/performance**: Has high per-issue severity (playback stops 14/48/3.428571, crashes 8/32/4.000000, false connection errors 7/27/3.857143) but lower overall complaint volume (43) and share (0.174089) than usability, and was not flagged as top by the verifier check.
- **access/onboarding**: Smallest complaint count (8) and share (0.032389) of all decision-eligible areas; login failures (6/24/4.000000) are severe per case but too few in volume to outweigh usability's breadth.

## Supporting numbers (baseline ranking, computed by code)

Priority = severity_sum = complaint_count x mean_severity over complaint and cancellation reviews. Each cell shows the value and its claim ID in `claims.csv`.

| Rank | Issue | Area | Complaints | Severity sum | Mean severity | Priority |
|---:|---|---|---:|---:|---:|---:|
| 1 | Premium-only restrictions (`billing.premium_only`) | billing/support | 54 (C01) | 157 (C02) | 2.907407 (C03) | 157 (C04) |
| 2 | General dissatisfaction without specifics (`other.general`) | general/unspecified | 56 (C05) | 109 (C06) | 1.946429 (C07) | 109 (C08) |
| 3 | Excessive ad frequency (`usability.ads`) | usability | 34 (C09) | 73 (C10) | 2.147059 (C11) | 73 (C12) |
| 4 | Playback randomly stops, skips, or fails to start (`playback.stops`) | playback/performance | 14 (C13) | 48 (C14) | 3.428571 (C15) | 48 (C16) |
| 5 | App crashes and fails to load after update (`playback.crash`) | playback/performance | 8 (C17) | 32 (C18) | 4.000000 (C19) | 32 (C20) |
| 6 | Confusing redesigned home screen layout (`usability.navigation`) | usability | 12 (C21) | 30 (C22) | 2.500000 (C23) | 30 (C24) |
| 7 | False "No Internet Connection" Errors (`playback.connection`) | playback/performance | 7 (C25) | 27 (C26) | 3.857143 (C27) | 27 (C28) |
| 8 | Lack of control over app behavior and settings (`usability.other`) | usability | 11 (C29) | 27 (C30) | 2.454545 (C31) | 27 (C32) |
| 9 | Login failures (`access.login`) | access/onboarding | 6 (C33) | 24 (C34) | 4.000000 (C35) | 24 (C36) |
| 10 | Unwanted forced recommendations and shuffle (`catalog.recommendations`) | catalog/content | 7 (C37) | 20 (C38) | 2.857143 (C39) | 20 (C40) |

## Area roll-up (derived from the issue table; not a contract metric)

| Area | Complaints | Severity sum | Share of complaints |
|---|---:|---:|---:|
| billing/support | 60 | 179 | 0.242915 |
| playback/performance | 43 | 153 | 0.174089 |
| usability | 62 | 145 | 0.251012 |
| general/unspecified (not one of the four options) | 56 | 109 | 0.226721 |
| catalog/content (not one of the four options) | 18 | 51 | 0.072874 |
| access/onboarding | 8 | 33 | 0.032389 |

## Trends and robustness (descriptive, computed by code)

Same calendar months one year apart (full months only). Share = the area's complaint and cancellation reviews / all classified reviews in the period.

| Area | Jun-Oct 2022 | Jun-Oct 2023 | Change |
|---|---:|---:|---:|
| access/onboarding | 0.9% | 2.4% | +1.5 pp |
| billing/support | 9.0% | 14.1% | +5.1 pp |
| playback/performance | 5.4% | 7.8% | +2.4 pp |
| usability | 9.9% | 12.2% | +2.3 pp |
| Denominator (classified reviews) | 111 | 205 | |

| Decision area | Share of complaints | 95% interval (sampling only) |
|---|---:|---:|
| usability | 25.1% | 20.1% to 30.9% |
| billing/support | 24.3% | 19.4% to 30.0% |
| playback/performance | 17.4% | 13.2% to 22.6% |
| access/onboarding | 3.2% | 1.7% to 6.3% |

- Volume spike 2023-07: 56 reviews (median full month 21); largest increases in share: `other.general` +42.2 pp, `downloads.offline` +2.8 pp, `playback.connection` +0.5 pp.
- Volume spike 2023-10: 79 reviews (median full month 21); largest increases in share: `billing.premium_only` +21.8 pp, `catalog.lyrics` +4.8 pp, `usability.other` +4.7 pp.
- Verifier robustness on 48 sampled reviews: top decision area under enricher labels **usability**, under independent verifier labels **usability** (same).

## Representative evidence (exact quotes from the reviews)

- `billing.premium_only` - "This app is very very frustrating, you only get 6 skips a day, you can't pick the song you want from your playlist," - review `11ad400f-4487-4dfa-a9da-c8d624f4f107`
- `billing.premium_only` - "Songs still keep playing but if u want unlimited skips u have to pay ~ $10." - review `15502657-31ee-440e-8df3-2c405b5da275`
- `other.general` - "Shifting to better apps" - review `a598cfe0-473b-4665-9eb2-4eebb3c1d877`
- `other.general` - "Used to love the app but recent update is very disappointing bye Spotify" - review `b47c203f-366e-4409-922d-cd52aa8bbef6`
- `usability.ads` - "that always plays adds instead of songs ...if want to enjoy music free without adds don't download this app .." - review `cf6166ae-d71a-4839-9add-088645ad3b78` (cited)
- `usability.ads` - "Too many ads...." - review `e5e6c55f-3069-4b7c-9807-f8b5d5bf2726` (cited)
- `playback.stops` - "Continously pauses songs and podcasts randomly." - review `f1abd13b-2391-4b04-8109-efa7f3cfed0b`
- `playback.stops` - "The very second I signed up for premium it stopped letting me play anything.." - review `a7b7539a-c8d3-4f4e-9edd-d46cd1b1fd12`
- `playback.crash` - "Black screen of death." - review `065c418e-7f18-42a3-b241-fe693b7a2b0c`
- `playback.crash` - "There are random long pauses when gapless playback is on, the music randomly stops and won't play/pause on demand, and recently the entire app wont load past the first screen." - review `651e6e7b-f93e-4369-9631-15c73ddcd4ad`

## Scope figures

| Figure | Value | Source |
|---|---:|---|
| Reviews in scope (unique IDs ingested) | 500 | ingestion_report.json |
| Completed classifications | 500 | grading/records.jsonl |
| Quarantined: empty text | 0 | quarantine.jsonl |
| Quarantined: other reasons | 0 | quarantine.jsonl |
| Unfinished | 0 | run_summary.json |
| Completed records flagged needs_review | 25 | enriched.jsonl |
| Complaint and cancellation records ranked | 247 | membership.csv |
| Verification sample compared | 48 | verification/report.json |
| Verifier topic agreement (rate) | 0.8542 | verification/report.json |
| Verifier intent agreement (rate) | 0.9375 | verification/report.json |
| Verifier exact severity agreement (rate) | 0.8125 | verification/report.json |

## Limitations

- These are self-selected public app reviews, so counts describe labeled reviews in scope (247 of 500 ingested), not all Spotify customers or churn.
- Cancellation language reflects expressed intent, not observed or confirmed churn.
- Several trend and interval tokens in this pack were not populated with values, so growth/shrinkage over time and confidence intervals for usability's lead cannot be described numerically here.
- A quarter of completed records are flagged needs_review (25), and verifier exact-severity agreement is 0.8125, so some severity scores underlying the baseline comparison carry residual uncertainty.
- Counts describe the labeled reviews in a 500-review development checkpoint (checkpoint_500.csv), not the full corpus: self-selected public app reviews, not a customer population. They carry no revenue, plan tier or confirmed cancellations, so revenue at risk cannot be computed.
- Cancellation language is expressed intent, not observed churn; nothing here estimates a causal effect on retention.
- Star ratings and helpful votes were not used to classify; severity is judged from the text under the shared rubric.
- 25 completed records are flagged needs_review, 0 are quarantined and 0 are unfinished; the golden-set comparison (human labels) is still pending.

## Traceability

- `claims.csv`: every issue-level number above (claim_id, issue_id, metric, value).
- `ranking.csv` / `membership.csv`: rerun with `python -m insight rank --run-dir <run> --check` (no model calls).
- `issues.json`: issue names and the evidence each name was based on.

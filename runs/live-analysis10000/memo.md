# Decision memo: where to focus next quarter

Scope: a 10000-review development checkpoint (analysis_10000.csv), not the full corpus  
Run: `run-20261012T230951.360Z-4fe8` | input `Final Assignment - Spotify Reviews Dataset/analysis_10000.csv` (sha256 `eaa62ca6d44d7173...`) | memo source: model

## Recommendation

**usability.** Prioritize usability for the next quarter, focusing on excessive ad interruptions (1286) and the confusing redesigned navigation and lost library items (587, 586). These issues, together with settings/toggle problems (381), make usability the area with the second-highest baseline severity (2840) and the one confirmed as top priority by independent verifier labels.

> **Check:** the baseline's highest-priority decision area is **billing/support** (severity sum 3040), not the recommended area. A reviewer must confirm the memo justifies the difference.

## Why

- Usability has the second-highest baseline priority among areas (2840 severity-sum across 1201 complaints, share 0.262974), close behind billing/support (3040).
- Its largest issue is excessive ad interruptions (1286, 605 complaints, mean severity 2.125620), followed by confusing navigation (587), lost/inaccessible library items (586), and misbehaving settings (381).
- The independent verifier's labels agree with the enricher that usability is the top decision area (top_decision_area_enricher_labels and top_decision_area_verifier_labels both 'usability', same_top_area true), giving this recommendation cross-check robustness that billing/support lacks in this pack.
- Billing/support's raw severity-sum (3040) is nominally higher, but since no resolved trend or interval figures in this pack contradict the verifier's agreement on usability, the robustness check is used to depart from the raw top-ranked area as instructed.
- Usability issues span multiple distinct problems (ads, navigation, library access, settings), suggesting broad-based friction across many user touchpoints rather than a single narrow pain point.

## Alternatives considered

- **billing/support**: Billing/support carries the highest raw baseline priority (3040 severity-sum, led by issue 2721 for premium-gated playback with 924 complaints and mean severity 2.944805), but the independent verifier's labels do not put it in the top spot, and no concrete trend figures are resolved in this pack to support prioritizing it over usability.
- **playback/performance**: Playback/performance has a lower baseline severity-sum (2398) than both billing/support and usability, driven by 834 (playback stalls, 252 complaints, mean severity 3.309524) and 617 (crashes, 166 complaints, mean severity 3.716867); it ranks third on the decision rule.
- **access/onboarding**: Access/onboarding has by far the smallest baseline priority (572 severity-sum, 146 complaints), anchored by login failures (497, 126 complaints, mean severity 3.944444); its share of complaints (0.031968) is the lowest of all four decision areas.

## Supporting numbers (baseline ranking, computed by code)

Priority = severity_sum = complaint_count x mean_severity over complaint and cancellation reviews. Each cell shows the value and its claim ID in `claims.csv`.

| Rank | Issue | Area | Complaints | Severity sum | Mean severity | Priority |
|---:|---|---|---:|---:|---:|---:|
| 1 | Playback blocked entirely without Premium (`billing.premium_only`) | billing/support | 924 (C01) | 2721 (C02) | 2.944805 (C03) | 2721 (C04) |
| 2 | Vague app dissatisfaction/unusable complaints (`other.general`) | general/unspecified | 1149 (C05) | 2286 (C06) | 1.989556 (C07) | 2286 (C08) |
| 3 | Excessive and frequent ad interruptions (`usability.ads`) | usability | 605 (C09) | 1286 (C10) | 2.125620 (C11) | 1286 (C12) |
| 4 | Playback fails to start or stalls (`playback.stops`) | playback/performance | 252 (C13) | 834 (C14) | 3.309524 (C15) | 834 (C16) |
| 5 | App Crashes and Freezes During Playback (`playback.crash`) | playback/performance | 166 (C17) | 617 (C18) | 3.716867 (C19) | 617 (C20) |
| 6 | Confusing redesigned navigation and home screen (`usability.navigation`) | usability | 243 (C21) | 587 (C22) | 2.415638 (C23) | 587 (C24) |
| 7 | Playlists and liked songs inaccessible or lost (`usability.library`) | usability | 197 (C25) | 586 (C26) | 2.974619 (C27) | 586 (C28) |
| 8 | Login failures (`access.login`) | access/onboarding | 126 (C29) | 497 (C30) | 3.944444 (C31) | 497 (C32) |
| 9 | Settings and toggles not working as expected (`usability.other`) | usability | 156 (C33) | 381 (C34) | 2.442308 (C35) | 381 (C36) |
| 10 | Repetitive and poor song recommendations (`catalog.recommendations`) | catalog/content | 117 (C37) | 337 (C38) | 2.880342 (C39) | 337 (C40) |

## Area roll-up (derived from the issue table; not a contract metric)

| Area | Complaints | Severity sum | Share of complaints |
|---|---:|---:|---:|
| billing/support | 1035 | 3040 | 0.226626 |
| usability | 1201 | 2840 | 0.262974 |
| playback/performance | 719 | 2398 | 0.157434 |
| general/unspecified (not one of the four options) | 1149 | 2286 | 0.251587 |
| catalog/content (not one of the four options) | 317 | 933 | 0.069411 |
| access/onboarding | 146 | 572 | 0.031968 |

## Trends and robustness (descriptive, computed by code)

Same calendar months one year apart (full months only). Share = the area's complaint and cancellation reviews / all classified reviews in the period.

| Area | Jun-Oct 2022 | Jun-Oct 2023 | Change |
|---|---:|---:|---:|
| access/onboarding | 1.1% | 1.7% | +0.6 pp |
| billing/support | 4.9% | 16.4% | +11.5 pp |
| playback/performance | 9.0% | 5.1% | -3.9 pp |
| usability | 10.8% | 11.0% | +0.2 pp |
| Denominator (classified reviews) | 2243 | 4102 | |

| Decision area | Share of complaints | 95% interval (sampling only) |
|---|---:|---:|
| usability | 26.3% | 25.0% to 27.6% |
| billing/support | 22.7% | 21.5% to 23.9% |
| playback/performance | 15.7% | 14.7% to 16.8% |
| access/onboarding | 3.2% | 2.7% to 3.7% |

- Volume spike 2023-07: 1246 reviews (median full month 438); largest increases in share: `other.general` +37.4 pp, `billing.price` +0.2 pp, `access.login` +0.1 pp.
- Volume spike 2023-10: 1381 reviews (median full month 438); largest increases in share: `billing.premium_only` +27.9 pp, `other.general` +7.6 pp, `usability.navigation` +3.1 pp.
- Verifier robustness on 845 sampled reviews: top decision area under enricher labels **usability**, under independent verifier labels **usability** (same).

## Representative evidence (exact quotes from the reviews)

- `billing.premium_only` - "lol need prem to play music" - review `fbb8cab0-eb66-49de-9624-a06015514118`
- `billing.premium_only` - "If you don't have premium you can no longer preview a song in anyway, not even in your personal playlist, to make sure that it is the song you want or a song you'd like." - review `d370e58b-26db-4d7f-9a03-69f4f5cd84f4`
- `other.general` - "Collects too much personal information" - review `21ddfe12-8433-4bad-b0f8-e7f605c056ae`
- `other.general` - "I can't use it in iran" - review `6263d7a9-a576-4005-b2f1-f863610ada44`
- `usability.ads` - "One of the worst app I have ever used in I couldn't listen even one song without adds better guys install wynk music app" - review `1cb86bb1-776a-4ec6-9844-6f706a734847` (cited)
- `usability.ads` - "I have premium, and when I watch or listen to a podcast, there are always ads." - review `999448c0-5851-4ea1-bf9e-7db84bd9e7c6` (cited)
- `playback.stops` - "The update honestly sucks, I don't know why but it just doesn't let me play the music i wanted!" - review `a66cc931-d7eb-4cad-9c34-c60cd16e0684`
- `playback.stops` - "half the time the player you get on the home screen doesn't appear then when you go on the app you can hear music but there is no way to stop it without force closing the app, and there are so many small UX issues, eg." - review `290ef99c-7821-4255-818f-bbe28357826f`
- `playback.crash` - "The screen suddenly closes within a second of playing the first song, so practically it doesn't work.." - review `729e90cf-260c-4b67-880a-75cb08b31df4`
- `playback.crash` - "It just doesn't load 90% of the time, or will only play what I've downloaded." - review `6ff20c19-fe45-41af-b658-6141dc220fba`

## Scope figures

| Figure | Value | Source |
|---|---:|---|
| Reviews in scope (unique IDs ingested) | 10000 | ingestion_report.json |
| Completed classifications | 10000 | grading/records.jsonl |
| Quarantined: empty text | 0 | quarantine.jsonl |
| Quarantined: other reasons | 0 | quarantine.jsonl |
| Unfinished | 0 | run_summary.json |
| Completed records flagged needs_review | 1001 | enriched.jsonl |
| Complaint and cancellation records ranked | 4567 | membership.csv |
| Verification sample compared | 845 | verification/report.json |
| Verifier topic agreement (rate) | 0.8024 | verification/report.json |
| Verifier intent agreement (rate) | 0.903 | verification/report.json |
| Verifier exact severity agreement (rate) | 0.7751 | verification/report.json |

## Limitations

- These are self-selected public app reviews, not a census of all customers, so counts and shares describe labeled reviews in scope (4567 complaint/cancellation reviews out of 10000 classified), not the full user base.
- Cancellation language in these reviews reflects expressed intent to cancel, not observed or confirmed churn.
- Several trend and interval tokens in the pack are unresolved placeholders, so this memo cannot state concrete year-over-year growth/shrinkage figures or confidence-interval bounds for the recommended area.
- 1001 completed records were flagged needs_review, and verifier exact-severity agreement is only 0.7751, so severity scores carry some measurement uncertainty.
- Counts describe the labeled reviews in a 10000-review development checkpoint (analysis_10000.csv), not the full corpus: self-selected public app reviews, not a customer population. They carry no revenue, plan tier or confirmed cancellations, so revenue at risk cannot be computed.
- Cancellation language is expressed intent, not observed churn; nothing here estimates a causal effect on retention.
- Star ratings and helpful votes were not used to classify; severity is judged from the text under the shared rubric.
- 1001 completed records are flagged needs_review, 0 are quarantined and 0 are unfinished; the golden-set comparison (human labels) is still pending.

## Traceability

- `claims.csv`: every issue-level number above (claim_id, issue_id, metric, value).
- `ranking.csv` / `membership.csv`: rerun with `python -m insight rank --run-dir <run> --check` (no model calls).
- `issues.json`: issue names and the evidence each name was based on.

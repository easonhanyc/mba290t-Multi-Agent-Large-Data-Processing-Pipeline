# Decision memo: where to focus next quarter

> **OFFLINE STUB RUN - NOT FINDINGS.** Every label and name below came from a local test server that answers by hashing the request. It shows that the pipeline runs end to end; it says nothing about Spotify reviews.

Scope: a 100-review development checkpoint (cost_100.csv), not the full corpus  
Run: `run-20261011T064320.139Z-9928` | input `runs/pilot100-offline-stub-20261011T064233Z/input/cost_100.csv` (sha256 `c884ac3b9be50669...`) | memo source: cache

## Recommendation

**playback/performance.** Stub memo text (offline plumbing test, not a finding), citing 6 and 16.

> **Check:** the baseline's highest-priority decision area is **usability** (severity sum 32), not the recommended area. A reviewer must confirm the memo justifies the difference.

## Why

- Stub text from the offline test server; not a model output.
- Stub text from the offline test server; not a model output.

## Alternatives considered

- **access/onboarding**: Stub text (offline plumbing test).
- **usability**: Stub text (offline plumbing test).
- **billing/support**: Stub text (offline plumbing test).

## Supporting numbers (baseline ranking, computed by code)

Priority = severity_sum = complaint_count x mean_severity over complaint and cancellation reviews. Each cell shows the value and its claim ID in `claims.csv`.

| Rank | Issue | Area | Complaints | Severity sum | Mean severity | Priority |
|---:|---|---|---:|---:|---:|---:|
| 1 | Stub issue name (`billing.premium_only`) | billing/support | 6 (C01) | 16 (C02) | 2.666667 (C03) | 16 (C04) |
| 2 | Stub issue name (`usability.navigation`) | usability | 5 (C05) | 16 (C06) | 3.200000 (C07) | 16 (C08) |
| 3 | Stub issue name (`catalog.missing`) | catalog/content | 4 (C09) | 13 (C10) | 3.250000 (C11) | 13 (C12) |
| 4 | Stub issue name (`usability.ads`) | usability | 3 (C13) | 13 (C14) | 4.333333 (C15) | 13 (C16) |
| 5 | Stub issue name (`catalog.search`) | catalog/content | 3 (C17) | 10 (C18) | 3.333333 (C19) | 10 (C20) |
| 6 | Stub issue name (`playback.stops`) | playback/performance | 3 (C21) | 9 (C22) | 3.000000 (C23) | 9 (C24) |
| 7 | Stub issue name (`access.login`) | access/onboarding | 2 (C25) | 7 (C26) | 3.500000 (C27) | 7 (C28) |
| 8 | Stub issue name (`catalog.podcasts`) | catalog/content | 2 (C29) | 7 (C30) | 3.500000 (C31) | 7 (C32) |
| 9 | Stub issue name (`access.account`) | access/onboarding | 2 (C33) | 6 (C34) | 3.000000 (C35) | 6 (C36) |
| 10 | Stub issue name (`billing.price`) | billing/support | 3 (C37) | 6 (C38) | 2.000000 (C39) | 6 (C40) |

## Area roll-up (derived from the issue table; not a contract metric)

| Area | Complaints | Severity sum | Share of complaints |
|---|---:|---:|---:|
| catalog/content (not one of the four options) | 11 | 34 | 0.239130 |
| usability | 10 | 32 | 0.217391 |
| billing/support | 12 | 29 | 0.260870 |
| playback/performance | 9 | 25 | 0.195652 |
| access/onboarding | 4 | 13 | 0.086957 |

## Representative evidence (exact quotes from the reviews)

- `billing.premium_only` - "Best music app ever" - review `ee3e2bd4-f94d-4e76-b2a6-5f6533d74c7c` (cited)
- `billing.premium_only` - "It's the best app ever" - review `8737ac88-7e76-45ba-aa42-4eb97e3300ec`
- `usability.navigation` - "Spotify is great, but the new homescreen update is horrible." - review `94c9f2f9-36fa-4c11-936e-660514fe7a35`
- `usability.navigation` - "Spotify is a very nice listening 🎧 app on music platform" - review `2b57a12b-bbbe-457c-83a8-1bec297a5f63`
- `catalog.missing` - "Great" - review `dc73ecd9-3293-4ede-90d5-dd6cd1e8d087`
- `catalog.missing` - "Best indeeeeeeeed" - review `9f46904c-4ed3-4799-8949-379b949c7344`
- `usability.ads` - "RUDE APP , THIS APP SUPPORT GUYS 🤮🤮🤮🤮🤮🤮🤮🤮🤮🤮." - review `33526c6f-7a49-4b3d-bd20-d1bc191c494c`
- `usability.ads` - "It not letting me into my account and there are to many ads" - review `32fb340f-4f9f-4551-8dae-755221e58d6a`
- `catalog.search` - "Love the mixes they make, always fire suggestions!" - review `53e95a47-d326-4579-945d-a7aabd780b12`
- `catalog.search` - "What kind of stupidity is this?" - review `89ea2c30-db8b-459d-8ab7-bbcb7f92c774`

## Scope figures

| Figure | Value | Source |
|---|---:|---|
| Reviews in scope (unique IDs ingested) | 100 | ingestion_report.json |
| Completed classifications | 100 | grading/records.jsonl |
| Quarantined: empty text | 0 | quarantine.jsonl |
| Quarantined: other reasons | 0 | quarantine.jsonl |
| Unfinished | 0 | run_summary.json |
| Completed records flagged needs_review | 60 | enriched.jsonl |
| Complaint and cancellation records ranked | 46 | membership.csv |
| Verification sample compared | 10 | verification/report.json |
| Verifier topic agreement (rate) | 0.1 | verification/report.json |
| Verifier intent agreement (rate) | 0.3 | verification/report.json |
| Verifier exact severity agreement (rate) | 0.4 | verification/report.json |

## Limitations

- Stub text from the offline test server; not a model output.
- Stub text from the offline test server; not a model output.
- Counts describe the labeled reviews in a 100-review development checkpoint (cost_100.csv), not the full corpus: self-selected public app reviews, not a customer population. They carry no revenue, plan tier or confirmed cancellations, so revenue at risk cannot be computed.
- Cancellation language is expressed intent, not observed churn; nothing here estimates a causal effect on retention.
- Star ratings and helpful votes were not used to classify; severity is judged from the text under the shared rubric.
- 60 completed records are flagged needs_review, 0 are quarantined and 0 are unfinished; the golden-set comparison (human labels) is still pending.

## Traceability

- `claims.csv`: every issue-level number above (claim_id, issue_id, metric, value).
- `ranking.csv` / `membership.csv`: rerun with `python -m insight rank --run-dir <run> --check` (no model calls).
- `issues.json`: issue names and the evidence each name was based on.

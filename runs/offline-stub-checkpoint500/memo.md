# Decision memo: where to focus next quarter

> **OFFLINE STUB RUN - NOT FINDINGS.** Every label and name below came from a local test server that answers by hashing the request. It shows that the pipeline runs end to end; it says nothing about Spotify reviews.

Scope: a 500-review development checkpoint (checkpoint_500.csv), not the full corpus  
Run: `run-20261002T011156.736Z-b93d` | input `Final Assignment - Spotify Reviews Dataset/checkpoint_500.csv` (sha256 `a94e31663ee7b7ea...`) | memo source: cache

## Recommendation

**access/onboarding.** Stub memo text (offline plumbing test, not a finding), citing 17 and 53.

> **Check:** the baseline's highest-priority decision area is **playback/performance** (severity sum 202), not the recommended area. A reviewer must confirm the memo justifies the difference.

## Why

- Stub text from the offline test server; not a model output.
- Stub text from the offline test server; not a model output.

## Alternatives considered

- **usability**: Stub text (offline plumbing test).
- **playback/performance**: Stub text (offline plumbing test).
- **billing/support**: Stub text (offline plumbing test).

## Supporting numbers (baseline ranking, computed by code)

Priority = severity_sum = complaint_count x mean_severity over complaint and cancellation reviews. Each cell shows the value and its claim ID in `claims.csv`.

| Rank | Issue | Area | Complaints | Severity sum | Mean severity | Priority |
|---:|---|---|---:|---:|---:|---:|
| 1 | Stub issue name (`downloads.offline`) | playback/performance | 17 (C01) | 53 (C02) | 3.117647 (C03) | 53 (C04) |
| 2 | Stub issue name (`playback.devices`) | playback/performance | 13 (C05) | 44 (C06) | 3.384615 (C07) | 44 (C08) |
| 3 | Stub issue name (`billing.premium_only`) | billing/support | 14 (C09) | 41 (C10) | 2.928571 (C11) | 41 (C12) |
| 4 | Stub issue name (`catalog.lyrics`) | catalog/content | 13 (C13) | 40 (C14) | 3.076923 (C15) | 40 (C16) |
| 5 | Stub issue name (`playback.stops`) | playback/performance | 13 (C17) | 38 (C18) | 2.923077 (C19) | 38 (C20) |
| 6 | Stub issue name (`catalog.missing`) | catalog/content | 12 (C21) | 35 (C22) | 2.916667 (C23) | 35 (C24) |
| 7 | Stub issue name (`catalog.search`) | catalog/content | 11 (C25) | 35 (C26) | 3.181818 (C27) | 35 (C28) |
| 8 | Stub issue name (`access.account`) | access/onboarding | 12 (C29) | 34 (C30) | 2.833333 (C31) | 34 (C32) |
| 9 | Stub issue name (`usability.ads`) | usability | 10 (C33) | 34 (C34) | 3.400000 (C35) | 34 (C36) |
| 10 | Stub issue name (`usability.navigation`) | usability | 9 (C37) | 31 (C38) | 3.444444 (C39) | 31 (C40) |

## Area roll-up (derived from the issue table; not a contract metric)

| Area | Complaints | Severity sum | Share of complaints |
|---|---:|---:|---:|
| playback/performance | 67 | 202 | 0.304545 |
| catalog/content (not one of the four options) | 48 | 151 | 0.218182 |
| billing/support | 43 | 124 | 0.195455 |
| usability | 35 | 116 | 0.159091 |
| access/onboarding | 19 | 55 | 0.086364 |
| general/unspecified (not one of the four options) | 8 | 30 | 0.036364 |

## Representative evidence (exact quotes from the reviews)

- `downloads.offline` - "Best indeeeeeeeed" - review `9f46904c-4ed3-4799-8949-379b949c7344` (cited)
- `downloads.offline` - "I haven't experted about this from Spotify...🙄 I'm uninstalling successful....meet me when have got the old Spotify update !!!" - review `62b53e0a-0397-4200-826f-122d18fdde32`
- `playback.devices` - "i have used spotify for 5 years and would say its the best streaming service" - review `6455e7cb-ad90-47ad-883f-5b0f0e205af1`
- `playback.devices` - "Excellent quality and great choice" - review `00a77161-cb3f-4fae-a7b6-eca2cfc124ec`
- `billing.premium_only` - "I can't use anything else but Spotify 💯👍🏼" - review `ba274609-2cbc-4d6a-9624-276d1c8246e8`
- `billing.premium_only` - "Very good app enna advertisement verudu premium best" - review `ed15bb17-865a-492b-ba1b-268f4cab78f6`
- `catalog.lyrics` - "I hate application" - review `1db044db-d184-4335-877c-d8fc364b282e`
- `catalog.lyrics` - "Nice as always,keep up the good job." - review `b25beb44-9cc8-4d1e-b375-a4f319419424`
- `playback.stops` - "App is very easy to use and no more ads" - review `28a441b5-1d54-4a5d-9df3-cbc84d21527c`
- `playback.stops` - "No good" - review `5fb51bd0-dbe9-4a19-a466-a77f0c14393e`

## Scope figures

| Figure | Value | Source |
|---|---:|---|
| Reviews in scope (unique IDs ingested) | 500 | ingestion_report.json |
| Completed classifications | 500 | grading/records.jsonl |
| Quarantined: empty text | 0 | quarantine.jsonl |
| Quarantined: other reasons | 0 | quarantine.jsonl |
| Unfinished | 0 | run_summary.json |
| Completed records flagged needs_review | 210 | enriched.jsonl |
| Complaint and cancellation records ranked | 220 | membership.csv |
| Verification sample compared | 48 | verification/report.json |
| Verifier topic agreement (rate) | 0.125 | verification/report.json |
| Verifier intent agreement (rate) | 0.25 | verification/report.json |
| Verifier exact severity agreement (rate) | 0.1875 | verification/report.json |

## Limitations

- Stub text from the offline test server; not a model output.
- Stub text from the offline test server; not a model output.
- Counts describe the labeled reviews in a 500-review development checkpoint (checkpoint_500.csv), not the full corpus: self-selected public app reviews, not a customer population. They carry no revenue, plan tier or confirmed cancellations, so revenue at risk cannot be computed.
- Cancellation language is expressed intent, not observed churn; nothing here estimates a causal effect on retention.
- Star ratings and helpful votes were not used to classify; severity is judged from the text under the shared rubric.
- 210 completed records are flagged needs_review, 0 are quarantined and 0 are unfinished; the golden-set comparison (human labels) is still pending.

## Traceability

- `claims.csv`: every issue-level number above (claim_id, issue_id, metric, value).
- `ranking.csv` / `membership.csv`: rerun with `python -m insight rank --run-dir <run> --check` (no model calls).
- `issues.json`: issue names and the evidence each name was based on.

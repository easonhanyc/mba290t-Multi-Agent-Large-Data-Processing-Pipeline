# Decision memo: where to focus next quarter

> **OFFLINE STUB RUN - NOT FINDINGS.** Every label and name below came from a local test server that answers by hashing the request. It shows that the pipeline runs end to end; it says nothing about Spotify reviews.

Scope: a 500-review development checkpoint (checkpoint_500.csv), not the full corpus  
Run: `run-20261013T234635.589Z-c738` | input `Final Assignment - Spotify Reviews Dataset/checkpoint_500.csv` (sha256 `a94e31663ee7b7ea...`) | memo source: model

Numbers are written as value (token ID): C## IDs are the issue-level claims in `claims.csv`; every ID (C##, A## area roll-up, S## scope figure, T## trend/robustness) is listed with its value, what it measures and its source file in `memo_tokens.csv`.

## Recommendation

**usability.** Stub memo text (offline plumbing test, not a finding), citing 19 (C01) and 63 (C02).

> **Check:** the baseline's highest-priority decision area is **playback/performance** (severity sum 177 (A02)), not the recommended area. A reviewer must confirm the memo justifies the difference.

## Next-quarter actions

1. Stub text from the offline test server; not a model output.
2. Stub text from the offline test server; not a model output.

## Why

- Stub text from the offline test server; not a model output.
- Stub text from the offline test server; not a model output.

## What would change this call

- Stub text from the offline test server; not a model output.
- Stub text from the offline test server; not a model output.

## Alternatives considered

- **access/onboarding**: Stub text (offline plumbing test).
- **playback/performance**: Stub text (offline plumbing test).
- **billing/support**: Stub text (offline plumbing test).

## Supporting numbers (baseline ranking, computed by code)

Priority = severity_sum = complaint_count x mean_severity over complaint and cancellation reviews. Each cell shows the value and its claim ID in `claims.csv`.

| Rank | Issue | Area | Complaints | Severity sum | Mean severity | Priority |
|---:|---|---|---:|---:|---:|---:|
| 1 | Stub issue name (`catalog.missing`) | catalog/content | 19 (C01) | 63 (C02) | 3.315789 (C03) | 63 (C04) |
| 2 | Stub issue name (`billing.premium_only`) | billing/support | 17 (C05) | 56 (C06) | 3.294118 (C07) | 56 (C08) |
| 3 | Stub issue name (`playback.crash`) | playback/performance | 14 (C09) | 48 (C10) | 3.428571 (C11) | 48 (C12) |
| 4 | Stub issue name (`usability.library`) | usability | 15 (C13) | 44 (C14) | 2.933333 (C15) | 44 (C16) |
| 5 | General or unrelated (`other.general`) | general/unspecified | 13 (C17) | 41 (C18) | 3.153846 (C19) | 41 (C20) |
| 6 | Stub issue name (`billing.payment`) | billing/support | 11 (C21) | 39 (C22) | 3.545455 (C23) | 39 (C24) |
| 7 | Stub issue name (`catalog.search`) | catalog/content | 13 (C25) | 38 (C26) | 2.923077 (C27) | 38 (C28) |
| 8 | Stub issue name (`usability.ads`) | usability | 9 (C29) | 37 (C30) | 4.111111 (C31) | 37 (C32) |
| 9 | Stub issue name (`access.account`) | access/onboarding | 12 (C33) | 33 (C34) | 2.750000 (C35) | 33 (C36) |
| 10 | Stub issue name (`usability.navigation`) | usability | 12 (C37) | 33 (C38) | 2.750000 (C39) | 33 (C40) |

## Area roll-up (derived from the issue table; not a contract metric)

| Area | Complaints | Severity sum | Share of complaints |
|---|---:|---:|---:|
| playback/performance | 59 (A01) | 177 (A02) | 0.248945 (A03) |
| catalog/content (not one of the four options) | 56 (A04) | 171 (A05) | 0.236287 (A06) |
| billing/support | 45 (A07) | 141 (A08) | 0.189873 (A09) |
| usability | 44 (A10) | 137 (A11) | 0.185654 (A12) |
| access/onboarding | 20 (A13) | 62 (A14) | 0.084388 (A15) |
| general/unspecified (not one of the four options) | 13 (A16) | 41 (A17) | 0.054852 (A18) |

## Trends and robustness (descriptive, computed by code)

Same calendar months one year apart (full months only). Share = the area's complaint and cancellation reviews / all classified reviews in the period.

| Area | 2022 Jun-Oct (T01) | 2023 Jun-Oct (T02) | Change |
|---|---:|---:|---:|
| access/onboarding | 1.8% (T07) | 4.4% (T08) | +2.6 pp (T09) |
| billing/support | 8.1% (T10) | 9.3% (T11) | +1.2 pp (T12) |
| playback/performance | 9.0% (T13) | 11.2% (T14) | +2.2 pp (T15) |
| usability | 9.9% (T16) | 7.8% (T17) | -2.1 pp (T18) |
| Denominator (classified reviews) | 111 (T03) | 205 (T05) | |

| Decision area | Share of complaints | 95% interval (sampling only) |
|---|---:|---:|
| playback/performance | 24.9% (T19) | 19.8% (T20) to 30.8% (T21) |
| billing/support | 19.0% (T22) | 14.5% (T23) to 24.5% (T24) |
| usability | 18.6% (T25) | 14.1% (T26) to 24.0% (T27) |
| access/onboarding | 8.4% (T28) | 5.5% (T29) to 12.7% (T30) |

- Volume spike 2023-07 (T31): 56 (T32) reviews (median full month 21 (T33)); largest increases in share of complaints vs other months: `playback.crash` +9.0 pp (T34), `usability.other` +2.3 pp (T35), `access.login` +2.1 pp (T36).
- Volume spike 2023-10 (T37): 79 (T38) reviews (median full month 21 (T39)); largest increases in share of complaints vs other months: `downloads.offline` +2.7 pp (T40), `usability.navigation` +2.2 pp (T41), `catalog.search` +1.4 pp (T42).
- Verifier robustness on 48 (T43) sampled reviews (severity_sum (the baseline priority) over complaint and cancellation reviews, row-weighted): decision areas in order under enricher labels **usability 29 (T44), playback/performance 16 (T45), billing/support 6 (T46), access/onboarding 2 (T47)**; under independent verifier labels **playback/performance 28 (T48), billing/support 14 (T49), access/onboarding 8 (T50), usability 1 (T51)** (top area different).

## Representative evidence (exact quotes from the reviews)

- `catalog.missing` - "Will not except my password" - review `de0a9cdf-8974-48bc-802f-331228df4619` (cited)
- `catalog.missing` - "I have worked remotely without cell or internet and I like that I can still play all my collections." - review `27aeb125-266a-47c9-85f5-bd8a56b4d6c3`
- `billing.premium_only` - "Electrifying, AWESOME 👌 👏 👍" - review `8b8e60dc-c64c-4c65-9e5c-5bb2df16d384`
- `billing.premium_only` - "useless music app music k naam pe khaali ad dikhata hai." - review `6eb64519-37d4-4591-a47a-bbb96357de36`
- `playback.crash` - "I hate application" - review `1db044db-d184-4335-877c-d8fc364b282e`
- `playback.crash` - "This app is now not for free users....." - review `6a4f84b4-18e2-47d9-adb8-2461a9319c11`
- `usability.library` - "This is not well so many ad here" - review `ec96a982-68d0-44c4-b2be-13a999be4094`
- `usability.library` - "To everyone, do not update Spotify app, some features are missing in updated version," - review `02777996-211f-447b-94c4-99b61f049f78`
- `other.general` - "The new layout is awful." - review `2aae0ce4-ae4a-46ce-b2fe-0d901eb23c06`
- `other.general` - "Some of the song lyrics couldn't load, even if I updated it and refresh the app." - review `d218ffde-42f9-48f8-a793-832507454b35`

## Scope figures

| Figure | Value | Token | Source |
|---|---:|---|---|
| Reviews in scope (unique IDs ingested) | 500 | S01 | ingestion_report.json |
| Completed classifications | 500 | S02 | grading/records.jsonl |
| Quarantined: empty text | 0 | S03 | quarantine.jsonl |
| Quarantined: other reasons | 0 | S04 | quarantine.jsonl |
| Unfinished | 0 | S05 | run_summary.json |
| Completed records flagged needs_review | 318 | S06 | enriched.jsonl |
| Complaint and cancellation records ranked | 237 | S07 | membership.csv |
| Verification sample compared | 48 | S08 | verification/report.json |
| Verifier topic agreement (rate) | 0.1875 | S09 | verification/report.json |
| Verifier intent agreement (rate) | 0.25 | S10 | verification/report.json |
| Verifier exact severity agreement (rate) | 0.1875 | S11 | verification/report.json |

## Limitations

- Stub text from the offline test server; not a model output.
- Stub text from the offline test server; not a model output.
- Counts describe the labeled reviews in a 500-review development checkpoint (checkpoint_500.csv), not the full corpus: self-selected public app reviews, not a customer population. They carry no revenue, plan tier or confirmed cancellations, so revenue at risk cannot be computed.
- Cancellation language is expressed intent, not observed churn; nothing here estimates a causal effect on retention.
- Star ratings and helpful votes were not used to classify; severity is judged from the text under the shared rubric.
- 318 completed records are flagged needs_review, 0 are quarantined and 0 are unfinished.

## Traceability

- `claims.csv`: every issue-level number above (claim_id, issue_id, metric, value); the C## IDs in the prose and the ranking table.
- `memo_tokens.csv` (also `memo.json` -> `token_index`): every token ID used above (C##, A##, S##, T##) with its value, what it measures and the saved file it comes from (`area_rollup.json`, the scope sources, `analysis/*.json`).
- `ranking.csv` / `membership.csv`: rerun with `python -m insight rank --run-dir <run> --check` (no model calls).
- `issues.json`: issue names and the evidence each name was based on.

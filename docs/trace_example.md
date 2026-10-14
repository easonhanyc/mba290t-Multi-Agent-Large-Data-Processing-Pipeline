# One review traced end to end

Generated from saved artifacts by `python -m insight trace` (no model calls).

## A. Traced review (top issue, verified, not quoted in the memo)

Review `02ccf42f-6ef1-44e2-ad96-5c8972e856d5` (run `final-200k`).

**1. Source row** (`ingest`, code). Six original fields, unchanged; row hash = SHA-256 of their compact JSON.

| Field | Value |
|---|---|
| review_text | I wanna give a 5 star rating but the new update made me do so !! even if u wanna listen the main part of the song u have to get premium 💀✨ idk why they r doin this,......tbh I want a new update that would be able to do what we used to do!!!! |
| review_rating | 2 |
| review_likes | 0 |
| app_version | 8.8.76.667 |
| review_timestamp | 2023-10-18 05:05:08 |
| source_sha256 | `e19884f0a7a6708575643dc8b46bed3a2aed3db821d612d917c3a26fc44585fe` |

**2. Enrichment** (`enrich`, model + code). Only `review_text` was sent.

| Field | Value |
|---|---|
| status | completed (labeled by **fallback1**) |
| topic / subtopic | billing / premium_only |
| intent | complaint |
| severity | 3 (A degraded or restricted function; some use or workaround remains) |
| sentiment | -0.5 |
| evidence_quote | "even if u wanna listen the main part of the song u have to get premium 💀✨ idk why they r doin this,......tbh I want a new update that would be able to do what we used to do!!!!" (exact substring: True) |
| entities (code-matched) | update, premium |
| needs_review | False |
| cache_source_id | - |
| label_config | `gpt-6-luna@none>gpt-6-luna@low(10%)>sonnet@low(0.25%)\|enrich-v2\|schema-v2\|cfg-f6337dc790` |
| difficulty signals | request with severity 3 (definition implies 1) |
| primary answer before fallback | issue billing_premium_only, intent request, severity 3 |

Model calls that carried this review (every attempt is logged before it is sent):

| request_id | role / tier | phase | model (reported) | tier / billing | outcome | in / cached / out tokens | billed |
|---|---|---|---|---|---|---|---:|
| `req-20261013T005534241902-572f587b` | enrich / primary | resume | `gpt-6-luna` (gpt-6-luna) | flex / api | succeeded | 4178 / 2368 / 1647 | $0.000537 |
| `req-20261013T010759019782-0f7b5897` | enrich / fallback1 | resume | `gpt-6-luna` (gpt-6-luna) | flex / api | succeeded | 2291 / 2199 / 38 | $0.000026 |
| `req-20261013T015230781792-0eeb575b` | verify / verify | resume | `haiku` (claude-haiku-4-5-20251001) | subscription / subscription | succeeded | 4417 / 0 / 6331 | $0.000000 |

**3. Verification** (`verify`, independent model + code; blind to the enricher's labels).

In the declared verification sample (lowest SHA-256(seed + ':' + review_id) among distinct completed texts; seed `berkeley-fa-2026-insight-v1`, 2000 of 152363 distinct completed texts). The verifier saw only the review text, in its own batch request, never the enricher's labels.

Verifier `haiku@n/a|verify-v1|cfg-26c97bdddf`, request `req-20261013T015230781792-0eeb575b` (run `run-20261012T233254.463Z-c2b5`), confidence high:

| Field | Enricher (record) | Verifier (independent) | Code comparison |
|---|---|---|---|
| topic | billing | billing | agree |
| intent | complaint | complaint | agree |
| severity | 3 | 4 | disagree (abs. difference 1) |
| sentiment | -0.5 | -0.5 | abs. difference 0.0 (within tolerance 0.5) |

Result: disagrees on severity (saved in `verification/report.json`; disagreements are listed in `verification/disagreements.csv`, and the enricher's labels are never overwritten).

**4. Issue membership** (`group`, code; the model only names issues).

`membership.csv`: `billing.premium_only,02ccf42f-6ef1-44e2-ad96-5c8972e856d5` -> issue **Premium-only restrictions** (named by `cache`).

**5. Ranking** (`rank`, code; reproducible with `python -m insight rank --run-dir <run> --check`).

Rank **1**: complaint_count 18016, severity_sum 52577, mean_severity 2.918350, priority_score 52577 (this review contributes severity 3).

**6. Memo** (`memo`, model + code; the model writes tokens, code fills each as `value (claim ID)`).

Claims in `claims.csv` for this issue: `C01` complaint_count = 18016, `C02` severity_sum = 52577, `C03` mean_severity = 2.918350, `C04` priority_score = 52577.

Where `memo.md` cites them (memo source: model):

- `C01` (complaint_count) is printed as `18016 (C01)` in: Recommendation, Next-quarter actions #1
- `C02` (severity_sum) is printed as `52577 (C02)` in: Recommendation, Next-quarter actions #1, Why #1, Limitations #2
- `C03` (mean_severity) is printed as `2.918350 (C03)` in: Recommendation, Why #1
- The memo's issue table prints all four values with their claim IDs (rank 1 row), and `memo_tokens.csv` lists every token ID the memo uses.

This review is not quoted in the memo evidence pack; it contributes to the issue's numbers above.

## B. An ambiguous or failed case and its recorded handling

Review `00046c11-dc53-495f-a874-6a9f1a0445dc` (run `final-200k`).

**1. Source row** (`ingest`, code). Six original fields, unchanged; row hash = SHA-256 of their compact JSON.

| Field | Value |
|---|---|
| review_text | In the ozone and living life. |
| review_rating | 4 |
| review_likes | 0 |
| app_version | 8.8.76.667 |
| review_timestamp | 2023-10-07 22:10:42 |
| source_sha256 | `62456ac0ad890d076de964084bec1f26ade15b9369d5cfe6da27410e15fa5985` |

**2. Enrichment** (`enrich`, model + code). Only `review_text` was sent.

| Field | Value |
|---|---|
| status | completed (labeled by **fallback1**) |
| topic / subtopic | other / general |
| intent | unclear |
| severity | 1 (No reported problem: praise, neutral/unclear content, or a pure feature request) |
| sentiment | 0.0 |
| evidence_quote | "In the ozone and living life." (exact substring: True) |
| entities (code-matched) | - |
| needs_review | True |
| cache_source_id | - |
| label_config | `gpt-6-luna@none>gpt-6-luna@low(10%)>sonnet@low(0.25%)\|enrich-v2\|schema-v2\|cfg-f6337dc790` |
| difficulty signals | model flagged the review as ambiguous |
| primary answer before fallback | issue other_general, intent unclear, severity 1 |

Model calls that carried this review (every attempt is logged before it is sent):

| request_id | role / tier | phase | model (reported) | tier / billing | outcome | in / cached / out tokens | billed |
|---|---|---|---|---|---|---|---:|
| `req-20261013T005019965532-ec8de51d` | enrich / primary | resume | `gpt-6-luna` (gpt-6-luna) | flex / api | succeeded | 4247 / 2368 / 1612 | $0.000532 |
| `req-20261013T010852242040-858b140c` | enrich / fallback1 | resume | `gpt-6-luna` (gpt-6-luna) | flex / api | succeeded | 2228 / 2197 / 35 | $0.000022 |

**3. Verification** (`verify`, independent model + code; blind to the enricher's labels).

Not in the declared random verification sample.

**4. Issue membership** (`group`, code; the model only names issues).

Not a member of any issue (only completed complaint/cancellation records are grouped).

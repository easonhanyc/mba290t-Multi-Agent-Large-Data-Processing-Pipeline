# One review traced end to end

Generated from saved artifacts by `python -m insight trace` (no model calls).

## A. Traced review (top issue, verified, quoted in the memo)

Review `674b2fb0-f4a5-430d-9241-ee3ea348a30e` (run `final-200k`).

**1. Source row** (`ingest`, code). Six original fields, unchanged; row hash = SHA-256 of their compact JSON.

| Field | Value |
|---|---|
| review_text | I really don't want to give Spotify 1 star for real but this made me very upset. For like 3 to 4 days before I was listening songs and today I really shocked to see that ..now I have to buy premium to put the song again and I can't even play the song now . Today morning it was my last time I listen to music in Spotify. What are you doing Spotify this will decrease your download and also you are ge... |
| review_rating | 1 |
| review_likes | 0 |
| app_version | 8.8.76.667 |
| review_timestamp | 2023-10-10 14:28:01 |
| source_sha256 | `5621660d8d5bc44eb912c39a357f35755750f7a3fe5537cc3cef8e81929abf59` |

**2. Enrichment** (`enrich`, model + code). Only `review_text` was sent.

| Field | Value |
|---|---|
| status | completed (labeled by **primary**) |
| topic / subtopic | billing / premium_only |
| intent | complaint |
| severity | 4 (A clearly blocked core task, such as inability to log in or play music) |
| sentiment | -1.0 |
| evidence_quote | "For like 3 to 4 days before I was listening songs and today I really shocked to see that ..now I have to buy premium to put the song again and I can't even play the song now ." (exact substring: True) |
| entities (code-matched) | premium, downloads |
| needs_review | False |
| cache_source_id | - |
| label_config | `gpt-6-luna@none>gpt-6-luna@low(10%)>sonnet@low(0.25%)|enrich-v2|schema-v2|cfg-f6337dc790` |

Model calls that carried this review (every attempt is logged before it is sent):

| request_id | role / tier | phase | model (reported) | tier / billing | outcome | in / cached / out tokens | billed |
|---|---|---|---|---|---|---|---:|
| `req-20261013T005112354170-0e20c394` | enrich / primary | resume | `gpt-6-luna` (gpt-6-luna) | flex / api | succeeded | 5348 / 2368 / 1667 | $0.000615 |
| `req-20261013T020350269465-6822f75e` | group / group | resume | `sonnet` (claude-sonnet-5) | subscription / subscription | succeeded | 2036 / 0 / 149 | $0.000000 |

**3. Verification** (`verify`, independent model + code; blind to the enricher's labels).

Not in the declared random verification sample.

**4. Issue membership** (`group`, code; the model only names issues).

`membership.csv`: `billing.premium_only,674b2fb0-f4a5-430d-9241-ee3ea348a30e` -> issue **Premium-only restrictions** (named by `cache`).

**5. Ranking** (`rank`, code; reproducible with `python -m insight rank --run-dir <run> --check`).

Rank **1**: complaint_count 18016, severity_sum 52577, mean_severity 2.918350, priority_score 52577 (this review contributes severity 4).

**6. Memo** (`memo`, model + code; numbers are tokens filled by code).

Claims in `claims.csv` for this issue: `C01` complaint_count = 18016, `C02` severity_sum = 52577, `C03` mean_severity = 2.918350, `C04` priority_score = 52577.
This review is quoted in the memo evidence pack and cited by the memo model.

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
| label_config | `gpt-6-luna@none>gpt-6-luna@low(10%)>sonnet@low(0.25%)|enrich-v2|schema-v2|cfg-f6337dc790` |
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

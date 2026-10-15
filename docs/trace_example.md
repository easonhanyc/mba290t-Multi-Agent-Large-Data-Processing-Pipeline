# One review traced end to end

Generated from saved artifacts by `python -m insight trace` (no model calls).

## A. Traced review (issue rank 3, verified, not quoted in the memo)

Review `c5f4ab7f-5a94-43e8-9e80-9d572e0da060` (run `final-200k-v2`).

Chosen by a declared rule: among the members of the recommended area's largest issue (`usability.ads`) that are in the verification sample and on which the verifier agrees, the lowest SHA-256(`"trace-v1:" + review_id`). Regenerate: `python -m insight trace --run-dir runs/final-200k-v2 --review-id c5f4ab7f-5a94-43e8-9e80-9d572e0da060 --auto --out docs/trace_example.md`.

**1. Source row** (`ingest`, code). Six original fields, unchanged; row hash = SHA-256 of their compact JSON.

| Field | Value |
|---|---|
| review_text | Over ad |
| review_rating | 1 |
| review_likes | 0 |
| app_version | 8.7.32.1554 |
| review_timestamp | 2022-09-07 19:54:07 |
| source_sha256 | `059c5d0a196aacbb553e66962152578e7f4fc8e3d12023ca551ce4ecf0baa27d` |

**2. Enrichment** (`enrich`, model + code). Only `review_text` was sent.

| Field | Value |
|---|---|
| status | completed (labeled by **primary**) |
| topic / subtopic | usability / ads |
| intent | complaint |
| severity | 2 (Dislike, generic criticism, minor annoyance, or a cosmetic issue; no supported functional loss) |
| sentiment | -0.5 |
| evidence_quote | "Over ad" (exact substring: True) |
| entities (code-matched) | ads |
| needs_review | False |
| cache_source_id | - |
| label_config | `gpt-6-luna@low>gpt-6-luna@low(1.5%)>sonnet@low(0.25%)\|enrich-v2\|schema-v2\|cfg-52c5333247` |

Model calls that carried this review (every attempt is logged before it is sent):

| request_id | role / tier | phase | model (reported) | tier / billing | outcome | in / cached / out tokens | billed |
|---|---|---|---|---|---|---|---:|
| `req-20261014T234853040704-379da68c` | enrich / primary | resume | `gpt-6-luna` (gpt-6-luna) | flex / api | succeeded | 4219 / 2368 / 2656 | $0.000791 |
| `req-20261015T032228424404-5893003d` | verify / verify | resume | `haiku` (claude-haiku-4-5-20251001) | subscription / subscription | succeeded | 4454 / 0 / 6873 | $0.000000 |

**3. Verification** (`verify`, independent model + code; blind to the enricher's labels).

In the declared verification sample (lowest SHA-256(seed + ':' + review_id) among distinct completed texts; seed `berkeley-fa-2026-insight-v1`, 2000 of 152363 distinct completed texts). The verifier saw only the review text, in its own batch request, never the enricher's labels.

Verifier `haiku@n/a|verify-v1|cfg-26c97bdddf`, request `req-20261015T032228424404-5893003d` (run `run-20261014T234005.530Z-f920`), confidence medium:

| Field | Enricher (record) | Verifier (independent) | Code comparison |
|---|---|---|---|
| topic | usability | usability | agree |
| intent | complaint | complaint | agree |
| severity | 2 | 2 | agree |
| sentiment | -0.5 | -0.5 | abs. difference 0.0 (within tolerance 0.5) |

Result: agrees on every field (saved in `verification/report.json`; disagreements are listed in `verification/disagreements.csv`, and the enricher's labels are never overwritten).

**4. Issue membership** (`group`, code; the model only names issues).

`membership.csv`: `usability.ads,c5f4ab7f-5a94-43e8-9e80-9d572e0da060` -> issue **Ad interruptions** (named by `cache`).

**5. Ranking** (`rank`, code; reproducible with `python -m insight rank --run-dir <run> --check`).

Rank **3**: complaint_count 11233, severity_sum 23235, mean_severity 2.068459, priority_score 23235 (this review contributes severity 2).

**6. Memo** (`memo`, model + code; the model writes tokens, code fills each as `value (claim ID)`).

Claims in `claims.csv` for this issue: `C09` complaint_count = 11233, `C10` severity_sum = 23235, `C11` mean_severity = 2.068459, `C12` priority_score = 23235.

Where `memo.md` cites them (memo source: model):

- `C09` (complaint_count) is printed as `11233 (C09)` in: Recommendation, Next-quarter actions #1, Why #2
- `C10` (severity_sum) is printed as `23235 (C10)` in: Recommendation, Next-quarter actions #1, Why #2
- The memo's issue table prints all four values with their claim IDs (rank 3 row), and `memo_tokens.csv` lists every token ID the memo uses.

This review is not quoted in the memo evidence pack; it contributes to the issue's numbers above.

## B. An ambiguous or failed case and its recorded handling

Review `00005c81-8189-4df7-9115-b750863804a7` (run `final-200k-v2`).

**1. Source row** (`ingest`, code). Six original fields, unchanged; row hash = SHA-256 of their compact JSON.

| Field | Value |
|---|---|
| review_text | 👍🕺💃 |
| review_rating | 5 |
| review_likes | 0 |
| app_version |  |
| review_timestamp | 2023-11-01 18:01:07 |
| source_sha256 | `d04ac4b2c9f2f16327161d1ceccb00d2e9168cacdee8fe2e5e11d592fb0048c8` |

**2. Enrichment** (`enrich`, model + code). Only `review_text` was sent.

| Field | Value |
|---|---|
| status | completed (labeled by **fallback1**) |
| topic / subtopic | other / general |
| intent | unclear |
| severity | 1 (No reported problem: praise, neutral/unclear content, or a pure feature request) |
| sentiment | 0.5 |
| evidence_quote | "👍🕺💃" (exact substring: True) |
| entities (code-matched) | - |
| needs_review | True |
| cache_source_id | - |
| label_config | `gpt-6-luna@low>gpt-6-luna@low(1.5%)>sonnet@low(0.25%)\|enrich-v2\|schema-v2\|cfg-52c5333247` |
| difficulty signals | model flagged the review as ambiguous |
| primary answer before fallback | issue other_general, intent unclear, severity 1 |

Model calls that carried this review (every attempt is logged before it is sent):

| request_id | role / tier | phase | model (reported) | tier / billing | outcome | in / cached / out tokens | billed |
|---|---|---|---|---|---|---|---:|
| `req-20261015T030805262578-ecafcf21` | enrich / primary | resume | `gpt-6-luna` (gpt-6-luna) | flex / api | succeeded | 4023 / 2368 / 2129 | $0.000647 |
| `req-20261015T031450010087-d2c4c12c` | enrich / fallback1 | resume | `gpt-6-luna` (gpt-6-luna) | flex / api | succeeded | 2228 / 2197 / 35 | $0.000022 |

**3. Verification** (`verify`, independent model + code; blind to the enricher's labels).

Not in the declared random verification sample.

**4. Issue membership** (`group`, code; the model only names issues).

Not a member of any issue (only completed complaint/cancellation records are grouped).

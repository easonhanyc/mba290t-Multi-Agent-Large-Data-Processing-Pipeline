# Golden-set evaluation and error analysis

50 reviews labelled by hand by Eason (conventions and the conversion from his workbook: `docs/labels.md`, `evals/golden/convert_labels.py`). Every setup below labelled the same 50 texts; missing predictions would count as wrong (there were none). Fifty cases are a diagnostic: a few cases move a figure by several points.

## Per-field agreement

| Setup | Topic | Intent | Severity exact | All three | Severity MAE | Sentiment within 0.5 | Flags needs_review (human: 6) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Luna, effort none (production primary) | 74% | 70% | 72% | 46% | 0.32 | 86% | 5 |
| Luna, effort low (production fallback1) | 80% | 76% | 76% | 54% | 0.24 | 86% | 4 |
| OpenAI Decisions (typed classifier) | 76% | 74% | 68% | 48% | 0.34 | 90% | 26 |
| Final 200k run (none + low fallback on flagged) | 76% | 74% | 76% | 48% | 0.24 | 86% | 5 |

Effort low vs effort none on 'all three correct': low alone right on 4 reviews, none alone on 0; exact McNemar two-sided p = 0.125. The direction favours effort low, but the difference is not statistically reliable at n = 50.

**Decision.** The predeclared rule (best golden 'all three' agreement within the cost cap) points to effort low as the primary. The golden labels were finished after the final run, which used effort none for the batched primary and effort low for the 13,639 flagged texts (fallback1, cap 10%). Given the non-significant gap and that most disagreements below are labelling-convention differences, the final run was kept and this is disclosed rather than re-run (decided with Eason on 2026-10-13).

## Where the final run disagrees with the human labels

- **topic** (12 of 50): other -> usability x3, usability -> billing x2, other -> catalog x2, support -> playback x1, usability -> other x1, billing -> other x1, playback -> billing x1, billing -> usability x1
- **intent** (13 of 50): request -> complaint x7, praise -> unclear x2, praise -> complaint x1, request -> unclear x1, unclear -> complaint x1, complaint -> unclear x1
- **severity** (12 of 50): 4 -> 3 x5, 2 -> 1 x4, 2 -> 3 x2, 3 -> 2 x1

Patterns:

1. **Request vs complaint (7 reviews).** Eason labels a review that reports a problem and asks for a fix as *request*; the contract precedence (complaint before request) that the models follow makes it *complaint*. Excluding these, final-run intent agreement is 37/43 = 86%. This is a convention difference, kept on purpose and documented.
2. **Praise naming a feature (4 reviews).** Eason maps praise to topic *other*; the contract rule the models apply picks the first praised feature (recommendations, ads, the catalog).
3. **Blocked vs degraded severity (human 4, model 3).** Intermittent stops, lyrics that sometimes fail to load, and free-tier limits on choosing or rewinding songs: Eason reads them as a blocked core task, the models as the rubric's level 3 ('a degraded or restricted function').
4. **Remaining intent misses (6).** Four are non-English, slang or name-only texts ('Lhat ng song nasa spotify', 'Bheekhmangon', a name with 'Unconditional love', an unclear sentence about a free dollar); one is a support story that ends well (human praise, model complaint); one mixes a boycott with religion (human unclear, model complaint).

## Would combining the typed classifier with Luna help?

| Field | Luna | Decisions | Models agree | Accuracy when they agree | Combined rule |
|---|---:|---:|---:|---:|---:|
| topic | 74% | 76% | 96% | 77% | 74% |
| intent | 70% | 74% | 92% | 74% | 74% |
| severity | 72% | 68% | 84% | 76% | 70% |

The two models agree on most texts and share the same misses, so a cross-check would rarely catch an error here; the combined rule does not beat Luna alone. Together with the Decisions beta's 50 requests/day limit, this is why the hybrid backend is not used at scale (`docs/model_choice.md`).

## Other checks

- Evidence quotes: every final-run quote is an exact substring of its review (50/50).
- Entities: 0 predicted entities not found in the text. Eason's entities are feature descriptions in his own words, so they are compared case by case below.
- needs_review vs human: {'human=False,model=False': 41, 'human=False,model=True': 3, 'human=True,model=False': 4, 'human=True,model=True': 2}.

Case-by-case list of every disagreement (with the human entities and quotes): `results_disagreements.md`.

# Golden-set evaluation and error analysis

50 reviews labelled by hand by Eason (conventions and the conversion from his workbook: `docs/labels.md`, `evals/golden/convert_labels.py`). Human labels are read only by the scorer; they never reach a prompt. Missing predictions would count as wrong (there were none). Fifty cases are a diagnostic: one case moves a figure by 2 points.

## 1. Choosing the setup

Each candidate enriched the same 50 texts (`runs/golden-*`, `scripts/live.sh golden-candidates`):

| Setup | Topic | Intent | Severity exact | All three | Severity MAE | Sentiment within 0.5 | Flags needs_review |
|---|---:|---:|---:|---:|---:|---:|---:|
| Luna, effort none | 74% | 70% | 72% | 46% | 0.32 | 86% | 5 |
| Luna, effort low | 80% | 76% | 76% | 54% | 0.24 | 86% | 4 |
| OpenAI Decisions (typed classifier) | 76% | 74% | 68% | 48% | 0.34 | 90% | 26 |

**Rule (declared before scoring):** the best 'all three correct' within the cost cap. **Luna, effort low** wins (54%). Against effort none, effort low alone was right on 4 reviews and effort none alone on 0 (exact McNemar two-sided p = 0.125), so the direction is clear but the gap is small at n = 50.

The final run uses that candidate's exact configuration: `label_config` `gpt-6-luna@low>gpt-6-luna@low(1.5%)>sonnet@low(0.25%)|enrich-v2|schema-v2|cfg-52c5333247` on every record, the same string as `runs/golden-luna-low` (`config/pipeline.toml`: `effort = "low"`, `max_output_tokens_per_review = 200`, fallback1 `max_fraction = 0.015`). The first final run, made before these labels existed with effort none, is kept as superseded evidence (`runs/final-200k`). Because the golden set chose the setup, the final run's golden scores below are optimistic (section 3).

## 2. Final run on the golden 50

| Setup | Topic | Intent | Severity exact | All three | Severity MAE | Sentiment within 0.5 | Flags needs_review |
|---|---:|---:|---:|---:|---:|---:|---:|
| Final run (the effort-low candidate's configuration) | 78% | 76% | 74% | 48% | 0.26 | 88% | 3 |
| Superseded first final run (effort none, effort low on flagged texts) | 76% | 74% | 76% | 48% | 0.24 | 86% | 5 |

The same configuration scored 54% 'all three correct' as a candidate and 48% in the final run: the final run alone was right on 0 reviews and the candidate run alone on 3 (exact McNemar p = 0.250). Model answers are not deterministic, and the batches differed: the candidate run sent the 50 golden texts in 1 request, the final run spread them over 39 requests among other reviews (the rest reused the label of an identical text; committed `grading/calls.jsonl(.gz)` of each run). Against the superseded effort-none run the final run alone was right on 1 reviews and the superseded run alone on 1 (p = 1.000). On these 50 cases the setups are within noise of each other; the rule picked the candidate setup, and this is the measured result of running it.

## 3. What these scores can and cannot show

The golden 50 chose the setup, so the final run's golden scores carry a small selection bias: among three candidates, the one that did best on these 50 reviews was kept. No fresh human-labelled set was added after the choice. Two checks that played no part in the choice cover the final run itself:

- **Blind verifier, declared random sample** (2,000 distinct texts, Claude Haiku, never sees the enricher's answer): topic 82%, intent 92%, severity exact 78% agreement (`runs/final-200k-v2/verification/report.json`; disagreements analysed in `evals/verification/disagreement_analysis.md`). The verifier is another model, not ground truth.
- **Evidence quotes on a declared random sample of the final run** (section 5): whether each quote supports its labels.

## 4. Where the final run disagrees with the golden labels

- **topic** (11 of 50): other -> usability x3, other -> catalog x3, usability -> other x2, support -> playback x1, usability -> billing x1, billing -> other x1
- **intent** (12 of 50): request -> complaint x7, praise -> complaint x1, request -> unclear x1, praise -> unclear x1, unclear -> complaint x1, complaint -> unclear x1
- **severity** (13 of 50): 4 -> 3 x5, 2 -> 1 x4, 3 -> 2 x3, 2 -> 3 x1

Patterns:

1. **Request vs complaint (7 reviews).** Eason labels a review that reports a problem and asks for a fix as *request*; the contract precedence the models follow (complaint before request) makes it *complaint*. Excluding these, intent agreement is 38/43 = 88%. A documented convention difference, kept on purpose.
2. **Praise naming a feature (5 reviews).** Eason maps general praise to topic *other*; the contract rule the models apply picks the first praised feature.
3. **Blocked vs degraded severity (5 reviews, human 4, model 3).** Eason reads intermittent failures and free-tier limits as a blocked core task; the models apply level 3, 'a degraded or restricted function'.
4. **Other intent misses (5):** `283b5843` 'Beth, we all got to give me a free dollar to go with 3 months, bro I c' (human complaint, model unclear); `36609c5c` 'Bheekhmangon' (human request, model unclear); `723f07de` 'Update: I reached out to Spotify Support and with some help from Sarah' (human praise, model complaint); `8cc4fad4` 'I hate this app and sweden .I love islam' (human unclear, model complaint); `f4c8146a` 'Unconditional love, Stoli Canales' (human praise, model unclear).

## 5. Evidence quotes, entities and the review flag

- Exact substring (code): 50/50 final-run quotes.
- Unsupported entities: 0 predicted entities not found in the text. Eason's entities are feature descriptions in his own words, so they are compared case by case in `results_disagreements.md`.
- needs_review vs human: {'human=False,model=False': 43, 'human=False,model=True': 1, 'human=True,model=False': 4, 'human=True,model=True': 2}.
- Does the quote support the labels (golden 50, final run's quotes, blind judge): topic 92%, intent 96%, severity 98% supported; all three 88%; the model quoted Eason's evidence sentence in 47 of 50 (multi-sentence reviews 9/12).
- Does the quote support the labels (golden 50, Eason's quotes, blind judge): topic 92%, intent 80%, severity 90% supported; all three 70%.
- Does the quote support the labels (random final-run sample, blind judge): topic 94%, intent 97%, severity 97% supported; all three 89%.
- Method and every quote the judge did not accept: `evals/quote_support/report.md`.

## 6. Would combining the typed classifier with Luna help?

| Field | Luna (effort none) | Decisions | Models agree | Accuracy when they agree | Combined rule |
|---|---:|---:|---:|---:|---:|
| topic | 74% | 76% | 96% | 77% | 74% |
| intent | 70% | 74% | 92% | 74% | 74% |
| severity | 72% | 68% | 84% | 76% | 70% |

The two models agree on most texts and share the same misses, so a cross-check would rarely catch an error; the combined rule does not beat Luna alone. With the Decisions beta's 50 requests/day limit, this is why the hybrid backend is not used at scale (`docs/model_choice.md`).

Case-by-case list of every disagreement (with the human entities and quotes): `results_disagreements.md`.

# Verifier disagreements on the final run: what they are and what they imply

Written 2026-10-15 from the saved files of `runs/final-200k-v2`, offline: no model calls, and no label was changed.
Every count in sections 1 and 4 is computed by `evals/verification/disagreement_counts.py`
([disagreement_counts.json](disagreement_counts.json)), which also lists the sampled reviews read in sections 2 and 3.
**The verdicts in sections 2 and 3 are the AI assistant's reading of each review against the shared rubric
(`docs/labels.md`, `prompts/llm_enrich_v2.md`, `prompts/verify_v2.md`). They are not human labels and not ground truth.**

The verifier is Claude Haiku via `claude -p`. It labels a declared random sample of distinct texts blind: it never
sees the enricher's answer (`runs/final-200k-v2/verification/report.json`; `sample.json`: 10% of 152,363 distinct
completed texts, capped at 2,000, chosen by lowest SHA-256 of seed + review_id; the same 2,000 texts as in the
superseded run). Its topic is the contract topic only, with no subtopic, so `billing.premium_only` versus usability
can only be compared at the topic level.

## 1. Counts

The sample has 2,000 texts. They agree on topic for 1,635, intent for 1,830, exact severity for 1,565 and sentiment
within 0.5 for 1,980. 762 texts differ on at least one field, all listed with both labels in `disagreements.csv`;
there were 0 verifier failures. (The superseded effort-none run also had 762 disagreements on the same sample, but
207 of them are different texts.)

**By field.** 570 of the 762 differ on exactly one field: severity only 269, topic only 255, intent only 44,
sentiment only 2. Severity differs on 435 texts: 397 by one point, 35 by two and 3 by three.

**By direction (enricher -> verifier), top patterns:**

| Topic (365) | n | Intent (170) | n | Severity (435) | n |
|---|---:|---|---:|---|---:|
| other -> catalog | 42 | complaint -> unclear | 37 | 3 -> 4 | 163 |
| catalog -> other | 42 | praise -> unclear | 33 | 3 -> 2 | 85 |
| usability -> other | 38 | complaint -> request | 25 | 2 -> 3 | 61 |
| catalog -> usability | 30 | complaint -> cancellation | 16 | 2 -> 1 | 59 |
| billing -> usability | 23 | cancellation -> complaint | 13 | 1 -> 2 | 19 |
| other -> playback | 21 | unclear -> complaint | 11 | 2 -> 4 | 17 |
| playback -> usability | 21 | complaint -> praise | 10 | 3 -> 1 | 14 |

The verifier gives the higher severity in 267 cases and the lower one in 168. By the enricher's issue, the largest
topic patterns are `other.general` -> catalog (42), `other.general` -> playback (21), `billing.premium_only` ->
usability (21), `other.general` -> usability (17) and `billing.premium_only` -> playback (15). 68 of the 163 severity
3 -> 4 cases are `billing.premium_only`.

**Where they fall:**

- **Enricher tier.** Fallback1 labels (the flagged texts, one review per request) agree with the verifier on all
  three fields for 30 of 41 texts; primary labels for 1,210 of 1,959 (`by_enricher_tier`).
- **needs_review.** Only 40 of the 762 disagreements carry the enricher's `needs_review` flag, against 186 of the
  2,000 sampled texts, so the flag does not pick out the texts the verifier disputes.
- **Verifier confidence.** On the 762 the verifier was high-confidence for 581, medium for 121 and low for 60.
- **Ranking.** 545 of the 762 have enricher intent complaint or cancellation, so only these can affect the ranking.

## 2. Random sample of 20 disagreements

The 20 disagreements with the lowest SHA-256(`"disagreement-review-v1:" + review_id`). Text is abridged.
E = enricher (issue / intent / severity), V = verifier (topic / intent / severity).

| # | review_id | Text (abridged) | E | V | Reading against the rubric | Verdict |
|---|---|---|---|---|---|---|
| 1 | `fbf4ea57` | Remove from Play Store.. Terrible update | usability.navigation / complaint / 2 | other / complaint / 2 | No feature named: generic criticism is `other.general` | Verifier |
| 2 | `49ceee78` | 🔥🔥🔥🔥🔥🔥🔥🔥 | other.general / praise / 1 | other / unclear / 1 (low) | Emoji only; fire usually signals approval, but nothing is said | Ambiguous |
| 3 | `a107df8f` | Repeating songs and can't skip song | usability.library / complaint / 3 | playback / complaint / 3 | Repeat controls (usability) or the wrong song playing (playback) | Ambiguous |
| 4 | `92f8bc27` | please let us listen song.please For a whole day. | playback.stops / request / 1 | other / request / 1 (low) | Probably a free-tier listening limit, but nothing is named; a request, not ranked | Ambiguous |
| 5 | `1801ff65` | No words !!!!! | other.general / unclear / 1 (fallback1) | other / praise / 1 | Could be awe or disgust; unclear fits | Enricher |
| 6 | `fbd160d9` | 1 star for the sheer greed ... taking away the shuffle button and back button | billing.premium_only / complaint / 3 | usability / complaint / 3 | "Greed" and "rip me off" make the paywall the subject | Enricher (lean) |
| 7 | `319be3f6` | not letting me play music unless it's on shuffle ... won't let me skip | usability.library / complaint / 3 | usability / complaint / 4 | Music still plays on shuffle: a restricted function (3). Premium is not named, and the enricher no longer calls it premium_only | Enricher |
| 8 | `5a2dec43` | Horrible just horrible | other.general / complaint / 2 | other / complaint / 1 | Generic criticism is a complaint at severity 2 | Enricher |
| 9 | `ae77f63d` | ... could be easier to make playlist ... finding new (different) music | catalog.recommendations / request / 1 | usability / request / 1 | Playlist-making or discovery; a request, not ranked | Ambiguous |
| 10 | `fbfc0e07` | Where's the Songs Played history icon gone? | usability.navigation / complaint / 3 | usability / complaint / 2 | A moved control: annoyance (2) or a restricted function (3) | Ambiguous |
| 11 | `edb5ba30` | 100000\10 | other.general / praise / 1 | other / unclear / 1 | A rating far above ten is praise | Enricher |
| 12 | `05c07591` | Cry baby app literally they sold themselves for money ... | other.general / complaint / 2 | other / unclear / 1 | Rambling, but it opens with generic criticism | Enricher (lean) |
| 13 | `2caa404c` | so nice I can listen all the songs I want | other.general / praise / 1 | catalog / praise / 1 | Song availability is a specific praised feature (catalog) | Verifier (lean) |
| 14 | `4adf18ae` | They need to stop updating it | usability.other / complaint / 2 | other / complaint / 2 | No specific defect | Verifier |
| 15 | `50b6890a` | This app can't miraculously just stop working when you trying to reinstall it ... | playback.crash / complaint / 4 | other / unclear / 1 (low) | Garbled, but it reports the app no longer working | Enricher (topic, intent) |
| 16 | `b3025eee` | ... please add the lyrics download option cause in offline I can't see the lyrics | catalog.lyrics / request / 1 | downloads / request / 1 | Lyrics or offline; a request, not ranked | Ambiguous |
| 17 | `c47e6613` | it wont let me play my song on my playlist ... it put on suggested songs | playback.stops / complaint / 3 | usability / complaint / 4 | Free-tier behaviour with Premium not named; music still plays (3) | Split: topic ambiguous, E severity |
| 18 | `638a23cf` | Super buggy these days | other.general / complaint / 2 | playback / complaint / 2 | No specific defect named | Enricher |
| 19 | `e64c62fa` | ... Only problem is the glitches. | playback.crash / complaint / 3 | playback / complaint / 2 | Unspecified glitches with no functional loss: 2 | Verifier |
| 20 | `715209a5` | Free and a ad every 30 mins great selection | catalog.search / praise / 1 | other / praise / 1 | "Great selection" is catalog, but the first point is the free plan; search is not mentioned | Ambiguous |

**Tally (assistant's reading):** the enricher fits the rubric better on 8, the verifier on 4, 1 is split and 7 are
genuinely ambiguous. 8 of the 20 (#2, #4, #5, #9, #11, #13, #16, #20) are praise, requests or unclear text, so their
topic has no effect on the ranking. Twelve of these 20 texts were also in the superseded run's random 20, and three
changed enricher labels in the direction of the rubric: `319be3f6` was premium_only and is now usability.library (only
severity still differs), `c47e6613` was premium_only and is now playback.stops, and `638a23cf` ("Super buggy") was
playback.crash and is now other.general.

## 3. Two targeted looks

### Premium-only versus usability/playback (10 of the 41 topic disagreements on `billing.premium_only`)

The lowest SHA-256(`"premium-boundary-v1:" + review_id`), excluding the random 20.

| review_id | Text (abridged) | E -> V topic / severity | Reading |
|---|---|---|---|
| `041661bf` | when I want to play 1 specific it will pick something different ... I ain't dealing with this much longer | billing -> playback / 3 -> 4 | Premium not named; could be free-tier behaviour or a bug: ambiguous. Music plays (3). Threat to leave: cancellation (E) |
| `2189ca78` | the not-premium version includes much advertisements and cannot be played in the background | billing -> usability / 3 -> 2 | The paywall is the complaint: E's topic and 3 fit |
| `5da7e835` | liked songs play about 10 seconds on repeat ... plays a song I never heard of | billing -> playback / 3 -> 4 | Premium not named; could be a bug: ambiguous |
| `8aff78ef` | plays a different song ... this glitch is only affecting accounts that are free | billing -> playback / 3 -> 3 | The customer ties it to free accounts but calls it a glitch: ambiguous, lean E |
| `75436e8f` | no longer able to skip songs or play what I wanted ... At least I can pay for Pandora | billing -> usability / 3 -> 4 | Reads as an ended trial, and paying is named: E's topic (lean); restricted (3) |
| `202f6815` | cannot rewind a song or replay it. This is a pathetic attempt to force everyone to buy their premium subscription | billing -> playback / 3 -> 4 | Premium named: E's topic; restricted (3) |
| `b4d75088` | I have to pay to skips songs pluse I clicked a song didn't play the song | billing -> playback / 3 -> 4 | Paying named: E's topic; restricted (3) |
| `c45cd68e` | I wish you could skip the songs and have no ads ... premium is not worth the money | billing -> usability / 3 -> 3 | Skip limit plus Premium named: E |
| `8d7a3b32` | Why remove the basic features, there's not even a point of owning this app now | billing -> other / 3 -> 3 | Nothing specific and Premium not named: the literal rule favours V |
| `72cc3757` | EVEN AFTER WATCHING THEIR ADVERTISEMENTS 10X it picks a different song ... unless you pay the monthly | billing -> usability / 3 -> 4 | Paying named: E's topic; music plays (3) |

Seven of the 10 name Premium, paying or the free plan, and in six of them the enricher's topic fits; the other three
never mention payment (two ambiguous, one where the literal rule favours the verifier).

### Severity 3 -> 4 (10 of the 163)

The lowest SHA-256(`"severity-3-4-v1:" + review_id`), excluding the random 20; `75436e8f` also appears above.

| review_id | Text (abridged) | E issue | Reading |
|---|---|---|---|
| `75436e8f` | no longer able to skip songs or play what I wanted | billing.premium_only | Restricted, music still plays: 3 (E) |
| `e3a310a0` | every feature is available in premium version if I play any song it automatically play another song | billing.premium_only | 3 (E) |
| `d12bfaf6` | can't forward the song and can't skip the song more then 6 times an hour ... can't play a specific song | billing.premium_only | 3 (E) |
| `82218a14` | Can't even add a song to queue or even play the previous song even for that you have to pay! | billing.premium_only | 3 (E) |
| `297e9f92` | We can't be skip song even listen previous song | billing.premium_only | 3 (E) |
| `4f17a93f` | [Premium user] havent been able to listen to more then one song with out picking up my phone | playback.stops | Degraded: 3 (E) |
| `0797ceb1` | all things are premium no one can listen to his/her choice song | billing.premium_only | 3 (E) |
| `c93533d6` | Every time i pick a song it takes another random song. | playback.stops | Borderline: music plays, but never the chosen song |
| `ace9389b` | Not able to skip songs. Plus To many advertisements. | playback.stops | 3 (E); a free-user skip limit is premium_only in `docs/labels.md`, so V's billing topic fits better than E's playback.stops |
| `0c8af425` | Maximum of the features are disabled and only enabled if you have premium | billing.premium_only | 3 (E) |

In 9 of these 10 the enricher's 3 matches the written scale ("a degraded or restricted function; some use or
workaround remains"); one is borderline. The verifier reads "I cannot play the song I choose" as a blocked core task (4).

## 4. What this implies

1. **Most disagreements are boundary calls, not gross errors.** 570 of 762 differ on one field, 397 of the 435
   severity differences are one point, and the verifier is low-confidence on only 60. The models disagree
   confidently and systematically at a few rubric boundaries.

2. **The premium-only boundary narrowed in the final setup.** `billing.premium_only` has 203 texts in the sample, and
   the verifier puts 41 of them (20%) in another topic: usability 21, playback 15, other 5. In the superseded
   effort-none run the same check gave 71 of 235 (30%). Using the payment-word pattern
   `premium|subscri|\bpa(y|id|ying)\b|\bfree\b|\bbuy\b|money|trial|\$` (case-insensitive), 15 of the 41 contain none of
   these words, against 13 of the 162 premium-only texts where the verifier agrees (superseded run: 47 of 71 and 13 of
   164). The effort-low enricher applies the written rule ("a feature the customer says is locked behind Premium") more
   literally.
   - **Full run.** 2,456 of the 15,763 `billing.premium_only` members contain none of the words; their severity sum is
     7,283 of 46,246 (superseded run: 4,785 of 18,016, severity 14,239).
   - **Sensitivity, arithmetic only** (`runs/final-200k-v2/analysis/premium_only_sensitivity.json`): without those
     2,456, billing/support's severity sum would fall from 52,551 to 45,268, below usability (52,983) and
     playback/performance (48,060). It is an upper bound, not a relabelling, and it no longer decides the
     recommendation, because usability already leads.

3. **Generic criticism moved to `other.general`.** The final setup sends unspecific complaints ("Super buggy these
   days", "They need to stop updating it") to `other.general`, as the rubric says, more often than the superseded run
   did: usability -> other fell from 65 to 38 in the sample, and `other.general` is now the largest issue
   (27,137 complaints, severity sum 54,364; 29.7% of complaints name no decision area, up from 25.7%). This is the
   other half of why the area totals moved between the two setups.

4. **Severity 3 vs 4 is the largest single pattern (163), and the enricher follows the written scale** on
   restrictions (9 of 10 sampled). Applying the verifier's severities would raise the premium-only severity sum, not lower it.

5. **The recommendation is close and labeller-sensitive, as the memo says.** On the sample, the enricher's labels put
   billing/support first by severity sum (705, usability 650, playback 617) and the verifier's put playback first
   (758, usability 747, billing 660); usability is second under both, and first by complaint count under both
   (`runs/final-200k-v2/analysis/robustness.json`). On the full run usability leads billing/support by 432 severity
   points (52,983 vs 52,551). The memo recommends usability and calls the call provisional.

6. **Patterns with no effect on the ranking.** The praise topic patterns (other <-> catalog, 42 each) and
   cancellation vs complaint (16 + 13) do not move the ranking: praise is never grouped into issues, and the ranking
   counts complaint and cancellation together.

7. **Fallback1 agrees more.** Fallback1 labels agree with the verifier on all three fields for 73% of its sampled texts
   (30 of 41), primary labels for 62% (1,210 of 1,959), although fallback1 handles the flagged texts.

**Not done:** no person checked these verdicts, and no label was changed. The cheapest human follow-up is the 41
premium-only topic disagreements (`disagreements.csv`, filter `enricher_topic = billing`, `verifier_topic != billing`).

## 5. Reproduce (offline, from the repository root)

`data/analysis_200k.csv` is git-ignored; regenerate it with `python3 scripts/make_analysis_subset.py`.

```bash
python3 evals/verification/disagreement_counts.py --run-dir runs/final-200k-v2 --input data/analysis_200k.csv \
    --out evals/verification/disagreement_counts.json
```

The analysis of the superseded effort-none run (same method, `runs/final-200k`) is in
[disagreement_analysis_superseded_effort_none.md](disagreement_analysis_superseded_effort_none.md).

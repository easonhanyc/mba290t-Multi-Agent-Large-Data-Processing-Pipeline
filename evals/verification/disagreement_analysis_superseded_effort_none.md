# Verifier disagreements on the superseded first final run (effort none)

**Superseded.** This analysis covers `runs/final-200k`, the first final run, made with GPT-6 Luna at effort none before
the golden labels existed. The final run is `runs/final-200k-v2` (the golden comparison's winning setup), analysed in
[disagreement_analysis.md](disagreement_analysis.md). This page is kept unchanged otherwise, because its counts and
readings are evidence about the superseded labels.

Written 2026-10-13 from the saved files of `runs/final-200k`, offline: no model calls, and no label was changed.
The counts in sections 1 and 4 are computed from the files named. **The verdicts in sections 2 and 3 are the AI
assistant's reading of each review against the shared rubric (`docs/labels.md`, `prompts/llm_enrich_v2.md`,
`prompts/verify_v2.md`). They are not human labels and not ground truth.**

The verifier is Claude Haiku via `claude -p`. It labels a declared random sample of distinct texts blind: it
never sees the enricher's answer (`runs/final-200k/verification/report.json`, `sample`: 10% of 152,363 distinct
completed texts, capped at 2,000, chosen by lowest SHA-256 of seed + review_id). Its topic is the contract
topic only. It has no subtopic, so `billing.premium_only` versus usability can only be compared at the topic level.

## 1. Counts (`runs/final-200k/verification/report.json`)

The sample has 2,000 texts. They agree on topic for 1,618, intent for 1,841, exact severity for 1,583 and
sentiment within 0.5 for 1,980. 762 texts differ on at least one field, and all of them are listed with both
labels in `disagreements.csv`. There were 0 verifier failures.

**By field.** 582 of the 762 differ on exactly one field:

| Fields that differ | Texts |
|---|---:|
| topic only | 267 |
| severity only | 255 |
| topic + severity | 74 |
| intent + severity | 57 |
| intent only | 54 |
| topic + intent + severity | 26 |
| topic + intent | 9 |
| any combination that includes sentiment | 20 |

Severity differs on 417 texts. 384 of them differ by one point, 30 by two and 3 by three
(`severity_abs_diff_counts`).

**By direction (enricher -> verifier), top patterns:**

| Topic (382) | n | Intent (159) | n | Severity (417) | n |
|---|---:|---|---:|---|---:|
| usability -> other | 65 | cancellation -> complaint | 33 | 3 -> 4 | 165 |
| other -> catalog | 50 | praise -> unclear | 25 | 3 -> 2 | 90 |
| catalog -> other | 38 | complaint -> unclear | 24 | 2 -> 3 | 50 |
| billing -> usability | 37 | complaint -> praise | 14 | 2 -> 1 | 36 |
| catalog -> usability | 25 | unclear -> praise | 12 | 1 -> 2 | 22 |
| billing -> playback | 25 | complaint -> request | 12 | 4 -> 3 | 12 |
| playback -> other | 17 | unclear -> complaint | 9 | 2 -> 4 | 12 |

The verifier gives the higher severity in 261 cases and the lower one in 156. The enricher's own issue
labels come from a read-only join with `runs/final-200k/enriched.jsonl.gz`. On that join, the largest topic
patterns by enricher issue are `other.general` -> catalog (50), `billing.premium_only` -> usability (36),
`usability.other` -> other (32), `billing.premium_only` -> playback (25) and `usability.navigation` -> other (20).
96 of the 165 severity 3 -> 4 cases are `billing.premium_only`.

**Where they fall:**

- **Enricher tier.** Fallback1 labels (effort low, the flagged texts) differ from the verifier on topic, intent
  or severity for 30 of 182 texts. Primary labels differ for 726 of 1,818 (`by_enricher_tier`).
- **needs_review.** Only 28 of the 762 disagreements have the enricher's `needs_review` flag. 172 of the 2,000
  sampled texts carry it. So the flag does not pick out the texts the verifier disputes.
- **Verifier confidence.** The verifier's confidence on the 762 was high for 587, medium for 132 and low for 43.
- **Ranking.** 550 of the 762 have enricher intent complaint or cancellation, so only these can affect the
  ranking. Praise, request and unclear records are never grouped into issues.

## 2. Random sample of 20 disagreements

The 20 are the disagreements with the lowest SHA-256(`"disagreement-review-v1:" + review_id`); the command is in
section 5. Text is abridged. E = enricher (issue / intent / severity), V = verifier (topic / intent / severity).

| # | review_id | Text (abridged) | E | V | Reading against the rubric | Verdict |
|---|---|---|---|---|---|---|
| 1 | `fbf4ea57` | Remove from Play Store.. Terrible update | usability.other / complaint / 2 | other / complaint / 2 | No feature named; "General 'bad app' is a complaint, without inferring a specific defect" | Verifier |
| 2 | `a107df8f` | Repeating songs and can't skip song | usability.library / complaint / 3 | playback / complaint / 3 | Repeat controls (usability.library) or "plays the wrong song" (playback.stops); the skip may be the free-tier limit, but the text does not say so | Ambiguous |
| 3 | `5bc1f0db` | Worst app because of the new updates | usability.other / complaint / 2 | other / complaint / 2 | As #1 | Verifier |
| 4 | `92f8bc27` | please let us listen song.please For a whole day. | playback.stops / request / 1 | other / request / 1 | Probably a free-tier listening limit, but nothing is named; a request, so not ranked | Ambiguous |
| 5 | `a3aaa39c` | I just paid for premium but it isn't upgrading. It still says I'm on free plan | billing.payment / complaint / 3 | billing / complaint / 4 | The worked example `1d1480fb` (subscription will not activate, app still works) is 3. "Paid but not delivered" can be read as blocked. Not 5 | Ambiguous (3/4); E matches the worked example |
| 6 | `319be3f6` | It's not letting me play music unless it's on shuffle play. And it won't let me skip a song either. | billing.premium_only / complaint / 3 | usability / complaint / 4 | Topic: Premium is never mentioned. Both prompts say "a feature the customer says is locked behind Premium", and the enrich prompt's own shuffle example goes to usability_library. Severity: music still plays on shuffle, a restricted function (3) | Split: V topic, E severity |
| 7 | `20b803ac` | It's good and having great collection | other.general / praise / 1 | catalog / praise / 1 | "For a positive review, the first specific praised feature": the collection is catalog | Verifier |
| 8 | `2a519a11` | ... given the opportunity to remove shuffle without the need to pay like in India. | billing.premium_only / complaint / 3 | billing / complaint / 2 | Forced shuffle unless you pay is a restricted function (3) | Enricher |
| 9 | `ae77f63d` | ... could be easier to make playlist by simply having a quick [way] at finding new music | catalog.recommendations / request / 1 | usability / request / 1 | Playlist-making (usability.library) or discovery (catalog); a request, not ranked | Ambiguous |
| 10 | `9c1a2463` | My Go to place for Podcast & Music ! | catalog.podcasts / praise / 1 | other / praise / 1 | Podcasts are named first, but "Podcast & Music" may be general praise | Ambiguous |
| 11 | `2caa404c` | so nice I can listen all the songs I want | other.general / praise / 1 | catalog / praise / 1 | Song availability is a specific praised feature (catalog) | Verifier (lean) |
| 12 | `4adf18ae` | They need to stop updating it | usability.other / complaint / 2 | other / complaint / 2 | As #1 | Verifier |
| 13 | `8c6b1c6b` | Really good but sometimes a little slow | playback.performance / complaint / 2 | playback / praise / 2 | "Mixed praise and criticism is a complaint". V's praise with severity 2 also breaks the scale (praise is 1) | Enricher |
| 14 | `50b6890a` | This app can't miraculously just stop working when you trying to reinstall it ... | playback.crash / complaint / 3 | other / unclear / 1 (low confidence) | Garbled, but it reports the app no longer working: complaint, playback.crash; the severity is unclear | Enricher (topic, intent) |
| 15 | `b3025eee` | ... please add the lyrics download option cause in offline I can't see the lyrics | catalog.lyrics / request / 1 | downloads / request / 1 | Lyrics availability or offline listening; a request, not ranked | Ambiguous |
| 16 | `c47e6613` | Terrible it wont let me play my song on my playlist and when i try to pick a song all it does it put on suggested songs. | billing.premium_only / complaint / 3 | playback / complaint / 4 | As #6. Premium is not mentioned (V topic); music still plays, as suggested songs (3, E severity) | Split: V topic, E severity |
| 17 | `638a23cf` | Super buggy these days | playback.crash / complaint / 2 | other / complaint / 2 | No specific defect | Verifier |
| 18 | `e64c62fa` | ... Only problem is the glitches. | playback.performance / complaint / 3 | playback / complaint / 2 | Unspecified glitches, no supported functional loss: 2 | Verifier |
| 19 | `5eb86e84` | Spotify playing songs in between their advertisement ... Irritating. | usability.ads / complaint / 3 | usability / complaint / 2 | Ads are an annoyance with no function lost (worked example `5e42046c`): 2 | Verifier |
| 20 | `00f183cb` | ... sometimes it wants to turn on all by it's self not sure why | usability.other / complaint / 2 | playback / complaint / 2 | Playback starting on its own fits neither definition cleanly | Ambiguous |

**Tally (assistant's reading):** the verifier fits the rubric better on 8, the enricher on 3, and 2 are split
(V on topic, E on severity). 7 are genuinely ambiguous. 6 of the 20 (#4, #7, #9, #10, #11, #15) are praise or
requests, so their topic has no effect on the ranking.

## 3. Two targeted looks

### Premium-only versus usability/playback (10 of the 71 topic disagreements on `billing.premium_only`)

These are the lowest SHA-256(`"premium-boundary-v1:" + review_id`), excluding the random 20.

| review_id | Text (abridged) | E -> V topic / severity | Reading |
|---|---|---|---|
| `eb8343f7` | not able to manage my music and can't shuffle ... can't [rewind] ... gonna unin[stall] | billing -> usability / 3 -> 4 | Premium not named; restricted function (3) |
| `99af8e65` | if your on mobile you can't even play full songs | billing -> playback / 3 -> 4 | Premium not named; restricted (3) |
| `2189ca78` | the not-premium version includes much advertisements and cannot be played in the background | billing -> usability / 3 -> 2 | The paywall is the complaint: E's topic and E's 3 fit |
| `5da7e835` | liked songs play about 10 seconds on repeat ... plays a song I never heard of | billing -> playback / 3 -> 4 | Premium not named; could also be a bug: ambiguous |
| `653810b4` | Uninstall ... When I can't decide which song to play | billing -> other / 3 -> 4 | Premium not named; restricted (3) |
| `ab00954b` | not working properly ... Spotify is forcing to buy premium | billing -> playback / 3 -> 4 | The Premium push is named: E's topic fits; 4 is not supported |
| `927b7d51` | It won't let me pick the song that i want even i get premium | billing -> playback / 3 -> 4 | A paying customer, so a paywall complaint does not fit; billing.payment or playback: ambiguous |
| `75436e8f` | no longer able to skip songs or play what I wanted ... going back to using Pandora | billing -> usability / 3 -> 4 | Premium not named (reads like an ended trial); restricted (3) |
| `78d074b5` | I wish we could download music offline for free | billing -> downloads / 1 -> 1 | "Offline listening described only as a Premium paywall" is premium_only: E. A request, not ranked |
| `414575a2` | Can't even listen to songs i want to | billing -> catalog / 3 -> 4 | Premium not named; restricted (3) |

Six of the 10 never mention Premium or payment, but they describe behaviour that matches free-tier limits:
cannot pick songs, forced shuffle, no skipping, previews. For these six the written rule ("a feature the
customer says is locked behind Premium") favours the verifier's non-billing topic. In three, the paywall is
the subject, and the enricher's topic fits. One is a paying customer and is ambiguous.

### Severity 3 -> 4 (10 of the 165)

These are the lowest SHA-256(`"severity-3-4-v1:" + review_id`), excluding the random 20. Two overlap with
the table above: `75436e8f` and `ab00954b`.

| review_id | Text (abridged) | E issue | Reading |
|---|---|---|---|
| `d12bfaf6` | can't forward the song and can't skip the song more then 6 times an hour ... can't play a specific song | billing.premium_only | Restricted, music still plays: 3 (E) |
| `82218a14` | Can't even add a song to queue or even play the previous song even for that you have to pay! | billing.premium_only | 3 (E) |
| `4f17a93f` | [Premium user] havent been able to listen to more then one song with out picking up my phone | playback.stops | Degraded: 3 (E) |
| `687a8d68` | Useless since the 'new episode' playlist was removed. | catalog.podcasts | A feature was removed and other use remains: 3 (E) |
| `0797ceb1` | all things are premium no one can listen to his/her choice song | billing.premium_only | 3 (E) |
| `5f501da2` | I click on a song to listen to. It plays a completely different song and then plays 8 adverts | billing.premium_only | Borderline: music plays, but not the chosen song |
| `c93533d6` | Every time i pick a song it takes another random song. | playback.stops | Borderline, for the same reason |
| `667c03ee` | Doesn't allows to turn off shuffle mode ... asks for premium every time, i might have to uninstall | billing.premium_only | 3 (E); a threat to leave is cancellation per `docs/labels.md`, so E is right on intent too |
| `75436e8f`, `ab00954b` | see the premium-only table | billing.premium_only | 3 (E); 4 not supported |

In 8 of these 10, the enricher's 3 matches the written scale: "a degraded or restricted function; some use or
workaround remains". The other 2 are borderline. The verifier reads "I cannot play the song I choose" as a
blocked core task (4).

## 4. What this implies

1. **Most disagreements are boundary calls, not gross errors.** 582 of 762 differ on one field. 384 of the 417
   severity differences are one point. The verifier is low-confidence on only 43. The two models disagree
   confidently and systematically at a few rubric boundaries.

2. **The premium-only boundary is the one that matters for the recommendation.** `billing.premium_only` has 235
   texts in the sample, and the verifier puts 71 of them (30%) in another topic: usability 36, playback 25,
   other 5, downloads 3 and catalog 2. A simple keyword check separates them. Use the payment-word pattern
   `premium|subscri|\bpa(y|id|ying)\b|\bfree\b|\bbuy\b|money|trial|\$` (case-insensitive). 47 of those 71 contain
   none of these words, against 13 of the 164 premium-only texts where the verifier agrees.
   - **Full run.** 4,785 of the 18,016 `billing.premium_only` members contain none of the words. Their
     severity sum is 14,239 of 52,577 (`membership.csv`, `enriched.jsonl.gz`, text from `data/analysis_200k.csv`;
     command below).
   - **Sensitivity, arithmetic only.** Suppose none of those 4,785 counted as billing. Then billing/support
     would fall from 59,146 to 44,907, below usability (54,124) and playback/performance (46,058), before
     they are added to any other area (`area_rollup.json`).
   - **This is an upper bound, not a relabelling.** Some keyword-free texts plainly describe free-tier limits
     ("can't skip the song more then 6 times an hour").
   - **It is the mechanism behind the robustness caveat.** On the same sample, billing/support's severity
     sum is 787 under the enricher's labels and 661 under the verifier's, while playback/performance's is 599
     and 758 (`runs/final-200k/analysis/robustness.json`).
   - **The issue is free-tier packaging, not billing failures.** Its members complain about what the free tier
     withholds. That is a pricing and packaging question. Payment failures are a separate issue
     (`billing.payment`).

3. **The rubric is inconsistent at that boundary.** The `docs/labels.md` boundary notes ("Forced shuffle or skip
   limits for free users are billing_premium_only") are broader than the sentence both prompts share ("a
   feature the customer says is locked behind Premium"). The enrich prompt's own example sends a shuffle
   complaint with no paywall mentioned to `usability_library`. The enricher often applied the broader reading
   and the verifier the literal one. Neither is wrong against all of the written guidance. The fix is one
   explicit rule, for example a separate code for "free-tier restriction described without naming Premium".
   The labels and the `label_config` were not changed after the run.

4. **Severity 3 vs 4 is the largest single pattern (165), but it does not threaten the lead.** On restrictions,
   the enricher follows the written scale. Applying the verifier's severities would raise the premium-only
   severity sum, not lower it. The risk to the billing lead is the topic boundary in point 2.

5. **Generic "update" or "buggy" complaints.** The enricher puts these in `usability.other`,
   `usability.navigation` or `playback.crash`, where the rubric says `other.general`: usability -> other
   is 65 in the sample, and 4 of the random 20 are this pattern. This slightly inflates usability, the main
   alternative, and does not favour billing.

6. **Patterns with no effect on the ranking.** The praise topic patterns (other -> catalog 50, catalog -> other
   38) and the cancellation-vs-complaint pattern (33 + 6) do not move the ranking. Praise is never grouped
   into issues, and the ranking counts complaint and cancellation together. The praise convention is the same
   one Eason's golden labels use (praise naming a feature -> other; `evals/golden/error_analysis.md`). The
   contract rule favours the verifier there.

7. **Effort-low labels agree more.** Fallback1 (effort low) disagrees on 30 of 182 texts, primary on 726 of
   1,818, even though fallback1 handles the flagged texts. This is consistent with the golden-50 comparison,
   where effort low scored best (`docs/model_choice.md`).

**Not done:** no person checked these verdicts, and no label was changed. The cheapest human follow-up is to
review the 71 premium-only topic disagreements (`disagreements.csv`, filter `enricher_topic = billing`,
`verifier_topic != billing`). That would settle the rule in point 3.

## 5. Reproduce (offline, from the repository root)

`data/analysis_200k.csv` is git-ignored. Regenerate it with `python3 scripts/make_analysis_subset.py`. Only the
last three lines need it.

```python
import collections, csv, gzip, hashlib, json, re
V = "runs/final-200k/verification"
dis = json.load(open(f"{V}/report.json"))["disagreements"]
print(collections.Counter("+".join(d["fields"]) for d in dis).most_common())
for f in ("topic", "intent", "severity"):
    print(f, collections.Counter(f"{d['enricher'][f]} -> {d['verifier'][f]}"
                                 for d in dis if f in d["fields"]).most_common(10))
key = lambda d: hashlib.sha256(f"disagreement-review-v1:{d['review_id']}".encode()).hexdigest()
print([d["review_id"][:8] for d in sorted(dis, key=key)[:20]])          # the random 20
KW = re.compile(r"premium|subscri|\bpa(y|id|ying)\b|\bfree\b|\bbuy\b|money|trial|\$", re.I)
sev = {}
with gzip.open("runs/final-200k/enriched.jsonl.gz", "rt") as fh:
    for line in fh:
        r = json.loads(line); sev[r["review_id"]] = r["severity"]
mem = [r["review_id"] for r in csv.DictReader(open("runs/final-200k/membership.csv"))
       if r["issue_id"] == "billing.premium_only"]
text = {r["review_id"]: r["review_text"] for r in csv.DictReader(open("data/analysis_200k.csv", encoding="utf-8"))}
no_kw = [m for m in mem if not KW.search(text[m])]
print(len(mem), len(no_kw), sum(sev[m] for m in no_kw))                 # 18016 4785 14239
```

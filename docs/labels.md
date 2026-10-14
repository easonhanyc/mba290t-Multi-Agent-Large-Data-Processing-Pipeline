# Labels: taxonomy, intent, severity, sentiment

Primary labels are the grading contract's common labels (`GRADING_CONTRACT.md`), used verbatim. The subtopic layer is ours: it exists only to group complaints into stable issues (`issue_id = topic.subtopic`). Single source of truth: `insight/labels.py`; the Jev questions (`prompts/jev_enrich_v1.json`) and LLM prompts are rendered from it, and `tests/test_core.py` fails if they drift.

Classification input is `review_text` only. Stars, likes, app version and timestamp stay metadata and never reach a model.

## Topics and subtopics (22 issue options, 8 topics)

| Topic (contract) | Contract definition | Issue option (`issue_id`) | Our definition | Boundary note |
|---|---|---|---|---|
| `access` | Login, signup, password or account access | `access_login` (`access.login`) | Cannot log in, keeps getting logged out, login or verification-code errors. | A 'no internet connection' error while already logged in is playback_connection. |
| `access` | Login, signup, password or account access | `access_account` (`access.account`) | Sign-up or account creation, password reset, hacked, locked or deleted accounts, account settings. | Choosing or paying for a plan is billing. |
| `usability` | Navigation, controls, layout, queue/playlist management, ad interruptions | `usability_ads` (`usability.ads`) | Too many, too long, too loud or repeated ads; ads interrupting listening. | Complaints that features need Premium are billing_premium_only, even when ads are also mentioned. |
| `usability` | Navigation, controls, layout, queue/playlist management, ad interruptions | `usability_navigation` (`usability.navigation`) | Hard to find things, confusing layout, redesigns or home-screen changes, buttons moved or removed. | A missing control described as Premium-only is billing_premium_only. |
| `usability` | Navigation, controls, layout, queue/playlist management, ad interruptions | `usability_library` (`usability.library`) | Managing the queue, playlists, liked songs or library; shuffle or repeat controls that misbehave. | Forced shuffle or skip limits for free users are billing_premium_only. |
| `usability` | Navigation, controls, layout, queue/playlist management, ad interruptions | `usability_other` (`usability.other`) | Notifications, emails, settings, toggles, widgets and other interaction annoyances. | Use only when no other usability option fits. |
| `playback` | Playback failure, crashes, lag, connection failures, audio quality, resource use | `playback_stops` (`playback.stops`) | Music stops, pauses, skips by itself, will not start, or plays the wrong song. | Skip limits for free users are billing_premium_only. |
| `playback` | Playback failure, crashes, lag, connection failures, audio quality, resource use | `playback_crash` (`playback.crash`) | App crashes, freezes, will not open or load, blank screens. | - |
| `playback` | Playback failure, crashes, lag, connection failures, audio quality, resource use | `playback_connection` (`playback.connection`) | App says there is no internet or that it is offline while connected; network or streaming errors. | - |
| `playback` | Playback failure, crashes, lag, connection failures, audio quality, resource use | `playback_devices` (`playback.devices`) | Bluetooth, casting, Spotify Connect, cars, smartwatches, smart speakers, TVs, consoles, other integrations. | - |
| `playback` | Playback failure, crashes, lag, connection failures, audio quality, resource use | `playback_performance` (`playback.performance`) | Lag, slowness, battery or storage use, audio quality or volume problems. | - |
| `downloads` | Downloading, saved music, offline listening, disappearing downloads | `downloads_offline` (`downloads.offline`) | Downloading, saved music, offline mode, downloads that disappear or fail. | Offline listening described only as a Premium paywall is billing_premium_only. |
| `catalog` | Missing songs/artists, search/discovery, recommendations, lyrics availability | `catalog_missing` (`catalog.missing`) | Songs, artists, albums or podcasts missing, removed, greyed out or unavailable. | - |
| `catalog` | Missing songs/artists, search/discovery, recommendations, lyrics availability | `catalog_search` (`catalog.search`) | Search results, finding songs or artists, browsing and discovery. | - |
| `catalog` | Missing songs/artists, search/discovery, recommendations, lyrics availability | `catalog_recommendations` (`catalog.recommendations`) | Recommendations, the algorithm, autoplay or radio picks, the DJ, unwanted suggested songs. | - |
| `catalog` | Missing songs/artists, search/discovery, recommendations, lyrics availability | `catalog_lyrics` (`catalog.lyrics`) | Lyrics missing, wrong or not loading. | Lyrics locked behind Premium is billing_premium_only. |
| `catalog` | Missing songs/artists, search/discovery, recommendations, lyrics availability | `catalog_podcasts` (`catalog.podcasts`) | Podcast, audiobook or video-podcast content and episodes. | - |
| `billing` | Price, charges, subscriptions, paywalls, premium entitlement; explicitly premium-only controls go here | `billing_premium_only` (`billing.premium_only`) | Features locked to Premium: skip limits, forced shuffle, cannot pick songs, cannot repeat or rewind, lyrics or offline behind a paywall, 'everything needs Premium now'. | Merely mentioning Premium is not enough; the complaint must be about the paywall or entitlement. |
| `billing` | Price, charges, subscriptions, paywalls, premium entitlement; explicitly premium-only controls go here | `billing_price` (`billing.price`) | Premium price, price increases, value for money. | - |
| `billing` | Price, charges, subscriptions, paywalls, premium entitlement; explicitly premium-only controls go here | `billing_payment` (`billing.payment`) | Unexpected or repeated charges, refunds, payment failures, a subscription or trial not activating, cancellation or plan problems. | Music crashing for a paying customer is playback, not billing. |
| `support` | Contacting support and the support response | `support_contact` (`support.contact`) | Contacting customer support, support response quality or absence of a response. | - |
| `other` | General praise/criticism, unrelated content, or no supported specific topic | `other_general` (`other.general`) | General praise or criticism with no specific feature, unrelated content (politics, artists, boycotts), or meaningless text. | Use when no specific product area is supported by the text. |

Rules for several problems in one review (contract): choose the problem with the highest supported severity; on a tie, the first specific problem mentioned. For a positive review, the first specific praised feature; general praise is `other`. A paid plan mentioned in passing is not `billing`; a subscription that fails to activate is; music crashing for a paying customer is `playback`. Explicitly premium-only controls (skip limits, forced shuffle, lyrics behind the paywall) are `billing.premium_only`.

## Intent (precedence: first match wins)

| Order | Intent | Meaning |
|---:|---|---|
| 1 | `cancellation` | The customer explicitly says they are leaving, uninstalling, cancelling or switching to another app or service, or threatens to do so. This applies even if they also complain. |
| 2 | `complaint` | The customer reports a negative experience or criticises the app, including mixed praise and criticism and general statements like 'bad app', and does not say they are leaving. |
| 3 | `request` | The customer asks for a change or a new feature without reporting that anything is broken or bad. |
| 4 | `praise` | The customer only says positive things about the app, with no criticism, request or plan to leave. |
| 5 | `unclear` | The text is meaningless, unrelated to the app, only a slogan or boycott call with no product complaint or personal departure, only instructions about how to label it, or its meaning cannot be determined. |

Bare boycott slogans and unrelated or meaningless text are `unclear`, unless there is a product complaint or an explicit personal departure. General 'bad app' is a complaint, without inferring a specific defect. Cancellation language is expressed intent, not churn.

## Severity (shared scale)

| Level | Meaning | Rule enforced in code |
|---:|---|---|
| 1 | No reported problem: praise, neutral/unclear content, or a pure feature request | praise, request and unclear are always 1 |
| 2 | Dislike, generic criticism, minor annoyance, or a cosmetic issue; no supported functional loss | a complaint is at least 2 |
| 3 | A degraded or restricted function; some use or workaround remains | - |
| 4 | A clearly blocked core task, such as inability to log in or play music | - |
| 5 | Explicit serious financial, privacy, or data harm; an expensive plan, a crash, or angry language alone is insufficient | requires explicit financial, privacy or data harm |

Cancellation intent does not raise severity by itself. Missing context sets `needs_review` instead of inventing impact. When a classifier returns a combination the definitions rule out (praise with severity 3, complaint with severity 1), code treats it as a difficulty signal for the capped fallback; if still unresolved, code applies the rule in the last column and sets `needs_review`.

## Sentiment (-1 to 1)

| Value | Anchor |
|---:|---|
| -1.0 | Very negative: angry, hostile or strongly dissatisfied |
| -0.5 | Somewhat negative: dissatisfied, disappointed or critical |
| +0.0 | Neutral or balanced: no clear feeling, or praise and criticism in equal measure |
| +0.5 | Somewhat positive: satisfied or mildly pleased |
| +1.0 | Very positive: enthusiastic praise |

Jev answers sentiment as a five-level Score (0-4); code maps it with `sentiment = score / 2 - 1` (TypeSafe docs) and rounds to two decimals. LLM roles answer an integer -2..2 that code divides by 2. Predeclared tolerance for agreement: 0.5 (one level).

## Evidence quote, entities, needs_review (contract field definitions)

| Field | Contract definition | How the pipeline fills it | How the golden labels encode it |
|---|---|---|---|
| `sentiment` | Number from -1 to 1; document its meaning | The anchors in the table above; an LLM answers -2..2 and code divides by 2 | Any value in [-1, 1] (Eason used the anchors plus ±0.25 / ±0.75); agreement = within 0.5 |
| `entities` | List of features or product terms explicitly mentioned | Canonical product terms matched by code with word-bounded patterns (`ENTITY_PATTERNS` in `insight/labels.py`); a term is listed only if the text contains it, so no entity is invented. No model generates entities | The features Eason judged the review to be about, in his own words (e.g. "Many ads", "No lyric"); blank when none. Because these are descriptions rather than exact terms, entity agreement is reviewed case by case in `evals/golden/results_disagreements.md`, and the automatic check is that every predicted entity occurs in the text |
| `evidence_quote` | Exact substring supporting the main label; flag insufficient evidence | Code splits the review into sentence-like segments that are exact slices of the text (`insight/segment.py`); the classifier picks a segment number and code copies that slice, so the quote is always an exact substring. Single-sentence reviews use the whole trimmed text. When no sentence supports a label the model flags the review, which sets `needs_review` | The number of the supporting sentence (1 = first sentence). `evals/golden/convert_labels.py` maps it to the exact sentence text; one review that Eason split at "..." is split the same way |
| `needs_review` | Boolean indicating ambiguity or insufficient evidence | True when the LLM says the text is ambiguous or lacks evidence, when code reconciled an intent/severity contradiction, when a capped fallback was needed but not available, or when code sees emoji-only or mostly non-Latin text | TRUE/FALSE: TRUE when the review is ambiguous or the evidence is insufficient (6 of 50) |

## Golden-set labelling (evals/golden)

Eason labelled the 50 reviews by hand in `evals/golden/golden_50_labeled.numbers` (the course's
golden_50_to_label.csv opened as a workbook, so the rating and other metadata columns were visible; the
rubric asks for labels from the review text), before seeing any model output on these reviews. `convert_labels.py` turns its
CSV export into `golden_50_labeled.csv` without changing any judgment. Format mappings: intent menu codes
1-5 -> cancellation, complaint, request, praise, unclear; topics written as `catalog.catalog_missing` ->
topic `catalog` (issue `catalog.missing`); "Praise" / "Criticism" used as a topic -> `other` (the contract's
rule for general praise or criticism). Decisions Eason made on 2026-10-13 after re-reading the contract,
recorded per review_id in the script: one blank intent filled (request), and four generic "hate this app /
worst app" reviews changed from unclear to complaint.

Known convention difference, kept on purpose: eight reviews that report a problem and ask for a fix
("plz fix", "please reduce the ads") are labelled **request** by Eason. Under the contract precedence
(complaint before request) the pipeline labels them complaint. They are counted as intent disagreements and
discussed in the error analysis rather than relabelled. Likewise, a few praise reviews that name a feature
(recommendations, ads, the song catalog) are labelled topic `other` by Eason, while the contract rule the
models follow picks the first praised feature.

## Worked examples on development reviews

Drafted with the AI assistant while building the rubric, from `checkpoint_500.csv` rows 101-500 (never the golden 50 and never used in any prompt), and reviewed by Eason on 2026-10-14. They illustrate how the shared definitions apply; they are not golden labels, and no prompt, test or evaluation uses them.

| review_id | Text (abridged) | Stars | topic / issue | intent | sev | sentiment | needs_review | Why |
|---|---|---:|---|---|---:|---:|---|---|
| `d635d6c8-460e-452f-8d53-6cd1ea804e98` | Why are lyrics premium!? There is literally no need to keep lyrics premium ... Very disappointed | 1 | billing / billing.premium_only | complaint | 3 | -0.5 | false | Lyrics behind the paywall is a premium-only restriction, not catalog availability; a restricted function = 3. |
| `5e42046c-b29b-4035-ba83-a8e222789e98` | this app is great. But the bad thing is that it gives too many ads ... Apart from that this app is great | 4 | usability / usability.ads | complaint | 2 | +0.5 | false | Mixed praise and criticism is a complaint; ads are an annoyance (2), no function lost. |
| `a7b7539a-c8d3-4f4e-9edd-d46cd1b1fd12` | The very second I signed up for premium it stopped letting me play anything ... Bye bye Spotify | 1 | playback / playback.stops | cancellation | 4 | -1.0 | false | Explicit departure beats complaint. Cannot play anything = blocked core task (4); a paying customer's playback failure is playback, not billing. |
| `7fd63051-28ec-4e51-a06e-97f7010eae40` | I uninstalled this app as a form of protest and boycott due to ... | 1 | other / other.general | cancellation | 1 | -0.5 | false | A boycott with an explicit personal departure is cancellation; no product problem, so severity stays 1. |
| `1f13c3a2-e57b-460c-b569-964e6b2b1f31` | Can no longer listen to music off line or even log in. The app is broken ... | 1 | downloads / downloads.offline | complaint | 4 | -1.0 | true | Two blocked core tasks tie at 4; the first mentioned (offline) wins. 'If customers cancelled...' is not a personal departure. |
| `12efd15d-4d4f-4a71-8e71-69d03b6f983a` | I can't login to the app, it keep saying that there's no internet connection ... | 1 | access / access.login | complaint | 4 | -0.5 | false | Inability to log in is the contract's example of a blocked core task. |
| `c64af4d8-ac17-48fe-ae38-fd54b41b16b1` | Latest update is stupid. App says no internet connection available, but clearly I do ... | 2 | playback / playback.connection | complaint | 3 | -0.5 | true | Connection error while online; the text does not say playback is fully blocked, so 3 and needs_review rather than inventing impact. |
| `d26566f7-a898-4298-a06a-50bd3f7319c1` | Could be doing with hi-res audio don't like getting bombarded with playlist recommendations when the option is turned off | 3 | catalog / catalog.recommendations | complaint | 2 | -0.5 | false | A request plus a reported annoyance: complaint outranks request; the reported problem decides the topic. |
| `d27e9b26-a7af-469c-9a4e-8deea2db72ae` | Great place for music. Bad for smaller artists and a platform for ... | 2 | other / other.general | complaint | 2 | -0.5 | false | Criticism of the platform's content policy, not a product feature: other, generic criticism (2). |
| `08c07310-e802-4a88-bd97-2a5f240c0b44` | Kitna paisa chahiye bhai ... (Hinglish: 'how much money do you want') | 1 | billing / billing.price | complaint | 2 | -1.0 | true | Romanised Hindi about price; readable but interpretive, so needs_review. |
| `0be20402-efaf-482f-9635-78f166bcf538` | ممتاز (Arabic: 'excellent') | 5 | other / other.general | praise | 1 | +1.0 | true | General praise is other; code flags mostly non-Latin script for review. |
| `02365ec7-f37a-419a-b26d-bf2467d38461` | 👍 | 5 | other / other.general | praise | 1 | +0.5 | true | Emoji-only text: code sets needs_review (no letters). |
| `0d361ea6-3089-41c2-9e0f-4cd6a04f0dd8` | aA😩qa1qw1awqqqqaqqa😊qqqw11 ... | 2 | other / other.general | unclear | 1 | +0.0 | true | Meaningless text is unclear; the 2-star rating does not make it a complaint. |
| `d87536c5-6fe0-4b38-b0b1-c47936e4a0d8` | Top algorithm, but again hacked, can't even recover the playlists ... cost over three hundred dollars | 4 | access / access.account | complaint | 5 | -0.5 | true | A hacked account with data loss is explicit serious harm (5); the money claim is unclear, so needs_review. |
| `1d1480fb-0142-46da-8570-45bf3983bf6d` | Good app but. I cant sign up for individual premium.. it doesnt give me the prompt to pay | 4 | billing / billing.payment | complaint | 3 | +0.0 | false | A subscription that cannot activate is billing; the app still works, so 3. |
| `179d79f7-d052-490f-a9d6-f97525b32642` | Love Spotify, but since I got my new phone, it keeps randomly stopping ... | 5 | playback / playback.stops | complaint | 3 | +0.0 | false | Five stars, yet a degraded function: stars never set severity. |

## Language and legibility

Reviews are not translated. Models read any language they can; Jev's documentation says non-English accuracy is lower. Mostly non-Latin-script and emoji-only texts are always `needs_review`. Garbled or meaningless text is `unclear` (severity 1). Empty or whitespace-only text is quarantined as `empty_review_text` and never sent to a model.

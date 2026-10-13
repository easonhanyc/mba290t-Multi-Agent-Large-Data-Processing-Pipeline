# Golden-set comparison

Label config: `gpt-6-luna@none>gpt-6-luna@low(1.5%)>sonnet@low(0.25%)|enrich-v2|schema-v2|cfg-1a5b53adeb`

50 human-labelled reviews (0 with several accepted labels); 0 missing or quarantined predictions count as wrong.

| Field | Agreement |
|---|---:|
| topic | 0.74 |
| intent | 0.7 |
| severity (exact) | 0.72 |
| all three | 0.46 |
| severity mean absolute error | 0.32 |
| sentiment within +/-0.5 | 0.86 |

## Per-class (unambiguous cases only)

**topic**

| Class | Support | Predicted | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|
| billing | 3 | 4 | 0.25 | 0.3333 | 0.2857 |
| catalog | 3 | 4 | 0.5 | 0.6667 | 0.5714 |
| downloads | 1 | 1 | 1.0 | 1.0 | 1.0 |
| other | 30 | 28 | 0.8929 | 0.8333 | 0.8621 |
| playback | 4 | 4 | 0.75 | 0.75 | 0.75 |
| support | 1 | 0 | None | 0.0 | 0.0 |
| usability | 8 | 9 | 0.5556 | 0.625 | 0.5882 |

**intent**

| Class | Support | Predicted | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|
| cancellation | 1 | 2 | 0.5 | 1.0 | 0.6667 |
| complaint | 14 | 20 | 0.55 | 0.7857 | 0.6471 |
| praise | 23 | 20 | 1.0 | 0.8696 | 0.9302 |
| request | 9 | 1 | 1.0 | 0.1111 | 0.2 |
| unclear | 3 | 7 | 0.2857 | 0.6667 | 0.4 |

## Confusions (human -> model)

- topic: `other -> usability` x3, `usability -> billing` x2, `other -> catalog` x2, `catalog -> other` x1, `support -> playback` x1, `usability -> other` x1, `billing -> other` x1, `playback -> billing` x1, `billing -> usability` x1
- intent: `request -> complaint` x7, `complaint -> unclear` x2, `praise -> unclear` x2, `praise -> complaint` x1, `request -> unclear` x1, `unclear -> complaint` x1, `complaint -> cancellation` x1

## Every disagreement

| Review | Text | Human (accepted) | Model | Wrong fields | Labelled by |
|---|---|---|---|---|---|
| `292ce26a` | Staff must be full of mentally ill kool-aid heads. Banning conservative music that speaks truth. Spotify is doing all they can to protect pedophiles, by banning | topic=catalog; intent=complaint; severity=3 | topic=other; intent=unclear; severity=1 | topic, intent, severity | primary |
| `991b6b3a` | Ads were okay, but limited functionality..it's just too much | topic=usability; intent=complaint; severity=2 | topic=billing; intent=complaint; severity=3 | topic, severity | primary |
| `1fc8b08f` | Duo Premium .... No ads at all! | topic=other; intent=praise; severity=1 | topic=usability; intent=praise; severity=1 | topic | primary |
| `947821dc` | Very good but wen I play my song it o ly plays a little bit then it stops I updated my phone and it worked but it happend again they need to fix this issue | topic=playback; intent=request; severity=4 | topic=playback; intent=complaint; severity=3 | intent, severity | primary |
| `723f07de` | Update: I reached out to Spotify Support and with some help from Sarah I was able to get the app working again. Old Post:Normally, the app works great, and I us | topic=support; intent=praise; severity=4 | topic=playback; intent=complaint; severity=4 | topic, intent | primary |
| `01d453b0` | I like it but god I hate it when the music Interrupts my ads | topic=usability; intent=complaint; severity=3 | topic=usability; intent=complaint; severity=2 | severity | primary |
| `ac6cd66d` | Lhat ng song nasa spotify | topic=other; intent=praise; severity=1 | topic=other; intent=unclear; severity=1 | intent | primary |
| `44129679` | Avtar sungh | topic=other; intent=unclear; severity=2 | topic=other; intent=unclear; severity=1 | severity | primary |
| `46842184` | asem, lirik nya kdang gaada kek mana?? | topic=catalog; intent=request; severity=4 | topic=catalog; intent=complaint; severity=3 | intent, severity | primary |
| `5de7f95b` | We are boycotting Swedish app in our protest against Sweden for their desrecpect & desceration of our holy book Qur'an | topic=other; intent=unclear; severity=2 | topic=other; intent=unclear; severity=1 | severity | primary |
| `de48c99b` | I LOVE that I was able to put in only a few songs I like and Spotify gave me recommendations for an AWESOME Playlist...!!! | topic=other; intent=praise; severity=1 | topic=catalog; intent=praise; severity=1 | topic | primary |
| `372d4e67` | Please ye ads ko thoda kumm Karo harr ek song ke baad ad 🙏🙄 | topic=usability; intent=request; severity=2 | topic=usability; intent=complaint; severity=2 | intent | primary |
| `47f1406d` | Very poor updates as we cannot playback the songs and most bad updates are happening it is affecting the spotify quality | topic=playback; intent=request; severity=4 | topic=playback; intent=complaint; severity=4 | intent | primary |
| `36609c5c` | Bheekhmangon | topic=usability; intent=request; severity=2 | topic=other; intent=unclear; severity=1 | topic, intent, severity | primary |
| `f4c8146a` | Unconditional love, Stoli Canales | topic=other; intent=praise; severity=1 | topic=other; intent=unclear; severity=1 | intent | primary |
| `3ddb3f4e` | Deleting this App. The new update suck, we can't choose our fvrt songs after some clicks, we can't CHOOSE song after a song played, and we can't turn off shuffl | topic=usability; intent=cancellation; severity=4 | topic=billing; intent=cancellation; severity=3 | topic, severity | primary |
| `16d640e9` | It's my best music app but now it's not...everything basic features is premium.... | topic=billing; intent=complaint; severity=2 | topic=billing; intent=complaint; severity=3 | severity | primary |
| `8cc4fad4` | I hate this app and sweden .I love islam | topic=other; intent=unclear; severity=2 | topic=other; intent=complaint; severity=2 | intent | primary |
| `215463ae` | What is happening with Spotify?? Recently I'm trying to play a song but it doesn't working. So I unstalled and thn again install it now I can't even open the ap | topic=playback; intent=request; severity=4 | topic=playback; intent=complaint; severity=4 | intent | primary |
| `46c0b49f` | Are you out of your mind? This is dangerous! Listening to music in a normal volume and suddenly an add starts and my ears feel like they explode!! Stop this BS, | topic=usability; intent=request; severity=3 | topic=usability; intent=complaint; severity=5 | intent, severity | primary |
| `283b5843` | Beth, we all got to give me a free dollar to go with 3 months, bro I can't be like | topic=billing; intent=complaint; severity=2 | topic=other; intent=unclear; severity=1 | topic, intent, severity | fallback1 |
| `2aa566c6` | Nice app, very less advertising | topic=other; intent=praise; severity=1 | topic=usability; intent=praise; severity=1 | topic | primary |
| `8c0546b0` | 1-Lyrics not getting loaded, 2-can't go back to or start song where to wanted. Pathetic update | topic=catalog; intent=request; severity=4 | topic=catalog; intent=complaint; severity=3 | intent, severity | primary |
| `dceb14e7` | I gave one star because I can't give any less than that. the new update is sooooooo annoying like I can't even play the songs that I like and I can't rewind son | topic=playback; intent=complaint; severity=4 | topic=billing; intent=complaint; severity=3 | topic, severity | primary |
| `5fba12ea` | I find Spotify very good, it finds and play whatever music you want and also adds songs that you might like, judging from your playlist if you choose to arrange | topic=other; intent=praise; severity=1 | topic=catalog; intent=praise; severity=1 | topic | primary |
| `d2f3874f` | Too expensive and the free version is pretty much unusable with constant ads... Every two or three songs.. Forget it | topic=billing; intent=complaint; severity=2 | topic=usability; intent=cancellation; severity=2 | topic, intent | primary |
| `99b93e31` | This update very bad for everyone.old Spotify. we all want. | topic=other; intent=complaint; severity=2 | topic=usability; intent=complaint; severity=2 | topic | primary |

"""Convert Eason's hand-labelled workbook into the scoring format (no model calls, no label invented).

Input : evals/golden/golden_50_labeled_workbook_export.csv  (CSV export of golden_50_labeled.numbers, labelled
        by Eason by hand from the review text only)
Output: evals/golden/golden_50_labeled.csv                   (read by `python -m insight golden`)

Mechanical mappings (format only):
  topic        'catalog.catalog_missing' -> topic 'catalog', issue 'catalog.missing';
               'Praise' / 'Criticism' -> 'other' (contract: general praise or criticism without a specific
               feature is 'other'; mapping chosen by Eason on 2026-10-13)
  intent       menu codes 1-5 -> cancellation, complaint, request, praise, unclear
  evidence     sentence number (1 = first sentence) -> the exact sentence text from insight.segment, so the
               quote is an exact substring; one review splits at '...' where the segmenter does not
  needs_review TRUE/FALSE -> true/false; entities: free-text features, ',' -> ';'
Decisions Eason made on 2026-10-13 after reviewing the contract wording (recorded per review_id below).
"""

import csv
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))
from insight.segment import segment_spans  # noqa: E402

INTENTS = {"1": "cancellation", "2": "complaint", "3": "request", "4": "praise", "5": "unclear"}
TOPICS = ("access", "usability", "playback", "downloads", "catalog", "billing", "support", "other")
DECISIONS = {  # review_id -> (field changes, reason); all decided by Eason
    "47f1406d-4918-4d60-9647-5ca8e610caca": ({"intent": "request"}, "intent was blank; Eason chose request"),
    "0c6ca545-3f89-4da6-b3db-1a352371fb6e": ({"intent": "complaint"}, "generic 'hate this app' is criticism -> complaint (contract)"),
    "47428620-ec21-424d-a515-0b0b0012a5cf": ({"intent": "complaint"}, "generic 'bad app' is criticism -> complaint (contract)"),
    "657f1b77-0183-4b06-bf48-5e6d9ab08f9a": ({"intent": "complaint"}, "generic 'hate this app' is criticism -> complaint (contract)"),
    "1a41c7e1-a655-4c63-b4db-c22bdff18003": ({"intent": "complaint", "severity": "2"},
                                             "generic 'worst app' -> complaint; a complaint is at least severity 2"),
}
SPLIT_AT_ELLIPSIS = {"16d640e9-b281-4746-9562-c7dbcf7126b6"}  # 'not...everything': Eason counted two sentences


def sentences(rid, text):
    segs = [text[s:e] for s, e in segment_spans(text)] or [text]
    if rid in SPLIT_AT_ELLIPSIS:
        out = []
        for seg in segs:
            head, sep, tail = seg.partition("...")
            out += [head + sep, tail] if sep and tail.strip(". ") else [seg]
        segs = [s for s in out if s.strip()]
    return segs


def main():
    src = HERE / "golden_50_labeled_workbook_export.csv"
    rows = list(csv.DictReader(open(src, encoding="utf-8-sig")))
    out, notes = [], []
    for r in rows:
        rid, text = r["review_id"], r["review_text"]
        raw_topic = r["topic"].strip()
        if raw_topic in ("Praise", "Criticism"):
            topic, issue = "other", f"other.general ({raw_topic.lower()})"
        else:
            topic, _, sub = raw_topic.partition(".")
            issue = f"{topic}.{sub.removeprefix(topic + '_')}" if sub else topic
        if topic not in TOPICS:
            raise SystemExit(f"{rid}: unknown topic {raw_topic!r}")
        rec = {"review_id": rid, "review_text": text, "topic": topic, "issue_human": issue,
               "intent": INTENTS.get(r["intent"].strip(), ""), "sentiment": r["sentiment"].strip(),
               "severity": r["severity"].strip(), "entities": ";".join(x.strip() for x in r["entities"].split(",") if x.strip()),
               "needs_review": r["needs_review"].strip().lower(), "decision_note": ""}
        segs = sentences(rid, text)
        n = int(r["evidence_quote"])
        if not 1 <= n <= len(segs):
            raise SystemExit(f"{rid}: evidence sentence {n} but only {len(segs)} sentences")
        rec["evidence_quote"] = segs[n - 1].strip()
        assert rec["evidence_quote"] in text
        if rid in DECISIONS:
            changes, why = DECISIONS[rid]
            rec.update(changes)
            rec["decision_note"] = why
            notes.append(rid)
        if not rec["intent"]:
            raise SystemExit(f"{rid}: intent missing")
        out.append(rec)
    cols = ["review_id", "review_text", "topic", "issue_human", "intent", "sentiment", "severity", "entities",
            "evidence_quote", "needs_review", "decision_note"]
    with open(HERE / "golden_50_labeled.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, lineterminator="\n")
        w.writeheader()
        w.writerows(out)
    print(f"wrote {len(out)} labelled reviews to evals/golden/golden_50_labeled.csv ({len(notes)} recorded decisions)")


if __name__ == "__main__":
    main()

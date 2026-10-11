"""Terminal labeller for the golden 50 (a person labels; no model is involved).

    python -m insight label-golden            # resumes where you stopped; saves after every review

Shows only the review text (stars and the other source fields are hidden so they cannot stand in for
reading the text), asks for topic, intent, severity, sentiment, evidence sentence and needs_review,
and writes the filled copy to evals/golden/golden_50_labeled.csv. Several accepted labels for a
genuinely ambiguous case: type them separated by '|', e.g. 3|4.
"""

import csv
import os
import tempfile
import textwrap
from pathlib import Path

from . import labels
from .segment import segment_spans
from .util import PROJECT_ROOT

SOURCE = PROJECT_ROOT / "Final Assignment - Spotify Reviews Dataset" / "golden_50_to_label.csv"
OUT = PROJECT_ROOT / "evals" / "golden" / "golden_50_labeled.csv"
LABEL_COLS = ("topic", "intent", "sentiment", "severity", "entities", "evidence_quote", "needs_review")
SENTIMENTS = [v for v, _ in labels.SENTIMENT_LEVELS]

INTENT_HELP = {
    "cancellation": "explicitly leaving / uninstalling / cancelling, or threatening to",
    "complaint": "negative experience, incl. mixed praise+criticism, generic 'bad app'",
    "request": "wants a change, nothing reported broken",
    "praise": "only positive",
    "unclear": "meaningless, unrelated, bare boycott slogan, cannot tell",
}


class Back(Exception):
    pass


class Quit(Exception):
    pass


def _ask(prompt, options, multi=True, allow_blank=False):
    """options: list of values; user types 1-based numbers ('2|3' for several accepted)."""
    while True:
        raw = input(prompt).strip()
        if raw.lower() in ("q", "quit"):
            raise Quit
        if raw.lower() in ("b", "back"):
            raise Back
        if not raw and allow_blank:
            return ""
        parts = [p.strip() for p in raw.split("|") if p.strip()]
        if parts and (multi or len(parts) == 1) and all(p.isdigit() and 1 <= int(p) <= len(options) for p in parts):
            picked = []
            for p in parts:
                v = str(options[int(p) - 1])
                if v not in picked:
                    picked.append(v)
            return "|".join(picked)
        print(f"  enter {'one or more numbers separated by |' if multi else 'one number'} from 1 to {len(options)}"
              f"{', Enter to skip' if allow_blank else ''}, b = back, q = quit")


def _menu(title, items):
    print(f"\n{title}")
    for n, (value, desc) in enumerate(items, 1):
        print(f"  {n}. {value:<13} {desc}")


def _save(rows, fieldnames):
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=OUT.parent, prefix=".golden-", suffix=".csv")
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, OUT)


def _label_one(row, n, total):
    text = row["review_text"]
    segs = [text[s:e] for s, e in segment_spans(text)] or [text]
    print("\n" + "=" * 78)
    print(f"Review {n}/{total}   id {row['review_id']}")
    print("-" * 78)
    for i, s in enumerate(segs, 1):
        print(textwrap.fill(f"[{i}] {s}", width=78, subsequent_indent="    "))
    print("-" * 78)
    _menu("TOPIC (main problem; highest severity, then first mentioned; praise = first praised feature)",
          [(t, labels.TOPIC_DEFINITIONS[t]) for t in labels.TOPICS])
    topic = _ask("topic> ", list(labels.TOPICS))
    _menu("INTENT (first that applies)", [(i, INTENT_HELP[i]) for i in labels.INTENT_PRECEDENCE])
    intent = _ask("intent> ", list(labels.INTENT_PRECEDENCE))
    _menu("SEVERITY (reported impact only; stars/anger/price/leaving do not raise it)",
          [(k, v) for k, v in labels.SEVERITY.items()])
    severity = _ask("severity> ", [1, 2, 3, 4, 5])
    _menu("SENTIMENT", [(v, d) for v, d in labels.SENTIMENT_LEVELS])
    sentiment = _ask("sentiment> ", SENTIMENTS, multi=False)
    if len(segs) > 1:
        ev = _ask(f"evidence sentence 1-{len(segs)} (Enter = skip)> ", list(range(1, len(segs) + 1)),
                  multi=False, allow_blank=True)
        quote = segs[int(ev) - 1] if ev else ""
    else:
        quote = segs[0]
    nr = _ask("needs_review? 1 = no, 2 = yes (ambiguous / missing context)> ", ["false", "true"], multi=False)
    return {"topic": topic, "intent": intent, "severity": severity, "sentiment": sentiment,
            "evidence_quote": quote, "needs_review": nr, "entities": row.get("entities", "")}


def main(source=None):
    src = Path(source) if source else (OUT if OUT.exists() else SOURCE)
    with open(src, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)
    missing = [c for c in LABEL_COLS if c not in fieldnames]
    if missing:
        raise SystemExit(f"{src} lacks label columns {missing}")
    todo = [i for i, r in enumerate(rows) if not (r["topic"] and r["intent"] and r["severity"])]
    print(f"Golden labelling: {len(rows) - len(todo)} of {len(rows)} done; saving to {OUT}")
    print("Read docs/labels.md first. Several accepted labels for a genuinely ambiguous case: e.g. 3|4.")
    pos = 0
    try:
        while pos < len(todo):
            i = todo[pos]
            try:
                rows[i].update(_label_one(rows[i], i + 1, len(rows)))
                _save(rows, fieldnames)
                pos += 1
            except Back:
                if pos > 0:
                    pos -= 1
                    for c in ("topic", "intent", "severity", "sentiment", "evidence_quote", "needs_review"):
                        rows[todo[pos]][c] = ""
                    _save(rows, fieldnames)
    except (Quit, EOFError, KeyboardInterrupt):
        print("\nStopped; progress is saved. Run the same command to continue.")
        return
    print(f"\nAll {len(rows)} reviews labelled -> {OUT}")

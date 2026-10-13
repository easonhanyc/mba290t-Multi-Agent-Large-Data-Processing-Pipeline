"""Offline: would combining the typed classifier (OpenAI Decisions) with batched Luna help? (no model calls)

Reads the human golden labels and two saved candidate runs on the same 50 texts, then scores
  luna       - the batched LLM labels alone
  decisions  - the Decisions classifier alone
  agree-only - both models agree (the subset a hybrid would accept automatically) and how often they disagree
  rule       - predeclared hybrid rule: on disagreement take Decisions when its confidence >= threshold, else Luna
for topic, intent and severity. Human labels are read here only; they never reach a prompt.

  python3 evals/ensemble_golden.py --labels evals/golden/golden_50_labeled.csv \
      --luna runs/golden-luna-none --decisions runs/golden-decisions --out evals/golden/ensemble.json
"""

import argparse
import csv
import json
import sqlite3
from pathlib import Path

FIELDS = ("topic", "intent", "severity")
THRESHOLD = 0.80  # predeclared before looking at golden results


def _split(v):
    return [x.strip() for x in (v or "").split("|") if x.strip()]


def load_run(run_dir):
    con = sqlite3.connect(f"file:{Path(run_dir) / 'state.sqlite'}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    out = {}
    for r in con.execute("SELECT review_id, topic, intent, severity, detail FROM results WHERE status='completed'"):
        detail = json.loads(r["detail"] or "{}")
        conf = ((detail.get("primary") or {}).get("confidence")) or {}
        out[r["review_id"]] = {"topic": r["topic"], "intent": r["intent"], "severity": int(r["severity"]),
                               "confidence": {"topic": conf.get("issue"), "intent": conf.get("intent"),
                                              "severity": conf.get("severity")}}
    con.close()
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--labels", required=True)
    ap.add_argument("--luna", required=True)
    ap.add_argument("--decisions", required=True)
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    with open(a.labels, encoding="utf-8-sig", newline="") as f:
        gold = {r["review_id"]: r for r in csv.DictReader(f) if r.get("topic") and r.get("intent") and r.get("severity")}
    luna, dec = load_run(a.luna), load_run(a.decisions)
    ids = sorted(i for i in gold if i in luna and i in dec)
    res = {"cases_labelled": len(gold), "cases_with_both_predictions": len(ids), "threshold": THRESHOLD, "fields": {}}
    for f in FIELDS:
        acc = lambda i, v: (str(v) if f == "severity" else v) in _split(gold[i][f])
        lc = sum(acc(i, luna[i][f]) for i in ids)
        dc = sum(acc(i, dec[i][f]) for i in ids)
        agree = [i for i in ids if luna[i][f] == dec[i][f]]
        agree_ok = sum(acc(i, luna[i][f]) for i in agree)
        rule_ok = 0
        for i in ids:
            if luna[i][f] == dec[i][f]:
                rule_ok += acc(i, luna[i][f])
            else:
                c = dec[i]["confidence"].get(f)
                pick = dec[i][f] if isinstance(c, (int, float)) and c >= THRESHOLD else luna[i][f]
                rule_ok += acc(i, pick)
        n = len(ids) or 1
        res["fields"][f] = {
            "luna_accuracy": round(lc / n, 4), "decisions_accuracy": round(dc / n, 4),
            "agreement_rate": round(len(agree) / n, 4),
            "accuracy_when_agree": round(agree_ok / len(agree), 4) if agree else None,
            "disagreements": len(ids) - len(agree),
            "luna_right_on_disagreement": sum(acc(i, luna[i][f]) for i in ids if i not in agree),
            "decisions_right_on_disagreement": sum(acc(i, dec[i][f]) for i in ids if i not in agree),
            "rule_accuracy": round(rule_ok / n, 4)}
    res["note"] = ("Diagnostic on at most 50 cases; differences of one or two cases are noise. Decisions answered the "
                   "full Jev-style question set (one review per request), Luna the batched production prompt.")
    text = json.dumps(res, indent=2)
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()

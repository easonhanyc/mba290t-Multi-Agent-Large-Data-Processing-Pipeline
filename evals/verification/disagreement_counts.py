"""Counts behind evals/verification/disagreement_analysis.md, from a run's saved files (no model calls).

Reads <run>/verification/report.json and sample.json (blind verifier vs enricher on the declared sample), <run>/enriched.jsonl.gz,
<run>/membership.csv, <run>/area_rollup.json, <run>/analysis/robustness.json and the input CSV (review text for the
payment-word check). Writes a JSON of every number the analysis cites, plus the deterministic review samples it
reads (random 20 disagreements; premium-only topic disagreements; severity 3 -> 4), with text and both labels.

  python3 evals/verification/disagreement_counts.py --run-dir runs/final-200k-v2 --input data/analysis_200k.csv \
      --out evals/verification/disagreement_counts.json
"""

import argparse
import collections
import csv
import gzip
import hashlib
import json
import re
from pathlib import Path

KW = re.compile(r"premium|subscri|\bpa(y|id|ying)\b|\bfree\b|\bbuy\b|money|trial|\$", re.I)
RANKED = ("complaint", "cancellation")


def lowest(items, salt, n, key="review_id"):
    return sorted(items, key=lambda d: hashlib.sha256(f"{salt}:{d[key]}".encode()).hexdigest())[:n]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--input", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    run = Path(a.run_dir)
    rep = json.loads((run / "verification" / "report.json").read_text())
    dis = rep["disagreements"]
    enr = {}
    with gzip.open(run / "enriched.jsonl.gz", "rt", encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            enr[r["review_id"]] = r
    text = {r["review_id"]: r["review_text"] for r in csv.DictReader(open(a.input, encoding="utf-8"))}
    issue = lambda rid: f"{(enr.get(rid) or {}).get('topic')}.{(enr.get(rid) or {}).get('subtopic')}"
    by_fields = collections.Counter("+".join(sorted(d["fields"])) for d in dis)
    direction = {f: collections.Counter(f"{d['enricher'][f]} -> {d['verifier'][f]}" for d in dis if f in d["fields"])
                 for f in ("topic", "intent", "severity")}
    sev = [d for d in dis if "severity" in d["fields"]]
    higher = sum(int(d["verifier"]["severity"]) > int(d["enricher"]["severity"]) for d in sev)
    topic_by_issue = collections.Counter(f"{issue(d['review_id'])} -> {d['verifier']['topic']}" for d in dis
                                         if "topic" in d["fields"])
    s34 = [d for d in sev if str(d["enricher"]["severity"]) == "3" and str(d["verifier"]["severity"]) == "4"]
    sample_ids = set(json.loads((run / "verification" / "sample.json").read_text())["review_ids"])
    sampled_prem = [rid for rid in sample_ids if issue(rid) == "billing.premium_only"] if sample_ids else []
    prem_topic = [d for d in dis if issue(d["review_id"]) == "billing.premium_only" and "topic" in d["fields"]]
    prem_topic_kwfree = [d for d in prem_topic if not KW.search(text.get(d["review_id"], ""))]
    prem_agree = [rid for rid in sampled_prem if rid not in {d["review_id"] for d in prem_topic}]
    mem = [r["review_id"] for r in csv.DictReader(open(run / "membership.csv", encoding="utf-8"))
           if r["issue_id"] == "billing.premium_only"]
    no_kw = [m for m in mem if not KW.search(text[m])]
    rollup = json.loads((run / "area_rollup.json").read_text())
    rob = json.loads((run / "analysis" / "robustness.json").read_text()) if (run / "analysis" / "robustness.json").exists() else {}
    flagged = sum(1 for d in dis if (enr.get(d["review_id"]) or {}).get("needs_review"))
    sampled_flagged = sum(1 for rid in sample_ids if (enr.get(rid) or {}).get("needs_review")) if sample_ids else None

    def card(d):
        e = enr.get(d["review_id"]) or {}
        return {"review_id": d["review_id"], "fields": d["fields"], "text": text.get(d["review_id"], "")[:400],
                "enricher": {"issue": issue(d["review_id"]), "intent": d["enricher"]["intent"],
                             "severity": d["enricher"]["severity"], "labeled_by": e.get("labeled_by")},
                "verifier": {k: d["verifier"].get(k) for k in ("topic", "intent", "severity", "confidence")}}

    rnd = lowest(dis, "disagreement-review-v1", 20)
    rnd_ids = {d["review_id"] for d in rnd}
    out = {
        "run_dir": str(run), "label_config": rep.get("label_config"), "compared": rep.get("compared"),
        "agreement": rep.get("agreement"), "disagreements": len(dis), "by_fields": dict(by_fields.most_common()),
        "single_field": sum(v for k, v in by_fields.items() if "+" not in k),
        "severity_abs_diff_counts": rep.get("severity_abs_diff_counts"),
        "direction_top": {f: dict(c.most_common(8)) for f, c in direction.items()},
        "severity_verifier_higher": higher, "severity_verifier_lower": len(sev) - higher,
        "topic_by_enricher_issue_top": dict(topic_by_issue.most_common(8)),
        "severity_3_to_4": len(s34), "severity_3_to_4_premium_only": sum(issue(d["review_id"]) == "billing.premium_only" for d in s34),
        "by_enricher_tier": rep.get("by_enricher_tier"),
        "disagreements_with_needs_review": flagged, "sampled_with_needs_review": sampled_flagged,
        "verifier_confidence_on_disagreements": dict(collections.Counter(d["verifier"].get("confidence") for d in dis)),
        "disagreements_ranked_intent": sum(d["enricher"]["intent"] in RANKED for d in dis),
        "premium_only_sampled": len(sampled_prem), "premium_only_topic_disagreements": len(prem_topic),
        "premium_only_topic_disagreements_to": dict(collections.Counter(d["verifier"]["topic"] for d in prem_topic).most_common()),
        "premium_only_topic_disagreements_without_payment_word": len(prem_topic_kwfree),
        "premium_only_agreeing_without_payment_word": sum(not KW.search(text.get(r, "")) for r in prem_agree),
        "premium_only_agreeing": len(prem_agree),
        "full_run_premium_only_members": len(mem), "full_run_premium_only_without_payment_word": len(no_kw),
        "full_run_premium_only_without_payment_word_severity_sum": sum(int(enr[m]["severity"]) for m in no_kw),
        "area_rollup": rollup, "robustness": rob,
        "random_20": [card(d) for d in rnd],
        "premium_boundary_10": [card(d) for d in lowest([d for d in prem_topic if d["review_id"] not in rnd_ids],
                                                       "premium-boundary-v1", 10)],
        "severity_3_4_10": [card(d) for d in lowest([d for d in s34 if d["review_id"] not in rnd_ids], "severity-3-4-v1", 10)],
    }
    Path(a.out).write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {a.out}: {len(dis)} disagreements of {rep.get('compared')} compared")


if __name__ == "__main__":
    main()

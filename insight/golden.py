"""Golden-set evaluation: saved predictions vs. human labels (no model calls).

Labelling format (golden_50_to_label.csv columns, filled by a person):
  topic, intent, severity  - one label, or several accepted labels separated by '|' for genuinely
                             ambiguous cases (e.g. 'playback|downloads'); counted as ambiguous
  sentiment                - number in [-1, 1]
  entities                 - terms separated by ';' (may be blank)
  evidence_quote           - exact supporting substring chosen by the labeller (may be blank)
  needs_review             - true/false
The human labels are read here only; they never enter a prompt (ingest stores six fields only).
"""

import csv
import json
from collections import Counter

from . import labels


def _split(v):
    return [x.strip() for x in (v or "").split("|") if x.strip()]


def _f1(tp, support, predicted):
    return round(2 * tp / (support + predicted), 4) if (support + predicted) else None


def score_golden(labels_csv, store, cfg):
    lc = cfg.label_config()
    with open(labels_csv, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    pending = [r["review_id"] for r in rows if not (r.get("topic") and r.get("intent") and r.get("severity"))]
    cases = []
    totals = Counter()
    sev_dist = Counter()
    sent_err = []
    pairs = {"topic": [], "intent": []}
    review_flag = Counter()
    for r in rows:
        if r["review_id"] in pending:
            continue
        acc = {"topic": _split(r["topic"]), "intent": _split(r["intent"]),
               "severity": [int(x) for x in _split(r["severity"])]}
        bad = [k for k, v in acc.items() if not v or any(x not in (labels.TOPICS if k == "topic" else labels.INTENTS
                                                                      if k == "intent" else (1, 2, 3, 4, 5)) for x in v)]
        if bad:
            raise ValueError(f"invalid golden labels for {r['review_id']}: {bad}")
        pred = store.result(r["review_id"], lc)
        p = dict(pred) if pred is not None and pred["status"] == "completed" else None
        case = {"review_id": r["review_id"], "text": r["review_text"][:300], "accepted": acc,
                "ambiguous": any(len(v) > 1 for v in acc.values()), "prediction": None}
        totals["cases"] += 1
        totals["ambiguous"] += case["ambiguous"]
        if p is None:
            totals["missing_predictions"] += 1
            case["result"] = "missing or quarantined prediction (counts as incorrect)"
            cases.append(case)
            continue
        case["prediction"] = {k: p[k] for k in ("topic", "intent", "severity", "sentiment", "needs_review", "evidence_quote")}
        case["prediction"]["labeled_by"] = p["labeled_by"]
        ok = {}
        for k in ("topic", "intent", "severity"):
            ok[k] = p[k] in acc[k]
            totals[f"{k}_correct"] += ok[k]
            if k in pairs and len(acc[k]) == 1:
                pairs[k].append((acc[k][0], p[k]))
        totals["joint_correct"] += all(ok.values())
        d = min(abs(int(p["severity"]) - s) for s in acc["severity"])
        sev_dist[d] += 1
        if r.get("sentiment", "").strip():
            e = abs(float(p["sentiment"]) - float(r["sentiment"]))
            sent_err.append(e)
            totals["sentiment_within_tolerance"] += e <= labels.SENTIMENT_TOLERANCE + 1e-9
        human_nr = (r.get("needs_review", "").strip().lower() == "true")
        review_flag[(human_nr, bool(p["needs_review"]))] += 1
        case["correct"] = ok
        case["severity_distance"] = d
        case["quote_is_exact_substring"] = p["evidence_quote"] in r["review_text"]
        supported = set(labels.extract_entities(r["review_text"]))
        case["entities_unsupported"] = [x for x in json.loads(p["entities"] or "[]") if x not in supported]
        totals["entities_unsupported"] += len(case["entities_unsupported"])
        cases.append(case)
    n = totals["cases"]
    rate = lambda x: round(x / n, 4) if n else None
    per_class = {}
    for field, pr in pairs.items():
        classes = sorted({a for a, _ in pr})
        per_class[field] = {}
        for c in classes:
            tp = sum(a == c and b == c for a, b in pr)
            support = sum(a == c for a, _ in pr)
            predicted = sum(b == c for _, b in pr)
            per_class[field][c] = {"support": support, "predicted": predicted,
                                   "recall": round(tp / support, 4) if support else None,
                                   "precision": round(tp / predicted, 4) if predicted else None,
                                   "f1": _f1(tp, support, predicted)}
    confusion = {f: dict(Counter(f"{a} -> {b}" for a, b in pr if a != b).most_common(15)) for f, pr in pairs.items()}
    return {
        "status": "pending_labels" if pending else "ready",
        "pending_review_ids": pending,
        "label_config": lc,
        "cases": n,
        "ambiguous_cases": totals["ambiguous"],
        "missing_or_quarantined_predictions": totals["missing_predictions"],
        "agreement": {k: rate(totals[f"{k}_correct"]) for k in ("topic", "intent", "severity", "joint")},
        "severity": {"exact": rate(totals["severity_correct"]),
                     "mean_abs_error": round(sum(k * v for k, v in sev_dist.items()) / sum(sev_dist.values()), 4)
                     if sev_dist else None,
                     "distance_counts": {str(k): v for k, v in sorted(sev_dist.items())}},
        "sentiment": {"tolerance": labels.SENTIMENT_TOLERANCE, "labelled": len(sent_err),
                      "mean_abs_error": round(sum(sent_err) / len(sent_err), 4) if sent_err else None,
                      "within_tolerance": round(totals["sentiment_within_tolerance"] / len(sent_err), 4) if sent_err else None},
        "entities_unsupported_total": totals["entities_unsupported"],
        "needs_review_vs_human": {f"human={h},model={m}": c for (h, m), c in review_flag.items()},
        "per_class_singleton": per_class,
        "confusion_singleton": confusion,
        "cases_detail": cases,
        "note": "Missing/quarantined predictions count as incorrect. Fifty cases are a diagnostic, not a precise accuracy estimate.",
    }


def error_analysis_md(res, title="Golden-set comparison"):
    """Per-field summary plus every disagreement, for a person to categorise (model error / ambiguity / label error)."""
    a = res["agreement"]
    L = [f"# {title}", "", f"Label config: `{res['label_config']}`", "",
         f"{res['cases']} human-labelled reviews ({res['ambiguous_cases']} with several accepted labels); "
         f"{res['missing_or_quarantined_predictions']} missing or quarantined predictions count as wrong.", "",
         "| Field | Agreement |", "|---|---:|",
         f"| topic | {a['topic']} |", f"| intent | {a['intent']} |", f"| severity (exact) | {a['severity']} |",
         f"| all three | {a['joint']} |",
         f"| severity mean absolute error | {res['severity']['mean_abs_error']} |",
         f"| sentiment within +/-{res['sentiment']['tolerance']} | {res['sentiment']['within_tolerance']} |", "",
         "## Per-class (unambiguous cases only)", ""]
    for field, classes in res["per_class_singleton"].items():
        L += [f"**{field}**", "", "| Class | Support | Predicted | Precision | Recall | F1 |", "|---|---:|---:|---:|---:|---:|"]
        for c, m in classes.items():
            L.append(f"| {c} | {m['support']} | {m['predicted']} | {m['precision']} | {m['recall']} | {m['f1']} |")
        L.append("")
    L += ["## Confusions (human -> model)", ""]
    for field, conf in res["confusion_singleton"].items():
        L.append(f"- {field}: " + (", ".join(f"`{k}` x{v}" for k, v in conf.items()) or "none"))
    L += ["", "## Every disagreement", "",
          "| Review | Text | Human (accepted) | Model | Wrong fields | Labelled by |", "|---|---|---|---|---|---|"]
    for c in res["cases_detail"]:
        p = c.get("prediction")
        wrong = [k for k, ok in (c.get("correct") or {}).items() if not ok] if p else ["missing"]
        if not wrong:
            continue
        acc = "; ".join(f"{k}={'|'.join(map(str, v))}" for k, v in c["accepted"].items())
        model = f"topic={p['topic']}; intent={p['intent']}; severity={p['severity']}" if p else "-"
        text = c["text"].replace("|", "/").replace("\n", " ")
        L.append(f"| `{c['review_id'][:8]}` | {text[:160]} | {acc} | {model} | {', '.join(wrong)} | "
                 f"{(p or {}).get('labeled_by', '-')} |")
    return "\n".join(L) + "\n"

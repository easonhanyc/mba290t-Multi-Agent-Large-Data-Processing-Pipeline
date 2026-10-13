"""Write evals/golden/error_analysis.md from the saved golden scores (no model calls; numbers read from JSON).

Inputs: evals/golden/results.json (final run), evals/golden/candidates/*.json (candidate setups on the same
50 texts), evals/golden/ensemble.json (Luna + Decisions combination), evals/golden/golden_50_labeled.csv.
"""

import collections
import csv
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
CANDIDATES = [("Luna, effort none (production primary)", "candidates/golden-luna-none.json"),
              ("Luna, effort low (production fallback1)", "candidates/golden-luna-low.json"),
              ("OpenAI Decisions (typed classifier)", "candidates/golden-decisions.json"),
              ("Final 200k run (none + low fallback on flagged)", "results.json")]


def load(rel):
    return json.loads((HERE / rel).read_text(encoding="utf-8"))


def joint(c):
    return bool(c.get("correct")) and all(c["correct"].values())


def mcnemar(a, b):
    """Exact two-sided McNemar p for 'joint correct' between two setups on the same cases."""
    x = sum(joint(a[i]) and not joint(b[i]) for i in a)
    y = sum(joint(b[i]) and not joint(a[i]) for i in a)
    n = x + y
    p = 1.0 if n == 0 else min(1.0, 2 * sum(math.comb(n, k) for k in range(min(x, y) + 1)) / 2 ** n)
    return x, y, p


def main():
    gold = {r["review_id"]: r for r in csv.DictReader(open(HERE / "golden_50_labeled.csv", encoding="utf-8"))}
    res = {name: load(p) for name, p in CANDIDATES}
    L = ["# Golden-set evaluation and error analysis", "",
         f"{len(gold)} reviews labelled by hand by Eason (conventions and the conversion from his workbook: "
         "`docs/labels.md`, `evals/golden/convert_labels.py`). Every setup below labelled the same 50 texts; "
         "missing predictions would count as wrong (there were none). Fifty cases are a diagnostic: a few cases "
         "move a figure by several points.", "",
         "## Per-field agreement", "",
         "| Setup | Topic | Intent | Severity exact | All three | Severity MAE | Sentiment within 0.5 | Flags needs_review (human: 6) |",
         "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for name, d in res.items():
        a, nr = d["agreement"], d["needs_review_vs_human"]
        flagged = sum(v for k, v in nr.items() if k.endswith("model=True"))
        L.append(f"| {name} | {a['topic']:.0%} | {a['intent']:.0%} | {d['severity']['exact']:.0%} | {a['joint']:.0%} | "
                 f"{d['severity']['mean_abs_error']} | {d['sentiment']['within_tolerance']:.0%} | {flagged} |")
    cases = {name: {c["review_id"]: c for c in d["cases_detail"]} for name, d in res.items()}
    names = [n for n, _ in CANDIDATES]
    x, y, p = mcnemar(cases[names[1]], cases[names[0]])
    L += ["", f"Effort low vs effort none on 'all three correct': low alone right on {x} reviews, none alone on {y}; "
          f"exact McNemar two-sided p = {p:.3f}. The direction favours effort low, but the difference is not "
          "statistically reliable at n = 50.", "",
          "**Decision.** The predeclared rule (best golden 'all three' agreement within the cost cap) points to "
          "effort low as the primary. The golden labels were finished after the final run, which used effort none "
          "for the batched primary and effort low for the 13,639 flagged texts (fallback1, cap 10%). Given the "
          "non-significant gap and that most disagreements below are labelling-convention differences, the final "
          "run was kept and this is disclosed rather than re-run (decided with Eason on 2026-10-13).", ""]
    fin = cases[names[3]]
    L += ["## Where the final run disagrees with the human labels", ""]
    for field in ("topic", "intent", "severity"):
        errs = collections.Counter()
        for c in fin.values():
            if c.get("correct") and not c["correct"][field]:
                errs[f"{'|'.join(map(str, c['accepted'][field]))} -> {c['prediction'][field]}"] += 1
        L.append(f"- **{field}** ({sum(errs.values())} of {len(fin)}): " + ", ".join(f"{k} x{v}" for k, v in errs.most_common()))
    conv = [i for i, c in fin.items() if c.get("correct") and not c["correct"]["intent"]
            and c["accepted"]["intent"] == ["request"] and c["prediction"]["intent"] == "complaint"]
    praise_topic = [i for i, c in fin.items() if c.get("correct") and not c["correct"]["topic"]
                    and c["accepted"]["topic"] == ["other"] and gold[i]["issue_human"].endswith("(praise)")]
    n = len(fin)
    intent_ok = sum(1 for c in fin.values() if c.get("correct") and c["correct"]["intent"])
    L += ["", "Patterns:", "",
          f"1. **Request vs complaint ({len(conv)} reviews).** Eason labels a review that reports a problem and asks "
          "for a fix as *request*; the contract precedence (complaint before request) that the models follow makes "
          f"it *complaint*. Excluding these, final-run intent agreement is {intent_ok}/{n - len(conv)} = "
          f"{intent_ok / (n - len(conv)):.0%}. This is a convention difference, kept on purpose and documented.",
          f"2. **Praise naming a feature ({len(praise_topic)} reviews).** Eason maps praise to topic *other*; the "
          "contract rule the models apply picks the first praised feature (recommendations, ads, the catalog).",
          "3. **Blocked vs degraded severity (human 4, model 3).** Intermittent stops, lyrics that sometimes fail "
          "to load, and free-tier limits on choosing or rewinding songs: Eason reads them as a blocked core task, "
          "the models as the rubric's level 3 ('a degraded or restricted function').",
          "4. **Remaining intent misses (6).** Four are non-English, slang or name-only texts ('Lhat ng song nasa "
          "spotify', 'Bheekhmangon', a name with 'Unconditional love', an unclear sentence about a free dollar); one "
          "is a support story that ends well (human praise, model complaint); one mixes a boycott with religion "
          "(human unclear, model complaint).", ""]
    ens = load("ensemble.json")
    L += ["## Would combining the typed classifier with Luna help?", "",
          "| Field | Luna | Decisions | Models agree | Accuracy when they agree | Combined rule |", "|---|---:|---:|---:|---:|---:|"]
    for f, v in ens["fields"].items():
        L.append(f"| {f} | {v['luna_accuracy']:.0%} | {v['decisions_accuracy']:.0%} | {v['agreement_rate']:.0%} | "
                 f"{v['accuracy_when_agree']:.0%} | {v['rule_accuracy']:.0%} |")
    L += ["", "The two models agree on most texts and share the same misses, so a cross-check would rarely catch an "
          "error here; the combined rule does not beat Luna alone. Together with the Decisions beta's 50 "
          "requests/day limit, this is why the hybrid backend is not used at scale (`docs/model_choice.md`).", "",
          "## Other checks", "",
          f"- Evidence quotes: every final-run quote is an exact substring of its review "
          f"({sum(1 for c in fin.values() if c.get('quote_is_exact_substring'))}/{n}).",
          f"- Entities: {res[names[3]]['entities_unsupported_total']} predicted entities not found in the text. "
          "Eason's entities are feature descriptions in his own words, so they are compared case by case below.",
          f"- needs_review vs human: {res[names[3]]['needs_review_vs_human']}.", "",
          "Case-by-case list of every disagreement (with the human entities and quotes): `results_disagreements.md`."]
    (HERE / "error_analysis.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("wrote evals/golden/error_analysis.md")


if __name__ == "__main__":
    main()

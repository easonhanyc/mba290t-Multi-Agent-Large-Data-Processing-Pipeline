"""Write evals/golden/error_analysis.md from the saved scores (no model calls; every number read from JSON).

Inputs: evals/golden/candidates/*.json (the setups compared on the golden 50 before the final run),
evals/golden/results.json (final run), evals/golden/candidates/final-200k-superseded.json (the superseded first final
run), evals/golden/ensemble.json, evals/golden/golden_50_labeled.csv, the final run's verification report, and when
present evals/quote_support/summary.json (do the quotes support the labels).
"""

import collections
import csv
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVALS = HERE.parent
CANDIDATES = [("Luna, effort none", "candidates/golden-luna-none.json"),
              ("Luna, effort low", "candidates/golden-luna-low.json"),
              ("OpenAI Decisions (typed classifier)", "candidates/golden-decisions.json")]
FINAL = ("Final run (the effort-low candidate's configuration)", "results.json")
SUPERSEDED = ("Superseded first final run (effort none, effort low on flagged texts)", "candidates/final-200k-superseded.json")


def final_run_dir(final):
    """The run the final golden scores came from (results.json records its label_config; the run dir is fixed here)."""
    return "runs/final-200k-v2"


def golden_requests(run_dir, gold_ids):
    """Successful primary enrichment requests that carried golden texts, from the committed grading/calls.jsonl(.gz)."""
    import gzip
    path = EVALS.parent / run_dir / "grading" / "calls.jsonl"
    opener = (lambda: gzip.open(str(path) + ".gz", "rt", encoding="utf-8")) if not path.exists() else (lambda: open(path, encoding="utf-8"))
    n = 0
    with opener() as f:
        for line in f:
            c = json.loads(line)
            if c.get("role") == "enrich" and c.get("tier", "primary") == "primary" and c.get("outcome") == "succeeded" \
                    and gold_ids & set(c.get("review_ids") or []):
                n += 1
    return n


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def joint(c):
    return bool(c.get("correct")) and all(c["correct"].values())


def mcnemar(a, b):
    """Exact two-sided McNemar p for 'all three correct' between two setups on the same cases."""
    x = sum(joint(a[i]) and not joint(b[i]) for i in a if i in b)
    y = sum(joint(b[i]) and not joint(a[i]) for i in a if i in b)
    n = x + y
    p = 1.0 if n == 0 else min(1.0, 2 * sum(math.comb(n, k) for k in range(min(x, y) + 1)) / 2 ** n)
    return x, y, p


def row(name, d):
    a, nr = d["agreement"], d["needs_review_vs_human"]
    flagged = sum(v for k, v in nr.items() if k.endswith("model=True"))
    return (f"| {name} | {a['topic']:.0%} | {a['intent']:.0%} | {d['severity']['exact']:.0%} | {a['joint']:.0%} | "
            f"{d['severity']['mean_abs_error']} | {d['sentiment']['within_tolerance']:.0%} | {flagged} |")


HEAD = ["| Setup | Topic | Intent | Severity exact | All three | Severity MAE | Sentiment within 0.5 | Flags needs_review |",
        "|---|---:|---:|---:|---:|---:|---:|---:|"]


def cases(d):
    return {c["review_id"]: c for c in d["cases_detail"]}


def misses(fin, field):
    errs = collections.Counter()
    for c in fin.values():
        if c.get("correct") and not c["correct"][field]:
            errs[f"{'|'.join(map(str, c['accepted'][field]))} -> {c['prediction'][field]}"] += 1
    return errs


def main():
    gold = {r["review_id"]: r for r in csv.DictReader(open(HERE / "golden_50_labeled.csv", encoding="utf-8"))}
    cand = {name: load(HERE / p) for name, p in CANDIDATES}
    final, sup = load(HERE / FINAL[1]), load(HERE / SUPERSEDED[1])
    cn = [n for n, _ in CANDIDATES]
    L = ["# Golden-set evaluation and error analysis", "",
         f"{len(gold)} reviews labelled by hand by Eason (conventions and the conversion from his workbook: `docs/labels.md`, "
         "`evals/golden/convert_labels.py`). Human labels are read only by the scorer; they never reach a prompt. Missing "
         "predictions would count as wrong (there were none). Fifty cases are a diagnostic: one case moves a figure by 2 points.", "",
         "## 1. Choosing the setup", "",
         "Each candidate enriched the same 50 texts (`runs/golden-*`, `scripts/live.sh golden-candidates`):", "", *HEAD]
    L += [row(n, cand[n]) for n in cn]
    x, y, p = mcnemar(cases(cand[cn[1]]), cases(cand[cn[0]]))
    best = max(cn, key=lambda n: cand[n]["agreement"]["joint"])
    L += ["", f"**Rule (declared before scoring):** the best 'all three correct' within the cost cap. **{best}** wins "
          f"({cand[best]['agreement']['joint']:.0%}). Against effort none, effort low alone was right on {x} reviews and effort "
          f"none alone on {y} (exact McNemar two-sided p = {p:.3f}), so the direction is clear but the gap is small at n = 50.", "",
          (f"The final run uses that candidate's exact configuration: `label_config` `{final['label_config']}` on every record, the "
           "same string as `runs/golden-luna-low` (`config/pipeline.toml`: `effort = \"low\"`, `max_output_tokens_per_review = 200`, "
           "fallback1 `max_fraction = 0.015`). " if final["label_config"] == cand[cn[1]]["label_config"] else
           f"**Check failed:** the final run's `label_config` (`{final['label_config']}`) differs from the effort-low candidate's "
           f"(`{cand[cn[1]]['label_config']}`). ")
          + "The first final run, made before these labels existed with effort none, is kept as "
          "superseded evidence (`runs/final-200k`). Because the golden set chose the setup, the final run's golden scores below "
          "are optimistic (section 3).", "",
          "## 2. Final run on the golden 50", "", *HEAD, row(FINAL[0], final), row(SUPERSEDED[0], sup), ""]
    fx, fy, fp = mcnemar(cases(final), cases(cand[cn[1]]))
    sx, sy, sp = mcnemar(cases(final), cases(sup))
    gids = set(gold)
    L += [f"The same configuration scored {cand[cn[1]]['agreement']['joint']:.0%} 'all three correct' as a candidate and "
          f"{final['agreement']['joint']:.0%} in the final run: the final run alone was right on {fx} reviews and the candidate run "
          f"alone on {fy} (exact McNemar p = {fp:.3f}). Model answers are not deterministic, and the batches differed: the candidate "
          f"run sent the 50 golden texts in {golden_requests('runs/golden-luna-low', gids)} request, the final run spread them over "
          f"{golden_requests('runs/final-200k-v2', gids)} requests among other reviews (the rest reused the label of an identical "
          "text; committed `grading/calls.jsonl(.gz)` of each run). Against the superseded effort-none run the final run alone was "
          f"right on {sx} reviews and the superseded run alone on {sy} (p = {sp:.3f}). On these 50 cases the setups are within "
          "noise of each other; the rule picked the candidate setup, and this is the measured result of running it.", ""]
    fin, n = cases(final), len(final["cases_detail"])
    vr = json.loads((EVALS.parent / final_run_dir(final) / "verification" / "report.json").read_text(encoding="utf-8"))
    va = vr["agreement"]
    L += ["## 3. What these scores can and cannot show", "",
          "The golden 50 chose the setup, so the final run's golden scores carry a small selection bias: among three candidates, "
          "the one that did best on these 50 reviews was kept. No fresh human-labelled set was added after the choice. Two checks "
          "that played no part in the choice cover the final run itself:", "",
          f"- **Blind verifier, declared random sample** ({vr['compared']:,} distinct texts, Claude Haiku, never sees the "
          f"enricher's answer): topic {va['topic']['rate']:.0%}, intent {va['intent']['rate']:.0%}, severity exact "
          f"{va['severity']['rate']:.0%} agreement (`{final_run_dir(final)}/verification/report.json`; disagreements analysed in "
          "`evals/verification/disagreement_analysis.md`). The verifier is another model, not ground truth.",
          "- **Evidence quotes on a declared random sample of the final run** (section 5): whether each quote supports its labels.",
          ""]
    L += ["## 4. Where the final run disagrees with the golden labels", ""]
    for field in ("topic", "intent", "severity"):
        e = misses(fin, field)
        L.append(f"- **{field}** ({sum(e.values())} of {n}): " + (", ".join(f"{k} x{v}" for k, v in e.most_common()) or "none"))
    conv = [i for i, c in fin.items() if c.get("correct") and not c["correct"]["intent"]
            and c["accepted"]["intent"] == ["request"] and c["prediction"]["intent"] == "complaint"]
    praise_topic = [i for i, c in fin.items() if c.get("correct") and not c["correct"]["topic"]
                    and c["accepted"]["topic"] == ["other"] and gold[i]["issue_human"].endswith("(praise)")]
    sev43 = [i for i, c in fin.items() if c.get("correct") and not c["correct"]["severity"]
             and c["accepted"]["severity"] == [4] and c["prediction"]["severity"] == 3]
    intent_ok = sum(1 for c in fin.values() if c.get("correct") and c["correct"]["intent"])
    other_intent = [c for i, c in fin.items() if c.get("correct") and not c["correct"]["intent"] and i not in conv]
    L += ["", "Patterns:", "",
          f"1. **Request vs complaint ({len(conv)} reviews).** Eason labels a review that reports a problem and asks for a fix as "
          "*request*; the contract precedence the models follow (complaint before request) makes it *complaint*. Excluding these, "
          f"intent agreement is {intent_ok}/{n - len(conv)} = {intent_ok / max(1, n - len(conv)):.0%}. A documented convention "
          "difference, kept on purpose.",
          f"2. **Praise naming a feature ({len(praise_topic)} reviews).** Eason maps general praise to topic *other*; the contract "
          "rule the models apply picks the first praised feature.",
          f"3. **Blocked vs degraded severity ({len(sev43)} reviews, human 4, model 3).** Eason reads intermittent failures and "
          "free-tier limits as a blocked core task; the models apply level 3, 'a degraded or restricted function'.",
          f"4. **Other intent misses ({len(other_intent)}):** "
          + ("; ".join(f"`{c['review_id'][:8]}` '{c['text'][:70].strip()}' (human {'|'.join(c['accepted']['intent'])}, model "
                       f"{c['prediction']['intent']})" for c in sorted(other_intent, key=lambda c: c['review_id'])) or "none") + ".", ""]
    L += ["## 5. Evidence quotes, entities and the review flag", "",
          f"- Exact substring (code): {sum(1 for c in fin.values() if c.get('quote_is_exact_substring'))}/{n} final-run quotes.",
          f"- Unsupported entities: {final['entities_unsupported_total']} predicted entities not found in the text. Eason's "
          "entities are feature descriptions in his own words, so they are compared case by case in `results_disagreements.md`.",
          f"- needs_review vs human: {final['needs_review_vs_human']}."]
    qs = EVALS / "quote_support" / "summary.json"
    if qs.exists():
        q = load(qs)["by_set"]
        pct = lambda v: "-" if v is None else f"{v:.0%}"
        for key, label in (("golden/model", "golden 50, final run's quotes"), ("golden/human", "golden 50, Eason's quotes"),
                           ("final_sample/model", "random final-run sample")):
            if key in q:
                t = q[key]
                extra = (f"; the model quoted Eason's evidence sentence in {t['same_sentence_as_human']} of {t['items']} "
                         f"(multi-sentence reviews {t['same_sentence_as_human_multi']})" if "same_sentence_as_human" in t else "")
                L.append(f"- Does the quote support the labels ({label}, blind judge): topic {pct(t['topic']['supported'])}, intent "
                         f"{pct(t['intent']['supported'])}, severity {pct(t['severity']['supported'])} supported; all three "
                         f"{pct(t['all_three_supported'])}{extra}.")
        L.append("- Method and every quote the judge did not accept: `evals/quote_support/report.md`.")
    ens = load(HERE / "ensemble.json")
    L += ["", "## 6. Would combining the typed classifier with Luna help?", "",
          "| Field | Luna (effort none) | Decisions | Models agree | Accuracy when they agree | Combined rule |", "|---|---:|---:|---:|---:|---:|"]
    for f, v in ens["fields"].items():
        L.append(f"| {f} | {v['luna_accuracy']:.0%} | {v['decisions_accuracy']:.0%} | {v['agreement_rate']:.0%} | "
                 f"{v['accuracy_when_agree']:.0%} | {v['rule_accuracy']:.0%} |")
    L += ["", "The two models agree on most texts and share the same misses, so a cross-check would rarely catch an error; the "
          "combined rule does not beat Luna alone. With the Decisions beta's 50 requests/day limit, this is why the hybrid backend "
          "is not used at scale (`docs/model_choice.md`).", "",
          "Case-by-case list of every disagreement (with the human entities and quotes): `results_disagreements.md`."]
    (HERE / "error_analysis.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("wrote evals/golden/error_analysis.md")


if __name__ == "__main__":
    main()

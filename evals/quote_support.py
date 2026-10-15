"""Does each evidence quote support its labels? Code checks plus a blind judge (Claude Haiku via Claude Pro).

The Doc asks to check evidence_quote membership in code AND to inspect whether the quote supports the label.
  code   every quote is an exact substring of its review; on human-labelled sets, whether the model quoted the
         same sentence the human chose as evidence (reported separately for multi-sentence reviews, where the
         choice is not forced)
  judge  for each (review, quote, topic, intent, severity) item: supported / partial / not_supported per label,
         and whether another part of the review is clearly better evidence. The judge never sees who labelled an
         item: model and human items from the labelled sets are shuffled together under neutral IDs, so the human
         items calibrate the judge. A declared random sample of final-run records adds scale.
Human labels are read here only to build the human items and to score; they never reach the enricher.

  .venv/bin/python evals/quote_support.py --run-dir runs/final-200k-v2 \
      --labelled golden=evals/golden/golden_50_labeled.csv --sample 500 --out-dir evals/quote_support
Judge answers are cached in <out-dir>/judgments.jsonl by item content, so a rerun only sends new items.
"""

import argparse
import collections
import csv
import hashlib
import json
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from insight.cli import _load_cfg_for_run  # noqa: E402
from insight.prompts import render_template  # noqa: E402
from insight.providers import ProviderError, ProviderRegistry, Rates  # noqa: E402
from insight.segment import segment_spans  # noqa: E402
from insight.store import Store  # noqa: E402

PROMPT = "quote_support_v1.md"
JUDGE = ("claude_code", "haiku", "n/a")
FIELDS = ("topic", "intent", "severity")
VERDICTS = ("supported", "partial", "not_supported")
BATCH = 50
SAMPLE_SEED = "quote-support-v1"
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["results"], "properties": {"results": {
    "type": "array", "items": {"type": "object", "additionalProperties": False,
                               "required": ["id", "topic", "intent", "severity", "quote_choice", "reason"],
                               "properties": {"id": {"type": "string"},
                                              **{f: {"type": "string", "enum": list(VERDICTS)} for f in FIELDS},
                                              "quote_choice": {"type": "string", "enum": ["best", "other_better"]},
                                              "reason": {"type": "string"}}}}}}


def _norm(s):
    return " ".join((s or "").split()).strip(" .!?,;:").lower()


def same_sentence(a, b):
    a, b = _norm(a), _norm(b)
    return bool(a and b) and (a == b or a in b or b in a)


def _first(v):
    return (v or "").split("|")[0].strip()


def _esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_items(store, lc, labelled, sample_n):
    items, label_rows = [], {}
    for name, path in labelled:
        with open(path, encoding="utf-8-sig", newline="") as f:
            rows = [r for r in csv.DictReader(f) if r.get("topic") and r.get("intent") and r.get("severity")]
        label_rows[name] = rows
        for r in rows:
            p = store.result(r["review_id"], lc)
            text = r["review_text"]
            multi = len(segment_spans(text)) > 1
            base = {"set": name, "review_id": r["review_id"], "text": text, "multi_sentence": multi}
            if p is not None and p["status"] == "completed":
                items.append({**base, "who": "model", "quote": p["evidence_quote"], "topic": p["topic"],
                              "intent": p["intent"], "severity": int(p["severity"]),
                              "human": {f: r[f].split("|") for f in FIELDS}, "human_quote": r["evidence_quote"]})
            items.append({**base, "who": "human", "quote": r["evidence_quote"], "topic": _first(r["topic"]),
                          "intent": _first(r["intent"]), "severity": int(_first(r["severity"]))})
    if sample_n:
        taken = {r["review_id"] for rows in label_rows.values() for r in rows}
        pool = []
        for p in store.results(lc, status="completed"):
            if p["cache_source_id"] or p["review_id"] in taken:
                continue  # one item per distinct text; labelled reviews are scored above
            pool.append((hashlib.sha256(f"{SAMPLE_SEED}:{p['review_id']}".encode()).hexdigest(), p))
        for _, p in sorted(pool, key=lambda t: t[0])[:sample_n]:
            text = store.review(p["review_id"])["review_text"]
            items.append({"set": "final_sample", "review_id": p["review_id"], "text": text, "who": "model",
                          "multi_sentence": len(segment_spans(text)) > 1, "quote": p["evidence_quote"],
                          "topic": p["topic"], "intent": p["intent"], "severity": int(p["severity"])})
    for it in items:
        it["key"] = hashlib.sha256(json.dumps([it["text"], it["quote"]] + [it[f] for f in FIELDS]).encode()).hexdigest()[:20]
    rng = random.Random(SAMPLE_SEED)
    rng.shuffle(items)  # model and human items interleaved, so a batch never groups one labeller
    for n, it in enumerate(items, 1):
        it["id"] = f"q{n:04d}"
    return items


def render(batch):
    out = []
    for it in batch:
        out.append(f'<item id="{it["id"]}">\n<review>{_esc(it["text"])}</review>\n<quote>{_esc(it["quote"])}</quote>\n'
                   f'<labels>topic={it["topic"]}; intent={it["intent"]}; severity={it["severity"]}</labels>\n</item>')
    return "\n\n".join(out)


def valid(data, batch):
    want = {it["id"] for it in batch}
    res = (data or {}).get("results") if isinstance(data, dict) else None
    if not isinstance(res, list):
        return None
    got = {}
    for r in res:
        if not isinstance(r, dict) or r.get("id") not in want or r["id"] in got:
            return None
        if any(r.get(f) not in VERDICTS for f in FIELDS) or r.get("quote_choice") not in ("best", "other_better"):
            return None
        got[r["id"]] = r
    return got if set(got) == want else None


def judge(provider, system, batch, rates, log):
    """One request per batch, one retry on invalid output or a transient error; returns (answers, call records)."""
    calls = []
    for attempt in (1, 2):
        t0 = time.perf_counter()
        rec = {"batch_ids": [it["id"] for it in batch], "attempt": attempt, "model": JUDGE[1], "billing": "subscription"}
        try:
            r = provider.call({"system": system, "user": render(batch), "schema": SCHEMA, "max_output_tokens": 16000})
        except ProviderError as e:
            rec.update(outcome="failed", error=f"{e.kind}: {str(e)[:200]}", duration_s=round(time.perf_counter() - t0, 3))
            calls.append(rec)
            if e.kind == "systemic":
                raise
            continue
        usage = {k: v for k, v in r.usage.items() if k != "raw"}
        got = valid(r.data, batch)
        rec.update(outcome="succeeded" if got else "invalid_output", request_id=r.provider_request_id,
                   model_reported=r.model_reported, usage=usage, billed_usd=0.0,
                   api_equivalent_usd=round(rates.api_equivalent(r.model_reported, r.usage) or 0.0, 6),
                   duration_s=round(time.perf_counter() - t0, 3))
        calls.append(rec)
        if got:
            return got, calls
        log(f"[quote-support] invalid output for {batch[0]['id']}..{batch[-1]['id']} (attempt {attempt})")
    return {}, calls


def share(rows, field, value):
    return round(sum(r[field] == value for r in rows) / len(rows), 4) if rows else None


def summarise(items, answers):
    groups = collections.defaultdict(list)
    for it in items:
        a = answers.get(it["key"])
        if a:
            groups[(it["set"], it["who"])].append({**it, **{f"j_{f}": a[f] for f in FIELDS},
                                                    "j_choice": a["quote_choice"], "j_reason": a["reason"]})
    table = {}
    for (s, who), rows in sorted(groups.items()):
        t = {"items": len(rows), "multi_sentence": sum(r["multi_sentence"] for r in rows),
             "exact_substring": sum(r["quote"] in r["text"] for r in rows)}
        for f in FIELDS:
            t[f] = {v: share(rows, f"j_{f}", v) for v in VERDICTS}
        t["all_three_supported"] = round(sum(all(r[f"j_{f}"] == "supported" for f in FIELDS) for r in rows) / len(rows), 4)
        t["any_not_supported"] = round(sum(any(r[f"j_{f}"] == "not_supported" for f in FIELDS) for r in rows) / len(rows), 4)
        t["quote_best"] = share(rows, "j_choice", "best")
        if who == "model" and rows and "human_quote" in rows[0]:
            multi = [r for r in rows if r["multi_sentence"]]
            t["same_sentence_as_human"] = sum(same_sentence(r["quote"], r["human_quote"]) for r in rows)
            t["same_sentence_as_human_multi"] = f"{sum(same_sentence(r['quote'], r['human_quote']) for r in multi)}/{len(multi)}"
            for f in FIELDS:
                ok = [r for r in rows if str(r[f]) in r["human"][f]]
                bad = [r for r in rows if str(r[f]) not in r["human"][f]]
                t[f"{f}_supported_when_label_matches_human"] = share(ok, f"j_{f}", "supported")
                t[f"{f}_supported_when_label_differs_from_human"] = share(bad, f"j_{f}", "supported")
                t[f"{f}_label_differs_from_human"] = len(bad)
        table[f"{s}/{who}"] = t
    return table, groups


def report(table, groups, calls, meta):
    L = ["# Evidence quotes: do they support the labels?", "",
         "Generated by `evals/quote_support.py` (prompt `prompts/quote_support_v1.md`). No model call is billed: the judge is "
         f"Claude Haiku through the Claude Pro plan (`claude -p`), reported as {meta['models_reported']}; API-equivalent "
         f"${meta['api_equivalent_usd']:.4f} over {meta['requests']} requests ({meta['attempts']} attempts).", "",
         "**Method.** Code checks that every quote is an exact substring of its review and, on the human-labelled golden set, "
         "whether the model quoted the sentence the human chose as evidence. A blind judge then reads each review, the quote "
         "and the three labels and says, per label, whether the quote on its own supports it (`supported`), is consistent "
         "but needs the rest of the review (`partial`), or does not show it (`not_supported`). Model and human items are "
         "shuffled together under neutral IDs, so the judge cannot tell who labelled what; the human items show how often "
         "the judge accepts a person's own evidence. The final-run sample is a declared random sample of distinct texts "
         f"(lowest SHA-256('{SAMPLE_SEED}:' + review_id), excluding the labelled sets).", "",
         "| Set / labeller | Items | Exact substring | Topic supported | Intent supported | Severity supported | All three supported | Any label not supported | Quote is the best evidence |",
         "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    pct = lambda x: "-" if x is None else f"{x:.0%}"
    for k, t in table.items():
        L.append(f"| {k} | {t['items']} | {t['exact_substring']}/{t['items']} | {pct(t['topic']['supported'])} | "
                 f"{pct(t['intent']['supported'])} | {pct(t['severity']['supported'])} | {pct(t['all_three_supported'])} | "
                 f"{pct(t['any_not_supported'])} | {pct(t['quote_best'])} |")
    L += ["", "## Model quotes against the human's evidence sentence", ""]
    for k, t in table.items():
        if "same_sentence_as_human" in t:
            L.append(f"- **{k}**: the model quoted the human's evidence sentence in {t['same_sentence_as_human']} of "
                     f"{t['items']} reviews; in multi-sentence reviews, where the choice is not forced, "
                     f"{t['same_sentence_as_human_multi']}.")
            for f in FIELDS:
                L.append(f"  - {f}: judge says the quote supports the model's label in "
                         f"{pct(t[f'{f}_supported_when_label_matches_human'])} of reviews where that label matches the human, "
                         f"and {pct(t[f'{f}_supported_when_label_differs_from_human'])} of the "
                         f"{t[f'{f}_label_differs_from_human']} where it differs.")
    L += ["", "## Every model quote the judge did not accept", "",
          "Model items with at least one `not_supported` label, from every set (texts cut at 160 characters).", "",
          "| Set | Review | Text | Quote | Labels | Not supported | Judge's reason |", "|---|---|---|---|---|---|---|"]
    for (s, who), rows in sorted(groups.items()):
        if who != "model":
            continue
        for r in sorted(rows, key=lambda r: r["review_id"]):
            bad = [f for f in FIELDS if r[f"j_{f}"] == "not_supported"]
            if bad:
                cell = lambda x: str(x).replace("|", "/").replace("\n", " ")
                L.append(f"| {s} | `{r['review_id'][:8]}` | {cell(r['text'][:160])} | {cell(r['quote'][:120])} | "
                         f"{r['topic']} / {r['intent']} / {r['severity']} | {', '.join(bad)} | {cell(r['j_reason'])} |")
    return "\n".join(L) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--labelled", action="append", default=[], metavar="NAME=CSV")
    ap.add_argument("--sample", type=int, default=0)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--offline-stub", action="store_true")
    a = ap.parse_args(argv)
    cfg = _load_cfg_for_run(SimpleNamespace(run_dir=a.run_dir, config=None, offline_stub=a.offline_stub, set=[]))
    store = Store(Path(a.run_dir))
    lc = cfg.label_config()
    labelled = [tuple(x.split("=", 1)) for x in a.labelled]
    items = build_items(store, lc, labelled, a.sample)
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    cache_path = out / "judgments.jsonl"
    system = render_template(PROMPT)
    prompt_sha = hashlib.sha256(system.encode()).hexdigest()
    answers = {}
    if cache_path.exists():
        for line in cache_path.read_text(encoding="utf-8").splitlines():
            j = json.loads(line)
            if j.get("prompt_sha256") == prompt_sha:
                answers[j["key"]] = j
    todo = [it for it in items if it["key"] not in answers]
    todo_unique = list({it["key"]: it for it in todo}.values())
    batches = [todo_unique[i:i + BATCH] for i in range(0, len(todo_unique), BATCH)]
    print(f"[quote-support] {len(items)} items ({len(items) - len(todo)} cached); {len(batches)} requests to send", flush=True)
    provider = ProviderRegistry(cfg).get(*JUDGE)
    rates = Rates()
    calls_path = out / "calls.jsonl"

    def run(batch):
        got, calls = judge(provider, system, batch, rates, print)
        return batch, got, calls

    with ThreadPoolExecutor(max_workers=max(1, a.workers)) as pool, open(cache_path, "a", encoding="utf-8") as cf, \
            open(calls_path, "a", encoding="utf-8") as kf:
        for batch, got, calls in pool.map(run, batches):
            for c in calls:
                kf.write(json.dumps(c) + "\n")
            for it in batch:
                g = got.get(it["id"])
                if g:
                    j = {"key": it["key"], "prompt_sha256": prompt_sha, **{f: g[f] for f in FIELDS},
                         "quote_choice": g["quote_choice"], "reason": g["reason"]}
                    answers[it["key"]] = j
                    cf.write(json.dumps(j, ensure_ascii=False) + "\n")
            print(f"[quote-support] batch {batch[0]['id']}..: {len(got)}/{len(batch)} judged", flush=True)
    with open(out / "items.jsonl", "w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps({k: it[k] for k in ("id", "key", "set", "who", "review_id", "multi_sentence", "quote", *FIELDS)},
                               ensure_ascii=False) + "\n")
    all_calls = [json.loads(x) for x in calls_path.read_text(encoding="utf-8").splitlines()] if calls_path.exists() else []
    ok_calls = [c for c in all_calls if c.get("outcome") == "succeeded"]
    meta = {"run_dir": a.run_dir, "label_config": lc, "prompt": f"prompts/{PROMPT}", "prompt_sha256": prompt_sha,
            "judge": {"provider": JUDGE[0], "model_alias": JUDGE[1]},
            "models_reported": ", ".join(sorted({c.get("model_reported") or "?" for c in ok_calls})) or "-",
            "requests": len(ok_calls), "attempts": len(all_calls),
            "api_equivalent_usd": round(sum(c.get("api_equivalent_usd") or 0 for c in all_calls), 6),
            "billed_usd": 0.0, "sample_seed": SAMPLE_SEED, "sample_size": a.sample, "offline_stub": a.offline_stub,
            "unjudged_items": sum(it["key"] not in answers for it in items)}
    table, groups = summarise(items, answers)
    (out / "summary.json").write_text(json.dumps({"meta": meta, "by_set": table}, indent=2) + "\n", encoding="utf-8")
    (out / "report.md").write_text(report(table, groups, all_calls, meta), encoding="utf-8")
    print(f"[quote-support] wrote {out}/report.md and summary.json ({meta['unjudged_items']} items unjudged)")
    return 0 if meta["unjudged_items"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

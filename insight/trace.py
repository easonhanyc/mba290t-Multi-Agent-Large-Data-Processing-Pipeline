"""Trace one real review through every stage, from saved artifacts only (no model calls).

    python -m insight trace --run-dir runs/<run> --auto --out docs/trace_example.md
    python -m insight trace --run-dir runs/<run> --review-id <ID>
    python -m insight trace --run-dir runs/<run> --review-id <ID> --auto   # <ID> as case A, plus the auto case B

source row -> enrichment (calls, tier, label_config, quote) -> verification (the verifier's independent
labels, its call and the field-by-field comparison) -> issue membership -> ranking row -> memo claims
(claim IDs and where the memo prose cites them). --auto picks (1) a review that was verified, belongs to
the top-ranked issue and is quoted in the memo evidence, and (2) an ambiguous or failed case with its
recorded handling.
"""

import csv
import json
import re
from pathlib import Path

from . import labels

_TOKEN = re.compile(r"\{(C\d{2,3})\}")


def _read_csv(path):
    if not Path(path).exists():
        return []
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _calls_for(store, rid):
    rows = store.conn.execute(
        "SELECT request_id, role, tier, phase, model, model_reported, service_tier, billing, outcome, input_tokens, "
        "cached_input_tokens, output_tokens, cost_usd, api_equiv_usd, started_at, error FROM calls "
        "WHERE review_ids LIKE ? ORDER BY started_at", (f'%"{rid}"%',)).fetchall()
    return [dict(r) for r in rows]


def pick_reviews(store, cfg, run_dir):
    lc, vconf = cfg.label_config(), cfg.stage_config("verify")
    ranking = _read_csv(run_dir / "ranking.csv")
    memo = json.loads((run_dir / "memo.json").read_text()) if (run_dir / "memo.json").exists() else {}
    evidence = [e for e in (memo.get("payload") or {}).get("evidence", [])]
    verified = {v["review_id"]: v for v in store.verifications(vconf) if v["status"] == "completed"}
    main = None
    top_issue = ranking[0]["issue_id"] if ranking else None
    for e in evidence:  # quoted in the memo, top issue, verified, and the verifier agrees on topic
        r = store.result(e["review_id"], lc)
        if r and e["issue_id"] == top_issue and e["review_id"] in verified and verified[e["review_id"]]["topic"] == r["topic"]:
            main = e["review_id"]
            break
    if main is None:
        for e in evidence:
            if e["review_id"] in verified:
                main = e["review_id"]
                break
    if main is None and evidence:
        main = evidence[0]["review_id"]
    hard = store.conn.execute(  # a quarantine that is not an empty text, else a fallback-routed review, else a flag
        "SELECT review_id FROM results WHERE label_config=? AND status='quarantined' AND reason != 'empty_review_text' "
        "AND cache_source_id IS NULL ORDER BY review_id LIMIT 1", (lc,)).fetchone()
    if hard is None:
        hard = store.conn.execute("SELECT review_id FROM results WHERE label_config=? AND labeled_by IN ('fallback1','fallback2') "
                                  "ORDER BY review_id LIMIT 1", (lc,)).fetchone()
    if hard is None:
        hard = store.conn.execute("SELECT review_id FROM results WHERE label_config=? AND needs_review=1 ORDER BY review_id "
                                  "LIMIT 1", (lc,)).fetchone()
    return main, (hard[0] if hard else None)


def trace_markdown(store, cfg, run_dir, rid, title):
    lc, vconf = cfg.label_config(), cfg.stage_config("verify")
    src = store.review(rid)
    rec = store.result(rid, lc)
    if src is None:
        return f"## {title}\n\nReview `{rid}` is not in this run.\n"
    L = [f"## {title}", "", f"Review `{rid}` (run `{run_dir.name}`).", "",
         "**1. Source row** (`ingest`, code). Six original fields, unchanged; row hash = SHA-256 of their compact JSON.", "",
         "| Field | Value |", "|---|---|"]
    for k in ("review_text", "review_rating", "review_likes", "app_version", "review_timestamp"):
        v = str(src[k]).replace("\n", " ").replace("|", "\\|")
        L.append(f"| {k} | {v[:400]}{'...' if len(v) > 400 else ''} |")
    L.append(f"| source_sha256 | `{src['source_sha256']}` |")
    L += ["", "**2. Enrichment** (`enrich`, model + code). Only `review_text` was sent.", ""]
    if rec is None:
        L.append("No saved result (pending).")
    else:
        rec = dict(rec)
        detail = json.loads(rec["detail"]) if rec.get("detail") else {}
        if rec["status"] == "completed":
            L += ["| Field | Value |", "|---|---|",
                  f"| status | completed (labeled by **{rec['labeled_by']}**) |",
                  f"| topic / subtopic | {rec['topic']} / {rec['subtopic']} |", f"| intent | {rec['intent']} |",
                  f"| severity | {rec['severity']} ({labels.SEVERITY[rec['severity']]}) |", f"| sentiment | {rec['sentiment']} |",
                  f"| evidence_quote | \"{rec['evidence_quote']}\" (exact substring: {rec['evidence_quote'] in src['review_text']}) |",
                  f"| entities (code-matched) | {', '.join(json.loads(rec['entities'] or '[]')) or '-'} |",
                  f"| needs_review | {bool(rec['needs_review'])} |", f"| cache_source_id | {rec['cache_source_id'] or '-'} |",
                  f"| label_config | `{rec['label_config'].replace('|', chr(92) + '|')}` |"]
            if detail.get("difficulty"):
                L.append(f"| difficulty signals | {'; '.join(detail['difficulty'])} |")
            if detail.get("fallback"):
                L.append(f"| fallback decision | {detail['fallback']} |")
            if detail.get("reconciled"):
                L.append(f"| reconciled | {detail['reconciled']} |")
            if detail.get("primary") and rec["labeled_by"] != "primary":
                p = detail["primary"]
                L.append(f"| primary answer before fallback | issue {p.get('issue')}, intent {p.get('intent')}, "
                         f"severity {p.get('severity')} |")
        else:
            L += [f"Status **quarantined**: {rec['reason']}", "", f"Recorded handling: `{json.dumps(detail)[:600]}`"]
    calls = _calls_for(store, rec["cache_source_id"] if rec and rec.get("cache_source_id") else rid)
    if calls:
        L += ["", "Model calls that carried this review (every attempt is logged before it is sent):", "",
              "| request_id | role / tier | phase | model (reported) | tier / billing | outcome | in / cached / out tokens | billed |",
              "|---|---|---|---|---|---|---|---:|"]
        for c in calls:
            L.append(f"| `{c['request_id']}` | {c['role']} / {c['tier']} | {c['phase']} | `{c['model']}` "
                     f"({c['model_reported'] or '-'}) | {c['service_tier'] or 'standard'} / {c['billing'] or 'api'} | {c['outcome']} | "
                     f"{c['input_tokens']} / {c['cached_input_tokens']} / {c['output_tokens']} | "
                     f"{'-' if c['cost_usd'] is None else f'${c['cost_usd']:.6f}'} |")
    v = store.verification(rid, vconf)
    L += ["", "**3. Verification** (`verify`, independent model + code; blind to the enricher's labels).", ""]
    if v is None:
        L.append("Not in the declared random verification sample.")
    elif v["status"] != "completed":
        L.append(f"In the sample; verifier failed: {v['reason']}")
    else:
        v = dict(v)
        sample = _verification_sample(run_dir)
        if sample:
            L += [f"In the declared verification sample ({sample.get('method')}; seed `{sample.get('seed')}`, "
                  f"{sample.get('sample_size')} of {sample.get('population')} distinct completed texts). The verifier saw "
                  "only the review text, in its own batch request, never the enricher's labels.", ""]
        from .verify import compare
        cmp = compare(dict(rec), v) if rec and rec["status"] == "completed" else None
        L += [f"Verifier `{vconf}`, request `{v.get('request_id') or '-'}` (run `{v.get('run_id') or '-'}`), "
              f"confidence {v['confidence']}:", "",
              "| Field | Enricher (record) | Verifier (independent) | Code comparison |", "|---|---|---|---|"]
        if cmp:
            ag = cmp["agree"]
            L += [f"| topic | {rec['topic']} | {v['topic']} | {'agree' if ag['topic'] else 'disagree'} |",
                  f"| intent | {rec['intent']} | {v['intent']} | {'agree' if ag['intent'] else 'disagree'} |",
                  f"| severity | {rec['severity']} | {v['severity']} | "
                  f"{'agree' if ag['severity'] else 'disagree (abs. difference ' + str(cmp['severity_abs_diff']) + ')'} |",
                  f"| sentiment | {rec['sentiment']} | {v['sentiment']} | abs. difference {cmp['sentiment_abs_diff']} "
                  f"({'within' if ag['sentiment_within_tolerance'] else 'outside'} tolerance {labels.SENTIMENT_TOLERANCE}) |",
                  "", f"Result: {'agrees on every field' if not cmp['disagreement_fields'] else 'disagrees on ' + ', '.join(cmp['disagreement_fields'])}"
                  " (saved in `verification/report.json`; disagreements are listed in `verification/disagreements.csv`, "
                  "and the enricher's labels are never overwritten)."]
        else:
            L.append(f"| topic / intent / severity / sentiment | - | {v['topic']} / {v['intent']} / {v['severity']} / "
                     f"{v['sentiment']} | n/a |")
    members = [m for m in _read_csv(run_dir / "membership.csv") if m["review_id"] == rid]
    L += ["", "**4. Issue membership** (`group`, code; the model only names issues).", ""]
    if not members:
        L.append("Not a member of any issue (only completed complaint/cancellation records are grouped).")
        return "\n".join(L) + "\n"
    iid = members[0]["issue_id"]
    issues = json.loads((run_dir / "issues.json").read_text())["issues"] if (run_dir / "issues.json").exists() else []
    meta = next((i for i in issues if i["issue_id"] == iid), {})
    L.append(f"`membership.csv`: `{iid},{rid}` -> issue **{meta.get('name', labels.ISSUE_BY_ID[iid]['name'])}** "
             f"(named by `{meta.get('named_by', 'taxonomy')}`).")
    rank = next((r for r in _read_csv(run_dir / "ranking.csv") if r["issue_id"] == iid), None)
    L += ["", "**5. Ranking** (`rank`, code; reproducible with `python -m insight rank --run-dir <run> --check`).", ""]
    if rank:
        L.append(f"Rank **{rank['rank']}**: complaint_count {rank['complaint_count']}, severity_sum {rank['severity_sum']}, "
                 f"mean_severity {rank['mean_severity']}, priority_score {rank['priority_score']} (this review contributes "
                 f"severity {rec['severity']}).")
    claims = [c for c in _read_csv(run_dir / "claims.csv") if c["issue_id"] == iid]
    memo = json.loads((run_dir / "memo.json").read_text()) if (run_dir / "memo.json").exists() else {}
    cited = rid in ((memo.get("output") or {}).get("cited_reviews") or [])
    quoted = any(e["review_id"] == rid for e in (memo.get("payload") or {}).get("evidence", []))
    L += ["", "**6. Memo** (`memo`, model + code; the model writes tokens, code fills each as `value (claim ID)`).", ""]
    if claims:
        L.append("Claims in `claims.csv` for this issue: " + ", ".join(f"`{c['claim_id']}` {c['metric']} = {c['value']}"
                                                                    for c in claims) + ".")
        where = _claim_citations(memo.get("output") or {})
        cited_here = [(c, where[c["claim_id"]]) for c in claims if c["claim_id"] in where]
        if cited_here:
            L += ["", f"Where `memo.md` cites them (memo source: {memo.get('source', '-')}):", ""]
            L += [f"- `{c['claim_id']}` ({c['metric']}) is printed as `{c['value']} ({c['claim_id']})` in: "
                  f"{', '.join(places)}" for c, places in cited_here]
            L.append(f"- The memo's issue table prints all four values with their claim IDs (rank {rank['rank'] if rank else '-'} "
                     "row), and `memo_tokens.csv` lists every token ID the memo uses.")
        else:
            L.append("The memo prose cites none of these claim IDs; they appear in the memo's issue table only.")
    L.append("")
    L.append(f"This review is {'quoted in the memo evidence pack' if quoted else 'not quoted in the memo evidence pack'}"
             f"{' and cited by the memo model' if cited else ''}; it contributes to the issue's numbers above.")
    return "\n".join(L) + "\n"


def _verification_sample(run_dir):
    path = Path(run_dir) / "verification" / "report.json"
    try:
        return json.loads(path.read_text()).get("sample") if path.exists() else None
    except (OSError, ValueError):
        return None


def _claim_citations(output):
    """claim ID -> memo.md sections whose prose cites it (from the saved model output in memo.json)."""
    places = {}
    fields = [("Recommendation", output.get("recommendation"))]
    for name, heading in (("next_quarter_actions", "Next-quarter actions"), ("rationale", "Why"),
                          ("what_would_change_the_call", "What would change this call"), ("limitations", "Limitations")):
        fields += [(f"{heading} #{i + 1}", t) for i, t in enumerate(output.get(name) or [])]
    fields += [(f"Alternatives ({a.get('area')})", a.get("why_not_first")) for a in output.get("alternatives") or []
               if isinstance(a, dict)]
    for where, text in fields:
        for cid in _TOKEN.findall(text or ""):
            if where not in places.setdefault(cid, []):
                places[cid].append(where)
    return places


def run_trace(store, cfg, run_dir, review_id=None, auto=False):
    run_dir = Path(run_dir)
    parts = ["# One review traced end to end", "",
             "Generated from saved artifacts by `python -m insight trace` (no model calls).", ""]
    if auto:
        main, hard = pick_reviews(store, cfg, run_dir)
        if review_id:  # an explicitly chosen case A; case B is still picked automatically
            main = review_id
        if main:
            parts.append(trace_markdown(store, cfg, run_dir, main, "A. Traced review (" + _describe(store, cfg, run_dir, main) + ")"))
        if hard:
            parts.append(trace_markdown(store, cfg, run_dir, hard, "B. An ambiguous or failed case and its recorded handling"))
    else:
        parts.append(trace_markdown(store, cfg, run_dir, review_id, "Traced review (" + _describe(store, cfg, run_dir, review_id) + ")"))
    return "\n".join(parts)


def _describe(store, cfg, run_dir, rid):
    """Which pipeline evidence this review carries, for the section title."""
    ranking = _read_csv(Path(run_dir) / "ranking.csv")
    member = next((m["issue_id"] for m in _read_csv(Path(run_dir) / "membership.csv") if m["review_id"] == rid), None)
    v = store.verification(rid, cfg.stage_config("verify"))
    memo = json.loads((Path(run_dir) / "memo.json").read_text()) if (Path(run_dir) / "memo.json").exists() else {}
    quoted = any(e["review_id"] == rid for e in (memo.get("payload") or {}).get("evidence", []))
    bits = []
    if member:
        rank = next((r["rank"] for r in ranking if r["issue_id"] == member), None)
        bits.append("top issue" if rank == "1" else f"issue rank {rank}")
    bits.append("verified" if v is not None and v["status"] == "completed" else "not in the verification sample")
    bits.append("quoted in the memo" if quoted else "not quoted in the memo")
    return ", ".join(bits)

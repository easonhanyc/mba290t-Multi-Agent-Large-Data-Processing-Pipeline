#!/usr/bin/env python3
"""Score a run on evals/synthetic/injection_cases.csv against evals/synthetic/expected.json (no model calls).

Usage: python3 evals/check_synthetic.py runs/<run-dir>
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def check(rec, exp):
    problems = []
    if rec is None:
        return ["no record"]
    if rec["status"] != exp["status"]:
        problems.append(f"status {rec['status']} != {exp['status']}")
    if "reason" in exp and rec.get("reason") != exp["reason"]:
        problems.append(f"reason {rec.get('reason')!r} != {exp['reason']!r}")
    for field in ("intent", "topic"):
        if f"{field}_in" in exp and rec.get(field) not in exp[f"{field}_in"]:
            problems.append(f"{field} {rec.get(field)!r} not in {exp[f'{field}_in']}")
        if f"{field}_not_in" in exp and rec.get(field) in exp[f"{field}_not_in"]:
            problems.append(f"{field} {rec.get(field)!r} is forbidden")
    if "severity_min" in exp and (rec.get("severity") or 0) < exp["severity_min"]:
        problems.append(f"severity {rec.get('severity')} < {exp['severity_min']}")
    if "severity_max" in exp and (rec.get("severity") or 99) > exp["severity_max"]:
        problems.append(f"severity {rec.get('severity')} > {exp['severity_max']}")
    return problems


def main(run_dir):
    run_dir = Path(run_dir)
    expected = json.loads((HERE / "synthetic" / "expected.json").read_text())
    recs = {}
    with open(run_dir / "grading" / "records.jsonl", encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            recs[r["review_id"]] = r
    stub = json.loads((run_dir / "grading" / "run.json").read_text()).get("offline_stub")
    results = {}
    for rid, exp in expected.items():
        if rid.startswith("_"):
            continue
        p = check(recs.get(rid), exp)
        results[rid] = {"pass": not p, "problems": p, "record": recs.get(rid), "expected": exp}
    out = {"run_dir": str(run_dir), "offline_stub": stub,
           "note": ("OFFLINE STUB: labels are hash-based, so label checks are meaningless; only quarantine and plumbing "
                    "checks are informative." if stub else "Live model run."),
           "passed": sum(r["pass"] for r in results.values()), "cases": len(results), "results": results}
    out["cases"] = [{"case_id": rid, "expectation": r["expected"].get("why", ""), "passed": r["pass"],
                     "detail": "; ".join(r["problems"]) or (
                         f"{r['record'].get('status')}: {r['record'].get('topic', r['record'].get('reason', ''))} / "
                         f"{r['record'].get('intent', '')} / severity {r['record'].get('severity', '-')}" if r["record"] else "")}
                    for rid, r in results.items()]
    out["case_count"] = len(results)
    out["summary"] = (f"{out['passed']} of {out['case_count']} synthetic cases passed "
                      f"({'offline stub: label checks not meaningful' if stub else 'live enricher'}). Synthetic cases run in their "
                      "own run directory and never enter business results.")
    text = json.dumps(out, indent=2, ensure_ascii=False) + "\n"
    (run_dir / "evals").mkdir(exist_ok=True)
    (run_dir / "evals" / "synthetic_check.json").write_text(text)
    if not stub:  # the live result is the project's injection evidence (loaded into the dashboard)
        (HERE / "injection").mkdir(exist_ok=True)
        (HERE / "injection" / "synthetic_check.json").write_text(text)
    for rid, r in results.items():
        print(f"{'PASS' if r['pass'] else 'FAIL'} {rid}: {'; '.join(r['problems']) or 'ok'}")
    print(f"{out['passed']}/{out['case_count']} passed. {out['note']}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "runs/synthetic-injection")

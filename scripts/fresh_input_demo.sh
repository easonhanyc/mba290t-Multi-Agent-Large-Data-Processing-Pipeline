#!/usr/bin/env bash
# Fresh-input demonstration: run every stage on a CSV the pipeline has never seen, then check the result.
#   ./scripts/fresh_input_demo.sh <input.csv>            live: real models, BUDGET (default $0.05) per run
#   ./scripts/fresh_input_demo.sh <input.csv> --offline  no key, no cost: local stub models (labels are fake)
# Steps: prepare the CSV (six source columns) -> python -m insight run (ingest, enrich, verify, group, rank, memo,
# export) -> course checker against a reference built from the same CSV -> ranking rebuilt without a model ->
# short summary. Output: runs/fresh-<name>-<UTC time>/ (live) or runs/fresh-offline-<name>-<UTC time>/ (offline).
set -euo pipefail
cd "$(dirname "$0")/.."
[ $# -ge 1 ] || { sed -n '2,7p' "$0"; exit 2; }
SRC="$1"; MODE="${2:-live}"
PY=.venv/bin/python; [ -x "$PY" ] || PY=python3
CHECKER="Final Assignment - Spotify Reviews Dataset/check_submission.py"
NAME="$(basename "${SRC%.*}" | tr -c 'A-Za-z0-9_\n-' '-')"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
if [ "$MODE" = "--offline" ]; then RUN="runs/fresh-offline-$NAME-$STAMP"; FLAGS=(--offline-stub); READ=(--offline-stub)
else RUN="runs/fresh-$NAME-$STAMP"; FLAGS=(--allow-paid --budget-usd "${BUDGET:-0.05}"); READ=(); fi
mkdir -p "$RUN"
INPUT="$RUN/input.csv"

echo "== 1. prepare $SRC"
python3 scripts/prepare_fresh_input.py "$SRC" "$INPUT"

DISTINCT=$(python3 -c "import csv,sys; print(len({r['review_text'] for r in csv.DictReader(open(sys.argv[1], encoding='utf-8')) if r['review_text'].strip()}))" "$INPUT")
if [ "$DISTINCT" -gt 50 ]; then
  echo "== 2a. initial run, one worker, stopped after the first saved request (an interruption with saved progress)"
  $PY -m insight run --input "$INPUT" --run-dir "$RUN" --workers 1 --stop-after 1 "${FLAGS[@]}" 2>&1 | tee "$RUN/console.log" || true
  echo "== 2b. resume the same run directory: only reviews not yet saved are sent"
  $PY -m insight run --input "$INPUT" --run-dir "$RUN" --workers "${WORKERS:-2}" "${FLAGS[@]}" 2>&1 | tee -a "$RUN/console.log"
else
  echo "== 2. run every stage (${FLAGS[*]}); $DISTINCT distinct texts fit one request, so there is no interruption"
  echo "   (the checker's two resume_* items then report the missing interruption, which needs more than 50 texts)"
  $PY -m insight run --input "$INPUT" --run-dir "$RUN" --workers "${WORKERS:-2}" "${FLAGS[@]}" 2>&1 | tee "$RUN/console.log"
fi

echo "== 3. course checker (reference built from the same CSV)"
$PY "$CHECKER" reference --full "$INPUT" --analysis "$INPUT" --out "$RUN/local-reference.json" >/dev/null
$PY "$CHECKER" check --reference "$RUN/local-reference.json" --submission "$RUN/grading" --out "$RUN/self-check.json" >/dev/null || true

echo "== 4. ranking rebuilt from saved outputs, no model call"
$PY -m insight rank --run-dir "$RUN" --check ${READ[@]+"${READ[@]}"} >/dev/null

echo "== 5. summary"
python3 - "$RUN" <<'EOF'
import csv, json, sys
from pathlib import Path
run = Path(sys.argv[1])
s = json.loads((run / "run_summary.json").read_text())["latest"]
res = s.get("results", {})
chk = json.loads((run / "self-check.json").read_text())
rk = json.loads((run / "rank_check.json").read_text())
calls = s.get("calls_all_invocations", {})
print(f"run dir      {run}")
print(f"records      completed {res.get('completed')} | quarantined {res.get('quarantined')} | unfinished {res.get('unfinished')}")
print(f"model calls  " + ", ".join(f"{k} {v.get('succeeded', 0)}/{v.get('attempts', 0)}" for k, v in sorted(calls.items())))
print(f"billed       ${sum(v.get('cost_usd', 0) for v in calls.values()):.6f} (Claude roles on Claude Pro are not billed per call)")
cov = chk.get("coverage", {})
print(f"checker      {chk.get('status')} | issues {chk.get('issue_counts') or {}} | coverage candidate "
      f"{chk.get('working_coverage_point_candidate')} ({cov.get('valid_completed')} completed, {cov.get('quarantined')} quarantined)")
print(f"rank check   identical={rk.get('identical')} | issues {rk.get('issues')}")
rows = list(csv.DictReader(open(run / "ranking.csv", encoding="utf-8")))[:5]
for r in rows:
    print(f"  #{r.get('rank')} {r.get('issue_id')}: {r.get('complaint_count')} complaints, severity sum {r.get('severity_sum')}")
memo = (run / "memo.md").read_text(encoding="utf-8").splitlines()
rec = memo.index("## Recommendation") if "## Recommendation" in memo else 0
print("memo         " + next((l for l in memo[rec + 1:] if l.strip() and not l.startswith("#")), "")[:300])
EOF

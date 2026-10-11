#!/usr/bin/env bash
# Offline plumbing demo on checkpoint_500.csv. NO real model is called and nothing is billed:
# every request goes to the local stub server (model IDs are stub-*), so labels are meaningless.
# It demonstrates: ingest, a real Ctrl-C interruption, resume without re-sending completed IDs,
# a warm rerun with zero calls, the course checker, rank reproducibility, the planted-error test,
# transient/invalid-output fault handling, and the budget cap.
set -u
cd "$(dirname "$0")/.."
PY=.venv/bin/python
DATA="Final Assignment - Spotify Reviews Dataset"
IN="$DATA/checkpoint_500.csv"
RUN=runs/offline-stub-checkpoint500
rm -rf "$RUN" runs/offline-stub-fault-drill-500 runs/offline-stub-budget-drill-500

echo "== 1. start, then a real SIGINT after ~4 s (each stub response is delayed 25 ms) =="
$PY -m insight run --input "$IN" --run-dir "$RUN" --offline-stub \
    --stub-faults "typesafe:1-2000=slow" --stub-timeout-sleep 0.025 &
PID=$!
sleep 4
kill -INT $PID
wait $PID; echo "exit code: $?"

echo; echo "== 2. resume (same command, same run dir) =="
$PY -m insight run --input "$IN" --run-dir "$RUN" --offline-stub; echo "exit code: $?"

echo; echo "== 3. warm rerun: everything cached, zero model calls =="
$PY -m insight run --input "$IN" --run-dir "$RUN" --offline-stub; echo "exit code: $?"

echo; echo "== 4. course checker (reference built from checkpoint_500.csv) =="
(cd "$RUN" && ../../$PY "../../$DATA/check_submission.py" reference --full "../../$IN" --analysis "../../$IN" --out local-reference.json \
 && ../../$PY "../../$DATA/check_submission.py" check --reference local-reference.json --submission grading --out self-check.json \
 && ../../$PY -c "import json; r=json.load(open('self-check.json')); print('status:', r['status'], '| issues:', r['issue_counts'], '| coverage:', {k: r['coverage'][k] for k in ('expected','valid_completed','quarantined','valid_cache_reuses')})")

echo; echo "== 5. ranking rebuilt from grading/ files, no model calls =="
$PY -m insight rank --run-dir "$RUN" --check --offline-stub

echo; echo "== 6. planted wrong label in a test copy =="
$PY -m insight planted-error --run-dir "$RUN" --offline-stub | head -20

echo; echo "== 7. fault drill: 429, 500, timeout, malformed Jev answer, malformed and truncated LLM output =="
$PY -m insight run --input "$IN" --run-dir runs/offline-stub-fault-drill-500 --offline-stub --timeout-s 1 --stub-timeout-sleep 2 \
    --stub-faults "typesafe:3=429,typesafe:4=429,typesafe:10=500,typesafe:20=timeout,typesafe:30=malformed,openai:2=malformed,openai:5=truncated" | tail -4
$PY - <<'PYEOF'
import json, collections
calls = [json.loads(l) for l in open("runs/offline-stub-fault-drill-500/grading/calls.jsonl")]
failed = [c for c in calls if c["outcome"] == "failed"]
print("failed attempts:", len(failed))
for c in failed:
    print(f"  {c['role']}/{c['tier']} attempt {c['attempt']} task_attempt {c['task_attempt']}: {c['error'][:90]}")
print("retried attempts (attempt>1):", sum(c["attempt"] > 1 for c in calls), "| invalid-output retries:", sum(c["task_attempt"] > 1 for c in calls))
PYEOF

echo; echo "== 8. budget drill: stub calls shadow-priced at real rates, cap \$0.005 =="
$PY -m insight run --input "$IN" --run-dir runs/offline-stub-budget-drill-500 --offline-stub --shadow-rates --budget-usd 0.005 | tail -3
$PY -c "import json; s=json.load(open('runs/offline-stub-budget-drill-500/run_summary.json'))['latest']; print('ledger:', s['ledger'], '| unfinished:', s['results']['unfinished'])"
echo "resume with a larger cap:"
$PY -m insight run --input "$IN" --run-dir runs/offline-stub-budget-drill-500 --offline-stub --shadow-rates --budget-usd 0.50 | tail -2

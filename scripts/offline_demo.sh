#!/usr/bin/env bash
# Offline plumbing demo on checkpoint_500.csv. NO real model is called and nothing is billed:
# every request goes to the local stub server (model IDs are stub-*), so labels are meaningless.
# It demonstrates: ingest, a real Ctrl-C interruption, resume without re-sending completed IDs,
# a warm rerun with zero calls, the course checker, rank reproducibility, the planted-error test,
# transient/invalid-output fault handling, and the budget cap.
# The faults target the provider the production backend uses (enrich.backend = "llm": batched OpenAI
# Responses requests, 50 reviews each, one worker), so the SIGINT lands while enrichment is still running.
set -u
cd "$(dirname "$0")/.."
PY=.venv/bin/python
DATA="Final Assignment - Spotify Reviews Dataset"
IN="$DATA/checkpoint_500.csv"
RUN=runs/offline-stub-checkpoint500
rm -rf "$RUN" runs/offline-stub-fault-drill-500 runs/offline-stub-budget-drill-500

echo "== 1. start, then a real SIGINT after ~4 s (each stub LLM response is delayed 1 s; ~10 batches of 50) =="
$PY -m insight run --input "$IN" --run-dir "$RUN" --offline-stub \
    --stub-faults "openai:1-2000=slow" --stub-timeout-sleep 1.0 &
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

echo; echo "== 7. fault drill on the LLM backend: malformed and truncated output, 429 twice, 500, timeout =="
$PY -m insight run --input "$IN" --run-dir runs/offline-stub-fault-drill-500 --offline-stub --timeout-s 1 --stub-timeout-sleep 2 \
    --stub-faults "openai:2=malformed,openai:3=429,openai:4=429,openai:5=truncated,openai:7=500,openai:9=timeout" 2>&1 \
    | grep -v -e '^Traceback' -e '^  File ' -e '^    ' -e '^-----' -e 'BrokenPipeError' -e '^Exception occurred' | tail -4
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

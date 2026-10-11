#!/usr/bin/env bash
# Live (billed) steps, one explicit step per invocation:  ./scripts/live.sh <step> [workers]
# Every step has its own per-run budget; the pipeline also enforces run.project_cap_usd across all runs.
# Keys come from .env (never printed). Offline steps (finalize, load-db) make no model calls.
set -euo pipefail
cd "$(dirname "$0")/.."
PY=.venv/bin/python
DATA="Final Assignment - Spotify Reviews Dataset"
FULL="$DATA/spotify_reviews_18months.csv"
FINAL=runs/final-200k
WORKERS="${2:-4}"

case "${1:-help}" in
  pilot)            # required 100-review cold/warm pilot with the configured setup (one worker, empty cache)
    $PY cost/calculator.py pilot --execute --allow-paid --budget-usd 0.10 ;;
  pilot-jev)        # same pilot with the Jev candidate as primary (comparison experiment)
    $PY cost/calculator.py pilot --execute --allow-paid --budget-usd 0.10 --name jev --set enrich.backend=jev ;;
  checkpoint500)    # 500-review development checkpoint, 1 worker then a 2-worker cold rerun on the same reviews
    $PY -m insight run --input "$DATA/checkpoint_500.csv" --run-dir runs/live-checkpoint500 --allow-paid --budget-usd 0.15 --workers 1
    $PY -m insight run --input "$DATA/checkpoint_500.csv" --run-dir runs/live-checkpoint500-w2 --allow-paid --budget-usd 0.15 --workers 2 --stages ingest,enrich,export
    $PY cost/calculator.py refresh --run-dir runs/live-checkpoint500 --label checkpoint_500 ;;
  budget-drill)     # live spending control: a tiny cap stops admission, then a larger cap resumes
    $PY -m insight run --input "$DATA/checkpoint_500.csv" --run-dir runs/live-budget-drill --allow-paid --budget-usd 0.002 --stages ingest,enrich,export || true
    $PY -m insight run --input "$DATA/checkpoint_500.csv" --run-dir runs/live-budget-drill --allow-paid --budget-usd 0.05 --stages ingest,enrich,export ;;
  injection)        # synthetic prompt-injection cases through the live enricher (own run directory; never in business results)
    $PY -m insight run --input evals/synthetic/injection_cases.csv --run-dir runs/live-synthetic-injection --allow-paid --budget-usd 0.02 --stages ingest,enrich,export
    python3 evals/check_synthetic.py runs/live-synthetic-injection ;;
  golden-candidates) # enrichment candidates on the golden 50 texts (human labels are never ingested)
    $PY -m insight run --input "$DATA/golden_50_to_label.csv" --run-dir runs/golden-luna-none --allow-paid --budget-usd 0.05 --stages ingest,enrich,export
    $PY -m insight run --input "$DATA/golden_50_to_label.csv" --run-dir runs/golden-jev --allow-paid --budget-usd 0.05 --stages ingest,enrich,export --set enrich.backend=jev
    $PY -m insight run --input "$DATA/golden_50_to_label.csv" --run-dir runs/golden-luna-low --allow-paid --budget-usd 0.05 --stages ingest,enrich,export --set enrich.llm.effort=low --set enrich.llm.max_output_tokens_per_review=200
    for r in golden-luna-none golden-jev golden-luna-low; do
      $PY -m insight golden --labels evals/golden/golden_50_labeled.csv --run-dir runs/$r --out evals/golden/candidates/$r.json
    done ;;
  analysis10k)      # 10,000-review development and budget checkpoint
    $PY -m insight run --input "$DATA/analysis_10000.csv" --run-dir runs/live-analysis10000 --allow-paid --budget-usd 0.50 --workers "$WORKERS"
    $PY cost/calculator.py refresh --run-dir runs/live-analysis10000 --label analysis_10000 ;;
  final-initial)    # declared 200k scope, recorded; Ctrl-C (SIGINT) is sent after 180 s of saved progress
    python3 scripts/make_analysis_subset.py
    python3 scripts/record_session.py --out $FINAL/recording/1-initial-interrupted.cast --interrupt-after 180 -- \
      $PY -m insight run --input data/analysis_200k.csv --full "$FULL" --run-dir $FINAL --allow-paid --budget-usd 4.00 --workers "$WORKERS" || true ;;
  final-resume)     # resume the same run directory (phase "resume"): only pending reviews are sent
    python3 scripts/record_session.py --out $FINAL/recording/2-resume.cast -- \
      $PY -m insight run --input data/analysis_200k.csv --full "$FULL" --run-dir $FINAL --allow-paid --budget-usd 4.00 --workers "$WORKERS" ;;
  finalize)         # offline: checker, reproducible ranking, planted error, trace, golden, calculator refresh
    $PY "$DATA/check_submission.py" reference --full "$FULL" --analysis data/analysis_200k.csv --out $FINAL/local-reference.json
    $PY "$DATA/check_submission.py" check --reference $FINAL/local-reference.json --submission $FINAL/grading --out $FINAL/self-check.json
    $PY -m insight rank --run-dir $FINAL --check
    $PY -m insight planted-error --run-dir $FINAL
    $PY -m insight trace --run-dir $FINAL --auto --out docs/trace_example.md
    $PY -m insight golden --labels evals/golden/golden_50_labeled.csv --run-dir $FINAL --out evals/golden/results.json
    $PY cost/calculator.py refresh --run-dir $FINAL --label final_200k ;;
  load-db)          # offline: load the final run into the dashboard database (DATABASE_URL in .env)
    $PY web/load_db.py --run-dir $FINAL ;;
  *)
    sed -n '2,5p' "$0"; grep -E '^  [a-z0-9-]+\)' "$0" | sed 's/)//' ;;
esac

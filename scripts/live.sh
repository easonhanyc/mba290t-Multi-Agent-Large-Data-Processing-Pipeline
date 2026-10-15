#!/usr/bin/env bash
# Live (billed) steps, one explicit step per invocation:  ./scripts/live.sh <step> [workers]
# Every step has its own per-run budget; the pipeline also enforces run.project_cap_usd across all runs.
# Keys come from .env (never printed). Offline steps (finalize, load-db) make no model calls.
set -euo pipefail
cd "$(dirname "$0")/.."
PY=.venv/bin/python
DATA="Final Assignment - Spotify Reviews Dataset"
FULL="$DATA/spotify_reviews_18months.csv"
SCOPE="${SCOPE:-200k}"         # 200k: declared subset data/analysis_200k.csv | full: all 660,622 rows
# The final setup is the golden-50 winner (config/pipeline.toml: Luna effort low, label_config cfg-52c5333247).
# Superseded effort-none runs keep their directories: runs/final-200k, runs/live-checkpoint500(-w2),
# runs/live-analysis10000 and the first pilot (cost/experiments/pilot-effort-none).
if [ "$SCOPE" = "full" ]; then INPUT="$FULL"; FINAL=runs/final-full-v2; else INPUT=data/analysis_200k.csv; FINAL=runs/final-200k-v2; fi
FINAL_LABEL="final_${SCOPE}_v2"
FINAL_BUDGET="${FINAL_BUDGET:-3.50}"
WORKERS="${2:-4}"

case "${1:-help}" in
  pilot)            # required 100-review cold/warm pilot with the configured setup (one worker, empty cache)
    $PY cost/calculator.py pilot --execute --allow-paid --budget-usd 0.10 ;;
  probes)           # done 2026-10-12: 5 dev reviews each through Decisions and batched Luna (usage + rate-limit headers)
    $PY -m insight run --input data/probe_dev_5.csv --run-dir runs/probe-decisions --allow-paid --budget-usd 0.01 --stages ingest,enrich --set enrich.backend=decisions --set enrich.fallback1.max_fraction=0 --set enrich.fallback2.max_fraction=0
    $PY -m insight run --input data/probe_dev_5.csv --run-dir runs/probe-luna --allow-paid --budget-usd 0.01 --stages ingest,enrich --set enrich.backend=llm --set enrich.fallback1.max_fraction=0 --set enrich.fallback2.max_fraction=0 ;;
  checkpoint500)    # 500-review development checkpoint with the final setup, 1 worker (the 1-vs-2 worker comparison
                    # was measured on the effort-none setup: runs/live-checkpoint500 and runs/live-checkpoint500-w2)
    $PY -m insight run --input "$DATA/checkpoint_500.csv" --run-dir runs/live-checkpoint500-low --allow-paid --budget-usd 0.15 --workers 1
    $PY cost/calculator.py refresh --run-dir runs/live-checkpoint500-low --label checkpoint_500_low ;;
  budget-drill)     # live spending control: a $0.005 cap stops admission after two batches, then a larger cap resumes
    $PY -m insight run --input "$DATA/checkpoint_500.csv" --run-dir runs/live-budget-drill --allow-paid --budget-usd 0.005 --stages ingest,enrich,export || true
    $PY -m insight run --input "$DATA/checkpoint_500.csv" --run-dir runs/live-budget-drill --allow-paid --budget-usd 0.05 --stages ingest,enrich,export ;;
  injection)        # synthetic prompt-injection cases through the live enricher (own run directory; never in business results)
    $PY -m insight run --input evals/synthetic/injection_cases.csv --run-dir runs/live-synthetic-injection --allow-paid --budget-usd 0.02 --stages ingest,enrich,export
    python3 evals/check_synthetic.py runs/live-synthetic-injection ;;
  golden-candidates) # enrichment candidates on the golden 50 texts (human labels are never ingested).
                    # Decisions allows 50 requests/day on this account: its run may stop early and is resumed later.
    $PY -m insight run --input "$DATA/golden_50_to_label.csv" --run-dir runs/golden-luna-none --allow-paid --budget-usd 0.05 --stages ingest,enrich,export
    $PY -m insight run --input "$DATA/golden_50_to_label.csv" --run-dir runs/golden-decisions --allow-paid --budget-usd 0.05 --stages ingest,enrich,export --set enrich.backend=decisions --set enrich.fallback1.max_fraction=0 --set enrich.fallback2.max_fraction=0 || true
    $PY -m insight run --input "$DATA/golden_50_to_label.csv" --run-dir runs/golden-luna-low --allow-paid --budget-usd 0.05 --stages ingest,enrich,export --set enrich.llm.effort=low --set enrich.llm.max_output_tokens_per_review=200
    for r in golden-luna-none golden-decisions golden-luna-low; do
      $PY -m insight golden --labels evals/golden/golden_50_labeled.csv --run-dir runs/$r --out evals/golden/candidates/$r.json
    done ;;
  analysis10k)      # 10,000-review development and budget checkpoint
    # 2026-10-14: the first invocation's Claude stages hit the Pro session limit (then treated as transient, now a
    # systemic stop); rerunning this same command resumed them with no enrichment calls.
    $PY -m insight run --input "$DATA/analysis_10000.csv" --run-dir runs/live-analysis10000-low --allow-paid --budget-usd 0.50 --workers "$WORKERS"
    $PY cost/calculator.py refresh --run-dir runs/live-analysis10000-low --label analysis_10000_low ;;
  final-initial)    # final run (SCOPE=200k|full), recorded; Ctrl-C (SIGINT) is sent after 180 s of saved progress
    [ "$SCOPE" = "full" ] || python3 scripts/make_analysis_subset.py
    python3 scripts/record_session.py --out $FINAL/recording/1-initial-interrupted.cast --interrupt-after 180 -- \
      $PY -m insight run --input "$INPUT" --full "$FULL" --run-dir $FINAL --allow-paid --budget-usd "$FINAL_BUDGET" --workers "$WORKERS" || true ;;
  final-resume)     # resume the same run directory (phase "resume"): only pending reviews are sent
    python3 scripts/record_session.py --out $FINAL/recording/2-resume.cast -- \
      $PY -m insight run --input "$INPUT" --full "$FULL" --run-dir $FINAL --allow-paid --budget-usd "$FINAL_BUDGET" --workers "$WORKERS" ;;
  finalize)         # offline: checker, reproducible ranking, planted error, trace, golden, calculator refresh
    $PY "$DATA/check_submission.py" reference --full "$FULL" --analysis "$INPUT" --out $FINAL/local-reference.json
    $PY "$DATA/check_submission.py" check --reference $FINAL/local-reference.json --submission $FINAL/grading --out $FINAL/self-check.json
    $PY -m insight rank --run-dir $FINAL --check
    $PY -m insight planted-error --run-dir $FINAL
    # traced review: lowest SHA-256('trace-v1:' + review_id) among usability.ads members in the verification sample
    # whose verifier labels agree (docs/trace_example.md); --auto adds the ambiguous/failed case
    $PY -m insight trace --run-dir $FINAL --review-id c5f4ab7f-5a94-43e8-9e80-9d572e0da060 --auto --out docs/trace_example.md
    $PY -m insight golden --labels evals/golden/golden_50_labeled.csv --run-dir $FINAL --out evals/golden/results.json
    $PY "$DATA/check_submission.py" reference --full "$FULL" --analysis "$FULL" --out $FINAL/full-reference.json
    $PY "$DATA/check_submission.py" check --reference $FINAL/full-reference.json --submission $FINAL/grading --out $FINAL/self-check-vs-full-reference.json || true
    python3 evals/verification/disagreement_counts.py --run-dir $FINAL --input "$INPUT" --out evals/verification/disagreement_counts.json
    $PY cost/calculator.py refresh --run-dir $FINAL --label "$FINAL_LABEL" ;;
  quote-support)    # Claude Pro, $0 billed: does each evidence quote support its labels? (golden 50 + 500 sampled texts)
    $PY evals/quote_support.py --run-dir $FINAL --labelled golden=evals/golden/golden_50_labeled.csv \
        --sample 500 --out-dir evals/quote_support ;;
  fresh-demo)       # small fresh-input demonstration on any CSV with every stage and the checker (BUDGET, default $0.05)
    ./scripts/fresh_input_demo.sh "${2:?usage: ./scripts/live.sh fresh-demo <input.csv>}" ;;
  load-db)          # offline: load the final run into the dashboard database (DATABASE_URL in .env)
    $PY web/load_db.py --run-dir $FINAL ;;
  *)
    sed -n '2,5p' "$0"; grep -E '^  [a-z0-9-]+\)' "$0" | sed 's/)//' ;;
esac

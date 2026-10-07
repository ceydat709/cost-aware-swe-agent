#!/usr/bin/env bash
# Score a run with the official SWE-bench harness (builds Docker images; needs disk space).
# Usage: scripts/evaluate.sh <run-name>      score runs/<run-name>/predictions.jsonl
#        scripts/evaluate.sh gold <ids...>   sanity-check the harness with the reference patches
set -euo pipefail
RUN_NAME="${1:?usage: scripts/evaluate.sh <run-name> | gold <instance_ids...>}"
shift
mkdir -p "runs/${RUN_NAME}"
if [[ "$RUN_NAME" == "gold" ]]; then
  PREDS=gold
  IDS=(--instance_ids "$@")
else
  PREDS="runs/${RUN_NAME}/predictions.jsonl"
  IDS=()
fi
python -m swebench.harness.run_evaluation \
  --dataset_name SWE-bench/SWE-bench_Lite \
  --predictions_path "$PREDS" \
  ${IDS[@]+"${IDS[@]}"} \
  --max_workers 1 \
  --run_id "${RUN_NAME}" \
  --report_dir "runs/${RUN_NAME}"

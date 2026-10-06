#!/usr/bin/env bash
# Score a run with the official SWE-bench harness (builds Docker images; needs disk space).
set -euo pipefail
RUN_NAME="${1:?usage: scripts/evaluate.sh <run-name>}"
python -m swebench.harness.run_evaluation \
  --dataset_name princeton-nlp/SWE-bench_Lite \
  --predictions_path "runs/${RUN_NAME}/predictions.jsonl" \
  --max_workers 1 \
  --run_id "${RUN_NAME}"

#!/usr/bin/env bash
# Compare the agent with and without verify-before-submit on the same tasks, then score both.
#
# Usage: scripts/run_comparison.sh [model] [experiment-name]
#   e.g. scripts/run_comparison.sh qwen2.5-coder:7b exp1
#
# Safe to re-run: tasks that already have a prediction or a score are skipped,
# so if the laptop sleeps mid-run, just start it again with the same name.
set -uo pipefail

MODEL="${1:-qwen2.5-coder:7b}"
EXP="${2:-exp1}"
INSTANCES=(psf__requests-1963 psf__requests-2148 psf__requests-2317 psf__requests-2674 psf__requests-3362)
MAX_STEPS=30
MIN_FREE_GB=25

# Keep the Mac awake (with the lid open) until this script finishes.
if [[ -z "${CAFFEINATED:-}" ]] && command -v caffeinate >/dev/null; then
  CAFFEINATED=1 exec caffeinate -i "$0" "$@"
fi

cd "$(dirname "$0")/.."

source .venv/bin/activate
mkdir -p "runs"
LOG="runs/${EXP}.log"
log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG"; }

# --- Preflight: fail in the first minute, not at 3am -------------------------
docker info >/dev/null 2>&1 || { echo "Docker isn't running. Open Docker Desktop and retry."; exit 1; }
curl -sf localhost:11434/api/tags | grep -q "\"${MODEL}\"" \
  || { echo "Ollama isn't running or model '${MODEL}' isn't pulled (ollama pull ${MODEL})."; exit 1; }
FREE_GB=$(df -g . | awk 'NR==2 {print $4}')
(( FREE_GB >= MIN_FREE_GB )) || { echo "Only ${FREE_GB}GB free; need ${MIN_FREE_GB}GB for Docker images."; exit 1; }

log "Experiment ${EXP}: model=${MODEL}, ${#INSTANCES[@]} tasks, baseline vs --verify"

log "Pulling task images (x86, emulated)..."
for id in "${INSTANCES[@]}"; do
  image="swebench/sweb.eval.x86_64.${id/__/_1776_}:latest"
  docker image inspect "$image" >/dev/null 2>&1 || docker pull -q --platform linux/amd64 "$image" >>"$LOG" 2>&1 \
    || log "WARN: could not pull $image"
done

# --- Run the agent ------------------------------------------------------------
for config in baseline verify; do
  run="${EXP}-${config}"
  flags=(); [[ "$config" == "verify" ]] && flags=(--verify)
  for id in "${INSTANCES[@]}"; do
    if grep -qs "\"$id\"" "runs/${run}/predictions.jsonl"; then
      log "skip ${run} ${id} (already done)"; continue
    fi
    log "agent ${run} ${id}"
    swe-agent --model "$MODEL" --instances "$id" --max-steps "$MAX_STEPS" --run-name "$run" \
      ${flags[@]+"${flags[@]}"} 2>>"$LOG" | grep '^{' | tee -a "$LOG" \
      || log "ERROR: agent failed on ${run} ${id} (see log); continuing"
  done
done

# --- Score both runs with the official harness --------------------------------
for config in baseline verify; do
  run="${EXP}-${config}"
  if ls "runs/${run}/"*".${run}.json" >/dev/null 2>&1; then
    log "skip scoring ${run} (report exists)"; continue
  fi
  log "scoring ${run} (~10 min per task on Apple Silicon)"
  scripts/evaluate.sh "$run" >>"$LOG" 2>&1 || log "ERROR: scoring failed for ${run} (see log)"
done

log "Done."
python scripts/summarize.py "${EXP}-baseline" "${EXP}-verify" | tee -a "$LOG"

#!/usr/bin/env bash
set -u

STATE_DIR="/home/elf/project_evidence/day32_productization/runtime_state"
LOG_DIR="/home/elf/project_evidence/day32_productization/unified_logs"
ANALYZE_SCRIPT="/home/elf/sensor_work/day32_product_ops/elf2_analyze_event_after_fast_capture.sh"

LOCK_FILE="/tmp/elf2_latest_ai_worker.singleton.lock"

mkdir -p "$STATE_DIR" "$LOG_DIR"

exec 8>"$LOCK_FILE"
if ! flock -n 8; then
  echo "Another latest AI worker is already running. Exit duplicate worker."
  exit 0
fi

WORKER_LOG="$LOG_DIR/latest_ai_worker_$(date +%Y%m%d_%H%M%S).txt"

echo "==================================================" | tee "$WORKER_LOG"
echo "ELF2 Latest AI Worker"
echo "time=$(date '+%Y-%m-%d %H:%M:%S')" | tee -a "$WORKER_LOG"
echo "==================================================" | tee -a "$WORKER_LOG"

while true; do
  EVENT=$(cat "$STATE_DIR/latest_ai_event" 2>/dev/null || true)

  if [ -z "${EVENT:-}" ] || [ ! -d "$EVENT" ]; then
    echo "No latest_ai_event. Worker exit." | tee -a "$WORKER_LOG"
    break
  fi

  echo "$EVENT" > "$STATE_DIR/current_ai_event"
  rm -f "$STATE_DIR/latest_ai_event"

  echo "Start analyzing latest event:" | tee -a "$WORKER_LOG"
  echo "$EVENT" | tee -a "$WORKER_LOG"

  bash "$ANALYZE_SCRIPT" "$EVENT" 2>&1 | tee -a "$WORKER_LOG"

  echo "$EVENT" > "$STATE_DIR/last_ai_done_event"

  NEXT=$(cat "$STATE_DIR/latest_ai_event" 2>/dev/null || true)

  if [ -n "${NEXT:-}" ] && [ -d "$NEXT" ] && [ "$NEXT" != "$EVENT" ]; then
    echo "Newer event arrived during analysis. Continue to latest event." | tee -a "$WORKER_LOG"
    continue
  fi

  echo "No newer event. Worker finished." | tee -a "$WORKER_LOG"
  break
done

rm -f "$STATE_DIR/current_ai_event"
echo "RESULT=OK" | tee -a "$WORKER_LOG"

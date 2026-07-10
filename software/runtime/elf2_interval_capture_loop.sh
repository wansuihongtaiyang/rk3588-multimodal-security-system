#!/usr/bin/env bash
set -u

CAPTURE_INTERVAL="${CAPTURE_INTERVAL:-60}"
IDLE_CHECK_INTERVAL="${IDLE_CHECK_INTERVAL:-5}"
AI_TIMEOUT="${AI_TIMEOUT:-120}"
FACE_THRESHOLD="${FACE_THRESHOLD:-0.363}"

CAPTURE_ONCE="/home/elf/sensor_work/day32_product_ops/elf2_ai_capture_once_with_context.sh"

STATE_DIR="/home/elf/project_evidence/day32_productization/runtime_state"
LOG_DIR="/home/elf/project_evidence/day32_productization/interval_capture_logs"

mkdir -p "$STATE_DIR" "$LOG_DIR"

[ -f "$STATE_DIR/mode" ] || echo "READY" > "$STATE_DIR/mode"
[ -f "$STATE_DIR/auto_capture_enabled" ] || echo "0" > "$STATE_DIR/auto_capture_enabled"

echo "=================================================="
echo "ELF2 Interval Capture Loop"
echo "CAPTURE_INTERVAL = $CAPTURE_INTERVAL"
echo "=================================================="


sleep_interval_with_state_check() {
  local TOTAL="$1"
  local I=0

  while [ "$I" -lt "$TOTAL" ]; do
    MODE=$(cat "$STATE_DIR/mode" 2>/dev/null || echo READY)
    AUTO=$(cat "$STATE_DIR/auto_capture_enabled" 2>/dev/null || echo 0)

    if [ "$MODE" != "RUNNING" ] || [ "$AUTO" != "1" ]; then
      echo "interval sleep interrupted: MODE=$MODE AUTO=$AUTO"
      return 0
    fi

    sleep 1
    I=$((I + 1))
  done
}

COUNT=0

while true; do
  MODE=$(cat "$STATE_DIR/mode" 2>/dev/null || echo READY)
  AUTO=$(cat "$STATE_DIR/auto_capture_enabled" 2>/dev/null || echo 0)

  if [ "$MODE" = "RUNNING" ] && [ "$AUTO" = "1" ]; then
    COUNT=$((COUNT + 1))
    STAMP=$(date +"%Y%m%d_%H%M%S")
    LOG="$LOG_DIR/interval_round_${COUNT}_${STAMP}.txt"

    echo
    echo "================ interval capture round $COUNT ================"
    echo "time = $(date '+%Y-%m-%d %H:%M:%S')"
    echo "LOG=$LOG"

    TRIGGER_TYPE="interval_capture" \
    SELECTED_EVENT="AUTO_INTERVAL_CAPTURE" \
    VOICE_TEXT="AUTO_INTERVAL_CAPTURE" \
    VOICE_LOG="" \
    AI_TIMEOUT="$AI_TIMEOUT" \
    FACE_THRESHOLD="$FACE_THRESHOLD" \
    bash "$CAPTURE_ONCE" \
    2>&1 | tee "$LOG"

    echo "sleep ${CAPTURE_INTERVAL}s before next interval capture..."
    sleep_interval_with_state_check "$CAPTURE_INTERVAL"
  else
    echo "interval loop idle: MODE=$MODE AUTO=$AUTO"
    sleep "$IDLE_CHECK_INTERVAL"
  fi
done

#!/usr/bin/env bash
set -u

VOICE_PERIOD="${VOICE_PERIOD:-10}"
REC_SECONDS="${REC_SECONDS:-7}"
AI_TIMEOUT="${AI_TIMEOUT:-120}"
FACE_THRESHOLD="${FACE_THRESHOLD:-0.363}"

DISPATCH="/home/elf/sensor_work/day22_vosk/vosk_command_dispatch.py"
CAPTURE_ONCE="/home/elf/sensor_work/day32_product_ops/elf2_priority_capture_fast_web.sh"
CONTROL_SCRIPT="/home/elf/sensor_work/day32_product_ops/elf2_runtime_control.sh"

STATE_DIR="/home/elf/project_evidence/day32_productization/runtime_state"
LOG_DIR="/home/elf/project_evidence/day32_productization/voice_command_logs"

mkdir -p "$STATE_DIR" "$LOG_DIR"

[ -f "$STATE_DIR/mode" ] || echo "READY" > "$STATE_DIR/mode"
[ -f "$STATE_DIR/auto_capture_enabled" ] || echo "0" > "$STATE_DIR/auto_capture_enabled"
[ -f "$STATE_DIR/alarm_enabled" ] || echo "1" > "$STATE_DIR/alarm_enabled"
[ -f "$STATE_DIR/night_mode" ] || echo "0" > "$STATE_DIR/night_mode"

CSV="$LOG_DIR/voice_command_history.csv"
if [ ! -f "$CSV" ]; then
  echo "timestamp,text,selected_event,mode,auto_capture,alarm_enabled,night_mode,log" > "$CSV"
fi

echo "=================================================="
echo "ELF2 Voice Command Loop 10s"
echo "VOICE_PERIOD = $VOICE_PERIOD"
echo "REC_SECONDS  = $REC_SECONDS"
echo "=================================================="

COUNT=0

while true; do
  COUNT=$((COUNT + 1))
  START_TS=$(date +%s)
  STAMP=$(date +"%Y%m%d_%H%M%S")
  LOG="$LOG_DIR/voice_round_${COUNT}_${STAMP}.txt"

  echo
  echo "================ voice round $COUNT ================"
  echo "time = $(date '+%Y-%m-%d %H:%M:%S')"
  echo "请说：唤醒词 + 命令"
  echo "支持：开始检测、停止检测、查看状态、抓拍、开启告警、关闭告警、夜间模式"
  echo "LOG=$LOG"

  python3 "$DISPATCH" \
    --seconds "$REC_SECONDS" \
    --mode open \
    2>&1 | tee "$LOG"

  TEXT=$(sed -n 's/^text[[:space:]]*=[[:space:]]*//p' "$LOG" | tail -n 1)
  SELECTED=$(sed -n 's/^selected_event[[:space:]]*=[[:space:]]*//p' "$LOG" | tail -n 1)

  MODE=$(cat "$STATE_DIR/mode" 2>/dev/null || echo READY)
  AUTO=$(cat "$STATE_DIR/auto_capture_enabled" 2>/dev/null || echo 0)
  ALARM=$(cat "$STATE_DIR/alarm_enabled" 2>/dev/null || echo 1)
  NIGHT=$(cat "$STATE_DIR/night_mode" 2>/dev/null || echo 0)

  if [ -n "${SELECTED:-}" ]; then
    echo "VOICE_SELECTED=$SELECTED"

    case "$SELECTED" in
      VOICE_START)
        echo "Action: start detection, enable camera loop + sensor trigger + alarm"
        bash "$CONTROL_SCRIPT" start 2>&1 | tee -a "$LOG" || true
        ;;

      VOICE_STOP)
        echo "Action: stop detection, disable camera loop + sensor trigger + alarm"
        bash "$CONTROL_SCRIPT" stop 2>&1 | tee -a "$LOG" || true
        ;;

      VOICE_CAPTURE)
        echo "Action: immediate one-shot fast capture. Runtime mode/auto/alarm are not changed by capture command."
        TRIGGER_TYPE="voice_capture" \
        SELECTED_EVENT="$SELECTED" \
        VOICE_TEXT="$TEXT" \
        VOICE_LOG="$LOG" \
        WAIT_FOR_LOCK=1 \
        AI_TIMEOUT="$AI_TIMEOUT" \
        FACE_THRESHOLD="$FACE_THRESHOLD" \
        bash "$CAPTURE_ONCE" &
        ;;

      VOICE_STATUS)
        echo "Action: status requested"
        bash /home/elf/sensor_work/day32_product_ops/elf2_status.sh 2>&1 | tee -a "$LOG" || true
        ;;

      VOICE_ALARM_ON)
        echo "Action: alarm enabled"
        bash "$CONTROL_SCRIPT" alarm_on 2>&1 | tee -a "$LOG" || true
        ;;

      VOICE_ALARM_OFF)
        echo "Action: alarm disabled"
        bash "$CONTROL_SCRIPT" alarm_off 2>&1 | tee -a "$LOG" || true
        ;;

      VOICE_NIGHT)
        echo "Action: night mode enabled"
        bash "$CONTROL_SCRIPT" night_on 2>&1 | tee -a "$LOG" || true
        ;;

      *)
        echo "Action: selected event not handled by unified loop: $SELECTED"
        ;;
    esac
  else
    echo "VOICE_SELECTED=NONE"
  fi

  MODE=$(cat "$STATE_DIR/mode" 2>/dev/null || echo READY)
  AUTO=$(cat "$STATE_DIR/auto_capture_enabled" 2>/dev/null || echo 0)
  ALARM=$(cat "$STATE_DIR/alarm_enabled" 2>/dev/null || echo 1)
  NIGHT=$(cat "$STATE_DIR/night_mode" 2>/dev/null || echo 0)

  echo "$(date '+%Y-%m-%d %H:%M:%S'),\"$TEXT\",\"$SELECTED\",\"$MODE\",\"$AUTO\",\"$ALARM\",\"$NIGHT\",\"$LOG\"" >> "$CSV"

  ELAPSED=$(( $(date +%s) - START_TS ))
  SLEEP_TIME=$(( VOICE_PERIOD - ELAPSED ))

  if [ "$SLEEP_TIME" -gt 0 ]; then
    echo "sleep ${SLEEP_TIME}s before next voice listen..."
    sleep "$SLEEP_TIME"
  else
    echo "voice round took ${ELAPSED}s, start next round immediately."
  fi
done

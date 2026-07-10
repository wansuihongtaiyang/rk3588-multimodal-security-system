#!/usr/bin/env bash
set -u

# SENSOR_WATCH_SINGLETON_LOCK
# 防止多个传感器监控循环同时运行，避免重复触发抓拍、重复中断 AI。
LOCK_FILE="/tmp/elf2_sensor_watch_loop.singleton.lock"
exec 8>"$LOCK_FILE"
if ! flock -n 8; then
  echo "Another elf2_sensor_watch_loop.sh is already running. Exit duplicate instance."
  exit 0
fi


SENSOR_PERIOD="${SENSOR_PERIOD:-5}"

AI_TIMEOUT="${AI_TIMEOUT:-120}"
FACE_THRESHOLD="${FACE_THRESHOLD:-0.363}"

# 是否允许 READY 状态也触发抓拍：
# 0 = 只检测和记录，只有 RUNNING 才触发抓拍
# 1 = READY 也可以触发抓拍
SENSOR_TRIGGER_IN_READY="${SENSOR_TRIGGER_IN_READY:-0}"

ALERT_SCRIPT="/home/elf/sensor_work/day24_network_alert/abnormal_event_check_and_alert_v3.py"
CAPTURE_ONCE="/home/elf/sensor_work/day32_product_ops/elf2_priority_capture_fast_web.sh"

STATE_DIR="/home/elf/project_evidence/day32_productization/runtime_state"
LOG_DIR="/home/elf/project_evidence/day32_productization/sensor_watch_logs"

mkdir -p "$STATE_DIR" "$LOG_DIR"

[ -f "$STATE_DIR/mode" ] || echo "READY" > "$STATE_DIR/mode"
[ -f "$STATE_DIR/alarm_enabled" ] || echo "1" > "$STATE_DIR/alarm_enabled"
[ -f "$STATE_DIR/night_mode" ] || echo "0" > "$STATE_DIR/night_mode"
[ -f "$STATE_DIR/last_sensor_trigger_ts" ] || echo "0" > "$STATE_DIR/last_sensor_trigger_ts"
[ -f "$STATE_DIR/sensor_abnormal_count" ] || echo "0" > "$STATE_DIR/sensor_abnormal_count"

choose_cooldown() {
  local KIND="$1"
  local COUNT="$2"
  local NIGHT="$3"

  if [ "$KIND" = "MOTION" ]; then
    if [ "$COUNT" -lt 2 ]; then
      echo 10
    elif [ "$COUNT" -lt 5 ]; then
      echo 8
    else
      echo 8
    fi
    return
  fi

  if [ "$KIND" = "MIXED" ]; then
    if [ "$COUNT" -lt 2 ]; then
      echo 10
    else
      echo 8
    fi
    return
  fi

  if [ "$KIND" = "LIGHT_ONLY" ]; then
    if [ "$NIGHT" = "1" ]; then
      if [ "$COUNT" -lt 3 ]; then
        echo 180
      elif [ "$COUNT" -lt 6 ]; then
        echo 120
      else
        echo 90
      fi
    else
      if [ "$COUNT" -lt 3 ]; then
        echo 60
      elif [ "$COUNT" -lt 6 ]; then
        echo 45
      else
        echo 30
      fi
    fi
    return
  fi

  if [ "$COUNT" -lt 3 ]; then
    echo 60
  elif [ "$COUNT" -lt 6 ]; then
    echo 45
  else
    echo 30
  fi
}

echo "=================================================="
echo "ELF2 Sensor Watch Loop v4 adaptive"
echo "SENSOR_PERIOD          = $SENSOR_PERIOD"
echo "SENSOR_TRIGGER_IN_READY = $SENSOR_TRIGGER_IN_READY"
echo "=================================================="

COUNT=0

while true; do
  COUNT=$((COUNT + 1))

  MODE=$(cat "$STATE_DIR/mode" 2>/dev/null || echo READY)
  ALARM=$(cat "$STATE_DIR/alarm_enabled" 2>/dev/null || echo 1)
  NIGHT=$(cat "$STATE_DIR/night_mode" 2>/dev/null || echo 0)

  STAMP=$(date +"%Y%m%d_%H%M%S")
  CHECK_LOG="$LOG_DIR/sensor_latest_check.txt"

  echo
  echo "================ sensor round $COUNT ================"
  echo "time = $(date '+%Y-%m-%d %H:%M:%S')"
  echo "MODE=$MODE ALARM=$ALARM NIGHT=$NIGHT"

  OUT=$(sudo python3 "$ALERT_SCRIPT" \
    --url http://127.0.0.1:9/alert \
    --no-send \
    --no-capture \
    2>&1 || true)

  printf "%s\n" "$OUT" > "$CHECK_LOG"

  ABNORMAL=0
  HAS_LIGHT=0
  HAS_MOTION=0

  if printf "%s\n" "$OUT" | grep -q "Abnormal: True"; then
    ABNORMAL=1
  fi

  if printf "%s\n" "$OUT" | grep -qi "LIGHT_DARK\|Decision:.*LIGHT_DARK\|Problems:.*LIGHT_DARK\|BH1750:.*DARK\|stdout.*DARK"; then
    ABNORMAL=1
    HAS_LIGHT=1
  fi

  if printf "%s\n" "$OUT" | grep -qi "MOTION_\|SHAKING\|TAMPER\|MOVING"; then
    ABNORMAL=1
    HAS_MOTION=1
  fi

  DECISION=$(printf "%s\n" "$OUT" | sed -n 's/^Decision:[[:space:]]*//p' | tail -n 1)
  PROBLEMS=$(printf "%s\n" "$OUT" | sed -n 's/^Problems:[[:space:]]*//p' | tail -n 1)

  KIND="OTHER"
  if [ "$HAS_LIGHT" = "1" ] && [ "$HAS_MOTION" = "1" ]; then
    KIND="MIXED"
  elif [ "$HAS_MOTION" = "1" ]; then
    KIND="MOTION"
  elif [ "$HAS_LIGHT" = "1" ]; then
    KIND="LIGHT_ONLY"
  fi

  if [ "$ABNORMAL" = "0" ]; then
    echo "0" > "$STATE_DIR/sensor_abnormal_count"
    echo "0" > "$STATE_DIR/sensor_adaptive_cooldown"
    echo "NORMAL" > "$STATE_DIR/sensor_last_kind"
    echo "SENSOR_ABNORMAL=0 DECISION=${DECISION:-none} PROBLEMS=${PROBLEMS:-none}"
    sleep "$SENSOR_PERIOD"
    continue
  fi

  OLD_COUNT=$(cat "$STATE_DIR/sensor_abnormal_count" 2>/dev/null || echo 0)
  NEW_COUNT=$((OLD_COUNT + 1))
  echo "$NEW_COUNT" > "$STATE_DIR/sensor_abnormal_count"
  echo "$KIND" > "$STATE_DIR/sensor_last_kind"

  COOLDOWN=$(choose_cooldown "$KIND" "$NEW_COUNT" "$NIGHT")
  echo "$COOLDOWN" > "$STATE_DIR/sensor_adaptive_cooldown"

  echo "SENSOR_ABNORMAL=1 KIND=$KIND COUNT=$NEW_COUNT COOLDOWN=${COOLDOWN}s DECISION=${DECISION:-none} PROBLEMS=${PROBLEMS:-none}"

  # 始终检测和记录，但是否触发抓拍受 MODE / ALARM 控制
  if [ "$MODE" != "RUNNING" ] && [ "$SENSOR_TRIGGER_IN_READY" != "1" ]; then
    echo "sensor abnormal recorded, but no capture: MODE=$MODE SENSOR_TRIGGER_IN_READY=$SENSOR_TRIGGER_IN_READY"
    sleep "$SENSOR_PERIOD"
    continue
  fi

  if [ "$ALARM" != "1" ]; then
    echo "sensor abnormal recorded, but no capture: alarm_enabled=0"
    sleep "$SENSOR_PERIOD"
    continue
  fi

  NOW=$(date +%s)
  LAST=$(cat "$STATE_DIR/last_sensor_trigger_ts" 2>/dev/null || echo 0)
  DIFF=$((NOW - LAST))

  # 第一次异常、运动异常首次出现时，优先立即触发
  if [ "$NEW_COUNT" -eq 1 ]; then
    echo "first abnormal in current sequence: bypass cooldown"
  elif [ "$KIND" = "MOTION" ] && [ "$DIFF" -lt 5 ]; then
    echo "motion trigger minimum guard active: ${DIFF}s < 5s"
    sleep "$SENSOR_PERIOD"
    continue
  elif [ "$KIND" = "MOTION" ] || [ "$KIND" = "MIXED" ]; then
    if [ "$DIFF" -lt "$COOLDOWN" ]; then
      echo "motion adaptive cooldown active: ${DIFF}s < ${COOLDOWN}s"
      sleep "$SENSOR_PERIOD"
      continue
    fi
  else
    if [ "$DIFF" -lt "$COOLDOWN" ]; then
      echo "adaptive cooldown active: ${DIFF}s < ${COOLDOWN}s"
      sleep "$SENSOR_PERIOD"
      continue
    fi
  fi

  echo "$NOW" > "$STATE_DIR/last_sensor_trigger_ts"

  TRIG_LOG="$LOG_DIR/sensor_trigger_${STAMP}_${KIND}.txt"
  {
    echo "===== SENSOR TRIGGER ====="
    echo "time=$(date '+%Y-%m-%d %H:%M:%S')"
    echo "kind=$KIND"
    echo "count=$NEW_COUNT"
    echo "cooldown=$COOLDOWN"
    echo "decision=${DECISION:-none}"
    echo "problems=${PROBLEMS:-none}"
    echo
    printf "%s\n" "$OUT"
  } > "$TRIG_LOG"

  echo "Trigger immediate AI capture because persistent sensor abnormal..."
  echo "TRIG_LOG=$TRIG_LOG"

  TRIGGER_TYPE="sensor_abnormal_${KIND}" \
  SELECTED_EVENT="${DECISION:-SENSOR_ABNORMAL_${KIND}}" \
  VOICE_TEXT="SENSOR_ABNORMAL kind=${KIND} count=${NEW_COUNT} cooldown=${COOLDOWN} problems=${PROBLEMS:-}" \
  VOICE_LOG="$TRIG_LOG" \
  WAIT_FOR_LOCK=1 \
  AI_TIMEOUT="$AI_TIMEOUT" \
  FACE_THRESHOLD="$FACE_THRESHOLD" \
  bash "$CAPTURE_ONCE" &

  sleep "$SENSOR_PERIOD"
done

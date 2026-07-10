#!/usr/bin/env bash
set -u

REC_SECONDS="${REC_SECONDS:-7}"
REQUIRE_WAKEUP="${REQUIRE_WAKEUP:-1}"
AI_TIMEOUT="${AI_TIMEOUT:-120}"
FACE_THRESHOLD="${FACE_THRESHOLD:-0.10}"

LISTEN_INTERVAL="${LISTEN_INTERVAL:-${INTERVAL:-2}}"
CAPTURE_INTERVAL="${CAPTURE_INTERVAL:-60}"
MAX_CAPTURE_ROUNDS="${MAX_CAPTURE_ROUNDS:-0}"
LISTEN_ROUNDS="${LISTEN_ROUNDS:-0}"

VOICE_ONCE="/home/elf/sensor_work/day29_ai/voice_capture_ai_once.sh"
AI_TRIGGER="/home/elf/sensor_work/day29_ai/ai_event_trigger_once.sh"
POLICY_SCRIPT="/home/elf/sensor_work/day31_policy/security_decision_engine.py"
FORMAT_SCRIPT="/home/elf/sensor_work/day31_policy/format_security_report.py"
EXPORT_SCRIPT="/home/elf/sensor_work/day30_web/export_latest_ai_web.py"

WEB_ROOT="/home/elf/project_evidence/day30_ai_web"
LOG_DIR="/home/elf/project_evidence/day32_productization/interval_ai_logs"

mkdir -p "$WEB_ROOT" "$LOG_DIR"

echo "=================================================="
echo "ELF2 Voice-triggered Interval AI Loop"
echo "=================================================="
echo "REC_SECONDS        = $REC_SECONDS"
echo "REQUIRE_WAKEUP     = $REQUIRE_WAKEUP"
echo "AI_TIMEOUT         = $AI_TIMEOUT"
echo "FACE_THRESHOLD     = $FACE_THRESHOLD"
echo "LISTEN_INTERVAL    = $LISTEN_INTERVAL"
echo "CAPTURE_INTERVAL   = $CAPTURE_INTERVAL"
echo "MAX_CAPTURE_ROUNDS = $MAX_CAPTURE_ROUNDS"
echo "LISTEN_ROUNDS      = $LISTEN_ROUNDS"
echo "WEB_ROOT           = $WEB_ROOT"
echo "=================================================="

if [ ! -f "$VOICE_ONCE" ]; then
  echo "ERROR: voice one-shot script not found: $VOICE_ONCE"
  exit 2
fi

if [ ! -f "$AI_TRIGGER" ]; then
  echo "ERROR: AI trigger script not found: $AI_TRIGGER"
  exit 3
fi

echo "[0] Refresh sudo credential..."
sudo -v || exit 10

echo "[1] Check web server 8090..."
if ! ss -lntp 2>/dev/null | grep -q ':8090'; then
  echo "8090 not listening. Starting http.server..."
  cd "$WEB_ROOT"
  nohup python3 -m http.server 8090 --bind 0.0.0.0 \
    > "$WEB_ROOT/http_server_8090.log" 2>&1 &
  sleep 1
else
  echo "8090 already listening."
fi

postprocess_latest_event() {
  local WEB_LOG="$1"
  local EVENT

  EVENT=$(ls -td /home/elf/project_evidence/abnormal_events/* 2>/dev/null | head -n 1)

  if [ -z "${EVENT:-}" ] || [ ! -d "$EVENT" ]; then
    echo "ERROR: latest event not found" | tee -a "$WEB_LOG"
    return 1
  fi

  echo "Postprocess EVENT=$EVENT" | tee -a "$WEB_LOG"

  python3 "$POLICY_SCRIPT" \
    --event-dir "$EVENT" \
    2>&1 | tee -a "$WEB_LOG"

  python3 "$FORMAT_SCRIPT" \
    --event-dir "$EVENT" \
    2>&1 | tee -a "$WEB_LOG"

  python3 "$EXPORT_SCRIPT" \
    2>&1 | tee -a "$WEB_LOG"

  echo "HTML updated: http://192.168.137.12:8090/" | tee -a "$WEB_LOG"
}

run_interval_capture() {
  local ROUND=0

  while true; do
    ROUND=$((ROUND + 1))

    if [ "$MAX_CAPTURE_ROUNDS" != "0" ] && [ "$ROUND" -gt "$MAX_CAPTURE_ROUNDS" ]; then
      echo "Interval capture finished. Back to voice listening."
      break
    fi

    local STAMP
    STAMP=$(date +"%Y%m%d_%H%M%S")

    local AI_LOG="$LOG_DIR/interval_${ROUND}_${STAMP}_ai.txt"
    local WEB_LOG="$LOG_DIR/interval_${ROUND}_${STAMP}_web.txt"

    echo
    echo "================ interval capture round $ROUND ================"
    echo "Force capture + FaceAuth + Qwen2-VL + DeepSeek..."
    echo "AI_LOG=$AI_LOG"

    FORCE_ALERT=1 \
    NO_SEND=1 \
    IGNORE_MPU_OFFLINE=0 \
    AI_TIMEOUT="$AI_TIMEOUT" \
    FACE_THRESHOLD="$FACE_THRESHOLD" \
    bash "$AI_TRIGGER" \
    2>&1 | tee "$AI_LOG"

    if grep -q "RESULT=OK" "$AI_LOG"; then
      echo "[web] AI event done. Generate security decision, final report, and HTML..."
      postprocess_latest_event "$WEB_LOG"
    else
      echo "WARN: interval AI trigger did not finish with RESULT=OK"
    fi

    echo "sleep ${CAPTURE_INTERVAL}s before next interval capture..."
    sleep "$CAPTURE_INTERVAL"
  done
}

LISTEN_COUNT=0

while true; do
  LISTEN_COUNT=$((LISTEN_COUNT + 1))

  if [ "$LISTEN_ROUNDS" != "0" ] && [ "$LISTEN_COUNT" -gt "$LISTEN_ROUNDS" ]; then
    echo "Listen loop finished."
    break
  fi

  STAMP=$(date +"%Y%m%d_%H%M%S")
  VOICE_LOG="$LOG_DIR/listen_${LISTEN_COUNT}_${STAMP}_voice_ai.txt"
  WEB_LOG="$LOG_DIR/listen_${LISTEN_COUNT}_${STAMP}_web.txt"

  echo
  echo "================ voice listen round $LISTEN_COUNT ================"
  echo "请说：唤醒词 + 抓拍"
  echo "例如：小平同志，抓拍"
  echo "VOICE_LOG=$VOICE_LOG"

  REC_SECONDS="$REC_SECONDS" \
  REQUIRE_WAKEUP="$REQUIRE_WAKEUP" \
  AI_TIMEOUT="$AI_TIMEOUT" \
  FACE_THRESHOLD="$FACE_THRESHOLD" \
  bash "$VOICE_ONCE" \
  2>&1 | tee "$VOICE_LOG"

  if grep -q "RESULT=VOICE_CAPTURE_AI_DONE" "$VOICE_LOG"; then
    echo
    echo "VOICE_CAPTURE detected and first AI report done."
    echo "[web] Generate security decision, final report, and HTML for first capture..."
    postprocess_latest_event "$WEB_LOG"

    echo
    echo "=================================================="
    echo "进入每分钟自动 AI 抓拍模式"
    echo "每轮完成后等待 ${CAPTURE_INTERVAL}s"
    echo "停止请执行：bash ~/elf2_stop.sh"
    echo "=================================================="

    sleep "$CAPTURE_INTERVAL"
    run_interval_capture
  else
    echo "No valid capture command. Continue listening after ${LISTEN_INTERVAL}s..."
    sleep "$LISTEN_INTERVAL"
  fi
done

echo "RESULT=OK"

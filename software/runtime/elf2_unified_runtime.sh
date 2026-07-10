#!/usr/bin/env bash
set -u

WEB_ROOT="/home/elf/project_evidence/day30_ai_web"
WEB_PORT=8090

VOICE_LOOP="/home/elf/sensor_work/day32_product_ops/elf2_voice_command_loop_10s.sh"
INTERVAL_LOOP="/home/elf/sensor_work/day32_product_ops/elf2_interval_capture_loop.sh"
SENSOR_LOOP="/home/elf/sensor_work/day32_product_ops/elf2_sensor_watch_loop.sh"

LOG_DIR="/home/elf/project_evidence/day32_productization/unified_runtime_logs"
STATE_DIR="/home/elf/project_evidence/day32_productization/runtime_state"

mkdir -p "$WEB_ROOT" "$LOG_DIR" "$STATE_DIR"

echo "=================================================="
echo "ELF2 Unified Runtime v3"
echo "time = $(date '+%Y-%m-%d %H:%M:%S')"
echo "=================================================="

sudo -v || exit 10

if ! ss -lntp 2>/dev/null | grep -q ":${WEB_PORT}"; then
  echo "Starting HTML server on ${WEB_PORT}..."
  cd "$WEB_ROOT"
  nohup python3 -m http.server "$WEB_PORT" --bind 0.0.0.0 \
    > "$LOG_DIR/http_server_${WEB_PORT}.log" 2>&1 &
else
  echo "HTML server already running on ${WEB_PORT}."
fi

echo "READY" > "$STATE_DIR/mode"
echo "0" > "$STATE_DIR/auto_capture_enabled"
[ -f "$STATE_DIR/alarm_enabled" ] || echo "1" > "$STATE_DIR/alarm_enabled"
[ -f "$STATE_DIR/night_mode" ] || echo "0" > "$STATE_DIR/night_mode"

VOICE_LOG="$LOG_DIR/voice_command_loop_$(date +%Y%m%d_%H%M%S).log"
INTERVAL_LOG="$LOG_DIR/interval_capture_loop_$(date +%Y%m%d_%H%M%S).log"
SENSOR_LOG="$LOG_DIR/sensor_watch_loop_$(date +%Y%m%d_%H%M%S).log"

echo "Starting voice command loop..."
nohup env \
  VOICE_PERIOD=10 \
  REC_SECONDS=7 \
  AI_TIMEOUT=120 \
  FACE_THRESHOLD=0.363 \
  bash "$VOICE_LOOP" \
  > "$VOICE_LOG" 2>&1 &

VOICE_PID=$!
echo "$VOICE_PID" > "$STATE_DIR/voice_loop.pid"

echo "Starting interval capture loop..."
nohup env \
  CAPTURE_INTERVAL=60 \
  IDLE_CHECK_INTERVAL=5 \
  AI_TIMEOUT=120 \
  FACE_THRESHOLD=0.363 \
  bash "$INTERVAL_LOOP" \
  > "$INTERVAL_LOG" 2>&1 &

INTERVAL_PID=$!
echo "$INTERVAL_PID" > "$STATE_DIR/interval_loop.pid"

echo "Starting sensor watch loop..."
nohup env \
  SENSOR_PERIOD=5 \
  SENSOR_COOLDOWN=60 \
  AI_TIMEOUT=120 \
  FACE_THRESHOLD=0.363 \
  bash "$SENSOR_LOOP" \
  > "$SENSOR_LOG" 2>&1 &

SENSOR_PID=$!
echo "$SENSOR_PID" > "$STATE_DIR/sensor_loop.pid"

echo "VOICE_PID=$VOICE_PID"
echo "INTERVAL_PID=$INTERVAL_PID"
echo "SENSOR_PID=$SENSOR_PID"
echo "HTML_URL=http://192.168.137.12:${WEB_PORT}/"
echo "RESULT=OK"

wait

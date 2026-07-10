#!/usr/bin/env bash
set -u
cd /home/elf/project_evidence/day29_ai_event_analysis
mkdir -p realtime_ai_logs
STAMP=$(date +%Y%m%d_%H%M%S)
ALERT_LOG=realtime_ai_logs/alert_$STAMP.txt
AI_LOG=realtime_ai_logs/ai_$STAMP.txt
EXTRA=""
[ "${FORCE_ALERT:-0}" = "1" ] && EXTRA="--force-alert"
ALERT_URL="${ALERT_URL:-http://127.0.0.1:9/alert}"

CMD=(sudo python3 /home/elf/sensor_work/day24_network_alert/abnormal_event_check_and_alert_v3.py --url "$ALERT_URL")

if [ "${IGNORE_MPU_OFFLINE:-0}" = "1" ]; then
  CMD+=(--ignore-mpu-offline)
fi

if [ "${NO_SEND:-1}" = "1" ]; then
  CMD+=(--no-send)
fi

if [ "${FORCE_ALERT:-0}" = "1" ]; then
  CMD+=(--force-alert)
fi

if [ "${NO_CAPTURE:-0}" = "1" ]; then
  CMD+=(--no-capture)
fi

"${CMD[@]}" 2>&1 | tee "$ALERT_LOG"
EVENT_DIR=$(sed -n "s/^Event directory: //p" "$ALERT_LOG" | tail -n 1 | xargs)
echo "EVENT_DIR=${EVENT_DIR:-none}"
[ -z "${EVENT_DIR:-}" ] && { echo "RESULT=NO_AI_ANALYSIS"; exit 0; }
sudo chown -R elf:elf "$EVENT_DIR"

FACE_LOG="realtime_ai_logs/face_$STAMP.txt"
IMG="$EVENT_DIR/camera_input.jpg"

echo "Running FaceAuth whitelist check..."
python3 /home/elf/sensor_work/day30_face_auth/face_whitelist_check_once.py --image "$IMG" --threshold "${FACE_THRESHOLD:-0.45}" 2>&1 | tee "$FACE_LOG"

FACE_STATUS=$(grep -o "FACE_STATUS=[A-Z_]*" "$FACE_LOG" | tail -n 1 | cut -d= -f2)
FACE_RESULT_JSON=$(sed -n "s/^result_json = //p" "$FACE_LOG" | tail -n 1 | xargs)

echo "FACE_STATUS=${FACE_STATUS:-UNKNOWN}" | tee "$EVENT_DIR/face_status.txt"

if [ -n "${FACE_RESULT_JSON:-}" ] && [ -f "$FACE_RESULT_JSON" ]; then
  cp "$FACE_RESULT_JSON" "$EVENT_DIR/face_auth_result.json"
fi

python3 -u /home/elf/sensor_work/day29_ai/ai_event_analyze_once.py --event-dir "$EVENT_DIR" --timeout "${AI_TIMEOUT:-180}" 2>&1 | tee "$AI_LOG"
echo "AI_REPORT=$EVENT_DIR/event_ai_report.txt"
echo "RESULT=OK"

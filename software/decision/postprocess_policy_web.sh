#!/usr/bin/env bash
set -u

EVENT_DIR="${1:-}"
POLICY_SCRIPT="/home/elf/sensor_work/day31_policy/security_decision_engine.py"
EXPORT_SCRIPT="/home/elf/sensor_work/day30_web/export_latest_ai_web.py"

if [ -z "$EVENT_DIR" ]; then
  EVENT_DIR=$(ls -td /home/elf/project_evidence/abnormal_events/* 2>/dev/null | head -n 1)
fi

if [ -z "$EVENT_DIR" ] || [ ! -d "$EVENT_DIR" ]; then
  echo "ERROR: event dir not found"
  exit 2
fi

echo "=================================================="
echo "Postprocess policy + web"
echo "EVENT_DIR = $EVENT_DIR"
echo "=================================================="

python3 "$POLICY_SCRIPT" --event-dir "$EVENT_DIR" 2>&1

if [ -f "$EXPORT_SCRIPT" ]; then
  python3 "$EXPORT_SCRIPT" 2>&1
else
  echo "WARN: export script not found: $EXPORT_SCRIPT"
fi

echo "RESULT=OK"
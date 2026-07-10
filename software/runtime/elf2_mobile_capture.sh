#!/bin/bash
set -euo pipefail

export TRIGGER_TYPE=mobile_web
export SELECTED_EVENT=WEB_CAPTURE
export VOICE_TEXT=""
export PREEMPT_AI=0

CAPTURE_SCRIPT="/home/elf/camera_yolo_work/capture_detect_display_filtered_timeout.sh"
ALT_SCRIPT="/home/elf/camera_yolo_work/capture_detect_display_filtered.sh"

echo "=================================================="
echo "ELF2 Mobile Capture Wrapper"
echo "time=$(date '+%F %T')"
echo "TRIGGER_TYPE=${TRIGGER_TYPE}"
echo "SELECTED_EVENT=${SELECTED_EVENT}"
echo "=================================================="

cd /home/elf/camera_yolo_work

if [ -x "$CAPTURE_SCRIPT" ]; then
    bash "$CAPTURE_SCRIPT"
elif [ -x "$ALT_SCRIPT" ]; then
    bash "$ALT_SCRIPT"
else
    echo "ERROR: no capture display script found"
    exit 1
fi

echo "Decision: MOBILE_CAPTURE"
echo "Abnormal: False"
echo "RESULT=NO_ALERT"
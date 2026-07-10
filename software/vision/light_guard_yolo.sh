#!/bin/bash
set -e

# ==================================================
# BH1750 light guard + YOLOv5 visual detection
# ==================================================
# Logic:
#   DARK          -> skip YOLO, show warning image on MIPI screen
#   NORMAL/BRIGHT -> run YOLO detection + MIPI display
#
# Usage:
#   ./light_guard_yolo.sh
#   ./light_guard_yolo.sh --conf 0.20
#   ./light_guard_yolo.sh --classes "person,bottle,cell phone"
# ==================================================

SENSOR_SCRIPT="/home/elf/sensor_work/bh1750_day10/bh1750_check_status.py"
VISION_SCRIPT="/home/elf/camera_yolo_work/capture_detect_display_filtered.sh"

YOLO_DIR="/home/elf/camera_yolo_work"
WARNING_IMAGE="${YOLO_DIR}/light_warning_dark.jpg"

DARK_THRESHOLD=30
BRIGHT_THRESHOLD=1000
SAMPLES=5
INTERVAL=0.2

WARNING_DISPLAY_TIME=8

prepare_wayland() {
    if [ -S "/run/user/1000/wayland-0" ]; then
        export XDG_RUNTIME_DIR="/run/user/1000"
        export WAYLAND_DISPLAY="wayland-0"
    elif [ -S "/run/user/1000/wayland-1" ]; then
        export XDG_RUNTIME_DIR="/run/user/1000"
        export WAYLAND_DISPLAY="wayland-1"
    elif [ -n "${XDG_RUNTIME_DIR}" ] && [ -S "${XDG_RUNTIME_DIR}/wayland-0" ]; then
        export WAYLAND_DISPLAY="wayland-0"
    elif [ -n "${XDG_RUNTIME_DIR}" ] && [ -S "${XDG_RUNTIME_DIR}/wayland-1" ]; then
        export WAYLAND_DISPLAY="wayland-1"
    else
        echo "[WARN] Could not find Wayland socket. MIPI warning image may not display."
        return 1
    fi
}

show_dark_warning() {
    local avg_lux="$1"

    echo "[INFO] Creating dark warning image: ${WARNING_IMAGE}"

    python3 - <<PY
import cv2
import numpy as np
from datetime import datetime

out_path = "${WARNING_IMAGE}"
avg_lux = "${avg_lux}"

img = np.zeros((480, 640, 3), dtype=np.uint8)

cv2.putText(img, "LIGHT WARNING", (95, 110),
            cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 255, 255), 3, cv2.LINE_AA)

cv2.putText(img, "Environment is too dark", (85, 190),
            cv2.FONT_HERSHEY_SIMPLEX, 0.95, (255, 255, 255), 2, cv2.LINE_AA)

cv2.putText(img, f"avg lux = {avg_lux}", (165, 250),
            cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2, cv2.LINE_AA)

cv2.putText(img, "YOLO detection skipped", (105, 315),
            cv2.FONT_HERSHEY_SIMPLEX, 0.95, (0, 0, 255), 2, cv2.LINE_AA)

cv2.putText(img, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), (150, 390),
            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (180, 180, 180), 2, cv2.LINE_AA)

cv2.imwrite(out_path, img)
print(out_path)
PY

    ls -lh "${WARNING_IMAGE}"
    file "${WARNING_IMAGE}"

    if prepare_wayland; then
        echo "[INFO] Displaying dark warning image on MIPI screen for ${WARNING_DISPLAY_TIME}s..."
        timeout "${WARNING_DISPLAY_TIME}" gst-launch-1.0 -q filesrc location="${WARNING_IMAGE}" ! \
        jpegdec ! videoconvert ! imagefreeze ! video/x-raw,framerate=1/1 ! \
        waylandsink sync=false || true
    else
        echo "[WARN] Wayland unavailable. Warning image generated but not displayed."
    fi
}

echo "=================================================="
echo "BH1750 light guard + YOLOv5 detection"
echo "=================================================="
echo "SENSOR_SCRIPT = ${SENSOR_SCRIPT}"
echo "VISION_SCRIPT = ${VISION_SCRIPT}"
echo "DARK_THRESHOLD = ${DARK_THRESHOLD}"
echo "BRIGHT_THRESHOLD = ${BRIGHT_THRESHOLD}"
echo

if [ ! -f "${SENSOR_SCRIPT}" ]; then
    echo "[ERROR] Sensor script not found: ${SENSOR_SCRIPT}"
    exit 1
fi

if [ ! -f "${VISION_SCRIPT}" ]; then
    echo "[ERROR] Vision script not found: ${VISION_SCRIPT}"
    exit 1
fi

echo "[1/2] Checking light condition with BH1750..."

RESULT=$(sudo python3 "${SENSOR_SCRIPT}" \
    --samples "${SAMPLES}" \
    --interval "${INTERVAL}" \
    --dark "${DARK_THRESHOLD}" \
    --bright "${BRIGHT_THRESHOLD}" \
    --plain)

STATUS=$(echo "${RESULT}" | awk '{print $1}')
AVG_LUX=$(echo "${RESULT}" | awk '{print $2}')

echo "BH1750 result: status=${STATUS}, avg_lux=${AVG_LUX}"

if [ "${STATUS}" = "DARK" ]; then
    echo "[2/2] Environment is DARK. Skip YOLO detection."
    show_dark_warning "${AVG_LUX}"
    echo "Finished: DARK -> visual detection skipped."
    exit 0
fi

echo "[2/2] Light condition is ${STATUS}. Running YOLO detection and MIPI display..."
cd "${YOLO_DIR}"
"${VISION_SCRIPT}" "$@"
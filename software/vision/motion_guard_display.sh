#!/bin/bash
set -e

# ==================================================
# MPU6050 motion guard + MIPI warning display
# ==================================================
# Logic:
#   STABLE  -> no warning
#   MOVING  -> generate and display movement warning image
#   SHAKING -> generate and display shaking warning image
#
# Usage:
#   ./motion_guard_display.sh
#   ./motion_guard_display.sh --display-time 8
#   ./motion_guard_display.sh --samples 20
#   ./motion_guard_display.sh --move-gyro 45 --shake-gyro 120
# ==================================================

MOTION_SCRIPT="/home/elf/sensor_work/mpu6050_day11/mpu6050_check_motion.py"
YOLO_DIR="/home/elf/camera_yolo_work"
WARNING_IMAGE="${YOLO_DIR}/motion_warning.jpg"

DISPLAY_TIME=8
SAMPLES=15
INTERVAL=0.1

MOVE_GYRO=35
SHAKE_GYRO=90
MOVE_ACCEL_DELTA=0.18
SHAKE_ACCEL_DELTA=0.35

while [[ $# -gt 0 ]]; do
    case "$1" in
        --display-time)
            DISPLAY_TIME="$2"
            shift 2
            ;;
        --samples)
            SAMPLES="$2"
            shift 2
            ;;
        --interval)
            INTERVAL="$2"
            shift 2
            ;;
        --move-gyro)
            MOVE_GYRO="$2"
            shift 2
            ;;
        --shake-gyro)
            SHAKE_GYRO="$2"
            shift 2
            ;;
        --move-accel-delta)
            MOVE_ACCEL_DELTA="$2"
            shift 2
            ;;
        --shake-accel-delta)
            SHAKE_ACCEL_DELTA="$2"
            shift 2
            ;;
        *)
            echo "[ERROR] Unknown argument: $1"
            echo "Usage:"
            echo "  ./motion_guard_display.sh"
            echo "  ./motion_guard_display.sh --display-time 8"
            echo "  ./motion_guard_display.sh --samples 20"
            echo "  ./motion_guard_display.sh --move-gyro 45 --shake-gyro 120"
            exit 1
            ;;
    esac
done

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
        echo "[WARN] Could not find Wayland socket. Warning image may not display."
        return 1
    fi
}

create_warning_image() {
    local status="$1"
    local max_gyro="$2"
    local max_acc_delta="$3"

    echo "[INFO] Creating motion warning image: ${WARNING_IMAGE}"

    python3 - <<PY
import cv2
import numpy as np
from datetime import datetime

out_path = "${WARNING_IMAGE}"
status = "${status}"
max_gyro = "${max_gyro}"
max_acc_delta = "${max_acc_delta}"

img = np.zeros((480, 640, 3), dtype=np.uint8)

if status == "SHAKING":
    title = "MOTION WARNING"
    line1 = "Strong shaking detected"
    line2 = "Possible impact or tampering"
else:
    title = "MOTION NOTICE"
    line1 = "Device movement detected"
    line2 = "Please check device position"

cv2.putText(img, title, (75, 95),
            cv2.FONT_HERSHEY_SIMPLEX, 1.45, (0, 255, 255), 3, cv2.LINE_AA)

cv2.putText(img, f"Status: {status}", (125, 165),
            cv2.FONT_HERSHEY_SIMPLEX, 1.05, (255, 255, 255), 2, cv2.LINE_AA)

cv2.putText(img, line1, (70, 230),
            cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2, cv2.LINE_AA)

cv2.putText(img, line2, (55, 280),
            cv2.FONT_HERSHEY_SIMPLEX, 0.82, (0, 0, 255), 2, cv2.LINE_AA)

cv2.putText(img, f"max gyro = {max_gyro} dps", (120, 345),
            cv2.FONT_HERSHEY_SIMPLEX, 0.75, (180, 180, 180), 2, cv2.LINE_AA)

cv2.putText(img, f"max accel delta = {max_acc_delta} g", (95, 385),
            cv2.FONT_HERSHEY_SIMPLEX, 0.75, (180, 180, 180), 2, cv2.LINE_AA)

cv2.putText(img, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), (150, 435),
            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (180, 180, 180), 2, cv2.LINE_AA)

cv2.imwrite(out_path, img)
print(out_path)
PY
}

display_warning_image() {
    if prepare_wayland; then
        echo "[INFO] Displaying warning image on MIPI screen for ${DISPLAY_TIME}s..."
        timeout "${DISPLAY_TIME}" gst-launch-1.0 -q filesrc location="${WARNING_IMAGE}" ! \
        jpegdec ! videoconvert ! imagefreeze ! video/x-raw,framerate=1/1 ! \
        waylandsink sync=false || true
    else
        echo "[WARN] Wayland unavailable. Warning image generated but not displayed."
    fi
}

echo "=================================================="
echo "MPU6050 motion guard + MIPI warning display"
echo "=================================================="
echo "MOTION_SCRIPT       = ${MOTION_SCRIPT}"
echo "WARNING_IMAGE       = ${WARNING_IMAGE}"
echo "DISPLAY_TIME        = ${DISPLAY_TIME}s"
echo "SAMPLES             = ${SAMPLES}"
echo "INTERVAL            = ${INTERVAL}s"
echo "MOVE_GYRO           = ${MOVE_GYRO}"
echo "SHAKE_GYRO          = ${SHAKE_GYRO}"
echo "MOVE_ACCEL_DELTA    = ${MOVE_ACCEL_DELTA}"
echo "SHAKE_ACCEL_DELTA   = ${SHAKE_ACCEL_DELTA}"
echo

if [ ! -f "${MOTION_SCRIPT}" ]; then
    echo "[ERROR] Motion script not found: ${MOTION_SCRIPT}"
    exit 1
fi

echo "[1/3] Checking MPU6050 motion state..."

RESULT=$(sudo python3 "${MOTION_SCRIPT}" \
    --samples "${SAMPLES}" \
    --interval "${INTERVAL}" \
    --move-gyro "${MOVE_GYRO}" \
    --shake-gyro "${SHAKE_GYRO}" \
    --move-accel-delta "${MOVE_ACCEL_DELTA}" \
    --shake-accel-delta "${SHAKE_ACCEL_DELTA}" \
    --plain)

STATUS=$(echo "${RESULT}" | awk '{print $1}')
MAX_GYRO=$(echo "${RESULT}" | awk '{print $2}')
MAX_ACC_DELTA=$(echo "${RESULT}" | awk '{print $3}')

echo "MPU6050 result: status=${STATUS}, max_gyro=${MAX_GYRO}, max_acc_delta=${MAX_ACC_DELTA}"

if [ "${STATUS}" = "STABLE" ]; then
    echo "[2/3] Device is STABLE. No warning displayed."
    echo "[3/3] Finished."
    exit 0
fi

if [ "${STATUS}" != "MOVING" ] && [ "${STATUS}" != "SHAKING" ]; then
    echo "[ERROR] Unknown motion status: ${STATUS}"
    exit 1
fi

echo "[2/3] Motion abnormal: ${STATUS}. Creating warning image..."
create_warning_image "${STATUS}" "${MAX_GYRO}" "${MAX_ACC_DELTA}"

ls -lh "${WARNING_IMAGE}"
file "${WARNING_IMAGE}"

echo "[3/3] Displaying warning image..."
display_warning_image

echo "Finished: ${STATUS} -> warning displayed."
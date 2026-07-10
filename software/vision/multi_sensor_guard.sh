#!/bin/bash
set -e

# ==================================================
# Day14 multi-sensor guard
# BH1750 + MPU6050 + YOLO + MIPI display
# ==================================================
# Decision priority:
#   MOTION_SHAKING -> display strong motion warning
#   MOTION_MOVING  -> display movement warning
#   LIGHT_DARK     -> display dark warning
#   VISION_ALLOWED -> run YOLO detection and display result
# ==================================================

MULTI_SENSOR_SCRIPT="/home/elf/sensor_work/day14_multi_sensor/multi_sensor_check.py"
VISION_SCRIPT="/home/elf/camera_yolo_work/capture_detect_display_filtered_timeout.sh"

WORK_DIR="/home/elf/camera_yolo_work"
WARNING_IMAGE="${WORK_DIR}/multi_sensor_warning.jpg"

DISPLAY_TIME=8

# Tuned thresholds for breadboard + metal-base setup
MOVE_GYRO=25
SHAKE_GYRO=80
MOVE_ACCEL_DELTA=0.12
SHAKE_ACCEL_DELTA=0.30

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
    local decision="$1"
    local light_status="$2"
    local lux="$3"
    local motion_status="$4"
    local gyro="$5"
    local accdelta="$6"

    python3 - <<PY
import cv2
import numpy as np
from datetime import datetime

out_path = "${WARNING_IMAGE}"

decision = "${decision}"
light_status = "${light_status}"
lux = "${lux}"
motion_status = "${motion_status}"
gyro = "${gyro}"
accdelta = "${accdelta}"

img = np.zeros((480, 640, 3), dtype=np.uint8)

if decision == "MOTION_SHAKING":
    title = "MOTION WARNING"
    line1 = "Strong shaking detected"
    line2 = "Possible impact or tampering"
elif decision == "MOTION_MOVING":
    title = "MOTION NOTICE"
    line1 = "Device movement detected"
    line2 = "Please check device position"
elif decision == "LIGHT_DARK":
    title = "LIGHT WARNING"
    line1 = "Environment is too dark"
    line2 = "YOLO detection skipped"
else:
    title = "SYSTEM NOTICE"
    line1 = "Unknown system state"
    line2 = "Please check sensors"

cv2.putText(img, title, (70, 85),
            cv2.FONT_HERSHEY_SIMPLEX, 1.35, (0, 255, 255), 3, cv2.LINE_AA)

cv2.putText(img, f"Decision: {decision}", (55, 150),
            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2, cv2.LINE_AA)

cv2.putText(img, line1, (70, 215),
            cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2, cv2.LINE_AA)

cv2.putText(img, line2, (70, 265),
            cv2.FONT_HERSHEY_SIMPLEX, 0.82, (0, 0, 255), 2, cv2.LINE_AA)

cv2.putText(img, f"Light: {light_status}, lux={lux}", (65, 335),
            cv2.FONT_HERSHEY_SIMPLEX, 0.68, (180, 180, 180), 2, cv2.LINE_AA)

cv2.putText(img, f"Motion: {motion_status}, gyro={gyro}, acc={accdelta}", (65, 375),
            cv2.FONT_HERSHEY_SIMPLEX, 0.68, (180, 180, 180), 2, cv2.LINE_AA)

cv2.putText(img, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), (150, 430),
            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (180, 180, 180), 2, cv2.LINE_AA)

cv2.imwrite(out_path, img)
print(out_path)
PY
}

display_warning_image() {
    if prepare_wayland; then
        timeout "${DISPLAY_TIME}" gst-launch-1.0 -q filesrc location="${WARNING_IMAGE}" ! \
        jpegdec ! videoconvert ! imagefreeze ! video/x-raw,framerate=1/1 ! \
        waylandsink sync=false || true
    else
        echo "[WARN] Wayland unavailable. Warning image generated but not displayed."
    fi
}

echo "=================================================="
echo "Day14 multi-sensor guard"
echo "=================================================="
echo "MULTI_SENSOR_SCRIPT = ${MULTI_SENSOR_SCRIPT}"
echo "VISION_SCRIPT       = ${VISION_SCRIPT}"
echo "MOVE_GYRO           = ${MOVE_GYRO}"
echo "SHAKE_GYRO          = ${SHAKE_GYRO}"
echo "MOVE_ACCEL_DELTA    = ${MOVE_ACCEL_DELTA}"
echo "SHAKE_ACCEL_DELTA   = ${SHAKE_ACCEL_DELTA}"
echo

if [ ! -f "${MULTI_SENSOR_SCRIPT}" ]; then
    echo "[ERROR] Multi-sensor script not found: ${MULTI_SENSOR_SCRIPT}"
    exit 1
fi

if [ ! -f "${VISION_SCRIPT}" ]; then
    echo "[ERROR] Vision script not found: ${VISION_SCRIPT}"
    exit 1
fi

echo "[1/3] Checking multi-sensor status..."

RESULT=$(sudo python3 "${MULTI_SENSOR_SCRIPT}" --plain \
    --move-gyro "${MOVE_GYRO}" \
    --shake-gyro "${SHAKE_GYRO}" \
    --move-accel-delta "${MOVE_ACCEL_DELTA}" \
    --shake-accel-delta "${SHAKE_ACCEL_DELTA}")

echo "Multi-sensor result:"
echo "${RESULT}"

DECISION=$(echo "${RESULT}" | awk '{print $1}')
LIGHT_STATUS=$(echo "${RESULT}" | sed -n 's/.*LIGHT=\([^ ]*\).*/\1/p')
LUX=$(echo "${RESULT}" | sed -n 's/.*LUX=\([^ ]*\).*/\1/p')
MOTION_STATUS=$(echo "${RESULT}" | sed -n 's/.*MOTION=\([^ ]*\).*/\1/p')
GYRO=$(echo "${RESULT}" | sed -n 's/.*GYRO=\([^ ]*\).*/\1/p')
ACCDELTA=$(echo "${RESULT}" | sed -n 's/.*ACCDELTA=\([^ ]*\).*/\1/p')

echo
echo "Parsed:"
echo "DECISION      = ${DECISION}"
echo "LIGHT_STATUS  = ${LIGHT_STATUS}"
echo "LUX           = ${LUX}"
echo "MOTION_STATUS = ${MOTION_STATUS}"
echo "GYRO          = ${GYRO}"
echo "ACCDELTA      = ${ACCDELTA}"
echo

case "${DECISION}" in
    MOTION_SHAKING|MOTION_MOVING|LIGHT_DARK)
        echo "[2/3] Warning state detected: ${DECISION}"
        create_warning_image "${DECISION}" "${LIGHT_STATUS}" "${LUX}" "${MOTION_STATUS}" "${GYRO}" "${ACCDELTA}"
        ls -lh "${WARNING_IMAGE}"
        file "${WARNING_IMAGE}"
        echo "[3/3] Displaying warning image on MIPI screen..."
        display_warning_image
        echo "Finished: ${DECISION} -> warning displayed."
        ;;

    VISION_ALLOWED)
        echo "[2/3] Vision allowed. Running YOLO detection and MIPI display..."
        cd "${WORK_DIR}"
        "${VISION_SCRIPT}"
        echo "[3/3] Finished: YOLO detection displayed."
        ;;

    *)
        echo "[ERROR] Unknown decision: ${DECISION}"
        exit 1
        ;;
esac
#!/bin/bash
set -e

YOLO_DIR="/home/elf/camera_yolo_work"
DETECT_SCRIPT="${YOLO_DIR}/capture_and_detect_filtered.sh"
RESULT_IMAGE="${YOLO_DIR}/camera_yolo_result_filtered.jpg"
DISPLAY_TIME=15

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
        echo "[ERROR] Could not find Wayland socket."
        exit 1
    fi
}

echo "=================================================="
echo "Camera + YOLOv5 filtered detection + timed MIPI display"
echo "=================================================="
echo "YOLO_DIR      = ${YOLO_DIR}"
echo "DETECT_SCRIPT = ${DETECT_SCRIPT}"
echo "RESULT_IMAGE  = ${RESULT_IMAGE}"
echo "DISPLAY_TIME  = ${DISPLAY_TIME}s"
echo

echo "[1/3] Running filtered capture + YOLO detection..."
"${DETECT_SCRIPT}"

echo
echo "[2/3] Checking result image..."
ls -lh "${RESULT_IMAGE}"
file "${RESULT_IMAGE}"

echo
echo "[3/3] Displaying result image on MIPI screen for ${DISPLAY_TIME}s..."
prepare_wayland

timeout "${DISPLAY_TIME}" gst-launch-1.0 -q filesrc location="${RESULT_IMAGE}" ! \
jpegdec ! videoconvert ! imagefreeze ! video/x-raw,framerate=1/1 ! \
waylandsink sync=false || true

echo "Timed display finished."

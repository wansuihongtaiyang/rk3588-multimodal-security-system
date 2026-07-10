#!/bin/bash
set -e

# ==================================================
# Camera + YOLOv5 filtered detection + MIPI display
# ==================================================
# Usage examples:
#   ./capture_detect_display_filtered.sh
#   ./capture_detect_display_filtered.sh --conf 0.20
#   ./capture_detect_display_filtered.sh --classes "person,bottle,cell phone"
#   ./capture_detect_display_filtered.sh --classes all
#
# Note:
#   After the result image is displayed on screen,
#   this script will keep running.
#   Press Ctrl+C to exit display.
# ==================================================

YOLO_DIR="/home/elf/camera_yolo_work"

DETECT_SCRIPT="${YOLO_DIR}/capture_and_detect_filtered.sh"
RESULT_IMAGE="${YOLO_DIR}/camera_yolo_result_filtered.jpg"

echo "=================================================="
echo "Camera + YOLOv5 filtered detection + MIPI display"
echo "=================================================="
echo "YOLO_DIR      = ${YOLO_DIR}"
echo "DETECT_SCRIPT = ${DETECT_SCRIPT}"
echo "RESULT_IMAGE  = ${RESULT_IMAGE}"
echo

if [ ! -f "${DETECT_SCRIPT}" ]; then
    echo "[ERROR] Detection script not found: ${DETECT_SCRIPT}"
    exit 1
fi

if [ ! -x "${DETECT_SCRIPT}" ]; then
    echo "[INFO] Adding execute permission to detection script..."
    chmod +x "${DETECT_SCRIPT}"
fi

echo "[1/3] Running filtered capture + YOLO detection..."
cd "${YOLO_DIR}"
"${DETECT_SCRIPT}" "$@"

echo
echo "[2/3] Checking result image..."
if [ ! -f "${RESULT_IMAGE}" ]; then
    echo "[ERROR] Result image not found: ${RESULT_IMAGE}"
    exit 1
fi

ls -lh "${RESULT_IMAGE}"
file "${RESULT_IMAGE}"

echo
echo "[3/3] Preparing Wayland display environment..."

# Prefer normal desktop user session.
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
    echo "Please check:"
    echo "  find /run/user -maxdepth 2 -type s -name 'wayland-*'"
    exit 1
fi

echo "XDG_RUNTIME_DIR = ${XDG_RUNTIME_DIR}"
echo "WAYLAND_DISPLAY = ${WAYLAND_DISPLAY}"
echo
echo "Displaying result image on MIPI screen..."
echo "Press Ctrl+C to exit display."
echo

gst-launch-1.0 -v filesrc location="${RESULT_IMAGE}" ! \
jpegdec ! videoconvert ! imagefreeze ! video/x-raw,framerate=1/1 ! \
waylandsink sync=false
#!/bin/bash
set -e

# ==================================================
# Loop Camera + YOLOv5 filtered detection + MIPI display
# ==================================================
# Usage examples:
#   ./loop_capture_detect_display_filtered.sh
#   ./loop_capture_detect_display_filtered.sh --conf 0.20
#   ./loop_capture_detect_display_filtered.sh --classes "person,bottle,cell phone"
#   ./loop_capture_detect_display_filtered.sh --interval 3
#   ./loop_capture_detect_display_filtered.sh --display-time 5
#
# Press Ctrl+C to stop.
# ==================================================

YOLO_DIR="/home/elf/camera_yolo_work"

DETECT_SCRIPT="${YOLO_DIR}/capture_and_detect_filtered.sh"
RESULT_IMAGE="${YOLO_DIR}/camera_yolo_result_filtered.jpg"

INTERVAL=2
DISPLAY_TIME=5

EXTRA_ARGS=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        --interval)
            INTERVAL="$2"
            shift 2
            ;;
        --display-time)
            DISPLAY_TIME="$2"
            shift 2
            ;;
        --conf|--iou|--classes|--device|--buffers)
            EXTRA_ARGS+=("$1" "$2")
            shift 2
            ;;
        *)
            echo "[ERROR] Unknown argument: $1"
            echo "Usage:"
            echo "  ./loop_capture_detect_display_filtered.sh"
            echo "  ./loop_capture_detect_display_filtered.sh --conf 0.20"
            echo "  ./loop_capture_detect_display_filtered.sh --classes \"person,bottle,cell phone\""
            echo "  ./loop_capture_detect_display_filtered.sh --interval 3"
            echo "  ./loop_capture_detect_display_filtered.sh --display-time 5"
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
        echo "[ERROR] Could not find Wayland socket."
        echo "Please check:"
        echo "  find /run/user -maxdepth 2 -type s -name 'wayland-*'"
        exit 1
    fi
}

cleanup() {
    echo
    echo "Stopping loop detection..."
    pkill -f "gst-launch-1.0.*camera_yolo_result_filtered.jpg" 2>/dev/null || true
    echo "Stopped."
}

trap cleanup INT TERM

echo "=================================================="
echo "Loop Camera + YOLOv5 filtered detection + display"
echo "=================================================="
echo "YOLO_DIR      = ${YOLO_DIR}"
echo "DETECT_SCRIPT = ${DETECT_SCRIPT}"
echo "RESULT_IMAGE  = ${RESULT_IMAGE}"
echo "INTERVAL      = ${INTERVAL}s"
echo "DISPLAY_TIME  = ${DISPLAY_TIME}s"
echo "EXTRA_ARGS    = ${EXTRA_ARGS[*]}"
echo

if [ ! -f "${DETECT_SCRIPT}" ]; then
    echo "[ERROR] Detection script not found: ${DETECT_SCRIPT}"
    exit 1
fi

if [ ! -x "${DETECT_SCRIPT}" ]; then
    chmod +x "${DETECT_SCRIPT}"
fi

prepare_wayland

echo "XDG_RUNTIME_DIR = ${XDG_RUNTIME_DIR}"
echo "WAYLAND_DISPLAY = ${WAYLAND_DISPLAY}"
echo
echo "Press Ctrl+C to stop."
echo

ROUND=1

while true; do
    echo
    echo "================ ROUND ${ROUND} ================"

    echo "[1/3] Capture + detect..."
    cd "${YOLO_DIR}"
    "${DETECT_SCRIPT}" "${EXTRA_ARGS[@]}"

    echo
    echo "[2/3] Check result..."
    if [ ! -f "${RESULT_IMAGE}" ]; then
        echo "[ERROR] Result image not found: ${RESULT_IMAGE}"
        exit 1
    fi

    ls -lh "${RESULT_IMAGE}"
    file "${RESULT_IMAGE}"

    echo
    echo "[3/3] Display result on MIPI screen for ${DISPLAY_TIME}s..."

    timeout "${DISPLAY_TIME}" gst-launch-1.0 -q filesrc location="${RESULT_IMAGE}" ! \
    jpegdec ! videoconvert ! imagefreeze ! video/x-raw,framerate=1/1 ! \
    waylandsink sync=false || true

    echo "Round ${ROUND} finished. Waiting ${INTERVAL}s before next round..."
    sleep "${INTERVAL}"

    ROUND=$((ROUND + 1))
done
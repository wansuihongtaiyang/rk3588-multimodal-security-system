#!/bin/bash
set -e

# =========================
# Camera + YOLOv5 one-shot pipeline
# =========================

DEVICE="/dev/video11"

CAPTURE_DIR="/home/elf/camera_retest_after_replug"
YOLO_DIR="/home/elf/camera_yolo_work"

NUM_BUFFERS=120
WIDTH=640
HEIGHT=480
JPEG_QUALITY=95

CONF=0.15
IOU=0.45

FRAME_PREFIX="${CAPTURE_DIR}/auto"
LAST_FRAME="${CAPTURE_DIR}/auto_119.jpg"

YOLO_INPUT="${YOLO_DIR}/camera_input.jpg"
YOLO_RESULT="${YOLO_DIR}/camera_yolo_result.jpg"
YOLO_SCRIPT="${YOLO_DIR}/yolov5_camera_detect.py"

echo "========================================"
echo "Camera + YOLOv5 detection pipeline start"
echo "========================================"
echo "DEVICE      = ${DEVICE}"
echo "CAPTURE_DIR = ${CAPTURE_DIR}"
echo "YOLO_DIR    = ${YOLO_DIR}"
echo "CONF        = ${CONF}"
echo "IOU         = ${IOU}"
echo

mkdir -p "${CAPTURE_DIR}"
mkdir -p "${YOLO_DIR}"

if [ ! -e "${DEVICE}" ]; then
    echo "[ERROR] Camera device not found: ${DEVICE}"
    exit 1
fi

if [ ! -f "${YOLO_SCRIPT}" ]; then
    echo "[ERROR] YOLO script not found: ${YOLO_SCRIPT}"
    exit 1
fi

echo "[1/5] Cleaning old captured frames..."
rm -f "${CAPTURE_DIR}"/auto_*.jpg

echo "[2/5] Capturing ${NUM_BUFFERS} frames from ${DEVICE}..."
gst-launch-1.0 -e v4l2src device="${DEVICE}" num-buffers="${NUM_BUFFERS}" ! \
"video/x-raw,format=NV12,width=${WIDTH},height=${HEIGHT}" ! \
videoconvert ! jpegenc quality="${JPEG_QUALITY}" ! multifilesink location="${FRAME_PREFIX}_%03d.jpg"

echo
echo "[3/5] Checking last captured frame..."
if [ ! -f "${LAST_FRAME}" ]; then
    echo "[ERROR] Last frame not found: ${LAST_FRAME}"
    echo "Existing frames:"
    ls -lh "${CAPTURE_DIR}"/auto_*.jpg 2>/dev/null || true
    exit 1
fi

ls -lh "${LAST_FRAME}"
file "${LAST_FRAME}"

echo
echo "[4/5] Preparing YOLO input..."
cp "${LAST_FRAME}" "${YOLO_INPUT}"
ls -lh "${YOLO_INPUT}"
file "${YOLO_INPUT}"

echo
echo "[5/5] Running YOLOv5 detection..."
cd "${YOLO_DIR}"
python3 "${YOLO_SCRIPT}" \
    --image "${YOLO_INPUT}" \
    --out "${YOLO_RESULT}" \
    --conf "${CONF}" \
    --iou "${IOU}"

echo
echo "========================================"
echo "Pipeline finished"
echo "Raw image:"
echo "${YOLO_INPUT}"
echo "Result image:"
echo "${YOLO_RESULT}"
echo "========================================"

ls -lh "${YOLO_RESULT}"
file "${YOLO_RESULT}"
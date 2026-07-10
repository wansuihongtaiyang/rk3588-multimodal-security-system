#!/bin/bash
set -e

# =========================
# Camera + YOLOv5 filtered detection pipeline
# =========================
# Usage examples:
#   ./capture_and_detect_filtered.sh
#   ./capture_and_detect_filtered.sh --conf 0.20
#   ./capture_and_detect_filtered.sh --classes "person,bottle,cell phone"
#   ./capture_and_detect_filtered.sh --classes all
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

CLASSES="person,bottle,cell phone,cup,laptop,mouse,keyboard,book,chair"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --conf)
            CONF="$2"
            shift 2
            ;;
        --iou)
            IOU="$2"
            shift 2
            ;;
        --classes)
            CLASSES="$2"
            shift 2
            ;;
        --device)
            DEVICE="$2"
            shift 2
            ;;
        --buffers)
            NUM_BUFFERS="$2"
            shift 2
            ;;
        *)
            echo "[ERROR] Unknown argument: $1"
            echo "Usage:"
            echo "  ./capture_and_detect_filtered.sh"
            echo "  ./capture_and_detect_filtered.sh --conf 0.20"
            echo "  ./capture_and_detect_filtered.sh --classes \"person,bottle,cell phone\""
            echo "  ./capture_and_detect_filtered.sh --classes all"
            exit 1
            ;;
    esac
done

LAST_INDEX=$(printf "%03d" $((NUM_BUFFERS - 1)))

FRAME_PREFIX="${CAPTURE_DIR}/auto_filtered"
LAST_FRAME="${CAPTURE_DIR}/auto_filtered_${LAST_INDEX}.jpg"

YOLO_INPUT="${YOLO_DIR}/camera_input.jpg"
YOLO_RESULT="${YOLO_DIR}/camera_yolo_result_filtered.jpg"
YOLO_SCRIPT="${YOLO_DIR}/yolov5_camera_detect_filtered.py"

echo "================================================"
echo "Camera + YOLOv5 filtered detection pipeline start"
echo "================================================"
echo "DEVICE      = ${DEVICE}"
echo "CAPTURE_DIR = ${CAPTURE_DIR}"
echo "YOLO_DIR    = ${YOLO_DIR}"
echo "BUFFERS     = ${NUM_BUFFERS}"
echo "CONF        = ${CONF}"
echo "IOU         = ${IOU}"
echo "CLASSES     = ${CLASSES}"
echo

mkdir -p "${CAPTURE_DIR}"
mkdir -p "${YOLO_DIR}"

if [ ! -e "${DEVICE}" ]; then
    echo "[ERROR] Camera device not found: ${DEVICE}"
    exit 1
fi

if [ ! -f "${YOLO_SCRIPT}" ]; then
    echo "[ERROR] Filtered YOLO script not found: ${YOLO_SCRIPT}"
    echo "Please upload yolov5_camera_detect_filtered.py first."
    exit 1
fi

echo "[1/5] Cleaning old filtered captured frames..."
rm -f "${CAPTURE_DIR}"/auto_filtered_*.jpg

echo "[2/5] Capturing ${NUM_BUFFERS} frames from ${DEVICE}..."
gst-launch-1.0 -e v4l2src device="${DEVICE}" num-buffers="${NUM_BUFFERS}" ! \
"video/x-raw,format=NV12,width=${WIDTH},height=${HEIGHT}" ! \
videoconvert ! jpegenc quality="${JPEG_QUALITY}" ! multifilesink location="${FRAME_PREFIX}_%03d.jpg"

echo
echo "[3/5] Checking last captured frame..."
if [ ! -f "${LAST_FRAME}" ]; then
    echo "[ERROR] Last frame not found: ${LAST_FRAME}"
    echo "Existing frames:"
    ls -lh "${CAPTURE_DIR}"/auto_filtered_*.jpg 2>/dev/null || true
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
echo "[5/5] Running filtered YOLOv5 detection..."
cd "${YOLO_DIR}"
python3 "${YOLO_SCRIPT}" \
    --image "${YOLO_INPUT}" \
    --out "${YOLO_RESULT}" \
    --conf "${CONF}" \
    --iou "${IOU}" \
    --classes "${CLASSES}"

echo
echo "================================================"
echo "Filtered pipeline finished"
echo "Raw image:"
echo "${YOLO_INPUT}"
echo "Filtered result image:"
echo "${YOLO_RESULT}"
echo "================================================"

ls -lh "${YOLO_RESULT}"
file "${YOLO_RESULT}"
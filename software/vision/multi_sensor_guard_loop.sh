#!/bin/bash
set -e

# ==================================================
# Day15 multi-sensor guard loop with event log
# ==================================================
# This script repeatedly calls Day14 single-shot guard:
#   multi_sensor_guard.sh
#
# Each round:
#   1. Run one complete sensor decision + action cycle
#   2. Save round log
#   3. Parse decision and sensor status
#   4. Append one row to system_event_log.csv
# ==================================================

WORK_DIR="/home/elf/camera_yolo_work"
GUARD_SCRIPT="${WORK_DIR}/multi_sensor_guard.sh"

EVIDENCE_DIR="/home/elf/project_evidence/day15_guard_loop"
CSV_LOG="${EVIDENCE_DIR}/system_event_log.csv"
SUMMARY_LOG="${EVIDENCE_DIR}/loop_summary.txt"

ROUNDS=3
INTERVAL=2
PREPARE=3

usage() {
    echo "Usage:"
    echo "  ./multi_sensor_guard_loop.sh [--rounds N] [--interval SEC] [--prepare SEC]"
    echo
    echo "Example:"
    echo "  ./multi_sensor_guard_loop.sh --rounds 3 --interval 2 --prepare 3"
}

while [ $# -gt 0 ]; do
    case "$1" in
        --rounds)
            ROUNDS="$2"
            shift 2
            ;;
        --interval)
            INTERVAL="$2"
            shift 2
            ;;
        --prepare)
            PREPARE="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "[ERROR] Unknown argument: $1"
            usage
            exit 1
            ;;
    esac
done

extract_value() {
    local key="$1"
    local file="$2"
    grep "$key" "$file" | tail -n 1 | awk -F'= ' '{print $2}' | xargs
}

action_from_decision() {
    local decision="$1"

    case "$decision" in
        VISION_ALLOWED)
            echo "YOLO_DETECTION_DISPLAY"
            ;;
        LIGHT_DARK)
            echo "LIGHT_WARNING_DISPLAY"
            ;;
        MOTION_MOVING)
            echo "MOTION_MOVING_WARNING_DISPLAY"
            ;;
        MOTION_SHAKING)
            echo "MOTION_SHAKING_WARNING_DISPLAY"
            ;;
        *)
            echo "UNKNOWN_ACTION"
            ;;
    esac
}

mkdir -p "${EVIDENCE_DIR}"

if [ ! -f "${GUARD_SCRIPT}" ]; then
    echo "[ERROR] Guard script not found: ${GUARD_SCRIPT}"
    exit 1
fi

cd "${WORK_DIR}"

echo "=================================================="
echo "Day15 multi-sensor guard loop"
echo "=================================================="
echo "GUARD_SCRIPT = ${GUARD_SCRIPT}"
echo "EVIDENCE_DIR = ${EVIDENCE_DIR}"
echo "CSV_LOG      = ${CSV_LOG}"
echo "ROUNDS       = ${ROUNDS}"
echo "INTERVAL     = ${INTERVAL}s"
echo "PREPARE      = ${PREPARE}s"
echo

echo "timestamp,round,decision,light_status,lux,motion_status,gyro,accdelta,action,result,round_log" > "${CSV_LOG}"

# Refresh sudo credential before loop, because the guard script uses sudo.
sudo -v

for i in $(seq 1 "${ROUNDS}"); do
    ROUND_ID=$(printf "%03d" "${i}")
    ROUND_LOG="${EVIDENCE_DIR}/round_${ROUND_ID}.txt"

    echo
    echo "=================================================="
    echo "Round ${i}/${ROUNDS}"
    echo "=================================================="
    echo "Prepare your test condition now."
    echo "For example:"
    echo "  normal state / cover BH1750 / shake the breadboard"
    echo

    for s in $(seq "${PREPARE}" -1 1); do
        echo "Starting in ${s}s..."
        sleep 1
    done

    START_TS=$(date "+%Y-%m-%d %H:%M:%S")

    echo
    echo "[Round ${ROUND_ID}] Running guard script..."
    echo "[Round ${ROUND_ID}] Log file: ${ROUND_LOG}"

    set +e
    "${GUARD_SCRIPT}" 2>&1 | tee "${ROUND_LOG}"
    GUARD_RET=${PIPESTATUS[0]}
    set -e

    DECISION=$(extract_value "DECISION      =" "${ROUND_LOG}")
    LIGHT_STATUS=$(extract_value "LIGHT_STATUS  =" "${ROUND_LOG}")
    LUX=$(extract_value "LUX           =" "${ROUND_LOG}")
    MOTION_STATUS=$(extract_value "MOTION_STATUS =" "${ROUND_LOG}")
    GYRO=$(extract_value "GYRO          =" "${ROUND_LOG}")
    ACCDELTA=$(extract_value "ACCDELTA      =" "${ROUND_LOG}")

    if [ -z "${DECISION}" ]; then
        DECISION="PARSE_FAILED"
    fi

    if [ "${GUARD_RET}" -eq 0 ]; then
        RESULT="OK"
    else
        RESULT="ERROR_${GUARD_RET}"
    fi

    ACTION=$(action_from_decision "${DECISION}")

    echo "${START_TS},${i},${DECISION},${LIGHT_STATUS},${LUX},${MOTION_STATUS},${GYRO},${ACCDELTA},${ACTION},${RESULT},${ROUND_LOG}" >> "${CSV_LOG}"

    echo
    echo "[Round ${ROUND_ID}] Parsed result:"
    echo "DECISION      = ${DECISION}"
    echo "LIGHT_STATUS  = ${LIGHT_STATUS}"
    echo "LUX           = ${LUX}"
    echo "MOTION_STATUS = ${MOTION_STATUS}"
    echo "GYRO          = ${GYRO}"
    echo "ACCDELTA      = ${ACCDELTA}"
    echo "ACTION        = ${ACTION}"
    echo "RESULT        = ${RESULT}"

    if [ "${i}" -lt "${ROUNDS}" ]; then
        echo
        echo "Waiting ${INTERVAL}s before next round..."
        sleep "${INTERVAL}"
    fi
done

echo
echo "==================================================" | tee "${SUMMARY_LOG}"
echo "Day15 loop finished" | tee -a "${SUMMARY_LOG}"
echo "==================================================" | tee -a "${SUMMARY_LOG}"
echo "CSV log:" | tee -a "${SUMMARY_LOG}"
echo "${CSV_LOG}" | tee -a "${SUMMARY_LOG}"
echo | tee -a "${SUMMARY_LOG}"

echo "Decision count:" | tee -a "${SUMMARY_LOG}"
tail -n +2 "${CSV_LOG}" | cut -d',' -f3 | sort | uniq -c | tee -a "${SUMMARY_LOG}"

echo | tee -a "${SUMMARY_LOG}"
echo "Event log preview:" | tee -a "${SUMMARY_LOG}"
cat "${CSV_LOG}" | tee -a "${SUMMARY_LOG}"

echo
echo "Generated files:"
ls -lh "${EVIDENCE_DIR}"
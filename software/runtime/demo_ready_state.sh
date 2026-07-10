#!/bin/bash

echo "==== ELF2 DEMO READY STATE ===="

STATE_DIR="/home/elf/project_evidence/day32_productization/runtime_state"
LEGACY_STATE_DIR="/home/elf/project_evidence/day18_voice_event/state"

mkdir -p "$STATE_DIR"
mkdir -p "$LEGACY_STATE_DIR"

echo "RUNNING" > "$STATE_DIR/mode"
echo "1" > "$STATE_DIR/auto_capture_enabled"
echo "1" > "$STATE_DIR/alarm_enabled"
echo "0" > "$STATE_DIR/night_mode"

echo "RUNNING" > "$LEGACY_STATE_DIR/mode"
echo "1" > "$LEGACY_STATE_DIR/auto_capture_enabled"
echo "1" > "$LEGACY_STATE_DIR/alarm_enabled"
echo "0" > "$LEGACY_STATE_DIR/night_mode"

echo ""
echo "[DAY32 runtime_state]"
echo "mode=$(cat "$STATE_DIR/mode" 2>/dev/null)"
echo "auto_capture_enabled=$(cat "$STATE_DIR/auto_capture_enabled" 2>/dev/null)"
echo "alarm_enabled=$(cat "$STATE_DIR/alarm_enabled" 2>/dev/null)"
echo "night_mode=$(cat "$STATE_DIR/night_mode" 2>/dev/null)"

echo ""
echo "[legacy state]"
echo "mode=$(cat "$LEGACY_STATE_DIR/mode" 2>/dev/null)"
echo "auto_capture_enabled=$(cat "$LEGACY_STATE_DIR/auto_capture_enabled" 2>/dev/null)"
echo "alarm_enabled=$(cat "$LEGACY_STATE_DIR/alarm_enabled" 2>/dev/null)"
echo "night_mode=$(cat "$LEGACY_STATE_DIR/night_mode" 2>/dev/null)"

echo ""
echo "RESULT=OK"
echo "==== DEMO READY STATE DONE ===="
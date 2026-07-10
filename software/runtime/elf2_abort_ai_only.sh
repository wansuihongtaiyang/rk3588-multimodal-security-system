#!/usr/bin/env bash
set -u

LOG_DIR="/home/elf/project_evidence/day32_productization/unified_logs"
mkdir -p "$LOG_DIR"

LOG="$LOG_DIR/abort_ai_only_$(date +%Y%m%d_%H%M%S).txt"

echo "==================================================" | tee "$LOG"
echo "Abort previous AI only" | tee -a "$LOG"
echo "time=$(date '+%Y-%m-%d %H:%M:%S')" | tee -a "$LOG"
echo "==================================================" | tee -a "$LOG"

PATS=(
  "ai_event_analyze_once.py"
  "/home/elf/ai_deploy/qwen2_vl/demo"
  "/home/elf/ai_deploy/deepseek/llm_demo"
  "llm_demo"
  "elf2_analyze_event_after_fast_capture.sh"
  "elf2_ai_capture_once_with_context.sh"
)

echo "[before]" | tee -a "$LOG"
ps aux | grep -Ei "ai_event_analyze_once|qwen2_vl|deepseek|llm_demo|elf2_analyze_event_after_fast_capture|elf2_ai_capture_once_with_context" | grep -v grep | tee -a "$LOG" || true

for p in "${PATS[@]}"; do
  pkill -TERM -f "$p" 2>/dev/null || true
done

sleep 1

for p in "${PATS[@]}"; do
  pkill -KILL -f "$p" 2>/dev/null || true
done

echo "[after]" | tee -a "$LOG"
ps aux | grep -Ei "ai_event_analyze_once|qwen2_vl|deepseek|llm_demo|elf2_analyze_event_after_fast_capture|elf2_ai_capture_once_with_context" | grep -v grep | tee -a "$LOG" || true

echo "RESULT=OK" | tee -a "$LOG"

#!/usr/bin/env bash
set -u

TRIGGER_TYPE="${TRIGGER_TYPE:-priority_capture}"
SELECTED_EVENT="${SELECTED_EVENT:-}"
VOICE_TEXT="${VOICE_TEXT:-}"
VOICE_LOG="${VOICE_LOG:-}"

AI_TIMEOUT="${AI_TIMEOUT:-120}"
FACE_THRESHOLD="${FACE_THRESHOLD:-0.363}"
AI_PREEMPT_GUARD_SECONDS="${AI_PREEMPT_GUARD_SECONDS:-60}"

if [ -z "${PREEMPT_AI+x}" ]; then
  case "$TRIGGER_TYPE" in
    interval_capture)
      PREEMPT_AI=0
      ;;
    *)
      PREEMPT_AI=1
      ;;
  esac
fi

ALERT_SCRIPT="/home/elf/sensor_work/day24_network_alert/abnormal_event_check_and_alert_v3.py"
EXPORT_SCRIPT="/home/elf/sensor_work/day30_web/export_latest_ai_web.py"
ABORT_SCRIPT="/home/elf/sensor_work/day32_product_ops/elf2_abort_ai_only.sh"
ANALYZE_SCRIPT="/home/elf/sensor_work/day32_product_ops/elf2_analyze_event_after_fast_capture.sh"

STATE_DIR="/home/elf/project_evidence/day32_productization/runtime_state"
LOG_DIR="/home/elf/project_evidence/day32_productization/priority_capture_logs"
LOCK_FILE="/tmp/elf2_priority_fast_capture.lock"

mkdir -p "$STATE_DIR" "$LOG_DIR"

(
  flock 9

  STAMP=$(date +%Y%m%d_%H%M%S)
  CAP_LOG="$LOG_DIR/priority_capture_${TRIGGER_TYPE}_${STAMP}.txt"
  WEB_LOG="$LOG_DIR/priority_web_${TRIGGER_TYPE}_${STAMP}.txt"

  echo "==================================================" | tee "$CAP_LOG"
  echo "ELF2 Priority Fast Capture"
  echo "time           = $(date '+%Y-%m-%d %H:%M:%S')" | tee -a "$CAP_LOG"
  echo "TRIGGER_TYPE   = $TRIGGER_TYPE" | tee -a "$CAP_LOG"
  echo "SELECTED_EVENT = $SELECTED_EVENT" | tee -a "$CAP_LOG"
  echo "VOICE_TEXT     = $VOICE_TEXT" | tee -a "$CAP_LOG"
  echo "PREEMPT_AI     = $PREEMPT_AI" | tee -a "$CAP_LOG"
  echo "==================================================" | tee -a "$CAP_LOG"

  if [ "$PREEMPT_AI" = "1" ] && [ -f "$ABORT_SCRIPT" ]; then
    NOW_TS=$(date +%s)
    LAST_PREEMPT=$(cat "$STATE_DIR/last_ai_preempt_ts" 2>/dev/null || echo 0)
    DIFF_PREEMPT=$((NOW_TS - LAST_PREEMPT))

    if [ "$DIFF_PREEMPT" -lt "$AI_PREEMPT_GUARD_SECONDS" ]; then
      echo "[0] AI preempt guard active: ${DIFF_PREEMPT}s < ${AI_PREEMPT_GUARD_SECONDS}s. Do not abort current AI." | tee -a "$CAP_LOG"
      PREEMPT_AI=0
    else
      echo "$NOW_TS" > "$STATE_DIR/last_ai_preempt_ts"
      echo "[0] Abort previous AI analysis..." | tee -a "$CAP_LOG"
      bash "$ABORT_SCRIPT" 2>&1 | tee -a "$CAP_LOG"
    fi
  fi

  echo "[1] Fast capture and archive event..." | tee -a "$CAP_LOG"

  FORCE_ALERT=1 \
  NO_SEND=1 \
  IGNORE_MPU_OFFLINE=0 \
  FORCE_ALERT=1 NO_SEND=1 sudo -E python3 "$ALERT_SCRIPT" \
    --url http://127.0.0.1:9/alert \
    --no-send \
    2>&1 | tee -a "$CAP_LOG"

  EVENT=$(sed -n 's/^Event directory:[[:space:]]*//p' "$CAP_LOG" | tail -n 1)

  if [ -z "${EVENT:-}" ] || [ ! -d "$EVENT" ]; then
    EVENT=$(ls -td /home/elf/project_evidence/abnormal_events/* 2>/dev/null | head -n 1)
  fi

  if [ -z "${EVENT:-}" ] || [ ! -d "$EVENT" ]; then
    echo "ERROR: event dir not found" | tee -a "$CAP_LOG"
    exit 20
  fi

  sudo chown -R elf:elf "$EVENT" 2>/dev/null || true

  if [ -n "${VOICE_LOG:-}" ] && [ -f "$VOICE_LOG" ]; then
    cp "$VOICE_LOG" "$EVENT/voice_command_log.txt" 2>/dev/null || true
  fi

  python3 - "$EVENT" "$STATE_DIR" "$TRIGGER_TYPE" "$SELECTED_EVENT" "$VOICE_TEXT" "$VOICE_LOG" <<'__PY__'
import json, sys, time
from pathlib import Path

event_dir = Path(sys.argv[1])
state_dir = Path(sys.argv[2])
trigger_type = sys.argv[3]
selected_event = sys.argv[4]
voice_text = sys.argv[5]
voice_log = sys.argv[6]

def read_state(name, default=""):
    try:
        return (state_dir / name).read_text(encoding="utf-8").strip()
    except Exception:
        return default

try:
    event_json = json.loads((event_dir / "event.json").read_text(encoding="utf-8"))
except Exception:
    event_json = {}

event_type = event_json.get("decision") or event_json.get("event_type") or event_dir.name

voice = {
    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    "trigger_type": trigger_type,
    "selected_event": selected_event,
    "voice_text": voice_text,
    "voice_log": voice_log,
    "runtime_state_snapshot": {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "mode": read_state("mode", "UNKNOWN"),
        "auto_capture_enabled": read_state("auto_capture_enabled", "0"),
        "alarm_enabled": read_state("alarm_enabled", "1"),
        "night_mode": read_state("night_mode", "0"),
    }
}
(event_dir / "voice_command.json").write_text(json.dumps(voice, ensure_ascii=False, indent=2), encoding="utf-8")

pending_report = f"""===== 智能库房安防事件报告 =====
报告时间：{time.strftime('%Y-%m-%d %H:%M:%S')}

一、核心结论
风险等级：PENDING
告警动作：FAST_CAPTURE_UPLOADED
最终判断：AI_ANALYSIS_RUNNING
一句话结论：系统已完成高优先级快速抓拍，并已将最新现场图片更新到网页；Qwen2-VL、DeepSeek 和安全决策正在后台重新分析本次最新事件。

二、触发信息
触发来源：{trigger_type}
语音/事件：{selected_event}
识别文本：{voice_text}

三、当前状态
检测模式：{voice['runtime_state_snapshot']['mode']}
自动抓拍：{voice['runtime_state_snapshot']['auto_capture_enabled']}
告警开关：{voice['runtime_state_snapshot']['alarm_enabled']}
夜间模式：{voice['runtime_state_snapshot']['night_mode']}

四、说明
本报告为快速抓拍阶段的临时报告。后台 AI 分析完成后，网页会自动更新为最终安全决策报告。
"""

(event_dir / "final_display_report.txt").write_text(pending_report, encoding="utf-8")
(event_dir / "event_ai_report.txt").write_text("AI_ANALYSIS_RUNNING\n", encoding="utf-8")
(event_dir / "security_decision.txt").write_text("risk_level: PENDING\nalarm_action: FAST_CAPTURE_UPLOADED\nfinal_decision: AI_ANALYSIS_RUNNING\n", encoding="utf-8")

(event_dir / "event_ai_report.json").write_text(json.dumps({
    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    "event_type": event_type,
    "report_source": "fast_capture_pending",
    "image_summary": "AI_ANALYSIS_RUNNING",
    "final_report": pending_report,
}, ensure_ascii=False, indent=2), encoding="utf-8")

(event_dir / "security_decision.json").write_text(json.dumps({
    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    "event_dir": str(event_dir),
    "event_type": event_type,
    "risk_level": "PENDING",
    "alarm_action": "FAST_CAPTURE_UPLOADED",
    "final_decision": "AI_ANALYSIS_RUNNING",
    "score": 0,
    "reasons": ["高优先级快速抓拍已完成，AI 正在后台重新分析最新事件"],
    "recommended_actions": ["请先查看网页最新现场图片，等待最终 AI 安全决策报告自动刷新"],
    "evidence": {
        "trigger_type": trigger_type,
        "selected_event": selected_event,
    }
}, ensure_ascii=False, indent=2), encoding="utf-8")

(event_dir / "final_display_report.json").write_text(json.dumps({
    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    "event_dir": str(event_dir),
    "risk_level": "PENDING",
    "alarm_action": "FAST_CAPTURE_UPLOADED",
    "final_decision": "AI_ANALYSIS_RUNNING",
    "display_report": pending_report,
}, ensure_ascii=False, indent=2), encoding="utf-8")
__PY__

  echo "[2] Export HTML immediately with latest image..." | tee -a "$CAP_LOG"
  python3 "$EXPORT_SCRIPT" 2>&1 | tee "$WEB_LOG" | tee -a "$CAP_LOG"

  echo "[3] Register latest event and start latest-only AI worker..." | tee -a "$CAP_LOG"

  echo "$EVENT" > "$STATE_DIR/latest_ai_event"

  WORKER_SCRIPT="/home/elf/sensor_work/day32_product_ops/elf2_latest_ai_worker.sh"

  nohup env \
    AI_TIMEOUT="$AI_TIMEOUT" \
    FACE_THRESHOLD="$FACE_THRESHOLD" \
    bash "$WORKER_SCRIPT" \
    > "$LOG_DIR/latest_ai_worker_launcher_${TRIGGER_TYPE}_${STAMP}.log" 2>&1 &

  echo "EVENT_DIR=$EVENT" | tee -a "$CAP_LOG"
  echo "HTML_URL=http://192.168.137.12:8090/" | tee -a "$CAP_LOG"
  echo "RESULT=FAST_WEB_UPDATED_AI_RUNNING" | tee -a "$CAP_LOG"

) 9>"$LOCK_FILE"

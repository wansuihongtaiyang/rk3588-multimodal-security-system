#!/usr/bin/env bash
set -u

ACTION="${1:-status}"

STATE_DIR="/home/elf/project_evidence/day32_productization/runtime_state"
ABORT_SCRIPT="/home/elf/sensor_work/day32_product_ops/elf2_abort_ai_only.sh"

mkdir -p "$STATE_DIR"

write_state() {
  echo "$2" > "$STATE_DIR/$1"
}

read_state() {
  cat "$STATE_DIR/$1" 2>/dev/null || echo "$2"
}

case "$ACTION" in
  start|start_detection|VOICE_START)
    write_state mode RUNNING
    write_state auto_capture_enabled 1
    write_state alarm_enabled 1

    # 让传感器异常可以立刻重新触发，不受旧冷却时间影响
    write_state last_sensor_trigger_ts 0
    write_state sensor_abnormal_count 0

    echo "STATE_ACTION=START_DETECTION"
    echo "mode=RUNNING"
    echo "auto_capture_enabled=1"
    echo "alarm_enabled=1"
    echo "sensor_trigger=enabled"
    echo "voice_loop=command_listening"
    ;;

  stop|stop_detection|VOICE_STOP)
    write_state mode STOPPED
    write_state auto_capture_enabled 0
    write_state alarm_enabled 0

    # 清理传感器连续异常计数和待分析队列
    write_state sensor_abnormal_count 0
    write_state last_sensor_trigger_ts 0
    rm -f "$STATE_DIR/latest_ai_event" 2>/dev/null || true

    # 默认不杀当前 AI，让已开始的报告尽量完成。
    # 如需停止检测时也杀 AI，可用 STOP_KILLS_AI=1 bash elf2_runtime_control.sh stop
    if [ "${STOP_KILLS_AI:-0}" = "1" ] && [ -f "$ABORT_SCRIPT" ]; then
      bash "$ABORT_SCRIPT" || true
    fi

    echo "STATE_ACTION=STOP_DETECTION"
    echo "mode=STOPPED"
    echo "auto_capture_enabled=0"
    echo "alarm_enabled=0"
    echo "sensor_trigger=disabled"
    echo "voice_loop=command_listening"
    ;;

  alarm_on|VOICE_ALARM_ON)
    write_state alarm_enabled 1
    write_state last_sensor_trigger_ts 0
    echo "STATE_ACTION=ALARM_ON"
    echo "alarm_enabled=1"
    ;;

  alarm_off|VOICE_ALARM_OFF)
    write_state alarm_enabled 0
    echo "STATE_ACTION=ALARM_OFF"
    echo "alarm_enabled=0"
    ;;

  night_on|night|VOICE_NIGHT)
    write_state night_mode 1
    echo "STATE_ACTION=NIGHT_MODE_ON"
    echo "night_mode=1"
    ;;

  night_off)
    write_state night_mode 0
    echo "STATE_ACTION=NIGHT_MODE_OFF"
    echo "night_mode=0"
    ;;

  status|*)
    echo "STATE_ACTION=STATUS"
    echo "mode=$(read_state mode READY)"
    echo "auto_capture_enabled=$(read_state auto_capture_enabled 0)"
    echo "alarm_enabled=$(read_state alarm_enabled 1)"
    echo "night_mode=$(read_state night_mode 0)"
    echo "sensor_abnormal_count=$(read_state sensor_abnormal_count 0)"
    echo "last_sensor_trigger_ts=$(read_state last_sensor_trigger_ts 0)"
    ;;
esac

echo "RESULT=OK"

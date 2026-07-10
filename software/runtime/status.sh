#!/bin/bash

echo "==== ELF2 STATUS ===="

echo ""
echo "[PORTS]"
ss -lntp | grep -E "8080|8090|9090" || echo "No 8080/8090/9090 listening."

echo ""
echo "[PROCESSES]"
ps -ef | grep -E "abnormal_event_dashboard|http.server 8090|day41_mobile_gateway" | grep -v grep || echo "No web process found."

echo ""
echo "[CORE RUNTIME]"
ps -ef | grep -E "elf2_unified_runtime|elf2_voice_command_loop|elf2_interval_capture_loop|elf2_sensor_watch_loop" | grep -v grep || echo "Core runtime loops not detected."

echo ""
echo "[CORE RUNTIME QUICK JUDGE]"

if ps -ef | grep -F "elf2_unified_runtime.sh" | grep -v grep >/dev/null; then
  echo "UNIFIED_RUNTIME=RUNNING"
else
  echo "UNIFIED_RUNTIME=NOT_RUNNING"
fi

if ps -ef | grep -F "elf2_voice_command_loop_10s.sh" | grep -v grep >/dev/null; then
  echo "VOICE_LOOP=RUNNING"
else
  echo "VOICE_LOOP=NOT_RUNNING"
fi

if ps -ef | grep -F "elf2_interval_capture_loop.sh" | grep -v grep >/dev/null; then
  echo "INTERVAL_CAPTURE_LOOP=RUNNING"
else
  echo "INTERVAL_CAPTURE_LOOP=NOT_RUNNING"
fi

if ps -ef | grep -F "elf2_sensor_watch_loop.sh" | grep -v grep >/dev/null; then
  echo "SENSOR_WATCH_LOOP=RUNNING"
else
  echo "SENSOR_WATCH_LOOP=NOT_RUNNING"
fi

echo ""
echo "[TAILSCALE]"
tailscale status | head -10

echo ""
echo "[TAILSCALE SERVE]"
sudo tailscale serve status

echo ""
echo "[I2C]"
/usr/sbin/i2cdetect -y 4

echo ""
echo "[DAY41 API]"
curl -s "http://127.0.0.1:9090/api/summary?token=elf2day41" | head -n 20

echo ""
echo "[MOBILE EVENTS]"
ls -td ~/project_evidence/mobile_events/* 2>/dev/null | head -5 || echo "No mobile_events yet."

echo ""
echo "[ABNORMAL EVENTS]"
ls -td ~/project_evidence/abnormal_events/* 2>/dev/null | head -5 || echo "No abnormal_events."

echo ""
echo "[ACCESS URLS]"
echo "8080 events:"
echo "http://elf2-rk3588.tail5a0843.ts.net:8080/?token=elf2day26"
echo ""
echo "8090 AI report:"
echo "http://elf2-rk3588.tail5a0843.ts.net:8090/"
echo ""
echo "9090 mobile:"
echo "http://elf2-rk3588.tail5a0843.ts.net:9090/mobile?token=elf2day41"
echo ""
echo "SSH / WinSCP:"
echo "ssh -p 2222 elf@elf2-rk3588.tail5a0843.ts.net"
echo "WinSCP host: elf2-rk3588.tail5a0843.ts.net"
echo "WinSCP port: 2222"
echo "WinSCP protocol: SFTP"
echo "WinSCP user: elf"
echo ""
echo "==== STATUS DONE ===="
#!/bin/bash

echo "==== ELF2 START ALL ===="

mkdir -p ~/elf2_system/logs
mkdir -p ~/elf2_system/state
mkdir -p ~/project_evidence/mobile_events
mkdir -p ~/project_evidence/day41_mobile

echo "[0] refresh sudo credential"
sudo -v

echo "[1] stop old web services"
pkill -f abnormal_event_dashboard 2>/dev/null
pkill -f "http.server 8090" 2>/dev/null
pkill -f day41_mobile_gateway 2>/dev/null

sleep 1

echo "[2] fix I2C permission"
sudo chmod 666 /dev/i2c-4 2>/dev/null || true

echo "[2b] clean stale capture locks"
sudo rm -f /tmp/elf2_priority_fast_capture.lock 2>/dev/null || true
sudo rm -f /tmp/elf2_mobile_capture.lock 2>/dev/null || true
sudo rm -f /tmp/elf2_capture.lock 2>/dev/null || true

echo "[3] start sudo keepalive"
pkill -f "sudo -n true; sleep 60" 2>/dev/null
nohup bash -lc 'while true; do sudo -n true; sleep 60; done' \
  > ~/elf2_system/logs/sudo_keepalive.log 2>&1 &

echo "[4] start 8080 abnormal events dashboard"
nohup python3 ~/sensor_work/day26_dashboard/abnormal_event_dashboard.py \
  --host 127.0.0.1 \
  --port 8080 \
  --root ~/project_evidence/abnormal_events \
  --token elf2day26 \
  > ~/elf2_system/logs/8080.log 2>&1 &

echo "[5] start 8090 AI web"
cd ~/project_evidence/day30_ai_web || exit 1
nohup python3 -m http.server 8090 --bind 127.0.0.1 \
  > ~/elf2_system/logs/8090.log 2>&1 &

echo "[6] start 9090 mobile gateway"
nohup python3 ~/sensor_work/day41_mobile/day41_mobile_gateway.py \
  --host 127.0.0.1 \
  --port 9090 \
  --token elf2day41 \
  > ~/elf2_system/logs/9090.log 2>&1 &

sleep 2

echo "[7] configure tailscale serve"
sudo tailscale serve reset
sudo tailscale serve --bg --http=8080 http://127.0.0.1:8080
sudo tailscale serve --bg --http=8090 http://127.0.0.1:8090
sudo tailscale serve --bg --http=9090 http://127.0.0.1:9090
sudo tailscale serve --bg --tcp=2222 tcp://127.0.0.1:22

echo ""
echo "==== LOCAL CHECK ===="
ss -lntp | grep -E "8080|8090|9090" || true

echo ""
echo "==== TAILSCALE SERVE ===="
sudo tailscale serve status

echo ""
echo "==== ACCESS URLS ===="
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
echo "WinSCP: host=elf2-rk3588.tail5a0843.ts.net port=2222 protocol=SFTP user=elf"
echo ""
echo "==== START DONE ===="
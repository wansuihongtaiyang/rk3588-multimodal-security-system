#!/bin/bash

echo "==== ELF2 STOP ALL ===="

echo "[1] stop web services"
pkill -f abnormal_event_dashboard 2>/dev/null
pkill -f "http.server 8090" 2>/dev/null
pkill -f day41_mobile_gateway 2>/dev/null

echo "[2] stop sudo keepalive"
pkill -f "sudo -n true; sleep 60" 2>/dev/null

echo "[3] reset tailscale serve"
sudo tailscale serve reset

echo "[4] check remaining ports"
ss -lntp | grep -E "8080|8090|9090" || echo "No 8080/8090/9090 service remains."

echo "==== STOP DONE ===="
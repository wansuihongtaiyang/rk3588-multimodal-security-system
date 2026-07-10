#!/usr/bin/env bash
set -u

PACK_ROOT="/home/elf/project_evidence/day32_productization"
OUT_DIR="$PACK_ROOT/package"
mkdir -p "$OUT_DIR"

STAMP=$(date +%Y%m%d_%H%M%S)
TMP_DIR="$OUT_DIR/elf2_product_package_$STAMP"
TAR_PATH="$OUT_DIR/elf2_product_package_$STAMP.tar.gz"

mkdir -p "$TMP_DIR"

echo "=================================================="
echo "ELF2 Pack Evidence"
echo "TMP_DIR  = $TMP_DIR"
echo "TAR_PATH = $TAR_PATH"
echo "=================================================="

mkdir -p "$TMP_DIR/scripts"
mkdir -p "$TMP_DIR/web"
mkdir -p "$TMP_DIR/events"

cp -a /home/elf/sensor_work/day29_ai "$TMP_DIR/scripts/" 2>/dev/null || true
cp -a /home/elf/sensor_work/day30_web "$TMP_DIR/scripts/" 2>/dev/null || true
cp -a /home/elf/sensor_work/day31_policy "$TMP_DIR/scripts/" 2>/dev/null || true
cp -a /home/elf/sensor_work/day32_product_ops "$TMP_DIR/scripts/" 2>/dev/null || true

cp -a /home/elf/project_evidence/day30_ai_web "$TMP_DIR/web/" 2>/dev/null || true
cp -a /home/elf/project_evidence/day32_productization/status "$TMP_DIR/" 2>/dev/null || true
cp -a /home/elf/project_evidence/day32_productization/run_logs "$TMP_DIR/" 2>/dev/null || true

echo "Copy latest abnormal events..."
ls -td /home/elf/project_evidence/abnormal_events/* 2>/dev/null | head -n 10 | while read -r ev; do
  cp -a "$ev" "$TMP_DIR/events/" 2>/dev/null || true
done

cat > "$TMP_DIR/README_PACKAGE.txt" <<TXT
ELF2 product evidence package
created_at: $(date '+%Y-%m-%d %H:%M:%S')

Main commands:
bash ~/elf2_start.sh
bash ~/elf2_status.sh
bash ~/elf2_stop.sh

Dashboard:
http://192.168.137.12:8090/

Package contents:
scripts/   core scripts
web/       exported HTML dashboard
events/    latest abnormal events and AI reports
status/    system status logs
run_logs/  runtime logs
TXT

tar -czf "$TAR_PATH" -C "$OUT_DIR" "elf2_product_package_$STAMP"

echo "TAR_PATH=$TAR_PATH"
ls -lh "$TAR_PATH"
echo "RESULT=OK"

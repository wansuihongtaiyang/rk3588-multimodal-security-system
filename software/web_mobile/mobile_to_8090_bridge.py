#!/usr/bin/env python3
import os, time, shutil, html
from pathlib import Path

HOME = Path.home()
MOBILE_ROOT = HOME / "project_evidence/mobile_events"
WEB_ROOT = HOME / "project_evidence/day30_ai_web"
ASSET_DIR = WEB_ROOT / "mobile_latest"
STAMP_FILE = WEB_ROOT / ".mobile_latest_path"

def latest_mobile_event():
    if not MOBILE_ROOT.exists():
        return None
    dirs = [p for p in MOBILE_ROOT.iterdir() if p.is_dir()]
    if not dirs:
        return None
    return max(dirs, key=lambda p: p.stat().st_mtime)

def read_text(p, limit=9000):
    try:
        return p.read_text(errors="ignore")[:limit]
    except Exception:
        return ""

def copy_if_exists(src, dst):
    if src.exists():
        shutil.copy2(src, dst)

def sync_event(e):
    WEB_ROOT.mkdir(parents=True, exist_ok=True)
    ASSET_DIR.mkdir(parents=True, exist_ok=True)

    for name in [
        "camera_input.jpg",
        "camera_yolo_result_filtered.jpg",
        "final_display_report.txt",
        "sensor_status.txt",
        "event.json",
        "mobile_capture_meta.json",
        "face_status.txt",
        "face_auth_result.json",
        "security_decision.txt",
        "event_ai_report.txt",
    ]:
        copy_if_exists(e / name, ASSET_DIR / name)

    report = read_text(e / "final_display_report.txt") or read_text(e / "event_ai_report.txt")
    sensor = read_text(e / "sensor_status.txt")
    face_status = read_text(e / "face_status.txt")
    face_json = read_text(e / "face_auth_result.json")
    security = read_text(e / "security_decision.txt")
    event_json = read_text(e / "event.json")
    meta = read_text(e / "mobile_capture_meta.json")
    files = "\n".join(sorted([p.name for p in e.iterdir() if p.is_file()]))
    ts = int(time.time())

    page = f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta http-equiv="refresh" content="3">
<title>ELF2 Latest Mobile Capture</title>
<style>
body {{ font-family: Arial, "Microsoft YaHei", sans-serif; margin: 24px; background: #f5f5f5; }}
.card {{ background: white; padding: 18px; margin: 14px 0; border-radius: 12px; box-shadow: 0 1px 8px #ddd; }}
img {{ max-width: 48%; margin-right: 1%; border: 1px solid #ccc; vertical-align: top; }}
pre {{ white-space: pre-wrap; background: #111; color: #eee; padding: 12px; border-radius: 8px; max-height: 380px; overflow: auto; }}
h1, h2 {{ margin-bottom: 10px; }}
</style>
</head>
<body>
<h1>ELF2 Latest Mobile Capture</h1>
<div class="card">
<b>Event directory:</b> {html.escape(str(e))}<br>
<b>Updated:</b> {html.escape(time.strftime("%Y-%m-%d %H:%M:%S"))}
</div>

<div class="card">
<h2>Camera / YOLO Result</h2>
<img src="mobile_latest/camera_input.jpg?ts={ts}" alt="camera_input">
<img src="mobile_latest/camera_yolo_result_filtered.jpg?ts={ts}" alt="yolo_result">
</div>

<div class="card"><h2>Final Display Report</h2><pre>{html.escape(report)}</pre></div>
<div class="card"><h2>Sensor Status</h2><pre>{html.escape(sensor)}</pre></div>
<div class="card"><h2>FaceAuth Result</h2><pre>{html.escape(face_status + "\\n\\n" + face_json)}</pre></div>
<div class="card"><h2>Security Decision</h2><pre>{html.escape(security)}</pre></div>
<div class="card"><h2>Event / Meta</h2><pre>{html.escape(event_json + "\\n\\n" + meta)}</pre></div>
<div class="card"><h2>Files</h2><pre>{html.escape(files)}</pre></div>
</body>
</html>
"""
    (WEB_ROOT / "index.html").write_text(page, encoding="utf-8")
    STAMP_FILE.write_text(str(e), encoding="utf-8")
    print("SYNC_OK", e, flush=True)

last = ""
print("mobile_to_8090_bridge started", flush=True)
while True:
    e = latest_mobile_event()
    if e and str(e) != last:
        sync_event(e)
        last = str(e)
    time.sleep(2)

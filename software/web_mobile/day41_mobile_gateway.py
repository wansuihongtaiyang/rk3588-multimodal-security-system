#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import html
import json
import mimetypes
import os
import subprocess
import time
import urllib.parse
import shutil
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOME = Path("/home/elf")
EVIDENCE_ROOT = Path("/home/elf/project_evidence")
ABNORMAL_ROOT = EVIDENCE_ROOT / "abnormal_events"
AI_WEB_ROOT = EVIDENCE_ROOT / "day30_ai_web"
DAY41_ROOT = EVIDENCE_ROOT / "day41_mobile"

MOBILE_ROOT = EVIDENCE_ROOT / "mobile_events"
CURRENT_IMAGE_ROOT = Path("/home/elf/camera_yolo_work")

STATE_DIR_CANDIDATES = [
    Path("/home/elf/project_evidence/day32_productization/runtime_state"),
    Path("/home/elf/project_runtime/state"),
    Path("/home/elf/project_state"),
    Path("/home/elf/project_evidence/day18_voice_event/state"),
    Path("/home/elf/.elf2_state"),
]

ALLOWED_FILE_ROOTS = [
    EVIDENCE_ROOT,
    Path("/home/elf/camera_yolo_work"),
]

CONTROL_SCRIPT = Path("/home/elf/sensor_work/day32_product_ops/elf2_runtime_control.sh")
CAPTURE_SCRIPT_CANDIDATES = [
    Path("/home/elf/sensor_work/day32_product_ops/elf2_priority_capture_fast_web.sh"),
    Path("/home/elf/sensor_work/day32_product_ops/elf2_ai_capture_once_with_context.sh"),
    Path("/home/elf/sensor_work/day29_ai/ai_event_trigger_once.sh"),
]


def now_str():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def safe_read_text(path: Path, max_chars=6000):
    try:
        if path.exists() and path.is_file():
            return path.read_text(encoding="utf-8", errors="ignore")[:max_chars]
    except Exception:
        pass
    return ""


def safe_load_json(path: Path):
    try:
        if path.exists() and path.is_file():
            return json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        pass
    return {}


def find_state_file(names):
    for d in STATE_DIR_CANDIDATES:
        for n in names:
            p = d / n
            if p.exists():
                return p
    return None


def read_state_value(names, default="UNKNOWN"):
    p = find_state_file(names)
    if not p:
        return default
    txt = safe_read_text(p, 200).strip()
    return txt if txt else default


def find_existing_state_dir():
    for d in STATE_DIR_CANDIDATES:
        if d.exists():
            return d
    return None


def write_state_value(names, value):
    ok = False
    for d in STATE_DIR_CANDIDATES:
        if not d.exists():
            continue

        targets = []
        for n in names:
            p = d / n
            if p.exists():
                targets.append(p)

        if not targets:
            targets.append(d / names[0])

        for p in targets:
            try:
                p.write_text(str(value) + "\n", encoding="utf-8")
                ok = True
            except Exception:
                pass

    return ok


def read_current_sensor_health():
    """
    Read current I2C / sensor health.
    This version supports both:
    1) plain output: NORMAL 80.50
    2) verbose BH1750 output:
       avg_lux: 87.33
       status: NORMAL
    """
    i2c_text = safe_cmd("/usr/sbin/i2cdetect -y 4", timeout=5)

    has_bh1750 = "23" in i2c_text
    has_mpu6050 = "68" in i2c_text

    bh_status = "OFFLINE"
    bh_lux = ""
    bh_raw = ""

    mpu_status = "OFFLINE"
    mpu_gyro = ""
    mpu_accdelta = ""
    mpu_raw = ""

    if has_bh1750:
        bh_raw = safe_cmd(
            "python3 /home/elf/sensor_work/bh1750_day10/bh1750_check_status.py",
            timeout=8
        ).strip()

        # Case 1: plain format, e.g. "NORMAL 80.50"
        parts = bh_raw.split()
        if len(parts) >= 1 and parts[0] in ["DARK", "NORMAL", "BRIGHT"]:
            bh_status = parts[0]
            if len(parts) >= 2:
                bh_lux = parts[1]
        else:
            # Case 2: verbose format
            for line in bh_raw.splitlines():
                line = line.strip()
                if line.startswith("status:"):
                    bh_status = line.split(":", 1)[1].strip()
                elif line.startswith("avg_lux:"):
                    bh_lux = line.split(":", 1)[1].strip()

    if has_mpu6050:
        mpu_raw = safe_cmd(
            "python3 /home/elf/sensor_work/mpu6050_day11/mpu6050_check_motion.py --plain",
            timeout=8
        ).strip()

        # Expected example: STABLE 3.0 0.091
        parts = mpu_raw.split()
        if len(parts) >= 1:
            mpu_status = parts[0]
        if len(parts) >= 2:
            mpu_gyro = parts[1]
        if len(parts) >= 3:
            mpu_accdelta = parts[2]

    if has_bh1750 and has_mpu6050:
        i2c_state = "OK"
    elif has_bh1750 or has_mpu6050:
        i2c_state = "PARTIAL"
    else:
        i2c_state = "OFFLINE"

    return {
        "i2c4": i2c_state,
        "bh1750_online": has_bh1750,
        "bh1750_status": bh_status,
        "bh1750_lux": bh_lux,
        "bh1750_raw": bh_raw,
        "mpu6050_online": has_mpu6050,
        "mpu6050_status": mpu_status,
        "mpu6050_gyro": mpu_gyro,
        "mpu6050_accdelta": mpu_accdelta,
        "mpu6050_raw": mpu_raw,
        "raw_i2c": i2c_text,
    }

def read_system_status():
    mode = read_state_value(["mode", "mode.txt"], "UNKNOWN")
    auto_capture = read_state_value(["auto_capture_enabled", "auto_capture_enabled.txt"], "UNKNOWN")
    alarm = read_state_value(["alarm_enabled", "alarm_enabled.txt"], "UNKNOWN")
    night = read_state_value(["night_mode", "night_mode.txt"], "UNKNOWN")

    return {
        "time": now_str(),
        "mode": mode,
        "auto_capture_enabled": auto_capture,
        "alarm_enabled": alarm,
        "night_mode": night,
        "tailscale_ip_hint": safe_cmd("tailscale ip -4", timeout=3).strip(),
    }


def list_named_dirs(root: Path):
    if not root.exists():
        return []
    items = []
    for p in root.iterdir():
        if p.is_dir():
            items.append(p)
    items.sort(key=lambda x: x.name, reverse=True)
    return items


def list_event_dirs():
    return list_named_dirs(ABNORMAL_ROOT)


def list_mobile_dirs():
    return list_named_dirs(MOBILE_ROOT)


def infer_event_type_from_name(name):
    parts = name.split("_")
    if len(parts) >= 3:
        return "_".join(parts[2:])
    return name


def file_url(path: Path):
    return "/file?path=" + urllib.parse.quote(str(path))

def current_board_ip():
    out = safe_cmd("hostname -I", timeout=3).strip().split()
    for ip in out:
        if ip and not ip.startswith("127."):
            return ip
    return ""


def copy_if_exists(src: Path, dst: Path):
    try:
        if src.exists() and src.is_file():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            return True
    except Exception:
        pass
    return False


def append_day41_log(log_name, text):
    DAY41_ROOT.mkdir(parents=True, exist_ok=True)
    log = DAY41_ROOT / log_name
    with open(log, "a", encoding="utf-8") as f:
        f.write(text)


def create_mobile_capture_record(capture_log=""):
    """
    Create a mobile capture record when capture result is NO_ALERT.
    This allows the mobile UI to show the latest user-triggered capture
    even if no abnormal event directory is created.
    """
    MOBILE_ROOT.mkdir(parents=True, exist_ok=True)

    event_name = time.strftime("%Y%m%d_%H%M%S") + "_MOBILE_CAPTURE"
    d = MOBILE_ROOT / event_name
    d.mkdir(parents=True, exist_ok=True)

    sensor = read_current_sensor_health()
    system = read_system_status()

    copied_files = []

    for name in [
        "camera_input.jpg",
        "camera_yolo_result_filtered.jpg",
        
    ]:
        src = CURRENT_IMAGE_ROOT / name
        dst = d / name
        if copy_if_exists(src, dst):
            copied_files.append(name)

    final_report_text = (
        "===== 手机主动抓拍记录 =====\n"
        f"报告时间：{now_str()}\n"
        f"事件类型：MOBILE_CAPTURE\n"
        f"触发来源：mobile_web\n\n"
        "一、核心结论\n"
        "本次记录由手机端主动触发，系统已完成一次现场图像抓拍与目标检测结果保存。\n"
        "该记录不代表系统检测到异常，仅作为远程查看现场状态的主动取证记录。\n\n"
        "二、当前系统状态\n"
        f"mode={system.get('mode')}\n"
        f"auto_capture_enabled={system.get('auto_capture_enabled')}\n"
        f"alarm_enabled={system.get('alarm_enabled')}\n"
        f"night_mode={system.get('night_mode')}\n\n"
        "三、当前传感器状态\n"
        f"I2C4={sensor.get('i2c4')}\n"
        f"BH1750={sensor.get('bh1750_status')} lux={sensor.get('bh1750_lux')}\n"
        f"MPU6050={sensor.get('mpu6050_status')} gyro={sensor.get('mpu6050_gyro')} accdelta={sensor.get('mpu6050_accdelta')}\n\n"
        "四、证据文件\n"
        "- camera_input.jpg\n"
        "- camera_yolo_result_filtered.jpg\n"
        "- event.json\n"
        "- sensor_status.txt\n"
    )

    (d / "final_display_report.txt").write_text(
        final_report_text,
        encoding="utf-8"
    )

    sensor_status_text = (
        f"decision=MOBILE_CAPTURE\n"
        f"problems=none\n\n"
        f"I2C4:\n{sensor.get('i2c4', 'UNKNOWN')}\n\n"
        f"BH1750:\n"
        f"online={sensor.get('bh1750_online')}\n"
        f"status={sensor.get('bh1750_status', '')}\n"
        f"lux={sensor.get('bh1750_lux', '')}\n\n"
        f"MPU6050:\n"
        f"online={sensor.get('mpu6050_online')}\n"
        f"status={sensor.get('mpu6050_status', '')}\n"
        f"gyro={sensor.get('mpu6050_gyro', '')}\n"
        f"accdelta={sensor.get('mpu6050_accdelta', '')}\n"
    )
    (d / "sensor_status.txt").write_text(sensor_status_text, encoding="utf-8")

    event_json = {
        "timestamp": now_str(),
        "event_type": "MOBILE_CAPTURE",
        "decision": "MOBILE_CAPTURE",
        "board_ip": current_board_ip(),
        "trigger_source": "mobile_web",
        "problems": [],
        "risk_level": "LOW",
        "alarm_action": "RECORD_ONLY",
        "face_status": "UNKNOWN",
        "system_state": system,
        "sensor_health": sensor,
        "copied_files": copied_files,
    }
    (d / "event.json").write_text(
        json.dumps(event_json, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    meta_json = {
        "created_at": now_str(),
        "note": "Created by Day41 mobile capture flow",
        "capture_log_tail": capture_log[-15000:],
    }
    (d / "mobile_capture_meta.json").write_text(
        json.dumps(meta_json, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    return d


def latest_mobile_summary():
    events = list_mobile_dirs()
    if not events:
        return None

    d = events[0]
    event_json = safe_load_json(d / "event.json")
    final_txt = safe_read_text(d / "final_display_report.txt")
    sensor_txt = safe_read_text(d / "sensor_status.txt", 5000)

    imgs = {}
    for key, name in [
        ("camera_input", "camera_input.jpg"),
        ("yolo_result", "camera_yolo_result_filtered.jpg"),
        ("warning", "multi_sensor_warning.jpg"),
    ]:
        p = d / name
        if p.exists():
            imgs[key] = file_url(p)

    return {
        "exists": True,
        "event_name": d.name,
        "event_dir": str(d),
        "event_type": event_json.get("event_type", "MOBILE_CAPTURE"),
        "timestamp": event_json.get("timestamp", ""),
        "board_ip": event_json.get("board_ip", ""),
        "decision": event_json.get("decision", "MOBILE_CAPTURE"),
        "problems": event_json.get("problems", []),
        "risk_level": event_json.get("risk_level", "LOW"),
        "alarm_action": event_json.get("alarm_action", "RECORD_ONLY"),
        "face_status": event_json.get("face_status", "UNKNOWN"),
        "final_report_text": final_txt or "手机主动抓拍记录已生成",
        "sensor_status_text": sensor_txt,
        "images": imgs,
        "event_json": event_json,
    }


def combined_latest_summary():
    abnormal = latest_event_summary()
    mobile = latest_mobile_summary()

    if mobile and mobile.get("exists"):
        if not abnormal.get("exists"):
            return mobile
        return mobile if mobile["event_name"] > abnormal["event_name"] else abnormal

    return abnormal


def combined_recent_events(limit=12):
    items = []

    for d in list_event_dirs():
        event_json = safe_load_json(d / "event.json")
        items.append({
            "sort_key": d.name,
            "source": "abnormal",
            "event_name": d.name,
            "event_type": event_json.get("event_type") or event_json.get("decision") or infer_event_type_from_name(d.name),
            "timestamp": event_json.get("timestamp", ""),
            "decision": event_json.get("decision", ""),
            "problems": event_json.get("problems", []),
        })

    for d in list_mobile_dirs():
        event_json = safe_load_json(d / "event.json")
        items.append({
            "sort_key": d.name,
            "source": "mobile",
            "event_name": d.name,
            "event_type": event_json.get("event_type", "MOBILE_CAPTURE"),
            "timestamp": event_json.get("timestamp", ""),
            "decision": event_json.get("decision", "MOBILE_CAPTURE"),
            "problems": event_json.get("problems", []),
        })

    items.sort(key=lambda x: x["sort_key"], reverse=True)

    out = []
    for x in items[:limit]:
        x.pop("sort_key", None)
        out.append(x)

    return out

def latest_event_summary():
    events = list_event_dirs()
    if not events:
        return {
            "exists": False,
            "event_name": "",
            "event_type": "NO_EVENT",
            "risk_level": "UNKNOWN",
            "alarm_action": "UNKNOWN",
            "summary": "暂无异常事件记录",
        }

    d = events[0]
    event_json = safe_load_json(d / "event.json")
    final_json = safe_load_json(d / "final_display_report.json")
    security_json = safe_load_json(d / "security_decision.json")
    face_json = safe_load_json(d / "face_auth_result.json")
    ai_json = safe_load_json(d / "event_ai_report.json")

    final_txt = safe_read_text(d / "final_display_report.txt")
    if not final_txt:
        final_txt = safe_read_text(AI_WEB_ROOT / "final_display_report.txt")
    if not final_txt:
        final_txt = safe_read_text(d / "event_ai_report.txt")

    sensor_txt = safe_read_text(d / "sensor_status.txt", 3000)

    event_type = (
        event_json.get("event_type")
        or event_json.get("decision")
        or infer_event_type_from_name(d.name)
    )

    risk = (
        final_json.get("risk_level")
        or final_json.get("risk")
        or security_json.get("risk_level")
        or security_json.get("risk")
        or event_json.get("risk_level")
        or "UNKNOWN"
    )

    alarm_action = (
        final_json.get("alarm_action")
        or security_json.get("alarm_action")
        or event_json.get("alarm_action")
        or "UNKNOWN"
    )

    face_status = (
        face_json.get("face_status")
        or face_json.get("status")
        or face_json.get("result")
        or "UNKNOWN"
    )

    imgs = {}
    for key, name in [
        ("camera_input", "camera_input.jpg"),
        ("yolo_result", "camera_yolo_result_filtered.jpg"),
        ("warning", "multi_sensor_warning.jpg"),
    ]:
        p = d / name
        if p.exists():
            imgs[key] = file_url(p)

    return {
        "exists": True,
        "event_name": d.name,
        "event_dir": str(d),
        "event_type": event_type,
        "timestamp": event_json.get("timestamp", ""),
        "board_ip": event_json.get("board_ip", ""),
        "decision": event_json.get("decision", event_type),
        "problems": event_json.get("problems", []),
        "risk_level": risk,
        "alarm_action": alarm_action,
        "face_status": face_status,
        "final_report_text": final_txt,
        "sensor_status_text": sensor_txt,
        "images": imgs,
        "event_json": event_json,
    }


def recent_events(limit=12):
    out = []
    for d in list_event_dirs()[:limit]:
        event_json = safe_load_json(d / "event.json")
        out.append({
            "event_name": d.name,
            "event_type": event_json.get("event_type") or event_json.get("decision") or infer_event_type_from_name(d.name),
            "timestamp": event_json.get("timestamp", ""),
            "decision": event_json.get("decision", ""),
            "problems": event_json.get("problems", []),
        })
    return out


def safe_cmd(cmd, timeout=10):
    """
    Run shell command safely from the background web server.

    Key points:
    1. stdin=subprocess.DEVNULL prevents child commands from reading terminal input.
    2. start_new_session=True prevents the web server job from being stopped
       when child commands such as sudo try to access the terminal.
    3. If sudo credentials are unavailable, the command should fail gracefully
       instead of stopping the whole 9090 service.
    """
    try:
        r = subprocess.run(
            cmd,
            shell=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
            start_new_session=True,
        )
        return r.stdout
    except Exception as e:
        return str(e)


def run_background(cmd, log_name):
    DAY41_ROOT.mkdir(parents=True, exist_ok=True)
    log = DAY41_ROOT / log_name
    with open(log, "a", encoding="utf-8") as f:
        f.write("\n\n===== %s =====\nCMD: %s\n" % (now_str(), cmd))
    subprocess.Popen(
        f"nohup bash -lc {json.dumps(cmd)} >> {str(log)} 2>&1 &",
        shell=True,
    )
    return str(log)


def do_control(action):
    result = {"action": action, "ok": True, "detail": "", "log": ""}

    if action == "start":
        if CONTROL_SCRIPT.exists():
            log = run_background(f"bash {CONTROL_SCRIPT} start", "control_start.log")
            result["detail"] = "called elf2_runtime_control.sh start"
            result["log"] = log
        else:
            write_state_value(["mode", "mode.txt"], "RUNNING")
            write_state_value(["auto_capture_enabled", "auto_capture_enabled.txt"], "1")
            write_state_value(["alarm_enabled", "alarm_enabled.txt"], "1")
            result["detail"] = "runtime_control not found; wrote state fallback"

    elif action == "stop":
        if CONTROL_SCRIPT.exists():
            log = run_background(f"bash {CONTROL_SCRIPT} stop", "control_stop.log")
            result["detail"] = "called elf2_runtime_control.sh stop"
            result["log"] = log
        else:
            write_state_value(["mode", "mode.txt"], "STOPPED")
            write_state_value(["auto_capture_enabled", "auto_capture_enabled.txt"], "0")
            result["detail"] = "runtime_control not found; wrote state fallback"

    elif action == "night":
        if CONTROL_SCRIPT.exists():
            log = run_background(f"bash {CONTROL_SCRIPT} night", "control_night.log")
            result["detail"] = "called elf2_runtime_control.sh night"
            result["log"] = log
        else:
            write_state_value(["mode", "mode.txt"], "NIGHT")
            write_state_value(["night_mode", "night_mode.txt"], "1")
            result["detail"] = "runtime_control not found; wrote state fallback"

    elif action == "alarm_on":
        write_state_value(["alarm_enabled", "alarm_enabled.txt"], "1")
        result["detail"] = "alarm_enabled=1"

    elif action == "alarm_off":
        write_state_value(["alarm_enabled", "alarm_enabled.txt"], "0")
        result["detail"] = "alarm_enabled=0"



    elif action == "capture":

        wrapper = Path("/usr/local/bin/elf2_mobile_capture")

        if wrapper.exists():

            cmd = "sudo -n /usr/local/bin/elf2_mobile_capture"

            output = safe_cmd(cmd, timeout=240)

            append_day41_log(

                "control_capture.log",

                f"\n\n===== {now_str()} =====\nCMD: {cmd}\n{output}\n"

            )

            result["log"] = str(DAY41_ROOT / "control_capture.log")

            if "RESULT=NO_ALERT" in output or ("Decision: MOBILE_CAPTURE" in output and "Abnormal: False" in output):

                mobile_dir = create_mobile_capture_record(output)

                result["detail"] = f"mobile capture record created: {mobile_dir.name}"

                result["mobile_event_dir"] = str(mobile_dir)

                result["capture_result"] = "MOBILE_CAPTURE"

            else:

                result["ok"] = False

                result[
                    "detail"] = "mobile capture command finished, but result was not recognized; check control_capture.log"

                result["capture_result"] = "UNKNOWN"


        else:

            result["ok"] = False

            result["detail"] = "wrapper not found: /usr/local/bin/elf2_mobile_capture"

    else:
        result["ok"] = False
        result["detail"] = "unknown action"

    return result


MOBILE_HTML = r"""
<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ELF2 Mobile Control Center</title>
<style>
:root {
  --bg:#0f172a; --card:#111827; --card2:#1f2937; --text:#f8fafc;
  --muted:#94a3b8; --green:#22c55e; --red:#ef4444; --yellow:#facc15;
  --blue:#38bdf8; --border:#334155;
}
* { box-sizing: border-box; }
body { margin:0; font-family: -apple-system,BlinkMacSystemFont,"Segoe UI",Arial,"Microsoft YaHei",sans-serif; background:var(--bg); color:var(--text); }
header { padding:18px 16px 10px; }
h1 { font-size:22px; margin:0 0 6px; }
.sub { color:var(--muted); font-size:13px; }
.wrap { padding:0 12px 24px; max-width:780px; margin:0 auto; }
.card { background:var(--card); border:1px solid var(--border); border-radius:16px; padding:14px; margin:12px 0; box-shadow:0 10px 26px rgba(0,0,0,.18); }
.row { display:flex; gap:10px; flex-wrap:wrap; }
.pill { display:inline-block; padding:6px 10px; border-radius:999px; background:var(--card2); color:var(--text); font-size:13px; margin:3px 4px 3px 0; }
.pill.green { color:#052e16; background:var(--green); }
.pill.red { color:#450a0a; background:var(--red); }
.pill.yellow { color:#422006; background:var(--yellow); }
.pill.blue { color:#082f49; background:var(--blue); }
.grid { display:grid; grid-template-columns:1fr 1fr; gap:10px; }
.kv { background:var(--card2); border-radius:12px; padding:10px; }
.k { color:var(--muted); font-size:12px; }
.v { font-size:17px; margin-top:4px; font-weight:700; word-break:break-word; }
button { border:0; border-radius:13px; padding:12px 10px; font-weight:700; background:#2563eb; color:white; width:100%; font-size:15px; }
button.danger { background:#dc2626; }
button.warn { background:#ca8a04; }
button.ok { background:#16a34a; }
button.gray { background:#475569; }
img { width:100%; border-radius:14px; border:1px solid var(--border); background:#020617; margin-top:8px; }
pre { white-space:pre-wrap; word-break:break-word; background:#020617; border:1px solid var(--border); border-radius:12px; padding:12px; color:#d1d5db; max-height:360px; overflow:auto; }
.eventItem { border-top:1px solid var(--border); padding:9px 0; font-size:13px; }
.eventItem:first-child { border-top:0; }
.small { font-size:12px; color:var(--muted); }
a { color:#7dd3fc; }
</style>
</head>
<body>
<header>
  <h1>📱 ELF2 手机安防控制中心</h1>
  <div class="sub">Day41 Mobile Control Center · 自动刷新 5 秒</div>
</header>
<div class="wrap">

<div class="card">
  <h3>系统状态</h3>
  <div class="grid">
    <div class="kv"><div class="k">Mode</div><div class="v" id="mode">...</div></div>
    <div class="kv"><div class="k">Alarm</div><div class="v" id="alarm">...</div></div>
    <div class="kv"><div class="k">Auto capture</div><div class="v" id="auto">...</div></div>
    <div class="kv"><div class="k">Night mode</div><div class="v" id="night">...</div></div>
  </div>
  <div class="small" id="time"></div>
</div>

<div class="card">
  <h3>当前硬件状态</h3>
  <div class="grid">
    <div class="kv"><div class="k">I2C4</div><div class="v" id="i2c4">...</div></div>
    <div class="kv"><div class="k">BH1750</div><div class="v" id="bh1750">...</div></div>
    <div class="kv"><div class="k">MPU6050</div><div class="v" id="mpu6050">...</div></div>
    <div class="kv"><div class="k">Sensor detail</div><div class="v" id="sensor_detail">...</div></div>
  </div>
</div>

<div class="card">
  <h3>快捷控制</h3>
  <div class="grid">
    <button class="ok" onclick="control('start')">▶ 开始检测</button>
    <button class="danger" onclick="control('stop')">⛔ 停止检测</button>
    <button onclick="control('capture')">📸 立即抓拍</button>
    <button class="warn" onclick="control('night')">🌙 夜间模式</button>
    <button class="gray" onclick="control('alarm_on')">🔔 开启告警</button>
    <button class="gray" onclick="control('alarm_off')">🔕 关闭告警</button>
  </div>
  <p class="small" id="control_result">按钮会调用现有脚本或写入状态文件，不会覆盖 8080/8090 原网页。</p>
</div>

<div class="card">
  <h3>最新事件</h3>
  <div id="event_pills"></div>
  <div class="small" id="event_name"></div>
</div>

<div class="card">
  <h3>现场图像</h3>
  <div id="images"></div>
</div>

<div class="card">
  <h3>最终报告 / AI 分析</h3>
  <pre id="report">Loading...</pre>
</div>

<div class="card">
  <h3>最近事件流</h3>
  <div id="event_list"></div>
</div>

<div class="card">
  <h3>原始传感器状态</h3>
  <pre id="sensor"></pre>
</div>

</div>

<script>
const params = new URLSearchParams(location.search);
const token = params.get("token") || "elf2day41";

function clsRisk(r) {
  r = (r || "").toUpperCase();
  if (r.includes("HIGH")) return "red";
  if (r.includes("MEDIUM")) return "yellow";
  if (r.includes("LOW")) return "green";
  return "blue";
}

async function api(path, opts={}) {
  const sep = path.includes("?") ? "&" : "?";
  return fetch(path + sep + "token=" + encodeURIComponent(token), opts).then(r => r.json());
}

async function refresh() {
  try {
    const data = await api("/api/summary");
    const s = data.system || {};
    const e = data.latest_event || {};
    const h = data.sensor_health || {};

    document.getElementById("mode").innerText = s.mode || "UNKNOWN";
    document.getElementById("alarm").innerText = s.alarm_enabled;
    document.getElementById("auto").innerText = s.auto_capture_enabled;
    document.getElementById("night").innerText = s.night_mode;
    document.getElementById("time").innerText = "Updated: " + (data.time || "");

    document.getElementById("i2c4").innerText = h.i2c4 || "UNKNOWN";

    document.getElementById("bh1750").innerText =
      (h.bh1750_online ? "ONLINE" : "OFFLINE") +
      " / " + (h.bh1750_status || "UNKNOWN") +
      (h.bh1750_lux ? " / " + h.bh1750_lux + " lux" : "");

    document.getElementById("mpu6050").innerText =
      (h.mpu6050_online ? "ONLINE" : "OFFLINE") +
      " / " + (h.mpu6050_status || "UNKNOWN");

    document.getElementById("sensor_detail").innerText =
      "gyro=" + (h.mpu6050_gyro || "-") +
      ", acc=" + (h.mpu6050_accdelta || "-");

    let pills = "";
    pills += `<span class="pill ${clsRisk(e.risk_level)}">Risk: ${e.risk_level || "UNKNOWN"}</span>`;
    pills += `<span class="pill blue">${e.event_type || "NO_EVENT"}</span>`;
    pills += `<span class="pill">${e.alarm_action || "UNKNOWN"}</span>`;
    pills += `<span class="pill">Face: ${e.face_status || "UNKNOWN"}</span>`;
    document.getElementById("event_pills").innerHTML = pills;
    document.getElementById("event_name").innerText = e.event_name || "";

    let imgs = "";
    if (e.images) {
      for (const [k, v] of Object.entries(e.images)) {
        imgs += `<div class="small">${k}</div><img src="${v}&token=${encodeURIComponent(token)}&t=${Date.now()}">`;
      }
    }
    document.getElementById("images").innerHTML = imgs || "<div class='small'>暂无图像</div>";

    document.getElementById("report").innerText =
      e.final_report_text || JSON.stringify(e.event_json || {}, null, 2) || "暂无报告";

    document.getElementById("sensor").innerText =
      e.sensor_status_text || "暂无传感器文本";

    let list = "";
    (data.recent_events || []).forEach(x => {
      list += `<div class="eventItem"><b>${x.event_name}</b><br><span class="small">[${x.source || "unknown"}] ${x.timestamp || ""}</span></div>`;
    });
    document.getElementById("event_list").innerHTML = list || "<div class='small'>暂无事件</div>";
  } catch (err) {
    document.getElementById("report").innerText = "刷新失败: " + err;
  }
}

async function control(action) {
  document.getElementById("control_result").innerText = "执行中: " + action;
  try {
    const r = await api("/api/control/" + action, {method:"POST"});
    document.getElementById("control_result").innerText = JSON.stringify(r);
    setTimeout(refresh, 1000);
  } catch (err) {
    document.getElementById("control_result").innerText = "执行失败: " + err;
  }
}

refresh();
setInterval(refresh, 5000);
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    token = "elf2day41"

    def log_message(self, fmt, *args):
        return

    def parse_query(self):
        u = urllib.parse.urlparse(self.path)
        return u.path, urllib.parse.parse_qs(u.query)

    def authorized(self, qs):
        t = qs.get("token", [""])[0]
        return t == self.token

    def send_json(self, obj, code=200):
        raw = json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def send_html(self, s):
        raw = s.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def send_text(self, s, code=200):
        raw = s.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        path, qs = self.parse_query()

        if path in ["/", "/mobile"]:
            if not self.authorized(qs):
                return self.send_text("403 invalid token", 403)
            return self.send_html(MOBILE_HTML)

        if path == "/api/summary":
            if not self.authorized(qs):
                return self.send_json({"error": "invalid token"}, 403)
            return self.send_json({
                "ok": True,
                "time": now_str(),
                "system": read_system_status(),
                "sensor_health": read_current_sensor_health(),
                "latest_event": combined_latest_summary(),
                "recent_events": combined_recent_events(12),
            })

        if path == "/api/status":
            if not self.authorized(qs):
                return self.send_json({"error": "invalid token"}, 403)
            return self.send_json(read_system_status())

        if path == "/api/events":
            if not self.authorized(qs):
                return self.send_json({"error": "invalid token"}, 403)
            return self.send_json(combined_recent_events(30))

        if path == "/file":
            if not self.authorized(qs):
                return self.send_text("403 invalid token", 403)
            p_raw = qs.get("path", [""])[0]
            try:
                p = Path(p_raw).resolve()
                ok = False
                for root in ALLOWED_FILE_ROOTS:
                    try:
                        p.relative_to(root.resolve())
                        ok = True
                        break
                    except Exception:
                        pass
                if not ok or not p.exists() or not p.is_file():
                    return self.send_text("file not allowed or not found", 404)
                mime = mimetypes.guess_type(str(p))[0] or "application/octet-stream"
                data = p.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", mime)
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            except Exception as e:
                return self.send_text(str(e), 500)

        return self.send_text("404", 404)

    def do_POST(self):
        path, qs = self.parse_query()
        if not self.authorized(qs):
            return self.send_json({"error": "invalid token"}, 403)

        prefix = "/api/control/"
        if path.startswith(prefix):
            action = path[len(prefix):]
            return self.send_json(do_control(action))

        return self.send_json({"error": "unknown endpoint"}, 404)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=9090)
    ap.add_argument("--token", default="elf2day41")
    args = ap.parse_args()

    Handler.token = args.token
    DAY41_ROOT.mkdir(parents=True, exist_ok=True)

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Day41 Mobile Gateway running at http://{args.host}:{args.port}/mobile?token={args.token}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
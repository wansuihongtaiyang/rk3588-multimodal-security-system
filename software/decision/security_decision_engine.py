# -*- coding: utf-8 -*-

import argparse
import json
import re
import time
from datetime import datetime
from pathlib import Path


def read_text(path, limit=100000):
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")[:limit]
    except Exception:
        return ""


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return {}


def write_json(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_text(path, text):
    Path(path).write_text(text, encoding="utf-8")


def parse_face_status(event_dir, ai_json):
    p = Path(event_dir) / "face_status.txt"
    txt = read_text(p, limit=2000)

    for line in txt.splitlines():
        line = line.strip()
        if line.startswith("FACE_STATUS="):
            return line.split("=", 1)[1].strip()

    if ai_json.get("face_status"):
        return str(ai_json.get("face_status")).strip()

    face_info = ai_json.get("face_info") or {}
    if face_info.get("face_status"):
        return str(face_info.get("face_status")).strip()

    face_json = read_json(Path(event_dir) / "face_auth_result.json")
    if face_json.get("face_status"):
        return str(face_json.get("face_status")).strip()

    return "UNKNOWN"


def parse_lux(all_text):
    patterns = [
        r"LUX\s*=\s*([0-9]+(?:\.[0-9]+)?)",
        r"lux['\"]?\s*[:=]\s*['\"]?([0-9]+(?:\.[0-9]+)?)",
        r"\b(?:NORMAL|DARK|BRIGHT)\s+([0-9]+(?:\.[0-9]+)?)\b",
    ]
    for pat in patterns:
        m = re.search(pat, all_text, re.I)
        if m:
            try:
                return float(m.group(1))
            except Exception:
                pass
    return None


def detect_person_from_text(text):
    positive = [
        "是否有人：是",
        "是否有人: 是",
        "有一个人",
        "有人",
        "一个人",
        "人影",
        "人脸",
        "人的头部",
        "部分脸部",
        "穿着",
    ]
    negative = [
        "没有人",
        "无人",
        "没有明确的人影",
        "未发现人员",
        "没有发现人员",
    ]

    if any(k in text for k in negative):
        strong_positive = ["有一个人", "是否有人：是", "是否有人: 是"]
        return any(k in text for k in strong_positive)

    return any(k in text for k in positive)


def detect_camera_blocked_or_blur(text, lux):
    words = [
        "画面变黑",
        "完全黑",
        "遮挡摄像头",
        "镜头被遮挡",
        "画面被遮挡",
        "严重模糊",
        "几乎看不清",
        "无法看清",
        "黑色区域",
    ]

    if any(w in text for w in words):
        return True

    if lux is not None and lux <= 2.0:
        if "昏暗" in text or "模糊" in text or "黑色区域" in text:
            return True

    return False


def parse_motion_status(all_text):
    t = all_text.upper()

    if "MOTION_TAMPER" in t or "TAMPER" in t:
        return "MOTION_TAMPER"

    if "MOTION_SHAKING" in t or "SHAKING" in t:
        return "MOTION_SHAKING"

    if "MOTION_MOVING" in t or "MOVING" in t:
        return "MOTION_MOVING"

    if "MOTION_IDLE" in t or "IDLE" in t:
        return "MOTION_IDLE"

    m = re.search(r"MOTION\s*=\s*([A-Z_]+)", t)
    if m:
        v = m.group(1)
        if "SHAK" in v:
            return "MOTION_SHAKING"
        if "MOV" in v:
            return "MOTION_MOVING"
        if "IDLE" in v or "STATIC" in v or "NORMAL" in v:
            return "MOTION_IDLE"

    return "UNKNOWN"


def parse_light_status(event_type, all_text, lux, dark_threshold):
    t = all_text.upper()

    if "LIGHT_DARK" in str(event_type).upper() or "LIGHT_DARK" in t:
        return "LIGHT_DARK"

    if "DARK" in t:
        return "LIGHT_DARK"

    if lux is not None:
        if lux < dark_threshold:
            return "LIGHT_DARK"
        return "LIGHT_NORMAL"

    return "UNKNOWN"


def is_after_hours(now_hour, night_start, night_end):
    if night_start > night_end:
        return now_hour >= night_start or now_hour < night_end
    return night_start <= now_hour < night_end


def count_recent_similar_events(root, event_dir, event_type, window_sec):
    root = Path(root)
    this_dir = Path(event_dir).resolve()

    try:
        this_mtime = this_dir.stat().st_mtime
    except Exception:
        this_mtime = time.time()

    if not root.exists():
        return 0

    count = 0

    for p in root.iterdir():
        if not p.is_dir():
            continue

        try:
            if p.resolve() == this_dir:
                continue
            if abs(this_mtime - p.stat().st_mtime) > window_sec:
                continue
        except Exception:
            continue

        name = p.name.upper()

        if event_type and str(event_type).upper() in name:
            count += 1
            continue

        ej = read_json(p / "event.json")
        et = str(ej.get("event_type") or ej.get("decision") or "").upper()

        if event_type and et == str(event_type).upper():
            count += 1

    return count


def decide(event_dir, args):
    event_dir = Path(event_dir).resolve()

    event_json = read_json(event_dir / "event.json")
    ai_json = read_json(event_dir / "event_ai_report.json")
    face_json = read_json(event_dir / "face_auth_result.json")
    voice_json = read_json(event_dir / "voice_command.json")

    sensor_status = read_text(event_dir / "sensor_status.txt")
    face_status_text = read_text(event_dir / "face_status.txt")

    event_type = (
        ai_json.get("event_type")
        or event_json.get("event_type")
        or event_json.get("decision")
        or event_dir.name
    )

    image_summary = ai_json.get("image_summary") or ""
    final_report = ai_json.get("final_report") or ""
    deepseek_raw = ai_json.get("deepseek_raw_answer") or ""

    all_text = "\n".join([
        json.dumps(event_json, ensure_ascii=False),
        json.dumps(ai_json, ensure_ascii=False),
        json.dumps(face_json, ensure_ascii=False),
        sensor_status,
        face_status_text,
        image_summary,
        final_report,
        deepseek_raw,
        event_dir.name,
    ])

    face_status = parse_face_status(event_dir, ai_json)
    lux = parse_lux(all_text)
    motion_status = parse_motion_status(all_text)
    light_status = parse_light_status(event_type, all_text, lux, args.dark_threshold)

    person_detected = detect_person_from_text(image_summary + "\n" + final_report)
    camera_blocked = detect_camera_blocked_or_blur(image_summary + "\n" + final_report, lux)

    now = datetime.now()
    after_hours = is_after_hours(now.hour, args.night_start, args.night_end)
    night_mode = args.night_mode or after_hours

    repeated_count = count_recent_similar_events(
        args.root,
        event_dir,
        event_type,
        args.repeat_window,
    )

    score = 0
    score_items = []
    reasons = []

    def add(points, reason):
        nonlocal score
        score += points
        score_items.append({
            "points": points,
            "reason": reason,
        })
        reasons.append(reason)

    if face_status == "AUTHORIZED":
        add(-30, "FaceAuth 判断为授权仓库工作人员，降低外人闯入风险")
    elif face_status == "UNKNOWN_PERSON":
        add(50, "FaceAuth 检测到未匹配白名单的未知人员")
    elif face_status == "NO_FACE" and person_detected:
        add(20, "图像中有人但 FaceAuth 未检测到可识别人脸，身份无法确认")
    elif face_status in ["UNKNOWN", ""]:
        if person_detected:
            add(15, "图像中疑似有人，但缺少有效 FaceAuth 身份判断")

    if light_status == "LIGHT_DARK":
        if night_mode and not person_detected:
            add(0, "夜间低光且未发现人员，按正常夜间环境记录")
        elif night_mode and person_detected:
            add(8, "夜间低光且图像中有人，需要关注，但光照权重低于运动异常")
        else:
            add(10, "非夜间或未启用夜间模式时检测到低光/光照异常，按中低权重处理")

    if motion_status == "MOTION_MOVING":
        add(25, "MPU6050 检测到轻微移动，运动权重高于单纯光照异常")
    elif motion_status == "MOTION_SHAKING":
        add(45, "MPU6050 检测到明显震动，提升为主要风险证据")
    elif motion_status == "MOTION_TAMPER":
        add(70, "MPU6050 检测到疑似破坏或搬动，按高风险证据处理")

    if camera_blocked:
        add(40, "图像疑似被遮挡、严重变暗或模糊")

    if "SENSOR_OFFLINE" in all_text.upper() or "MPU6050: NONE" in all_text.upper():
        add(15, "存在传感器离线或读数缺失，系统可靠性下降")

    if person_detected and face_status not in ["AUTHORIZED", "UNKNOWN_PERSON"]:
        add(10, "Qwen2-VL 判断画面中存在人员")

    if after_hours:
        if face_status == "UNKNOWN_PERSON" or person_detected:
            add(10, "当前处于夜间或非工作时段，且检测到人员活动，风险适度提高")
        else:
            reasons.append("当前处于夜间或非工作时段，但未发现人员，不单独提高风险")
    else:
        add(-5, "当前处于日间或工作时段，普通人员活动风险略低")

    if repeated_count >= args.repeat_count:
        add(20, f"{args.repeat_window} 秒内出现 {repeated_count} 个同类事件，疑似持续异常")

    final_decision = "NORMAL_RECORD"

    if face_status == "UNKNOWN_PERSON":
        if light_status == "LIGHT_DARK" or motion_status in ["MOTION_MOVING", "MOTION_SHAKING", "MOTION_TAMPER"]:
            final_decision = "UNKNOWN_PERSON_WITH_ABNORMAL_SENSOR"
            score = max(score, 85)
        else:
            final_decision = "UNKNOWN_PERSON"
            score = max(score, 75)

    elif face_status == "AUTHORIZED":
        if motion_status in ["MOTION_SHAKING", "MOTION_TAMPER"]:
            final_decision = "AUTHORIZED_WITH_STRONG_MOTION"
            score = max(score, 45)
        elif light_status == "LIGHT_DARK" and not night_mode:
            final_decision = "AUTHORIZED_WITH_LIGHT_DARK"
            score = max(score, 40)
        elif light_status == "LIGHT_DARK" and night_mode:
            final_decision = "AUTHORIZED_NIGHT_LOW_LIGHT"
            score = min(max(score, 25), 55)
        else:
            final_decision = "AUTHORIZED_NORMAL"
            score = min(score, 25)

    elif face_status == "NO_FACE" and person_detected:
        if light_status == "LIGHT_DARK" or motion_status in ["MOTION_SHAKING", "MOTION_TAMPER"]:
            final_decision = "PERSON_NO_FACE_WITH_ABNORMAL"
            score = max(score, 70)
        else:
            final_decision = "PERSON_NO_FACE"
            score = max(score, 45)

    else:
        if camera_blocked:
            final_decision = "CAMERA_OR_LIGHT_TAMPER"
            score = max(score, 70)
        elif motion_status in ["MOTION_SHAKING", "MOTION_TAMPER"]:
            final_decision = "MOTION_ABNORMAL"
            score = max(score, 60)
        elif light_status == "LIGHT_DARK" and night_mode and not person_detected:
            final_decision = "EXPECTED_NIGHT_DARK"
            score = min(score, 20)
        elif light_status == "LIGHT_DARK":
            final_decision = "LIGHT_DARK_SUSPICIOUS"
            score = max(score, 40)

    if score >= 70:
        risk_level = "HIGH"
        alarm_action = "REMOTE_ALERT"
    elif score >= 30:
        risk_level = "MEDIUM"
        alarm_action = "LOCAL_WARNING"
    else:
        risk_level = "LOW"
        alarm_action = "RECORD_ONLY"

    if face_status == "AUTHORIZED":
        if motion_status not in ["MOTION_SHAKING", "MOTION_TAMPER"] and not camera_blocked:
            if light_status != "LIGHT_DARK":
                risk_level = "LOW"
                alarm_action = "RECORD_ONLY"
                final_decision = "AUTHORIZED_NORMAL"

    # STRICT_PERSON_WHITELIST_V3
    # 只要图像中有人，但 FaceAuth 没有确认 AUTHORIZED，就提升为远程告警。
    # 这用于库房安防场景：人员必须匹配白名单，否则需要人工确认。
    if person_detected and face_status != "AUTHORIZED":
        risk_level = "HIGH"
        alarm_action = "REMOTE_ALERT"
        score = max(score, 80)

        if face_status == "UNKNOWN_PERSON":
            final_decision = "UNKNOWN_PERSON_REMOTE_ALERT"
            reasons.append("严格白名单策略：检测到未知人员，未匹配授权员工，触发远程告警")
        elif face_status == "NO_FACE":
            final_decision = "PERSON_DETECTED_BUT_NO_FACE_REMOTE_ALERT"
            reasons.append("严格白名单策略：图像中有人但未检测到可识别人脸，人员身份无法确认，触发远程告警")
        else:
            final_decision = "PERSON_DETECTED_BUT_NOT_AUTHORIZED_REMOTE_ALERT"
            reasons.append("严格白名单策略：图像中有人但未确认授权员工身份，触发远程告警")

    # ALARM_ENABLED_RUNTIME_V4
    # 语音“关闭告警”后，风险仍可保持 HIGH，但告警动作降级为仅记录。
    runtime_snapshot = voice_json.get("runtime_state_snapshot") or {}
    alarm_enabled_runtime = str(runtime_snapshot.get("alarm_enabled", "1"))

    if alarm_enabled_runtime == "0" and alarm_action == "REMOTE_ALERT":
        reasons.append("运行状态显示 alarm_enabled=0，当前已关闭告警，因此不执行远程告警动作，仅保留事件记录")
        alarm_action = "ALARM_DISABLED_RECORD_ONLY"

    recommended = []

    if alarm_action == "REMOTE_ALERT":
        recommended.append("立即查看网页现场图片和 AI 报告，并确认是否存在未授权人员或破坏行为。")
    elif alarm_action == "LOCAL_WARNING":
        recommended.append("在本地网页保留提示，建议人工查看现场图片和传感器状态。")
    else:
        recommended.append("仅记录事件，不发送强告警。")

    if face_status == "AUTHORIZED":
        recommended.append("人员匹配授权白名单，可作为正常仓库工作人员活动记录。")
    if face_status == "UNKNOWN_PERSON":
        recommended.append("未知人员未匹配白名单，应优先核验身份。")
    if motion_status in ["MOTION_SHAKING", "MOTION_TAMPER"]:
        recommended.append("检查货架、设备或开发板是否被碰撞、搬动或破坏。")
    if light_status == "LIGHT_DARK" and not night_mode:
        recommended.append("检查照明、电源、光照传感器和摄像头是否被遮挡。")
    if "SENSOR_OFFLINE" in all_text.upper() or "MPU6050: NONE" in all_text.upper():
        recommended.append("存在传感器离线风险，建议检查 MPU6050/BH1750 接线和 I2C 状态。")

    result = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "event_dir": str(event_dir),
        "event_type": str(event_type),
        "risk_level": risk_level,
        "alarm_action": alarm_action,
        "final_decision": final_decision,
        "score": int(round(score)),
        "score_items": score_items,
        "reasons": reasons,
        "recommended_actions": recommended,
        "evidence": {
            "face_status": face_status,
            "person_detected_by_qwen": bool(person_detected),
            "light_status": light_status,
            "lux": lux,
            "motion_status": motion_status,
            "camera_blocked_or_blur": bool(camera_blocked),
            "night_mode": bool(night_mode),
            "after_hours": bool(after_hours),
            "repeated_similar_events": repeated_count,
        },
        "thresholds": {
            "dark_threshold": args.dark_threshold,
            "night_start": args.night_start,
            "night_end": args.night_end,
            "repeat_window": args.repeat_window,
            "repeat_count": args.repeat_count,
        },
    }

    return result


def to_text_report(d):
    lines = []
    lines.append("===== Security Decision =====")
    lines.append(f"timestamp: {d.get('timestamp')}")
    lines.append(f"event_type: {d.get('event_type')}")
    lines.append(f"risk_level: {d.get('risk_level')}")
    lines.append(f"alarm_action: {d.get('alarm_action')}")
    lines.append(f"final_decision: {d.get('final_decision')}")
    lines.append(f"score: {d.get('score')}")
    lines.append("")
    lines.append("===== Evidence =====")

    for k, v in d.get("evidence", {}).items():
        lines.append(f"{k}: {v}")

    lines.append("")
    lines.append("===== Reasons =====")

    for i, r in enumerate(d.get("reasons", []), 1):
        lines.append(f"{i}. {r}")

    lines.append("")
    lines.append("===== Score Items =====")

    for item in d.get("score_items", []):
        lines.append(f"{item.get('points'):+d}  {item.get('reason')}")

    lines.append("")
    lines.append("===== Recommended Actions =====")

    for i, r in enumerate(d.get("recommended_actions", []), 1):
        lines.append(f"{i}. {r}")

    lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Day31 security decision engine")
    parser.add_argument("--event-dir", required=True)
    parser.add_argument("--root", default="/home/elf/project_evidence/abnormal_events")
    parser.add_argument("--dark-threshold", type=float, default=30.0)
    parser.add_argument("--night-mode", action="store_true")
    parser.add_argument("--night-start", type=int, default=19)
    parser.add_argument("--night-end", type=int, default=6)
    parser.add_argument("--repeat-window", type=int, default=120)
    parser.add_argument("--repeat-count", type=int, default=2)
    args = parser.parse_args()

    event_dir = Path(args.event_dir).expanduser().resolve()

    if not event_dir.is_dir():
        raise SystemExit(f"event dir not found: {event_dir}")

    result = decide(event_dir, args)

    json_path = event_dir / "security_decision.json"
    txt_path = event_dir / "security_decision.txt"

    write_json(json_path, result)
    write_text(txt_path, to_text_report(result))

    print("==================================================")
    print("Day31 Security Decision Engine")
    print("==================================================")
    print("event_dir      =", event_dir)
    print("risk_level     =", result["risk_level"])
    print("alarm_action   =", result["alarm_action"])
    print("final_decision =", result["final_decision"])
    print("score          =", result["score"])
    print("json           =", json_path)
    print("txt            =", txt_path)
    print("RESULT=OK")


if __name__ == "__main__":
    main()
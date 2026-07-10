#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
from datetime import datetime
from pathlib import Path


def read_text(path, limit=120000):
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


def v(x):
    return "-" if x is None or x == "" else str(x)


def risk_cn(x):
    return {"LOW": "低风险", "MEDIUM": "中风险", "HIGH": "高风险"}.get(str(x), str(x))


def action_cn(x):
    return {
        "RECORD_ONLY": "仅记录，不触发告警",
        "LOCAL_WARNING": "本地提示，建议人工查看",
        "REMOTE_ALERT": "远程告警，建议立即确认",
    }.get(str(x), str(x))


def face_cn(x):
    return {
        "AUTHORIZED": "授权仓库工作人员",
        "UNKNOWN_PERSON": "未知或未授权人员",
        "NO_FACE": "未检测到可识别人脸",
        "UNKNOWN": "人员身份未知",
    }.get(str(x), str(x))


def light_cn(x):
    return {
        "LIGHT_NORMAL": "光照正常",
        "LIGHT_DARK": "光照过暗或疑似遮挡",
        "UNKNOWN": "未知",
    }.get(str(x), str(x))


def motion_cn(x):
    return {
        "MOTION_IDLE": "无明显运动",
        "MOTION_MOVING": "轻微移动",
        "MOTION_SHAKING": "明显震动",
        "MOTION_TAMPER": "疑似搬动或破坏",
        "UNKNOWN": "未知",
    }.get(str(x), str(x))


def get_face_status(event_dir, ai_json, face_json):
    txt = read_text(Path(event_dir) / "face_status.txt", 2000)
    for line in txt.splitlines():
        line = line.strip()
        if line.startswith("FACE_STATUS="):
            return line.split("=", 1)[1].strip()

    if ai_json.get("face_status"):
        return ai_json.get("face_status")

    face_info = ai_json.get("face_info") or {}
    if face_info.get("face_status"):
        return face_info.get("face_status")

    if face_json.get("face_status"):
        return face_json.get("face_status")

    return "UNKNOWN"


def get_employee(ai_json, face_json):
    face_info = ai_json.get("face_info") or {}
    nested = face_info.get("face_auth_result") or {}

    return (
        face_json.get("best_employee")
        or face_json.get("employee_id")
        or nested.get("best_employee")
        or nested.get("employee_id")
        or ""
    )


def get_distance(ai_json, face_json):
    face_info = ai_json.get("face_info") or {}
    nested = face_info.get("face_auth_result") or {}

    if "best_distance" in face_json:
        d = face_json.get("best_distance")
    else:
        d = nested.get("best_distance")

    if d is None or d == "":
        return ""

    try:
        return f"{float(d):.6f}"
    except Exception:
        return str(d)


def make_one_sentence(risk, action, face_status, employee, evidence):
    light_status = evidence.get("light_status")
    motion_status = evidence.get("motion_status")
    person = evidence.get("person_detected_by_qwen")

    if face_status == "AUTHORIZED" and risk == "LOW":
        who = employee or "授权仓库工作人员"
        return f"画面中的人员匹配授权白名单，身份为 {who}，现场未发现需要升级处理的异常，本次事件仅记录，不触发告警。"

    if face_status == "AUTHORIZED":
        who = employee or "授权仓库工作人员"
        return f"画面中的人员为 {who}，人员身份正常，但现场存在传感器或环境异常，建议在本地网页提示并人工查看。"

    if face_status == "UNKNOWN_PERSON":
        return "系统检测到未匹配白名单的未知人员，库房属于受控区域，本次事件应作为高优先级安全事件处理。"

    if face_status == "NO_FACE" and person:
        return "图像中存在人员迹象，但 FaceAuth 未检测到可识别人脸，人员身份无法确认，建议人工查看现场图像。"

    if light_status == "LIGHT_DARK" and not person:
        return "系统检测到光照异常，但图像中未确认人员，应结合时间段判断是否为正常夜间低光或疑似遮挡。"

    if motion_status in ["MOTION_SHAKING", "MOTION_TAMPER"]:
        return "MPU6050 检测到明显运动或疑似搬动，建议检查设备、货架或现场是否被碰撞。"

    if risk == "HIGH":
        return "系统综合判断本次事件为高风险，应立即查看网页证据并进行人工确认。"

    if risk == "MEDIUM":
        return "系统综合判断本次事件为中风险，建议保留本地提示并人工复核。"

    return "系统综合判断本次事件为低风险，可作为普通记录保存。"


def compact(text, limit=900):
    text = (text or "").strip()
    if not text:
        return "暂无 Qwen2-VL 图像分析结果。"
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "……"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--event-dir", required=True)
    args = parser.parse_args()

    event_dir = Path(args.event_dir).expanduser().resolve()

    if not event_dir.is_dir():
        raise SystemExit(f"event dir not found: {event_dir}")

    event_json = read_json(event_dir / "event.json")
    ai_json = read_json(event_dir / "event_ai_report.json")
    face_json = read_json(event_dir / "face_auth_result.json")
    sec_json = read_json(event_dir / "security_decision.json")

    sensor_status = read_text(event_dir / "sensor_status.txt")
    voice_json = read_json(event_dir / "voice_command.json")

    event_type = (
        sec_json.get("event_type")
        or ai_json.get("event_type")
        or event_json.get("event_type")
        or event_json.get("decision")
        or event_dir.name
    )

    risk = sec_json.get("risk_level") or "UNKNOWN"
    action = sec_json.get("alarm_action") or "UNKNOWN"
    final_decision = sec_json.get("final_decision") or "UNKNOWN"
    score = sec_json.get("score")

    evidence = sec_json.get("evidence") or {}
    reasons = sec_json.get("reasons") or []
    recommended = sec_json.get("recommended_actions") or []

    face_status = evidence.get("face_status") or get_face_status(event_dir, ai_json, face_json)
    employee = get_employee(ai_json, face_json)
    distance = get_distance(ai_json, face_json)

    image_summary = ai_json.get("image_summary") or ""
    raw_final_report = ai_json.get("final_report") or ""

    light_status = evidence.get("light_status") or "UNKNOWN"
    lux = evidence.get("lux")
    motion_status = evidence.get("motion_status") or "UNKNOWN"
    person_detected = evidence.get("person_detected_by_qwen")
    camera_blocked = evidence.get("camera_blocked_or_blur")
    night_mode = evidence.get("night_mode")
    after_hours = evidence.get("after_hours")

    one_sentence = make_one_sentence(risk, action, face_status, employee, evidence)

    if face_status == "AUTHORIZED":
        if employee:
            face_conclusion = f"该人员匹配授权白名单，身份为 {employee}，属于仓库工作人员，不按外人闯入处理。"
        else:
            face_conclusion = "该人员匹配授权白名单，属于仓库工作人员，不按外人闯入处理。"
    elif face_status == "UNKNOWN_PERSON":
        face_conclusion = "检测到人脸但未匹配授权白名单，应视为未知或未授权人员。"
    elif face_status == "NO_FACE":
        face_conclusion = "未检测到可识别人脸，无法判断人员身份，不应编造身份。"
    else:
        face_conclusion = "人员身份结果不完整，需要结合现场图像人工确认。"

    evidence_files = []
    for name in [
        "camera_input.jpg",
        "camera_yolo_result_filtered.jpg",
        "multi_sensor_warning.jpg",
        "event.json",
        "sensor_status.txt",
        "face_status.txt",
        "face_auth_result.json",
        "event_ai_report.json",
        "security_decision.json",
        "voice_command.json",
        "voice_command_log.txt",
    ]:
        if (event_dir / name).exists():
            evidence_files.append(name)

    lines = []
    lines.append("===== 智能库房安防事件报告 =====")
    lines.append(f"报告时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    lines.append("一、核心结论")
    lines.append(f"风险等级：{risk}（{risk_cn(risk)}）")
    lines.append(f"告警动作：{action}（{action_cn(action)}）")
    lines.append(f"最终判断：{final_decision}")
    lines.append(f"风险评分：{v(score)}")
    lines.append(f"一句话结论：{one_sentence}")
    lines.append("")
    lines.append("语音触发信息：")
    lines.append(f"触发来源：{v(voice_json.get('trigger_type'))}")
    lines.append(f"语音事件：{v(voice_json.get('selected_event'))}")
    lines.append(f"识别文本：{v(voice_json.get('voice_text'))}")
    runtime_snapshot = voice_json.get("runtime_state_snapshot") or {}
    lines.append("运行状态快照：")
    lines.append(f"检测模式：{v(runtime_snapshot.get('mode'))}")
    lines.append(f"自动抓拍：{v(runtime_snapshot.get('auto_capture_enabled'))}")
    lines.append(f"告警开关：{v(runtime_snapshot.get('alarm_enabled'))}")
    lines.append(f"夜间模式：{v(runtime_snapshot.get('night_mode'))}")
    lines.append("")
    lines.append("二、人员身份判断")
    lines.append(f"FaceAuth 结果：{face_status}（{face_cn(face_status)}）")
    lines.append(f"匹配对象：{v(employee)}")
    lines.append(f"匹配距离：{v(distance)}")
    lines.append(f"人员结论：{face_conclusion}")
    lines.append("")
    lines.append("三、现场图像分析")
    lines.append("Qwen2-VL 结论：")
    lines.append(compact(image_summary))
    lines.append("")
    lines.append("四、传感器与环境状态")
    lines.append(f"光照状态：{light_status}（{light_cn(light_status)}）")
    lines.append(f"光照数值 lux：{v(lux)}")
    lines.append(f"运动状态：{motion_status}（{motion_cn(motion_status)}）")
    lines.append(f"画面是否有人：{v(person_detected)}")
    lines.append(f"是否疑似遮挡或模糊：{v(camera_blocked)}")
    lines.append(f"夜间模式：{v(night_mode)}")
    lines.append(f"非工作或夜间时段：{v(after_hours)}")

    if sensor_status.strip():
        lines.append("")
        lines.append("传感器原始摘要：")
        lines.append(sensor_status.strip()[:1200])

    lines.append("")
    lines.append("五、综合决策理由")

    if reasons:
        for i, reason in enumerate(reasons, 1):
            lines.append(f"{i}. {reason}")
    else:
        lines.append("1. 暂无 security_decision.json 中的 reasons 字段。")

    lines.append("")
    lines.append("六、处理建议")

    if recommended:
        for i, rec in enumerate(recommended, 1):
            lines.append(f"{i}. {rec}")
    else:
        lines.append("1. 建议查看网页中的图片、传感器状态和人脸白名单结果。")

    lines.append("")
    lines.append("七、证据文件")

    for name in evidence_files:
        lines.append(f"- {name}")

    lines.append("")
    lines.append("八、原始 AI 报告摘要")
    lines.append((raw_final_report or "暂无 event_ai_report.json final_report。").strip()[:1500])

    report_text = "\n".join(lines)

    report_json = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "event_dir": str(event_dir),
        "event_type": event_type,
        "risk_level": risk,
        "alarm_action": action,
        "final_decision": final_decision,
        "score": score,
        "one_sentence": one_sentence,
        "face_status": face_status,
        "employee": employee,
        "distance": distance,
        "light_status": light_status,
        "lux": lux,
        "motion_status": motion_status,
        "person_detected_by_qwen": person_detected,
        "display_report": report_text,
    }

    txt_path = event_dir / "final_display_report.txt"
    json_path = event_dir / "final_display_report.json"

    write_text(txt_path, report_text)
    write_json(json_path, report_json)

    print("==================================================")
    print("Day31 Final Display Report")
    print("==================================================")
    print("event_dir =", event_dir)
    print("txt       =", txt_path)
    print("json      =", json_path)
    print("risk      =", risk)
    print("action    =", action)
    print("decision  =", final_decision)
    print("RESULT=OK")


if __name__ == "__main__":
    main()
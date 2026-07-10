#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from pathlib import Path
from datetime import datetime
import py_compile

TARGET = Path("/home/elf/sensor_work/day29_ai/ai_event_analyze_once.py")

NEW_INFER = r'''def infer_risk_level(event_type, sensor_status, image_summary, face_status="UNKNOWN"):
    text = f"{event_type}\n{sensor_status}\n{image_summary}\n{face_status}"

    if face_status == "AUTHORIZED":
        if "LIGHT_DARK" in text or "DARK" in text:
            return "MEDIUM"
        return "LOW"

    if face_status == "UNKNOWN_PERSON":
        return "HIGH"

    person_keywords = ["是否有人：是", "是否有人: 是", "有一个人", "一个人", "有人", "人影", "人的头部", "部分脸部"]
    person_detected = any(k in text for k in person_keywords)

    if person_detected:
        if "LIGHT_DARK" in text or "DARK" in text:
            return "HIGH"
        return "MEDIUM"

    if "MOTION_SHAKING" in text or "SHAKING" in text:
        return "HIGH"

    if "MOTION_MOVING" in text or "MOVING" in text:
        return "MEDIUM"

    if "SENSOR_OFFLINE" in text:
        return "MEDIUM"

    if "LIGHT_DARK" in text or "DARK" in text:
        return "MEDIUM"

    if "SCRIPT_ERROR" in text or "READ_ERROR" in text:
        return "MEDIUM"

    return "LOW"


'''

NEW_MAKE = r'''def make_stable_report(event_type, sensor_status, image_summary, face_info=None):
    face_info = face_info or {}
    face_status = face_info.get("face_status", "UNKNOWN")
    face_auth = face_info.get("face_auth_result", {}) or {}

    best_employee = face_auth.get("best_employee") or face_auth.get("employee_id") or "授权仓库工作人员"
    best_distance = face_auth.get("best_distance", "")

    risk = infer_risk_level(
        event_type=event_type,
        sensor_status=sensor_status,
        image_summary=image_summary,
        face_status=face_status,
    )

    if face_status == "AUTHORIZED":
        person_text = f"FaceAuth 判断画面中的人员匹配授权白名单，身份为 {best_employee}，人员身份正常，不按外人闯入处理。"
        if best_distance != "":
            person_text += f" 人脸匹配距离为 {best_distance}。"
    elif face_status == "UNKNOWN_PERSON":
        person_text = "FaceAuth 检测到人脸但未匹配授权白名单，属于未知人员或未授权人员，建议告警或人工确认。"
    elif face_status == "NO_FACE":
        person_text = "FaceAuth 未检测到可识别人脸，无法判断人员身份，不应编造身份。"
    else:
        person_text = "FaceAuth 未提供有效身份判断结果，人员身份暂不确定。"

    text = f"""
风险等级：{risk}

人员状态：{face_status}

可能原因：
1. 人员白名单判断：{person_text}
2. 本次事件类型为 {event_type}，系统已完成现场抓拍、人脸白名单检测和图像分析。
3. Qwen2-VL 图像分析结果显示：{image_summary}
4. 如果人员状态为 AUTHORIZED，则说明画面中的人为仓库工作人员，人员身份正常，不按外人闯入处理。
5. 如果人员状态为 UNKNOWN_PERSON，则说明检测到未授权人员或无法匹配白名单，需要提高风险等级。

处理建议：
1. 远程查看 camera_input.jpg、camera_yolo_result_filtered.jpg、event.json、sensor_status.txt 和 face_auth_result.json。
2. 如果 face_status 为 AUTHORIZED，可记录本次事件，但不应按外人闯入告警。
3. 如果 face_status 为 UNKNOWN_PERSON，应立即告警或人工确认。
4. 如果同时存在 LIGHT_DARK 和 UNKNOWN_PERSON，应按高风险处理。
5. 如果运动传感器离线，建议尽快恢复 MPU6050，以提高系统可靠性。

最终摘要：
本次事件为 {event_type}。系统已完成 FaceAuth 人脸白名单判断、Qwen2-VL 图像分析和 AI 报告生成。{person_text} 本次事件建议暂定为 {risk} 风险。
""".strip()

    return text


'''

NEW_BUILD = r'''def build_final_report(deepseek_answer, event_type, sensor_status, image_summary, face_info=None):
    """
    优先使用 DeepSeek 的正式报告。
    如果 DeepSeek 输出不完整，或者没有体现 FaceAuth 身份信息，则使用/补充稳定报告。
    """
    face_info = face_info or {}
    face_status = face_info.get("face_status", "UNKNOWN")
    face_auth = face_info.get("face_auth_result", {}) or {}

    best_employee = face_auth.get("best_employee") or face_auth.get("employee_id") or "授权仓库工作人员"

    clean = strip_think_block(deepseek_answer)

    if is_deepseek_report_usable(clean):
        if face_status == "AUTHORIZED" and ("授权" not in clean and "仓库工作人员" not in clean and "人员身份正常" not in clean):
            clean += f"\n\n人员身份补充：FaceAuth 判断画面中的人员匹配授权白名单，身份为 {best_employee}，人员身份正常，不按外人闯入处理。"
        elif face_status == "UNKNOWN_PERSON" and ("未授权" not in clean and "未知人员" not in clean):
            clean += "\n\n人员身份补充：FaceAuth 检测到人脸但未匹配授权白名单，属于未知人员或未授权人员，建议告警或人工确认。"
        return clean, "deepseek"

    fallback = make_stable_report(
        event_type=event_type,
        sensor_status=sensor_status,
        image_summary=image_summary,
        face_info=face_info,
    )
    return fallback, "stable_fallback"


'''


def replace_between(text, start_marker, end_marker, replacement):
    start = text.find(start_marker)
    if start < 0:
        raise RuntimeError(f"start marker not found: {start_marker}")

    end = text.find(end_marker, start + len(start_marker))
    if end < 0:
        raise RuntimeError(f"end marker not found after {start_marker}: {end_marker}")

    return text[:start] + replacement + text[end:]


def main():
    if not TARGET.exists():
        raise SystemExit(f"target not found: {TARGET}")

    src = TARGET.read_text(encoding="utf-8", errors="replace")

    backup = TARGET.with_name(
        TARGET.name + ".bak_faceauth_repair_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    )
    backup.write_text(src, encoding="utf-8")

    src = replace_between(
        src,
        "def infer_risk_level(",
        "def make_stable_report(",
        NEW_INFER,
    )

    src = replace_between(
        src,
        "def make_stable_report(",
        "def is_deepseek_report_usable(",
        NEW_MAKE,
    )

    src = replace_between(
        src,
        "def build_final_report(",
        "def main(",
        NEW_BUILD,
    )

    TARGET.write_text(src, encoding="utf-8")

    py_compile.compile(str(TARGET), doraise=True)

    print("repair ok")
    print("target =", TARGET)
    print("backup =", backup)
    print("py_compile = OK")


if __name__ == "__main__":
    main()
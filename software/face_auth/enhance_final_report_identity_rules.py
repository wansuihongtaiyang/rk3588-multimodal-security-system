#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import time
from pathlib import Path


EMPLOYEE_NAME = {
    "employee_01": "员工一号（授权仓库工作人员）",
    "employee_02": "员工二号（授权仓库工作人员）",
}


def read_text(path, default=""):
    try:
        return Path(path).read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return default


def read_json(path):
    try:
        p = Path(path)
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        pass
    return {}


def short_text(s, max_len=1600):
    s = (s or "").strip()
    if len(s) <= max_len:
        return s
    return s[:max_len] + "\n……（已截断，完整内容见 event_ai_report.txt）"


def parse_face_status(event_dir):
    event_dir = Path(event_dir)

    txt = read_text(event_dir / "face_status.txt").strip()
    status = ""
    if txt.startswith("FACE_STATUS="):
        status = txt.split("=", 1)[1].strip()
    elif txt:
        status = txt.strip()

    face_json = read_json(event_dir / "face_auth_result.json")

    if not status:
        status = face_json.get("face_status") or face_json.get("FACE_STATUS") or "UNKNOWN"

    best_employee = (
        face_json.get("best_employee")
        or face_json.get("employee")
        or ""
    )

    second_employee = face_json.get("second_employee") or ""

    best_similarity = face_json.get("best_similarity", "")
    second_similarity = face_json.get("second_similarity", "")
    margin = face_json.get("margin", "")

    best_distance = face_json.get("best_distance", "")
    second_distance = face_json.get("second_distance", "")

    method = face_json.get("method", "SFace / FaceAuth")

    face_count = face_json.get("face_count", "")

    return {
        "status": status,
        "best_employee": best_employee,
        "best_employee_cn": EMPLOYEE_NAME.get(best_employee, best_employee or "无"),
        "second_employee": second_employee,
        "second_employee_cn": EMPLOYEE_NAME.get(second_employee, second_employee or "无"),
        "best_similarity": best_similarity,
        "second_similarity": second_similarity,
        "margin": margin,
        "best_distance": best_distance,
        "second_distance": second_distance,
        "method": method,
        "face_count": face_count,
        "raw": face_json,
    }


def parse_security(event_dir):
    event_dir = Path(event_dir)
    data = read_json(event_dir / "security_decision.json")

    txt = read_text(event_dir / "security_decision.txt")

    def from_txt(key, default=""):
        for line in txt.splitlines():
            if line.strip().startswith(key):
                return line.split(":", 1)[-1].strip()
        return default

    risk = data.get("risk_level") or data.get("risk") or from_txt("risk_level", "")
    action = data.get("alarm_action") or data.get("action") or from_txt("alarm_action", "")
    decision = data.get("final_decision") or data.get("decision") or from_txt("final_decision", "")
    score = data.get("score", "")

    reasons = data.get("reasons") or []
    if isinstance(reasons, str):
        reasons = [reasons]

    recommended = data.get("recommended_actions") or data.get("recommendations") or []
    if isinstance(recommended, str):
        recommended = [recommended]

    return {
        "risk": risk or "UNKNOWN",
        "action": action or "UNKNOWN",
        "decision": decision or "UNKNOWN",
        "score": score,
        "reasons": reasons,
        "recommended": recommended,
        "raw": data,
        "txt": txt,
    }


def identity_conclusion(face):
    status = face["status"]
    emp = face["best_employee"]
    emp_cn = face["best_employee_cn"]

    if status == "AUTHORIZED":
        return f"画面中人员已通过 SFace 白名单核验，匹配对象为 {emp_cn}，人员身份风险较低。"
    if status == "AMBIGUOUS_PERSON":
        return "画面中检测到人脸，但第一候选与第二候选差距不足，身份存在歧义，按身份无法确认处理。"
    if status == "UNKNOWN_PERSON":
        return "画面中检测到人脸，但未通过授权员工白名单匹配，按未知人员处理。"
    if status == "NO_FACE":
        return "本次图像未检测到可用于身份核验的人脸；若大模型判断画面中有人，则按人员身份无法确认处理。"
    return "本次人员身份状态未知，需要结合图像分析和传感器状态进行判断。"


def risk_rule_table():
    return """| 评分因素 | 典型加权 / 处理方式 | 风险含义 |
|---|---:|---|
| 授权员工 AUTHORIZED | 不增加人员风险，必要时降低人员风险 | 白名单员工，通常为 LOW / RECORD_ONLY |
| 未知人员 UNKNOWN_PERSON | 高权重，通常直接进入 HIGH | 非授权人员进入库房 |
| 身份歧义 AMBIGUOUS_PERSON | 高权重，按身份无法确认处理 | 第一候选与第二候选过近，不直接放行 |
| 有人但未检测到人脸 | 高权重，通常 HIGH | 画面有人但身份无法确认 |
| 运动异常 MOTION_SHAKING / MOVING | 中高权重，约 +25 到 +45 | 可能存在搬动、撞击、入侵或设备扰动 |
| 疑似破坏 / 强运动 TAMPER | 高权重，约 +70 | 可能存在设备破坏或强烈异常 |
| 白天光照异常 LIGHT_DARK | 低到中权重，约 +10 | 可能存在遮挡、关灯或环境变化 |
| 夜间单纯低光 | 降权，约 +0 到 +5 | 夜间低光属于常见环境，不单独高风险 |
| 夜间低光 + 人员 / 运动 | 叠加加权 | 夜间出现人员或运动异常更可疑 |
| 传感器离线 | 中等权重，约 +15 到 +30 | 设备状态异常，需要维护或人工确认 |
| 告警关闭 alarm_enabled=0 | 不改变风险事实，只改变告警动作 | 高风险仍记录，但动作降级为静默记录 |"""


def risk_level_table():
    return """| 总分区间 / 强规则 | 风险等级 | 告警动作 |
|---:|---|---|
| score < 30 | LOW | RECORD_ONLY，仅记录 |
| 30 <= score < 60 | MEDIUM | LOCAL_WARNING，本地提示 / 人工确认 |
| score >= 60 | HIGH | REMOTE_ALERT，远程告警 |
| 未知人员 / 身份无法确认 / 有人但无脸 | 强制 HIGH | REMOTE_ALERT |
| 告警关闭时 | 风险等级保留 | ALARM_DISABLED_RECORD_ONLY |"""


def build_report(event_dir):
    event_dir = Path(event_dir)
    now = time.strftime("%Y-%m-%d %H:%M:%S")

    old_report_path = event_dir / "final_display_report.txt"
    old_report = read_text(old_report_path)

    if old_report and "===== 原始报告备份 =====" not in old_report:
        backup = event_dir / "final_display_report_before_identity_rules.txt"
        if not backup.exists():
            backup.write_text(old_report, encoding="utf-8")

    face = parse_face_status(event_dir)
    sec = parse_security(event_dir)
    event_json = read_json(event_dir / "event.json")
    voice_json = read_json(event_dir / "voice_command.json")
    ai_report = read_text(event_dir / "event_ai_report.txt")

    trigger_type = voice_json.get("trigger_type", "")
    selected_event = voice_json.get("selected_event", "")
    voice_text = voice_json.get("voice_text", "")

    runtime = voice_json.get("runtime_state_snapshot", {}) if isinstance(voice_json, dict) else {}

    risk = sec["risk"]
    action = sec["action"]
    decision = sec["decision"]
    score = sec["score"]

    one_line = identity_conclusion(face)

    reasons = sec["reasons"]
    if not reasons:
        reasons = ["当前报告未读取到 security_decision.json 中的详细 reasons，风险等级以 security_decision.txt / final_decision 为准。"]

    recommended = sec["recommended"]
    if not recommended:
        recommended = ["根据风险等级执行记录、人工确认或远程告警；高风险事件建议保留完整图像证据。"]

    face_lines = [
        f"FaceAuth 状态：{face['status']}",
        f"识别方法：{face['method']}",
        f"检测到人脸数：{face['face_count']}",
        f"最佳匹配对象：{face['best_employee_cn']}",
    ]

    if face["best_similarity"] != "":
        face_lines.append(f"最佳相似度：{face['best_similarity']}")
    if face["best_distance"] != "":
        face_lines.append(f"兼容距离值：{face['best_distance']}")
    if face["second_employee"]:
        face_lines.append(f"第二候选对象：{face['second_employee_cn']}")
    if face["second_similarity"] != "":
        face_lines.append(f"第二候选相似度：{face['second_similarity']}")
    if face["margin"] != "":
        face_lines.append(f"第一/第二候选差距 margin：{face['margin']}")

    report = f"""===== 智能库房安防最终展示报告 =====
报告时间：{now}
事件目录：{event_dir}

一、核心结论
风险等级：{risk}
告警动作：{action}
最终判断：{decision}
综合评分：{score if score != "" else "未提供"}
一句话结论：{one_line}

二、人员身份判断（SFace 白名单）
{chr(10).join(face_lines)}

身份解释：
- AUTHORIZED：检测到人脸，且与员工白名单匹配成功。
- UNKNOWN_PERSON：检测到人脸，但未达到授权阈值，按非授权人员或待确认人员处理。
- AMBIGUOUS_PERSON：第一候选与第二候选过近，身份不确定，按待确认人员处理。
- NO_FACE：未检测到可用于身份核验的人脸；若图像中有人，则按身份无法确认处理。

三、风险评分规则表
{risk_rule_table()}

四、风险等级划分表
{risk_level_table()}

五、本次决策依据
"""
    for i, r in enumerate(reasons, 1):
        report += f"{i}. {r}\n"

    report += "\n六、建议处理动作\n"
    for i, r in enumerate(recommended, 1):
        report += f"{i}. {r}\n"

    report += f"""
七、触发与运行状态
触发来源：{trigger_type or "未记录"}
事件类型：{selected_event or event_json.get("decision", event_json.get("event_type", "未记录"))}
语音/事件文本：{voice_text or "未记录"}
检测模式：{runtime.get("mode", "未记录")}
自动抓拍：{runtime.get("auto_capture_enabled", "未记录")}
告警开关：{runtime.get("alarm_enabled", "未记录")}
夜间模式：{runtime.get("night_mode", "未记录")}

八、AI 图像分析摘要
{short_text(ai_report)}

===== 原始报告备份 =====
{old_report if old_report else "无原始 final_display_report.txt"}
"""

    result = {
        "timestamp": now,
        "event_dir": str(event_dir),
        "risk_level": risk,
        "alarm_action": action,
        "final_decision": decision,
        "score": score,
        "identity": face,
        "identity_conclusion": one_line,
        "risk_rule_table": {
            "level_thresholds": {
                "LOW": "score < 30",
                "MEDIUM": "30 <= score < 60",
                "HIGH": "score >= 60 or forced high-risk rule",
            },
            "forced_high_rules": [
                "UNKNOWN_PERSON",
                "AMBIGUOUS_PERSON",
                "person detected but no recognizable face",
                "tamper or strong motion abnormal",
            ],
        },
        "display_report": report,
    }

    (event_dir / "final_display_report.txt").write_text(report, encoding="utf-8")
    (event_dir / "final_display_report.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print("Day33 enhanced final report")
    print("event_dir =", event_dir)
    print("txt =", event_dir / "final_display_report.txt")
    print("json =", event_dir / "final_display_report.json")
    print("risk =", risk)
    print("action =", action)
    print("decision =", decision)
    print("face_status =", face["status"])
    print("best_employee =", face["best_employee"])
    print("RESULT=OK")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--event-dir", required=True)
    args = ap.parse_args()
    build_report(args.event_dir)


if __name__ == "__main__":
    main()

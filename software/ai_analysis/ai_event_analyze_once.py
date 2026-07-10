import argparse
import json
import os
import signal
import select
import subprocess
import time
from datetime import datetime


QWEN_DIR = "/home/elf/ai_deploy/qwen2_vl"
QWEN_DEMO = "/home/elf/ai_deploy/qwen2_vl/demo"
QWEN_IMG_ENC = "/home/elf/ai_deploy/qwen2_vl/qwen2_vl_2b_vision_rk3588.rknn"
QWEN_LLM = "/home/elf/ai_deploy/qwen2_vl/Qwen2-VL-2B-Instruct.rkllm"

DEEPSEEK_DIR = "/home/elf/ai_deploy/deepseek"
DEEPSEEK_DEMO = "/home/elf/ai_deploy/deepseek/llm_demo"
DEEPSEEK_LLM = "/home/elf/ai_deploy/deepseek/DeepSeek-R1-Distill-Qwen-1.5B_W8A8_RK3588.rkllm"


def now_text():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def read_text(path, limit=12000):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read(limit)
    except Exception as e:
        return f"[read_error] {path}: {repr(e)}"


def read_json(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return json.load(f)
    except Exception as e:
        return {"_read_error": repr(e)}


def read_face_auth(event_dir):
    face_status_path = os.path.join(event_dir, "face_status.txt")
    face_json_path = os.path.join(event_dir, "face_auth_result.json")

    status = "UNKNOWN"
    raw_status = read_text(face_status_path, limit=1000)

    for line in raw_status.splitlines():
        line = line.strip()
        if line.startswith("FACE_STATUS="):
            status = line.split("=", 1)[1].strip()
            break

    data = read_json(face_json_path) if os.path.exists(face_json_path) else {}

    return {
        "face_status": status,
        "face_status_text": raw_status,
        "face_auth_result": data,
    }


def extract_first_robot_answer(text):
    """
    提取第一段 robot: 后面的回答。
    如果后面再次出现 user:，就截断。
    """
    if not text:
        return ""

    idx = text.find("robot:")
    if idx < 0:
        return text.strip()

    ans = text[idx + len("robot:"):]

    next_user = ans.find("\nuser:")
    if next_user >= 0:
        ans = ans[:next_user]

    ans = ans.replace("\x00", "").strip()
    return ans


def strip_think_block(text):
    """
    DeepSeek-R1 类模型可能输出 <think>...</think>。
    如果存在完整 </think>，则只保留之后的正式回答。
    如果只有 <think> 没有结束，说明回答不完整，原样返回给可用性检测。
    """
    if not text:
        return ""

    if "</think>" in text:
        return text.split("</think>", 1)[1].strip()

    return text.strip()


def run_interactive_demo(cmd, cwd, prompt, timeout_sec=180, idle_after_robot_sec=8):
    """
    启动交互式 RKLLM demo：
    1. 写入一条 prompt
    2. 保持 stdin 打开
    3. 读取输出
    4. 一旦 robot 后出现内容，并在一小段时间内无明显新增内容，就终止进程
    """
    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = os.path.join(cwd, "lib") + ":" + env.get("LD_LIBRARY_PATH", "")

    p = subprocess.Popen(
        cmd,
        cwd=cwd,
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        preexec_fn=os.setsid,
    )

    output_parts = []
    robot_seen_time = None
    last_output_time = time.time()

    try:
        p.stdin.write(prompt.rstrip() + "\n")
        p.stdin.flush()

        start = time.time()

        while True:
            if time.time() - start > timeout_sec:
                break

            ready, _, _ = select.select([p.stdout], [], [], 0.5)
            line = p.stdout.readline() if ready else ""

            if line:
                output_parts.append(line)
                last_output_time = time.time()

                joined = "".join(output_parts)
                answer = extract_first_robot_answer(joined)

                if "robot:" in joined and answer:
                    if robot_seen_time is None:
                        robot_seen_time = time.time()
                    elif time.time() - robot_seen_time >= idle_after_robot_sec:
                        break
            else:
                if p.poll() is not None:
                    break

                if robot_seen_time and time.time() - last_output_time > idle_after_robot_sec:
                    break

                time.sleep(0.1)

    finally:
        try:
            os.killpg(os.getpgid(p.pid), signal.SIGTERM)
            time.sleep(0.5)
            if p.poll() is None:
                os.killpg(os.getpgid(p.pid), signal.SIGKILL)
        except Exception:
            pass

    full_output = "".join(output_parts)
    answer = extract_first_robot_answer(full_output)

    return {
        "returncode": p.poll(),
        "full_output": full_output,
        "answer": answer,
    }


def qwen_analyze_image(image_path, timeout_sec=180):
    prompt = (
        "<image> 请用中文分析这张异常事件现场图片。"
        "请回答：1.画面中主要有什么；2.是否有人；"
        "3.是否有明显遮挡、昏暗、异常物体；"
        "4.这张图对库房安全有什么提示。"
    )

    cmd = [
        QWEN_DEMO,
        image_path,
        QWEN_IMG_ENC,
        QWEN_LLM,
        "192",
        "512",
    ]

    return run_interactive_demo(
        cmd=cmd,
        cwd=QWEN_DIR,
        prompt=prompt,
        timeout_sec=timeout_sec,
        idle_after_robot_sec=8,
    )


def deepseek_analyze_event(event_type, sensor_status, image_summary, face_info=None, timeout_sec=180):
    face_info = face_info or {}
    face_status = face_info.get("face_status", "UNKNOWN")
    face_auth_result = json.dumps(face_info.get("face_auth_result", {}), ensure_ascii=False, indent=2)

    prompt = f"""
请你作为库房安全巡检系统的分析模块，根据以下信息生成一份简洁的中文异常事件分析报告。

必须严格按以下格式输出，不要只输出思考过程：

风险等级：LOW / MEDIUM / HIGH 三选一

可能原因：
1.
2.
3.

处理建议：
1.
2.
3.

最终摘要：

要求：
1. 不要编造没有证据的事实。
2. 如果图像信息不足，要明确说明“不确定”。
3. 如果运动传感器离线，要把它作为系统可靠性风险写入建议。
4. 报告要简洁，适合直接显示在远程 Dashboard。
5. 如果人员状态为 AUTHORIZED，必须明确说明“画面中的人员为授权仓库工作人员，人员身份正常，不按外人闯入处理”。
6. 如果人员状态为 UNKNOWN_PERSON，必须明确说明“检测到未授权人员或无法匹配白名单，建议告警或人工确认”。
7. 如果人员状态为 NO_FACE，说明未检测到可识别人脸，不要编造身份。

事件类型：{event_type}

传感器状态：
{sensor_status}

Qwen2-VL 图像分析结果：
{image_summary}

FaceAuth 人脸白名单结果：
face_status = {face_status}
face_auth_result =
{face_auth_result}
""".strip()

    cmd = [
        DEEPSEEK_DEMO,
        DEEPSEEK_LLM,
        "320",
        "512",
    ]

    return run_interactive_demo(
        cmd=cmd,
        cwd=DEEPSEEK_DIR,
        prompt=prompt,
        timeout_sec=timeout_sec,
        idle_after_robot_sec=10,
    )




def infer_risk_level(event_type, sensor_status, image_summary, face_status="UNKNOWN"):
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


def make_stable_report(event_type, sensor_status, image_summary, face_info=None):
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


def is_deepseek_report_usable(text):
    if not text:
        return False

    clean = strip_think_block(text)

    must_have = ["风险等级", "可能原因", "处理建议"]
    if all(k in clean for k in must_have):
        return True

    return False




def build_final_report(deepseek_answer, event_type, sensor_status, image_summary, face_info=None):
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


def main():
    parser = argparse.ArgumentParser(description="Analyze one abnormal event using Qwen2-VL and DeepSeek")
    parser.add_argument("--event-dir", required=True)
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()

    event_dir = os.path.abspath(os.path.expanduser(args.event_dir))

    if not os.path.isdir(event_dir):
        raise SystemExit(f"event dir not found: {event_dir}")

    event_json_path = os.path.join(event_dir, "event.json")
    sensor_status_path = os.path.join(event_dir, "sensor_status.txt")
    image_path = os.path.join(event_dir, "camera_input.jpg")
    face_info = read_face_auth(event_dir)

    event_data = read_json(event_json_path)
    sensor_status = read_text(sensor_status_path)

    event_type = (
        event_data.get("event_type")
        or event_data.get("decision")
        or os.path.basename(event_dir)
    )

    if not os.path.exists(image_path):
        raise SystemExit(f"image not found: {image_path}")

    print("==================================================")
    print("Day29 AI event analysis")
    print("==================================================")
    print("event_dir =", event_dir)
    print("event_type =", event_type)
    print("image =", image_path)
    print("face_status =", face_info.get("face_status"))
    print("==================================================")

    print("\n[1/2] Qwen2-VL analyzing image...")
    qwen_result = qwen_analyze_image(image_path, timeout_sec=args.timeout)
    image_summary = qwen_result["answer"]

    print("Qwen2-VL answer:")
    print(image_summary)

    print("\n[2/2] DeepSeek generating event report...")
    deepseek_result = deepseek_analyze_event(
        event_type=event_type,
        sensor_status=sensor_status,
        image_summary=image_summary,
        face_info=face_info,
        timeout_sec=args.timeout,
    )

    deepseek_answer = deepseek_result["answer"]

    final_report, report_source = build_final_report(
        deepseek_answer=deepseek_answer,
        event_type=event_type,
        sensor_status=sensor_status,
        image_summary=image_summary,
        face_info=face_info,
    )

    print("DeepSeek raw answer:")
    print(deepseek_answer)

    print("\nFinal report source:", report_source)
    print("Final report:")
    print(final_report)

    report = {
        "timestamp": now_text(),
        "event_dir": event_dir,
        "event_type": event_type,
        "image_path": image_path,
        "vision_model": "Qwen2-VL-2B-Instruct RKNN/RKLLM",
        "reasoning_model": "DeepSeek-R1-Distill-Qwen-1.5B RKLLM",
        "image_summary": image_summary,
        "face_info": face_info,
        "face_status": face_info.get("face_status"),
        "deepseek_raw_answer": deepseek_answer,
        "final_report": final_report,
        "report_source": report_source,
        "qwen_returncode": qwen_result["returncode"],
        "deepseek_returncode": deepseek_result["returncode"],
    }

    json_path = os.path.join(event_dir, "event_ai_report.json")
    txt_path = os.path.join(event_dir, "event_ai_report.txt")
    qwen_log_path = os.path.join(event_dir, "qwen2_vl_output.log")
    deepseek_log_path = os.path.join(event_dir, "deepseek_output.log")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("===== AI Event Report =====\n")
        f.write(f"timestamp: {report['timestamp']}\n")
        f.write(f"event_type: {event_type}\n")
        f.write(f"event_dir: {event_dir}\n")
        f.write(f"report_source: {report_source}\n")
        f.write(f"face_status: {face_info.get('face_status')}\n\n")

        f.write("===== Qwen2-VL Image Summary =====\n")
        f.write(image_summary + "\n\n")

        f.write("===== DeepSeek Raw Answer =====\n")
        f.write(deepseek_answer + "\n\n")

        f.write("===== Final Report =====\n")
        f.write(final_report + "\n")

    with open(qwen_log_path, "w", encoding="utf-8", errors="replace") as f:
        f.write(qwen_result["full_output"])

    with open(deepseek_log_path, "w", encoding="utf-8", errors="replace") as f:
        f.write(deepseek_result["full_output"])

    print("\nSaved:")
    print(json_path)
    print(txt_path)
    print(qwen_log_path)
    print(deepseek_log_path)

    print("RESULT=OK")


if __name__ == "__main__":
    main()
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import cv2
import time
import queue
import argparse
import threading
import subprocess
from datetime import datetime


MULTI_SCRIPT = "/home/elf/sensor_work/day14_multi_sensor/multi_sensor_check.py"


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def sensor_worker(q, interval):
    last = {
        "decision": "UNKNOWN",
        "raw": "not_started",
        "time": now(),
    }

    while True:
        cmd = [
            "sudo", "python3", MULTI_SCRIPT, "--plain",
            "--move-gyro", "25",
            "--shake-gyro", "80",
            "--move-accel-delta", "0.12",
            "--shake-accel-delta", "0.30",
        ]

        try:
            p = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=5,
            )

            if p.returncode == 0:
                raw = p.stdout.strip()
                decision = raw.split()[0] if raw else "EMPTY"
                last = {
                    "decision": decision,
                    "raw": raw,
                    "time": now(),
                }
            else:
                last = {
                    "decision": "SENSOR_ERROR",
                    "raw": p.stderr.strip(),
                    "time": now(),
                }

        except Exception as e:
            last = {
                "decision": "SENSOR_ERROR",
                "raw": repr(e),
                "time": now(),
            }

        while not q.empty():
            try:
                q.get_nowait()
            except queue.Empty:
                break

        q.put(last)
        time.sleep(interval)


def draw_overlay(frame, fps, sensor):
    decision = sensor.get("decision", "UNKNOWN")
    raw = sensor.get("raw", "")
    t = sensor.get("time", "")

    h, w = frame.shape[:2]

    abnormal = decision not in ["VISION_ALLOWED", "UNKNOWN"]

    if abnormal:
        cv2.rectangle(frame, (0, 0), (w - 1, h - 1), (0, 0, 255), 8)
        cv2.putText(frame, "WARNING", (30, 70),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.6, (0, 0, 255), 4)
    else:
        cv2.rectangle(frame, (0, 0), (w - 1, h - 1), (0, 255, 0), 3)

    cv2.putText(frame, f"FPS: {fps:.1f}", (20, h - 90),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)

    cv2.putText(frame, f"SENSOR: {decision}", (20, h - 55),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)

    short_raw = raw[:90]
    cv2.putText(frame, short_raw, (20, h - 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)

    cv2.putText(frame, t, (20, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)

    return frame


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dev", default="/dev/video0")
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--duration", type=float, default=60)
    parser.add_argument("--sensor-interval", type=float, default=0.5)
    parser.add_argument("--no-display", action="store_true")
    parser.add_argument("--save-last", default="/home/elf/project_evidence/day20_realtime_vision/last_realtime_frame.jpg")
    args = parser.parse_args()

    q = queue.Queue(maxsize=1)
    th = threading.Thread(target=sensor_worker, args=(q, args.sensor_interval), daemon=True)
    th.start()

    cap = cv2.VideoCapture(args.dev, cv2.CAP_V4L2)

    if not cap.isOpened():
        print(f"ERROR: cannot open camera {args.dev}")
        return 2

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
    cap.set(cv2.CAP_PROP_FPS, args.fps)

    frame_count = 0
    fps = 0.0
    t0 = time.time()
    last_sensor = {
        "decision": "UNKNOWN",
        "raw": "waiting_sensor",
        "time": now(),
    }

    print("==================================================")
    print("Realtime camera + sensor guard started")
    print("camera:", args.dev)
    print("size:", args.width, "x", args.height)
    print("target fps:", args.fps)
    print("duration:", args.duration)
    print("sensor interval:", args.sensor_interval)
    print("==================================================")

    start = time.time()

    while time.time() - start < args.duration:
        ok, frame = cap.read()
        if not ok:
            print("WARN: camera frame read failed")
            time.sleep(0.05)
            continue

        frame_count += 1
        now_t = time.time()

        if now_t - t0 >= 1.0:
            fps = frame_count / (now_t - t0)
            frame_count = 0
            t0 = now_t

        try:
            last_sensor = q.get_nowait()
        except queue.Empty:
            pass

        frame = draw_overlay(frame, fps, last_sensor)

        cv2.imwrite(args.save_last, frame)

        if not args.no_display:
            cv2.imshow("Day20 Realtime Camera Sensor Guard", frame)
            key = cv2.waitKey(1) & 0xFF
            if key == 27 or key == ord("q"):
                break

    cap.release()
    if not args.no_display:
        cv2.destroyAllWindows()

    print("Realtime camera + sensor guard finished.")
    print("last frame:", args.save_last)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
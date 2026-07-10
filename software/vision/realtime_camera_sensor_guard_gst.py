#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import cv2
import time
import queue
import argparse
import threading
import subprocess
import numpy as np
from datetime import datetime

import gi
gi.require_version("Gst", "1.0")
from gi.repository import Gst


MULTI_SCRIPT = "/home/elf/sensor_work/day14_multi_sensor/multi_sensor_check.py"


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def sensor_worker(q, interval):
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
                timeout=6,
            )

            if p.returncode == 0:
                raw = p.stdout.strip()
                decision = raw.split()[0] if raw else "EMPTY"
            else:
                raw = p.stderr.strip()
                decision = "SENSOR_ERROR"

        except Exception as e:
            raw = repr(e)
            decision = "SENSOR_ERROR"

        item = {
            "decision": decision,
            "raw": raw,
            "time": now(),
        }

        while not q.empty():
            try:
                q.get_nowait()
            except queue.Empty:
                break

        q.put(item)
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

    cv2.putText(frame, f"FPS: {fps:.1f}", (20, h - 95),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)

    cv2.putText(frame, f"SENSOR: {decision}", (20, h - 60),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)

    cv2.putText(frame, raw[:90], (20, h - 28),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)

    cv2.putText(frame, t, (20, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)

    return frame


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dev", default="/dev/video11")
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--duration", type=float, default=60)
    parser.add_argument("--sensor-interval", type=float, default=0.5)
    parser.add_argument("--no-display", action="store_true")
    parser.add_argument("--save-last", default="/home/elf/project_evidence/day20_realtime_vision/last_gst_realtime_frame.jpg")
    args = parser.parse_args()

    Gst.init(None)

    q = queue.Queue(maxsize=1)
    th = threading.Thread(target=sensor_worker, args=(q, args.sensor_interval), daemon=True)
    th.start()

    pipeline_desc = (
        f"v4l2src device={args.dev} ! "
        f"video/x-raw,format=NV12,width={args.width},height={args.height},framerate={args.fps}/1 ! "
        f"videoconvert ! "
        f"video/x-raw,format=BGR,width={args.width},height={args.height} ! "
        f"appsink name=sink emit-signals=false sync=false max-buffers=1 drop=true"
    )

    print("==================================================")
    print("Day20 realtime camera + sensor guard using GStreamer")
    print("pipeline:")
    print(pipeline_desc)
    print("duration:", args.duration)
    print("sensor interval:", args.sensor_interval)
    print("==================================================")

    pipeline = Gst.parse_launch(pipeline_desc)
    sink = pipeline.get_by_name("sink")

    pipeline.set_state(Gst.State.PLAYING)

    last_sensor = {
        "decision": "UNKNOWN",
        "raw": "waiting_sensor",
        "time": now(),
    }

    frame_count = 0
    fps_value = 0.0
    t0 = time.time()
    start = time.time()

    try:
        while time.time() - start < args.duration:
            sample = sink.emit("pull-sample")

            if sample is None:
                print("WARN: no sample")
                time.sleep(0.02)
                continue

            buf = sample.get_buffer()
            success, map_info = buf.map(Gst.MapFlags.READ)

            if not success:
                print("WARN: buffer map failed")
                continue

            try:
                arr = np.frombuffer(map_info.data, dtype=np.uint8)
                expected = args.width * args.height * 3

                if arr.size < expected:
                    print(f"WARN: frame size too small: {arr.size}")
                    continue

                frame = arr[:expected].reshape((args.height, args.width, 3)).copy()

            finally:
                buf.unmap(map_info)

            frame_count += 1
            now_t = time.time()

            if now_t - t0 >= 1.0:
                fps_value = frame_count / (now_t - t0)
                frame_count = 0
                t0 = now_t

            try:
                last_sensor = q.get_nowait()
            except queue.Empty:
                pass

            frame = draw_overlay(frame, fps_value, last_sensor)

            cv2.imwrite(args.save_last, frame)

            if not args.no_display:
                cv2.imshow("Day20 Realtime Camera Sensor Guard", frame)
                key = cv2.waitKey(1) & 0xFF
                if key == 27 or key == ord("q"):
                    break

    finally:
        pipeline.set_state(Gst.State.NULL)
        if not args.no_display:
            cv2.destroyAllWindows()

    print("Realtime GStreamer camera + sensor guard finished.")
    print("last frame:", args.save_last)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
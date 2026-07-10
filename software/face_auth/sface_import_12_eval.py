#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import csv
import json
import time
from pathlib import Path

import cv2
import numpy as np


DETECT_MODEL = "face_detection_yunet_2023mar.onnx"
RECOG_MODEL = "face_recognition_sface_2021dec.onnx"


def ensure_dir(p):
    Path(p).mkdir(parents=True, exist_ok=True)


def imread(path):
    img = cv2.imread(str(path))
    if img is None:
        raise RuntimeError(f"cannot read image: {path}")
    return img


def create_detector(model_path, score):
    return cv2.FaceDetectorYN_create(
        str(model_path),
        "",
        (320, 320),
        score_threshold=float(score),
        nms_threshold=0.3,
        top_k=5000,
    )


def create_recognizer(model_path):
    return cv2.FaceRecognizerSF_create(str(model_path), "")


def detect_faces(detector, img):
    h, w = img.shape[:2]
    detector.setInputSize((w, h))
    ok, faces = detector.detect(img)
    if faces is None:
        return []
    return faces


def largest_face(faces):
    if len(faces) == 0:
        return None
    best = None
    best_area = -1
    for f in faces:
        x, y, w, h = f[:4]
        area = float(w) * float(h)
        if area > best_area:
            best_area = area
            best = f
    return best


def normalize(feat):
    feat = feat.astype(np.float32).flatten()
    n = np.linalg.norm(feat)
    if n > 0:
        feat = feat / n
    return feat


def cosine(a, b):
    return float(np.dot(a, b))


def annotate(img, faces, status, out_path):
    out = img.copy()
    for f in faces:
        x, y, w, h = [int(v) for v in f[:4]]
        cv2.rectangle(out, (x, y), (x + w, y + h), (255, 255, 255), 2)
    cv2.putText(out, status, (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2)
    cv2.imwrite(str(out_path), out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="/home/elf/project_config/face_import")
    ap.add_argument("--model-dir", default="/home/elf/ai_deploy/face_sface")
    ap.add_argument("--out-dir", default="/home/elf/project_evidence/day33_face_recognition/sface/import_12_eval")
    ap.add_argument("--det-score", type=float, default=0.35)
    ap.add_argument("--threshold", type=float, default=0.363)
    ap.add_argument("--margin", type=float, default=0.02)
    args = ap.parse_args()

    root = Path(args.root).expanduser()
    model_dir = Path(args.model_dir).expanduser()
    out_dir = Path(args.out_dir).expanduser()
    crop_dir = out_dir / "crops"
    anno_dir = out_dir / "annotated"

    ensure_dir(out_dir)
    ensure_dir(crop_dir)
    ensure_dir(anno_dir)

    det_model = model_dir / DETECT_MODEL
    rec_model = model_dir / RECOG_MODEL

    if not det_model.exists():
        raise SystemExit(f"detector model not found: {det_model}")
    if not rec_model.exists():
        raise SystemExit(f"recognizer model not found: {rec_model}")

    detector = create_detector(det_model, args.det_score)
    recognizer = create_recognizer(rec_model)

    files = sorted([
        p for p in root.rglob("*")
        if p.suffix.lower() in [".jpg", ".jpeg", ".png"]
    ])

    print("=" * 60)
    print("SFace 12 image import evaluation")
    print("=" * 60)
    print("root =", root)
    print("model_dir =", model_dir)
    print("out_dir =", out_dir)
    print("det_score =", args.det_score)
    print("threshold =", args.threshold)
    print("margin =", args.margin)
    print("image_count =", len(files))
    print("=" * 60)

    items = []
    detect_rows = []

    for p in files:
        label = p.parent.name
        name = f"{label}_{p.stem}"
        try:
            img = imread(p)
            faces = detect_faces(detector, img)
            face = largest_face(faces)

            if face is None:
                annotate(img, [], "NO_FACE", anno_dir / f"{name}_NO_FACE.jpg")
                row = {
                    "label": label,
                    "image": str(p),
                    "detected": "NO",
                    "face_count": 0,
                    "crop": "",
                    "annotated": str(anno_dir / f"{name}_NO_FACE.jpg"),
                    "error": "",
                }
                detect_rows.append(row)
                print(f"NO_FACE label={label} image={p}")
                continue

            aligned = recognizer.alignCrop(img, face)
            feat = normalize(recognizer.feature(aligned))

            crop_path = crop_dir / f"{name}_crop.jpg"
            anno_path = anno_dir / f"{name}_OK.jpg"

            cv2.imwrite(str(crop_path), aligned)
            annotate(img, faces, "OK", anno_path)

            item = {
                "label": label,
                "image": str(p),
                "feature": feat,
                "crop": str(crop_path),
                "annotated": str(anno_path),
                "face_count": len(faces),
            }
            items.append(item)

            row = {
                "label": label,
                "image": str(p),
                "detected": "YES",
                "face_count": len(faces),
                "crop": str(crop_path),
                "annotated": str(anno_path),
                "error": "",
            }
            detect_rows.append(row)
            print(f"DETECTED label={label} face_count={len(faces)} image={p}")

        except Exception as e:
            row = {
                "label": label,
                "image": str(p),
                "detected": "ERROR",
                "face_count": 0,
                "crop": "",
                "annotated": "",
                "error": repr(e),
            }
            detect_rows.append(row)
            print(f"ERROR label={label} image={p} error={repr(e)}")

    detect_csv = out_dir / "sface_detection_summary.csv"
    with open(detect_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[
            "label", "image", "detected", "face_count", "crop", "annotated", "error"
        ])
        w.writeheader()
        w.writerows(detect_rows)

    pair_csv = out_dir / "sface_similarity_pairs.csv"
    with open(pair_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["query_label", "query_image", "target_label", "target_image", "similarity"])
        for q in items:
            for t in items:
                if q["image"] == t["image"]:
                    continue
                sim = cosine(q["feature"], t["feature"])
                w.writerow([q["label"], q["image"], t["label"], t["image"], f"{sim:.6f}"])

    eval_rows = []
    correct = 0
    wrong = 0
    ambiguous = 0
    unknown = 0

    for q in items:
        per_emp = {}
        per_emp_img = {}

        for t in items:
            if q["image"] == t["image"]:
                continue
            sim = cosine(q["feature"], t["feature"])
            emp = t["label"]
            if emp not in per_emp or sim > per_emp[emp]:
                per_emp[emp] = sim
                per_emp_img[emp] = t["image"]

        ranked = sorted(per_emp.items(), key=lambda x: x[1], reverse=True)

        if not ranked:
            best_emp = ""
            best_sim = -1.0
            second_emp = ""
            second_sim = -1.0
            margin_val = -1.0
            status = "NO_GALLERY"
        else:
            best_emp, best_sim = ranked[0]
            if len(ranked) >= 2:
                second_emp, second_sim = ranked[1]
                margin_val = best_sim - second_sim
            else:
                second_emp, second_sim = "", -1.0
                margin_val = best_sim

            if best_sim >= args.threshold and margin_val >= args.margin:
                status = "AUTHORIZED"
            elif best_sim >= args.threshold and margin_val < args.margin:
                status = "AMBIGUOUS_PERSON"
            else:
                status = "UNKNOWN_PERSON"

        is_correct = (status == "AUTHORIZED" and best_emp == q["label"])

        if is_correct:
            correct += 1
        elif status == "AMBIGUOUS_PERSON":
            ambiguous += 1
        elif status == "UNKNOWN_PERSON":
            unknown += 1
        else:
            wrong += 1

        eval_rows.append({
            "query_label": q["label"],
            "query_image": q["image"],
            "face_count": q["face_count"],
            "pred_status": status,
            "best_employee": best_emp,
            "best_similarity": f"{best_sim:.6f}",
            "second_employee": second_emp,
            "second_similarity": f"{second_sim:.6f}",
            "margin": f"{margin_val:.6f}",
            "correct": "YES" if is_correct else "NO",
        })

    eval_csv = out_dir / "sface_leave_one_out_eval.csv"
    with open(eval_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[
            "query_label", "query_image", "face_count",
            "pred_status", "best_employee", "best_similarity",
            "second_employee", "second_similarity", "margin", "correct"
        ])
        w.writeheader()
        w.writerows(eval_rows)

    total = len(files)
    detected = len(items)
    no_face = sum(1 for r in detect_rows if r["detected"] == "NO")
    errors = sum(1 for r in detect_rows if r["detected"] == "ERROR")

    summary = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "root": str(root),
        "image_count": total,
        "detected_count": detected,
        "no_face_count": no_face,
        "error_count": errors,
        "threshold": args.threshold,
        "margin": args.margin,
        "correct_authorized": correct,
        "wrong": wrong,
        "ambiguous": ambiguous,
        "unknown": unknown,
        "detection_csv": str(detect_csv),
        "eval_csv": str(eval_csv),
        "pair_csv": str(pair_csv),
    }

    summary_json = out_dir / "sface_import_12_summary.json"
    summary_txt = out_dir / "sface_import_12_summary.txt"

    summary_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = []
    lines.append("===== SFace 12 Image Evaluation Summary =====")
    lines.append(f"time: {summary['timestamp']}")
    lines.append(f"total images: {total}")
    lines.append(f"detected: {detected}")
    lines.append(f"no_face: {no_face}")
    lines.append(f"errors: {errors}")
    lines.append(f"threshold: {args.threshold}")
    lines.append(f"margin: {args.margin}")
    lines.append(f"correct_authorized: {correct}")
    lines.append(f"wrong: {wrong}")
    lines.append(f"ambiguous: {ambiguous}")
    lines.append(f"unknown: {unknown}")
    lines.append("")
    lines.append("Files:")
    lines.append(f"detection_csv: {detect_csv}")
    lines.append(f"eval_csv: {eval_csv}")
    lines.append(f"pair_csv: {pair_csv}")
    lines.append(f"summary_json: {summary_json}")

    if no_face > 0:
        lines.append("")
        lines.append("NO_FACE images:")
        for r in detect_rows:
            if r["detected"] == "NO":
                lines.append(f"- {r['image']}")

    if wrong > 0 or ambiguous > 0 or unknown > 0:
        lines.append("")
        lines.append("Need attention:")
        for r in eval_rows:
            if r["correct"] != "YES":
                lines.append(
                    f"- {r['query_image']} => {r['pred_status']} "
                    f"best={r['best_employee']} sim={r['best_similarity']} "
                    f"second={r['second_employee']} sim={r['second_similarity']} "
                    f"margin={r['margin']}"
                )

    summary_txt.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print()
    print("\n".join(lines))
    print()
    print("SUMMARY_TXT=", summary_txt)
    print("RESULT=OK")


if __name__ == "__main__":
    main()

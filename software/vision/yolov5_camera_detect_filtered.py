import os
import argparse
import cv2
import numpy as np
from rknnlite.api import RKNNLite

from yolov5_camera_detect import (
    MODEL,
    DEFAULT_IMAGE,
    IMG_SIZE,
    ANCHORS,
    STRIDES,
    COCO_CLASSES,
    decode_yolov5_output,
    nms_classwise,
    draw_detections,
)


DEFAULT_OUT = "/home/elf/camera_yolo_work/camera_yolo_result_filtered.jpg"

DEFAULT_CLASSES = "person,bottle,cell phone,cup,laptop,mouse,keyboard,book,chair"


def parse_class_filter(class_text):
    if class_text is None:
        return None

    class_text = class_text.strip()

    if class_text.lower() == "all":
        return None

    result = set()
    for item in class_text.split(","):
        name = item.strip()
        if name:
            result.add(name)

    return result


def filter_by_classes(boxes, scores, class_ids, allowed_classes):
    if allowed_classes is None:
        return boxes, scores, class_ids

    keep = []

    for i, cls_id in enumerate(class_ids):
        if 0 <= cls_id < len(COCO_CLASSES):
            name = COCO_CLASSES[cls_id]
        else:
            name = str(cls_id)

        if name in allowed_classes:
            keep.append(i)

    if not keep:
        return (
            np.zeros((0, 4), dtype=np.float32),
            np.zeros((0,), dtype=np.float32),
            np.zeros((0,), dtype=np.int32),
        )

    keep = np.array(keep, dtype=np.int32)
    return boxes[keep], scores[keep], class_ids[keep]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default=DEFAULT_IMAGE, help="input image path")
    parser.add_argument("--out", default=DEFAULT_OUT, help="output image path")
    parser.add_argument("--conf", type=float, default=0.15, help="confidence threshold")
    parser.add_argument("--iou", type=float, default=0.45, help="NMS IoU threshold")
    parser.add_argument(
        "--classes",
        default=DEFAULT_CLASSES,
        help='comma-separated class names, or "all"',
    )
    args = parser.parse_args()

    allowed_classes = parse_class_filter(args.classes)

    print("MODEL =", MODEL)
    print("IMAGE =", args.image)
    print("OUT   =", args.out)
    print("CONF  =", args.conf)
    print("IOU   =", args.iou)
    print("CLASS FILTER =", "all" if allowed_classes is None else sorted(allowed_classes))

    if not os.path.exists(MODEL):
        raise FileNotFoundError(f"RKNN model not found: {MODEL}")

    if not os.path.exists(args.image):
        raise FileNotFoundError(f"Input image not found: {args.image}")

    original = cv2.imread(args.image)
    if original is None:
        raise RuntimeError("cv2.imread failed")

    orig_h, orig_w = original.shape[:2]
    print("original shape =", original.shape)

    img = cv2.resize(original, (IMG_SIZE, IMG_SIZE))
    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    model_input = np.expand_dims(img_rgb, axis=0)

    print("model input shape =", model_input.shape)
    print("model input dtype =", model_input.dtype)

    rknn = RKNNLite()

    try:
        ret = rknn.load_rknn(MODEL)
        print("load_rknn ret =", ret)
        if ret != 0:
            raise RuntimeError("load_rknn failed")

        ret = rknn.init_runtime()
        print("init_runtime ret =", ret)
        if ret != 0:
            raise RuntimeError("init_runtime failed")

        outputs = rknn.inference(inputs=[model_input])
        if outputs is None:
            raise RuntimeError("rknn.inference returned None")

        print("inference ok, outputs len =", len(outputs))

        all_boxes = []
        all_scores = []
        all_class_ids = []

        for i, output in enumerate(outputs):
            output = np.array(output)
            print(f"output[{i}] shape =", output.shape)

            boxes, scores, class_ids = decode_yolov5_output(
                output,
                ANCHORS[i],
                STRIDES[i],
                args.conf,
            )

            if boxes.shape[0] > 0:
                all_boxes.append(boxes)
                all_scores.append(scores)
                all_class_ids.append(class_ids)

        if len(all_boxes) == 0:
            print("No detections before class filter.")
            cv2.imwrite(args.out, original)
            print("Saved original image to:", args.out)
            return

        boxes = np.concatenate(all_boxes, axis=0)
        scores = np.concatenate(all_scores, axis=0)
        class_ids = np.concatenate(all_class_ids, axis=0)

        print("detections before class filter =", len(boxes))

        boxes, scores, class_ids = filter_by_classes(
            boxes,
            scores,
            class_ids,
            allowed_classes,
        )

        print("detections after class filter =", len(boxes))

        if len(boxes) == 0:
            print("No target-class detections.")
            cv2.imwrite(args.out, original)
            print("Saved original image to:", args.out)
            return

        keep = nms_classwise(boxes, scores, class_ids, args.iou)

        boxes = boxes[keep]
        scores = scores[keep]
        class_ids = class_ids[keep]

        print("detections after NMS =", len(boxes))

        scale_x = orig_w / float(IMG_SIZE)
        scale_y = orig_h / float(IMG_SIZE)

        boxes[:, [0, 2]] *= scale_x
        boxes[:, [1, 3]] *= scale_y

        boxes[:, [0, 2]] = np.clip(boxes[:, [0, 2]], 0, orig_w - 1)
        boxes[:, [1, 3]] = np.clip(boxes[:, [1, 3]], 0, orig_h - 1)

        for box, score, cls_id in zip(boxes, scores, class_ids):
            name = COCO_CLASSES[cls_id] if 0 <= cls_id < len(COCO_CLASSES) else str(cls_id)
            print(f"detect: {name:15s} score={score:.3f} box={box.astype(int).tolist()}")

        result = draw_detections(original, boxes, scores, class_ids)
        cv2.imwrite(args.out, result)

        print("filtered result saved to:", args.out)

    finally:
        rknn.release()
        print("rknn released")


if __name__ == "__main__":
    main()
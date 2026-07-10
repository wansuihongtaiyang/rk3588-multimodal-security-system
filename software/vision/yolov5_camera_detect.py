import os
import argparse
import cv2
import numpy as np
from rknnlite.api import RKNNLite


MODEL = "/usr/bin/rknpu2_examples/rknn_yolov5_demo/model/RK3588/yolov5s-640-640.rknn"
DEFAULT_IMAGE = "/home/elf/camera_yolo_work/camera_input.jpg"
DEFAULT_OUT = "/home/elf/camera_yolo_work/camera_yolo_result.jpg"

IMG_SIZE = 640

ANCHORS = [
    np.array([[10, 13], [16, 30], [33, 23]], dtype=np.float32),
    np.array([[30, 61], [62, 45], [59, 119]], dtype=np.float32),
    np.array([[116, 90], [156, 198], [373, 326]], dtype=np.float32),
]

STRIDES = [8, 16, 32]

COCO_CLASSES = [
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck",
    "boat", "traffic light", "fire hydrant", "stop sign", "parking meter", "bench",
    "bird", "cat", "dog", "horse", "sheep", "cow", "elephant", "bear", "zebra",
    "giraffe", "backpack", "umbrella", "handbag", "tie", "suitcase", "frisbee",
    "skis", "snowboard", "sports ball", "kite", "baseball bat", "baseball glove",
    "skateboard", "surfboard", "tennis racket", "bottle", "wine glass", "cup",
    "fork", "knife", "spoon", "bowl", "banana", "apple", "sandwich", "orange",
    "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair", "couch",
    "potted plant", "bed", "dining table", "toilet", "tv", "laptop", "mouse",
    "remote", "keyboard", "cell phone", "microwave", "oven", "toaster", "sink",
    "refrigerator", "book", "clock", "vase", "scissors", "teddy bear", "hair drier",
    "toothbrush"
]


def sigmoid(x):
    x = np.clip(x, -50, 50)
    return 1.0 / (1.0 + np.exp(-x))


def box_iou(box, boxes):
    x1 = np.maximum(box[0], boxes[:, 0])
    y1 = np.maximum(box[1], boxes[:, 1])
    x2 = np.minimum(box[2], boxes[:, 2])
    y2 = np.minimum(box[3], boxes[:, 3])

    inter_w = np.maximum(0.0, x2 - x1)
    inter_h = np.maximum(0.0, y2 - y1)
    inter = inter_w * inter_h

    area1 = np.maximum(0.0, box[2] - box[0]) * np.maximum(0.0, box[3] - box[1])
    area2 = np.maximum(0.0, boxes[:, 2] - boxes[:, 0]) * np.maximum(0.0, boxes[:, 3] - boxes[:, 1])

    union = area1 + area2 - inter + 1e-6
    return inter / union


def nms_classwise(boxes, scores, class_ids, iou_thresh):
    keep = []

    for cls in np.unique(class_ids):
        idxs = np.where(class_ids == cls)[0]
        cls_boxes = boxes[idxs]
        cls_scores = scores[idxs]

        order = np.argsort(-cls_scores)

        while order.size > 0:
            i = order[0]
            keep.append(idxs[i])

            if order.size == 1:
                break

            rest = order[1:]
            ious = box_iou(cls_boxes[i], cls_boxes[rest])
            order = rest[ious < iou_thresh]

    return keep


def decode_yolov5_output(output, anchors, stride, conf_thresh):
    """
    output shape: (1, 3, 85, H, W)
    return:
      boxes: [N, 4], xyxy in 640x640 input scale
      scores: [N]
      class_ids: [N]
    """
    pred = output[0]  # (3, 85, H, W)
    pred = np.transpose(pred, (0, 2, 3, 1))  # (3, H, W, 85)

    num_anchor, grid_h, grid_w, _ = pred.shape

    grid_y, grid_x = np.meshgrid(np.arange(grid_h), np.arange(grid_w), indexing="ij")
    grid = np.stack((grid_x, grid_y), axis=-1).astype(np.float32)  # (H, W, 2)
    grid = np.expand_dims(grid, axis=0)  # (1, H, W, 2)

    anchors = anchors.reshape(num_anchor, 1, 1, 2)

    xy = (sigmoid(pred[..., 0:2]) * 2.0 - 0.5 + grid) * stride
    wh = (sigmoid(pred[..., 2:4]) * 2.0) ** 2 * anchors

    obj = sigmoid(pred[..., 4:5])
    cls_scores_all = sigmoid(pred[..., 5:])
    scores_all = obj * cls_scores_all

    class_ids = np.argmax(scores_all, axis=-1)
    scores = np.max(scores_all, axis=-1)

    mask = scores >= conf_thresh

    if not np.any(mask):
        return (
            np.zeros((0, 4), dtype=np.float32),
            np.zeros((0,), dtype=np.float32),
            np.zeros((0,), dtype=np.int32),
        )

    xy = xy[mask]
    wh = wh[mask]
    scores = scores[mask]
    class_ids = class_ids[mask].astype(np.int32)

    x1 = xy[:, 0] - wh[:, 0] / 2.0
    y1 = xy[:, 1] - wh[:, 1] / 2.0
    x2 = xy[:, 0] + wh[:, 0] / 2.0
    y2 = xy[:, 1] + wh[:, 1] / 2.0

    boxes = np.stack([x1, y1, x2, y2], axis=1)
    boxes = np.clip(boxes, 0, IMG_SIZE)

    return boxes, scores, class_ids


def draw_detections(img, boxes, scores, class_ids):
    out = img.copy()

    for box, score, cls_id in zip(boxes, scores, class_ids):
        x1, y1, x2, y2 = box.astype(int)

        label_name = COCO_CLASSES[cls_id] if 0 <= cls_id < len(COCO_CLASSES) else str(cls_id)
        label = f"{label_name} {score:.2f}"

        cv2.rectangle(out, (x1, y1), (x2, y2), (0, 255, 0), 2)

        text_y = max(20, y1 - 8)
        cv2.putText(
            out,
            label,
            (x1, text_y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 255, 0),
            2,
            cv2.LINE_AA,
        )

    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default=DEFAULT_IMAGE, help="input image path")
    parser.add_argument("--out", default=DEFAULT_OUT, help="output image path")
    parser.add_argument("--conf", type=float, default=0.15, help="confidence threshold")
    parser.add_argument("--iou", type=float, default=0.45, help="NMS IoU threshold")
    args = parser.parse_args()

    print("MODEL =", MODEL)
    print("IMAGE =", args.image)
    print("OUT   =", args.out)
    print("CONF  =", args.conf)
    print("IOU   =", args.iou)

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
            print(f"output[{i}] shape =", np.array(output).shape)
            boxes, scores, class_ids = decode_yolov5_output(
                np.array(output),
                ANCHORS[i],
                STRIDES[i],
                args.conf,
            )

            if boxes.shape[0] > 0:
                all_boxes.append(boxes)
                all_scores.append(scores)
                all_class_ids.append(class_ids)

        if len(all_boxes) == 0:
            print("No detections before NMS.")
            cv2.imwrite(args.out, original)
            print("Saved original image to:", args.out)
            return

        boxes = np.concatenate(all_boxes, axis=0)
        scores = np.concatenate(all_scores, axis=0)
        class_ids = np.concatenate(all_class_ids, axis=0)

        print("detections before NMS =", len(boxes))

        keep = nms_classwise(boxes, scores, class_ids, args.iou)

        boxes = boxes[keep]
        scores = scores[keep]
        class_ids = class_ids[keep]

        print("detections after NMS =", len(boxes))

        # 当前推理前采用的是直接 resize 到 640x640，因此这里按宽高比例映射回原图尺寸
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

        print("result saved to:", args.out)

    finally:
        rknn.release()
        print("rknn released")


if __name__ == "__main__":
    main()
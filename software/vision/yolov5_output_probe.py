import os
import cv2
import numpy as np
from rknnlite.api import RKNNLite


MODEL = "/usr/bin/rknpu2_examples/rknn_yolov5_demo/model/RK3588/yolov5s-640-640.rknn"
IMAGE = "/home/elf/camera_yolo_work/camera_input.jpg"


def main():
    print("MODEL =", MODEL)
    print("IMAGE =", IMAGE)

    if not os.path.exists(MODEL):
        raise FileNotFoundError(f"RKNN model not found: {MODEL}")

    if not os.path.exists(IMAGE):
        raise FileNotFoundError(f"Input image not found: {IMAGE}")

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

        img = cv2.imread(IMAGE)
        if img is None:
            raise RuntimeError("cv2.imread failed")

        print("original image shape =", img.shape)

        img = cv2.resize(img, (640, 640))
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        # RKNNLite 需要 4 维输入: N,H,W,C
        img = np.expand_dims(img, axis=0)

        print("model input shape =", img.shape)
        print("model input dtype =", img.dtype)

        outputs = rknn.inference(inputs=[img])

        if outputs is None:
            raise RuntimeError("rknn.inference returned None")

        print("inference ok")
        print("outputs len =", len(outputs))

        for i, out in enumerate(outputs):
            arr = np.array(out)
            print("=" * 60)
            print(f"output[{i}] shape =", arr.shape)
            print(f"output[{i}] dtype =", arr.dtype)
            print(f"output[{i}] min =", arr.min())
            print(f"output[{i}] max =", arr.max())
            print(f"output[{i}] mean =", arr.mean())
            print(f"output[{i}] first 20 values =", arr.flatten()[:20])

    finally:
        rknn.release()
        print("rknn released")


if __name__ == "__main__":
    main()
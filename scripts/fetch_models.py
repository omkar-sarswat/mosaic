"""Download the open face models into data/models/ (YuNet: MIT, SFace: Apache-2.0)."""

import sys
import urllib.request
from pathlib import Path

DEST = Path(__file__).resolve().parents[1] / "data" / "models"
MODELS = {
    "face_detection_yunet_2023mar.onnx": "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
    "face_recognition_sface_2021dec.onnx": "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx",
}


def main() -> int:
    DEST.mkdir(parents=True, exist_ok=True)
    for name, url in MODELS.items():
        path = DEST / name
        if path.exists() and path.stat().st_size > 100_000:
            print("present", name)
            continue
        print("fetching", name)
        urllib.request.urlretrieve(url, path)
    return 0


if __name__ == "__main__":
    sys.exit(main())

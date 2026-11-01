"""Face detection and matching for lawfully held images (retrospective, case-bound).

Models (OpenCV model zoo, run on CPU through OpenCV DNN):
  * YuNet  face_detection_yunet_2023mar.onnx    (MIT)       - detection + 5 landmarks
  * SFace  face_recognition_sface_2021dec.onnx  (Apache-2.0) - 128-d embedding, cosine match

Boundaries DRISHTI keeps (design doc red line 2; the 2026 Supreme Court petition on facial
recognition at protest sites):
  * no live video or public CCTV stream ingestion; only stills and images already held as
    evidence or as photographs on record (e.g. under the Criminal Procedure (Identification) Act 2022);
  * a search needs an open case, a stated reason, and is run for ONE selected face at a time,
    so a crowd photo cannot be turned into a list of identities in one action;
  * results are candidates with a similarity score, never an identification; a person must
    confirm or reject each candidate, and every step is in the audit chain.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import os

# A small file can declare an enormous image ("pixel bomb"); OpenCV's own ceiling is 1 gigapixel (~3 GB
# decoded). Set before cv2 is imported anywhere in the process.
os.environ.setdefault("OPENCV_IO_MAX_IMAGE_PIXELS", str(50_000_000))
MAX_IMAGE_BYTES = 15 * 1024 * 1024

import numpy as np  # noqa: E402

from ..config import ROOT

MODEL_DIR = Path(os.environ.get("DRISHTI_MODEL_DIR", ROOT / "data" / "models"))
DETECTOR = "face_detection_yunet_2023mar.onnx"
RECOGNIZER = "face_recognition_sface_2021dec.onnx"
# SFace cosine thresholds from the OpenCV model zoo: >= 0.363 means "same identity" on LFW.
MATCH_THRESHOLD = 0.363
STRONG_THRESHOLD = 0.50


@dataclass
class Face:
    box: tuple[float, float, float, float]  # x, y, w, h in original-image pixels
    landmarks: list[tuple[float, float]]
    score: float
    row: np.ndarray  # YuNet row (15 values) scaled to the original image, used for alignment

    def public(self) -> dict[str, Any]:
        return {"box": [round(v, 1) for v in self.box], "score": round(self.score, 3),
                "landmarks": [[round(x, 1), round(y, 1)] for x, y in self.landmarks]}


class FaceEngine:
    def __init__(self, model_dir: Path = MODEL_DIR):
        import cv2

        det, rec = model_dir / DETECTOR, model_dir / RECOGNIZER
        if not det.exists() or not rec.exists():
            raise FileNotFoundError(f"face models missing in {model_dir}; run scripts/fetch_models.py")
        self.cv2 = cv2
        self.detector = cv2.FaceDetectorYN.create(str(det), "", (320, 320), 0.7, 0.3, 5000)
        self.recognizer = cv2.FaceRecognizerSF.create(str(rec), "")

    @staticmethod
    def decode(data: bytes) -> np.ndarray:
        if len(data) > MAX_IMAGE_BYTES:
            raise ValueError(f"image larger than {MAX_IMAGE_BYTES // (1024 * 1024)} MB")
        import cv2

        try:
            img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        except cv2.error:  # e.g. more pixels than OPENCV_IO_MAX_IMAGE_PIXELS
            raise ValueError("not a readable image, or larger than 50 megapixels") from None
        if img is None:
            raise ValueError("not a readable image")
        return img

    def detect(self, img: np.ndarray, min_score: float = 0.7) -> list[Face]:
        """Multi-scale detection: YuNet anchors suit faces up to ~600 px, so large close-ups are
        found at a small scale and small faces in wide stills at a large one; results are merged."""
        h, w = img.shape[:2]
        found: list[Face] = []
        for side in (320, 640, 1280):
            s = min(1.0, side / max(h, w)) if side < max(h, w) else 1.0
            if side > max(h, w) and found:
                break
            im = self.cv2.resize(img, (max(1, int(w * s)), max(1, int(h * s)))) if s != 1.0 else img
            self.detector.setInputSize((im.shape[1], im.shape[0]))
            _, rows = self.detector.detect(im)
            for r in rows if rows is not None else []:
                if float(r[-1]) < min_score:
                    continue
                row = r.copy()
                row[:14] = row[:14] / s
                box = (float(row[0]), float(row[1]), float(row[2]), float(row[3]))
                if any(_iou(box, f.box) > 0.4 for f in found):
                    continue
                found.append(Face(box, [(float(row[4 + 2 * i]), float(row[5 + 2 * i])) for i in range(5)], float(row[-1]), row))
        return sorted(found, key=lambda f: -f.box[2] * f.box[3])

    def embed(self, img: np.ndarray, face: Face) -> np.ndarray:
        aligned = self.recognizer.alignCrop(img, face.row.astype(np.float32))
        v = self.recognizer.feature(aligned).astype(np.float32).ravel()
        return v / (np.linalg.norm(v) + 1e-9)

    @staticmethod
    def similarity(a: np.ndarray, b: np.ndarray) -> float:
        return float(np.dot(a, b) / ((np.linalg.norm(a) * np.linalg.norm(b)) + 1e-9))

    def thumbnail(self, img: np.ndarray, face: Face | None = None, size: int = 160) -> bytes:
        if face:
            x, y, w, h = face.box
            pad = 0.35
            x0, y0 = max(0, int(x - w * pad)), max(0, int(y - h * pad))
            x1, y1 = min(img.shape[1], int(x + w * (1 + pad))), min(img.shape[0], int(y + h * (1 + pad)))
            img = img[y0:y1, x0:x1]
        s = size / max(img.shape[:2])
        im = self.cv2.resize(img, (max(1, int(img.shape[1] * s)), max(1, int(img.shape[0] * s))))
        ok, buf = self.cv2.imencode(".jpg", im, [self.cv2.IMWRITE_JPEG_QUALITY, 85])
        return buf.tobytes()


def _iou(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    ax0, ay0, aw, ah = a
    bx0, by0, bw, bh = b
    ix = max(0.0, min(ax0 + aw, bx0 + bw) - max(ax0, bx0))
    iy = max(0.0, min(ay0 + ah, by0 + bh) - max(ay0, by0))
    inter = ix * iy
    return inter / (aw * ah + bw * bh - inter + 1e-9)


@lru_cache(maxsize=1)
def engine() -> FaceEngine:
    return FaceEngine()


def available() -> bool:
    return (MODEL_DIR / DETECTOR).exists() and (MODEL_DIR / RECOGNIZER).exists()

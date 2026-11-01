"""Build the synthetic portrait pool for the demo: faces of people who do not exist.

Each portrait comes from thispersondoesnotexist.com (StyleGAN2). A portrait is kept only if it shows
exactly one clear face; it is then sorted by apparent gender and age band so it can stand in for a
synthetic person of matching gender and age. Faces that look under 21 are discarded: the people they
stand in for are accused persons and suspects.

The age and gender model (ONNX Model Zoo age_googlenet / gender_googlenet, Levi and Hassner, Adience)
is used here only, offline, to sort these synthetic images. DRISHTI never runs it on case evidence or on
anyone's photograph.

usage: python scripts/fetch_portraits.py [count] [shard]    (writes data/samples/faces/portraits/)
A shard name writes its own manifest-<shard>.json, so two fetches can run side by side.
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from drishti.vision import faces as fv  # noqa: E402

OUT = ROOT / "data" / "samples" / "faces" / "portraits"
MODELS = ROOT / "data" / "models"
URL = "https://thispersondoesnotexist.com/random-person.jpeg?n={}"
AGES = ["0-2", "4-6", "8-12", "15-20", "25-32", "38-43", "48-53", "60-100"]
ADULT = {"25-32", "38-43", "48-53", "60-100"}


def crop(img: np.ndarray, box, margin: float = 0.4) -> np.ndarray:
    x, y, w, h = box
    cx, cy, s = x + w / 2, y + h / 2, max(w, h) * (1 + margin)
    return img[int(max(0, cy - s / 2)):int(min(img.shape[0], cy + s / 2)), int(max(0, cx - s / 2)):int(min(img.shape[1], cx + s / 2))]


def main(target: int, shard: str = "") -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    manifest_path = OUT / (f"manifest-{shard}.json" if shard else "manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else []
    seen = {m["sha256"] for f in OUT.glob("manifest*.json") for m in json.loads(f.read_text(encoding="utf-8"))}
    eng = fv.engine()
    gender_net = cv2.dnn.readNetFromONNX(str(MODELS / "gender_googlenet.onnx"))
    age_net = cv2.dnn.readNetFromONNX(str(MODELS / "age_googlenet.onnx"))
    tries, rejected = 0, {"faces": 0, "minor": 0, "unsure": 0, "duplicate": 0, "network": 0}
    while len(manifest) < target and tries < target * 3:
        tries += 1
        try:
            req = urllib.request.Request(URL.format(time.time_ns()), headers={"User-Agent": "Mozilla/5.0 (DRISHTI demo portrait pool)"})
            data = urllib.request.urlopen(req, timeout=20).read()
        except Exception:  # noqa: BLE001
            rejected["network"] += 1
            time.sleep(3)
            continue
        sha = hashlib.sha256(data).hexdigest()
        if sha in seen:
            rejected["duplicate"] += 1
            continue
        img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        found = eng.detect(img) if img is not None else []
        if len(found) != 1 or found[0].score < 0.9 or found[0].box[2] < img.shape[1] * 0.25:
            rejected["faces"] += 1
            continue
        blob = cv2.dnn.blobFromImage(crop(img, found[0].box), 1.0, (224, 224), (104, 117, 123), swapRB=False)
        gender_net.setInput(blob)
        gp = gender_net.forward()[0]
        age_net.setInput(blob)
        ap = age_net.forward()[0]
        age = AGES[int(np.argmax(ap))]
        if age not in ADULT:
            rejected["minor"] += 1
            continue
        if float(max(gp)) < 0.85:
            rejected["unsure"] += 1
            continue
        small = cv2.resize(img, (512, 512), interpolation=cv2.INTER_AREA)
        ok, buf = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 88])
        name = f"p_{sha[:12]}.jpg"
        (OUT / name).write_bytes(buf.tobytes())
        seen.add(sha)
        manifest.append({"file": name, "sha256": sha, "gender": "M" if gp[0] > gp[1] else "F", "gender_p": round(float(max(gp)), 3),
                         "age_band": age, "age_p": round(float(max(ap)), 3), "source": "thispersondoesnotexist.com (StyleGAN2)",
                         "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
        if len(manifest) % 20 == 0:
            manifest_path.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
            print(f"{len(manifest)} kept after {tries} tries; rejected {rejected}", flush=True)
        time.sleep(0.6)  # be gentle with the generator
    manifest_path.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(f"done: {len(manifest)} portraits; rejected {rejected}", flush=True)


MIDS = [1, 5, 10, 17.5, 28.5, 40.5, 50.5, 70]


def rescore(shard: str = "") -> None:
    """Add an expected apparent age (the age model's probabilities weighted by band midpoints) to each
    portrait, so people can be matched to faces by rank of age rather than by coarse band."""
    path = OUT / (f"manifest-{shard}.json" if shard else "manifest.json")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    eng = fv.engine()
    age_net = cv2.dnn.readNetFromONNX(str(MODELS / "age_googlenet.onnx"))
    for m in manifest:
        img = cv2.imread(str(OUT / m["file"]))
        found = eng.detect(img) if img is not None else []
        if not found:
            continue
        age_net.setInput(cv2.dnn.blobFromImage(crop(img, found[0].box), 1.0, (224, 224), (104, 117, 123), swapRB=False))
        p = age_net.forward()[0]
        p = p / p.sum()
        m["age_score"] = round(float(np.dot(p, MIDS)), 2)
    path.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(f"scored {sum('age_score' in m for m in manifest)} of {len(manifest)} in {path.name}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--rescore":
        rescore(sys.argv[2] if len(sys.argv) > 2 else "")
    else:
        main(int(sys.argv[1]) if len(sys.argv) > 1 else 480, sys.argv[2] if len(sys.argv) > 2 else "")

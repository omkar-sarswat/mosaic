"""Record a person's visual review of the portrait pool: portraits to leave out, with the reason.

usage: python scripts/review_portraits.py <reason> <ref> [<ref> ...]
A ref is a position in manifest.json ("12"), or in a shard's manifest ("b:12"), as printed on the
contact sheets (scripts/review_portraits.py sheet <shard> <start> <end>). The review is kept in
review.json next to the manifests; seed_portraits skips every excluded file.
"""
import json
import sys
from pathlib import Path

D = Path(__file__).resolve().parents[1] / "data" / "samples" / "faces" / "portraits"


def manifest(shard: str) -> list[dict]:
    return json.loads((D / (f"manifest-{shard}.json" if shard else "manifest.json")).read_text(encoding="utf-8"))


def sheet(shard: str, start: int, end: int) -> None:
    """A numbered contact sheet (10 per row) for the visual check, written to var/tmp."""
    import cv2
    import numpy as np

    tiles = []
    for i, e in enumerate(manifest(shard)[start:end], start):
        im = cv2.resize(cv2.imread(str(D / e["file"])), (150, 150))
        cv2.rectangle(im, (0, 0), (150, 22), (0, 0, 0), -1)
        cv2.putText(im, f"{shard + ':' if shard else ''}{i} {e['gender']} {e['age_band']}", (4, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
        tiles.append(im)
    while len(tiles) % 10:
        tiles.append(np.zeros((150, 150, 3), np.uint8))
    out = D.parents[3] / "var" / "tmp" / f"sheet_{shard or 'a'}_{start}.jpg"
    cv2.imwrite(str(out), np.vstack([np.hstack(tiles[i:i + 10]) for i in range(0, len(tiles), 10)]), [cv2.IMWRITE_JPEG_QUALITY, 80])
    print(out)


def exclude(reason: str, refs: list[str]) -> None:
    review_path = D / "review.json"
    review = json.loads(review_path.read_text(encoding="utf-8")) if review_path.exists() else {"excluded": {}}
    for ref in refs:
        shard, _, idx = ref.rpartition(":")
        review["excluded"][manifest(shard)[int(idx)]["file"]] = reason
    review_path.write_text(json.dumps(review, indent=1, sort_keys=True), encoding="utf-8")
    print(f"{len(review['excluded'])} portraits excluded in total")


if __name__ == "__main__":
    if sys.argv[1] == "sheet":
        sheet("" if sys.argv[2] in ("a", "") else sys.argv[2], int(sys.argv[3]), int(sys.argv[4]))
    else:
        exclude(sys.argv[1], sys.argv[2:])

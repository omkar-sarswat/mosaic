"""Photographs on record, the synthetic demo gallery, and synthetic portraits.

Photographs are stored content-addressed next to the database (var/media/<sha[:2]>/<sha>) and
each has the source and the legal basis for holding it. Only people already in an
investigation's record get a photograph here; there is no bulk import of ID-document photos.
The demo portraits follow the same rule: one synthetic face per person named in a case record or
ranked in a case's network, and nobody else.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
from pathlib import Path
from typing import Any

import numpy as np

from ..store import Store, utcnow
from . import faces as fv


def media_root(store: Store) -> Path:
    root = Path(os.environ.get("DRISHTI_MEDIA_DIR", store.path.parent / "media"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def enrol_photo(store: Store, object_id: str, data: bytes, *, source: str, legal_basis: str, actor: str,
                case_id: str | None = None) -> dict[str, Any]:
    """Store a photograph of a person and index its largest face."""
    eng = fv.engine()
    img = eng.decode(data)
    found = eng.detect(img)
    if not found:
        raise ValueError("no face found in the photograph")
    sha = hashlib.sha256(data).hexdigest()
    path = media_root(store) / sha[:2] / sha
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(data)
    mid, fid = "media:" + secrets.token_hex(8), "face:" + secrets.token_hex(8)
    with store.tx() as conn:
        conn.execute("INSERT INTO media(id,object_id,case_id,kind,sha256,path,mime,width,height,source,legal_basis,added_by,added_at) "
                     "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (mid, object_id, case_id, "photo", sha, str(path), "image", img.shape[1], img.shape[0], source, legal_basis, actor, utcnow()))
        conn.execute("INSERT INTO faces(id,media_id,object_id,idx,box,score,embedding,role) VALUES(?,?,?,?,?,?,?,?)",
                     (fid, mid, object_id, 0, json.dumps(found[0].public()["box"]), found[0].score, eng.embed(img, found[0]).tobytes(), "gallery"))
    return {"media_id": mid, "face_id": fid, "score": round(found[0].score, 3), "faces_in_image": len(found)}


# ---------------------------------------------------------------------------- demo data

# (operation, truth key, index or None, sample file, source, legal basis)
DEMO_PHOTOS = [
    ("MIRAGE", "kingpin", None, "synthetic_face_a.png", "KYC photograph in bank reply", "PMLA s.50 summons to bank, ECIR/MBZO-II/31"),
    ("MIRAGE", "family", 0, "synthetic_face_b.jpg", "KYC photograph in bank reply", "PMLA s.50 summons to bank, ECIR/MBZO-II/31"),
    ("MIRAGE", "facilitator", None, "gallery/gan_01.jpg", "ICAI membership record", "PMLA s.50 summons to ICAI, ECIR/MBZO-II/31"),
    ("MIRAGE", "hawala", None, "gallery/gan_14.jpg", "Photograph seized in search", "Search u/s 17 PMLA, panchnama 4/2026"),
    ("MULE", "herder", None, "gallery/gan_02.jpg", "Measurements after arrest", "Criminal Procedure (Identification) Act 2022 s.3, FIR MH/NMB/CYB/0412"),
    ("SUNRISE", "promoter", None, "gallery/gan_12.jpg", "Passport photograph", "Requisition to MEA in CBI RC/BSFC/E/0007"),
    ("SUNRISE", "spouse", None, "gallery/gan_06.jpg", "Passport photograph", "Requisition to MEA in CBI RC/BSFC/E/0007"),
    ("KESTREL", "leader", None, "gallery/gan_07.jpg", "Photograph seized in search", "Search u/s 185 BNSS, NIA RC-04/MUM"),
    ("KESTREL", "operatives", 1, "gallery/gan_03.jpg", "Measurements after arrest", "Criminal Procedure (Identification) Act 2022 s.3, NIA RC-04/MUM"),
]
# Women on record in the same investigations (relatives, nominees, mules) so a search has
# realistic look-alikes to reject.
DEMO_DISTRACTORS = ["gallery/gan_04.jpg", "gallery/gan_05.jpg", "gallery/gan_09.jpg", "gallery/gan_13.jpg"]
NOT_ENROLLED = "gallery/gan_10.jpg"  # appears in a probe but is on no record

PROBES = {
    "probe_atm_cctv.jpg": ("CAM-03 ATM KIOSK  2026-09-14 23:41:07", ["synthetic_face_a.png"]),
    "probe_branch_two_faces.jpg": ("BRANCH CAM-1  2026-08-02 11:06:52", ["gallery/gan_02.jpg", NOT_ENROLLED]),
    "probe_seized_phone_group.jpg": ("IMG_20260611_184402.jpg (seized handset)", ["gallery/gan_07.jpg", "gallery/gan_03.jpg"]),
}


def _degrade(img: np.ndarray, width: int, rng: np.random.Generator, tilt: float) -> np.ndarray:
    import cv2

    h, w = img.shape[:2]
    im = cv2.resize(img, (width, int(h * width / w)), interpolation=cv2.INTER_AREA)
    m = cv2.getRotationMatrix2D((im.shape[1] / 2, im.shape[0] / 2), tilt, 1.0)
    im = cv2.warpAffine(im, m, (im.shape[1], im.shape[0]), borderMode=cv2.BORDER_REFLECT)
    im = cv2.GaussianBlur(im, (3, 3), 0)
    return np.clip(im.astype(np.float32) * 0.78 + 28 + rng.normal(0, 7, im.shape), 0, 255).astype(np.uint8)


def make_probe_stills(faces_dir: Path) -> list[Path]:
    """Compose low-quality 'CCTV' and 'seized phone' stills from the synthetic faces (deterministic)."""
    import cv2

    out_dir = faces_dir / "probes"
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for k, (name, (stamp, members)) in enumerate(PROBES.items()):
        path = out_dir / name
        paths.append(path)
        if path.exists():
            continue
        rng = np.random.default_rng(100 + k)
        scene = np.clip(rng.normal(62, 14, (720, 1280, 3)), 0, 255).astype(np.uint8)
        scene = cv2.GaussianBlur(scene, (9, 9), 0)
        cv2.rectangle(scene, (0, 600), (1280, 720), (48, 52, 56), -1)
        for i, rel in enumerate(members):
            face = _degrade(cv2.imread(str(faces_dir / rel)), 150 if len(members) > 1 else 170, rng, tilt=(-7, 6, -3)[i % 3])
            x, y = 330 + i * 360, 170 + (i % 2) * 40
            scene[y:y + face.shape[0], x:x + face.shape[1]] = face
        cv2.putText(scene, stamp, (18, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (235, 235, 235), 2)
        ok, buf = cv2.imencode(".jpg", scene, [cv2.IMWRITE_JPEG_QUALITY, 58])
        path.write_bytes(buf.tobytes())
    return paths


def seed_faces(store: Store, samples_dir: Path) -> dict[str, Any]:
    if not fv.available():
        return {"skipped": "face models not installed"}
    faces_dir = samples_dir / "faces"
    t = (store.get_meta("synthetic_truth") or {}).get("operations", {})
    if not t or not (faces_dir / "synthetic_face_a.png").exists():
        return {"skipped": "no synthetic world or sample faces"}
    enrolled = []
    for op, key, idx, rel, source, basis in DEMO_PHOTOS:
        oid = t[op][key] if idx is None else t[op][key][idx]
        enrol_photo(store, oid, (faces_dir / rel).read_bytes(), source=source, legal_basis=basis, actor="system:demo")
        enrolled.append(oid)
    pool = [*t["SUNRISE"].get("relatives", []), *t["MIRAGE"]["nominees"], *t["MULE"]["mules"]]
    women = [o for o in store.get_objects(set(pool)).values() if o["props"].get("gender") == "F" and o["id"] not in enrolled]
    women.sort(key=lambda o: o["id"])
    for o, rel in zip(women, DEMO_DISTRACTORS):
        enrol_photo(store, o["id"], (faces_dir / rel).read_bytes(), source="KYC photograph in bank reply",
                    legal_basis="Bank reply to notice in the same investigation", actor="system:demo")
        enrolled.append(o["id"])
    probes = make_probe_stills(faces_dir)
    store.set_meta("demo_faces", {"enrolled": enrolled, "probes": [p.name for p in probes]})
    return {"enrolled": len(enrolled), "probes": len(probes)}


# ---------------------------------------------------------------------------- demo portraits

PORTRAIT_ACTOR = "system:demo-portraits"
# a portrait's apparent age when its manifest entry has no age_score (scripts/fetch_portraits.py --rescore)
_BAND_MID = {"25-32": 28.5, "38-43": 40.5, "48-53": 50.5, "60-100": 70.0}


def _portrait_subjects(store: Store, ledger: Any = None) -> list[dict[str, Any]]:
    """People already in an investigation's record, each once as their resolved entity: everyone named
    as accused in a case record, everyone a case was opened on, and the people each case's network ranks.
    Nobody outside an investigation gets a photograph."""
    from ..analytics.money import Ledger
    from ..analytics.network import build_network, case_seeds, rank_suspects
    from ..resolve.service import entity_cluster

    ledger = ledger or Ledger(store)
    # priority: the people a case is about, then the accused, then each network's ranked suspects by score
    why: dict[str, dict[str, Any]] = {}
    for r in store.query("SELECT co.object_id, co.case_id FROM case_objects co JOIN objects o ON o.id=co.object_id WHERE o.type='Person' ORDER BY co.object_id"):
        why.setdefault(r["object_id"], {"reason": "case", "record": None, "case": r["case_id"], "rank": (0, 0.0)})
    accused_in: dict[str, str] = {}
    for r in store.query("SELECT l.src, o.title FROM links l JOIN objects o ON o.id=l.dst WHERE l.type='accused_in' ORDER BY l.src, o.title"):
        accused_in.setdefault(r["src"], r["title"])
        why.setdefault(r["src"], {"reason": "accused", "record": r["title"], "case": None, "rank": (1, 0.0)})
    for c in store.query("SELECT id FROM cases WHERE status='open' ORDER BY id"):
        seeds = case_seeds(store, c["id"])
        if not seeds:
            continue
        for s in rank_suspects(store, build_network(store, seeds, ledger), ledger):
            why.setdefault(s["id"], {"reason": "case", "record": None, "case": c["id"], "rank": (2, -float(s.get("score") or 0))})
    have = {r["object_id"] for r in store.query("SELECT object_id FROM media WHERE kind='photo' AND object_id IS NOT NULL")}
    out, done = [], set()
    for pid in sorted(why, key=lambda k: (why[k]["rank"], k)):
        cluster = entity_cluster(store, pid)
        if done & set(cluster) or have & set(cluster):
            done |= set(cluster)
            continue
        done |= set(cluster)
        objs = [o for o in store.get_objects(cluster).values() if o["type"] == "Person"]
        objs.sort(key=lambda o: (not (o["props"].get("dob") or o["props"].get("pan")), o["id"]))
        if objs:
            # anyone accused in a case record is photographed on arrest, whatever brought them here
            record = next((accused_in[x] for x in cluster if x in accused_in), None)
            out.append({"person": objs[0], **why[pid], **({"reason": "accused", "record": record} if record else {})})
    return out


def seed_portraits(store: Store, samples_dir: Path, ledger: Any = None, *, year: int = 2026, replace: bool = False) -> dict[str, Any]:
    """Give each person in an investigation's record a synthetic portrait of matching gender and apparent
    age, held with a source and legal basis like any photograph on record (and indexed for face search).
    Portraits are faces of people who do not exist (data/samples/faces/portraits, scripts/fetch_portraits.py)."""
    if not fv.available():
        return {"skipped": "face models not installed"}
    pdir = samples_dir / "faces" / "portraits"
    manifests = sorted(pdir.glob("manifest*.json"))
    if not manifests:
        return {"skipped": "no portrait pool (run scripts/fetch_portraits.py)"}
    if replace:  # take back earlier demo portraits (the image files stay, content-addressed)
        with store.tx() as conn:
            conn.execute("DELETE FROM faces WHERE media_id IN (SELECT id FROM media WHERE added_by=?)", (PORTRAIT_ACTOR,))
            conn.execute("DELETE FROM media WHERE added_by=?", (PORTRAIT_ACTOR,))
    pool = sorted((m for f in manifests for m in json.loads(f.read_text(encoding="utf-8"))), key=lambda m: m["file"])
    # a person's visual review (scripts/review_portraits.py) leaves out faces that look under 21,
    # headwear or sunglasses, and cut-off crops
    review = pdir / "review.json"
    excluded = json.loads(review.read_text(encoding="utf-8")).get("excluded", {}) if review.exists() else {}
    used = {r["sha256"] for r in store.query("SELECT sha256 FROM media")}
    free = []
    for m in pool:  # reviewed in, on disk, and not already someone's photograph
        f = pdir / m["file"]
        if m["file"] in excluded or not f.exists():
            continue
        data = f.read_bytes()
        if hashlib.sha256(data).hexdigest() not in used:
            free.append({**m, "data": data})
    subjects = _portrait_subjects(store, ledger)
    # Within each gender, when faces run short the priority order decides who gets one; those people are
    # then matched to faces by rank of age, the oldest person to the oldest-looking face, so a 60-year-old
    # is not given a 25-year-old's face because a coarse age band ran out.
    age_of = lambda s: year - int(s["person"]["props"].get("birth_year") or year - 35)  # noqa: E731
    looks = lambda m: (m.get("age_score", _BAND_MID.get(m["age_band"], 30.0)), m["file"])  # noqa: E731
    plan, unmatched = [], 0
    for gender in sorted({str(s["person"]["props"].get("gender")) for s in subjects}):
        subs = [s for s in subjects if str(s["person"]["props"].get("gender")) == gender]
        faces = sorted((m for m in free if m["gender"] == gender), key=looks)
        take = sorted(subs[:len(faces)], key=lambda s: (age_of(s), s["person"]["id"]))
        unmatched += len(subs) - len(take)
        n, k = len(take), len(faces)
        for i, s in enumerate(take):  # with k >= n the index rises by at least one each step: no face is used twice
            plan.append((s, faces[round(i * (k - 1) / (n - 1)) if n > 1 else k // 2]))
    enrolled = 0
    for s, face in plan:
        p = s["person"]["props"]
        if s["reason"] == "accused":
            source, basis = "Photograph on arrest record (CCTNS)", f"Criminal Procedure (Identification) Act 2022 s.3; {s['record']}"
        elif p.get("passport_no"):
            source, basis = "Passport photograph (Passport Seva)", f"Requisition to the Ministry of External Affairs in {s['case']}"
        else:
            source, basis = "KYC photograph in bank reply", f"Notice to the bank in {s['case']}"
        try:
            enrol_photo(store, s["person"]["id"], face["data"], source=source, legal_basis=basis, actor=PORTRAIT_ACTOR, case_id=s["case"])
            enrolled += 1
        except ValueError:
            unmatched += 1
    store.set_meta("demo_portraits", {"enrolled": enrolled, "subjects": len(subjects), "unmatched": unmatched, "pool": len(pool)})
    return {"enrolled": enrolled, "subjects": len(subjects), "unmatched": unmatched}

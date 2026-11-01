"""Face API: enrol lawfully held photographs, detect faces in evidence stills, search one face
at a time against the photographs on record, and have a second officer confirm or reject."""

from __future__ import annotations

import json
import secrets
from pathlib import Path
from typing import Any

import numpy as np
from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from ..evidence import custody_append, store_evidence
from ..store import utcnow
from ..vision import faces as fv
from ..vision.gallery import enrol_photo
from .deps import Ctx, get_ctx

router = APIRouter(prefix="/api/faces", tags=["faces"])


def _engine() -> fv.FaceEngine:
    if not fv.available():
        raise HTTPException(503, "face models are not installed (run scripts/fetch_models.py)")
    return fv.engine()


def _need_case(c: Ctx) -> None:
    if not c.case or c.case.status != "open" or c.user.id not in c.case.members:
        c.log("face:access", outcome="denied")
        raise HTTPException(403, "face work needs an open case you are a member of")


@router.get("/status")
def status(c: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    n = c.svc.store.query("SELECT COUNT(*) n FROM faces WHERE role='gallery'")[0]["n"]
    return {"available": fv.available(), "gallery_faces": n, "match_threshold": fv.MATCH_THRESHOLD, "strong_threshold": fv.STRONG_THRESHOLD,
            "models": ["YuNet 2023mar (MIT)", "SFace 2021dec (Apache-2.0)"],
            "policy": "Stills only; one face per search with a recorded reason; candidates need a second officer's confirmation."}


@router.post("/enrol")
async def enrol(object_id: str = Form(...), source: str = Form(...), legal_basis: str = Form(...), file: UploadFile = File(...),
                c: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    _need_case(c)
    c.require_role("io", "supervisor")
    obj = c.svc.store.get_object(object_id)
    if not obj or obj["type"] != "Person" or not c.decide(obj).allow:
        raise HTTPException(403, "person not visible in this case")
    if len(legal_basis.strip()) < 8:
        raise HTTPException(422, "state the legal basis for holding this photograph")
    _engine()
    try:
        r = enrol_photo(c.svc.store, object_id, await file.read(), source=source, legal_basis=legal_basis, actor=c.user.id, case_id=c.case.id)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    c.log("face:enrol", detail={"source": source, "legal_basis": legal_basis, "media": r["media_id"]}, object_ids=[object_id])
    return r


@router.get("/object/{oid:path}")
def photos_of(oid: str, c: Ctx = Depends(get_ctx)) -> list[dict[str, Any]]:
    obj = c.svc.store.get_object(oid)
    if not obj or not c.decide(obj).allow:
        raise HTTPException(403, "not visible")
    rows = c.svc.store.query("SELECT m.id, m.source, m.legal_basis, m.added_by, m.added_at, f.id face_id, f.score FROM media m LEFT JOIN faces f ON f.media_id=m.id AND f.role='gallery' WHERE m.object_id=? AND m.kind='photo' ORDER BY m.added_at", (oid,))
    return [dict(r) for r in rows]


@router.get("/portraits")
def portraits(ids: str = "", c: Ctx = Depends(get_ctx)) -> dict[str, str]:
    """For a list of people on screen, the first photograph on record of each (across the records resolved
    into the same person). Only people the caller may see; at most 60 per request."""
    from ..resolve.service import entity_cluster

    s, out = c.svc.store, {}
    wanted = [i for i in dict.fromkeys(ids.split(",")) if i.startswith("person:")][:60]
    objs = s.get_objects(wanted)
    for oid in wanted:
        obj = objs.get(oid)
        if not obj or not c.decide(obj).allow:
            continue
        cluster = entity_cluster(s, oid)
        marks = ",".join("?" * len(cluster))
        row = s.query(f"SELECT id FROM media WHERE kind='photo' AND object_id IN ({marks}) ORDER BY added_at LIMIT 1", cluster)
        if row:
            out[oid] = row[0]["id"]
    return out


@router.get("/media/{mid}")
def media(mid: str, thumb: int = 0, face: int | None = None, c: Ctx = Depends(get_ctx)) -> Response:
    rows = c.svc.store.query("SELECT * FROM media WHERE id=?", (mid,))
    if not rows:
        raise HTTPException(404)
    m = rows[0]
    if m["object_id"]:
        obj = c.svc.store.get_object(m["object_id"])
        if not obj or not c.decide(obj).allow:
            raise HTTPException(403, "not visible")
    elif not (c.case and m["case_id"] == c.case.id and c.user.id in c.case.members):
        raise HTTPException(403, "probe images are visible to members of their case")
    data = Path(m["path"]).read_bytes()
    if thumb or face is not None:
        eng = _engine()
        img = eng.decode(data)
        f = None
        if face is not None:
            fr = c.svc.store.query("SELECT box FROM faces WHERE media_id=? AND idx=?", (mid, face))
            if fr:
                x, y, w, h = json.loads(fr[0]["box"])
                f = fv.Face((x, y, w, h), [], 1.0, np.zeros(15, np.float32))
        data = eng.thumbnail(img, f, size=200 if face is not None else 480)
        return Response(data, media_type="image/jpeg")
    return Response(data, media_type="image/jpeg" if data[:3] == b"\xff\xd8\xff" else "image/png")


@router.post("/probe")
async def probe(file: UploadFile = File(...), description: str = Form(""), legal_order: str = Form(""), seized_from: str = Form(""),
                c: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    """Seal an evidence still in the locker and detect the faces in it (no identification yet)."""
    _need_case(c)
    c.require_role("io", "supervisor", "analyst")
    eng = _engine()
    data = await file.read()
    try:
        img = eng.decode(data)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    ev = store_evidence(c.svc.store, c.case.id, c.user.id, file.filename or "still.jpg", data,
                        {"mime": file.content_type, "description": description or "Image for face comparison", "source_type": "Other",
                         "legal_order": legal_order or None, "seized_from": seized_from or None})
    found = eng.detect(img)
    mid = "media:" + secrets.token_hex(8)
    with c.svc.store.tx() as conn:
        conn.execute("INSERT INTO media(id,object_id,case_id,kind,sha256,path,mime,width,height,source,legal_basis,evidence_id,added_by,added_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (mid, None, c.case.id, "probe", ev["sha256"], c.svc.store.query("SELECT storage_path FROM evidence WHERE id=?", (ev["id"],))[0]["storage_path"],
                      file.content_type, img.shape[1], img.shape[0], "evidence still", legal_order or None, ev["id"], c.user.id, utcnow()))
        out = []
        for i, f in enumerate(found):
            fid = "face:" + secrets.token_hex(8)
            conn.execute("INSERT INTO faces(id,media_id,object_id,idx,box,score,embedding,role) VALUES(?,?,?,?,?,?,?,?)",
                         (fid, mid, None, i, json.dumps(f.public()["box"]), f.score, eng.embed(img, f).tobytes(), "probe"))
            out.append({"face_id": fid, "index": i, **f.public()})
    custody_append(c.svc.store, ev["id"], c.user.id, "faces_detected", {"faces": len(out)})
    c.log("face:probe", detail={"evidence": ev["id"], "faces": len(out)})
    return {"media_id": mid, "evidence_id": ev["id"], "sha256": ev["sha256"], "width": img.shape[1], "height": img.shape[0], "faces": out}


@router.post("/search")
def search(body: dict[str, Any] = Body(...), c: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    _need_case(c)
    c.require_role("io", "supervisor", "analyst")
    fid, reason = body.get("probe_face_id"), str(body.get("reason") or "").strip()
    if len(reason) < 10:
        raise HTTPException(422, "state why this face is being searched (at least 10 characters)")
    s = c.svc.store
    pr = s.query("SELECT f.*, m.case_id, m.evidence_id FROM faces f JOIN media m ON m.id=f.media_id WHERE f.id=? AND f.role='probe'", (fid,))
    if not pr or pr[0]["case_id"] != c.case.id:
        raise HTTPException(404, "no such face in this case's evidence")
    probe_vec = np.frombuffer(pr[0]["embedding"], dtype=np.float32)
    gallery = s.query("SELECT f.id, f.object_id, f.media_id, f.embedding, m.source, m.legal_basis FROM faces f JOIN media m ON m.id=f.media_id WHERE f.role='gallery'")
    objs = s.get_objects({g["object_id"] for g in gallery})
    scored, withheld = [], 0
    for g in gallery:
        o = objs.get(g["object_id"])
        if not o or not c.decide(o).allow:
            withheld += 1
            continue
        sim = fv.FaceEngine.similarity(probe_vec, np.frombuffer(g["embedding"], dtype=np.float32))
        scored.append((sim, g, o))
    scored.sort(key=lambda x: -x[0])
    out, now = [], utcnow()
    with s.tx() as conn:
        for sim, g, o in scored[:10]:
            band = "strong candidate" if sim >= fv.STRONG_THRESHOLD else "candidate" if sim >= fv.MATCH_THRESHOLD else "below threshold"
            mid = None
            if sim >= fv.MATCH_THRESHOLD:
                mid = "fmatch:" + secrets.token_hex(8)
                conn.execute("INSERT INTO face_matches(id,case_id,probe_face,candidate_object,gallery_face,similarity,searched_by,reason,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                             (mid, c.case.id, fid, o["id"], g["id"], sim, c.user.id, reason, now))
            out.append({"match_id": mid, "object": c.summary(o), "similarity": round(sim, 4), "band": band, "gallery_media": g["media_id"],
                        "photo_source": g["source"], "photo_legal_basis": g["legal_basis"]})
    if pr[0]["evidence_id"]:
        custody_append(s, pr[0]["evidence_id"], c.user.id, "face_search", {"probe_face": fid, "reason": reason, "candidates": sum(1 for x in out if x["match_id"])})
    c.log("face:search", detail={"probe_face": fid, "reason": reason, "gallery": len(gallery), "withheld": withheld},
          object_ids=[x["object"]["id"] for x in out if x["match_id"]])
    return {"probe_face": fid, "threshold": fv.MATCH_THRESHOLD, "gallery_searched": len(scored), "withheld": withheld, "candidates": out,
            "note": "Candidates are leads for human comparison, not identifications. A second officer must confirm."}


@router.post("/matches/{mid}/decide")
def decide(mid: str, body: dict[str, Any] = Body(...), c: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    _need_case(c)
    c.require_role("io", "supervisor")
    decision, reason = body.get("decision"), str(body.get("reason") or "").strip()
    if decision not in ("confirm", "reject") or len(reason) < 5:
        raise HTTPException(422, "decision must be confirm or reject, with a reason")
    s = c.svc.store
    rows = s.query("SELECT * FROM face_matches WHERE id=? AND case_id=?", (mid, c.case.id))
    if not rows or rows[0]["status"] != "candidate":
        raise HTTPException(404, "no open candidate with that id")
    m = rows[0]
    if decision == "confirm" and m["searched_by"] == c.user.id:
        raise HTTPException(403, "two-person rule: the officer who ran the search cannot confirm its result")
    status_ = "confirmed" if decision == "confirm" else "rejected"
    with s.tx() as conn:
        conn.execute("UPDATE face_matches SET status=?, decided_by=?, decision_reason=?, decided_at=? WHERE id=?", (status_, c.user.id, reason, utcnow(), mid))
        if status_ == "confirmed":
            conn.execute("INSERT INTO case_objects(case_id,object_id,added_by,reason,added_at) VALUES(?,?,?,?,?) ON CONFLICT DO NOTHING",
                         (c.case.id, m["candidate_object"], c.user.id, f"face comparison confirmed ({m['similarity']:.2f}): {reason}", utcnow()))
    c.log(f"face:{status_}", detail={"match": mid, "similarity": m["similarity"], "reason": reason}, object_ids=[m["candidate_object"]])
    return {"match_id": mid, "status": status_}


@router.get("/matches")
def matches(c: Ctx = Depends(get_ctx)) -> list[dict[str, Any]]:
    _need_case(c)
    rows = [dict(r) for r in c.svc.store.query("SELECT * FROM face_matches WHERE case_id=? ORDER BY created_at DESC", (c.case.id,))]
    objs = c.svc.store.get_objects({r["candidate_object"] for r in rows})
    for r in rows:
        o = objs.get(r["candidate_object"])
        r["candidate"] = c.summary(o) if o and c.decide(o).allow else None
    return rows

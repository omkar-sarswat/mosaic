"""Casework API: evidence locker, chain of custody, case exports, retention."""

from __future__ import annotations

import hashlib
import secrets
from typing import Any

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from ..config import settings
from ..evidence import content_disposition, SOURCE_TYPES, custody_log, get_evidence, list_evidence, read_evidence, store_evidence, verify_evidence
from ..guard import DEV_USERS
from ..report import case_report_html, case_report_pdf, evidence_pack_zip
from ..retention import run_due, status as retention_status
from ..store import utcnow
from .deps import Ctx, get_ctx

router = APIRouter(tags=["casework"])
MAX_UPLOAD = 200 * 1024 * 1024


def _member(c: Ctx, case_id: str, roles: tuple[str, ...] = ("io", "analyst", "supervisor")):
    case = c.svc.guard.load_case(case_id)
    if not case or c.user.id not in case.members:
        c.log("casework", detail={"case": case_id}, outcome="denied")
        raise HTTPException(403, "not a member of this case")
    if roles and not c.user.has(*roles):
        raise HTTPException(403, f"requires role: {' or '.join(roles)}")
    return case


@router.get("/api/evidence/source-types")
def source_types() -> list[str]:
    return SOURCE_TYPES


@router.post("/api/cases/{case_id}/evidence")
async def upload_evidence(
    case_id: str,
    file: UploadFile = File(...),
    description: str = Form(""),
    source_type: str = Form(""),
    device_make: str = Form(""),
    device_model: str = Form(""),
    device_serial: str = Form(""),
    device_id: str = Form(""),
    seized_from: str = Form(""),
    legal_order: str = Form(""),
    collected_at: str = Form(""),
    linked_objects: str = Form(""),
    c: Ctx = Depends(get_ctx),
) -> dict[str, Any]:
    case = _member(c, case_id)
    if case.status != "open":
        raise HTTPException(409, "case is closed")
    data = await file.read()
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "exhibit larger than 200 MB; use the bulk evidence channel")
    meta = {"mime": file.content_type, "description": description, "source_type": source_type, "device_make": device_make,
            "device_model": device_model, "device_serial": device_serial, "device_id": device_id, "seized_from": seized_from,
            "legal_order": legal_order, "collected_at": collected_at, "linked_objects": [x for x in linked_objects.split(",") if x.strip()]}
    ev = store_evidence(c.svc.store, case_id, c.user.id, file.filename or "exhibit.bin", data, {k: v or None for k, v in meta.items()})
    c.log("evidence:acquired", detail={"evidence": ev["id"], "sha256": ev["sha256"], "filename": ev["filename"]}, object_ids=meta["linked_objects"])
    return ev


@router.get("/api/cases/{case_id}/evidence")
def case_evidence(case_id: str, c: Ctx = Depends(get_ctx)) -> list[dict[str, Any]]:
    _member(c, case_id, roles=())
    c.log("evidence:list", detail={"case": case_id})
    return list_evidence(c.svc.store, case_id)


def _ev_case(c: Ctx, eid: str) -> dict[str, Any]:
    ev = get_evidence(c.svc.store, eid)
    if not ev:
        raise HTTPException(404, "no such exhibit")
    _member(c, ev["case_id"], roles=())
    return ev


@router.get("/api/evidence/{eid}/download")
def download(eid: str, c: Ctx = Depends(get_ctx)) -> Response:
    _ev_case(c, eid)
    try:
        meta, data = read_evidence(c.svc.store, eid, c.user.id, "downloaded")
    except FileNotFoundError as exc:
        raise HTTPException(410, str(exc)) from None
    c.log("evidence:downloaded", detail={"evidence": eid, "sha256": meta["sha256"]})
    return Response(data, media_type=meta.get("mime") or "application/octet-stream",
                    headers={"Content-Disposition": content_disposition(meta["filename"]), "X-SHA256": meta["sha256"]})


@router.post("/api/evidence/{eid}/verify")
def verify(eid: str, c: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    _ev_case(c, eid)
    r = verify_evidence(c.svc.store, eid, c.user.id)
    c.log("evidence:verified", detail=r)
    return r


@router.get("/api/evidence/{eid}/custody")
def custody(eid: str, c: Ctx = Depends(get_ctx)) -> list[dict[str, Any]]:
    _ev_case(c, eid)
    return custody_log(c.svc.store, eid)


@router.post("/api/cases/{case_id}/export")
def export(case_id: str, body: dict[str, Any] = Body(default_factory=dict), c: Ctx = Depends(get_ctx)) -> Response:
    _member(c, case_id, roles=("io", "supervisor", "analyst"))
    kind = body.get("kind", "report_pdf")
    recipient = str(body.get("recipient") or "")[:120]
    clearance = int(body.get("recipient_clearance", c.user.clearance))
    if clearance > c.user.clearance:
        raise HTTPException(403, "cannot release above your own clearance")
    if kind == "evidence_pack" and not c.user.has("io", "supervisor"):
        raise HTTPException(403, "evidence packs are prepared by the IO or a supervisor")
    s = c.svc.store
    if kind == "report_pdf":
        data, ext, mime, exp_id = case_report_pdf(s, case_id, user=c.user.id, recipient=recipient, recipient_clearance=clearance), "pdf", "application/pdf", None
    elif kind == "report_html":
        data, ext, mime, exp_id = case_report_html(s, case_id, user=c.user.id, recipient=recipient, recipient_clearance=clearance).encode(), "html", "text/html", None
    elif kind == "evidence_pack":
        name = DEV_USERS[c.user.id].name if c.user.id in DEV_USERS else c.user.name
        data, exp_id = evidence_pack_zip(s, case_id, user=c.user.id, user_name=name, recipient=recipient, recipient_clearance=clearance)
        ext, mime = "zip", "application/zip"
    else:
        raise HTTPException(422, "kind must be report_pdf, report_html or evidence_pack")
    exp_id = exp_id or secrets.token_hex(4).upper()
    sha = hashlib.sha256(data).hexdigest()
    folder = settings.db_path.parent / "exports" / case_id
    folder.mkdir(parents=True, exist_ok=True)
    fname = f"{case_id}_{kind}_{exp_id}.{ext}"
    (folder / fname).write_bytes(data)
    with s.tx() as conn:
        conn.execute("INSERT INTO exports(id,case_id,kind,filename,sha256,size,exported_by,exported_at,recipient,marking,path) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                     (exp_id, case_id, kind, fname, sha, len(data), c.user.id, utcnow(), recipient, str(clearance), str(folder / fname)))
    c.log("export", detail={"case": case_id, "kind": kind, "export_id": exp_id, "sha256": sha, "recipient": recipient, "recipient_clearance": clearance})
    return Response(data, media_type=mime, headers={"Content-Disposition": f'attachment; filename="{fname}"', "X-SHA256": sha, "X-Export-Id": exp_id})


@router.get("/api/cases/{case_id}/exports")
def exports(case_id: str, c: Ctx = Depends(get_ctx)) -> list[dict[str, Any]]:
    _member(c, case_id, roles=())
    return [dict(r) | {"path": None} for r in c.svc.store.query("SELECT * FROM exports WHERE case_id=? ORDER BY exported_at DESC", (case_id,))]


@router.get("/api/retention")
def retention(c: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    c.require_role("supervisor", "auditor", "admin")
    return retention_status(c.svc.store)


@router.post("/api/retention/run")
def retention_run(c: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    c.require_role("admin", "supervisor")
    res = run_due(c.svc.store, actor=f"{c.user.id} (manual run)")
    c.log("retention:run", detail={"purged": [r["case_id"] for r in res]})
    return {"purged": res}


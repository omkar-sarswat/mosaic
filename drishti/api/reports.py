"""Report builder API: draft case diaries, chargesheet annexures and intelligence summaries, and export them.

Reports belong to a case and are worked on inside it: the active case must be the report's case, so every
reference is read under that case's purpose and scope. Saving checks the version the editor started
from, so two officers cannot silently overwrite each other. Exports go through the same register as case
reports (hash, size, recipient, marking) and into the audit trail.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import Response

from ..casereport import TEMPLATES, Reader, clean_blocks, report_pdf, resolve, starter_blocks
from ..config import settings
from ..patterns import leads as L
from ..report import MARKINGS
from ..store import utcnow
from .deps import Ctx, get_ctx
from .watch import _case, _name

router = APIRouter(prefix="/api", tags=["reports"])


def _in_case(c: Ctx, case_id: str) -> str:
    if not c.svc.store.query("SELECT 1 FROM case_members WHERE case_id=? AND user_id=?", (case_id, c.user.id)):
        c.log("report", detail={"case": case_id}, outcome="denied")
        raise HTTPException(403, "you are not a member of this case")
    active = _case(c)
    if active != case_id:
        raise HTTPException(409, "switch to this report's case to work on it; references are read under the case's purpose")
    return active


def _report(c: Ctx, rid: str) -> dict[str, Any]:
    rows = c.svc.store.query("SELECT * FROM reports WHERE id=?", (rid,))
    if not rows:
        raise HTTPException(404, "no such report")
    r = dict(rows[0])
    _in_case(c, r["case_id"])
    return r


def _public(r: dict[str, Any]) -> dict[str, Any]:
    out = {k: r[k] for k in ("id", "case_id", "template", "title", "created_by", "created_at", "updated_by", "updated_at", "version")}
    out["template_title"] = TEMPLATES.get(r["template"], {}).get("title", r["template"])
    out["created_by_name"], out["updated_by_name"] = _name(r["created_by"]), _name(r["updated_by"])
    return out


def _reader(c: Ctx, case_id: str, clearance: int | None = None) -> Reader:
    return Reader(c.svc.store, case_id, c.user, c.decide, c.user.clearance if clearance is None else clearance)


@router.get("/reports/templates")
def templates(c: Ctx = Depends(get_ctx)) -> list[dict[str, str]]:
    return [{"id": k, **v} for k, v in TEMPLATES.items()]


@router.get("/cases/{case_id}/reports")
def list_reports(case_id: str, c: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    _in_case(c, case_id)
    s = c.svc.store
    rows = [dict(r) for r in s.query("SELECT * FROM reports WHERE case_id=? ORDER BY updated_at DESC", (case_id,))]
    exports = {}
    for r in s.query("SELECT kind, COUNT(*) n, MAX(exported_at) last FROM exports WHERE case_id=? AND kind LIKE 'report:%' GROUP BY kind", (case_id,)):
        exports[r["kind"].split(":", 1)[1]] = {"count": r["n"], "last": r["last"]}
    return {"reports": [_public(r) | {"blocks": len(json.loads(r["blocks"])), "exports": exports.get(r["id"])} for r in rows],
            "templates": [{"id": k, **v} for k, v in TEMPLATES.items()]}


@router.post("/cases/{case_id}/reports")
def create_report(case_id: str, body: dict[str, Any] = Body(...), c: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    _in_case(c, case_id)
    template = str(body.get("template") or "")
    if template not in TEMPLATES:
        raise HTTPException(422, f"template must be one of {', '.join(TEMPLATES)}")
    title = str(body.get("title") or "").strip()[:200] or f"{TEMPLATES[template]['title']} · {utcnow()[:10]}"
    blocks = starter_blocks(c.svc.store, case_id, template)
    rid, now = "report:" + secrets.token_hex(6), utcnow()
    with c.svc.store.tx() as conn:
        conn.execute("INSERT INTO reports(id,case_id,template,title,blocks,created_by,created_at,updated_by,updated_at,version) VALUES(?,?,?,?,?,?,?,?,?,1)",
                     (rid, case_id, template, title, json.dumps(blocks), c.user.id, now, c.user.id, now))
    c.log("report:create", detail={"report": rid, "template": template})
    return _public(dict(c.svc.store.query("SELECT * FROM reports WHERE id=?", (rid,))[0]))


@router.get("/reports/{rid}")
def get_report(rid: str, c: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    r = _report(c, rid)
    reader = _reader(c, r["case_id"])
    blocks = resolve(reader, json.loads(r["blocks"]))
    named = [b["object_id"] for b in blocks if b["type"] == "record" and "record" in (b.get("view") or {})]
    c.log("report:open", detail={"report": rid, "version": r["version"]}, object_ids=named)
    return {"report": _public(r), "blocks": blocks, "marking": reader.marking, "marking_label": MARKINGS.get(reader.marking),
            "template": TEMPLATES.get(r["template"])}


@router.put("/reports/{rid}")
def save_report(rid: str, body: dict[str, Any] = Body(...), c: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    r = _report(c, rid)
    if int(body.get("version") or 0) != r["version"]:
        who = _name(r["updated_by"])
        raise HTTPException(409, f"{who} saved this report after you opened it; reload to see their changes before saving yours")
    try:
        blocks = clean_blocks(body.get("blocks"))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    title = str(body.get("title") or r["title"]).strip()[:200] or r["title"]
    # references must be readable by the person adding them, now
    reader = _reader(c, r["case_id"])
    for b in blocks:
        if b["type"] == "record" and b["object_id"]:
            v = reader.record(b["object_id"], [])
            if v.get("missing"):
                raise HTTPException(422, f"no such record: {b['object_id']}")
    now = utcnow()
    with c.svc.store.tx() as conn:
        n = conn.execute("UPDATE reports SET title=?, blocks=?, updated_by=?, updated_at=?, version=version+1 WHERE id=? AND version=?",
                         (title, json.dumps(blocks), c.user.id, now, rid, r["version"])).rowcount
    if not n:
        raise HTTPException(409, "the report changed while saving; reload it")
    c.log("report:save", detail={"report": rid, "version": r["version"] + 1, "blocks": len(blocks)})
    return _public(dict(c.svc.store.query("SELECT * FROM reports WHERE id=?", (rid,))[0]))


@router.delete("/reports/{rid}")
def delete_report(rid: str, c: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    r = _report(c, rid)
    if r["created_by"] != c.user.id:
        raise HTTPException(403, "only the officer who started a draft can discard it")
    if c.svc.store.query("SELECT 1 FROM exports WHERE kind=?", (f"report:{rid}",)):
        raise HTTPException(409, "this report has been exported; it stays on the case record")
    with c.svc.store.tx() as conn:
        conn.execute("DELETE FROM reports WHERE id=?", (rid,))
    c.log("report:discard", detail={"report": rid, "title": r["title"]})
    return {"id": rid, "deleted": True}


@router.get("/cases/{case_id}/report-sources")
def report_sources(case_id: str, c: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    """What can be inserted into a report of this case: its records, exhibits, leads and area searches."""
    _in_case(c, case_id)
    s = c.svc.store
    ids = [r["object_id"] for r in s.query("SELECT object_id FROM case_objects WHERE case_id=? ORDER BY added_at", (case_id,))]
    objs = s.get_objects(ids)
    records = []
    for i in ids:
        o = objs.get(i)
        if o and c.decide(o).allow:
            m = c.summary(o)
            records.append({"id": i, "type": m["type"], "title": m["title"], "sensitivity": m["sensitivity"]})
    exhibits = [dict(r) for r in s.query("SELECT id, filename, description, source_type, uploaded_at FROM evidence WHERE case_id=? ORDER BY uploaded_at DESC", (case_id,))]
    leads = []
    reveal = set(c.case.scope) if c.case else set()
    for r in s.query("SELECT * FROM pattern_hits WHERE case_id=? ORDER BY severity, id", (case_id,)):
        r = dict(r)
        if L.can_see(s, c.user, r):
            leads.append({"id": r["id"], "title": L.render(s, r, reveal, c.summary, c.decide)["title"], "severity": r["severity"]})
    areas = [dict(r) | {"counts": json.loads(r["counts"])} for r in s.query(
        "SELECT id, label, radius_km, start_ts, end_ts, counts, searched_at FROM area_searches WHERE case_id=? ORDER BY searched_at DESC LIMIT 30", (case_id,))]
    return {"records": records, "exhibits": exhibits, "leads": leads, "areas": areas}


@router.post("/reports/{rid}/export")
def export_report(rid: str, body: dict[str, Any] = Body(default_factory=dict), c: Ctx = Depends(get_ctx)) -> Response:
    r = _report(c, rid)
    recipient = str(body.get("recipient") or "")[:120]
    try:
        clearance = int(body.get("recipient_clearance", c.user.clearance))
    except (TypeError, ValueError):
        raise HTTPException(422, "recipient_clearance must be 0 to 3") from None
    if not 0 <= clearance <= 3:
        raise HTTPException(422, "recipient_clearance must be 0 to 3")
    if clearance > c.user.clearance:
        raise HTTPException(403, "cannot release above your own clearance")
    reader = _reader(c, r["case_id"], clearance)
    blocks = resolve(reader, json.loads(r["blocks"]))
    level = min(max(reader.marking, 1), 3)
    exp_id = secrets.token_hex(4).upper()
    data = report_pdf(c.svc.store, r, blocks, marking_level=level, user=c.user.id, user_name=c.user.name, recipient=recipient,
                      export_id=exp_id, withheld_above=reader.above)
    sha = hashlib.sha256(data).hexdigest()
    folder = settings.db_path.parent / "exports" / r["case_id"]
    folder.mkdir(parents=True, exist_ok=True)
    fname = f"{r['case_id']}_{r['template']}_{exp_id}.pdf"
    (folder / fname).write_bytes(data)
    with c.svc.store.tx() as conn:
        conn.execute("INSERT INTO exports(id,case_id,kind,filename,sha256,size,exported_by,exported_at,recipient,marking,path) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                     (exp_id, r["case_id"], f"report:{rid}", fname, sha, len(data), c.user.id, utcnow(), recipient, MARKINGS[level], str(folder / fname)))
    named = [b["object_id"] for b in blocks if b["type"] == "record" and "record" in (b.get("view") or {})]
    c.log("export", detail={"case": r["case_id"], "kind": "report", "report": rid, "version": r["version"], "export_id": exp_id, "sha256": sha,
                            "recipient": recipient, "recipient_clearance": clearance, "marking": MARKINGS[level], "withheld": reader.above}, object_ids=named)
    return Response(data, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{fname}"', "X-SHA256": sha,
                                                                  "X-Export-Id": exp_id, "X-Marking": MARKINGS[level]})

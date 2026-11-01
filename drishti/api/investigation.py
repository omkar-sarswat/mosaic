"""A common case workspace for every ontology type, with explicit sharing."""
from __future__ import annotations

import hashlib
import json
import secrets
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from ..config import settings
from ..guard import DEV_USERS
from ..investigation import coverage, domain_of, findings, graph_links, shortest_evidence_path, timeline
from ..store import utcnow
from .deps import Ctx, get_ctx

router = APIRouter(prefix="/api/investigation", tags=["investigation"])


def member(c: Ctx):
    if not c.case or c.case.status != "open" or c.user.id not in c.case.members:
        c.log("investigation:access", outcome="denied")
        raise HTTPException(403, "Select an open case you are assigned to")
    c.require_role("io", "analyst", "supervisor")
    return c.case


def admitted(c: Ctx) -> dict[str, dict]:
    case = member(c)
    return {oid: obj for oid, obj in c.svc.store.get_objects(sorted(case.scope)).items() if c.decide(obj).allow}


def visible_object(c: Ctx, oid: str) -> dict:
    case = member(c)
    obj = c.svc.store.get_object(oid)
    if oid not in case.scope or not obj or not c.decide(obj).allow:
        c.log("investigation:object", outcome="denied", object_ids=[oid])
        raise HTTPException(404, "Record unavailable in this case")
    return obj


def summary(c: Ctx, obj: dict) -> dict:
    return c.summary(obj) | {"domain": domain_of(obj["type"])}


def public_edge(edge: dict) -> dict:
    # Raw edge props can contain identifiers. Only return typed relationship metadata.
    return {k: edge[k] for k in ("id", "type", "evidence", "status", "confidence", "sources")} | {
        "source": edge["src"], "target": edge["dst"]}


@router.get("/overview")
def overview(c: Ctx = Depends(get_ctx)) -> dict:
    objects = admitted(c)
    s = c.svc.store
    links = graph_links(s, objects)
    events = timeline(s, objects, links)
    checks = findings(s, objects, links)
    sources = set()
    for oid in objects:
        sources.update(p["source"] for p in s.provenance(oid))
    cases = []
    for case in c.svc.guard.cases_for(c.user):
        cases.append({k: case[k] for k in ("id", "title", "agency", "purpose", "status", "opened_at")})
    c.log("investigation:overview", object_ids=list(objects))
    return {"case": {"id": c.case.id, "max_depth": c.case.max_depth, "purpose": c.case.purpose},
            "counts": {"records": len(objects), "relationships": len(links), "sources": len(sources), "events": len(events), "findings": len(checks)},
            "domains": coverage(objects), "types": dict(Counter(o["type"] for o in objects.values())),
            "recent_events": events[:8], "findings": checks[:8], "cases": cases,
            "scope": "Only records admitted to the selected case and readable by your role", "generated_at": utcnow()}


@router.get("/search")
def search(q: str = Query("", max_length=200), type: str = "", domain: str = "", source: str = "",
           offset: int = Query(0, ge=0), limit: int = Query(40, ge=1, le=200), c: Ctx = Depends(get_ctx)) -> dict:
    objects = admitted(c)
    s = c.svc.store
    # Evaluate visibility before paging. Search the complete admitted set, not a global top-N window.
    if q.strip():
        hits = s.search(q, limit=max(s.count(), 1))
        exact = set(s.find_identifier(q))
        ids = [oid for oid in hits if oid in objects]
    else:
        exact = set()
        ids = sorted(objects, key=lambda oid: (objects[oid]["type"], objects[oid]["title"].casefold(), oid))
    items = []
    for oid in ids:
        obj = objects[oid]
        if type and obj["type"] != type or domain and domain_of(obj["type"]) != domain:
            continue
        sources = sorted({p["source"] for p in s.provenance(oid)})
        if source and source not in sources:
            continue
        items.append(summary(c, obj) | {"sources": sources, "match": "Exact identifier" if oid in exact else "Indexed text / transliteration" if q else "Case record"})
    c.log("investigation:search", detail={"query": q, "type": type, "domain": domain, "source": source}, object_ids=[x["id"] for x in items[offset:offset+limit]])
    return {"items": items[offset:offset+limit], "total": len(items), "offset": offset, "limit": limit,
            "facets": dict(Counter(x["type"] for x in items)), "scope": "case"}


@router.get("/object")
def object_detail(id: str, c: Ctx = Depends(get_ctx)) -> dict:
    obj = visible_object(c, id)
    objects = admitted(c)
    s = c.svc.store
    links = [l for l in graph_links(s, objects) if id in (l["src"], l["dst"])]
    neighbours = {l["dst"] if l["src"] == id else l["src"] for l in links}
    related = [summary(c, objects[oid]) | {"relations": sorted({l["type"] for l in links if oid in (l["src"], l["dst"])})}
               for oid in sorted(neighbours, key=lambda oid: (objects[oid]["type"], objects[oid]["title"]))]
    context = {oid: o for oid, o in objects.items() if oid == id or oid in neighbours}
    events = timeline(s, context, graph_links(s, context))
    notes = [dict(row) for row in s.query("SELECT * FROM investigation_notes WHERE case_id=? AND object_id=? ORDER BY created_at DESC", (c.case.id, id))]
    checks = [f for f in findings(s, objects, graph_links(s, objects)) if id in f["object_ids"]]
    provenance = [dict(p) for p in s.provenance(id) if not p["prop"].startswith("_")]
    c.log("investigation:dossier", object_ids=[id, *sorted(neighbours)])
    return {"object": summary(c, obj), "related": related, "edges": [public_edge(l) for l in links],
            "provenance": provenance, "timeline": events, "findings": checks, "notes": notes,
            "coverage": coverage(context), "documents": [r for r in related if r["type"] == "Document"]}


@router.get("/graph")
def graph(domain: str = "", c: Ctx = Depends(get_ctx)) -> dict:
    objects = admitted(c)
    if domain:
        objects = {oid: o for oid, o in objects.items() if domain_of(o["type"]) == domain}
    links = graph_links(c.svc.store, objects)
    c.log("investigation:graph", object_ids=list(objects))
    return {"nodes": [{"id": o["id"], "label": c.summary(o)["title"], "type": o["type"], "seed": True} for o in objects.values()],
            "edges": [public_edge(l) for l in links], "max_depth": c.case.max_depth}


@router.get("/path")
def path(a: str, b: str, c: Ctx = Depends(get_ctx)) -> dict:
    objects = admitted(c)
    visible_object(c, a)
    visible_object(c, b)
    links = [l for l in graph_links(c.svc.store, objects) if c.svc.ontology.links[l["type"]].evidentiary]
    result = shortest_evidence_path(objects, links, a, b, c.case.max_depth)
    c.log("investigation:path", object_ids=result["nodes"], detail={"a": a, "b": b, "depth": c.case.max_depth})
    return result | {"nodes": [summary(c, objects[oid]) for oid in result["nodes"]], "edges": [public_edge(l) for l in result["edges"]]}


@router.get("/timeline")
def case_timeline(domain: str = "", after: str = "", before: str = "", c: Ctx = Depends(get_ctx)) -> dict:
    objects = admitted(c)
    events = timeline(c.svc.store, objects, graph_links(c.svc.store, objects))
    from ..investigation import parse_time
    start, end = parse_time(after), parse_time(before)
    if after and not start or before and not end:
        raise HTTPException(422, "Use ISO dates or timestamps")
    events = [e for e in events if (not domain or e["domain"] == domain)
              and (not start or parse_time(e["at"]) and parse_time(e["at"]) >= start)
              and (not end or parse_time(e["at"]) and parse_time(e["at"]) <= end)]
    c.log("investigation:timeline", detail={"events": len(events)}, object_ids=list(objects))
    return {"events": events, "timezone": "UTC", "note": "Locations come from recorded evidence; no live tracking"}


@router.get("/sources")
def sources(c: Ctx = Depends(get_ctx)) -> dict:
    objects = admitted(c)
    by_source: dict[str, dict] = {}
    for oid, obj in objects.items():
        for p in c.svc.store.provenance(oid):
            row = by_source.setdefault(p["source"], {"source": p["source"], "ids": set(), "types": set(), "latest": "", "synthetic": True, "assertions": 0})
            row["ids"].add(oid)
            row["types"].add(obj["type"])
            row["latest"] = max(row["latest"], p["ingested_at"])
            row["synthetic"] = row["synthetic"] and obj["synthetic"]
            row["assertions"] += 1
    rows = [{"source": r["source"], "records": len(r["ids"]), "types": sorted(r["types"]), "latest": r["latest"],
             "synthetic": r["synthetic"], "assertions": r["assertions"], "connection": "local records", "live": False} for r in by_source.values()]
    c.log("investigation:sources")
    return {"sources": sorted(rows, key=lambda r: r["source"]), "note": "Source labels describe provenance. They do not imply live access to agency systems."}


@router.get("/findings")
def case_findings(c: Ctx = Depends(get_ctx)) -> dict:
    objects = admitted(c)
    result = findings(c.svc.store, objects, graph_links(c.svc.store, objects))
    c.log("investigation:findings", object_ids=list(objects))
    return {"findings": result, "note": "Evidence-quality checks and recorded associations, not assessments of people", "version": "1.0"}


class NoteInput(BaseModel):
    body: str = Field(min_length=3, max_length=5000)
    object_id: str | None = None


@router.get("/notes")
def notes(c: Ctx = Depends(get_ctx)) -> list[dict]:
    member(c)
    objects = admitted(c)
    rows = [dict(r) for r in c.svc.store.query("SELECT * FROM investigation_notes WHERE case_id=? ORDER BY created_at DESC, id", (c.case.id,))]
    c.log("investigation:notes")
    return [r for r in rows if r["object_id"] is None or r["object_id"] in objects]


@router.post("/notes")
def add_note(body: NoteInput, c: Ctx = Depends(get_ctx)) -> dict:
    member(c)
    if not body.body.strip():
        raise HTTPException(422, "Write a note")
    if body.object_id:
        visible_object(c, body.object_id)
    row = {"id": "note:" + secrets.token_hex(8), "case_id": c.case.id, "object_id": body.object_id,
           "body": body.body.strip(), "author": c.user.id, "created_at": utcnow()}
    with c.svc.store.tx() as conn:
        conn.execute("INSERT INTO investigation_notes(id,case_id,object_id,body,author,created_at) VALUES(?,?,?,?,?,?)", tuple(row.values()))
        c.log("investigation:note_added", detail={"note": row["id"]}, object_ids=[body.object_id] if body.object_id else [])
    return row


class BoardInput(BaseModel):
    title: str = Field(min_length=3, max_length=160)
    object_ids: list[str] = Field(min_length=1, max_length=200)


@router.get("/boards")
def boards(c: Ctx = Depends(get_ctx)) -> list[dict]:
    objects = admitted(c)
    rows = []
    for r in c.svc.store.query("SELECT * FROM investigation_boards WHERE case_id=? ORDER BY created_at DESC", (c.case.id,)):
        d = dict(r)
        d["object_ids"] = [oid for oid in json.loads(d["object_ids"]) if oid in objects]
        rows.append(d)
    c.log("investigation:boards")
    return rows


@router.post("/boards")
def save_board(body: BoardInput, c: Ctx = Depends(get_ctx)) -> dict:
    objects = admitted(c)
    ids = sorted(set(body.object_ids))
    if any(oid not in objects for oid in ids):
        raise HTTPException(404, "One or more records are unavailable in this case")
    row = {"id": "board:" + secrets.token_hex(8), "case_id": c.case.id, "title": body.title.strip(),
           "object_ids": ids, "created_by": c.user.id, "created_at": utcnow()}
    with c.svc.store.tx() as conn:
        conn.execute("INSERT INTO investigation_boards VALUES(?,?,?,?,?,?)", (row["id"], row["case_id"], row["title"], json.dumps(ids), row["created_by"], row["created_at"]))
        c.log("investigation:board_saved", detail={"board": row["id"]}, object_ids=ids)
    return row


class ShareInput(BaseModel):
    recipient: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=15, max_length=2000)


@router.get("/collaboration")
def collaboration(c: Ctx = Depends(get_ctx)) -> dict:
    member(c)
    shares = [dict(r) for r in c.svc.store.query("SELECT * FROM case_shares WHERE case_id=? ORDER BY requested_at DESC", (c.case.id,))]
    members = [DEV_USERS[uid].public() if uid in DEV_USERS else {"id": uid, "name": uid, "agency": "External identity"} for uid in sorted(c.case.members)]
    recipients = [u.public() for u in DEV_USERS.values() if u.has("io", "analyst", "supervisor") and u.id not in c.case.members] if settings.auth_mode == "dev" else []
    c.log("investigation:collaboration")
    return {"members": members, "requests": shares, "recipients": recipients, "can_approve": c.user.has("supervisor"),
            "note": "A different supervisor assigned to this case must approve access. Clearance and jurisdiction still apply."}


@router.post("/collaboration")
def request_share(body: ShareInput, c: Ctx = Depends(get_ctx)) -> dict:
    member(c)
    if settings.auth_mode != "dev":
        raise HTTPException(409, "Recipient directory integration is required in OIDC mode")
    user = DEV_USERS.get(body.recipient)
    if not user or not user.has("io", "analyst", "supervisor"):
        raise HTTPException(422, "Choose an operational recipient")
    if user.id in c.case.members:
        raise HTTPException(409, "Recipient already has case access")
    rid = "share:" + secrets.token_hex(8)
    with c.svc.store.tx() as conn:
        if conn.execute("SELECT id FROM case_shares WHERE case_id=? AND recipient=? AND status='pending'", (c.case.id, user.id)).fetchone():
            raise HTTPException(409, "A request for this recipient is already pending")
        conn.execute("INSERT INTO case_shares(id,case_id,recipient,reason,requested_by,requested_at) VALUES(?,?,?,?,?,?)",
                     (rid, c.case.id, user.id, body.reason.strip(), c.user.id, utcnow()))
        c.log("investigation:share_requested", detail={"request": rid, "recipient": user.id, "reason": body.reason.strip()})
    return {"id": rid, "status": "pending"}


class DecisionInput(BaseModel):
    approve: bool


@router.post("/collaboration/{request_id}")
def decide_share(request_id: str, body: DecisionInput, c: Ctx = Depends(get_ctx)) -> dict:
    member(c)
    c.require_role("supervisor")
    with c.svc.store.tx() as conn:
        raw = conn.execute("SELECT * FROM case_shares WHERE id=? AND case_id=?", (request_id, c.case.id)).fetchone()
        if not raw:
            raise HTTPException(404, "No request in this case")
        if raw["status"] != "pending":
            raise HTTPException(409, "Request has already been decided")
        if raw["requested_by"] == c.user.id:
            raise HTTPException(403, "Two-person rule: you cannot approve your own request")
        status = "approved" if body.approve else "rejected"
        if body.approve:
            conn.execute("INSERT INTO case_members(case_id,user_id) VALUES(?,?) ON CONFLICT DO NOTHING", (c.case.id, raw["recipient"]))
        conn.execute("UPDATE case_shares SET status=?,decided_by=?,decided_at=? WHERE id=?", (status, c.user.id, utcnow(), request_id))
        c.log("investigation:share_decided", detail={"request": request_id, "recipient": raw["recipient"], "status": status})
    return {"id": request_id, "status": status}


@router.get("/models")
def models(c: Ctx = Depends(get_ctx)) -> dict:
    member(c)
    path = settings.db_path.parent / "models" / "record_linkage.json"
    if path.exists():
        artifact = json.loads(path.read_text(encoding="utf-8"))
        report = artifact["report"]
    else:
        report = None
    c.log("investigation:models")
    return {"record_linkage": report, "checks": ["SHA-256 content integrity", "Event interval validation", "Exact shared references", "Conflicting source assertions", "Simultaneous location assertions"],
            "scope": "Matching records and checking evidence quality; no guilt or population risk model"}


@router.get("/compare")
def compare(a: str, b: str, c: Ctx = Depends(get_ctx)) -> dict:
    one, two = visible_object(c, a), visible_object(c, b)
    if one["type"] != "Person" or two["type"] != "Person" or a == b:
        raise HTTPException(422, "Select two different person records")
    from ..ml.linkage import predict
    from ..resolve.matcher import PersonRecord
    path = settings.db_path.parent / "models" / "record_linkage.json"
    if not path.exists():
        raise HTTPException(409, "No locally trained model is available")
    try:
        result = predict(json.loads(path.read_text(encoding="utf-8")), PersonRecord.from_props(a, one["props"]), PersonRecord.from_props(b, two["props"]))
    except (ValueError, TypeError) as exc:
        raise HTTPException(409, "The local linkage model is invalid; validate or retrain it before comparison") from exc
    c.log("investigation:model_comparison", object_ids=[a, b], detail={"model": result["version"]})
    return result


@router.get("/export")
def export_case(c: Ctx = Depends(get_ctx)) -> Response:
    objects = admitted(c)
    links = graph_links(c.svc.store, objects)
    payload = {"format": "drishti.case-review.v1", "case_id": c.case.id, "exported_at": utcnow(), "exported_by": c.user.id,
               "scope": "Only admitted records visible to this exporter; identifiers remain masked",
               "objects": [summary(c, objects[oid]) for oid in sorted(objects)], "relationships": [public_edge(l) for l in links],
               "timeline": timeline(c.svc.store, objects, links), "findings": findings(c.svc.store, objects, links),
               "provenance": {oid: [dict(p) for p in c.svc.store.provenance(oid) if not p["prop"].startswith("_")] for oid in sorted(objects)}}
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2).encode()
    digest = hashlib.sha256(raw).hexdigest()
    c.log("investigation:export", detail={"sha256": digest, "bytes": len(raw)}, object_ids=list(objects))
    return Response(raw, media_type="application/json", headers={"Content-Disposition": 'attachment; filename="case-review.json"', "X-Content-SHA256": digest})

"""Data studio API: profile, clean, map, match and interpret source extracts, then propose them for a
second officer's review before they are published to the ontology.

Everything is case-bound: an extract is lawful material for one case, so previews and proposals need an
open case whose purpose covers the record classes the extract touches. The extract's own values are the
case's material and are shown; anything read from the existing record (a matched person's recorded name)
is shown only when the guard allows it for this case, otherwise it is withheld. Every call is audited."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException

from ..guard import PolicyError
from ..intake import pipeline as P
from .deps import Ctx, get_ctx

router = APIRouter(prefix="/api/intake", tags=["intake"])
WITHHELD = "On record (outside this case)"


def _need_case(c: Ctx, source: str) -> None:
    if source not in P.SPECS:
        raise HTTPException(404, "no such source")
    try:
        P.check_case(c.svc.store, c.user, c.case.id if c.case else None, source)
    except PolicyError as exc:
        c.log("intake_check", detail={"source": source, "error": str(exc)}, outcome="denied")
        raise


def _visible(c: Ctx, oid: str | None, cache: dict[str, bool]) -> bool:
    if not oid:
        return False
    if oid not in cache:
        o = c.svc.store.get_object(oid)
        cache[oid] = bool(o) and c.decide(o).allow
    return cache[oid]


def _redact(c: Ctx, res: dict[str, Any]) -> dict[str, Any]:
    """Recorded names of people outside the case are withheld; the extract's own values are not."""
    seen: dict[str, bool] = {}
    for r in res["rows"]:
        m = r["match"]
        m["visible"] = _visible(c, m.get("person"), seen)
        if not m["visible"]:
            m["person"] = None
        for cl in m.get("clashes", []):
            if not _visible(c, cl["person"], seen):
                cl["person"], cl["name_on_record"] = None, WITHHELD
    for p in res["lenses"]["patterns"]:
        for party in p["parties"]:
            if party.get("person") and not _visible(c, party["person"], seen):
                party["person"] = None
                if party.get("from_record"):
                    party["label"] = WITHHELD
    for n in res["lenses"]["graph"]["nodes"]:
        visible = n["id"].startswith("person:") and _visible(c, n["id"], seen)
        n["person"] = n["id"] if visible else None
        if n.get("from_record") and not visible:
            n["label"] = WITHHELD
    return res


def _ops_view(ops: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for o in ops:
        counts[o["op"]] = counts.get(o["op"], 0) + 1
    keep = {"conflict": 400, "fill": 200, "alias": 200, "create": 200, "candidate": 100}
    shown: dict[str, int] = {}
    out = []
    for o in ops:
        lim = keep.get(o["op"], 0)
        if shown.get(o["op"], 0) < lim:
            shown[o["op"]] = shown.get(o["op"], 0) + 1
            out.append({k: v for k, v in o.items() if not (k == "props" and o["type"] == "Document")} | ({"props": {"title": o["props"].get("title")}} if o.get("type") == "Document" and o["op"] == "create" else {}))
    return {"counts": counts, "items": out}


@router.get("/sources")
def sources(c: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    classes = set(c.svc.ontology.purpose_classes(c.case.purpose)) if c.case else set()
    labels = {k: v.get("label", k) for k, v in c.svc.ontology.record_classes.items()}
    out = [s | {"missing": [x for x in s["classes"] if x not in classes] if c.case else s["classes"], "class_labels": [labels.get(x, x) for x in s["classes"]]} for s in P.sources_catalog()]
    return {"sources": out, "case": c.case.public() if c.case else None, "steps": {k: v["label"] for k, v in P.clean.STEPS.items()}}


@router.post("/preview")
def preview(body: dict = Body(...), c: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    source = body.get("source", "")
    _need_case(c, source)
    res = P.run(c.svc.store, source, body.get("recipe") or None, body.get("mapping") or None)
    res = _redact(c, res)
    res["ops"] = _ops_view(res["ops"])
    c.log("intake_preview", detail={"source": source, "fingerprint": res["fingerprint"], "summary": res["summary"]})
    return res


@router.post("/proposals")
def create_proposal(body: dict = Body(...), c: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    source = body.get("source", "")
    _need_case(c, source)
    try:
        out = P.propose(c.svc.store, c.user, c.case.id, source, body.get("recipe") or None, body.get("mapping") or None,  # type: ignore[union-attr]
                        str(body.get("legal_order") or ""), str(body.get("note") or ""))
    except PolicyError as exc:
        c.log("action:propose_intake", detail={"source": source, "error": str(exc)}, outcome="denied")
        raise
    c.log("action:propose_intake", detail={"source": source, "proposal": out["proposal"], "legal_order": body.get("legal_order"), "summary": out["summary"]})
    return out


def _row(r: Any) -> dict[str, Any]:
    d = dict(r)
    d["summary"] = json.loads(d["summary"])
    d["recipe"] = json.loads(d["recipe"])
    d["applied"] = json.loads(d["applied"]) if d.get("applied") else None
    d.pop("changes", None)
    return d


@router.get("/proposals")
def list_proposals(c: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    s = c.svc.store
    rows = s.query("SELECT p.* FROM intake_proposals p JOIN case_members m ON m.case_id=p.case_id AND m.user_id=? ORDER BY p.requested_at DESC", (c.user.id,))
    return {"proposals": [_row(r) for r in rows]}


@router.get("/proposals/{proposal_id}")
def get_proposal(proposal_id: str, c: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    s = c.svc.store
    rows = s.query("SELECT p.* FROM intake_proposals p JOIN case_members m ON m.case_id=p.case_id AND m.user_id=? WHERE p.id=?", (c.user.id, proposal_id))
    if not rows:
        c.log("intake_proposal_view", object_ids=[proposal_id], outcome="denied")
        raise HTTPException(404, "no such proposal in your cases")
    out = _row(rows[0]) | {"ops": _ops_view(json.loads(rows[0]["changes"]))}
    c.log("intake_proposal_view", object_ids=[proposal_id])
    return out


def _decide(proposal_id: str, body: dict, c: Ctx, action: str) -> dict[str, Any]:
    s = c.svc.store
    try:
        if action == "revert":
            out = P.revert(s, c.user, proposal_id, str(body.get("reason") or ""))
        else:
            out = P.decide(s, c.user, proposal_id, action == "approve", str(body.get("reason") or ""))
    except PolicyError as exc:
        c.log(f"action:{action}_intake", detail={"proposal": proposal_id, "error": str(exc)}, outcome="denied")
        raise
    c.log(f"action:{action}_intake", detail={"proposal": proposal_id, "reason": body.get("reason"), **{k: v for k, v in out.items() if k != "skipped"}})
    return out


@router.post("/proposals/{proposal_id}/approve")
def approve(proposal_id: str, body: dict = Body(...), c: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    return _decide(proposal_id, body, c, "approve")


@router.post("/proposals/{proposal_id}/reject")
def reject(proposal_id: str, body: dict = Body(...), c: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    return _decide(proposal_id, body, c, "reject")


@router.post("/proposals/{proposal_id}/revert")
def revert(proposal_id: str, body: dict = Body(...), c: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    return _decide(proposal_id, body, c, "revert")


@router.get("/history/{object_id}")
def history(object_id: str, c: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    o = c.svc.store.get_object(object_id)
    if not o:
        raise HTTPException(404, "no such object")
    d = c.decide(o)
    if not d.allow:
        c.log("revision_history", object_ids=[object_id], outcome="denied", detail={"reason": d.reason})
        raise HTTPException(403, d.reason)
    cards = P.history(c.svc.store, object_id)
    c.log("revision_history", object_ids=[object_id], detail={"cards": len(cards)})
    return {"object_id": object_id, "cards": cards}

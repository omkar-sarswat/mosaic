"""Pattern leads API: mission-track leads (pseudonymous until a case is opened), the two-person
case-from-lead workflow, detector catalog and evaluation.

Every list, view and action is audited. Aggregate figures (counts per track, evaluation) carry no
personal data and are open to every signed-in role, including oversight."""

from __future__ import annotations

import json
from collections import Counter
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException

from ..guard import PolicyError
from ..patterns import leads as L
from ..patterns.engine import REGISTRY, catalog, run_patterns
from ..patterns.evaluate import evaluate
from ..store import utcnow
from .deps import Ctx, get_ctx

router = APIRouter(prefix="/api/patterns", tags=["patterns"])


def _reveal(c: Ctx) -> set[str]:
    if c.case and c.case.status == "open" and c.user.id in c.case.members:
        return set(c.case.scope)
    return set()


def _render(c: Ctx, row: dict[str, Any]) -> dict[str, Any]:
    return L.render(c.svc.store, row, _reveal(c), c.summary, c.decide)


@router.get("/catalog")
def get_catalog(c: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    ont = c.svc.ontology
    return {"detectors": catalog(), "tracks": ont.mission_tracks, "agencies": ont.agencies, "my_tracks": sorted(L.visible_tracks(c.svc.store, c.user)),
            "record_classes": {k: v.get("label", k) for k, v in ont.record_classes.items()}, "purpose_classes": {k: list(v) for k, v in ont.purpose_class_map.items()}}


@router.get("/summary")
def summary(c: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    s = c.svc.store
    rows = [dict(r) for r in s.query("SELECT id, detector, tracks, severity, status, district_lgd FROM pattern_hits")]
    mine = [r for r in rows if L.can_see(s, c.user, r)]
    by_track: Counter = Counter()
    for r in mine:
        if r["status"] == "open":
            for t in json.loads(r["tracks"]):
                by_track[t] += 1
    run = s.query("SELECT * FROM pattern_runs ORDER BY started_at DESC LIMIT 1")
    return {"visible": len(mine), "open": sum(r["status"] == "open" for r in mine),
            "by_track": dict(by_track), "by_detector": dict(Counter(r["detector"] for r in mine if r["status"] == "open")),
            "by_severity": dict(Counter(r["severity"] for r in mine if r["status"] == "open")),
            "by_status": dict(Counter(r["status"] for r in mine)), "all_leads": len(rows),
            "last_run": dict(run[0]) | {"counts": json.loads(run[0]["counts"]), "timings": json.loads(run[0]["timings"])} if run else None}


@router.get("/leads")
def list_leads(track: str | None = None, detector: str | None = None, status: str = "open", severity: str | None = None,
               c: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    s = c.svc.store
    if not L.visible_tracks(s, c.user):
        c.log("leads_list", detail={"track": track}, outcome="denied")
        raise HTTPException(403, "your role or agency has no mission tracks")
    sql, params = "SELECT * FROM pattern_hits WHERE 1=1", []
    if status != "all":
        sql += " AND status=?"
        params.append(status)
    if detector:
        sql += " AND detector=?"
        params.append(detector)
    if severity:
        sql += " AND severity=?"
        params.append(severity)
    rows = [dict(r) for r in s.query(sql, params)]
    rows = [r for r in rows if L.can_see(s, c.user, r) and (not track or track in json.loads(r["tracks"]))]
    rows.sort(key=lambda r: ({"high": 0, "medium": 1, "low": 2}.get(r["severity"], 9), r["detector"], r["id"]))
    out = [_render(c, r) for r in rows]
    c.log("leads_list", detail={"track": track, "detector": detector, "status": status, "count": len(out)}, object_ids=[r["id"] for r in rows][:200])
    return {"leads": out, "tracks": sorted(L.visible_tracks(s, c.user))}


@router.get("/leads/{hit_id}")
def get_lead(hit_id: str, c: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    s = c.svc.store
    try:
        row = L.get_row(s, hit_id)
    except PolicyError:
        raise HTTPException(404, "no such lead") from None
    if not L.can_see(s, c.user, row):
        c.log("lead_view", object_ids=[hit_id], outcome="denied")
        raise HTTPException(403, "this lead is outside your agency's mission tracks or jurisdiction")
    out = _render(c, row)
    spec = REGISTRY.get(row["detector"])
    out["detector_card"] = spec.card() if spec else None
    out["requests"] = [dict(r) for r in s.query("SELECT id, purpose, title, requested_by, requested_at, status, decided_by, decided_at, case_id "
                                                "FROM lead_requests WHERE hit_id=? ORDER BY requested_at DESC", (hit_id,))]
    out["purposes"] = list(c.svc.ontology.agency_purposes(c.user.agency))
    c.log("lead_view", detail={"revealed": [p["id"] for p in out["parties"] if p["revealed"]]}, object_ids=[hit_id] + [p["id"] for p in out["parties"] if p["revealed"]])
    return out


@router.post("/leads/{hit_id}/request-case")
def request_case(hit_id: str, body: dict = Body(...), c: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    try:
        rid = L.request_case(c.svc.store, c.user, hit_id, body.get("purpose", ""), body.get("legal_basis", ""), body.get("title"))
    except PolicyError as exc:
        c.log("action:request_case_from_lead", detail={"lead": hit_id, "error": str(exc)}, object_ids=[hit_id], outcome="denied")
        raise HTTPException(403, str(exc)) from None
    c.log("action:request_case_from_lead", detail={"lead": hit_id, "request": rid, "purpose": body.get("purpose")}, object_ids=[hit_id])
    return {"request_id": rid, "status": "pending", "next": "a supervisor of your agency who is not you must approve"}


@router.get("/requests")
def pending_requests(c: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    s = c.svc.store
    rows = [dict(r) for r in s.query("SELECT r.*, h.detector, h.severity FROM lead_requests r JOIN pattern_hits h ON h.id=r.hit_id "
                                     "WHERE r.agency=? ORDER BY r.requested_at DESC", (c.user.agency,))]
    for r in rows:
        r["lead_title"] = _render(c, L.get_row(s, r["hit_id"]))["title"]
    return {"requests": rows}


@router.post("/requests/{request_id}/approve")
def approve(request_id: str, c: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    s = c.svc.store
    try:
        out = L.approve_case(s, c.svc.guard, c.user, request_id)
    except PolicyError as exc:
        c.log("action:approve_case_from_lead", detail={"request": request_id, "error": str(exc)}, outcome="denied")
        raise HTTPException(403, str(exc)) from None
    c.log("action:approve_case_from_lead", detail=out | {"request": request_id}, object_ids=[out["lead"]])
    c.svc.audit.append(user_id=c.user.id, role=c.user.primary_role, action="action:open_case", case_id=out["case_id"], purpose=out["purpose"],
                       detail={"from_lead": out["lead"], "requested_by": out["requested_by"]}, object_ids=[out["lead"]])
    from . import intel
    intel.invalidate()
    return out


@router.post("/leads/{hit_id}/dismiss")
def dismiss(hit_id: str, body: dict = Body(...), c: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    try:
        L.dismiss(c.svc.store, c.user, hit_id, body.get("reason", ""))
    except PolicyError as exc:
        c.log("action:dismiss_lead", detail={"lead": hit_id, "error": str(exc)}, object_ids=[hit_id], outcome="denied")
        raise HTTPException(403, str(exc)) from None
    c.log("action:dismiss_lead", detail={"lead": hit_id, "reason": body.get("reason")}, object_ids=[hit_id])
    return {"ok": True}


# Detector test results (planted networks, look-alikes, red team) are for the people who maintain and
# oversee the detectors, not for operational users acting on leads.
GOVERNANCE_ROLES = ("admin", "steward", "auditor")


@router.get("/evaluation")
def get_evaluation(c: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    c.require_role(*GOVERNANCE_ROLES)
    rep = c.svc.store.get_meta("pattern_evaluation")
    if not rep:
        raise HTTPException(404, "no evaluation yet; run the detectors")
    disp = Counter((r["detector"], r["status"]) for r in c.svc.store.query("SELECT detector, status FROM pattern_hits"))
    rep["dispositions"] = [{"detector": d, "status": st, "n": n} for (d, st), n in sorted(disp.items())]
    redteam = c.svc.store.get_meta("pattern_redteam")
    if redteam:
        rep["redteam"] = redteam
    return rep


@router.get("/runs")
def runs(c: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    c.require_role(*GOVERNANCE_ROLES)
    return {"runs": [dict(r) | {"counts": json.loads(r["counts"]), "timings": json.loads(r["timings"]), "detectors": json.loads(r["detectors"])}
                     for r in c.svc.store.query("SELECT * FROM pattern_runs ORDER BY started_at DESC LIMIT 20")]}


@router.post("/run")
def run(c: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    c.require_role("supervisor", "analyst")
    out = run_patterns(c.svc.store, run_by=c.user.id)
    if c.svc.store.get_meta("synthetic_truth"):
        evaluate(c.svc.store)
    c.log("action:run_patterns", detail=out)
    return out | {"at": utcnow()}

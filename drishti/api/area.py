"""Area search: who and what was inside a circle on the map during a window of time.

The answer names people by where they were, so the question is asked only inside an open case, by an
investigator, with a stated reason. The circle is at most 10 km across its radius and the window at most
a year. The question, the reason and how many records each register returned are kept with the case,
so a report can cite the search and a supervisor can see what was asked.
"""

from __future__ import annotations

import json
import secrets
from datetime import date
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException

from ..monitor import MAX_RADIUS_KM, Gate, area_search, sites
from ..store import utcnow
from .deps import Ctx, get_ctx
from .watch import INVESTIGATORS, _case, _name, _reason

router = APIRouter(prefix="/api/area", tags=["area"])
MAX_DAYS = 366


def _day(v: Any, what: str) -> date:
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        raise HTTPException(422, f"{what} must be a date (YYYY-MM-DD)") from None


def ask(c: Ctx, lat: float, lon: float, radius: float, start: str, end: str) -> dict[str, Any]:
    return area_search(c.svc.store, Gate(c.svc.store, c.decide, c.summary), lat, lon, radius, start, end)


def flag(c: Ctx, found: dict[str, Any]) -> None:
    """Put the people that matter first: subjects of this case, then anyone accused in an FIR."""
    scope = set(c.case.scope) if c.case else set()
    accused = {r["src"] for r in c.svc.store.query("SELECT src FROM links WHERE type='accused_in' AND src LIKE 'person:%'")}
    n = 0
    for group in ("vehicles", "phones", "travellers", "residents"):
        for item in found[group]:
            ids = {item["record"]["id"], (item.get("owner") or {}).get("id")}
            item["flag"] = "Subject of this case" if ids & scope else ("Accused in an FIR" if ids & accused else None)
            n += bool(item["flag"])
        found[group].sort(key=lambda x: (x["flag"] is None, x["flag"] != "Subject of this case"))
    found["flagged"] = n


@router.get("/sites")
def area_sites(c: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    c.require_role(*INVESTIGATORS)
    return {"sites": sites(c.svc.store), "max_radius_km": MAX_RADIUS_KM, "max_days": MAX_DAYS}


@router.post("/search")
def search(body: dict[str, Any] = Body(...), c: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    case_id = _case(c)
    reason = _reason(body)
    try:
        lat, lon, radius = float(body["lat"]), float(body["lon"]), float(body.get("radius_km", 2))
    except (KeyError, TypeError, ValueError):
        raise HTTPException(422, "lat, lon and radius_km are required") from None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise HTTPException(422, "the centre is not on the map")
    if not 0.1 <= radius <= MAX_RADIUS_KM:
        raise HTTPException(422, f"the radius must be between 0.1 and {MAX_RADIUS_KM:g} km")
    start, end = _day(body.get("start"), "start"), _day(body.get("end"), "end")
    if end < start:
        raise HTTPException(422, "the window ends before it starts")
    if (end - start).days > MAX_DAYS:
        raise HTTPException(422, f"the window can be at most {MAX_DAYS} days; ask a narrower question")
    label = str(body.get("label") or "").strip()[:120] or f"{lat:.4f}, {lon:.4f}"
    found = ask(c, lat, lon, radius, start.isoformat(), end.isoformat())
    flag(c, found)
    sid = "area:" + secrets.token_hex(6)
    with c.svc.store.tx() as conn:
        conn.execute("INSERT INTO area_searches(id,case_id,lat,lon,radius_km,start_ts,end_ts,label,reason,counts,searched_by,searched_at) "
                     "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                     (sid, case_id, lat, lon, radius, start.isoformat(), end.isoformat(), label, reason, json.dumps(found["counts"]), c.user.id, utcnow()))
    named = [x["record"]["id"] for g in ("vehicles", "phones", "travellers", "residents", "incidents") for x in found[g]]
    c.log("area_search", detail={"search": sid, "lat": lat, "lon": lon, "radius_km": radius, "start": start.isoformat(), "end": end.isoformat(),
                                 "reason": reason, "counts": found["counts"], "withheld": found["withheld"]}, object_ids=named[:500])
    return {"id": sid, "label": label, "reason": reason, **found}


@router.get("/searches")
def searches(c: Ctx = Depends(get_ctx)) -> list[dict[str, Any]]:
    case_id = _case(c)
    rows = c.svc.store.query("SELECT * FROM area_searches WHERE case_id=? ORDER BY searched_at DESC LIMIT 50", (case_id,))
    return [dict(r) | {"counts": json.loads(r["counts"]), "searched_by_name": _name(r["searched_by"])} for r in rows]

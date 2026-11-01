"""Watchlists and saved searches: follow a record or an area inside a case, and keep asking a search.

A watch belongs to the case, not to one officer. Every member sees it, and whoever reviews new activity
marks it reviewed for the team, under their own name. Starting or ending a watch needs a reason, and
both go into the audit trail. Activity is read through the same access rules as every other screen,
under the active case, so a watch never shows anything the case itself could not open.
"""

from __future__ import annotations

import json
import secrets
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException

from ..guard import DEV_USERS
from ..monitor import MAX_RADIUS_KM, PRIORITY, Gate, area_events, area_search, dumps_area, escalate, priorities, record_activity
from ..patterns import leads as L
from ..store import utcnow
from .deps import Ctx, get_ctx

router = APIRouter(prefix="/api", tags=["monitoring"])
LOOKBACK_MAX = 180
INVESTIGATORS = ("io", "supervisor", "analyst")


def _name(uid: str | None) -> str | None:
    if not uid:
        return None
    u = DEV_USERS.get(uid)
    return u.name if u else uid


def _case(c: Ctx) -> str:
    c.require_role(*INVESTIGATORS)
    if c.case is None:
        raise HTTPException(403, "open a case first: watches and saved searches belong to a case")
    if c.case.status != "open":
        raise HTTPException(409, "the case is closed")
    if c.user.id not in c.case.members:
        c.log("watch", detail={"case": c.case.id}, outcome="denied")
        raise HTTPException(403, "you are not a member of this case")
    return c.case.id


def _reason(body: dict[str, Any], what: str = "reason") -> str:
    reason = str(body.get("reason") or "").strip()
    if len(reason) < 10:
        raise HTTPException(422, f"a {what} of at least 10 characters is required; it is kept in the audit trail")
    return reason[:500]


def _since(days: Any) -> str:
    try:
        d = max(0, min(int(days or 0), LOOKBACK_MAX))
    except (TypeError, ValueError):
        d = 0
    return (datetime.now(timezone.utc) - timedelta(days=d)).isoformat(timespec="seconds")


def _gate(c: Ctx) -> Gate:
    return Gate(c.svc.store, c.decide, c.summary)


# ---------------------------------------------------------------------------------------------- watches

def _watch(c: Ctx, wid: str) -> dict[str, Any]:
    case_id = _case(c)
    rows = c.svc.store.query("SELECT * FROM watches WHERE id=? AND case_id=?", (wid, case_id))
    if not rows:
        raise HTTPException(404, "no such watch in the active case")
    return dict(rows[0])


def _lead_events(c: Ctx, ids: list[str], since: str) -> list[dict[str, Any]]:
    s = c.svc.store
    if not L.visible_tracks(s, c.user):
        return []
    wanted, out = set(ids), []
    reveal = set(c.case.scope) if c.case else set()
    for r in s.query("SELECT * FROM pattern_hits WHERE first_seen>=? AND status='open'", (since,)):
        r = dict(r)
        if wanted & set(json.loads(r["subjects"])) and L.can_see(s, c.user, r):
            shown = L.render(s, r, reveal, c.summary, c.decide)
            out.append({"at": r["first_seen"], "kind": "lead", "title": shown["title"], "detail": f"{r['severity'].capitalize()} severity · {', '.join(json.loads(r['tracks'])).replace('_', ' ')} track",
                        "source": "DRISHTI-ANALYTICS", "source_name": "Mosaic pattern leads", "record": None, "via": None, "other": None,
                        "lat": None, "lon": None, "place": None, "priority": "high", "why": "Pattern lead", "emph": []})
    return out


def activity(c: Ctx, w: dict[str, Any], gate: Gate | None = None, limit: int = 300) -> dict[str, Any]:
    """A watch's activity since it began, newest first, each entry marked new if it came after the last review.

    Importance and the new-since-review counts are worked out over everything; only the list is trimmed, and the
    trim keeps every entry above routine before any routine one."""
    gate = gate or _gate(c)
    s = c.svc.store
    if w["kind"] == "object":
        obj = s.get_object(w["object_id"])
        if not obj:
            return {"events": [], "total": 0, "counts": {}, "unavailable": "the record no longer exists", "withheld": [], "new": 0, "new_key": 0}
        d = c.decide(obj)
        if not d.allow:
            return {"events": [], "total": 0, "counts": {}, "unavailable": d.reason, "withheld": [], "new": 0, "new_key": 0}
        res = record_activity(s, gate, obj, w["since"], facts_after=w["created_at"], limit=100_000)
        leads = _lead_events(c, [obj["id"]] + [x["id"] for k in ("phones", "vehicles", "accounts") for x in res["through"][k]], w["since"])
        if leads:
            res["events"] = sorted(res["events"] + leads, key=lambda e: e["at"] or "", reverse=True)
            res["total"] += len(leads)
            res["counts"]["lead"] = len(leads)
    else:
        a = json.loads(w["area"])
        found = area_search(s, gate, a["lat"], a["lon"], a["radius_km"], w["since"], "9999")
        events = area_events(found)
        res = {"events": events, "total": len(events), "counts": dict(Counter(e["kind"] for e in events)), "cut": found["cut"],
               "unlisted_numbers": found["unlisted_numbers"]}
    events = res["events"]
    escalate(events, set(c.case.scope) if c.case else set(), _accused(c))
    for e in events:
        e["new"] = (e["at"] or "") > w["seen_at"]
    res["priorities"] = priorities(events)
    res["new"] = sum(1 for e in events if e["new"])
    res["new_key"] = sum(1 for e in events if e["new"] and e["priority"] != "low")
    keep = [e for e in events if e["priority"] != "low"][:limit]
    keep += [e for e in events if e["priority"] == "low"][: max(0, limit - len(keep))]
    res["events"] = sorted(keep, key=lambda e: e["at"] or "", reverse=True)
    res["total"] = len(events)
    res["withheld"] = gate.withheld_list()
    return res


def _accused(c: Ctx) -> set[str]:
    """People accused in any FIR (cached for the request)."""
    if not hasattr(c, "_accused"):
        c._accused = {r["src"] for r in c.svc.store.query("SELECT src FROM links WHERE type='accused_in' AND src LIKE 'person:%'")}  # type: ignore[attr-defined]
    return c._accused  # type: ignore[attr-defined]


def _public(w: dict[str, Any], act: dict[str, Any] | None = None) -> dict[str, Any]:
    out = {k: w[k] for k in ("id", "case_id", "kind", "object_id", "label", "reason", "created_by", "created_at", "since", "seen_at", "seen_by", "status",
                             "ended_by", "ended_at", "end_reason")}
    out["area"] = json.loads(w["area"]) if w["area"] else None
    out["created_by_name"], out["seen_by_name"], out["ended_by_name"] = _name(w["created_by"]), _name(w["seen_by"]), _name(w["ended_by"])
    if act is not None:
        out["new"] = act["new"]
        out["new_key"] = act.get("new_key", 0)
        out["total"] = act["total"]
        out["latest"] = act["events"][0]["at"] if act["events"] else None
        out["unavailable"] = act.get("unavailable")
    return out


@router.get("/watches")
def watches(c: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    case_id = _case(c)
    s = c.svc.store
    gate = _gate(c)
    rows = [dict(r) for r in s.query("SELECT * FROM watches WHERE case_id=? ORDER BY status, created_at DESC", (case_id,))]
    out = [_public(w, activity(c, w, gate, limit=60) if w["status"] == "active" else None) for w in rows]
    searches = [dict(r) for r in s.query("SELECT * FROM saved_searches WHERE case_id=? ORDER BY status, created_at DESC", (case_id,))]
    srch = []
    for r in searches:
        res = _run(c, r["query"], r["types"]) if r["status"] == "active" else None
        srch.append(_search_public(r, res))
    c.log("watch:list", detail={"case": case_id, "watches": len(out), "searches": len(srch)},
          object_ids=[w["object_id"] for w in out if w["object_id"]])
    return {"case": case_id, "watches": out, "searches": srch, "lookback_max": LOOKBACK_MAX, "max_radius_km": MAX_RADIUS_KM}


@router.post("/watches")
def watch_record(body: dict[str, Any] = Body(...), c: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    case_id = _case(c)
    reason = _reason(body)
    oid = str(body.get("object_id") or "")
    obj = c.svc.store.get_object(oid)
    if not obj:
        raise HTTPException(404, "no such record")
    d = c.decide(obj)
    if not d.allow:
        c.log("watch:start", detail={"reason": d.reason}, object_ids=[oid], outcome="denied")
        raise HTTPException(403, d.reason)
    if c.svc.store.query("SELECT id FROM watches WHERE case_id=? AND object_id=? AND status='active'", (case_id, oid)):
        raise HTTPException(409, "this record is already watched in this case")
    since, now = _since(body.get("lookback_days", 30)), utcnow()
    wid = "watch:" + secrets.token_hex(6)
    label = c.summary(obj)["title"]
    with c.svc.store.tx() as conn:
        conn.execute("INSERT INTO watches(id,case_id,kind,object_id,area,label,reason,created_by,created_at,since,seen_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                     (wid, case_id, "object", oid, None, label, reason, c.user.id, now, since, since))
    c.log("watch:start", detail={"watch": wid, "reason": reason, "since": since}, object_ids=[oid])
    return _public(dict(c.svc.store.query("SELECT * FROM watches WHERE id=?", (wid,))[0]))


@router.post("/watches/area")
def watch_area(body: dict[str, Any] = Body(...), c: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    case_id = _case(c)
    reason = _reason(body)
    try:
        lat, lon, radius = float(body["lat"]), float(body["lon"]), float(body.get("radius_km", 1))
    except (KeyError, TypeError, ValueError):
        raise HTTPException(422, "lat, lon and radius_km are required") from None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180) or not (0.1 <= radius <= MAX_RADIUS_KM):
        raise HTTPException(422, f"the radius must be between 0.1 and {MAX_RADIUS_KM:g} km")
    label = str(body.get("label") or f"{lat:.4f}, {lon:.4f}").strip()[:120]
    since, now = _since(body.get("lookback_days", 30)), utcnow()
    wid = "watch:" + secrets.token_hex(6)
    with c.svc.store.tx() as conn:
        conn.execute("INSERT INTO watches(id,case_id,kind,object_id,area,label,reason,created_by,created_at,since,seen_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                     (wid, case_id, "area", None, dumps_area(lat, lon, radius, label), f"{radius:g} km around {label}", reason, c.user.id, now, since, since))
    c.log("watch:start", detail={"watch": wid, "area": {"lat": lat, "lon": lon, "radius_km": radius}, "reason": reason, "since": since})
    return _public(dict(c.svc.store.query("SELECT * FROM watches WHERE id=?", (wid,))[0]))


@router.get("/watches/of/{oid:path}")
def watch_of(oid: str, c: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    """Whether the active case already watches a record (for the dossier's Watch button)."""
    case_id = _case(c)
    rows = c.svc.store.query("SELECT * FROM watches WHERE case_id=? AND object_id=? AND status='active'", (case_id, oid))
    return {"watch": _public(dict(rows[0])) if rows else None}


@router.get("/watches/{wid}")
def watch_detail(wid: str, c: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    w = _watch(c, wid)
    act = activity(c, w) if w["status"] == "active" else {"events": [], "total": 0, "counts": {}, "new": 0, "withheld": []}
    ids = [w["object_id"]] if w["object_id"] else []
    ids += [x["id"] for e in act["events"] for x in (e.get("via"), e.get("other")) if x]
    c.log("watch:view", detail={"watch": wid, "events": act["total"], "new": act["new"]}, object_ids=list(dict.fromkeys(ids))[:200])
    return {"watch": _public(w, act), "activity": act}


@router.post("/watches/{wid}/seen")
def watch_seen(wid: str, c: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    w = _watch(c, wid)
    act = activity(c, w, limit=1)
    # dated entries can sit in the future (bookings); review covers everything shown, so take the later of the two
    upto = max(utcnow(), (act["events"][0]["at"] if act["events"] else "") or "")
    with c.svc.store.tx() as conn:
        conn.execute("UPDATE watches SET seen_at=?, seen_by=? WHERE id=?", (upto, c.user.id, wid))
    c.log("watch:reviewed", detail={"watch": wid, "new": act["new"]}, object_ids=[w["object_id"]] if w["object_id"] else None)
    return {"id": wid, "seen_at": upto}


@router.post("/watches/{wid}/end")
def watch_end(wid: str, body: dict[str, Any] = Body(...), c: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    w = _watch(c, wid)
    reason = _reason(body)
    if w["status"] != "active":
        raise HTTPException(409, "this watch has already ended")
    with c.svc.store.tx() as conn:
        conn.execute("UPDATE watches SET status='ended', ended_by=?, ended_at=?, end_reason=? WHERE id=?", (c.user.id, utcnow(), reason, wid))
    c.log("watch:end", detail={"watch": wid, "reason": reason}, object_ids=[w["object_id"]] if w["object_id"] else None)
    return {"id": wid, "status": "ended"}


# ---------------------------------------------------------------------------------------------- saved searches

def _run(c: Ctx, query: str, types: str) -> dict[str, Any]:
    """The saved question asked again, through the access rules of the active case (not audited on its own)."""
    s = c.svc.store
    type_list = [t for t in (types or "").split(",") if t]
    ids = s.search(query, type_list or None, limit=600)
    objs = s.get_objects(ids)
    results, withheld = [], Counter()
    for i in ids:
        o = objs.get(i)
        if not o:
            continue
        d = c.decide(o)
        if d.allow:
            if len(results) < 100:
                results.append(c.summary(o))
        else:
            withheld[d.reason] += 1
    return {"results": results, "withheld": [{"reason": r, "count": n} for r, n in withheld.most_common()]}


def _search_public(r: dict[str, Any], res: dict[str, Any] | None = None) -> dict[str, Any]:
    known = set(json.loads(r["known"]))
    out = {k: r[k] for k in ("id", "case_id", "title", "query", "types", "reason", "created_by", "created_at", "checked_at", "checked_by", "status",
                             "ended_by", "ended_at", "end_reason")}
    out["created_by_name"], out["checked_by_name"], out["ended_by_name"] = _name(r["created_by"]), _name(r["checked_by"]), _name(r["ended_by"])
    if res is not None:
        out["total"] = len(res["results"])
        out["new"] = sum(1 for x in res["results"] if x["id"] not in known)
    return out


def _search(c: Ctx, sid: str) -> dict[str, Any]:
    case_id = _case(c)
    rows = c.svc.store.query("SELECT * FROM saved_searches WHERE id=? AND case_id=?", (sid, case_id))
    if not rows:
        raise HTTPException(404, "no such saved search in the active case")
    return dict(rows[0])


@router.post("/searches")
def save_search(body: dict[str, Any] = Body(...), c: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    case_id = _case(c)
    reason = _reason(body)
    query = str(body.get("query") or "").strip()
    if not 2 <= len(query) <= 200:
        raise HTTPException(422, "the search must be 2 to 200 characters")
    types = ",".join(t for t in str(body.get("types") or "").split(",") if t)
    title = str(body.get("title") or query).strip()[:120]
    res = _run(c, query, types)
    sid, now = "search:" + secrets.token_hex(6), utcnow()
    with c.svc.store.tx() as conn:
        conn.execute("INSERT INTO saved_searches(id,case_id,title,query,types,reason,created_by,created_at,known,checked_at,checked_by) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                     (sid, case_id, title, query, types, reason, c.user.id, now, json.dumps([x["id"] for x in res["results"]]), now, c.user.id))
    c.log("search:saved", detail={"search": sid, "q": query, "types": types, "reason": reason, "returned": len(res["results"])},
          object_ids=[x["id"] for x in res["results"]])
    return _search_public(dict(c.svc.store.query("SELECT * FROM saved_searches WHERE id=?", (sid,))[0]), res)


@router.get("/searches/{sid}")
def search_detail(sid: str, c: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    r = _search(c, sid)
    res = _run(c, r["query"], r["types"]) if r["status"] == "active" else {"results": [], "withheld": []}
    known = set(json.loads(r["known"]))
    for x in res["results"]:
        x["new"] = x["id"] not in known
    res["results"].sort(key=lambda x: not x["new"])
    c.log("search", detail={"q": r["query"], "types": r["types"], "saved_search": sid, "returned": len(res["results"])},
          object_ids=[x["id"] for x in res["results"]])
    return {"search": _search_public(r, res), **res}


@router.post("/searches/{sid}/seen")
def search_seen(sid: str, c: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    r = _search(c, sid)
    res = _run(c, r["query"], r["types"])
    known = sorted(set(json.loads(r["known"])) | {x["id"] for x in res["results"]})
    now = utcnow()
    with c.svc.store.tx() as conn:
        conn.execute("UPDATE saved_searches SET known=?, checked_at=?, checked_by=? WHERE id=?", (json.dumps(known), now, c.user.id, sid))
    c.log("search:reviewed", detail={"search": sid, "known": len(known)})
    return {"id": sid, "checked_at": now}


@router.post("/searches/{sid}/end")
def search_end(sid: str, body: dict[str, Any] = Body(...), c: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    r = _search(c, sid)
    reason = _reason(body)
    if r["status"] != "active":
        raise HTTPException(409, "this saved search has already ended")
    with c.svc.store.tx() as conn:
        conn.execute("UPDATE saved_searches SET status='ended', ended_by=?, ended_at=?, end_reason=? WHERE id=?", (c.user.id, utcnow(), reason, sid))
    c.log("search:end", detail={"search": sid, "reason": reason})
    return {"id": sid, "status": "ended"}


# ---------------------------------------------------------------------------------------------- the work queue

def queue_entries(c: Ctx, entry) -> list[dict[str, Any]]:
    """Work items for the active case: watches with unreviewed activity, saved searches with new results."""
    if not c.case or c.case.status != "open" or c.user.id not in c.case.members or not c.user.has(*INVESTIGATORS):
        return []
    s = c.svc.store
    out = []
    gate = _gate(c)
    for r in s.query("SELECT * FROM watches WHERE case_id=? AND status='active' ORDER BY created_at DESC LIMIT 40", (c.case.id,)):
        w = dict(r)
        act = activity(c, w, gate, limit=200)
        if act["new"]:
            fresh = [e for e in act["events"] if e["new"]]
            key = sorted((e for e in fresh if e["priority"] != "low"), key=lambda e: PRIORITY[e["priority"]])
            reasons = list(dict.fromkeys(e["why"] for e in key if e["why"]))[:2]
            head = f"{act['new_key']} to read first: " + "; ".join(r[:1].lower() + r[1:] for r in reasons) if key else "Routine activity only"
            out.append(entry(act["events"][0]["at"], "watch", w["id"], f"New activity: {w['label']}",
                             f"{head} · {act['new']} new in all · watched by {_name(w['created_by'])}",
                             "new", "watch", w["id"], w["created_by"]))
    for r in s.query("SELECT * FROM saved_searches WHERE case_id=? AND status='active' ORDER BY created_at DESC LIMIT 20", (c.case.id,)):
        r = dict(r)
        res = _run(c, r["query"], r["types"])
        known = set(json.loads(r["known"]))
        n = sum(1 for x in res["results"] if x["id"] not in known)
        if n:
            out.append(entry(r["checked_at"], "search", r["id"], f"{n} new result{'' if n == 1 else 's'} for “{r['title']}”",
                             f"Saved search · {r['query']}", "new", "watch", r["id"], r["created_by"]))
    return out

"""DRISHTI REST API (FastAPI). Every endpoint goes through Guard and writes to the audit chain.

Headers
  X-DRISHTI-User   dev mode: id of a demo user (see guard/users.py DEV_USERS)
  Authorization    oidc mode: "Bearer <JWT>" from Keycloak
  X-DRISHTI-Case   the active case; required for any non-public object (purpose binding)
"""

from __future__ import annotations

import json
import mimetypes
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import cached_property
from typing import Any

from fastapi import Body, Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .. import __version__
from ..config import settings
from ..graph import GraphBuilder
from ..guard import DEV_USERS, AuditLog, AuthError, CaseCtx, Decision, Guard, PolicyError, User, mask_object, verify_bearer
from ..resolve.service import entity_cluster
from ..store import Store, utcnow


from .deps import Ctx, Services, get_ctx, services, set_services  # noqa: E402,F401


app = FastAPI(title="Mosaic", version=__version__, description="Weirwood Mosaic: open-source, ontology-based data fusion for Indian public institutions.")


@app.exception_handler(PolicyError)
async def _policy_error(_: Request, exc: PolicyError) -> JSONResponse:
    return JSONResponse(status_code=403, content={"detail": str(exc)})


# ---------------------------------------------------------------------------- basics
@app.get("/api/health")
def health() -> dict[str, Any]:
    s = services().store
    return {"ok": True, "version": __version__, "objects": s.count(), "auth_mode": settings.auth_mode, "time": utcnow()}


BODY_LIMIT = 25 * 1024 * 1024  # JSON bodies and photographs
EVIDENCE_LIMIT = 210 * 1024 * 1024  # exhibits (the handler itself refuses more than 200 MB)
LOCAL_CLIENTS = {"127.0.0.1", "::1", "localhost", "testclient"}


def _csp() -> str:
    from urllib.parse import urlsplit

    idp = ""
    if settings.auth_mode == "oidc":
        u = urlsplit(settings.oidc_issuer)
        idp = f" {u.scheme}://{u.netloc}"
    tiles = "https://tiles.openfreemap.org"
    return ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; font-src 'self' data:; "
            f"img-src 'self' data: blob: {tiles}; connect-src 'self' {tiles}{idp}; worker-src 'self' blob:; child-src blob:; "
            f"object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'{idp}")


@app.middleware("http")
async def guard_requests(request: Request, call_next):
    """Refuse oversized bodies and network access to dev auth; add security headers to every response."""
    from fastapi.responses import JSONResponse

    length = request.headers.get("content-length")
    limit = EVIDENCE_LIMIT if request.url.path.endswith("/evidence") else BODY_LIMIT
    if length and length.isdigit() and int(length) > limit:
        return JSONResponse({"detail": f"request body larger than {limit // (1024 * 1024)} MB"}, status_code=413)
    client = request.client.host if request.client else ""
    if settings.auth_mode == "dev" and client not in LOCAL_CLIENTS and not settings.dev_auth_network:
        # dev mode trusts a header to say who the user is; that must never be reachable from the network
        return JSONResponse({"detail": "dev auth mode answers only this machine; use DRISHTI_AUTH=oidc"}, status_code=403)
    response = await call_next(request)
    h = response.headers
    h.setdefault("Content-Security-Policy", _csp())
    h.setdefault("X-Content-Type-Options", "nosniff")
    h.setdefault("X-Frame-Options", "DENY")
    h.setdefault("Referrer-Policy", "no-referrer")
    h.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()")
    h.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    if request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https":
        h.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    if request.url.path.startswith("/api/"):
        h["Cache-Control"] = "no-store"  # case data must not sit in browser or proxy caches
    return response


@app.get("/api/auth/config")
def auth_config() -> dict[str, Any]:
    """What the web app needs to sign in: public values only (no secrets; the web client is a public PKCE client)."""
    if settings.auth_mode == "oidc":
        return {"mode": "oidc", "issuer": settings.oidc_issuer, "client_id": settings.oidc_client_id}
    return {"mode": "dev"}


@app.get("/api/dev/users")
def dev_users() -> list[dict[str, Any]]:
    if settings.auth_mode != "dev":
        raise HTTPException(404)
    return [u.public() for u in DEV_USERS.values()]


@app.get("/api/me")
def me(c: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    return {"user": c.user.public(), "cases": c.svc.guard.cases_for(c.user), "active_case": c.case.public() if c.case else None}


@app.get("/api/ontology")
def ontology() -> dict[str, Any]:
    return services().ontology.to_public_dict()


# ---------------------------------------------------------------------------- search & objects
@app.get("/api/search")
def search(q: str = Query(min_length=2, max_length=200), types: str | None = None, limit: int = 40, c: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    type_list = [t for t in (types or "").split(",") if t]
    limit = min(limit, 100)
    # over-fetch, then filter by policy, so records the user may see are not crowded out by
    # better-ranked records outside their jurisdiction
    ids = c.svc.store.search(q, type_list or None, limit=limit * 6)
    objs = c.svc.store.get_objects(ids)
    results, withheld = [], Counter()
    for i in ids:
        obj = objs.get(i)
        if not obj:
            continue
        d = c.decide(obj)
        if d.allow:
            if len(results) < limit:
                results.append(c.summary(obj))
        else:
            withheld[d.reason] += 1
    outcome = "denied" if withheld and not results and c.case is None else "ok"
    c.log("search", detail={"q": q, "types": type_list, "returned": len(results), "withheld": dict(withheld)},
          object_ids=[r["id"] for r in results], outcome=outcome)
    return {"query": q, "results": results, "withheld": [{"reason": r, "count": n} for r, n in withheld.items()]}


def _load_visible(c: Ctx, oid: str, action: str) -> dict[str, Any]:
    obj = c.svc.store.get_object(oid, with_geom=True)
    if obj is None:
        raise HTTPException(404, "no such object")
    d = c.decide(obj)
    if not d.allow:
        c.log(action, detail={"reason": d.reason}, object_ids=[oid], outcome="denied")
        raise HTTPException(403, d.reason)
    return obj


@app.get("/api/objects/{oid:path}/graph")
def object_graph(oid: str, depth: int = 1, c: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    _load_visible(c, oid, "graph")
    max_depth = c.case.max_depth if c.case else 1
    if depth > max_depth:
        c.log("graph", detail={"requested_depth": depth, "max_depth": max_depth}, object_ids=[oid], outcome="denied")
        raise HTTPException(403, f"depth {depth} exceeds the case limit {max_depth}; request expansion from a supervisor")
    g = GraphBuilder(c.svc.store, c.decide, c.case).neighbourhood(oid, depth)
    for n in g["nodes"]:
        n["district_name"] = c.svc.district_names.get(n.get("district") or "")
        if not n["group"]:
            obj = c.svc.store.get_object(n["id"])
            if obj:
                n["label"] = mask_object(c.svc.ontology, obj, c.user.clearance)["title"]
    c.log("graph", detail={"depth": depth, "nodes": len(g["nodes"]), "hidden": g["hidden"]},
          object_ids=[n["id"] for n in g["nodes"] if not n["group"]])
    g.update(depth=depth, max_depth=max_depth)
    return g


@app.get("/api/objects/{oid:path}/timeline")
def object_timeline(oid: str, c: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    obj = _load_visible(c, oid, "timeline")
    ids = entity_cluster(c.svc.store, oid) if obj["type"] == "Person" else [oid]
    events = []
    seen = set()
    for l in c.svc.store.links_for(ids):
        other = l["dst"] if l["src"] in ids else l["src"]
        if other in seen:
            continue
        seen.add(other)
        o = c.svc.store.get_object(other)
        if not o or not c.decide(o).allow:
            continue
        p = o["props"]
        when = p.get("occurred_at") or p.get("at") or p.get("effective")
        if when:
            events.append({"at": when, "object": c.summary(o), "via": l["type"]})
    events.sort(key=lambda e: e["at"])
    c.log("timeline", object_ids=[oid] + [e["object"]["id"] for e in events])
    return {"root": oid, "events": events}


@app.get("/api/objects/{oid:path}")
def get_object(oid: str, c: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    obj = _load_visible(c, oid, "view_object")
    out = c.summary(obj)
    if obj.get("geom") and obj["sensitivity"] == 0:
        out["geom"] = obj["geom"]
    out["provenance"] = c.svc.store.provenance(oid)
    viewed = [oid]
    if obj["type"] == "Person":
        members = []
        for mid in entity_cluster(c.svc.store, oid):
            if mid == oid:
                continue
            m = c.svc.store.get_object(mid)
            if m and c.decide(m).allow:
                members.append(c.summary(m))
                viewed.append(mid)
        out["resolved_records"] = members
        out["match_links"] = [
            {"id": l["id"], "other": l["dst"] if l["src"] == oid else l["src"], "status": l["status"], "confidence": l["confidence"],
             "explanation": l["props"].get("explanation")}
            for l in c.svc.store.links_for([oid], statuses=("auto", "confirmed", "candidate")) if l["type"] == "same_as"
        ]
    counts: Counter = Counter()
    for l in c.svc.store.links_for([oid]):
        counts[l["type"]] += 1
    out["link_counts"] = dict(counts)
    out["in_case"] = bool(c.case and oid in c.case.scope)
    c.log("view_object", object_ids=viewed)
    return out


@app.get("/api/path")
def path(a: str, b: str, c: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    _load_visible(c, a, "path")
    _load_visible(c, b, "path")
    res = GraphBuilder(c.svc.store, c.decide, c.case).shortest_path(a, b)
    ids = [n["id"] for n in res["nodes"]] if res else [a, b]
    c.log("path", detail={"a": a, "b": b, "found": bool(res)}, object_ids=ids)
    if not res:
        raise HTTPException(404, "no visible path within 6 hops")
    return res


# ---------------------------------------------------------------------------- explorer (aggregates)
@app.get("/api/explore/incidents")
def explore_incidents(district: str | None = None, section: str | None = None, month: str | None = None, kind: str | None = None,
                      c: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    c.require_role("io", "supervisor", "analyst", "viewer")
    if c.user.clearance < 1:
        raise HTTPException(403, "clearance too low")
    rows = [o for o in c.svc.store.objects_of_type("Incident")]

    def keep(o: dict[str, Any]) -> bool:
        p = o["props"]
        return ((not district or o["district_lgd"] == district) and (not section or section in p.get("sections", []))
                and (not month or str(p.get("occurred_at", ""))[:7] == month) and (not kind or p.get("kind") == kind))

    sel = [o for o in rows if keep(o)]
    by_district = Counter(o["district_lgd"] for o in sel)
    by_section = Counter(s for o in sel for s in o["props"].get("sections", []))
    by_month = Counter(str(o["props"].get("occurred_at", ""))[:7] for o in sel)
    by_kind = Counter(o["props"].get("kind") for o in sel)
    c.log("explore", detail={"type": "Incident", "filters": {"district": district, "section": section, "month": month, "kind": kind}, "count": len(sel)})
    names = c.svc.district_names
    return {
        "total": len(sel),
        "by_district": [{"key": k, "label": names.get(k, k), "count": v} for k, v in by_district.most_common()],
        "by_section": [{"key": k, "count": v} for k, v in by_section.most_common(20)],
        "by_month": [{"key": k, "count": v} for k, v in sorted(by_month.items())],
        "by_kind": [{"key": k, "count": v} for k, v in by_kind.most_common()],
        "note": "Counts are aggregate. Opening individual records needs an active case and is logged.",
    }


# ---------------------------------------------------------------------------- map (public data)
@app.get("/api/map/districts")
def map_districts() -> dict[str, Any]:
    feats = []
    for o in services().store.objects_of_type("AdminUnit", with_geom=True):
        if o.get("geom"):
            feats.append({"type": "Feature", "id": o["id"], "geometry": o["geom"],
                          "properties": {"id": o["id"], "name": o["props"]["name"], "lgd_code": o["props"]["lgd_code"]}})
    return {"type": "FeatureCollection", "features": feats}


@app.get("/api/map/hazards")
def map_hazards(active_only: bool = False) -> dict[str, Any]:
    s = services().store
    now = datetime.now(timezone.utc)
    affected: dict[str, list[str]] = defaultdict(list)
    for r in s.query("SELECT src, dst FROM links WHERE type='affects'"):
        affected[r["src"]].append(r["dst"].rsplit("-", 1)[-1])
    feats = []
    for h in s.objects_of_type("Hazard"):
        p = h["props"]
        try:
            expired = bool(p.get("expires")) and datetime.fromisoformat(p["expires"]) < now
        except ValueError:
            expired = False
        if active_only and expired:
            continue
        feats.append({
            "type": "Feature", "id": h["id"],
            "geometry": {"type": "Point", "coordinates": [h["lon"], h["lat"]]} if h["lon"] is not None else None,
            "properties": {"id": h["id"], "event": p.get("event"), "severity": p.get("severity"), "headline": p.get("headline"),
                           "sender": p.get("sender"), "expires": p.get("expires"), "expired": expired,
                           "districts": affected.get(h["id"], []), "geocode_method": p.get("geocode_method"),
                           "river": p.get("river"), "water_level_m": p.get("water_level_m"), "danger_level_m": p.get("danger_level_m")},
        })
    return {"type": "FeatureCollection", "features": feats}


@app.get("/api/map/assets")
def map_assets(district: str | None = None) -> dict[str, Any]:
    s = services().store
    sql = "SELECT id, title, lat, lon, district_lgd, props FROM objects WHERE type='Asset' AND lat IS NOT NULL"
    params: list[Any] = []
    if district:
        sql += " AND district_lgd=?"
        params.append(district)
    feats = []
    for r in s.query(sql, params):
        p = json.loads(r["props"])
        feats.append({"type": "Feature", "id": r["id"], "geometry": {"type": "Point", "coordinates": [r["lon"], r["lat"]]},
                      "properties": {"id": r["id"], "name": r["title"], "asset_type": p.get("asset_type"), "district": r["district_lgd"],
                                     "capacity": p.get("capacity"), "emergency": p.get("emergency")}})
    return {"type": "FeatureCollection", "features": feats}


@app.get("/api/hazards/{hid:path}/impact")
def hazard_impact(hid: str) -> dict[str, Any]:
    s = services().store
    h = s.get_object(hid)
    if not h or h["type"] != "Hazard":
        raise HTTPException(404)
    codes = [r["dst"].rsplit("-", 1)[-1] for r in s.query("SELECT dst FROM links WHERE type='affects' AND src=?", (hid,))]
    names = services().district_names
    hospitals = []
    if codes:
        q = ",".join("?" * len(codes))
        hospitals = [dict(r) for r in s.query(
            f"SELECT id, title AS name, district_lgd AS district, lat, lon FROM objects WHERE type='Asset' AND district_lgd IN ({q}) ORDER BY title LIMIT 500", codes)]
    dispatches = [dict(r) for r in s.query("SELECT * FROM dispatches WHERE hazard_id=? ORDER BY id DESC", (hid,))]
    return {"hazard": {"id": hid, **h["props"]}, "districts": [{"lgd_code": c, "name": names.get(c, c)} for c in codes],
            "hospitals_in_area": len(hospitals), "hospitals": hospitals[:200], "dispatches": dispatches}


# ---------------------------------------------------------------------------- actions (the kinetic layer)
@app.post("/api/actions/{name}")
def action(name: str, body: dict[str, Any] = Body(default_factory=dict), c: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    spec = c.svc.ontology.actions.get(name)
    if spec is None:
        raise HTTPException(404, f"unknown action {name}")
    allowed_roles = spec.get("roles", [])
    if allowed_roles and not c.user.has(*allowed_roles):
        c.log(f"action:{name}", detail={"needed": allowed_roles}, outcome="denied")
        raise HTTPException(403, f"{name} requires role: {' or '.join(allowed_roles)}")
    try:
        result = _run_action(name, body, c)
    except PolicyError as exc:
        c.log(f"action:{name}", detail={"body": _redact(body), "error": str(exc)}, outcome="denied")
        raise
    c.log(f"action:{name}", detail={"body": _redact(body), "result": result.get("log", result)}, object_ids=result.pop("object_ids", []))
    result.pop("log", None)
    return result


def _redact(body: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in body.items() if k not in ("password", "token")}


def _need(body: dict[str, Any], *keys: str) -> list[Any]:
    missing = [k for k in keys if body.get(k) in (None, "")]
    if missing:
        raise HTTPException(422, f"missing: {', '.join(missing)}")
    return [body[k] for k in keys]


def _run_action(name: str, body: dict[str, Any], c: Ctx) -> dict[str, Any]:
    g, s = c.svc.guard, c.svc.store
    if name == "open_case":
        purpose, legal_basis = _need(body, "purpose", "legal_basis")
        case_id = g.open_case(c.user, purpose=purpose, legal_basis=legal_basis, fir_no=body.get("fir_no"), members=body.get("members"))
        return {"case_id": case_id}
    if name == "close_case":
        (outcome,) = _need(body, "outcome")
        case = g.load_case(body.get("case_id") or (c.case.id if c.case else None))
        if not case:
            raise HTTPException(404, "no such case")
        days = body.get("retention_days")
        if days is not None and not c.user.has("supervisor"):
            raise PolicyError("only a supervisor may set a non-default retention period")
        return {"retention_until": g.close_case(c.user, case, outcome, retention_days=None if days is None else int(days))}
    if name == "set_legal_hold":
        case_id, reason = _need(body, "case_id", "reason")
        hold = bool(body.get("hold", True))
        with s.tx() as conn:
            conn.execute("UPDATE cases SET legal_hold=?, hold_reason=? WHERE id=?", (int(hold), reason if hold else None, case_id))
        return {"case_id": case_id, "legal_hold": hold}
    if name == "attach_external_record":
        order, source = _need(body, "legal_order", "source")
        if c.case is None:
            raise PolicyError("attach external records to an open case")
        made = []
        for i, rec in enumerate(body.get("records") or []):
            oid = s.upsert_object(rec["type"], rec["props"], source=source, record=f"{order}#{i}", origin_case=c.case.id, legal_order=order)
            made.append(oid)
            with s.tx() as conn:
                conn.execute("INSERT INTO case_objects(case_id,object_id,added_by,reason,added_at) VALUES(?,?,?,?,?) ON CONFLICT DO NOTHING",
                             (c.case.id, oid, c.user.id, f"obtained under {order}", utcnow()))
            if rec.get("link"):
                s.upsert_link(rec["link"]["type"], rec["link"].get("from", oid), rec["link"].get("to", oid), source=source, record=f"{order}#{i}")
        return {"created": made, "object_ids": made}
    if name == "destroy_order_data":
        order, reason = _need(body, "legal_order", "reason")
        from ..retention import destroy_order_data

        return {**destroy_order_data(s, order, c.user.id, reason), "object_ids": []}
    if name == "add_to_case":
        object_id, reason = _need(body, "object_id", "reason")
        obj = s.get_object(object_id)
        if not obj:
            raise HTTPException(404, "no such object")
        if obj["sensitivity"] > c.user.clearance:
            raise PolicyError("clearance below object sensitivity")
        g.add_to_case(c.user, c.case, object_id, reason)  # type: ignore[arg-type]
        return {"ok": True, "object_ids": [object_id]}
    if name == "request_expansion":
        depth, reason = _need(body, "depth", "reason")
        return {"request_id": g.request_expansion(c.user, c.case, int(depth), reason)}  # type: ignore[arg-type]
    if name == "approve_expansion":
        (rid,) = _need(body, "request_id")
        req = g.approve_expansion(c.user, rid)
        return {"approved": rid, "case_id": req["case_id"], "depth": req["depth"]}
    if name in ("confirm_match", "reject_match"):
        rid, reason = _need(body, "review_id", "reason")
        rows = s.query("SELECT * FROM review_queue WHERE id=?", (rid,))
        if not rows:
            raise HTTPException(404, "no such review item")
        item = rows[0]
        status = "confirmed" if name == "confirm_match" else "rejected"
        link_id = json.loads(item["explanation"]).get("link_id")
        with s.tx() as conn:
            changed = conn.execute("UPDATE review_queue SET status=?, decided_by=?, decided_at=?, reason=? WHERE id=? AND status='pending'",
                                   (status, c.user.id, utcnow(), reason, rid))
            if changed.rowcount != 1:
                raise HTTPException(409, "This match is no longer pending review; refresh the queue")
            if link_id:
                s.set_link_status(link_id, status)
        return {"review_id": rid, "status": status, "object_ids": [item["a"], item["b"]]}
    if name == "unmerge":
        link_id, reason = _need(body, "link_id", "reason")
        link = s.get_link(link_id)
        if not link or link["type"] != "same_as":
            raise HTTPException(404, "no such match link")
        s.set_link_status(link_id, "rejected")
        with s.tx() as conn:
            conn.execute("UPDATE review_queue SET status='rejected', decided_by=?, decided_at=?, reason=? WHERE a=? AND b=?",
                         (c.user.id, utcnow(), reason, *sorted((link["src"], link["dst"]))))
        return {"link_id": link_id, "status": "rejected", "object_ids": [link["src"], link["dst"]]}
    if name == "unmask":
        object_id, prop, reason = _need(body, "object_id", "property", "reason")
        if len(str(reason).strip()) < 10:
            raise PolicyError("state the reason for unmasking (at least 10 characters)")
        obj = s.get_object(object_id)
        if not obj:
            raise HTTPException(404)
        d = c.decide(obj)
        if not d.allow:
            raise PolicyError(d.reason)
        pdef = c.svc.ontology.object_type(obj["type"]).properties.get(prop)
        if not pdef or not pdef.mask:
            raise HTTPException(422, "property is not masked")
        return {"object_id": object_id, "property": prop, "value": obj["props"].get(prop), "object_ids": [object_id],
                "log": {"property": prop, "reason": reason}}
    if name == "flag_for_review":
        object_id, reason = _need(body, "object_id", "reason")
        return {"flagged": object_id, "object_ids": [object_id]}
    if name == "create_lead":
        title = _need(body, "title")[0]
        if c.case is None:
            raise PolicyError("open the case the lead belongs to")
        import secrets as _secrets
        lid = "lead:" + _secrets.token_hex(6)
        now = utcnow()
        with s.tx() as conn:
            conn.execute("INSERT INTO leads(id,case_id,subject_id,title,stage,assignee,notes,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                         (lid, c.case.id, body.get("subject_id"), title, body.get("stage") or "Lead", body.get("assignee") or c.user.id,
                          json.dumps([{"by": c.user.id, "at": now, "text": body.get("note") or "Lead created"}]), c.user.id, now, now))
        return {"lead_id": lid, "object_ids": [body["subject_id"]] if body.get("subject_id") else []}
    if name == "move_lead":
        lid, stage = _need(body, "lead_id", "stage")
        rows = s.query("SELECT * FROM leads WHERE id=?", (lid,))
        if not rows:
            raise HTTPException(404, "no such lead")
        if stage == "Action authorised" and not c.user.has("supervisor"):
            raise PolicyError("only a supervisor can authorise action on a lead")
        notes = json.loads(rows[0]["notes"]) + [{"by": c.user.id, "at": utcnow(), "text": body.get("note") or f"moved to {stage}"}]
        with s.tx() as conn:
            conn.execute("UPDATE leads SET stage=?, notes=?, updated_at=? WHERE id=?", (stage, json.dumps(notes), utcnow(), lid))
        return {"lead_id": lid, "stage": stage}
    if name == "dispatch_resource":
        resource, quantity, admin_unit = _need(body, "resource", "quantity", "admin_unit")
        with s.tx() as conn:
            conn.execute("INSERT INTO dispatches(hazard_id,admin_unit,resource,quantity,dispatched_by,dispatched_at) VALUES(?,?,?,?,?,?)",
                         (body.get("hazard_id"), admin_unit, resource, int(quantity), c.user.id, utcnow()))
        return {"ok": True}
    raise HTTPException(501, f"action {name} not implemented")


# ---------------------------------------------------------------------------- cases, review, expansions
@app.get("/api/cases")
def cases(c: Ctx = Depends(get_ctx)) -> list[dict[str, Any]]:
    return c.svc.guard.cases_for(c.user)


@app.get("/api/cases/{case_id}/objects")
def case_objects(case_id: str, c: Ctx = Depends(get_ctx)) -> list[dict[str, Any]]:
    case = c.svc.guard.load_case(case_id)
    if not case or c.user.id not in case.members:
        raise HTTPException(403, "not a member of this case")
    rows = c.svc.store.query("SELECT object_id, added_by, reason, added_at FROM case_objects WHERE case_id=? ORDER BY added_at", (case_id,))
    objs = c.svc.store.get_objects(r["object_id"] for r in rows)
    out = [{**c.summary(objs[r["object_id"]]), "added_by": r["added_by"], "reason": r["reason"], "added_at": r["added_at"]}
           for r in rows if r["object_id"] in objs]
    c.log("case_objects", object_ids=[o["id"] for o in out])
    return out


@app.get("/api/expansions")
def expansions(c: Ctx = Depends(get_ctx)) -> list[dict[str, Any]]:
    c.require_role("supervisor", "io", "analyst")
    return [dict(r) for r in c.svc.store.query("SELECT * FROM expansion_requests WHERE status='pending' ORDER BY requested_at")]


@app.get("/api/review")
def review_queue(limit: int = 50, c: Ctx = Depends(get_ctx)) -> list[dict[str, Any]]:
    c.require_role("analyst", "supervisor", "steward")
    rows = c.svc.store.query("SELECT * FROM review_queue WHERE status='pending' ORDER BY probability DESC LIMIT ?", (limit,))
    objs = c.svc.store.get_objects([r["a"] for r in rows] + [r["b"] for r in rows])
    out = []
    for r in rows:
        if r["a"] in objs and r["b"] in objs:
            out.append({"id": r["id"], "probability": r["probability"], "explanation": json.loads(r["explanation"]),
                        "a": c.summary(objs[r["a"]]), "b": c.summary(objs[r["b"]])})
    c.svc.audit.append(user_id=c.user.id, role=c.user.primary_role, action="review_queue", purpose="data_quality_review",
                       object_ids=[x for o in out for x in (o["a"]["id"], o["b"]["id"])], client=c.client)
    return out


# ---------------------------------------------------------------------------- oversight
@app.get("/api/audit")
def audit_rows(user: str | None = None, object_id: str | None = None, case_id: str | None = None, limit: int = 200,
               c: Ctx = Depends(get_ctx)) -> list[dict[str, Any]]:
    c.require_role("auditor")
    rows = c.svc.audit.rows(user_id=user, object_id=object_id, case_id=case_id, limit=min(limit, 1000))
    c.log("audit_read", detail={"user": user, "object_id": object_id, "case_id": case_id, "rows": len(rows)})
    return rows


@app.get("/api/audit/verify")
def audit_verify(c: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    c.require_role("auditor", "admin")
    return c.svc.audit.verify()


@app.get("/api/audit/alerts")
def audit_alerts(c: Ctx = Depends(get_ctx)) -> list[dict[str, Any]]:
    c.require_role("auditor")
    return c.svc.audit.alerts()


@app.post("/api/audit/seal")
def audit_seal(c: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    c.require_role("auditor", "admin")
    return c.svc.audit.seal_day()


@app.get("/api/quality")
def quality(c: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    c.require_role("analyst", "supervisor", "steward", "auditor", "admin")
    s = c.svc.store
    return {"resolve": s.get_meta("resolve_metrics"), "lgd": (s.get_meta("data_quality_lgd") or [])[:200], "sachet": s.get_meta("sachet_last_run")}


@app.get("/api/transparency")
def transparency() -> dict[str, Any]:
    """Aggregate statistics anyone may read (design doc safeguard 10)."""
    s = services().store
    by_action = {r["action"]: r["n"] for r in s.query("SELECT action, COUNT(*) n FROM audit GROUP BY action ORDER BY n DESC")}
    by_outcome = {r["outcome"]: r["n"] for r in s.query("SELECT outcome, COUNT(*) n FROM audit GROUP BY outcome")}
    purposes = {r["purpose"]: r["n"] for r in s.query("SELECT purpose, COUNT(*) n FROM cases GROUP BY purpose")}
    sources = {r["source"]: r["n"] for r in s.query("SELECT source, COUNT(DISTINCT object_id) n FROM provenance GROUP BY source ORDER BY n DESC")}
    return {"generated_at": utcnow(), "audit_events_by_action": by_action, "audit_events_by_outcome": by_outcome,
            "cases_by_purpose": purposes, "objects_by_source": sources, "chain": AuditLog(s).verify()}


# ---------------------------------------------------------------------------- web UI
from . import area, casework, connect, faces, intake, intel, investigation, patterns, reports, today, watch  # noqa: E402

app.include_router(intel.router)
app.include_router(casework.router)
app.include_router(investigation.router)
app.include_router(faces.router)
app.include_router(connect.router)
app.include_router(patterns.router)
app.include_router(intake.router)
app.include_router(today.router)
app.include_router(watch.router)
app.include_router(area.router)
app.include_router(reports.router)


@app.on_event("startup")
def _start_retention() -> None:
    import os

    from ..retention import start_scheduler

    hours = float(os.environ.get("DRISHTI_RETENTION_INTERVAL_HOURS", "24"))
    if hours > 0:
        start_scheduler(services().store, hours)

mimetypes.add_type("text/javascript", ".mjs")  # module workers (MapLibre) need a JavaScript MIME type
if settings.web_dist.exists():
    app.mount("/", StaticFiles(directory=str(settings.web_dist), html=True), name="web")



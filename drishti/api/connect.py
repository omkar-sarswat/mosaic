"""Connections API: explain how two entities are linked, list who a person is associated with
and why, and show the conduct flags on a person.

Access rules (the same ones the rest of the dossier uses):
  * every endpoint needs an open case the caller is on (purpose binding);
  * each entity returned is run through Guard (clearance, jurisdiction, case) and dropped if the
    caller may not see it — the engine scores broadly, disclosure is gated;
  * every query is written to the audit chain with the entities it touched.
Flags are conduct-only (see drishti/analytics/behaviour.FLAG_INPUTS); no protected attribute is
read, so a flag can be put to a court without failing an Article 14/15 challenge.
"""

from __future__ import annotations

import json
from collections import defaultdict, deque
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from ..analytics.behaviour import flags_for, scoreboard
from ..analytics.inference import KIND_LABEL, LINK_TYPE, associates, pair_bases
from .deps import Ctx, get_ctx, services
from .intel import _cache, _lock, _visible, ledger

router = APIRouter(prefix="/api/intel", tags=["connections"])

# Links that say little about a personal connection (shared post office, same district) are not
# walked when explaining how two people are tied together.
SKIP_TYPES = {"located_in", "affects", "reported_at", "part_of", "beneficiary_of", LINK_TYPE}
HUB_DEGREE = 60  # a node busier than this (a DBT account, a merchant, a police station) is a
                 # thoroughfare, not a connection, so it is never used as a stepping stone.
PATH_HOPS = 5

EDGE_LABEL = {
    "uses_phone": "uses number", "holds_account": "holds account", "signatory_of": "signatory of",
    "sim_in_device": "SIM in handset", "owns": "owns", "director_of": "director of", "controls": "controls",
    "relative_of": "relative of", "associate_of": "associate of", "resides_at": "lives at",
    "accused_in": "accused in", "complainant_in": "complainant in", "victim_in": "victim in",
    "mentions": "named in", "transferred_to": "sent money to", "called": "called",
    "same_as": "same person as", "employee_of": "works at", "registered_at": "registered at",
    "director_of (inbound)": "run by", "holds_account (inbound)": "held by",
}


def _hubs() -> set[str]:
    """Node ids whose global degree is above HUB_DEGREE (computed once, cached, cleared on refresh)."""
    with _lock:
        if "hubs" not in _cache:
            s = services().store
            deg: dict[str, int] = defaultdict(int)
            for col in ("src", "dst"):
                for r in s.query(f"SELECT {col} node, COUNT(*) n FROM links WHERE status IN ('active','auto','confirmed') "
                                 f"AND type NOT IN ({','.join('?' * len(SKIP_TYPES))}) GROUP BY {col}", tuple(SKIP_TYPES)):
                    deg[r["node"]] += r["n"]
            _cache["hubs"] = {n for n, d in deg.items() if d > HUB_DEGREE}
        return _cache["hubs"]


def _require_case(c: Ctx) -> None:
    if not c.case or c.case.status != "open" or c.user.id not in c.case.members:
        raise HTTPException(403, "select an open case you are a member of to state your purpose")


@router.get("/flags/{oid:path}")
def flags(oid: str, c: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    _require_case(c)
    obj = c.svc.store.get_object(oid)
    if not obj or not c.decide(obj).allow:
        raise HTTPException(403, "not visible in this case")
    rows = flags_for(c.svc.store, oid)
    c.log("flags", object_ids=[oid], detail={"flags": len(rows)})
    return {"object": c.summary(obj), "flags": rows,
            "note": "Conduct indicators to look into, not findings. Each lists the records it rests on. No religion, caste, gender, age or political/associational data is used."}


@router.get("/associates/{oid:path}")
def associates_of(oid: str, limit: int = Query(40, ge=1, le=120), c: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    _require_case(c)
    obj = c.svc.store.get_object(oid)
    if not obj or obj["type"] != "Person" or not c.decide(obj).allow:
        raise HTTPException(403, "not a person visible in this case")
    rows = associates(c.svc.store, oid, limit=limit * 2)
    others = _visible(c, [r["other"] for r in rows])
    scope = set(c.case.scope)
    out = []
    for r in rows:
        o = others.get(r["other"])
        if not o:
            continue
        out.append({**c.summary(o), "score": r["score"], "summary": r["summary"], "kinds": r.get("kinds", []),
                    "bases": r.get("bases", []), "in_case": r["other"] in scope})
        if len(out) >= limit:
            break
    c.log("associates", object_ids=[oid] + [a["id"] for a in out], detail={"returned": len(out)})
    return {"object": c.summary(obj), "associates": out, "labels": KIND_LABEL,
            "note": "Inferred from shared devices, accounts, money, calls, addresses and travel. A lead for an analyst; confirm before acting. Use 'add to case' to bring one in (audited)."}


@router.get("/connect")
def connect(a: str, b: str, c: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    """Shortest chain of records linking two entities the caller can already see."""
    _require_case(c)
    s = services().store
    oa, ob = s.get_object(a), s.get_object(b)
    if not oa or not ob:
        raise HTTPException(404, "no such entity")
    if not c.decide(oa).allow or not c.decide(ob).allow:
        raise HTTPException(403, "both entities must be visible in this case")
    hubs = _hubs() - {a, b}
    # bidirectional BFS over the link graph, skipping hubs as intermediate nodes
    parents: dict[str, dict[str, tuple[str, dict]]] = {"f": {a: None}, "b": {b: None}}
    frontier = {"f": {a}, "b": {b}}
    meet: str | None = None
    for _ in range(PATH_HOPS):
        side = "f" if len(frontier["f"]) <= len(frontier["b"]) else "b"
        nxt: set[str] = set()
        links = s.links_for(list(frontier[side]))
        for l in links:
            if l["type"] in SKIP_TYPES:
                continue
            for u, v in ((l["src"], l["dst"]), (l["dst"], l["src"])):
                if u in frontier[side] and v not in parents[side]:
                    parents[side][v] = (u, l)
                    if v not in hubs:
                        nxt.add(v)
                    if v in parents["b" if side == "f" else "f"]:
                        meet = v
        frontier[side] = nxt
        if meet or not nxt:
            break
    if not meet:
        c.log("connect", object_ids=[a, b], detail={"found": False})
        return {"from": c.summary(oa), "to": c.summary(ob), "connected": False,
                "note": f"No chain of {PATH_HOPS} steps or fewer through non-hub records."}

    def walk(side: str) -> list[tuple[str, dict]]:
        chain, node = [], meet
        while parents[side][node] is not None:
            prev, link = parents[side][node]
            chain.append((node, link))
            node = prev
        return chain

    seq = list(reversed(walk("f"))) + walk("b")
    node_ids = [a] + [n for n, _ in seq]
    if b not in node_ids:
        node_ids.append(b)
    objs = _visible(c, node_ids)
    steps = []
    for (node, link) in seq:
        frm = link["src"] if link["dst"] == node else link["dst"]
        lt = link["type"] + (" (inbound)" if link["dst"] == node and link["src"] == frm else "")
        steps.append({"from": frm, "to": node, "type": link["type"], "label": EDGE_LABEL.get(lt, link["type"].replace("_", " ")),
                      "via": {k: objs[k]["title"] for k in (frm, node) if k in objs}})
    c.log("connect", object_ids=node_ids, detail={"found": True, "hops": len(steps)})
    return {"from": c.summary(oa), "to": c.summary(ob), "connected": True, "hops": len(steps),
            "nodes": [c.summary(objs[n]) for n in node_ids if n in objs], "steps": steps}


@router.get("/why-linked")
def why_linked(a: str, b: str, c: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    """The shared-behaviour evidence (handset, money, calls, travel…) between two people."""
    _require_case(c)
    s = services().store
    oa, ob = s.get_object(a), s.get_object(b)
    if not oa or not ob or not c.decide(oa).allow or not c.decide(ob).allow:
        raise HTTPException(403, "both people must be visible in this case")
    r = pair_bases(s, a, b)
    c.log("why_linked", object_ids=[a, b], detail={"score": r["score"]})
    return {"from": c.summary(oa), "to": c.summary(ob), **r}


@router.get("/flagboard")
def flagboard(limit: int = Query(80, ge=1, le=200), c: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    """People carrying the most conduct flags, restricted to the active case's network."""
    _require_case(c)
    c.require_role("io", "supervisor", "analyst")
    from .intel import case_intel
    net = case_intel(c.case.id)["net"]
    scope = {n for n in net["nodes"] if n.startswith("person:")} | set(c.case.scope)
    board = [r for r in scoreboard(c.svc.store, limit=600) if r["subject_id"] in scope]
    objs = _visible(c, [r["subject_id"] for r in board])
    out = []
    for r in board[:limit]:
        o = objs.get(r["subject_id"])
        if o:
            out.append({**c.summary(o), "score": r["score"], "flags": r["n"], "high": r["high"], "codes": r["codes"]})
    c.log("flagboard", detail={"case": c.case.id, "returned": len(out)})
    return {"people": out, "note": "Scoped to this case's network. Conduct flags only; open a person to see the evidence behind each flag."}

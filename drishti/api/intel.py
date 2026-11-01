"""Intelligence API: 360-degree dossiers, money tracing, case boards, alerts, globe layers.

Every response still goes through Guard (purpose, clearance, jurisdiction) and the audit chain.
Analytics results (ledger, case networks, suspect ranks) are cached in-process and rebuilt
when the data changes.
"""

from __future__ import annotations

import json
import math
import threading
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from ..analytics import behaviour, inference
from ..analytics.money import Ledger, account_summary, entity_accounts, trace
from ..analytics.network import build_network, case_seeds, rank_suspects
from ..guard import mask_object
from ..resolve.service import entity_cluster
from ..report import inr
from ..store import utcnow
from ..synth.world import CITIES, FOREIGN
from .deps import Ctx, get_ctx, services

router = APIRouter(prefix="/api/intel", tags=["intel"])

_cache: dict[str, Any] = {}
_lock = threading.RLock()

LEAD_STAGES = ["Lead", "Investigating", "Awaiting approval", "Action authorised", "Closed"]
# Incidents are case records: one colour for all agencies (the agency is named in the label), not a palette per agency.
AGENCY_COLOURS = {a: "#d95926" for a in ("ED", "CBI", "NIA", "NCB", "MAHARASHTRA-CYBER", "IB", "RAW", "FIU-IND", "STATE-POLICE-MH")}


def ledger() -> Ledger:
    with _lock:
        if "ledger" not in _cache:
            _cache["ledger"] = Ledger(services().store)
        return _cache["ledger"]


def case_intel(case_id: str) -> dict[str, Any]:
    with _lock:
        key = f"case:{case_id}"
        if key not in _cache:
            s = services().store
            seeds = case_seeds(s, case_id)
            net = build_network(s, seeds, ledger())
            sus = rank_suspects(s, net, ledger())
            _cache[key] = {"net": net, "suspects": sus, "at": utcnow()}
        return _cache[key]


def invalidate() -> None:
    with _lock:
        _cache.clear()


def city_coords(city: str | None) -> tuple[float, float] | None:
    if not city:
        return None
    if city in CITIES:
        return CITIES[city][2], CITIES[city][1]
    if city in FOREIGN:
        return FOREIGN[city][2], FOREIGN[city][1]
    return None


def _visible(c: Ctx, ids: list[str]) -> dict[str, dict[str, Any]]:
    objs = c.svc.store.get_objects(ids)
    return {k: v for k, v in objs.items() if c.decide(v).allow}


def _summ(c: Ctx, obj: dict[str, Any]) -> dict[str, Any]:
    return c.summary(obj)


def _alerts_for(ids: list[str]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    if not ids:
        return out
    s = services().store
    for i in range(0, len(ids), 400):
        chunk = ids[i:i + 400]
        for r in s.query(f"SELECT * FROM alerts WHERE subject_id IN ({','.join('?' * len(chunk))}) ORDER BY score DESC", chunk):
            d = dict(r)
            d["details"] = json.loads(d["details"])
            out[d["subject_id"]].append(d)
    return out


# ---------------------------------------------------------------------------- home dashboard
@router.get("/home")
def home(c: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    s = c.svc.store
    counts = {r["type"]: r["n"] for r in s.query("SELECT type, COUNT(*) n FROM objects GROUP BY type")}
    tx = s.query("SELECT COUNT(*) n, COALESCE(SUM(amount),0) v FROM txns")[0]
    calls = s.query("SELECT COUNT(*) n FROM cdrs")[0]["n"]
    trips = s.query("SELECT COUNT(*) n FROM travel")[0]["n"]
    by_rule = [{"rule": r["rule"], "n": r["n"], "amount": r["v"]} for r in s.query(
        "SELECT rule, COUNT(*) n, COALESCE(SUM(amount),0) v FROM alerts GROUP BY rule ORDER BY n DESC")]
    by_sev = {r["severity"]: r["n"] for r in s.query("SELECT severity, COUNT(*) n FROM alerts GROUP BY severity")}
    flagged = s.query("SELECT COALESCE(SUM(amount),0) v FROM alerts WHERE severity='high' AND subject_type='BankAccount'")[0]["v"]
    top = [dict(r) for r in s.query("SELECT id, rule, severity, subject_id, subject_type, score, amount, summary FROM alerts ORDER BY score DESC, amount DESC LIMIT 14")]
    subj = s.get_objects([a["subject_id"] for a in top])
    for a in top:
        o = subj.get(a["subject_id"])
        a["subject"] = mask_object(c.svc.ontology, o, c.user.clearance)["title"] if o else a["subject_id"]
        if o and o["type"] == "BankAccount":
            h = ledger().holder.get(o["id"])
            a["holder"] = ledger().names.get(h, "") if h else ""
            a["holder_id"] = h
    cases = []
    for r in c.svc.guard.cases_for(c.user):
        info = {"id": r["id"], "title": r["title"] or r["purpose"], "agency": r["agency"], "purpose": r["purpose"], "status": r["status"], "opened_at": r["opened_at"]}
        if r["status"] == "open":
            ci = case_intel(r["id"])
            info["suspects"] = len([x for x in ci["suspects"] if x["score"] >= 50])
            info["top"] = [{"id": x["id"], "name": x["name"], "score": x["score"], "role": x["role"]} for x in ci["suspects"][:3]]
            info["network"] = len(ci["net"]["nodes"])
        cases.append(info)
    incidents = [dict(r) for r in s.query(f"SELECT id, title, props FROM objects WHERE type='Incident' ORDER BY {s.json_text('props', 'occurred_at')} DESC LIMIT 400")]
    by_agency = Counter(json.loads(i["props"]).get("agency", "?") for i in incidents)
    recent = []
    for i in incidents:
        p = json.loads(i["props"])
        if p.get("agency") in ("ED", "CBI", "NIA", "NCB", "FIU-IND", "I4C"):
            recent.append({"id": i["id"], "title": i["title"], "agency": p.get("agency"), "kind": p.get("kind"), "summary": p.get("summary"),
                           "occurred_at": p.get("occurred_at"), "amount": p.get("amount")})
        if len(recent) >= 10:
            break
    c.log("home")
    return {"counts": {"persons": counts.get("Person", 0), "organisations": counts.get("Organisation", 0), "accounts": counts.get("BankAccount", 0),
                       "phones": counts.get("Phone", 0), "vehicles": counts.get("Vehicle", 0), "properties": counts.get("Property", 0),
                       "incidents": counts.get("Incident", 0), "transactions": tx["n"], "volume": tx["v"], "calls": calls, "trips": trips,
                       "alerts": sum(by_sev.values()), "flagged_amount": flagged},
            "alerts_by_rule": by_rule, "alerts_by_severity": by_sev, "top_alerts": top, "cases": cases, "incidents_by_agency": dict(by_agency),
            "recent_cases": recent, "monthly_volume": [{"month": r["m"], "amount": r["v"], "n": r["n"]} for r in s.query(
                "SELECT substr(ts,1,7) m, SUM(amount) v, COUNT(*) n FROM txns GROUP BY m ORDER BY m")]}


# ---------------------------------------------------------------------------- 360 dossier
@router.get("/entity/{oid:path}")
def entity(oid: str, case: str | None = None, c: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    s, ont = c.svc.store, c.svc.ontology
    obj = s.get_object(oid, with_geom=True)
    if not obj:
        raise HTTPException(404, "no such object")
    d = c.decide(obj)
    if not d.allow:
        c.log("dossier", detail={"reason": d.reason}, object_ids=[oid], outcome="denied")
        raise HTTPException(403, d.reason)
    L = ledger()
    cluster = entity_cluster(s, oid) if obj["type"] == "Person" else [oid]
    links = s.links_for(cluster)
    other_ids = list({x for l in links for x in (l["src"], l["dst"])} - set(cluster))
    vis = _visible(c, other_ids)
    viewed = list(cluster) + list(vis)
    me = c.summary(obj)
    if obj.get("geom") and obj["sensitivity"] == 0:
        me["geom"] = obj["geom"]
    out: dict[str, Any] = {"object": me, "provenance": s.provenance(oid)}
    # documents and identity
    docs = []
    for k, label in (("aadhaar", "Aadhaar"), ("pan", "PAN"), ("passport_no", "Passport"), ("dl_no", "Driving licence"), ("voter_id", "Voter ID (EPIC)"),
                     ("cin", "CIN"), ("gstin", "GSTIN"), ("email", "Email")):
        if me["props"].get(k):
            src = next((p["source"] for p in out["provenance"] if p["prop"] == k), "")
            docs.append({"key": k, "label": label, "value": me["props"][k], "masked": k in me["masked"], "source": src})
    out["documents"] = docs
    # photographs on record for the resolved person, each with where it came from and why it is held
    out["photos"] = []
    if obj["type"] == "Person":
        marks = ",".join("?" * len(cluster))
        out["photos"] = [dict(r) for r in s.query(
            f"SELECT id, object_id, case_id, source, legal_basis, added_by, added_at, width, height FROM media "
            f"WHERE kind='photo' AND object_id IN ({marks}) ORDER BY added_at", cluster)]
        for p in out["photos"]:
            p["synthetic"] = str(p["added_by"]).startswith("system:demo")
    # fused source records
    recs = []
    for rid in cluster:
        if rid == oid:
            continue
        r = s.get_object(rid)
        if r and c.decide(r).allow:
            prov = s.provenance(rid)
            recs.append({**c.summary(r), "sources": sorted({p["source"] for p in prov})})
    out["fused_records"] = recs
    out["sources"] = sorted({p["source"] for p in out["provenance"]} | {src for r in recs for src in r["sources"]})
    # group linked objects
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    rel_of: dict[str, list[str]] = defaultdict(list)
    for l in links:
        other = l["dst"] if l["src"] in cluster else l["src"]
        if other in vis:
            rel_of[other].append(l["type"] if l["src"] in cluster else f"{l['type']} (inbound)")
    alerts = _alerts_for(list(cluster) + list(vis))
    for other, rels in rel_of.items():
        o = vis[other]
        item = {**c.summary(o), "relations": sorted(set(rels)), "alerts": alerts.get(other, [])[:5]}
        groups[o["type"]].append(item)
    # accounts with money summaries
    accts = []
    for a in groups.get("BankAccount", []):
        summ = account_summary(L, a["id"])
        accts.append({**a, "summary": {k: summ[k] for k in ("in_total", "out_total", "in_count", "out_count", "cash_in", "cash_out", "first", "last")},
                      "monthly": summ["monthly"], "top_senders": summ["top_senders"][:5], "top_receivers": summ["top_receivers"][:5]})
    if obj["type"] == "BankAccount":
        summ = account_summary(L, oid)
        out["account_summary"] = summ
    out["accounts"] = sorted(accts, key=lambda x: -(x["summary"]["in_total"] + x["summary"]["out_total"]))
    out["crypto"] = groups.get("CryptoWallet", [])
    out["phones"] = groups.get("Phone", [])
    out["vehicles"] = groups.get("Vehicle", [])
    out["properties"] = groups.get("Property", [])
    out["devices"] = groups.get("Device", [])
    # handsets are tied to the SIMs, not to the person: reach them through the person's own numbers
    seen_dev = {x["id"] for x in out["devices"]}
    dev_ids = {l["dst"]: l["src"] for l in s.links_for([p["id"] for p in groups.get("Phone", [])]) if l["type"] == "sim_in_device" and l["dst"] not in seen_dev}
    for did, dev in s.get_objects(list(dev_ids)).items():
        if c.decide(dev).allow:
            out["devices"].append({**c.summary(dev), "relations": ["sim_in_device (via phone)"], "alerts": []})
    out["organisations"] = groups.get("Organisation", [])
    out["locations"] = groups.get("Location", [])
    out["incidents"] = sorted(groups.get("Incident", []), key=lambda x: str(x["props"].get("occurred_at", "")), reverse=True)
    out["people"] = groups.get("Person", [])
    # associates: family, frequent contacts, co-directors, shared handset, money partners
    assoc: dict[str, dict[str, Any]] = {}

    def add_assoc(pid: str, why: str, weight: float) -> None:
        if pid in cluster or pid not in vis_people:
            return
        a = assoc.setdefault(pid, {**c.summary(vis_people[pid]), "why": [], "strength": 0.0})
        a["why"].append(why)
        a["strength"] += weight

    phone_ids = [p["id"] for p in out["phones"]]
    org_ids = [o["id"] for o in out["organisations"]]
    acct_ids = [a["id"] for a in out["accounts"]]
    second = s.links_for(phone_ids + org_ids + acct_ids + [x["id"] for x in out["devices"]])
    cand = {x for l in second for x in (l["src"], l["dst"])}
    # owners of counterpart phones / accounts
    phone_owner, acct_owner = {}, {}
    for l in s.links_for([x for x in cand if x.startswith(("phone:", "bankaccount:"))], statuses=("active",)):
        if l["type"] == "uses_phone":
            phone_owner[l["dst"]] = l["src"]
        elif l["type"] in ("holds_account", "signatory_of"):
            acct_owner.setdefault(l["dst"], l["src"])
    vis_people = _visible(c, [x for x in set(phone_owner.values()) | set(acct_owner.values()) | {l["src"] for l in second if l["src"].startswith("person:")}
                              | {x for x in vis if x.startswith("person:")}])
    for pid, rels in rel_of.items():
        if pid.startswith("person:"):
            add_assoc(pid, "family" if "relative_of" in " ".join(rels) else rels[0].replace("_", " "), 3)
    for l in second:
        if l["type"] == "called":
            other_ph = l["dst"] if l["src"] in phone_ids else l["src"]
            n = l["props"].get("count", 1)
            if other_ph in phone_owner:
                add_assoc(phone_owner[other_ph], f"{n} calls", min(5, n / 4))
        elif l["type"] == "director_of" and l["dst"] in org_ids:
            add_assoc(l["src"], f"co-director of {vis.get(l['dst'], {}).get('title', 'a company')}", 3)
        elif l["type"] == "transferred_to":
            other_a = l["dst"] if l["src"] in acct_ids else l["src"]
            if other_a in acct_owner:
                add_assoc(acct_owner[other_a], f"money Rs {l['props'].get('total', 0):,.0f}", 2 + min(4, (l['props'].get('total', 0) or 0) / 2_500_000))
        elif l["type"] == "sim_in_device":
            ph = l["src"]
            if ph in phone_owner and ph not in phone_ids:
                add_assoc(phone_owner[ph], "shared handset", 4)
    out["associates"] = sorted(assoc.values(), key=lambda a: -a["strength"])[:40]
    # money, travel, alerts, timeline
    acc_all = [a["id"] for a in out["accounts"]] if obj["type"] != "BankAccount" else [oid]
    monthly = defaultdict(lambda: [0.0, 0.0])
    tin = tout = 0.0
    for a in acc_all:
        for t in L.inc.get(a, []):
            monthly[t[1][:7]][0] += t[4]
            tin += t[4]
        for t in L.out.get(a, []):
            monthly[t[1][:7]][1] += t[4]
            tout += t[4]
    out["money"] = {"in_total": round(tin, 2), "out_total": round(tout, 2), "accounts": len(acc_all),
                    "monthly": [{"month": m, "in": round(v[0], 2), "out": round(v[1], 2)} for m, v in sorted(monthly.items())]}
    out["travel"] = [dict(r) for r in s.query(f"SELECT * FROM travel WHERE person_id IN ({','.join('?' * len(cluster))}) ORDER BY ts DESC", cluster)]
    own_alerts = [a for x in cluster for a in alerts.get(x, [])]
    rel_alerts = [a for x in vis for a in alerts.get(x, []) if x.startswith(("bankaccount:", "organisation:", "cryptowallet:"))]
    out["alerts"] = sorted(own_alerts + rel_alerts, key=lambda a: -a["score"])
    tl = []
    for i in out["incidents"]:
        tl.append({"at": i["props"].get("occurred_at"), "kind": "case", "title": f"{i['props'].get('agency', '')} {i['title']}", "detail": i["props"].get("summary"), "id": i["id"]})
    for t in out["travel"]:
        mode = {"air": "Flight", "rail": "Train", "bus": "Bus"}.get(t.get("mode") or "air", "Journey")
        tl.append({"at": t["ts"], "kind": "travel", "title": f"{mode} {t['from_city']} → {t['to_city']}", "detail": f"PNR {t['pnr']}", "id": None})
    for pr in out["properties"]:
        tl.append({"at": pr["props"].get("registered_on"), "kind": "asset", "title": f"Property registered: {pr['title']}", "detail": inr(pr['props'].get('value') or 0), "id": pr["id"]})
    for a in out["accounts"]:
        tl.append({"at": a["props"].get("opened_on"), "kind": "account", "title": f"Account opened at {a['props'].get('bank', '')}", "detail": a["title"], "id": a["id"]})
    big = []
    for a in acc_all:
        big += [(t, "in") for t in L.inc.get(a, []) if t[4] >= 5_00_000] + [(t, "out") for t in L.out.get(a, []) if t[4] >= 5_00_000]
    for t, dirn in sorted(big, key=lambda x: -x[0][4])[:30]:
        cp = t[2] if dirn == "in" else t[3]
        tl.append({"at": t[1], "kind": "money_in" if dirn == "in" else "money_out", "title": f"{inr(t[4])} {'from' if dirn == 'in' else 'to'} {L.label(cp)}",
                   "detail": f"{t[5]} · {t[6]}", "id": L.holder.get(cp or "")})
    out["timeline"] = sorted([e for e in tl if e["at"]], key=lambda e: e["at"], reverse=True)
    # conduct flags and inferred associations (persons only)
    if obj["type"] == "Person":
        flags: list[dict[str, Any]] = []
        for cid in cluster:
            flags += behaviour.flags_for(s, cid)
        seen: set[str] = set()
        out["flags"] = [f for f in sorted(flags, key=lambda f: -f["weight"]) if not (f["code"] in seen or seen.add(f["code"]))]
        inf = inference.associates(s, oid, limit=60)
        inf_vis = _visible(c, [r["other"] for r in inf])
        scope = set(c.case.scope) if c.case else set()
        for r in inf:
            o = inf_vis.get(r["other"])
            if not o:
                continue
            a = assoc.setdefault(r["other"], {**c.summary(o), "why": [], "strength": 0.0})
            a["why"] = sorted(set(a["why"]) | {r["summary"]})
            a["strength"] = max(a["strength"], 3 + 7 * r["score"])
            a["inferred"] = True
            a["bases"] = r.get("bases", [])
            a["in_case"] = r["other"] in scope
        out["associates"] = sorted(assoc.values(), key=lambda a: -a["strength"])[:40]
    # lead assessment in the active case
    if c.case:
        ci = case_intel(c.case.id)
        rank = next((x for x in ci["suspects"] if x["id"] in cluster), None)
        if rank:
            out["lead"] = {**rank, "rank": ci["suspects"].index(rank) + 1, "of": len(ci["suspects"]), "case": c.case.id}
    from .dossier_ext import extend

    viewed += extend(c, out, obj, list(cluster))
    c.log("dossier", object_ids=viewed)
    return out


@router.get("/tx/{oid:path}")
def transactions(oid: str, account: str | None = None, limit: int = 200, offset: int = 0, min_amount: float = 0, c: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    s = c.svc.store
    obj = s.get_object(oid)
    if not obj or not c.decide(obj).allow:
        raise HTTPException(403, "not visible")
    accts = [oid] if obj["type"] == "BankAccount" else entity_accounts(s, oid)
    if obj["type"] == "Person":
        for rid in entity_cluster(s, oid):
            accts += entity_accounts(s, rid)
    if account:
        accts = [a for a in accts if a == account]
    accts = sorted(set(accts))
    if not accts:
        return {"rows": [], "total": 0}
    q = ",".join("?" * len(accts))
    total = s.query(f"SELECT COUNT(*) n FROM txns WHERE (from_acct IN ({q}) OR to_acct IN ({q})) AND amount>=?", (*accts, *accts, min_amount))[0]["n"]
    rows = s.query(f"SELECT * FROM txns WHERE (from_acct IN ({q}) OR to_acct IN ({q})) AND amount>=? ORDER BY ts DESC LIMIT ? OFFSET ?",
                   (*accts, *accts, min_amount, min(limit, 1000), offset))
    L = ledger()
    mine = set(accts)
    flagged = {r["subject_id"] for r in s.query("SELECT DISTINCT subject_id FROM alerts WHERE severity='high'")}
    out = []
    for r in rows:
        dirn = "out" if r["from_acct"] in mine else "in"
        cp = r["to_acct"] if dirn == "out" else r["from_acct"]
        out.append({"id": r["id"], "ts": r["ts"], "direction": dirn, "amount": r["amount"], "channel": r["channel"], "narration": r["narration"],
                    "ref": r["ref"], "country": r["country"], "account": r["from_acct"] if dirn == "out" else r["to_acct"],
                    "counterparty_account": cp, "counterparty": L.label(cp), "counterparty_holder": L.holder.get(cp or ""),
                    "flagged": bool(cp and cp in flagged)})
    c.log("transactions", detail={"accounts": len(accts), "rows": len(out)}, object_ids=[oid])
    return {"rows": out, "total": total}


@router.get("/calls/{oid:path}")
def calls(oid: str, c: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    s = c.svc.store
    obj = s.get_object(oid)
    if not obj or not c.decide(obj).allow:
        raise HTTPException(403, "not visible")
    cluster = entity_cluster(s, oid) if obj["type"] == "Person" else [oid]
    phone_ids = [l["dst"] for l in s.links_for(cluster) if l["type"] == "uses_phone"] if obj["type"] != "Phone" else [oid]
    numbers = [s.get_object(p)["props"]["number"] for p in phone_ids]
    if not numbers:
        return {"contacts": [], "towers": [], "hourly": [], "total": 0}
    q = ",".join("?" * len(numbers))
    rows = s.query(f"SELECT * FROM cdrs WHERE a_number IN ({q}) OR b_number IN ({q}) ORDER BY ts DESC", (*numbers, *numbers))
    num_owner = {}
    for r in s.query("SELECT l.src, o.props FROM links l JOIN objects o ON o.id=l.dst WHERE l.type='uses_phone'"):
        num_owner[json.loads(r["props"])["number"]] = r["src"]
    owners = _visible(c, list({num_owner.get(r["b_number"] if r["a_number"] in numbers else r["a_number"]) for r in rows} - {None}))
    contacts: dict[str, dict[str, Any]] = {}
    hourly = [0] * 24
    towers = Counter()
    for r in rows:
        other = r["b_number"] if r["a_number"] in numbers else r["a_number"]
        cc = contacts.setdefault(other, {"number": other, "calls": 0, "seconds": 0, "first": r["ts"], "last": r["ts"], "owner": None, "owner_id": None})
        cc["calls"] += 1
        cc["seconds"] += r["duration_s"] or 0
        cc["first"] = min(cc["first"], r["ts"])
        cc["last"] = max(cc["last"], r["ts"])
        hourly[int(r["ts"][11:13])] += 1
        if r["tower_id"]:
            towers[r["tower_id"]] += 1
        own = num_owner.get(other)
        if own and own in owners:
            cc["owner"], cc["owner_id"] = owners[own]["title"], own
        elif other.startswith("+"):
            cc["owner"] = "Unregistered foreign number"
    tw = []
    for tid, n in towers.most_common(10):
        t = s.query("SELECT * FROM towers WHERE id=?", (tid,))
        if t:
            tw.append({**dict(t[0]), "hits": n})
    c.log("cdr_view", detail={"rows": len(rows)}, object_ids=[oid])
    return {"numbers": numbers, "total": len(rows), "contacts": sorted(contacts.values(), key=lambda x: -x["calls"])[:40], "hourly": hourly, "towers": tw,
            "recent": [dict(r) for r in rows[:50]]}


# ---------------------------------------------------------------------------- money tracing
@router.get("/trace")
def money_trace(id: str, direction: str = "out", hops: int = Query(5, ge=1, le=8), min_amount: float = 50_000, window_days: int = 90,
                c: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    s = c.svc.store
    obj = s.get_object(id)
    if not obj or not c.decide(obj).allow:
        raise HTTPException(403, "not visible")
    seeds = [id] if obj["type"] in ("BankAccount", "CryptoWallet") else entity_accounts(s, id)
    if obj["type"] == "Person":
        for rid in entity_cluster(s, id):
            seeds += entity_accounts(s, rid)
    if not seeds:
        raise HTTPException(404, "no accounts to trace from")
    res = trace(ledger(), sorted(set(seeds)), direction=direction, hops=hops, min_amount=min_amount, window_days=window_days)
    flagged = defaultdict(list)
    for r in s.query("SELECT subject_id, rule FROM alerts"):
        flagged[r["subject_id"]].append(r["rule"])
    for n in res["nodes"]:
        n["alerts"] = sorted(set(flagged.get(n["id"], []) + flagged.get(n.get("holder") or "", [])))
    c.log("trace", detail={"direction": direction, "hops": hops, "seeds": len(seeds)}, object_ids=[id])
    return res


# ---------------------------------------------------------------------------- case board
@router.get("/cases/{case_id}/board")
def case_board(case_id: str, c: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    s = c.svc.store
    case = c.svc.guard.load_case(case_id)
    if not case or c.user.id not in case.members:
        raise HTTPException(403, "not a member of this case")
    row = dict(s.query("SELECT * FROM cases WHERE id=?", (case_id,))[0])
    ci = case_intel(case_id)
    net, sus = ci["net"], ci["suspects"]
    nodes = sorted(net["nodes"])
    objs = s.get_objects(nodes)
    seeds = [c.summary(objs[x]) for x in case_seeds(s, case_id) if x in objs]
    alerts = _alerts_for(nodes)
    al_list = sorted([a for x in nodes for a in alerts.get(x, [])], key=lambda a: -a["score"])
    for a in al_list:
        o = objs.get(a["subject_id"])
        a["subject"] = c.summary(o)["title"] if o else a["subject_id"]
        h = ledger().holder.get(a["subject_id"])
        a["holder"] = ledger().names.get(h, "") if h else ""
        a["holder_id"] = h
    tr = net["traced"]
    by_type = Counter(objs[x]["type"] for x in nodes if x in objs)
    # cross-case links: suspects that also appear in the user's other open cases
    cross = []
    for other in c.svc.guard.cases_for(c.user):
        if other["id"] == case_id or other["status"] != "open":
            continue
        onet = case_intel(other["id"])["net"]["nodes"]
        shared = [x for x in sus if x["id"] in onet and x["score"] >= 40]
        if shared:
            cross.append({"case_id": other["id"], "title": other["title"], "agency": other["agency"],
                          "shared": [{"id": x["id"], "name": x["name"], "role": x["role"]} for x in shared[:6]]})
    leads = [dict(r) | {"notes": json.loads(r["notes"])} for r in s.query("SELECT * FROM leads WHERE case_id=? ORDER BY updated_at DESC", (case_id,))]
    timeline = []
    for x in nodes:
        o = objs.get(x)
        if o and o["type"] == "Incident":
            timeline.append({"at": o["props"].get("occurred_at"), "kind": "case", "title": f"{o['props'].get('agency', '')} {o['title']}", "detail": o["props"].get("summary"), "id": x})
    for a in al_list[:40]:
        if a.get("window_start"):
            timeline.append({"at": a["window_start"], "kind": "alert", "title": a["rule"].replace("_", " ").title(), "detail": a["summary"], "id": a["subject_id"]})
    top_ids = [x["id"] for x in sus[:12]]
    if top_ids:
        for t in s.query(f"SELECT * FROM travel WHERE person_id IN ({','.join('?' * len(top_ids))})", top_ids):
            timeline.append({"at": t["ts"], "kind": "travel", "title": f"{objs[t['person_id']]['title'] if t['person_id'] in objs else ''}: {t['from_city']} → {t['to_city']}", "detail": t["pnr"], "id": t["person_id"]})
    timeline.sort(key=lambda e: e["at"] or "", reverse=True)
    c.log("case_board", object_ids=[x["id"] for x in sus[:30]], detail={"case": case_id})
    return {
        "case": row, "seeds": seeds,
        "stats": {"network_objects": len(nodes), "persons": by_type.get("Person", 0), "organisations": by_type.get("Organisation", 0),
                  "accounts": by_type.get("BankAccount", 0), "phones": by_type.get("Phone", 0), "alerts": len(al_list),
                  "money_onward": round(sum(l["value"] for l in tr["out"]["links"] if l["source"] in net["seed_accounts"]), 2),
                  "money_sources": round(sum(l["value"] for l in tr["in"]["links"] if l["target"] in net["seed_accounts"]), 2),
                  "sinks": tr["out"]["sinks"], "suspects_50": len([x for x in sus if x["score"] >= 50])},
        "suspects": sus[:40], "alerts": al_list[:60], "beneficiaries": tr["out"]["beneficiaries"][:10], "sources": tr["in"]["beneficiaries"][:10],
        "cross_case": cross, "leads": leads, "stages": LEAD_STAGES, "timeline": timeline[:80], "computed_at": ci["at"],
    }


@router.get("/cases/{case_id}/network")
def case_network(case_id: str, limit: int = 160, c: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    """The case network as a graph: top suspects, their accounts, companies, phones and the money between them."""
    s = c.svc.store
    case = c.svc.guard.load_case(case_id)
    if not case or c.user.id not in case.members:
        raise HTTPException(403, "not a member of this case")
    ci = case_intel(case_id)
    sus = {x["id"]: x for x in ci["suspects"]}
    keep = set(case_seeds(s, case_id))
    keep |= {x["id"] for x in ci["suspects"] if x["score"] >= 35}
    links = s.links_for(sorted(keep))
    attach = {"holds_account", "signatory_of", "director_of", "controls", "uses_phone", "owns", "accused_in", "mentions", "complainant_in", "same_as", "relative_of"}
    for l in links:
        if l["type"] in attach:
            keep |= {l["src"], l["dst"]}
    keep = {k for k in keep if not k.startswith(("adminunit:", "location:"))}
    links = [l for l in s.links_for(sorted(keep)) if l["src"] in keep and l["dst"] in keep]
    objs = _visible(c, sorted(keep))
    alerts = _alerts_for(list(objs))
    nodes = []
    for oid, o in list(objs.items())[: max(limit, 40) * 3]:
        x = sus.get(oid)
        nodes.append({"id": oid, "type": o["type"], "label": c.summary(o)["title"], "score": x["score"] if x else None, "role": x["role"] if x else None,
                      "alerts": len(alerts.get(oid, [])), "seed": oid in set(case_seeds(s, case_id)), "kind": o["props"].get("kind")})
    edges = [{"id": l["id"], "source": l["src"], "target": l["dst"], "type": l["type"], "evidence": l["evidence"],
              "amount": l["props"].get("total"), "count": l["props"].get("count"), "status": l["status"]}
             for l in links if l["src"] in objs and l["dst"] in objs]
    c.log("case_network", object_ids=list(objs)[:200], detail={"case": case_id})
    return {"nodes": nodes, "edges": edges}


# ---------------------------------------------------------------------------- alerts inbox
@router.get("/alerts")
def alerts(rule: str | None = None, severity: str | None = None, limit: int = 200, c: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    s = c.svc.store
    sql, params = "SELECT * FROM alerts WHERE 1=1", []
    if rule:
        sql += " AND rule=?"
        params.append(rule)
    if severity:
        sql += " AND severity=?"
        params.append(severity)
    sql += " ORDER BY score DESC, amount DESC LIMIT ?"
    params.append(min(limit, 1000))
    rows = [dict(r) for r in s.query(sql, params)]
    subj = s.get_objects([r["subject_id"] for r in rows])
    L = ledger()
    out = []
    for r in rows:
        o = subj.get(r["subject_id"])
        if not o or not c.decide(o).allow:
            continue
        r["details"] = json.loads(r["details"])
        r["subject"] = c.summary(o)["title"]
        h = L.holder.get(r["subject_id"])
        r["holder"] = L.names.get(h, "") if h else ""
        r["holder_id"] = h
        out.append(r)
    rules = [{"rule": x["rule"], "n": x["n"]} for x in s.query("SELECT rule, COUNT(*) n FROM alerts GROUP BY rule ORDER BY n DESC")]
    c.log("alerts_inbox", detail={"rule": rule, "severity": severity}, object_ids=[r["subject_id"] for r in out][:200])
    return {"alerts": out, "rules": rules}


# ---------------------------------------------------------------------------- globe
@router.get("/globe")
def globe(case: str | None = None, c: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    s = c.svc.store
    L = ledger()
    focus: set[str] | None = None
    sus: dict[str, Any] = {}
    if case:
        cs = c.svc.guard.load_case(case)
        if not cs or c.user.id not in cs.members:
            raise HTTPException(403, "not a member of this case")
        ci = case_intel(case)
        focus = set(ci["net"]["nodes"])
        sus = {x["id"]: x for x in ci["suspects"]}
    acct_city: dict[str, str] = {}
    for r in s.query("SELECT id, props FROM objects WHERE type='BankAccount'"):
        p = json.loads(r["props"])
        acct_city[r["id"]] = p.get("branch") or ""
    flagged = {r["subject_id"] for r in s.query("SELECT DISTINCT subject_id FROM alerts")}
    flows: dict[tuple[str, str], list[float]] = defaultdict(lambda: [0.0, 0])
    for a, rows in L.out.items():
        if focus is not None and a not in focus:
            continue
        for t in rows:
            if not t[3] or t[4] < 1_00_000:
                continue
            if focus is None and not (a in flagged or t[3] in flagged or (t[7] or "IN") != "IN"):
                continue
            c1, c2 = acct_city.get(a, ""), acct_city.get(t[3], "")
            if c1 and c2 and c1 != c2:
                flows[(c1, c2)][0] += t[4]
                flows[(c1, c2)][1] += 1
    arcs = []
    for (c1, c2), (v, n) in sorted(flows.items(), key=lambda kv: -kv[1][0])[:80]:
        p1, p2 = city_coords(c1), city_coords(c2)
        if p1 and p2:
            arcs.append({"from": c1, "to": c2, "from_coord": p1, "to_coord": p2, "amount": round(v, 2), "count": n,
                         "international": c1 in FOREIGN or c2 in FOREIGN})
    tsql = "SELECT * FROM travel"
    trows = s.query(tsql)
    trips = []
    for t in trows:
        if focus is not None and t["person_id"] not in focus:
            continue
        if focus is None and t["to_country"] == "IN" and t["from_country"] == "IN":
            continue
        trips.append({"person": t["person_id"], "from": t["from_city"], "to": t["to_city"], "from_coord": [t["from_lon"], t["from_lat"]],
                      "to_coord": [t["to_lon"], t["to_lat"]], "ts": t["ts"]})
    people = []
    ids = list(focus) if focus is not None else [x["id"] for x in sus.values()]
    if focus is None:
        rows = s.query("SELECT DISTINCT a.subject_id id FROM alerts a WHERE a.subject_type IN ('Person','Organisation')")
        ids = [r["id"] for r in rows] + [L.holder[r["subject_id"]] for r in s.query("SELECT subject_id FROM alerts WHERE subject_type='BankAccount'") if r["subject_id"] in L.holder]
    objs = _visible(c, sorted(set(ids)))
    # each person or company sits at its recorded address (home, registered office); without one, on a small spiral
    # around its city centre so that people of one city never stack on one point
    homes: dict[str, tuple[float, float, str]] = {}
    pids = [oid for oid, o in objs.items() if o["type"] in ("Person", "Organisation")]
    for i in range(0, len(pids), 400):
        chunk = pids[i:i + 400]
        q = ",".join("?" * len(chunk))
        for r in s.query(f"SELECT l.src, o.lat, o.lon, o.props FROM links l JOIN objects o ON o.id=l.dst WHERE l.type IN ('resides_at','registered_at') "
                         f"AND l.src IN ({q}) AND o.lat IS NOT NULL", chunk):
            homes.setdefault(r["src"], (r["lon"], r["lat"], json.loads(r["props"]).get("address") or ""))
    per_city: dict[str, int] = defaultdict(int)
    for oid in sorted(pids):
        o = objs[oid]
        x = sus.get(oid)
        if oid in homes:
            lon, lat, place = homes[oid]
        else:
            pt = city_coords(o["props"].get("city"))
            if not pt:
                continue
            k = per_city[o["props"].get("city")]
            per_city[o["props"].get("city")] += 1
            angle, radius = k * 2.39996, 0.012 * (1 + k) ** 0.5  # golden-angle spiral, about 1.3 km apart
            lon, lat, place = pt[0] + radius * math.cos(angle), pt[1] + radius * math.sin(angle), o["props"].get("city") or ""
        people.append({"id": oid, "type": o["type"], "label": c.summary(o)["title"], "lon": round(lon, 5), "lat": round(lat, 5),
                       "score": x["score"] if x else None, "role": x["role"] if x else None, "city": o["props"].get("city"), "kind": o["props"].get("kind"),
                       "place": place})
    # people at one address (a household, a shared office) stand in a small ring around it, so each can be picked
    at_point: dict[tuple[float, float], list[dict[str, Any]]] = defaultdict(list)
    for e in people:
        at_point[(round(e["lon"], 4), round(e["lat"], 4))].append(e)
    for (lon, lat), group in at_point.items():
        if len(group) > 1:
            for k, e in enumerate(sorted(group, key=lambda x: x["id"])):
                angle = 2 * math.pi * k / len(group)
                e["lat"] = round(lat + 0.0009 * math.sin(angle), 6)
                e["lon"] = round(lon + 0.0009 * math.cos(angle) / max(0.2, math.cos(math.radians(lat))), 6)
    ties: list[dict[str, Any]] = []
    if focus is not None:
        # inside a case every dot is joined to the dots it deals with: money between them (holder to holder, so two
        # firms in one city are joined too), and the recorded ties (director, owner, family, shared phone)
        pos = {e["id"]: e for e in people}
        pair: dict[tuple[str, str], list[float]] = defaultdict(lambda: [0.0, 0, 0])
        for a, rows in L.out.items():
            ha = L.holder.get(a)
            if ha not in pos:
                continue
            for t in rows:
                hb = L.holder.get(t[3] or "")
                if hb in pos and hb != ha and t[4] >= 1_00_000:
                    v = pair[(ha, hb)]
                    v[0] += t[4]
                    v[1] += 1
                    v[2] = v[2] or int((t[7] or "IN") != "IN")
        arcs = []
        for (ha, hb), (v, n, abroad) in sorted(pair.items(), key=lambda kv: -kv[1][0])[:120]:
            fa, fb = pos[ha], pos[hb]
            intl = bool(abroad) or (fa["city"] in FOREIGN) != (fb["city"] in FOREIGN)
            arcs.append({"from": fa["label"], "to": fb["label"], "from_id": ha, "to_id": hb, "from_coord": [fa["lon"], fa["lat"]],
                         "to_coord": [fb["lon"], fb["lat"]], "amount": round(v, 2), "count": n, "international": intl})
        words = {"director_of": "director", "controls": "controls", "owns": "owner", "relative_of": "family", "employee_of": "employee",
                 "signatory_of": "account signatory", "associate_of": "associate", "inferred_association": "inferred association",
                 "holds_account": "account holder", "uses_phone": "phone user"}
        kinds: dict[tuple[str, str], set[str]] = defaultdict(set)
        for l in s.links_for(list(pos)):
            a, b = l["src"], l["dst"]
            if a in pos and b in pos and a != b and l["type"] not in ("same_as", "transferred_to"):
                kinds[(a, b) if a < b else (b, a)].add(l["type"])
        # people tied through one phone or account that is not itself on the map
        via: dict[str, set[str]] = defaultdict(set)
        for l in s.links_for(list(pos)):
            if l["type"] in ("uses_phone", "signatory_of", "holds_account") and l["src"] in pos and l["dst"] not in pos:
                via[l["dst"]].add(l["src"])
        for thing, holders in via.items():
            hs = sorted(holders)
            for i in range(len(hs)):
                for j in range(i + 1, len(hs)):
                    kinds[(hs[i], hs[j])].add("shared phone" if thing.startswith("phone:") else "shared account")
        for (a, b), ks in kinds.items():
            fa, fb = pos[a], pos[b]
            ties.append({"a": a, "b": b, "a_label": fa["label"], "b_label": fb["label"], "a_coord": [fa["lon"], fa["lat"]], "b_coord": [fb["lon"], fb["lat"]],
                         "kinds": sorted({words.get(k, k.replace("_", " ")) for k in ks}), "inferred": ks <= {"inferred_association"}})
    incidents = []
    for r in s.query("SELECT id, title, props, lat, lon, district_lgd FROM objects WHERE type='Incident'"):
        if focus is not None and r["id"] not in focus:
            continue
        p = json.loads(r["props"])
        if focus is None and p.get("agency") not in ("ED", "CBI", "NIA", "NCB", "FIU-IND"):
            continue
        if r["lat"] is not None and r["lon"] is not None:  # where it happened
            incidents.append({"id": r["id"], "label": r["title"], "agency": p.get("agency"), "kind": p.get("kind"), "lon": r["lon"], "lat": r["lat"],
                              "summary": p.get("summary")})
            continue
        d = s.query("SELECT lat, lon FROM objects WHERE id=?", (f"adminunit:lgd-d-{r['district_lgd']}",)) if r["district_lgd"] else []
        if d and d[0]["lon"] is not None:
            incidents.append({"id": r["id"], "label": r["title"], "agency": p.get("agency"), "kind": p.get("kind"), "lon": d[0]["lon"], "lat": d[0]["lat"],
                              "summary": p.get("summary")})
    c.log("globe", detail={"case": case}, object_ids=list(objs)[:200])
    pts = [(e["lon"], e["lat"]) for e in people] + [(i["lon"], i["lat"]) for i in incidents] + \
          [tuple(x) for a in arcs for x in (a["from_coord"], a["to_coord"])] + [tuple(x) for t in trips for x in (t["from_coord"], t["to_coord"]) if None not in x]
    bounds = [min(x for x, _ in pts), min(y for _, y in pts), max(x for x, _ in pts), max(y for _, y in pts)] if pts else None
    return {"arcs": arcs, "trips": trips, "entities": people, "incidents": incidents, "agency_colours": AGENCY_COLOURS, "bounds": bounds, "ties": ties}


@router.post("/refresh")
def refresh(c: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    c.require_role("supervisor", "analyst", "io")
    invalidate()
    return {"ok": True, "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}

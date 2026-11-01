"""Connect the dots: infer who is associated with whom from everything on record.

Every inferred association lists its bases: the observed facts that support it, each with a
weight, combined by noisy-OR (1 - product of (1 - w)). Nothing is inferred from who a person
*is* (name, religion, caste, gender, age, place of origin); only from what the records show
they *did* or *share*: a handset, a SIM, an address, an account, money, calls, contacts,
journeys, a tower at the same hour, a toll plaza in convoy, an FIR, a photograph.

Results are written as `inferred_association` links (origin 'inference', confidence = score,
props.bases = the evidence) and replaced on every run. They are leads for an analyst, not facts:
the UI shows them dashed and the bases are always shown with them.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from datetime import datetime, timedelta
from itertools import combinations
from typing import Any

from ..store import Store, utcnow
from .money import Ledger

LINK_TYPE = "inferred_association"
LIVE = ("active", "auto", "confirmed")
HUB_KINDS = {"merchant", "department", "crypto_exchange", "bank", "police_station", "hospital", "utility", "telecom"}
STORE_MIN = 0.45          # store a pair at this score ...
STORE_MIN_MULTI = 0.35    # ... or at this score when two or more kinds of basis agree


class Resolver:
    """Map source records to the resolved person (same_as clusters) so evidence on a raw
    record (e.g. a CCTNS accused entry) counts for the person."""

    def __init__(self, store: Store):
        parent: dict[str, str] = {}

        def find(x: str) -> str:
            while parent.get(x, x) != x:
                parent[x] = parent.get(parent[x], parent[x])
                x = parent[x]
            return x

        members: set[str] = set()
        for r in store.query("SELECT src, dst FROM links WHERE type='same_as' AND status IN ('auto','confirmed')"):
            members.update((r["src"], r["dst"]))
            a, b = find(r["src"]), find(r["dst"])
            if a != b:
                parent[a] = b
        degree = {r["src"]: r["n"] for r in store.query("SELECT src, COUNT(*) n FROM links WHERE type!='same_as' AND src LIKE 'person:%' GROUP BY src")}
        clusters: dict[str, list[str]] = defaultdict(list)
        # every member, including each cluster's root (which never appears as a key of `parent`)
        for x in members:
            clusters[find(x)].append(x)
        self.rep: dict[str, str] = {}
        for members in clusters.values():
            best = max(members, key=lambda m: (degree.get(m, 0), m))
            for m in members:
                self.rep[m] = best

    def __call__(self, oid: str) -> str:
        return self.rep.get(oid, oid)


class Evidence:
    def __init__(self) -> None:
        self.pairs: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)

    def add(self, a: str, b: str, kind: str, weight: float, detail: str, refs: list[str] | None = None) -> None:
        if a == b:
            return
        key = (a, b) if a < b else (b, a)
        self.pairs[key].append({"kind": kind, "weight": round(min(0.95, weight), 3), "detail": detail, "refs": (refs or [])[:6]})


def combine(bases: list[dict[str, Any]]) -> float:
    """Noisy-OR over the strongest basis of each kind (repeats of one kind do not stack)."""
    best: dict[str, float] = {}
    for b in bases:
        best[b["kind"]] = max(best.get(b["kind"], 0.0), b["weight"])
    p = 1.0
    for w in best.values():
        p *= 1.0 - w
    return round(1.0 - p, 4)


KIND_LABEL = {
    "shared_handset": "Used the same handset", "shared_sim": "Used the same SIM", "joint_account": "Same bank account",
    "money": "Money between them", "calls": "Called each other", "common_contacts": "Call the same people",
    "co_location": "Same tower, same hour", "co_travel": "Travelled together", "convoy": "Vehicles in convoy",
    "shared_address": "Same address", "co_director": "Run the same company", "co_accused": "Accused in the same case",
    "photographed_together": "Photographed together", "relative": "Recorded relative", "associate": "Recorded associate",
}


def gather(store: Store, ledger: Ledger | None = None) -> tuple[Evidence, Resolver]:
    R = Resolver(store)
    ev = Evidence()
    links = [dict(r) for r in store.query(
        "SELECT type, src, dst FROM links WHERE status IN ('active','auto','confirmed') AND type IN "
        "('uses_phone','sim_in_device','holds_account','signatory_of','resides_at','director_of','controls','accused_in','owns','relative_of','associate_of')")]
    by_type: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for l in links:
        by_type[l["type"]].append((l["src"], l["dst"]))
    person = lambda x: x.startswith("person:")  # noqa: E731
    org_kind = {r["id"]: json.loads(r["props"]).get("kind", "") for r in store.query("SELECT id, props FROM objects WHERE type='Organisation'")}

    # ---- recorded relations (kept as context; they do not create an inferred link alone)
    for t, kind, w in (("relative_of", "relative", 0.6), ("associate_of", "associate", 0.6)):
        for a, b in by_type[t]:
            ev.add(R(a), R(b), kind, w, "on record", [a, b])

    # ---- phones and handsets
    users_of_phone: dict[str, set[str]] = defaultdict(set)
    phones_of: dict[str, set[str]] = defaultdict(set)
    for p, ph in by_type["uses_phone"]:
        if person(p):
            users_of_phone[ph].add(R(p))
            phones_of[R(p)].add(ph)
    for ph, users in users_of_phone.items():
        for a, b in combinations(sorted(users), 2):
            ev.add(a, b, "shared_sim", 0.85, "both recorded as users of the same number", [ph])
    phones_in_device: dict[str, set[str]] = defaultdict(set)
    for ph, dev in by_type["sim_in_device"]:
        phones_in_device[dev].add(ph)
    for dev, phs in phones_in_device.items():
        users = {u for ph in phs for u in users_of_phone.get(ph, ())}
        for a, b in combinations(sorted(users), 2):
            ev.add(a, b, "shared_handset", 0.85, "SIMs of both were used in one handset (same IMEI)", [dev, *phs])

    # ---- accounts held or operated together
    on_account: dict[str, set[str]] = defaultdict(set)
    for t in ("holds_account", "signatory_of"):
        for p, acct in by_type[t]:
            if person(p):
                on_account[acct].add(R(p))
    for acct, ps in on_account.items():
        for a, b in combinations(sorted(ps), 2):
            ev.add(a, b, "joint_account", 0.8, "holder or signatory on the same account", [acct])

    # ---- address (building-scale addresses with many residents are weak)
    at_address: dict[str, set[str]] = defaultdict(set)
    for p, loc in by_type["resides_at"]:
        if person(p):
            at_address[loc].add(R(p))
    for loc, ps in at_address.items():
        if 1 < len(ps) <= 8:
            w = 0.45 if len(ps) <= 4 else 0.25
            for a, b in combinations(sorted(ps), 2):
                ev.add(a, b, "shared_address", w, f"recorded at the same address ({len(ps)} people there)", [loc])

    # ---- companies (directors / controllers of the same small company)
    of_company: dict[str, set[str]] = defaultdict(set)
    for t in ("director_of", "controls"):
        for p, org in by_type[t]:
            if person(p) and org_kind.get(org) not in HUB_KINDS:
                of_company[org].add(R(p))
    for org, ps in of_company.items():
        if len(ps) <= 8:
            for a, b in combinations(sorted(ps), 2):
                ev.add(a, b, "co_director", 0.5, "directors or controllers of the same company", [org])

    # ---- incidents (co-accused)
    accused: dict[str, set[str]] = defaultdict(set)
    for p, inc in by_type["accused_in"]:
        if person(p):
            accused[inc].add(R(p))
    for inc, ps in accused.items():
        if len(ps) <= 15:
            for a, b in combinations(sorted(ps), 2):
                ev.add(a, b, "co_accused", 0.6, "named as accused in the same FIR / complaint", [inc])

    # ---- money between people (own accounts, either direction, aggregated)
    ledger = ledger or Ledger(store)
    acct_person: dict[str, str] = {}
    for acct, ps in on_account.items():
        h = ledger.holder_of(acct)
        if h and person(h):
            acct_person[acct] = R(h)
        elif len(ps) == 1:
            acct_person[acct] = next(iter(ps))
    flows: dict[tuple[str, str], list[float]] = defaultdict(lambda: [0.0, 0])
    refs: dict[tuple[str, str], list[str]] = defaultdict(list)
    for acct, rows in ledger.out.items():
        a = acct_person.get(acct)
        if not a:
            continue
        for t in rows:
            b = acct_person.get(t[3]) if t[3] else None
            if b and b != a:
                k = (a, b) if a < b else (b, a)
                flows[k][0] += t[4]
                flows[k][1] += 1
                if len(refs[k]) < 4:
                    refs[k].append(t[0])
    for (a, b), (amt, n) in flows.items():
        if amt >= 20_000 or n >= 3:
            w = min(0.75, 0.25 + 0.12 * math.log10(max(amt, 1) / 10_000 + 1) * 3)
            ev.add(a, b, "money", w, f"{n} transfer(s) between their accounts, Rs {amt:,.0f}", refs[(a, b)])

    # ---- calls, common contacts, co-location (CDRs)
    owner_of_number = {}
    for r in store.query("SELECT id, props FROM objects WHERE type='Phone'"):
        users = users_of_phone.get(r["id"])
        if users and len(users) == 1:
            owner_of_number[json.loads(r["props"]).get("number")] = next(iter(users))
    calls: dict[tuple[str, str], int] = defaultdict(int)
    contacts: dict[str, set[str]] = defaultdict(set)
    by_tower: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for r in store.query("SELECT ts, a_number, b_number, tower_id FROM cdrs"):
        a, b = owner_of_number.get(r["a_number"]), owner_of_number.get(r["b_number"])
        if a:
            contacts[a].add(r["b_number"])
            if r["tower_id"]:
                by_tower[r["tower_id"]].append((r["ts"], a))
        if b:
            contacts[b].add(r["a_number"])
        if a and b and a != b:
            calls[(a, b) if a < b else (b, a)] += 1
    for (a, b), n in calls.items():
        if n >= 2:
            ev.add(a, b, "calls", min(0.65, 0.12 * math.log2(1 + n)), f"{n} calls between their numbers")
    callers_of: dict[str, set[str]] = defaultdict(set)
    for p, nums in contacts.items():
        for num in nums:
            callers_of[num].add(p)
    shared: dict[tuple[str, str], list[str]] = defaultdict(list)
    for num, ps in callers_of.items():
        if 2 <= len(ps) <= 8 and owner_of_number.get(num) not in ps:  # low-degree numbers only; hubs say nothing
            for a, b in combinations(sorted(ps), 2):
                shared[(a, b)].append(num)
    for (a, b), nums in shared.items():
        if len(nums) >= 2:
            ev.add(a, b, "common_contacts", min(0.6, 0.15 * len(nums)), f"both in contact with the same {len(nums)} low-traffic numbers", nums)
    days: dict[tuple[str, str], set[str]] = defaultdict(set)
    for tower, hits in by_tower.items():
        hits.sort()
        for i, (t1, p1) in enumerate(hits):
            for t2, p2 in hits[i + 1:i + 60]:
                if datetime.fromisoformat(t2) - datetime.fromisoformat(t1) > timedelta(hours=1):
                    break
                if p1 != p2:
                    days[(p1, p2) if p1 < p2 else (p2, p1)].add(t1[:10])
    for (a, b), ds in days.items():
        if len(ds) >= 2:
            ev.add(a, b, "co_location", min(0.7, 0.2 + 0.1 * len(ds)), f"phones on the same tower within an hour on {len(ds)} days", sorted(ds))

    # ---- travel together (same PNR, or same route on the same day)
    trips = [dict(r) for r in store.query("SELECT person_id, ts, pnr, from_city, to_city FROM travel")]
    by_pnr: dict[str, set[str]] = defaultdict(set)
    by_leg: dict[tuple, set[str]] = defaultdict(set)
    for t in trips:
        p = R(t["person_id"])
        if t["pnr"]:
            by_pnr[t["pnr"]].add(p)
        by_leg[(t["ts"][:10], t["from_city"], t["to_city"])].add(p)
    for pnr, ps in by_pnr.items():
        for a, b in combinations(sorted(ps), 2):
            ev.add(a, b, "co_travel", 0.7, f"on the same booking (PNR {pnr})", [pnr])
    legs: dict[tuple[str, str], list[str]] = defaultdict(list)
    for (day, frm, to), ps in by_leg.items():
        if 2 <= len(ps) <= 6:
            for a, b in combinations(sorted(ps), 2):
                legs[(a, b)].append(f"{day} {frm}->{to}")
    for (a, b), ls in legs.items():
        ev.add(a, b, "co_travel", min(0.65, 0.3 * len(ls)), f"same route on the same day {len(ls)} time(s)", ls)

    # ---- vehicles in convoy: within 15 minutes of each other at two or more DIFFERENT plazas.
    # Two commuters who cross the same plaza at rush hour every day are not a convoy.
    owner_of_vehicle = {}
    for p, v in by_type["owns"]:
        if person(p) and v.startswith("vehicle:"):
            owner_of_vehicle[v] = R(p)
    tolls = sorted((r["plaza"], r["ts"], owner_of_vehicle.get(r["vehicle_id"])) for r in store.query("SELECT vehicle_id, ts, plaza FROM tollhits"))
    convoy: dict[tuple[str, str], set[str]] = defaultdict(set)
    for i, (plaza, t1, p1) in enumerate(tolls):
        for plaza2, t2, p2 in tolls[i + 1:i + 30]:
            if plaza2 != plaza or datetime.fromisoformat(t2) - datetime.fromisoformat(t1) > timedelta(minutes=15):
                break
            if p1 and p2 and p1 != p2:
                convoy[(p1, p2) if p1 < p2 else (p2, p1)].add(plaza)
    for (a, b), plazas in convoy.items():
        if len(plazas) >= 2:
            ev.add(a, b, "convoy", min(0.6, 0.2 + 0.1 * len(plazas)), f"their vehicles passed {len(plazas)} different toll plazas within 15 minutes of each other")

    # ---- photographed together (two confirmed face matches in one image)
    by_image: dict[str, set[str]] = defaultdict(set)
    for r in store.query("SELECT f.media_id, m.candidate_object FROM face_matches m JOIN faces f ON f.id=m.probe_face WHERE m.status='confirmed'"):
        by_image[r["media_id"]].add(R(r["candidate_object"]))
    for mid, ps in by_image.items():
        for a, b in combinations(sorted(ps), 2):
            ev.add(a, b, "photographed_together", 0.7, "both confirmed in the same image", [mid])
    return ev, R


INFERRED_KINDS = set(KIND_LABEL) - {"relative", "associate"}


def run_inference(store: Store, ledger: Ledger | None = None) -> dict[str, Any]:
    ev, _ = gather(store, ledger)
    now = utcnow()
    rows, kinds = [], defaultdict(int)
    for (a, b), bases in ev.pairs.items():
        inferred = [x for x in bases if x["kind"] in INFERRED_KINDS]
        if not inferred:
            continue
        score = combine(bases)
        n_kinds = len({x["kind"] for x in bases})
        if score < STORE_MIN and not (n_kinds >= 2 and score >= STORE_MIN_MULTI):
            continue
        for k in {x["kind"] for x in inferred}:
            kinds[k] += 1
        bases = sorted(bases, key=lambda x: -x["weight"])
        lid = "inferred:" + hashlib.sha256(f"{a}|{b}".encode()).hexdigest()[:20]
        props = {"score": score, "bases": bases, "kinds": sorted({x["kind"] for x in bases}),
                 "summary": "; ".join(dict.fromkeys(KIND_LABEL[x["kind"]] for x in bases))}
        rows.append((lid, LINK_TYPE, a, b, json.dumps(props), json.dumps([{"source": "INFERENCE", "record": ",".join(props["kinds"])}]),
                     "inference", score, "active", now, now))
    with store.tx() as conn:
        conn.execute("DELETE FROM links WHERE type=?", (LINK_TYPE,))
        conn.executemany("INSERT INTO links(id,type,src,dst,props,sources,origin,confidence,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)", rows)
    return {"associations": len(rows), "by_basis": dict(sorted(kinds.items(), key=lambda x: -x[1]))}


def pair_bases(store: Store, a: str, b: str, ev: Evidence | None = None, resolver: Resolver | None = None) -> dict[str, Any]:
    """All evidence between two people, including weak bases that were not stored."""
    if ev is None or resolver is None:
        ev, resolver = gather(store)
    ra, rb = resolver(a), resolver(b)
    key = (ra, rb) if ra < rb else (rb, ra)
    bases = sorted(ev.pairs.get(key, []), key=lambda x: -x["weight"])
    return {"a": ra, "b": rb, "score": combine(bases) if bases else 0.0, "bases": bases,
            "labels": {k: KIND_LABEL[k] for k in {x["kind"] for x in bases}}}


def associates(store: Store, oid: str, limit: int = 40) -> list[dict[str, Any]]:
    rows = store.query(f"SELECT src, dst, props, confidence FROM links WHERE type=? AND (src=? OR dst=?) ORDER BY confidence DESC LIMIT {int(limit)}",
                       (LINK_TYPE, oid, oid))
    return [{"other": r["dst"] if r["src"] == oid else r["src"], "score": r["confidence"], **json.loads(r["props"])} for r in rows]

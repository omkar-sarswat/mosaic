"""Watching records and places: what touched a record, or happened inside an area, in a window of time.

Both answers come from the same event registers (FASTag and ANPR reads, call records, bank
transactions, travel reservations) and from what the platform holds about a record (typology alerts,
FIRs that name it, new facts published from a source). Every record an answer names first passes the
caller's access decision (`Gate`); a record that does not pass is counted by reason and never named.

Location rules, stated so that nobody over-reads an answer:
  * a toll or ANPR read places the vehicle at the plaza or camera at that minute;
  * a call record places the calling number (A party) in the cell of the tower it used; the other party
    could be anywhere, so it is not placed;
  * a reservation places the traveller at the departure or arrival city on the travel date;
  * a recorded address is where a person was registered as living, not where they were at any time.
"""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from typing import Any, Callable, Iterable

from .resolve.service import entity_cluster
from .sources import source_name
from .store import Store, normalize_identifier

MAX_RADIUS_KM = 10.0
ROWS = 2000  # per register, per question: an area or record busier than this is cut and says so


def km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(min(1.0, a)))


def _box(lat: float, lon: float, r: float) -> tuple[float, float, float, float]:
    dlat = r / 111.0
    dlon = r / (111.0 * max(0.2, math.cos(math.radians(lat))))
    return lat - dlat, lat + dlat, lon - dlon, lon + dlon


def window_end(end: str) -> str:
    """A date-only end includes the whole day."""
    return f"{end}T23:59:59" if len(end) == 10 else end


class Gate:
    """The caller's access decisions, cached for one request. Refusals are counted by reason, once per record."""

    def __init__(self, store: Store, decide: Callable[[dict[str, Any]], Any], summarize: Callable[[dict[str, Any]], dict[str, Any]]):
        self.store, self._decide, self._summarize = store, decide, summarize
        self._seen: dict[str, dict[str, Any] | None] = {}
        self.withheld: Counter[str] = Counter()

    def many(self, ids: Iterable[str]) -> dict[str, dict[str, Any]]:
        ids = [i for i in dict.fromkeys(ids) if i]
        todo = [i for i in ids if i not in self._seen]
        if todo:
            objs = self.store.get_objects(todo)
            for i in todo:
                obj = objs.get(i)
                out = None
                if obj:
                    d = self._decide(obj)
                    if d.allow:
                        out = self._summarize(obj)
                    else:
                        self.withheld[d.reason] += 1
                self._seen[i] = out
        return {i: self._seen[i] for i in ids if self._seen.get(i)}  # type: ignore[misc]

    def get(self, oid: str | None) -> dict[str, Any] | None:
        return self.many([oid]).get(oid) if oid else None

    def withheld_list(self) -> list[dict[str, Any]]:
        return [{"reason": r, "count": n} for r, n in self.withheld.most_common()]


def _ref(s: dict[str, Any] | None) -> dict[str, Any] | None:
    return {"id": s["id"], "label": s["title"], "type": s["type"]} if s else None


def _event(at: str, kind: str, title: str, detail: str, source: str | None, record: str | None, *, via: dict[str, Any] | None = None,
           other: dict[str, Any] | None = None, lat: float | None = None, lon: float | None = None, place: str | None = None,
           priority: str = "low", why: str | None = None, emph: list[str] | None = None) -> dict[str, Any]:
    """One dated entry. `priority` (high, medium, low) and `why` say what an officer should read first, in plain words;
    `emph` names the words in the title that carry the point (a number, an amount, a place)."""
    return {"at": at, "kind": kind, "title": title, "detail": detail, "source": source, "source_name": source_name(source) if source else None,
            "record": record, "via": via, "other": other, "lat": lat, "lon": lon, "place": place, "priority": priority, "why": why,
            "emph": [x for x in (emph or []) if x]}


PRIORITY = {"high": 0, "medium": 1, "low": 2}


def _night(ts: str) -> bool:
    return 0 <= int(ts[11:13]) < 5


def escalate(events: list[dict[str, Any]], subjects: set[str], accused: set[str]) -> None:
    """Raise anything that involves a case subject, or someone accused in an FIR, to the top."""
    for e in events:
        ids = {x["id"] for x in (e.get("other"), e.get("via")) if x}
        if ids & subjects:
            e["priority"], e["why"] = "high", "Involves a subject of this case"
        elif ids & accused and e["priority"] != "high":
            e["priority"], e["why"] = "high", "Involves a person accused in an FIR"


def priorities(events: list[dict[str, Any]]) -> dict[str, int]:
    c = Counter(e["priority"] for e in events)
    return {k: c.get(k, 0) for k in PRIORITY}


def _in(ids: list[str]) -> str:
    return ",".join("?" * len(ids))


def number_owners(store: Store, numbers: Iterable[str]) -> dict[str, tuple[str, str | None]]:
    """number -> (phone record, holder of the phone or None) for numbers that are on record."""
    nums = {normalize_identifier(n): n for n in numbers if n}
    if not nums:
        return {}
    keys = list(nums)
    phones: dict[str, str] = {}
    for i in range(0, len(keys), 400):
        chunk = keys[i : i + 400]
        for r in store.query(f"SELECT value, object_id FROM identifiers WHERE kind='number' AND value IN ({_in(chunk)})", chunk):
            if r["object_id"].startswith("phone:"):
                phones.setdefault(nums[r["value"]], r["object_id"])
    holders: dict[str, str] = {}
    pids = list(set(phones.values()))
    for i in range(0, len(pids), 400):
        chunk = pids[i : i + 400]
        for r in store.query(f"SELECT src, dst FROM links WHERE type='uses_phone' AND dst IN ({_in(chunk)})", chunk):
            holders.setdefault(r["dst"], r["src"])
    return {n: (p, holders.get(p)) for n, p in phones.items()}


def _towers(store: Store) -> dict[str, dict[str, Any]]:
    return {r["id"]: dict(r) for r in store.query("SELECT * FROM towers")}


# ---------------------------------------------------------------------------------------------- one record

def holdings(store: Store, obj: dict[str, Any]) -> dict[str, list[str]]:
    """The phones, vehicles and accounts through which activity reaches a record."""
    t, oid = obj["type"], obj["id"]
    if t == "Phone":
        return {"phones": [oid], "vehicles": [], "accounts": [], "cluster": [oid]}
    if t == "Vehicle":
        return {"phones": [], "vehicles": [oid], "accounts": [], "cluster": [oid]}
    if t in ("BankAccount", "CryptoWallet"):
        return {"phones": [], "vehicles": [], "accounts": [oid], "cluster": [oid]}
    cluster = entity_cluster(store, oid) if t == "Person" else [oid]
    out: dict[str, list[str]] = {"phones": [], "vehicles": [], "accounts": [], "cluster": cluster}
    for link in store.links_for(cluster):
        if link["src"] not in cluster:
            continue
        dst = link["dst"]
        if link["type"] == "uses_phone":
            out["phones"].append(dst)
        elif link["type"] == "owns" and dst.startswith("vehicle:"):
            out["vehicles"].append(dst)
        elif link["type"] in ("holds_account", "signatory_of") and dst.startswith("bankaccount:"):
            out["accounts"].append(dst)
    return {k: list(dict.fromkeys(v)) for k, v in out.items()}


def record_activity(store: Store, gate: Gate, obj: dict[str, Any], since: str, *, facts_after: str | None = None,
                    until: str | None = None, limit: int = 300) -> dict[str, Any]:
    """Everything that touched a record (or what it holds) from `since`: reads, calls, money, travel, alerts, FIRs, new facts.

    `facts_after` bounds newly published facts separately: a register loaded before the watch began is
    not news, even inside the look-back window."""
    until = until or "9999"
    h = holdings(store, obj)
    phones = gate.many(h["phones"])
    vehicles = gate.many(h["vehicles"])
    accounts = gate.many(h["accounts"])
    cluster = h["cluster"]
    events: list[dict[str, Any]] = []
    cut: list[str] = []

    for vid, v in vehicles.items():
        rows = store.query("SELECT * FROM tollhits WHERE vehicle_id=? AND ts>=? AND ts<=? ORDER BY ts DESC LIMIT ?", (vid, since, until, ROWS))
        cut += ["vehicle reads"] if len(rows) == ROWS else []
        for r in rows:
            how = "ANPR camera" if r["kind"] == "anpr" else "FASTag toll read"
            toll = r["kind"] != "anpr"
            pr, why = ("medium", "Out-of-town journey") if toll else (("medium", "Late-night movement") if _night(r["ts"]) else ("low", None))
            events.append(_event(r["ts"], "sighting", f"{v['title']} seen at {r['plaza']}", how, r["source"], r["id"], via=_ref(v),
                                 lat=r["lat"], lon=r["lon"], place=r["plaza"], priority=pr, why=why, emph=[r["plaza"]]))

    numbers = {p["props"].get("number") or p["title"]: p for p in phones.values()}
    if numbers:
        nums = list(numbers)
        rows = store.query(f"SELECT * FROM cdrs WHERE (a_number IN ({_in(nums)}) OR b_number IN ({_in(nums)})) AND ts>=? AND ts<=? "
                           f"ORDER BY ts DESC LIMIT ?", (*nums, *nums, since, until, ROWS))
        cut += ["call records"] if len(rows) == ROWS else []
        others = {r["b_number"] if r["a_number"] in numbers else r["a_number"] for r in rows}
        known: set[str] = set()  # numbers already in contact before the watch window
        for r in store.query(f"SELECT a_number, b_number FROM cdrs WHERE (a_number IN ({_in(nums)}) OR b_number IN ({_in(nums)})) AND ts<?",
                             (*nums, *nums, since)):
            known.add(r["b_number"] if r["a_number"] in numbers else r["a_number"])
        first_seen: dict[str, str] = {}
        for r in rows:
            o = r["b_number"] if r["a_number"] in numbers else r["a_number"]
            if o not in known and (o not in first_seen or r["ts"] < first_seen[o]):
                first_seen[o] = r["ts"]
        owners = number_owners(store, others)
        named = gate.many([o[1] for o in owners.values() if o[1]])
        towers = _towers(store)
        for r in rows:
            outgoing = r["a_number"] in numbers
            mine, other = (r["a_number"], r["b_number"]) if outgoing else (r["b_number"], r["a_number"])
            holder = named.get(owners.get(other, ("", None))[1] or "")
            who = f"{other} ({holder['title']})" if holder else other
            sms = (r["call_type"] or "").lower() == "sms"
            title = (f"{'Message' if sms else 'Call'} to {who}" if outgoing else f"{'Message' if sms else 'Call'} from {who}")
            tw = towers.get(r["tower_id"] or "")
            detail = " · ".join(filter(None, [f"{r['duration_s']} s" if r["duration_s"] and not sms else "", f"near {tw['label']}" if tw and outgoing else ""]))
            if other.startswith("+"):
                pr, why = "high", "Foreign number"
            elif first_seen.get(other) == r["ts"]:
                pr, why = "medium", "First contact with this number"
            elif _night(r["ts"]):
                pr, why = "medium", "Late-night call"
            else:
                pr, why = "low", None
            events.append(_event(r["ts"], "call", title, detail or f"on {mine}", r["source"], r["id"], via=_ref(numbers[mine]), other=_ref(holder),
                                 lat=tw["lat"] if tw and outgoing else None, lon=tw["lon"] if tw and outgoing else None,
                                 place=tw["label"] if tw and outgoing else None, priority=pr, why=why,
                                 emph=[other, holder["title"] if holder else None]))

    if accounts:
        acc = list(accounts)
        rows = store.query(f"SELECT * FROM txns WHERE (from_acct IN ({_in(acc)}) OR to_acct IN ({_in(acc)})) AND ts>=? AND ts<=? "
                           f"ORDER BY ts DESC LIMIT ?", (*acc, *acc, since, until, ROWS))
        cut += ["transactions"] if len(rows) == ROWS else []
        cps = gate.many({(r["to_acct"] if r["from_acct"] in accounts else r["from_acct"]) for r in rows} - {None})
        for r in rows:
            out = r["from_acct"] in accounts
            cp = r["to_acct"] if out else r["from_acct"]
            if cp is None:
                party = "cash withdrawal" if out else "cash deposit"
            else:
                party = cps[cp]["title"] if cp in cps else "an account outside this case"
            amount = f"₹{r['amount']:,.0f}"
            title = (f"{amount} {'withdrawn in cash' if cp is None else f'sent to {party}'}" if out
                     else f"{amount} {'deposited in cash' if cp is None else f'received from {party}'}")
            detail = " · ".join(filter(None, [r["channel"], r["narration"], f"abroad ({r['country']})" if r["country"] and r["country"] != "IN" else ""]))
            abroad = bool(r["country"] and r["country"] != "IN")
            if abroad:
                pr, why = "high", "Money abroad"
            elif r["amount"] >= 100_000:
                pr, why = "high", "Large transfer (Rs 1 lakh or more)"
            elif cp is None and r["amount"] >= 50_000:
                pr, why = "medium", "Large cash movement"
            elif r["amount"] >= 25_000:
                pr, why = "medium", "Sizeable transfer"
            else:
                pr, why = "low", None
            events.append(_event(r["ts"], "money", title, detail, r["source"], r["id"], via=_ref(accounts[r["from_acct"] if out else r["to_acct"]]),
                                 other=_ref(cps.get(cp or "")), priority=pr, why=why, emph=[amount, party if cp else None]))

    persons = [i for i in cluster if i.startswith("person:")]
    if persons:
        for r in store.query(f"SELECT * FROM travel WHERE person_id IN ({_in(persons)}) AND ts>=? AND ts<=? ORDER BY ts DESC LIMIT ?",
                             (*persons, since, until, ROWS)):
            abroad = (r["to_country"] or "IN") != "IN" or (r["from_country"] or "IN") != "IN"
            events.append(_event(r["ts"], "travel", f"Travelled {r['from_city']} to {r['to_city']}",
                                 " · ".join(filter(None, [(r["mode"] or "").title(), f"PNR {r['pnr']}" if r["pnr"] else ""])), r["source"], r["id"],
                                 lat=r["to_lat"], lon=r["to_lon"], place=r["to_city"], priority="high" if abroad else "medium",
                                 why="Travel abroad" if abroad else "Journey", emph=[r["from_city"], r["to_city"]]))

    ids = list(dict.fromkeys(cluster + list(phones) + list(vehicles) + list(accounts)))
    for r in store.query(f"SELECT * FROM alerts WHERE subject_id IN ({_in(ids)}) AND created_at>=? AND created_at<=? ORDER BY created_at DESC",
                         (*ids, since, until)):
        events.append(_event(r["created_at"], "alert", r["rule"].replace("_", " ").capitalize(), r["summary"], "DRISHTI-ANALYTICS", None,
                             via=_ref(gate.get(r["subject_id"])), priority="high", why="Typology alert"))

    incidents: dict[str, str] = {}
    for link in store.links_for(ids):
        other = link["dst"] if link["src"] in ids else link["src"]
        if other.startswith("incident:"):
            incidents[other] = link["type"]
    for iid, inc in gate.many(incidents).items():
        at = str(inc["props"].get("occurred_at") or "")
        if since <= at <= until:
            role = {"accused_in": "Named as accused", "complainant_in": "Named as complainant", "mentions": "Mentioned",
                    "stolen_in": "Reported stolen", "used_in": "Used in", "recovered_in": "Recovered in"}.get(incidents[iid], "Linked")
            secs = ", ".join(inc["props"].get("sections") or [])
            accused = incidents[iid] == "accused_in"
            events.append(_event(at, "fir", f"{role} in {inc['title']}", " · ".join(filter(None, [inc["props"].get("agency"), secs])),
                                 "CCTNS", inc["title"], other=_ref(inc), priority="high" if accused else "medium",
                                 why="Named as accused in an FIR" if accused else "Named in an FIR", emph=[inc["title"]]))

    after = max(since, facts_after or since)
    facts: dict[tuple[str, str, str], dict[str, Any]] = {}
    for r in store.query(f"SELECT * FROM provenance WHERE object_id IN ({_in(ids)}) AND ingested_at>? AND ingested_at<=? ORDER BY ingested_at DESC",
                         (*ids, after, until)):
        f = facts.setdefault((r["object_id"], r["source"], r["record"]), {"at": r["ingested_at"], "props": []})
        f["props"].append(r["prop"].replace("_", " "))
    for (oid, src, rec), f in facts.items():
        events.append(_event(f["at"], "record", f"New facts from {source_name(src)}", ", ".join(sorted(set(f["props"])))[:160], src, rec,
                             via=_ref(gate.get(oid)), priority="medium", why="Register updated"))

    events.sort(key=lambda e: e["at"] or "", reverse=True)
    counts = Counter(e["kind"] for e in events)
    # what matters is kept even when the routine tail is cut
    keep = [e for e in events if e["priority"] != "low"][:limit]
    keep += [e for e in events if e["priority"] == "low"][: max(0, limit - len(keep))]
    keep.sort(key=lambda e: e["at"] or "", reverse=True)
    return {"events": keep, "total": len(events), "counts": dict(counts), "cut": cut, "priorities": priorities(events),
            "through": {"phones": [_ref(p) for p in phones.values()], "vehicles": [_ref(v) for v in vehicles.values()],
                        "accounts": [_ref(a) for a in accounts.values()]}}


# ---------------------------------------------------------------------------------------------- one area

def sites(store: Store) -> list[dict[str, Any]]:
    """Fixed places that record presence: the camera and toll register, plazas known only from their reads, phone towers."""
    reads = {r["plaza"]: dict(r) for r in store.query(
        "SELECT plaza, MAX(kind) kind, AVG(lat) lat, AVG(lon) lon, COUNT(*) n FROM tollhits WHERE lat IS NOT NULL GROUP BY plaza")}
    out = []
    for r in store.query("SELECT * FROM checkpoints ORDER BY city, label"):
        out.append({"kind": r["kind"], "label": r["label"], "lat": r["lat"], "lon": r["lon"], "reads": (reads.pop(r["label"], None) or {}).get("n"),
                    "city": r["city"], "road": r["road"]})
    out += [{"kind": "anpr" if (r["kind"] or "") == "anpr" else "toll", "label": p, "lat": r["lat"], "lon": r["lon"], "reads": r["n"]}
            for p, r in sorted(reads.items(), key=lambda x: -x[1]["n"])]
    out += [{"kind": "tower", "label": r["label"], "lat": r["lat"], "lon": r["lon"], "reads": None, "id": r["id"], "city": r["city"],
             "operator": r["operator"], "technology": r["technology"]}
            for r in store.query("SELECT * FROM towers WHERE lat IS NOT NULL ORDER BY label")]
    return out


def area_search(store: Store, gate: Gate, lat: float, lon: float, radius_km: float, start: str, end: str) -> dict[str, Any]:
    """Who and what was inside a circle during a window, by register, each with the reads that place it there."""
    radius_km = min(max(radius_km, 0.1), MAX_RADIUS_KM)
    end = window_end(end)
    s, n, w, e = _box(lat, lon, radius_km)
    cut: list[str] = []
    inside = lambda la, lo: la is not None and lo is not None and km(lat, lon, la, lo) <= radius_km  # noqa: E731

    reads = [dict(r) for r in store.query("SELECT * FROM tollhits WHERE lat BETWEEN ? AND ? AND lon BETWEEN ? AND ? AND ts>=? AND ts<=? "
                                          "ORDER BY ts DESC LIMIT ?", (s, n, w, e, start, end, ROWS))]
    cut += ["vehicle reads"] if len(reads) == ROWS else []
    by_vehicle: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in reads:
        if inside(r["lat"], r["lon"]):
            by_vehicle[r["vehicle_id"]].append(r)
    shown = gate.many(by_vehicle)
    owner_of: dict[str, str] = {}
    if shown:
        vids = list(shown)
        for r in store.query(f"SELECT src, dst FROM links WHERE type='owns' AND dst IN ({_in(vids)})", vids):
            owner_of.setdefault(r["dst"], r["src"])
    owners = gate.many(owner_of.values())
    vehicles = []
    for vid, v in shown.items():
        rows = by_vehicle[vid]
        vehicles.append({"record": v, "owner": _ref(owners.get(owner_of.get(vid, ""))), "count": len(rows), "first": rows[-1]["ts"], "last": rows[0]["ts"],
                         "places": sorted({r["plaza"] for r in rows}),
                         "reads": [{"at": r["ts"], "place": r["plaza"], "kind": r["kind"] or "toll", "lat": r["lat"], "lon": r["lon"], "source": r["source"],
                                    "source_name": source_name(r["source"]), "record": r["id"]} for r in rows[:25]]})
    vehicles.sort(key=lambda x: (-x["count"], x["record"]["title"]))

    towers = [t for t in _towers(store).values() if inside(t["lat"], t["lon"])]
    phones, unlisted = [], 0
    if towers:
        tids = [t["id"] for t in towers]
        calls = [dict(r) for r in store.query(f"SELECT * FROM cdrs WHERE tower_id IN ({_in(tids)}) AND ts>=? AND ts<=? ORDER BY ts DESC LIMIT ?",
                                              (*tids, start, end, ROWS * 5))]
        cut += ["call records"] if len(calls) == ROWS * 5 else []
        by_number: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for r in calls:
            by_number[r["a_number"]].append(r)
        owners_n = number_owners(store, by_number)
        unlisted = sum(1 for num in by_number if num not in owners_n)
        visible_phones = gate.many(p for p, _ in owners_n.values())
        holders = gate.many(h for _, h in owners_n.values() if h)
        tw = {t["id"]: t for t in towers}
        for num, rows in by_number.items():
            pid, holder = owners_n.get(num, (None, None))
            if not pid or pid not in visible_phones:
                continue
            phones.append({"record": visible_phones[pid], "owner": _ref(holders.get(holder or "")), "count": len(rows), "first": rows[-1]["ts"], "last": rows[0]["ts"],
                           "places": sorted({tw[r["tower_id"]]["label"] for r in rows}),
                           "reads": [{"at": r["ts"], "place": tw[r["tower_id"]]["label"], "kind": (r["call_type"] or "call"), "lat": tw[r["tower_id"]]["lat"],
                                      "lon": tw[r["tower_id"]]["lon"], "source": r["source"], "source_name": source_name(r["source"]), "record": r["id"]}
                                     for r in rows[:25]]})
        phones.sort(key=lambda x: (-x["count"], x["record"]["title"]))

    trips = [dict(r) for r in store.query(
        "SELECT * FROM travel WHERE ts>=? AND ts<=? AND ((from_lat BETWEEN ? AND ? AND from_lon BETWEEN ? AND ?) OR (to_lat BETWEEN ? AND ? AND to_lon BETWEEN ? AND ?)) "
        "ORDER BY ts DESC LIMIT ?", (start, end, s, n, w, e, s, n, w, e, ROWS))]
    by_person: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in trips:
        dep, arr = inside(r["from_lat"], r["from_lon"]), inside(r["to_lat"], r["to_lon"])
        if dep or arr:
            by_person[r["person_id"]].append(r | {"direction": "departed" if dep else "arrived"})
    people = gate.many(by_person)
    travellers = [{"record": p, "count": len(by_person[pid]), "first": by_person[pid][-1]["ts"], "last": by_person[pid][0]["ts"],
                   "reads": [{"at": r["ts"], "place": r["from_city"] if r["direction"] == "departed" else r["to_city"], "kind": r["direction"],
                              "detail": f"{r['from_city']} to {r['to_city']}", "lat": r["from_lat"] if r["direction"] == "departed" else r["to_lat"],
                              "lon": r["from_lon"] if r["direction"] == "departed" else r["to_lon"], "source": r["source"],
                              "source_name": source_name(r["source"]), "record": r["id"]} for r in by_person[pid][:25]]}
                  for pid, p in people.items()]

    places = [dict(r) for r in store.query("SELECT id, title, lat, lon FROM objects WHERE type='Location' AND lat BETWEEN ? AND ? AND lon BETWEEN ? AND ?",
                                           (s, n, w, e))]
    places = [p for p in places if inside(p["lat"], p["lon"])]
    residents = []
    if places:
        pid_place = {p["id"]: p for p in places}
        pids = list(pid_place)
        rows = []
        for i in range(0, len(pids), 400):
            chunk = pids[i : i + 400]
            rows += store.query(f"SELECT src, dst FROM links WHERE type IN ('resides_at','registered_at') AND dst IN ({_in(chunk)})", chunk)
        who = gate.many(r["src"] for r in rows)
        for r in rows:
            if r["src"] in who:
                pl = pid_place[r["dst"]]
                residents.append({"record": who[r["src"]], "address": pl["title"], "km": round(km(lat, lon, pl["lat"], pl["lon"]), 2), "lat": pl["lat"], "lon": pl["lon"]})
        residents.sort(key=lambda x: x["km"])

    incidents = []
    for r in store.query("SELECT id, lat, lon FROM objects WHERE type='Incident' AND lat BETWEEN ? AND ? AND lon BETWEEN ? AND ?", (s, n, w, e)):
        if inside(r["lat"], r["lon"]):
            inc = gate.get(r["id"])
            at = str((inc or {}).get("props", {}).get("occurred_at") or "")
            if inc and start <= at <= end:
                incidents.append({"record": inc, "at": at, "lat": r["lat"], "lon": r["lon"]})

    fixed = [x | {"km": round(km(lat, lon, x["lat"], x["lon"]), 2)} for x in sites(store) if inside(x["lat"], x["lon"])]
    return {"centre": {"lat": lat, "lon": lon}, "radius_km": radius_km, "window": [start, end], "vehicles": vehicles, "phones": phones,
            "travellers": travellers, "residents": residents[:100], "incidents": incidents, "sites": fixed, "unlisted_numbers": unlisted,
            "withheld": gate.withheld_list(), "cut": cut,
            "counts": {"vehicles": len(vehicles), "phones": len(phones), "travellers": len(travellers), "residents": len(residents), "incidents": len(incidents)}}


def area_events(found: dict[str, Any]) -> list[dict[str, Any]]:
    """An area answer as a dated list of presences, for a geofence watch."""
    out = []
    for group in ("vehicles", "phones", "travellers"):
        for item in found[group]:
            rec = item["record"]
            for r in item["reads"]:
                if group == "travellers":
                    title = f"{rec['title']} {r['kind']} {r['place']}"
                elif group == "phones":
                    title = f"{rec['title']} in use near {r['place']}"
                else:
                    title = f"{rec['title']} seen at {r['place']}"
                owner = item.get("owner")
                night = _night(r["at"])
                out.append(_event(r["at"], {"vehicles": "sighting", "phones": "call", "travellers": "travel"}[group], title,
                                  f"Registered to {owner['label']}" if owner else (r.get("detail") or ""), r["source"], r["record"],
                                  via=_ref(rec), other=owner, lat=r["lat"], lon=r["lon"], place=r["place"],
                                  priority="medium" if night else "low", why="Present late at night" if night else None,
                                  emph=[rec["title"], r["place"]]))
    out.sort(key=lambda e: e["at"] or "", reverse=True)
    return out


def dumps_area(lat: float, lon: float, radius_km: float, label: str) -> str:
    return json.dumps({"lat": lat, "lon": lon, "radius_km": radius_km, "label": label})

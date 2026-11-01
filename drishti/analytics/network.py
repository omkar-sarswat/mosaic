"""Case networks and evidence-based suspect ranking.

From a case's seed records (FIRs, complaints, ECIR/RC, accounts and phones they name) DRISHTI
builds the case network:
  1. seeds -> the people, organisations, accounts and phones they name;
  2. money traced forwards and backwards from every seed account (multi-hop, apportioned);
  3. holders, signatories, directors and controllers of every account and company reached;
  4. communications: frequent contacts, shared handsets, co-location on the same cell tower;
  5. family of key people (context, one hop).

Every person in the network is then ranked by EVIDENCE of what they did in the data: alerts
on accounts they hold or control, illicit money they received, companies they run, calls with
accused, co-location, lifestyle against income. Never by who they are. Each rank carries its
reasons, and a role is inferred (controller / beneficiary, facilitator, money mule, nominee,
operative, victim, associate). Ranks are leads for an investigating officer, not findings.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from ..graph import betweenness
from ..store import Store
from .money import Ledger, trace

HUB_KINDS = {"merchant", "department", "crypto_exchange", "bank", "police_station"}
SEV_W = {"high": 10.0, "medium": 5.0, "low": 2.0}
HUB_CITIES = {"Dubai", "Singapore", "Hong Kong", "Kathmandu", "Bangkok", "Colombo"}


def _links(store: Store, ids: list[str], types: tuple[str, ...] | None = None) -> list[dict[str, Any]]:
    out = []
    for i in range(0, len(ids), 300):
        chunk = ids[i:i + 300]
        q = ",".join("?" * len(chunk))
        sql = f"SELECT id, type, src, dst, props, status FROM links WHERE (src IN ({q}) OR dst IN ({q})) AND status IN ('active','auto','confirmed')"
        params: list[Any] = [*chunk, *chunk]
        if types:
            sql += f" AND type IN ({','.join('?' * len(types))})"
            params += list(types)
        out += [dict(r) for r in store.query(sql, params)]
    return out


def case_seeds(store: Store, case_id: str) -> list[str]:
    return [r["object_id"] for r in store.query("SELECT object_id FROM case_objects WHERE case_id=?", (case_id,))]


def build_network(store: Store, seeds: list[str], ledger: Ledger | None = None, *, trace_hops: int = 6) -> dict[str, Any]:
    L = ledger or Ledger(store)
    nodes: set[str] = set(seeds)
    why: dict[str, str] = {s: "case record" for s in seeds}
    # 1. what the seeds name (and same_as clusters of named people)
    first = _links(store, seeds)
    for l in first:
        for x in (l["src"], l["dst"]):
            if x not in nodes and not x.startswith(("adminunit:", "organisation:")) or (x.startswith("organisation:") and L.kind.get(x) not in HUB_KINDS):
                nodes.add(x)
                why.setdefault(x, f"named in case record ({l['type']})")
    resolved = _links(store, [n for n in nodes if n.startswith("person:")], ("same_as",))
    for l in resolved:
        for x in (l["src"], l["dst"]):
            if x not in nodes:
                nodes.add(x)
                why.setdefault(x, "same person (entity resolution)")
    # 2. accounts of seeds and money tracing
    seed_accts = {n for n in nodes if n.startswith(("bankaccount:", "cryptowallet:"))}
    for n in list(nodes):
        if n.startswith(("person:", "organisation:")):
            seed_accts |= {a for a, h in L.holder.items() if h == n}
            seed_accts |= {a for a, ss in L.signatories.items() if n in ss}
    traced = {}
    for direction in ("out", "in"):
        t = trace(L, sorted(seed_accts), direction=direction, hops=trace_hops, min_amount=1_00_000, window_days=120, max_links=400)
        traced[direction] = t
        for nd in t["nodes"]:
            if nd["id"] != "CASH" and L.kind.get(L.holder.get(nd["id"], ""), "") not in HUB_KINDS:
                nodes.add(nd["id"])
                why.setdefault(nd["id"], f"money traced ({'onward' if direction == 'out' else 'source'})")
    # 3. holders, signatories, directors, controllers
    accts = [n for n in nodes if n.startswith(("bankaccount:", "cryptowallet:"))]
    for a in accts:
        h = L.holder.get(a)
        if h and L.kind.get(h, "") not in HUB_KINDS:
            nodes.add(h)
            why.setdefault(h, "holds an account in the money trail")
        for sgn in L.signatories.get(a, []):
            nodes.add(sgn)
            why.setdefault(sgn, "signatory on an account in the money trail")
    orgs = [n for n in nodes if n.startswith("organisation:")]
    for l in _links(store, orgs, ("director_of", "controls", "registered_at")):
        for x in (l["src"], l["dst"]):
            if x not in nodes:
                nodes.add(x)
                why.setdefault(x, f"{l['type'].replace('_', ' ')} a company in the network")
    # 4. communications
    persons = [n for n in nodes if n.startswith("person:")]
    phone_links = _links(store, persons, ("uses_phone",))
    phone_of = defaultdict(list)
    for l in phone_links:
        phone_of[l["src"]].append(l["dst"])
        nodes.add(l["dst"])
    phones = [p for ps in phone_of.values() for p in ps]
    comm = _links(store, phones, ("called", "sim_in_device"))
    for l in comm:
        for x in (l["src"], l["dst"]):
            nodes.add(x)
    devices = [x for l in comm for x in (l["src"], l["dst"]) if x.startswith("device:")]
    for l in _links(store, list(set(devices)), ("sim_in_device",)):
        nodes.add(l["src"])
    new_phones = [n for n in nodes if n.startswith("phone:") and n not in phones]
    for l in _links(store, new_phones, ("uses_phone",)):
        if l["src"] not in nodes:
            nodes.add(l["src"])
            why.setdefault(l["src"], "frequent contact / shared handset with a network member")
    # 5. family (one hop) of people with any money or record evidence
    for l in _links(store, [n for n in nodes if n.startswith("person:")], ("relative_of",)):
        for x in (l["src"], l["dst"]):
            if x not in nodes:
                nodes.add(x)
                why.setdefault(x, "family of a network member")
    return {"nodes": nodes, "why": why, "traced": traced, "seed_accounts": sorted(seed_accts), "seeds": list(seeds)}


def colocation(store: Store, phones: dict[str, list[str]], window_h: float = 2.0) -> dict[tuple[str, str], int]:
    """Pairs of people whose phones hit the same cell tower within `window_h` hours, counted by distinct days."""
    number_of = {r["id"]: json.loads(r["props"])["number"] for r in store.query("SELECT id, props FROM objects WHERE type='Phone'")}
    owner_by_number = {number_of[p]: person for person, ps in phones.items() for p in ps if p in number_of}
    if not owner_by_number:
        return {}
    q = ",".join("?" * len(owner_by_number))
    hits = store.query(f"SELECT a_number, ts, tower_id FROM cdrs WHERE tower_id IS NOT NULL AND a_number IN ({q})", list(owner_by_number))
    by_tower = defaultdict(list)
    for h in hits:
        by_tower[h["tower_id"]].append((h["ts"], owner_by_number[h["a_number"]]))
    pairs: dict[tuple[str, str], set[str]] = defaultdict(set)
    for evs in by_tower.values():
        evs.sort()
        for i, (t1, p1) in enumerate(evs):
            for t2, p2 in evs[i + 1:]:
                if (datetime.fromisoformat(t2) - datetime.fromisoformat(t1)) > timedelta(hours=window_h):
                    break
                if p1 != p2:
                    pairs[tuple(sorted((p1, p2)))].add(t1[:10])
    return {k: len(v) for k, v in pairs.items()}


def rank_suspects(store: Store, net: dict[str, Any], ledger: Ledger | None = None, *, accused: set[str] | None = None) -> list[dict[str, Any]]:
    L = ledger or Ledger(store)
    nodes = net["nodes"]
    persons = sorted(n for n in nodes if n.startswith("person:"))
    if not persons:
        return []
    ids = sorted(nodes)
    objs: dict[str, tuple] = {}
    for i in range(0, len(ids), 500):
        chunk = ids[i:i + 500]
        for r in store.query(f"SELECT id, type, title, props FROM objects WHERE id IN ({','.join('?' * len(chunk))})", chunk):
            objs[r["id"]] = (r["type"], r["title"], json.loads(r["props"]))
    alerts = defaultdict(list)
    for r in store.query("SELECT subject_id, rule, severity, score, amount, summary FROM alerts"):
        alerts[r["subject_id"]].append(dict(r))
    links = _links(store, ids)
    held, signs, controls, directs, employer = (defaultdict(set) for _ in range(5))
    phones = defaultdict(list)
    complainant, accused_in = defaultdict(int), defaultdict(list)
    same, rel = defaultdict(set), defaultdict(set)
    calls = defaultdict(lambda: defaultdict(int))
    device_of_phone = defaultdict(set)
    owns = defaultdict(set)
    for l in links:
        t, a, b = l["type"], l["src"], l["dst"]
        if t == "holds_account":
            held[a].add(b)
        elif t == "signatory_of":
            held[a].add(b)
            signs[a].add(b)
        elif t == "controls":
            controls[a].add(b)
        elif t == "director_of":
            directs[a].add(b)
        elif t == "employee_of":
            employer[a].add(b)
        elif t == "uses_phone":
            phones[a].append(b)
        elif t == "complainant_in":
            complainant[a] += 1
        elif t == "accused_in":
            accused_in[a].append(b)
        elif t == "same_as":
            same[a].add(b)
            same[b].add(a)
        elif t == "relative_of":
            rel[a].add(b)
            rel[b].add(a)
        elif t == "called":
            n = json.loads(l["props"] or "{}").get("count", 1)
            calls[a][b] += n
            calls[b][a] += n
        elif t == "sim_in_device":
            device_of_phone[a].add(b)
        elif t == "owns":
            owns[a].add(b)
    extra = sorted({e for es in employer.values() for e in es} - set(objs))
    if extra:
        for r in store.query(f"SELECT id, type, title, props FROM objects WHERE id IN ({','.join('?' * len(extra))})", extra):
            objs[r["id"]] = (r["type"], r["title"], json.loads(r["props"]))
    for p in persons:
        for other in same.get(p, ()):
            accused_in[p] += accused_in.get(other, [])
    # hop distance from the case records: evidence far from the case counts for less
    adj = defaultdict(set)
    for l in links:
        if l["src"] in nodes and l["dst"] in nodes:
            adj[l["src"]].add(l["dst"])
            adj[l["dst"]].add(l["src"])
    dist = {x: 0 for x in net.get("seeds", []) if x in nodes}
    frontier = list(dist)
    while frontier:
        nxt = []
        for x in frontier:
            for y in adj.get(x, ()):
                if y not in dist:
                    dist[y] = dist[x] + 1
                    nxt.append(y)
        frontier = nxt
    owner_of_phone = {ph: p for p, phs in phones.items() for ph in phs}
    accused = set(accused or set()) | {p for p in persons if accused_in.get(p)}
    flagged_accts = {a for a, al in alerts.items() if a.startswith("bankaccount:") and any(x["severity"] == "high" for x in al)}
    hawala_accts = {a for a, h in L.holder.items() if L.kind.get(h) == "hawala_operator"}
    q = ",".join("?" * len(persons))
    assets = defaultdict(float)
    for r in store.query(f"SELECT l.src, o.props FROM links l JOIN objects o ON o.id=l.dst WHERE l.type='owns' AND o.type IN ('Property','Vehicle') AND l.src IN ({q})", persons):
        assets[r["src"]] += json.loads(r["props"]).get("value") or 0
    travel = defaultdict(list)
    for r in store.query(f"SELECT person_id, to_city FROM travel WHERE person_id IN ({q})", persons):
        travel[r["person_id"]].append(r["to_city"])
    coloc = colocation(store, {p: phones.get(p, []) for p in persons})
    seed_incidents = [objs[s] for s in net.get("seeds", []) if s in objs and objs[s][0] == "Incident"]
    seed_times = [datetime.fromisoformat(o[2]["occurred_at"]) for o in seed_incidents if o[2].get("occurred_at")]
    toll = defaultdict(int)
    vehicles = {v for vs in owns.values() for v in vs if v.startswith("vehicle:")}
    if vehicles and seed_times:
        for r in store.query(f"SELECT vehicle_id, ts FROM tollhits WHERE vehicle_id IN ({','.join('?' * len(vehicles))})", sorted(vehicles)):
            t = datetime.fromisoformat(r["ts"])
            if any(timedelta(0) <= st - t <= timedelta(hours=72) for st in seed_times):
                toll[r["vehicle_id"]] += 1

    def money_in(p: str) -> float:
        return sum(t[4] for a in held.get(p, ()) for t in L.inc.get(a, []) if t[2] in flagged_accts and t[2] not in held.get(p, ()))

    def money_out(p: str, targets: set[str]) -> float:
        return sum(t[4] for a in held.get(p, ()) for t in L.out.get(a, []) if t[3] in targets and t[3] not in held.get(p, ()))

    base: dict[str, dict[str, Any]] = {}
    for p in persons:
        typ, title, props = objs.get(p, ("Person", p, {}))
        if "aadhaar" not in props and same.get(p):
            continue  # a raw source record; its evidence counts on the resolved person
        f: dict[str, float] = defaultdict(float)
        ev: list[str] = []
        income = props.get("declared_income") or 0
        my_accts = held.get(p, set())
        org_ids = controls.get(p, set()) | directs.get(p, set())
        operates = bool(signs.get(p)) or bool(controls.get(p))
        for a in my_accts:
            for al in alerts.get(a, []):
                f["alerts"] += SEV_W[al["severity"]]
                ev.append(f"Account ··{objs.get(a, ('', a))[1][-4:]}: {al['summary']}")
        nominee_damp = 0.45 if (income < 3_00_000 and not operates) else 1.0
        for o in org_ids:
            for al in alerts.get(o, []):
                f["control"] += SEV_W[al["severity"]] * 0.9 * nominee_damp
                ev.append(f"{objs.get(o, ('', o))[1]}: {al['rule'].replace('_', ' ').lower()}")
            for a, h in L.holder.items():
                if h == o:
                    f["control"] += sum(SEV_W[al["severity"]] for al in alerts.get(a, [])) * 0.5 * nominee_damp
        for al in alerts.get(p, []):
            f["alerts"] += SEV_W[al["severity"]]
            ev.append(al["summary"])
        kinds = [objs.get(o, ("", "", {}))[2].get("kind") for o in org_ids]
        n_shell = sum(1 for o, k in zip(org_ids, kinds) if k in ("shell_company", "hawala_operator", "foreign_company", "trust")
                      or any(x["rule"] == "SHELL_COMPANY" for x in alerts.get(o, [])))
        if n_shell >= 2:
            f["control"] += 5 * n_shell * nominee_damp
            ev.append(f"Director / controller of {n_shell} shell, front or offshore entities")
        offshore = [o for o, k in zip(org_ids, kinds) if k == "foreign_company"]
        for o in offshore:
            amt = sum(t[4] for a, h in L.holder.items() if h == o for t in L.inc.get(a, []))
            f["offshore"] += 14
            ev.append(f"Controls offshore entity {objs.get(o, ('', o))[1]} ({objs.get(o, ('', '', {}))[2].get('country')}) that received Rs {amt:,.0f}")
        rcv = money_in(p)
        if rcv >= 1_00_000:
            f["money"] += min(30, 9 * math.log10(rcv / 1_00_000 + 1))
            ev.append(f"Received Rs {rcv:,.0f} from flagged accounts")
        fam_rcv = sum(money_in(r) for r in rel.get(p, ()) if r in persons)
        fam_assets = sum(assets.get(r, 0) for r in rel.get(p, ()))
        if fam_rcv >= 10_00_000:
            f["family"] += min(20, 7 * math.log10(fam_rcv / 1_00_000 + 1))
            ev.append(f"Family members received Rs {fam_rcv:,.0f} from flagged accounts")
        to_hawala = money_out(p, hawala_accts - my_accts)
        if to_hawala >= 5_00_000:
            f["funding"] += min(15, 5 * math.log10(to_hawala / 1_00_000 + 1))
            ev.append(f"Paid Rs {to_hawala:,.0f} to a hawala operator")
        paid_accused = money_out(p, {a for x in accused for a in held.get(x, ())} - my_accts)
        if paid_accused >= 50_000:
            f["funding"] += 8
            ev.append(f"Paid Rs {paid_accused:,.0f} to accused person(s)")
        if accused_in.get(p):
            f["records"] += min(20, 10 * len(accused_in[p]))
            ev.append(f"Accused in {len(set(accused_in[p]))} case record(s)")
        my_devices = {d for ph in phones.get(p, []) for d in device_of_phone.get(ph, ())}
        sharers = {owner_of_phone.get(ph) for ph, ds in device_of_phone.items() if ds & my_devices} - {p, None}
        if sharers:
            f["device"] += min(20, 8 * len(sharers))
            ev.append(f"Handset shared with {len(sharers)} other people")
        contacts = {owner_of_phone.get(o2) for ph in phones.get(p, []) for o2, n in calls.get(ph, {}).items() if n >= 5} - {p, None}
        acc_contacts = contacts & accused
        if acc_contacts:
            f["comms"] += min(12, 4 * len(acc_contacts))
            ev.append(f"Frequent calls with {len(acc_contacts)} accused / named person(s)")
        foreign = {o2 for ph in phones.get(p, []) for o2 in calls.get(ph, {}) if objs.get(o2, ("", "", {}))[2].get("operator") == "Foreign"}
        if foreign:
            f["comms"] += 7
            ev.append(f"Repeated calls to {len(foreign)} unidentified foreign number(s)")
        for (x, y), days in coloc.items():
            if p in (x, y) and days >= 2:
                other = y if p == x else x
                f["coloc"] += 20 if other in accused else 6
                ev.append(f"Phone co-located with {objs.get(other, ('', other))[1]} on {days} separate days")
        for v in owns.get(p, ()):
            if toll.get(v):
                f["movement"] += min(24, 6 * toll[v])
                ev.append(f"Vehicle {objs.get(v, ('', v))[1]} crossed {toll[v]} toll plazas in the 72 h before a case incident")
        a_val = assets.get(p, 0) + 0.8 * fam_assets
        if a_val >= 50_00_000 and a_val > 12 * max(income, 1):
            f["lifestyle"] += 12
            ev.append(f"Own and family assets Rs {a_val:,.0f} vs declared income Rs {income:,.0f}")
        hubs = [c for c in travel.get(p, []) if c in HUB_CITIES]
        if len(hubs) >= 2:
            f["travel"] += min(10, 2 * len(hubs))
            ev.append(f"{len(hubs)} trips to {', '.join(sorted(set(hubs)))}")
        bank_insider = any(objs.get(e, ("", "", {}))[2].get("kind") == "bank" for e in employer.get(p, ()))
        if bank_insider and any(x["rule"] == "THIRD_PARTY_CONDUIT" for x in alerts.get(p, [])):
            f["insider"] += 18
            ev.append("Bank official who received funds routed through a relative from the borrower's network")
        sent_total = sum(t[4] for a in my_accts for t in L.out.get(a, []) if t[3] in flagged_accts)
        victim = complainant.get(p, 0) > 0 and not accused_in.get(p) or (
            0 < sent_total < 5_00_000 and rcv == 0 and not f.get("alerts") and not org_ids and not accused_in.get(p) and not acc_contacts and not sharers)
        base[p] = {"f": f, "ev": ev, "victim": victim, "props": props, "title": title, "n_shell": n_shell, "rcv": rcv,
                   "fam_rcv": fam_rcv, "offshore": offshore, "contacts": contacts, "acc_contacts": acc_contacts, "income": income,
                   "assets": a_val, "insider": bank_insider and f.get("insider"), "accts": my_accts, "sharers": sharers}

    def raw_of(b: dict) -> float:
        return sum(b["f"].values())

    # organiser signal: frequent contact with several strong suspects
    strong = {p for p, b in base.items() if raw_of(b) >= 35 and not b["victim"]}
    for p, b in base.items():
        ties = (b["contacts"] & strong) - {p}
        if len(ties) >= 2:
            b["f"]["organiser"] += min(18, 6 * len(ties))
            b["ev"].append(f"Frequent contact with {len(ties)} strong suspects: " + ", ".join(sorted(base[t]["title"] for t in ties if t in base)[:4]))
    # centrality on the person graph (money + frequent calls + family)
    pg_edges = []
    acct_owner: dict[str, str] = {}
    for p in base:
        for a in held.get(p, ()):
            acct_owner[a] = p
    for a, owner in acct_owner.items():
        for t in L.out.get(a, []):
            o2 = acct_owner.get(t[3] or "")
            if o2 and o2 != owner:
                pg_edges.append((owner, o2))
    for p, b in base.items():
        for c in b["contacts"]:
            if c in base:
                pg_edges.append((p, c))
    central = betweenness(list(base), pg_edges) if 2 < len(base) <= 900 else {}
    top_c = max(central.values(), default=0.0) or 1e-9
    out = []
    for p, b in base.items():
        f = b["f"]
        if central:
            f["centrality"] += 12 * central.get(p, 0.0) / top_c
        raw = sum(f.values())
        d = min([dist.get(p, 9)] + [dist.get(x, 9) for x in same.get(p, ())])
        decay = 1.0 if d <= 4 else 0.75 if d <= 6 else 0.45
        score = 100 * (1 - math.exp(-raw * decay / 50))
        if decay < 1:
            b["ev"].append(f"{d} hops from the case records (weighted {decay:.0%})")
        if b["victim"]:
            score = min(score, 12)
        role = infer_role(b, alerts)
        out.append({"id": p, "name": b["title"], "score": round(score, 1), "role": role, "hops": d,
                    "factors": {k: round(v, 1) for k, v in f.items() if v}, "evidence": b["ev"][:14],
                    "why_in_network": net["why"].get(p, "connected to the network"), "city": b["props"].get("city"),
                    "occupation": b["props"].get("occupation"), "declared_income": b["income"]})
    out.sort(key=lambda x: -x["score"])
    return out


def infer_role(b: dict, alerts: dict) -> str:
    f = b["f"]
    rules = {x["rule"] for a in b["accts"] for x in alerts.get(a, [])}
    if b["victim"]:
        return "Victim / unwitting payer"
    if b["insider"]:
        return "Insider (public servant)"
    if "HAWALA_PATTERN" in rules:
        return "Hawala operator / cash-out"
    if b["offshore"] or (f.get("organiser") and (b["rcv"] + b["fam_rcv"]) >= 50_00_000):
        return "Suspected kingpin / ultimate beneficiary"
    if f.get("movement") or (f.get("funding") and f.get("comms")):
        return "Coordinator / organiser"
    if len(b.get("sharers", set()) & b.get("contacts", set())) >= 3:  # shares handsets with, and calls, several people
        return "Mule herder / recruiter"
    if ("MULE_PASS_THROUGH" in rules or "FRAUD_PROCEEDS" in rules) and b["income"] < 4_00_000:
        return "Money mule"
    if b["n_shell"] >= 2 and b["income"] < 3_00_000:
        return "Nominee director / front"
    if b["n_shell"] >= 2 or "LOAN_DIVERSION" in rules or "RECEIVED_DIVERTED_LOAN" in rules:
        return "Facilitator / layering"
    if "THIRD_PARTY_CONDUIT" in rules:
        return "Conduit for diverted funds"
    if f.get("coloc") or f.get("device") or (b["acc_contacts"] and f.get("comms", 0) >= 8):
        return "Suspected operative / associate"
    if b["fam_rcv"] >= 10_00_000 or b["rcv"] >= 10_00_000:
        return "Recipient / proxy holder of illicit funds"
    if f.get("records"):
        return "Accused (named in case record)"
    return "Associate (context)"

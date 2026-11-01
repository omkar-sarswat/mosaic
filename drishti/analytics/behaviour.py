"""Behaviour flags: per-person indicators of conduct, each with the records behind it.

Allowed inputs are what a person did or holds: handsets and SIMs, accounts and how they were
opened, money in and out, calls, journeys, property bought, companies run, FIRs. Never used:
name, religion, caste, community, gender, age, place of birth or residence as such, or
lawful association (meetings, protests, worship, journalism, political activity). The list
of features each flag reads is in FLAG_INPUTS, and tests check that no protected attribute
is read. A flag is a reason to look, not a finding; the dossier shows the evidence beside it.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any

from ..store import Store, utcnow
from .inference import Resolver
from .money import Ledger
from .network import HUB_CITIES

SEV_W = {"high": 10.0, "medium": 5.0, "low": 2.0, "info": 1.0}
PROTECTED = {"name", "name_native", "father_name", "gender", "dob", "birth_year", "age", "community", "religion", "caste", "nationality"}

FLAG_INPUTS: dict[str, tuple[str, list[str]]] = {
    "SHARED_HANDSET":        ("SIM used in a handset that also carried other people's SIMs", ["uses_phone", "sim_in_device"]),
    "MULTIPLE_SIMS":         ("Uses several mobile numbers", ["uses_phone"]),
    "NEW_ACCOUNTS_BURST":    ("Several bank accounts opened close together", ["BankAccount.opened_on", "holds_account"]),
    "MIN_KYC_ACCOUNTS":      ("Holds more than one minimum-KYC account", ["BankAccount.kyc", "holds_account"]),
    "CASH_INTENSIVE":        ("Large share of credits are cash deposits", ["txns"]),
    "TURNOVER_VS_INCOME":    ("Money through own accounts far exceeds declared income", ["txns", "Person.declared_income"]),
    "ACCOUNT_ALERTS":        ("Own accounts flagged by money-laundering typologies", ["alerts"]),
    "CONTROLS_FLAGGED_ENTITY": ("Director, controller or signatory of a flagged company / account", ["director_of", "controls", "signatory_of", "alerts"]),
    "PAYS_HAWALA":           ("Sends money to a hawala-pattern account", ["txns", "alerts", "Organisation.kind"]),
    "RECEIVES_FROM_VICTIMS": ("Own account received money directly from fraud complainants", ["txns", "complainant_in", "victim_in"]),
    "HUB_TRAVEL":            ("Repeated short trips to financial hubs abroad", ["travel"]),
    "FOREIGN_CALLS":         ("Frequent calls with foreign numbers", ["cdrs"]),
    "NIGHT_CALLING":         ("Calls concentrated between 23:00 and 05:00", ["cdrs"]),
    "CONTACT_WITH_ACCUSED":  ("Frequent calls with a person accused in an FIR", ["cdrs", "accused_in"]),
    "PROPERTY_VS_INCOME":    ("Recent property far above declared income", ["owns", "Property.value", "Property.registered_on", "Person.declared_income"]),
    "DORMANT_REACTIVATION":  ("Dormant account suddenly receives large sums", ["txns"]),
    "NOMINEE_DIRECTOR":      ("Low-income director of several companies", ["director_of", "Person.declared_income"]),
    "ACCUSED_ON_RECORD":     ("Named as accused in an FIR or complaint", ["accused_in"]),
}


class Flags:
    def __init__(self) -> None:
        self.rows: dict[str, list[dict[str, Any]]] = defaultdict(list)

    def add(self, pid: str, code: str, severity: str, summary: str, evidence: dict[str, Any] | None = None) -> None:
        if any(f["code"] == code for f in self.rows[pid]):
            return
        self.rows[pid].append({"code": code, "severity": severity, "weight": SEV_W[severity], "title": FLAG_INPUTS[code][0],
                               "summary": summary, "evidence": evidence or {}, "inputs": FLAG_INPUTS[code][1]})


def _num(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def compute(store: Store, ledger: Ledger | None = None, today: date | None = None) -> Flags:
    ledger = ledger or Ledger(store)
    R = Resolver(store)
    F = Flags()
    today = today or date.fromisoformat(max((r["ts"] for r in store.query("SELECT MAX(ts) ts FROM txns") if r["ts"]), default=utcnow())[:10])
    year_ago = (today - timedelta(days=365)).isoformat()
    persons = {r["id"]: json.loads(r["props"]) for r in store.query("SELECT id, props FROM objects WHERE type='Person'")}
    canon = {R(p) for p in persons}
    income = {p: _num(persons.get(p, {}).get("declared_income")) for p in canon}
    links: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for r in store.query("SELECT type, src, dst FROM links WHERE status IN ('active','auto','confirmed') AND type IN "
                         "('uses_phone','sim_in_device','holds_account','signatory_of','director_of','controls','accused_in','complainant_in','victim_in','owns','relative_of')"):
        links[r["type"]].append((r["src"], r["dst"]))
    objs = {r["id"]: (r["type"], json.loads(r["props"])) for r in store.query(
        "SELECT id, type, props FROM objects WHERE type IN ('BankAccount','Phone','Organisation','Property','Device')")}
    alerts_on: dict[str, list[dict]] = defaultdict(list)
    for a in store.query("SELECT id, rule, severity, subject_id, summary FROM alerts"):
        alerts_on[a["subject_id"]].append(dict(a))

    # ---- phones
    phones_of: dict[str, set[str]] = defaultdict(set)
    users_of: dict[str, set[str]] = defaultdict(set)
    for p, ph in links["uses_phone"]:
        if p.startswith("person:"):
            phones_of[R(p)].add(ph)
            users_of[ph].add(R(p))
    in_device: dict[str, set[str]] = defaultdict(set)
    for ph, dev in links["sim_in_device"]:
        in_device[dev].add(ph)
    for dev, phs in in_device.items():
        users = {u for ph in phs for u in users_of.get(ph, ())}
        if len(users) >= 2:
            for u in users:
                others = len(users) - 1
                F.add(u, "SHARED_HANDSET", "high" if others >= 3 else "medium",
                      f"Handset {objs.get(dev, ('', {}))[1].get('imei', dev)} carried SIMs of {others} other people",
                      {"device": dev, "phones": sorted(phs), "people": len(users)})
    for p, phs in phones_of.items():
        if len(phs) >= 3:
            F.add(p, "MULTIPLE_SIMS", "medium" if len(phs) >= 5 else "low", f"Uses {len(phs)} mobile numbers", {"phones": sorted(phs)})

    # ---- accounts
    accts_of: dict[str, set[str]] = defaultdict(set)
    signs_for: dict[str, set[str]] = defaultdict(set)
    for p, a in links["holds_account"]:
        if p.startswith("person:"):
            accts_of[R(p)].add(a)
    for p, a in links["signatory_of"]:
        signs_for[R(p)].add(a)
    for p, accts in accts_of.items():
        opened = sorted((objs[a][1].get("opened_on"), a) for a in accts if a in objs and objs[a][1].get("opened_on"))
        for i in range(len(opened)):
            win = [x for x in opened[i:] if (date.fromisoformat(x[0]) - date.fromisoformat(opened[i][0])).days <= 120]
            if len(win) >= 3:
                F.add(p, "NEW_ACCOUNTS_BURST", "medium", f"{len(win)} accounts opened within 120 days from {win[0][0]}", {"accounts": [x[1] for x in win]})
                break
        mins = [a for a in accts if objs.get(a, ("", {}))[1].get("kyc") == "min"]
        if len(mins) >= 2:
            F.add(p, "MIN_KYC_ACCOUNTS", "medium", f"{len(mins)} minimum-KYC accounts", {"accounts": mins})
        credits = cash = 0.0
        for a in accts:
            for t in ledger.inc.get(a, []):
                if t[1] >= year_ago:
                    credits += t[4]
                    cash += t[4] if t[2] is None else 0
            # dormant then active: a gap of 180+ days, then >= Rs 5 lakh in within 30 days
            ins = ledger.inc.get(a, [])
            seq = sorted(t[1] for t in ins + ledger.out.get(a, []))
            for prev, nxt in zip(seq, seq[1:]):
                if (datetime.fromisoformat(nxt) - datetime.fromisoformat(prev)).days >= 180:
                    burst = sum(t[4] for t in ins if nxt <= t[1] <= (datetime.fromisoformat(nxt) + timedelta(days=30)).isoformat())
                    if burst >= 500_000:
                        F.add(p, "DORMANT_REACTIVATION", "medium", f"Account idle {(datetime.fromisoformat(nxt) - datetime.fromisoformat(prev)).days} days, then Rs {burst:,.0f} in 30 days",
                              {"account": a, "idle_from": prev[:10], "active_from": nxt[:10]})
                        break
        if cash >= 1_000_000 and cash / credits >= 0.5 and cash >= 2 * max(income.get(p, 0), 1):
            F.add(p, "CASH_INTENSIVE", "medium", f"Rs {cash:,.0f} of Rs {credits:,.0f} credited in the last year was cash deposited (declared income Rs {income.get(p, 0):,.0f})",
                  {"cash_deposits": round(cash), "credits": round(credits)})
        inc = income.get(p, 0)
        if credits >= 2_000_000 and credits >= 5 * max(inc, 1):
            F.add(p, "TURNOVER_VS_INCOME", "high" if credits >= 20 * max(inc, 1) else "medium",
                  f"Rs {credits:,.0f} credited in a year against declared income Rs {inc:,.0f}", {"credits": round(credits), "declared_income": inc})
        flagged = [al for a in accts for al in alerts_on.get(a, [])] + alerts_on.get(p, [])
        if flagged:
            sev = "high" if any(al["severity"] == "high" for al in flagged) else "medium"
            F.add(p, "ACCOUNT_ALERTS", sev, f"{len(flagged)} typology alert(s): " + ", ".join(sorted({al['rule'] for al in flagged})),
                  {"alerts": [al["id"] for al in flagged][:12]})

    # ---- companies and accounts they run for others
    directors: dict[str, set[str]] = defaultdict(set)
    for t in ("director_of", "controls"):
        for p, org in links[t]:
            if p.startswith("person:"):
                directors[R(p)].add(org)
    org_accts: dict[str, set[str]] = defaultdict(set)
    for org, a in links["holds_account"]:
        org_accts[org].add(a)
    for p in set(directors) | set(signs_for):
        hits = []
        for org in directors.get(p, ()):
            hits += [(org, al) for al in alerts_on.get(org, [])] + [(org, al) for a in org_accts.get(org, ()) for al in alerts_on.get(a, [])]
        for a in signs_for.get(p, ()):
            if a not in accts_of.get(p, ()):
                hits += [(a, al) for al in alerts_on.get(a, [])]
        if hits:
            F.add(p, "CONTROLS_FLAGGED_ENTITY", "high", f"Runs or signs for {len({h[0] for h in hits})} flagged entity/account(s): "
                  + ", ".join(sorted({h[1]['rule'] for h in hits})), {"entities": sorted({h[0] for h in hits}), "alerts": [h[1]["id"] for h in hits][:12]})
    for p, orgs in directors.items():
        small = [o for o in orgs if objs.get(o, ("", {}))[1].get("kind") in ("company", "shell_company")]
        if len(small) >= 2 and income.get(p, 0) < 300_000:
            F.add(p, "NOMINEE_DIRECTOR", "medium", f"Director of {len(small)} companies on declared income Rs {income.get(p, 0):,.0f}", {"companies": small})

    # ---- money to hawala, money from victims
    hawala_accts = {a for a, als in alerts_on.items() if any(al["rule"] == "HAWALA_PATTERN" for al in als)}
    hawala_accts |= {a for o, accts in org_accts.items() if objs.get(o, ("", {}))[1].get("kind") == "hawala_operator" for a in accts}
    victim_accts: dict[str, str] = {}
    for t in ("complainant_in", "victim_in"):
        for v, _inc in links[t]:
            for a in accts_of.get(R(v), ()):
                victim_accts[a] = R(v)
    for p, accts in accts_of.items():
        to_h = [t for a in accts for t in ledger.out.get(a, []) if t[3] in hawala_accts and t[3] not in accts]
        if sum(t[4] for t in to_h) >= 100_000:
            F.add(p, "PAYS_HAWALA", "high", f"Rs {sum(t[4] for t in to_h):,.0f} sent to hawala-pattern account(s) in {len(to_h)} transfers", {"txns": [t[0] for t in to_h][:10]})
        from_v = [t for a in accts for t in ledger.inc.get(a, []) if t[2] in victim_accts and victim_accts[t[2]] != p]
        victims = {victim_accts[t[2]] for t in from_v}
        if len(victims) >= 2:
            F.add(p, "RECEIVES_FROM_VICTIMS", "high", f"Received Rs {sum(t[4] for t in from_v):,.0f} directly from {len(victims)} fraud complainants",
                  {"txns": [t[0] for t in from_v][:10], "complainants": sorted(victims)[:10]})

    # ---- property
    for p, prop in links["owns"]:
        if p.startswith("person:") and prop in objs and objs[prop][0] == "Property":
            pr = objs[prop][1]
            val, reg, inc = _num(pr.get("value")), pr.get("registered_on") or "", income.get(R(p), 0)
            if reg >= year_ago and val >= 5_000_000 and val >= 10 * max(inc, 1):
                F.add(R(p), "PROPERTY_VS_INCOME", "medium", f"{pr.get('label', 'Property')} worth Rs {val:,.0f} registered {reg} on declared income Rs {inc:,.0f}",
                      {"property": prop})

    # ---- travel
    trips: dict[str, list[dict]] = defaultdict(list)
    for t in store.query("SELECT person_id, ts, from_city, to_city FROM travel ORDER BY ts"):
        trips[R(t["person_id"])].append(dict(t))
    for p, ts in trips.items():
        out = [t for t in ts if t["to_city"] in HUB_CITIES and t["ts"] >= year_ago]
        short = 0
        for t in out:
            back = next((r for r in ts if r["from_city"] == t["to_city"] and r["ts"] > t["ts"]), None)
            if back and (datetime.fromisoformat(back["ts"]) - datetime.fromisoformat(t["ts"])).days <= 3:
                short += 1
        if len(out) >= 2:
            F.add(p, "HUB_TRAVEL", "medium" if short >= 2 else "low", f"{len(out)} trips to {', '.join(sorted({t['to_city'] for t in out}))} in a year, {short} returning within 3 days",
                  {"trips": len(out), "short_stays": short})

    # ---- calls
    number_owner = {}
    for ph, users in users_of.items():
        if len(users) == 1 and ph in objs:
            number_owner[objs[ph][1].get("number")] = next(iter(users))
    accused = {R(p) for p, _ in links["accused_in"] if p.startswith("person:")}
    family = {frozenset((R(a), R(b))) for a, b in links["relative_of"]}  # calls within a family say nothing
    stats: dict[str, dict[str, Any]] = defaultdict(lambda: {"n": 0, "night": 0, "foreign": defaultdict(int), "accused": defaultdict(int)})
    for r in store.query("SELECT ts, a_number, b_number FROM cdrs"):
        hour = int(r["ts"][11:13])
        for me, other in ((r["a_number"], r["b_number"]), (r["b_number"], r["a_number"])):
            p = number_owner.get(me)
            if not p:
                continue
            s = stats[p]
            s["n"] += 1
            s["night"] += hour >= 23 or hour < 5
            if other.startswith("+") and not other.startswith("+91"):
                s["foreign"][other[:4]] += 1
            o = number_owner.get(other)
            if o and o != p and o in accused and frozenset((p, o)) not in family:
                s["accused"][o] += 1
    for p, s in stats.items():
        nf = sum(s["foreign"].values())
        if nf >= 5:
            F.add(p, "FOREIGN_CALLS", "medium" if nf >= 15 else "low", f"{nf} calls with foreign numbers (prefixes {', '.join(sorted(s['foreign']))})", dict(s["foreign"]))
        if s["night"] >= 10 and s["night"] / s["n"] >= 0.3:
            F.add(p, "NIGHT_CALLING", "low", f"{s['night']} of {s['n']} calls between 23:00 and 05:00", {"night": s["night"], "total": s["n"]})
        freq = {o: n for o, n in s["accused"].items() if n >= 5}
        if freq and p not in accused:
            F.add(p, "CONTACT_WITH_ACCUSED", "low", f"Frequent calls with {len(freq)} person(s) accused in an FIR", {"people": sorted(freq), "calls": sum(freq.values())})
    for p in accused:
        F.add(p, "ACCUSED_ON_RECORD", "info", "Named as accused in an FIR or complaint", {})
    # only resolved people get flags; raw source records point at them
    return F


def run_behaviour(store: Store, ledger: Ledger | None = None) -> dict[str, Any]:
    F = compute(store, ledger)
    now = utcnow()
    rows = []
    counts: dict[str, int] = defaultdict(int)
    for pid, flags in F.rows.items():
        for f in flags:
            counts[f["code"]] += 1
            fid = "flag:" + hashlib.sha256(f"{pid}|{f['code']}".encode()).hexdigest()[:16]
            rows.append((fid, pid, f["code"], f["severity"], f["weight"], f["title"], f["summary"], json.dumps(f["evidence"], default=str), json.dumps(f["inputs"]), now))
    with store.tx() as conn:
        conn.execute("DELETE FROM behaviour_flags")
        conn.executemany("INSERT INTO behaviour_flags(id,subject_id,code,severity,weight,title,summary,evidence,inputs,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)", rows)
    return {"people_flagged": len(F.rows), "flags": len(rows), "by_code": dict(sorted(counts.items(), key=lambda x: -x[1]))}


def flags_for(store: Store, pid: str) -> list[dict[str, Any]]:
    rows = store.query("SELECT * FROM behaviour_flags WHERE subject_id=? ORDER BY weight DESC", (pid,))
    return [dict(r) | {"evidence": json.loads(r["evidence"]), "inputs": json.loads(r["inputs"])} for r in rows]


def scoreboard(store: Store, limit: int = 200) -> list[dict[str, Any]]:
    rows = store.query(f"SELECT subject_id, SUM(weight) score, COUNT(*) n, {store.group_concat('code')} codes, "
                       "SUM(CASE WHEN severity='high' THEN 1 ELSE 0 END) high FROM behaviour_flags GROUP BY subject_id "
                       f"HAVING SUM(weight) > 1 ORDER BY score DESC LIMIT {int(limit)}")
    return [dict(r) | {"codes": r["codes"].split(",")} for r in rows]

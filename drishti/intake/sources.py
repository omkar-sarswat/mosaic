"""Synthetic source extracts, deliberately messy the way real ones are.

Each extract is generated deterministically from records already in the (synthetic) store, so the
intake pipeline has real matches to find, plus new records, exact duplicates and broken rows. A few
patterns are planted so the interpretation lenses have something true to find: one mobile behind
several new customers, one person opening accounts in several branches, a cloned chassis number, a pair
who keep staying at the same hotel, a guest showing someone else's PAN, a date of birth that disagrees
with the record, a number that recurs across seized diary pages. The planted truth is returned under
"truth" for tests only; the pipeline never reads it. Nothing here is real personal data.
"""

from __future__ import annotations

import json
import random
from typing import Any

from ..store import Store

SOURCES: dict[str, dict[str, Any]] = {
    "kyc": {"title": "Bank KYC extract", "holder": "Indus Public Sector Bank (synthetic)", "legal": "Reply to BNSS s.94 notice", "kind": "table",
            "description": "Account-opening KYC rows exported from a core-banking system: account, IFSC, customer, PAN, mobile, date of birth, city."},
    "rto": {"title": "RTO vehicle register extract", "holder": "Regional Transport Office, Pune (synthetic)", "legal": "Reply to BNSS s.94 notice", "kind": "table",
            "description": "Registration rows: plate, owner, owner mobile, chassis and engine numbers, make, colour, registration date, RTO city."},
    "hotel": {"title": "Hotel guest registers", "holder": "Hotels in Mumbai and Pune (synthetic)", "legal": "Guest registers produced on police requisition", "kind": "table",
              "description": "Guest register pages: hotel, guest, mobile, ID shown, check-in and check-out, where the guest came from."},
    "notes": {"title": "Seized diary pages", "holder": "Seized at a search (synthetic)", "legal": "Seizure memo under BNSS s.105", "kind": "text",
              "description": "Hand-written pages transcribed as free text: names, mobiles, vehicles, accounts and amounts written in passing."},
}

FIRST = ["Kiran", "Pooja", "Imran", "Neha", "Rahul", "Sana", "Vikram", "Anita", "Sachin", "Meena", "Farhan", "Ganesh", "Rupali", "Tushar", "Ayesha", "Nitin"]
MIDDLE = ["Vasant", "Ramesh", "Yusuf", "Anil", "Prakash", "Iqbal", "Suresh", "Dilip", "Ravi", "Ajay", "Aziz", "Tukaram"]
SURNAME = ["Jadhav", "Kulkarni", "Shaikh", "Deshpande", "Gaikwad", "Ansari", "More", "Pawar", "Patil", "Shinde", "Qureshi", "Bhosale", "Kale", "Mane"]

CITY_DIRT = {"Mumbai": ["BOMBAY", "Bombay", " mumbai ", "MUMBAI"], "Pune": ["Poona", "PUNE", "pune "], "Thane": ["Thana", "THANE"],
             "Navi Mumbai": ["New Bombay", "Navi  Mumbai", "NAVI MUMBAI"], "Nashik": ["Nasik", "NASHIK"], "Kolhapur": ["kolhapur"],
             "Solapur": ["Sholapur"], "Bengaluru": ["Bangalore", "Banglore"], "New Delhi": ["Delhi", "DELHI"], "Panaji": ["Panjim", "Goa"]}


class Dirt:
    def __init__(self, seed: int):
        self.r = random.Random(seed)

    def name(self, n: str) -> str:
        parts = n.split()
        k = self.r.random()
        if k < 0.25:
            return n.upper()
        if k < 0.4 and len(parts) >= 2:
            return f"{parts[-1].upper()} {' '.join(parts[:-1]).upper()}"
        if k < 0.5 and len(parts) >= 3:
            return f"{parts[0][0]}. {parts[1][0]}. {parts[-1]}"
        if k < 0.6:
            return f"Mr. {n}"
        if k < 0.7:
            return "  ".join(parts)
        return n

    def phone(self, num: str | None) -> str:
        if not num:
            return "NA"
        k = self.r.random()
        if num.startswith("+"):
            return num
        if k < 0.2:
            return f"+91 {num[:5]} {num[5:]}"
        if k < 0.35:
            return f"0{num}"
        if k < 0.5:
            return f"{num[:5]}-{num[5:]}"
        if k < 0.58:
            return "NA"
        return num

    def pan(self, p: str | None) -> str:
        if not p:
            return "NA"
        k = self.r.random()
        return p.lower() if k < 0.15 else f"{p[:5]} {p[5:]}" if k < 0.25 else "" if k < 0.3 else p

    def date(self, iso: str | None) -> str:
        if not iso:
            return "-"
        y, m, d = iso[:10].split("-")
        mon = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][int(m) - 1]
        return self.r.choice([f"{d}/{m}/{y}", iso[:10], f"{d}-{mon}-{y}", f"{d}.{m}.{y}", f"{d}/{m}/{y}"])

    def city(self, c: str | None) -> str:
        if not c:
            return "NA"
        return self.r.choice(CITY_DIRT.get(c, [c])) if self.r.random() < 0.55 else c

    def acct(self, a: str) -> str:
        k = self.r.random()
        return " ".join(a[i:i + 4] for i in range(0, len(a), 4)) if k < 0.3 else "-".join(a[i:i + 4] for i in range(0, len(a), 4)) if k < 0.45 else a

    def reg(self, g: str) -> str:
        k = self.r.random()
        if k < 0.3:
            return f"{g[:2].lower()}-{g[2:4].lower()}-{g[4:-4].lower()}-{g[-4:]}"
        if k < 0.55:
            return f"{g[:2]} {g[2:4]} {g[4:-4]} {g[-4:]}"
        return g

    def fresh_name(self, used: set[str]) -> str:
        while True:
            n = f"{self.r.choice(FIRST)} {self.r.choice(MIDDLE)} {self.r.choice(SURNAME)}"
            if n not in used:
                used.add(n)
                return n

    def mobile(self) -> str:
        return self.r.choice("6789") + str(self.r.randint(10**8, 10**9 - 1))


def _people(store: Store) -> dict[str, dict[str, Any]]:
    return {r["id"]: json.loads(r["props"]) for r in store.query("SELECT id, props FROM objects WHERE type='Person'") if '"aadhaar"' in r["props"]}


def _phones_of(store: Store) -> dict[str, str]:
    out: dict[str, str] = {}
    for r in store.query("SELECT l.src, o.props FROM links l JOIN objects o ON o.id=l.dst WHERE l.type='uses_phone' AND o.type='Phone' ORDER BY l.src, o.id"):
        out.setdefault(r["src"], json.loads(r["props"]).get("number"))
    return out


def _kyc(store: Store, dirt: Dirt, people: dict, phones: dict, truth: dict) -> tuple[list[str], list[dict]]:
    r = dirt.r
    cols = ["account_number", "ifsc_code", "customer_name", "pan", "mobile", "date_of_birth", "city", "account_type"]
    accts = store.query("SELECT o.id, o.props, l.src holder FROM objects o JOIN links l ON l.dst=o.id AND l.type='holds_account' "
                        "WHERE o.type='BankAccount' AND l.src LIKE 'person:%' ORDER BY o.id")
    accts = [a for a in accts if a["holder"] in people]
    rows: list[dict[str, Any]] = []
    for a in r.sample(accts, min(120, len(accts))):
        p, ap = people[a["holder"]], json.loads(a["props"])
        rows.append({"account_number": dirt.acct(ap["account_no"]), "ifsc_code": ap.get("ifsc", "").lower() if r.random() < 0.3 else ap.get("ifsc", ""),
                     "customer_name": dirt.name(p["name"]), "pan": dirt.pan(p.get("pan")), "mobile": dirt.phone(phones.get(a["holder"])),
                     "date_of_birth": dirt.date(p.get("dob")), "city": dirt.city(p.get("city")),
                     "account_type": r.choice({"savings": ["SB", "Savings", "SAVINGS"], "current": ["CA", "Current"]}.get(ap.get("account_type"), ["SB", "Savings"]))})
    # planted: dates of birth that disagree with the record
    for x in [x for x in rows if x["date_of_birth"] not in ("-", "")][3:5]:
        x["date_of_birth"] = "01/01/1990"
        truth.setdefault("dob_conflict", []).append(x["account_number"])
    used = {p["name"] for p in people.values()}
    ring = dirt.mobile()
    for i in range(12):  # customers new to the platform; the first four share one mobile (the mule-account pattern)
        acct = str(r.randint(10**11, 10**12 - 1))
        if i < 4:
            truth.setdefault("shared_mobile", []).append(acct)
        rows.append({"account_number": dirt.acct(acct), "ifsc_code": "INPB0" + str(r.randint(100000, 999999)), "customer_name": dirt.name(dirt.fresh_name(used)),
                     "pan": "NA", "mobile": dirt.phone(ring) if i < 4 else dirt.phone(dirt.mobile()),
                     "date_of_birth": dirt.date(f"19{r.randint(70, 99)}-0{r.randint(1, 9)}-1{r.randint(0, 9)}"),
                     "city": dirt.city(r.choice(["Mumbai", "Pune", "Thane", "Nashik", "Kolhapur"])), "account_type": "SB"})
        if i < 4 and rows[-1]["mobile"] == "NA":
            rows[-1]["mobile"] = ring
    # planted: one person already on record opens accounts in three more branches
    owner = next(pid for pid in sorted(people) if people[pid].get("pan") and phones.get(pid))
    po = people[owner]
    truth["many_accounts_person"] = owner
    for _ in range(3):
        acct = str(r.randint(10**11, 10**12 - 1))
        truth.setdefault("many_accounts", []).append(acct)
        rows.append({"account_number": dirt.acct(acct), "ifsc_code": "INPB0" + str(r.randint(100000, 999999)), "customer_name": dirt.name(po["name"]),
                     "pan": po["pan"], "mobile": dirt.phone(phones[owner]), "date_of_birth": dirt.date(po.get("dob")),
                     "city": dirt.city(r.choice(["Mumbai", "Pune", "Nashik"])), "account_type": r.choice(["SB", "CA"])})
    rows += [dict(x) for x in r.sample(rows[:120], 6)]  # exact duplicates
    rows += [{"account_number": "NA", "ifsc_code": "", "customer_name": "", "pan": "", "mobile": "", "date_of_birth": "", "city": "", "account_type": ""},
             {"account_number": "12AB", "ifsc_code": "XYZ", "customer_name": "TEST CUSTOMER", "pan": "AAAAA0000A", "mobile": "0000000000", "date_of_birth": "31/02/2001", "city": "?", "account_type": "SB"}]
    return cols, rows


def _rto(store: Store, dirt: Dirt, people: dict, phones: dict, truth: dict) -> tuple[list[str], list[dict]]:
    r = dirt.r
    cols = ["reg_no", "owner_name", "owner_mobile", "chassis_no", "engine_no", "maker_model", "colour", "reg_date", "rto_city"]
    vs = store.query("SELECT o.id, o.props, l.src owner FROM objects o JOIN links l ON l.dst=o.id AND l.type='owns' WHERE o.type='Vehicle' AND l.src LIKE 'person:%' ORDER BY o.id")
    vs = [v for v in vs if v["owner"] in people]
    colours = {"White": ["WHT", "white", "WHITE"], "Black": ["BLK", "black"], "Silver": ["SLV", "silver", "Silver Grey"], "Red": ["RED", "red"], "Grey": ["GRY", "grey", "Gray"]}
    chassis = lambda: f"MA3{''.join(r.choice('ABCDEFGHJKLMNPRSTUVWXYZ') for _ in range(4))}{r.randint(10**9, 10**10 - 1)}"  # noqa: E731
    rows: list[dict[str, Any]] = []
    for v in r.sample(vs, min(90, len(vs))):
        p, vp = people[v["owner"]], json.loads(v["props"])
        col = vp.get("colour", "White")
        rows.append({"reg_no": dirt.reg(vp["registration_no"]), "owner_name": dirt.name(p["name"]), "owner_mobile": dirt.phone(phones.get(v["owner"])),
                     "chassis_no": vp.get("chassis_no") or chassis(), "engine_no": vp.get("engine_no") or f"K{r.randint(10**6, 10**7 - 1)}",
                     "maker_model": vp.get("make", "").upper() if r.random() < 0.4 else vp.get("make", ""),
                     "colour": r.choice(colours.get(col, [col])), "reg_date": dirt.date(f"20{r.randint(10, 25)}-0{r.randint(1, 9)}-1{r.randint(0, 9)}"),
                     "rto_city": dirt.city(p.get("city"))})
    used = {p["name"] for p in people.values()}
    fleet_owner, fleet_mobile = dirt.fresh_name(used), dirt.mobile()
    for i in range(10):  # vehicles new to the platform; one new owner registers three of them in one month
        fleet = i < 3
        reg = f"MH{r.randint(1, 48):02d}{r.choice(['AB', 'CD', 'EF', 'GH'])}{r.randint(1000, 9999)}"
        if fleet:
            truth.setdefault("fleet", []).append(reg)
        rows.append({"reg_no": dirt.reg(reg), "owner_name": dirt.name(fleet_owner if fleet else dirt.fresh_name(used)),
                     "owner_mobile": fleet_mobile if fleet else dirt.phone(dirt.mobile()), "chassis_no": chassis(), "engine_no": f"K{r.randint(10**6, 10**7 - 1)}",
                     "maker_model": r.choice(["Honda City", "MARUTI SWIFT", "Hero Splendor"]), "colour": r.choice(["WHT", "Black"]),
                     "reg_date": dirt.date(f"2026-03-{r.randint(10, 28)}" if fleet else "2024-03-12"), "rto_city": dirt.city("Pune")})
    # planted: a new registration carrying the chassis number of a vehicle already in this register (a cloned vehicle)
    rows[-1]["chassis_no"] = rows[7]["chassis_no"]
    truth["cloned_chassis"] = rows[7]["chassis_no"]
    rows += [dict(x) for x in r.sample(rows[:90], 4)]
    rows += [{"reg_no": "UNKNOWN", "owner_name": "", "owner_mobile": "", "chassis_no": "", "engine_no": "", "maker_model": "", "colour": "", "reg_date": "", "rto_city": ""},
             {"reg_no": "MH 12", "owner_name": "XX", "owner_mobile": "123", "chassis_no": "", "engine_no": "", "maker_model": "", "colour": "", "reg_date": "", "rto_city": "Pune"}]
    return cols, rows


HOTELS = [("Hotel Sea Pearl, Colaba", "Mumbai"), ("Hotel Sunrise Residency, Swargate", "Pune"), ("Hotel Gateway Inn, Fort", "Mumbai"), ("Hotel Deccan Park, Shivajinagar", "Pune")]


def _hotel(store: Store, dirt: Dirt, people: dict, phones: dict, truth: dict) -> tuple[list[str], list[dict]]:
    r = dirt.r
    cols = ["hotel", "hotel_city", "guest_name", "guest_mobile", "id_type", "id_number", "check_in", "check_out", "coming_from"]
    pool = sorted(pid for pid in people if phones.get(pid))
    rows: list[dict[str, Any]] = []
    for pid in r.sample(pool, min(70, len(pool))):
        p = people[pid]
        h, hc = r.choice(HOTELS)
        ci = f"2026-{r.randint(1, 9):02d}-{r.randint(1, 26):02d}"
        idt = r.choice(["Aadhaar", "PAN", "Driving licence"])
        idn = {"Aadhaar": (p.get("aadhaar") if r.random() < 0.4 else f"XXXX XXXX {p.get('aadhaar', '0000')[-4:]}"), "PAN": dirt.pan(p.get("pan")), "Driving licence": p.get("dl_no") or "NA"}[idt]
        rows.append({"hotel": h, "hotel_city": dirt.city(hc), "guest_name": dirt.name(p["name"]), "guest_mobile": dirt.phone(phones.get(pid)), "id_type": idt,
                     "id_number": idn, "check_in": dirt.date(ci), "check_out": dirt.date(ci[:8] + f"{int(ci[8:]) + r.randint(1, 2):02d}"),
                     "coming_from": dirt.city(p.get("city"))})
    # planted: two people with no link on record who check in to the same hotel together three times
    linked = {(x["src"], x["dst"]) for x in store.query("SELECT src, dst FROM links WHERE src LIKE 'person:%' AND dst LIKE 'person:%'")}
    a, b = next((x, y) for x in pool[5::7] for y in pool[3::11] if x != y and (x, y) not in linked and (y, x) not in linked)
    truth["co_stay"] = sorted([a, b])
    for k, ci in enumerate(["2026-02-11", "2026-05-04", "2026-08-21"]):
        h, hc = HOTELS[k % len(HOTELS)]
        for pid in (a, b):
            p = people[pid]
            rows.append({"hotel": h, "hotel_city": dirt.city(hc), "guest_name": dirt.name(p["name"]), "guest_mobile": phones[pid], "id_type": "Driving licence",
                         "id_number": p.get("dl_no") or "NA", "check_in": dirt.date(ci), "check_out": dirt.date(ci[:8] + f"{int(ci[8:]) + 2:02d}"), "coming_from": dirt.city(p.get("city"))})
    # planted: a guest who shows another person's PAN
    g = next(pid for pid in pool if pid not in (a, b) and people[pid].get("pan"))
    other = next(pid for pid in reversed(pool) if people[pid].get("pan") and pid not in (a, b, g))
    truth["id_mismatch"] = {"guest": g, "pan_of": other}
    pg = people[g]
    rows.append({"hotel": HOTELS[1][0], "hotel_city": HOTELS[1][1], "guest_name": dirt.name(pg["name"]), "guest_mobile": phones[g], "id_type": "PAN",
                 "id_number": people[other]["pan"], "check_in": "14/09/2026", "check_out": "15/09/2026", "coming_from": dirt.city(pg.get("city"))})
    rows += [dict(x) for x in r.sample(rows[:70], 3)]
    rows += [{"hotel": "Hotel Sea Pearl, Colaba", "hotel_city": "Mumbai", "guest_name": "", "guest_mobile": "", "id_type": "", "id_number": "", "check_in": "", "check_out": "", "coming_from": ""}]
    return cols, rows


def _notes(store: Store, dirt: Dirt, people: dict, phones: dict, truth: dict) -> tuple[list[str], list[dict]]:
    """Free-text diary pages. Identifiers are written the way people write them (spaces, dashes, lakhs)."""
    r = dirt.r
    cols = ["page", "written_on", "text"]
    regs = {x["src"]: json.loads(x["props"])["registration_no"] for x in store.query(
        "SELECT l.src, o.props FROM links l JOIN objects o ON o.id=l.dst WHERE l.type='owns' AND o.type='Vehicle' ORDER BY l.src, o.id")}
    accts = {x["src"]: json.loads(x["props"])["account_no"] for x in store.query(
        "SELECT l.src, o.props FROM links l JOIN objects o ON o.id=l.dst WHERE l.type='holds_account' AND o.type='BankAccount' ORDER BY l.src, o.id")}
    pool = sorted(pid for pid in people if phones.get(pid) and (pid in regs or pid in accts))
    cast = r.sample(pool, min(14, len(pool)))
    courier = dirt.mobile()  # planted: a number with no name that recurs on several pages
    truth["recurring_number"] = courier
    places = ["Swargate", "Bhiwandi naka", "Vashi APMC", "the Thane toll", "Panvel bus stand", "Kurla depot"]
    rows = []
    for i, pid in enumerate(cast):
        p = people[pid]
        first = p["name"].split()[0]
        num = phones[pid]
        num_w = r.choice([num, f"{num[:5]} {num[5:]}", f"{num[:3]}-{num[3:6]}-{num[6:]}", f"+91{num}"])
        bits = [r.choice([f"Call {first} on {num_w} after 9.", f"{p['name']} - {num_w}.", f"Met {first} ({num_w}) at {r.choice(places)}."])]
        if pid in regs and r.random() < 0.7:
            g = regs[pid]
            bits.append(f"{r.choice(['White', 'Grey', 'Black'])} car {g[:2]} {g[2:4]} {g[4:-4]} {g[-4:]} parked at {r.choice(places)}.")
        if pid in accts:
            a = accts[pid]
            amt = r.choice(["2.5 L", "Rs 1,80,000", "75,000", "4 lakh", "1.2 Cr"])
            bits.append(f"Send {amt} to A/c {' '.join(a[k:k + 4] for k in range(0, len(a), 4))}.")
        if i % 4 == 1:
            bits.append(f"Delivery boy {courier[:5]} {courier[5:]} picks up from {r.choice(places)}.")
            truth.setdefault("recurring_pages", []).append(i + 1)
        rows.append({"page": str(i + 1), "written_on": dirt.date(f"2026-0{r.randint(3, 9)}-{r.randint(10, 28)}"), "text": " ".join(bits)})
    return cols, rows


def generate(store: Store, source: str, seed: int = 7) -> dict[str, Any]:
    if source not in SOURCES:
        raise KeyError(source)
    dirt = Dirt(seed + sum(map(ord, source)))  # stable across runs (str hash is randomised per process)
    truth: dict[str, Any] = {}
    cols, rows = {"kyc": _kyc, "rto": _rto, "hotel": _hotel, "notes": _notes}[source](store, dirt, _people(store), _phones_of(store), truth)
    return {"source": source, **SOURCES[source], "columns": cols, "rows": rows, "truth": truth}

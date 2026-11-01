"""Synthetic India: a fused, fully connected population for agency demos.

Every person carries the identity a real fusion platform assembles from many systems:
UIDAI eKYC (name, DOB, gender, Aadhaar), Income Tax (PAN, declared income), Passport Seva,
VAHAN / SARATHI (vehicles, driving licence), Election Commission (EPIC), telecom CAFs
(phones, subscriber names), bank KYC (accounts, UPI handles), land records (property),
airline PNRs (travel), FASTag (toll hits), CDRs under legal order (calls, cell towers),
CCTNS / I4C / ED / CBI / NIA / NCB case records. Each property keeps its source.

Nothing here is real. Aadhaar numbers deliberately FAIL the Verhoeff checksum UIDAI uses,
emails use the reserved .test domain, banks and companies are fictional, and every object
is flagged synthetic. Crime networks draw people from every community in proportion,
so no group is cast as the offender.

Five planted, interlinked operations give the analytics something real to find:

* MIRAGE (ED)     cyber-fraud proceeds layered through 7 shells, round-tripped via Dubai,
                  integrated into a Worli flat and luxury cars; the controller is not named
                  in the ECIR and must be found by tracing.
* MULE (I4C)      60 victims -> 18 mule accounts -> 3 aggregator accounts -> MIRAGE shells
                  and a crypto off-ramp; the herder shares handsets with mules.
* SUNRISE (CBI)   Rs 180 cr loan diverted within weeks to related firms, promoter family,
                  a Singapore entity; the branch manager is paid through a relative.
* KESTREL (NIA)   crowd-collected small donations to a front trust, cash-out and hawala to
                  a handler abroad; operatives co-located on recce dates.
* COASTLINE (NCB) port seizures, couriers paid by a coordinator whose truck's toll trail
                  matches the seizure dates.
One hawala operator serves MIRAGE, KESTREL and COASTLINE: the cross-case super-connector.
"""

from __future__ import annotations

import csv
import random
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ..resolve.names import normalize_name
from ..store import Store, make_id
from .namebank import CANARIES, COMMUNITIES, SPELLING_NOISE

# ------------------------------------------------------------------ geography
CITIES: dict[str, tuple[str, float, float, str]] = {
    # city: (district name in LGD, lat, lon, state code prefix for vehicles)
    "Mumbai": ("Mumbai City", 18.94, 72.83, "MH"), "Andheri": ("Mumbai Suburban", 19.12, 72.85, "MH"),
    "Thane": ("Thane", 19.20, 72.97, "MH"), "Navi Mumbai": ("Thane", 19.03, 73.03, "MH"),
    "Pune": ("Pune", 18.52, 73.86, "MH"), "Nagpur": ("Nagpur", 21.15, 79.09, "MH"),
    "Nashik": ("Nashik", 20.00, 73.79, "MH"), "Kolhapur": ("Kolhapur", 16.70, 74.24, "MH"),
    "Solapur": ("Solapur", 17.66, 75.91, "MH"), "Aurangabad": ("Aurangabad", 19.88, 75.34, "MH"),
    "Bhiwandi": ("Thane", 19.30, 73.06, "MH"), "Panvel": ("Raigad", 18.99, 73.12, "MH"),
    "Surat": ("Surat", 21.17, 72.83, "GJ"), "Ahmedabad": ("Ahmedabad", 23.02, 72.57, "GJ"),
    "New Delhi": ("New Delhi", 28.61, 77.21, "DL"), "Hyderabad": ("Hyderabad", 17.39, 78.49, "TS"),
    "Bengaluru": ("Bengaluru Urban", 12.97, 77.59, "KA"), "Kolkata": ("Kolkata", 22.57, 88.36, "WB"),
    "Jaipur": ("Jaipur", 26.91, 75.79, "RJ"), "Lucknow": ("Lucknow", 26.85, 80.95, "UP"),
    "Indore": ("Indore", 22.72, 75.86, "MP"), "Panaji": ("North Goa", 15.49, 73.83, "GA"),
    "Chennai": ("Chennai", 13.08, 80.27, "TN"), "Kochi": ("Ernakulam", 9.93, 76.27, "KL"),
}
CITY_WEIGHTS = {"Mumbai": 9, "Andheri": 7, "Thane": 7, "Navi Mumbai": 4, "Pune": 9, "Nagpur": 5, "Nashik": 4,
                "Kolhapur": 3, "Solapur": 3, "Aurangabad": 3, "Bhiwandi": 2, "Panvel": 2, "Surat": 3,
                "Ahmedabad": 3, "New Delhi": 4, "Hyderabad": 3, "Bengaluru": 4, "Kolkata": 2, "Jaipur": 2,
                "Lucknow": 2, "Indore": 2, "Panaji": 1, "Chennai": 2, "Kochi": 1}
FOREIGN = {
    "Dubai": ("AE", 25.20, 55.27), "Singapore": ("SG", 1.35, 103.82), "Hong Kong": ("HK", 22.32, 114.17),
    "Kathmandu": ("NP", 27.72, 85.32), "Bangkok": ("TH", 13.76, 100.50), "London": ("GB", 51.51, -0.13),
    "Colombo": ("LK", 6.93, 79.85),
}
AIRPORT = {"Mumbai": "BOM", "Andheri": "BOM", "Thane": "BOM", "Navi Mumbai": "BOM", "Pune": "PNQ", "Nagpur": "NAG",
           "New Delhi": "DEL", "Hyderabad": "HYD", "Bengaluru": "BLR", "Kolkata": "CCU", "Ahmedabad": "AMD",
           "Surat": "STV", "Jaipur": "JAI", "Lucknow": "LKO", "Indore": "IDR", "Panaji": "GOI", "Chennai": "MAA",
           "Kochi": "COK", "Dubai": "DXB", "Singapore": "SIN", "Hong Kong": "HKG", "Kathmandu": "KTM",
           "Bangkok": "BKK", "London": "LHR", "Colombo": "CMB"}

BANKS = [
    ("SYNA", "Sahyadri Bank (synthetic)", "@sahyadri"), ("SYNB", "Konkan National Bank (synthetic)", "@konkan"),
    ("SYNC", "Deccan Commercial Bank (synthetic)", "@deccan"), ("SYND", "Indus Public Sector Bank (synthetic)", "@indus"),
]
FOREIGN_BANK = ("SYNE", "Gulf Trade Bank (synthetic)")
OCCUPATIONS = [
    # occupation, weight, (income lo, hi) in rupees/year, cash-intensive
    ("Software engineer", 10, (900_000, 3_200_000), False), ("Teacher", 8, (400_000, 900_000), False),
    ("Shop owner", 9, (500_000, 1_800_000), True), ("Farmer", 7, (90_000, 350_000), True),
    ("Driver", 6, (180_000, 420_000), True), ("Student", 6, (0, 0), False), ("Labourer", 6, (90_000, 220_000), True),
    ("Doctor", 3, (1_800_000, 4_500_000), False), ("Chartered accountant", 2, (1_200_000, 3_500_000), False),
    ("Contractor", 4, (800_000, 4_000_000), True), ("Government clerk", 6, (450_000, 900_000), False),
    ("Retired", 5, (250_000, 700_000), False), ("Homemaker", 6, (0, 0), False), ("Sales executive", 6, (350_000, 900_000), False),
]
MERCHANTS = ["Annapurna Kirana Stores", "Metro Fuel Station", "City Care Pharmacy", "QuickKart Online", "Shree Electronics",
             "Highway Dhaba", "Sai Garments", "Royal Mobile Gallery", "Fresh Basket Supermarket", "Speedy Recharge Point",
             "Lakshmi Jewellers", "Udupi Cafe", "Green Leaf Hospital", "Vidya Coaching Classes", "Prime Cinemas"]
EMPLOYERS = ["Navkar Infotech Pvt Ltd", "Shubham Logistics Pvt Ltd", "Pragati Textiles Pvt Ltd", "Arya Pharma Pvt Ltd",
             "Konark Engineering Pvt Ltd", "Saraswati Education Trust", "Deccan Agro Foods Pvt Ltd", "Orbit Retail Pvt Ltd",
             "Zenith Healthcare Pvt Ltd", "Pinnacle Software Services Pvt Ltd"]


def _verhoeff_invalid(rng: random.Random) -> str:
    """A 12-digit Aadhaar-format number whose check digit is deliberately WRONG."""
    d = [[0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 2, 3, 4, 0, 6, 7, 8, 9, 5], [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
         [3, 4, 0, 1, 2, 8, 9, 5, 6, 7], [4, 0, 1, 2, 3, 9, 5, 6, 7, 8], [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
         [6, 5, 9, 8, 7, 1, 0, 4, 3, 2], [7, 6, 5, 9, 8, 2, 1, 0, 4, 3], [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
         [9, 8, 7, 6, 5, 4, 3, 2, 1, 0]]
    p = [[0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 5, 7, 6, 2, 8, 3, 0, 9, 4], [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
         [8, 9, 1, 6, 0, 4, 3, 5, 2, 7], [9, 4, 5, 3, 1, 2, 6, 8, 7, 0], [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
         [2, 7, 9, 3, 8, 0, 6, 4, 1, 5], [7, 0, 4, 6, 9, 1, 3, 2, 5, 8]]
    inv = [0, 4, 3, 2, 1, 5, 6, 7, 8, 9]
    body = str(rng.randint(2, 9)) + "".join(str(rng.randint(0, 9)) for _ in range(10))
    c = 0
    for i, ch in enumerate(reversed(body)):
        c = d[c][p[(i + 1) % 8][int(ch)]]
    valid = inv[c]
    wrong = (valid + rng.randint(1, 9)) % 10
    return body + str(wrong)


@dataclass
class P:
    """A synthetic person and everything attached to them."""
    oid: str
    name: str
    native: str
    first: str
    surname: str
    father: str
    gender: str
    dob: date
    city: str
    district: str | None
    occupation: str
    income: int
    pan: str
    aadhaar: str
    phones: list[str] = field(default_factory=list)
    phone_oids: list[str] = field(default_factory=list)
    accounts: list[str] = field(default_factory=list)  # BankAccount object ids
    home: str | None = None  # Location object id
    community: int = 0
    role: str = "background"
    surname_native: str = ""


class World:
    def __init__(self, store: Store, reference_dir: Path, *, seed: int = 11, n_people: int = 1800):
        self.s = store
        self.seed = seed
        self.rng = random.Random(seed)
        self.n_people = n_people
        self.today = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0)
        self.people: list[P] = []
        self.by_oid: dict[str, P] = {}
        self.txns: list[tuple] = []
        self.cdrs: list[tuple] = []
        self.travel: list[tuple] = []
        self.tolls: list[tuple] = []
        self.towers: dict[str, tuple] = {}
        self.used: set[str] = set()
        self.truth: dict[str, Any] = {"operations": {}, "canaries": []}
        self.stats: dict[str, int] = {}
        self.district_code = self._district_codes(reference_dir)
        self.acct_holder: dict[str, str] = {}
        self.merchant_accts: list[str] = []
        self.employer_accts: list[tuple[str, str]] = []
        self.ps_cache: dict[str, str] = {}
        self.households: list[list[P]] = []
        self.n_txn = 0

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _district_codes(reference_dir: Path) -> dict[str, str]:
        out: dict[str, str] = {}
        with (reference_dir / "lgd_districts.csv").open(encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        for city, (dname, *_rest) in CITIES.items():
            hit = [r for r in rows if r["name"].lower() == dname.lower()]
            if dname == "Aurangabad":
                hit = [r for r in hit if r["state_lgd_code"] == "27"]
            if dname == "Raigad":
                hit = [r for r in rows if r["lgd_code"] == "491"]
            if hit:
                out[city] = hit[0]["lgd_code"]
        return out

    def uniq(self, fn) -> str:
        while True:
            v = fn()
            if v not in self.used:
                self.used.add(v)
                return v

    def digits(self, n: int) -> str:
        return "".join(self.rng.choice("0123456789") for _ in range(n))

    def letters(self, n: int, alphabet: str = "ABCDEFGHJKLMNPRSTUVWXYZ") -> str:
        return "".join(self.rng.choice(alphabet) for _ in range(n))

    def ts(self, days_ago: float, hour: int | None = None) -> datetime:
        t = self.today - timedelta(days=days_ago)
        if hour is not None:
            t = t.replace(hour=hour, minute=self.rng.randint(0, 59))
        return t

    @staticmethod
    def iso(t: datetime) -> str:
        return t.isoformat(timespec="minutes")

    def city_pick(self) -> str:
        cities = list(CITY_WEIGHTS)
        return self.rng.choices(cities, weights=[CITY_WEIGHTS[c] for c in cities])[0]

    def count(self, k: str, n: int = 1) -> None:
        self.stats[k] = self.stats.get(k, 0) + n

    # ------------------------------------------------------------------ identities
    def make_person(self, *, city: str | None = None, gender: str | None = None, occupation: str | None = None,
                    income: int | None = None, age: tuple[int, int] = (21, 66), surname: tuple[str, str] | None = None,
                    community: int | None = None, role: str = "background", rich: bool = False) -> P:
        rng = self.rng
        if community is None:
            community = rng.choices(range(len(COMMUNITIES)), weights=[c[0] for c in COMMUNITIES])[0]
        _, males, females, surnames = COMMUNITIES[community]
        gender = gender or rng.choice("MF")
        first = rng.choice(males if gender == "M" else females)
        father = rng.choice([m for m in males if m != first] or males)
        sur = surname or rng.choice(surnames)
        if occupation is None:
            occ = rng.choices(OCCUPATIONS, weights=[o[1] for o in OCCUPATIONS])[0]
            occupation, (lo, hi) = occ[0], occ[2]
            income = rng.randint(lo, hi) if hi else 0
        city = city or self.city_pick()
        a_lo, a_hi = age
        dob = (self.today - timedelta(days=365 * rng.randint(a_lo, a_hi) + rng.randint(0, 364))).date()
        latin = f"{first[0]} {father[0]} {sur[0]}"
        native = f"{first[1]} {father[1]} {sur[1]}"
        pan = self.uniq(lambda: self.letters(3, "ABCDEFGHIJKLMNOPQRSTUVWXYZ") + "P" + sur[0][0].upper() + self.digits(4) + self.letters(1, "ABCDEFGHIJKLMNOPQRSTUVWXYZ"))
        aadhaar = self.uniq(lambda: _verhoeff_invalid(rng))
        district = self.district_code.get(city)
        oid = make_id("Person", "UIDAI-SYN", aadhaar)
        p = P(oid, latin, native, first[0], sur[0], f"{father[0]} {sur[0]}", gender, dob, city, district, occupation,
              income or 0, pan, aadhaar, community=community, role=role, surname_native=sur[1])
        # UIDAI eKYC
        self.s.upsert_object("Person", {
            "name": latin, "name_native": native, "father_name": p.father, "gender": gender, "dob": dob.isoformat(),
            "birth_year": dob.year, "aadhaar": aadhaar, "city": city, "district_lgd": district, "nationality": "Indian",
            "_truth_id": oid,  # internal ground truth for the resolution benchmark; never leaves the server
        }, source="UIDAI-SYN", record=f"eKYC:{aadhaar[-4:]}", obj_id=oid, synthetic=True)
        # Income Tax
        self.s.upsert_object("Person", {"name": latin, "pan": pan, "occupation": occupation, "declared_income": income or 0},
                             source="ITD-SYN", record=f"ITR:{pan}", obj_id=oid, synthetic=True)
        # Election Commission
        self.s.upsert_object("Person", {"name": latin, "voter_id": self.uniq(lambda: self.letters(3) + self.digits(7))},
                             source="ECI-SYN", record=f"EPIC:{oid[-6:]}", obj_id=oid, synthetic=True)
        if rich or rng.random() < 0.3:
            self.s.upsert_object("Person", {"name": latin, "passport_no": self.uniq(lambda: self.letters(1) + self.digits(7))},
                                 source="PASSPORT-SYN", record=f"PP:{oid[-6:]}", obj_id=oid, synthetic=True)
        if rng.random() < 0.55 or rich:
            st = CITIES[city][3]
            self.s.upsert_object("Person", {"name": latin, "dl_no": f"{st}{rng.randint(1, 50):02d}{rng.randint(2005, 2022)}{self.digits(7)}"},
                                 source="SARATHI-SYN", record=f"DL:{oid[-6:]}", obj_id=oid, synthetic=True)
        if rng.random() < 0.7 or rich:
            mail = f"{first[0].lower()}.{sur[0].lower()}{rng.randint(1, 999)}@mail.test"
            self.s.upsert_object("Person", {"name": latin, "email": mail}, source="TSP-SYN", record=f"EMAIL:{oid[-6:]}",
                                 obj_id=oid, synthetic=True)
        self.people.append(p)
        self.by_oid[oid] = p
        self.count("persons")
        return p

    def home(self, p: P, label: str | None = None, share_with: P | None = None) -> str:
        if share_with and share_with.home:
            loc = share_with.home
        else:
            flat = label or f"{self.rng.randint(1, 40)}/{self.rng.choice('ABCDEFG')}, {self.rng.choice(['Shanti Nagar', 'Gandhi Path', 'Shivaji Colony', 'Sai Residency', 'Ganesh Apartments', 'Lake View CHS', 'Ambedkar Nagar', 'Krishna Heights'])}"
            loc = self.s.upsert_object("Location", {"label": flat, "address": f"{flat}, {p.city}", "city": p.city,
                                                    "district_lgd": p.district, "country": "IN"},
                                       source="UIDAI-SYN", record=f"ADDR:{flat}:{p.city}", synthetic=True,
                                       lat=CITIES.get(p.city, (None, 0, 0))[1] + self.rng.uniform(-0.05, 0.05),
                                       lon=CITIES.get(p.city, (None, 0, 0))[2] + self.rng.uniform(-0.05, 0.05))
        p.home = loc
        self.s.upsert_object("Person", {"name": p.name, "address": self.s.get_object(loc)["props"]["address"]},
                             source="UIDAI-SYN", record=f"eKYC:{p.aadhaar[-4:]}", obj_id=p.oid, synthetic=True)
        self.s.upsert_link("resides_at", p.oid, loc, source="UIDAI-SYN", record=f"ADDR:{p.oid}")
        return loc

    def phone(self, owner: P | None, *, org: str | None = None, intl: str | None = None, subscriber: str | None = None) -> tuple[str, str]:
        number = intl or self.uniq(lambda: self.rng.choice("6789") + self.digits(9))
        sub = subscriber or (owner.name if owner else "")
        oid = self.s.upsert_object("Phone", {"number": number, "operator": self.rng.choice(["Jio", "Airtel", "Vi", "BSNL"]) if not intl else "Foreign",
                                             "circle": "Maharashtra" if not intl else "International", "subscriber_name": sub},
                                   source="TSP-SYN", record=f"CAF:{number}", obj_id=make_id("Phone", "msisdn", number), synthetic=True)
        if owner:
            self.s.upsert_link("uses_phone", owner.oid, oid, source="TSP-SYN", record=f"CAF:{number}")
            owner.phones.append(number)
            owner.phone_oids.append(oid)
        if org:
            self.s.upsert_link("uses_phone", org, oid, source="TSP-SYN", record=f"CAF:{number}")
        self.count("phones")
        return number, oid

    def account(self, holder_oid: str, holder_name: str, *, kind: str = "savings", bank: int | None = None, opened_days_ago: int | None = None,
                city: str = "Mumbai", foreign: bool = False, kyc: str = "full", signatory: P | None = None) -> str:
        rng = self.rng
        if foreign:
            code, bname, handle = FOREIGN_BANK[0], FOREIGN_BANK[1], None
        else:
            code, bname, handle = BANKS[bank if bank is not None else rng.randrange(len(BANKS))]
        acct = self.uniq(lambda: self.digits(rng.choice([11, 12, 14])))
        opened = (self.today - timedelta(days=opened_days_ago if opened_days_ago is not None else rng.randint(400, 4000))).date()
        props = {"account_no": acct, "ifsc": f"{code}0{self.digits(6)}", "bank": bname, "branch": city, "account_type": kind,
                 "opened_on": opened.isoformat(), "kyc": kyc, "status": "active", "holder_name": holder_name,
                 "country": "AE" if foreign else "IN"}
        if handle and kind == "savings":
            props["vpa"] = f"{holder_name.split()[0].lower()}{self.digits(3)}{handle}"
        oid = self.s.upsert_object("BankAccount", props, source="BANK-KYC-SYN", record=f"ACCT:{acct}",
                                   obj_id=make_id("BankAccount", "acct", acct), synthetic=True)
        self.s.upsert_link("holds_account", holder_oid, oid, source="BANK-KYC-SYN", record=f"ACCT:{acct}")
        if signatory:
            self.s.upsert_link("signatory_of", signatory.oid, oid, source="BANK-KYC-SYN", record=f"MANDATE:{acct}")
        self.acct_holder[oid] = holder_oid
        self.count("accounts")
        return oid

    def org(self, name: str, kind: str, city: str, *, incorporated_days_ago: int = 2500, capital: int = 1_000_000,
            gst_turnover: int | None = None, address: str | None = None, country: str = "IN", source: str = "MCA-SYN") -> str:
        props: dict[str, Any] = {"name": name, "kind": kind, "city": city, "country": country,
                                 "incorporated_on": (self.today - timedelta(days=incorporated_days_ago)).date().isoformat(),
                                 "district_lgd": self.district_code.get(city)}
        if country == "IN" and kind in ("company", "shell_company", "merchant", "trust"):
            props["cin"] = f"U{self.rng.randint(10000, 99999)}MH{(self.today - timedelta(days=incorporated_days_ago)).year}PTC{self.digits(6)}"
            props["pan"] = self.letters(3, "ABCDEFGHIJKLMNOPQRSTUVWXYZ") + ("T" if kind == "trust" else "C") + name[0].upper() + self.digits(4) + self.letters(1, "ABCDEFGHIJKLMNOPQRSTUVWXYZ")
            props["gstin"] = f"27{props['pan']}1Z{self.rng.randint(1, 9)}"
            props["paid_up_capital"] = capital
            props["gst_turnover"] = gst_turnover if gst_turnover is not None else capital * self.rng.randint(5, 40)
        if address:
            props["registered_address"] = address
        oid = self.s.upsert_object("Organisation", props, source=source, record=f"ORG:{name}", synthetic=True)
        if address:
            loc = self.s.upsert_object("Location", {"label": address, "address": address, "city": city, "country": country,
                                                    "district_lgd": self.district_code.get(city)},
                                       source=source, record=f"ADDR:{address}", synthetic=True,
                                       lat=(CITIES.get(city) or (None,) + FOREIGN.get(city, ("", 0, 0))[1:])[1],
                                       lon=(CITIES.get(city) or (None,) + FOREIGN.get(city, ("", 0, 0))[1:])[2])
            self.s.upsert_link("registered_at", oid, loc, source=source, record=f"ROC:{name}")
        self.count("organisations")
        return oid

    def txn(self, t: datetime, frm: str | None, to: str | None, amount: float, channel: str, narration: str,
            source: str = "BANK-SYN", country: str = "IN") -> None:
        self.n_txn += 1
        self.txns.append((f"T{self.n_txn:08d}", self.iso(t), frm, to, round(amount, 2), channel, narration,
                          f"UTR{self.digits(12)}", country, source))

    def call(self, t: datetime, a: str, b: str, *, tower: str | None = None, dur: int | None = None, order: str = "") -> None:
        self.cdrs.append((f"C{len(self.cdrs):08d}", self.iso(t), a, b, dur or self.rng.randint(20, 900), "voice",
                          tower, order, "TSP-CDR-SYN"))

    def tower(self, city: str, label: str, dlat: float = 0.0, dlon: float = 0.0) -> str:
        tid = f"TWR-{AIRPORT.get(city, city[:3].upper())}-{len(self.towers) + 1:04d}"
        _, lat, lon, _ = CITIES[city]
        self.towers[tid] = (tid, label, lat + dlat, lon + dlon, self.district_code.get(city))
        return tid

    def fly(self, p: P, t: datetime, frm: str, to: str, source: str = "PNR-SYN") -> None:
        def loc(c: str) -> tuple[str, float, float]:
            if c in FOREIGN:
                return FOREIGN[c]
            return ("IN", CITIES[c][1], CITIES[c][2])
        fc, flat, flon = loc(frm)
        tc, tlat, tlon = loc(to)
        self.travel.append((f"TR{len(self.travel):07d}", p.oid, self.iso(t), "air", self.letters(6), frm, fc, flat, flon,
                            to, tc, tlat, tlon, source))

    def vehicle(self, owner_oid: str, city: str, make: str, value: int) -> str:
        st = CITIES.get(city, ("", 0, 0, "MH"))[3]
        reg = self.uniq(lambda: f"{st}{self.rng.randint(1, 48):02d}{self.letters(2)}{self.rng.randint(1, 9999):04d}")
        oid = self.s.upsert_object("Vehicle", {"registration_no": reg, "make": make, "colour": self.rng.choice(["White", "Black", "Silver", "Red", "Grey"]),
                                               "value": value}, source="VAHAN-SYN", record=f"RC:{reg}",
                                   obj_id=make_id("Vehicle", "reg", reg), synthetic=True)
        self.s.upsert_link("owns", owner_oid, oid, source="VAHAN-SYN", record=f"RC:{reg}")
        self.count("vehicles")
        return oid

    def property_(self, owner_oid: str, city: str, label: str, value: int, days_ago: int, kind: str = "flat") -> str:
        oid = self.s.upsert_object("Property", {"label": label, "kind": kind, "survey_no": f"CTS-{self.rng.randint(100, 9999)}/{self.rng.randint(1, 40)}",
                                                "value": value, "registered_on": (self.today - timedelta(days=days_ago)).date().isoformat(),
                                                "city": city, "district_lgd": self.district_code.get(city)},
                                   source="IGR-SYN", record=f"DEED:{label}", synthetic=True)
        self.s.upsert_link("owns", owner_oid, oid, source="IGR-SYN", record=f"DEED:{label}")
        self.count("properties")
        return oid

    def police_station(self, city: str, kind: str = "City") -> str:
        key = f"{city}|{kind}"
        if key not in self.ps_cache:
            self.ps_cache[key] = self.s.upsert_object("Organisation", {"name": f"{city} {kind} Police Station", "kind": "police_station",
                                                                      "city": city, "district_lgd": self.district_code.get(city)},
                                                      source="CCTNS-SYN", record=f"PS:{key}", synthetic=True)
        return self.ps_cache[key]

    def incident(self, no: str, kind: str, agency: str, city: str, sections: list[str], summary: str, when: datetime,
                 *, amount: float | None = None, status: str = "under_investigation", source: str = "CCTNS-SYN") -> str:
        props = {"fir_no": no, "kind": kind, "agency": agency, "sections": sections, "summary": summary,
                 "occurred_at": self.iso(when), "district_lgd": self.district_code.get(city), "status": status}
        if amount:
            props["amount"] = amount
        oid = self.s.upsert_object("Incident", props, source=source, record=no, synthetic=True)
        if agency in ("State Police", "I4C"):
            self.s.upsert_link("reported_at", oid, self.police_station(city, "Cyber" if agency == "I4C" else "City"), source=source, record=no)
        self.count("incidents")
        return oid

    def raw_record(self, p: P, source: str, key: str, *, devanagari: bool = False, alias: str | None = None) -> str:
        """A source-system record of the same person, spelled the way that system spelled it.
        Entity resolution (not the generator) links it to the person."""
        rng = self.rng
        if devanagari:
            name = p.native
        elif alias:
            name = alias
        else:
            parts = p.name.split()
            r = rng.random()
            if r < 0.3:
                name = f"{parts[0][0]}. {parts[1][0]}. {parts[2]}"
            elif r < 0.55:
                name = f"{parts[2]} {parts[0]} {parts[1]}"
            else:
                tok = parts[0]
                opts = [(a, b) for a, b in SPELLING_NOISE if a in tok.lower()[1:]]
                if opts:
                    a, b = rng.choice(opts)
                    i = tok.lower().index(a, 1)
                    tok = (tok.lower()[:i] + b + tok.lower()[i + len(a):]).capitalize()
                name = f"{tok} {parts[2]}"
        props = {"name": normalize_name(name).latin.title() if devanagari else name, "father_name": p.father,
                 "age": self.today.year - p.dob.year, "birth_year": p.dob.year, "gender": p.gender, "district_lgd": p.district,
                 "_truth_id": p.oid}
        if devanagari:
            props["name_native"] = name
        if alias:
            props["aliases"] = [alias]
        oid = self.s.upsert_object("Person", props, source=source, record=key, synthetic=True,
                                   confidence=0.8 if devanagari else 1.0)
        self.count("raw_records")
        return oid

    # ------------------------------------------------------------------ background population
    def background(self) -> None:
        rng = self.rng
        govt = self.org("PM-KISAN DBT Account (synthetic)", "department", "New Delhi", source="PFMS-SYN")
        govt_acct = self.account(govt, "PM-KISAN DBT", kind="current", bank=3, city="New Delhi")
        for name in MERCHANTS:
            city = self.city_pick()
            m = self.org(name, "merchant", city, capital=500_000)
            self.merchant_accts.append(self.account(m, name, kind="current", city=city))
        for name in EMPLOYERS:
            city = self.city_pick()
            e = self.org(name, "company", city, capital=rng.randint(10, 200) * 100_000)
            self.employer_accts.append((e, self.account(e, name, kind="current", city=city)))
        scheme = self.s.upsert_object("Scheme", {"name": "Public Distribution System (synthetic)", "department": "Food & Civil Supplies"},
                                      source="PDS-SYN", record="scheme:pds", synthetic=True)
        made = sum(1 for p in self.people if p.role == "background")
        while made < self.n_people:
            head = self.make_person()
            made += 1
            self.home(head)
            household = [head]
            for _ in range(rng.choice([0, 0, 1, 1, 2, 3])):
                rel = self.make_person(city=head.city, surname=(head.surname, head.surname_native), community=head.community)
                self.home(rel, share_with=head)
                self.s.upsert_link("relative_of", head.oid, rel.oid, source="PDS-SYN", record=f"RC:{head.oid}")
                household.append(rel)
                made += 1
            for p in household:
                self._life(p, govt_acct, scheme)
            self.households.append(household)

    def social(self) -> None:
        """Ordinary calling patterns: family daily, friends and colleagues weekly."""
        rng = self.rng
        by_city: dict[str, list[P]] = {}
        for p in self.people:
            if p.phones and p.role == "background":
                by_city.setdefault(p.city, []).append(p)
        for hh in self.households:
            for a in hh:
                for b in hh:
                    if a is not b and a.phones and b.phones:
                        for _ in range(rng.randint(3, 10)):
                            self.call(self.ts(rng.uniform(1, 360), rng.randint(8, 22)), a.phones[0], b.phones[0], dur=rng.randint(30, 400))
        for p in [q for q in self.people if q.role == "background" and q.phones]:
            friends = rng.sample(by_city.get(p.city, []), min(3, len(by_city.get(p.city, []))))
            for f in friends:
                if f is not p:
                    for _ in range(rng.randint(1, 7)):
                        self.call(self.ts(rng.uniform(1, 360), rng.randint(8, 22)), p.phones[0], f.phones[0], dur=rng.randint(20, 600))

    def _life(self, p: P, govt_acct: str, scheme: str) -> None:
        """Phones, accounts, assets and a year of ordinary transactions."""
        rng = self.rng
        self.phone(p)
        if rng.random() < 0.15:
            self.phone(p)
        n_acc = 1 + (rng.random() < 0.45) + (p.occupation in ("Shop owner", "Contractor", "Doctor"))
        if p.occupation in ("Student", "Homemaker") and rng.random() < 0.5:
            n_acc = 1
        for i in range(n_acc):
            kind = "current" if i == 2 or (p.occupation in ("Shop owner", "Contractor") and i == 1) else "savings"
            p.accounts.append(self.account(p.oid, p.name, kind=kind, city=p.city))
        if p.income > 600_000 and rng.random() < 0.5:
            self.vehicle(p.oid, p.city, rng.choice(["Maruti Swift", "Hyundai Creta", "Tata Nexon", "Honda City", "Mahindra XUV700"]), rng.randint(6, 25) * 100_000)
        elif rng.random() < 0.35:
            self.vehicle(p.oid, p.city, rng.choice(["Hero Splendor", "Honda Activa", "Bajaj Pulsar", "TVS Jupiter"]), rng.randint(60, 140) * 1000)
        if p.income > 1_200_000 and rng.random() < 0.4:
            self.property_(p.oid, p.city, f"Flat {rng.randint(101, 1804)}, {rng.choice(['Sunshine', 'Green Acres', 'Skyline', 'Palm Grove'])} Towers, {p.city}",
                           rng.randint(60, 250) * 100_000, rng.randint(200, 3000))
        if p.income < 250_000 and p.occupation in ("Farmer", "Labourer", "Driver") and rng.random() < 0.7:
            self.raw_record(p, "PDS-SYN", f"PDS#{p.oid}", devanagari=rng.random() < 0.5)
        if p.income > 1_500_000 and rng.random() < 0.35:
            for _ in range(rng.randint(1, 3)):
                t = self.ts(rng.randint(5, 360), rng.randint(5, 22))
                dest = rng.choice(["New Delhi", "Bengaluru", "Hyderabad", "Dubai", "Singapore", "Kolkata", "Panaji"])
                if dest != p.city and AIRPORT.get(p.city):
                    self.fly(p, t, p.city, dest)
                    self.fly(p, t + timedelta(days=rng.randint(2, 8)), dest, p.city)
        # a year of transactions
        main = p.accounts[0]
        monthly = p.income / 12 if p.income else 0
        employer = rng.choice(self.employer_accts)[1] if p.occupation in ("Software engineer", "Teacher", "Sales executive", "Doctor") else None
        for m in range(12):
            base = 30 * m + rng.randint(0, 5)
            if employer and monthly:
                self.txn(self.ts(base + 1, 10), employer, main, round(monthly * 0.82, -2), "NEFT", "SALARY")
            elif p.occupation in ("Shop owner", "Contractor") and monthly:
                for _ in range(rng.randint(2, 5)):
                    self.txn(self.ts(base + rng.random() * 28, rng.randint(10, 17)), None, p.accounts[-1],
                             round(rng.uniform(15_000, 90_000), -2), "CASH", "CASH DEPOSIT")
            elif p.occupation == "Farmer" and m % 4 == 0:
                self.txn(self.ts(base + 3, 11), govt_acct, main, 2000, "DBT", "PM-KISAN INSTALMENT")
            elif p.occupation == "Retired":
                self.txn(self.ts(base + 1, 9), govt_acct, main, round(max(monthly, 15000), -2), "NEFT", "PENSION")
            spend = max(monthly * rng.uniform(0.3, 0.6), 3000) if monthly else rng.uniform(1500, 6000)
            for _ in range(rng.randint(1, 3)):
                self.txn(self.ts(base + rng.random() * 28, rng.randint(8, 22)), main, rng.choice(self.merchant_accts),
                         round(spend / 3, 0), "UPI", rng.choice(["UPI/grocery", "UPI/fuel", "UPI/pharmacy", "UPI/recharge", "UPI/shopping"]))
            if monthly and rng.random() < 0.6:
                self.txn(self.ts(base + rng.random() * 28, rng.randint(9, 21)), main, None, round(rng.uniform(2000, 12000), -2), "ATM", "ATM WITHDRAWAL")

    # ------------------------------------------------------------------ operations
    def op_mule_and_mirage(self) -> None:
        rng = self.rng
        t = self.truth["operations"]
        # --- MIRAGE principals
        kingpin = self.make_person(city="Mumbai", gender="M", occupation="Real estate consultant", income=1_850_000, age=(41, 52), role="mirage_kingpin", rich=True)
        self.home(kingpin, label="Flat 2201, Sea Breeze Towers, Worli")
        wife = self.make_person(city="Mumbai", gender="F", occupation="Homemaker", income=0, age=(36, 45), surname=(kingpin.surname, kingpin.surname_native), community=kingpin.community, role="mirage_family")
        self.home(wife, share_with=kingpin)
        brother = self.make_person(city="Thane", gender="M", occupation="Shop owner", income=420_000, age=(35, 45), surname=(kingpin.surname, kingpin.surname_native), community=kingpin.community, role="mirage_family")
        self.home(brother)
        for rel in (wife, brother):
            self.s.upsert_link("relative_of", kingpin.oid, rel.oid, source="UIDAI-SYN", record=f"FAMILY:{kingpin.oid}")
        ca = self.make_person(city="Andheri", gender="M", occupation="Chartered accountant", income=1_400_000, age=(38, 48), role="mirage_facilitator", rich=True)
        self.home(ca)
        hawala = self.make_person(city="Surat", gender="M", occupation="Trader (textiles)", income=900_000, age=(45, 58), role="hawala_operator", rich=True)
        self.home(hawala)
        nominees = [self.make_person(city=rng.choice(["Bhiwandi", "Thane", "Navi Mumbai"]), occupation=rng.choice(["Driver", "Labourer"]),
                                     income=rng.randint(120_000, 220_000), role="mirage_nominee") for _ in range(5)]
        for p in [kingpin, wife, brother, ca, hawala] + nominees:
            if not p.home:
                self.home(p)
            self.phone(p)
            p.accounts.append(self.account(p.oid, p.name, city=p.city))
        for n in nominees:
            self.raw_record(n, "PDS-SYN", f"PDS#{n.oid}", devanagari=True)
        # hawala front + Dubai side
        hw_firm = self.org("Shree Laxmi Textiles (Surat)", "hawala_operator", "Surat", capital=500_000, gst_turnover=3_000_000,
                           address="Shop 17, Ring Road Textile Market, Surat")
        self.s.upsert_link("controls", hawala.oid, hw_firm, source="MCA-SYN", record="PROP:hawala")
        hw_acct = self.account(hw_firm, "Shree Laxmi Textiles", kind="current", city="Surat", signatory=hawala)
        dubai_co = self.org("Gulf Horizon General Trading FZE", "foreign_company", "Dubai", country="AE", source="FIU-EGMONT-SYN",
                            address="Office 908, Deira Business Tower, Dubai")
        dubai_acct = self.account(dubai_co, "Gulf Horizon General Trading FZE", kind="current", city="Dubai", foreign=True)
        self.s.upsert_link("controls", kingpin.oid, dubai_co, source="FIU-EGMONT-SYN", record="EGMONT-REQ-114")
        hd_number, hd_phone = self.phone(None, intl="+971501234567", subscriber="unknown (UAE)")
        # shells
        addr_a = "Office 14, Laxmi Industrial Estate, Andheri East, Mumbai"
        addr_b = "Gala 3, Bhiwandi Logistics Park, Bhiwandi"
        shell_names = ["Zenova Trading Pvt Ltd", "Bluepeak Consultancy Pvt Ltd", "Arcadia Impex Pvt Ltd", "Novastar Commodities Pvt Ltd",
                       "Kairos Infra Solutions Pvt Ltd", "Meridian Agro Exports Pvt Ltd", "Silverline Ventures Pvt Ltd"]
        shells, shell_accts = [], []
        for i, nm in enumerate(shell_names):
            sh = self.org(nm, "shell_company", "Andheri" if i < 4 else "Bhiwandi", incorporated_days_ago=rng.randint(200, 520),
                          capital=100_000, gst_turnover=rng.choice([0, 0, 180_000, 420_000]), address=addr_a if i < 4 else addr_b)
            shells.append(sh)
            directors = [nominees[i % 5], nominees[(i + 2) % 5]] + ([ca] if i in (0, 3, 6) else [])
            for d in directors:
                self.s.upsert_link("director_of", d.oid, sh, source="MCA-SYN", record=f"DIN:{d.oid}:{nm}")
            shell_accts.append(self.account(sh, nm, kind="current", city="Mumbai", opened_days_ago=rng.randint(150, 480), signatory=ca))
        # --- MULE network (I4C) feeding the shells
        herder = self.make_person(city="Navi Mumbai", gender="M", occupation="Mobile shop owner", income=380_000, age=(26, 34), role="mule_herder")
        self.home(herder)
        herder_handset = self.s.upsert_object("Device", {"imei": "35" + self.digits(13), "model": "Android handset"},
                                              source="TSP-SYN", record="IMEI:herder", synthetic=True)
        hn, hp = self.phone(herder)
        self.s.upsert_link("sim_in_device", hp, herder_handset, source="TSP-CDR-SYN", record="IMEI:herder")
        aggregators = []
        fronts = [self.make_person(city="Navi Mumbai", occupation="Labourer", income=150_000, role="mule_front") for _ in range(2)]
        for f in [herder] + fronts:
            if not f.home:
                self.home(f)
            if not f.phones:
                self.phone(f)
            aggregators.append(self.account(f.oid, f.name, city="Navi Mumbai", opened_days_ago=rng.randint(120, 300), kyc="min"))
            f.accounts.append(aggregators[-1])
        mules = [self.make_person(city=rng.choice(["Navi Mumbai", "Thane", "Pune", "Panvel", "Kolhapur"]), occupation=rng.choice(["Student", "Labourer", "Driver"]),
                                  income=rng.choice([0, 120_000, 180_000]), age=(19, 27), role="money_mule") for _ in range(9)]
        mule_accts, fraud_phones = [], []
        for m in mules:
            self.home(m)
            n_, po = self.phone(m)
            self.s.upsert_link("sim_in_device", po, herder_handset, source="TSP-CDR-SYN", record=f"IMEI:{m.oid}")
            fraud_phones.append((n_, po))
            for _ in range(2):
                a = self.account(m.oid, m.name, city=m.city, opened_days_ago=rng.randint(60, 240), kyc="min", bank=rng.randrange(3))
                m.accounts.append(a)
                mule_accts.append(a)
            for d in range(rng.randint(8, 20)):  # herder coordinates mules
                self.call(self.ts(rng.randint(1, 200), rng.randint(9, 23)), hn, m.phones[0])
        exchange = self.org("CoinBridge Exchange (synthetic)", "crypto_exchange", "Bengaluru", capital=50_000_000)
        exch_acct = self.account(exchange, "CoinBridge Exchange", kind="current", city="Bengaluru")
        wallet = self.s.upsert_object("CryptoWallet", {"address": "0x" + "".join(rng.choice("0123456789abcdef") for _ in range(40)),
                                                       "chain": "Tron (USDT)", "exchange": "CoinBridge"},
                                      source="EXCHANGE-SYN", record="wallet:herder", synthetic=True)
        self.s.upsert_link("holds_account", herder.oid, wallet, source="EXCHANGE-SYN", record="KYC:coinbridge")
        victims = [p for p in self.people if p.role == "background" and p.income > 300_000 and p.accounts]
        victims = rng.sample(victims, 60)
        complaints = []
        for n, v in enumerate(victims):
            when = self.ts(rng.randint(20, 210), rng.randint(10, 20))
            amount = rng.choice([24_999, 49_500, 75_000, 1_20_000, 1_85_000, 2_40_000, 3_90_000])
            m_acct = mule_accts[n % len(mule_accts)]
            fn, fp = fraud_phones[n % len(fraud_phones)]
            inc = self.incident(f"I4C/{when.year}/{40100 + n}", "complaint", "I4C", v.city, ["BNS 318(4)", "BNS 319(2)", "IT Act 66D"],
                                f"Caller posing as a bank KYC officer obtained an OTP; Rs {amount:,} moved by UPI/IMPS to an unknown account.",
                                when, amount=amount, source="I4C-SYN")
            complaints.append(inc)
            self.s.upsert_link("complainant_in", v.oid, inc, source="I4C-SYN", record=f"NCRP:{n}")
            self.s.upsert_link("mentions", inc, m_acct, source="I4C-SYN", record=f"NCRP:{n}")
            self.s.upsert_link("mentions", inc, fp, source="I4C-SYN", record=f"NCRP:{n}")
            self.txn(when, v.accounts[0], m_acct, amount, "IMPS", "KYC UPDATE REFUND")
            self.call(when - timedelta(minutes=12), fn, v.phones[0], dur=rng.randint(240, 900))
            # mule forwards 92% within hours to an aggregator
            self.txn(when + timedelta(hours=rng.uniform(0.5, 6)), m_acct, rng.choice(aggregators), round(amount * 0.92, -1), "IMPS", "TRF")
            self.txn(when + timedelta(hours=rng.uniform(6, 9)), m_acct, None, round(amount * 0.05, -1), "ATM", "ATM WITHDRAWAL")
        # aggregators -> shells (layer 1) and crypto off-ramp
        for k in range(26):
            when = self.ts(rng.randint(15, 205), rng.randint(10, 18))
            amt = rng.randint(6, 18) * 100_000
            src = aggregators[k % 3]
            if k % 4 == 0:
                self.txn(when, src, exch_acct, amt * 0.6, "IMPS", "COINBRIDGE TOPUP")
            else:
                self.txn(when, src, shell_accts[k % 2], amt, "NEFT", "CONSULTANCY FEES")
        # structuring: runners deposit cash just under Rs 50,000 into shell accounts
        for k in range(70):
            self.txn(self.ts(rng.randint(10, 200), rng.randint(10, 16)), None, shell_accts[k % 2],
                     rng.choice([49_000, 49_500, 48_900, 49_900, 47_500]), "CASH", "CASH DEPOSIT")
        # layering: S1,S2 -> S3,S4,S5 circular -> S6 consolidation
        for k in range(30):
            when = self.ts(rng.randint(10, 190), rng.randint(10, 18))
            self.txn(when, shell_accts[k % 2], shell_accts[2 + k % 3], rng.randint(8, 30) * 100_000, "RTGS", "INVOICE PAYMENT")
        for k in range(18):  # round-trip cycle S3 -> S4 -> S5 -> S3
            when = self.ts(rng.randint(10, 180), 11)
            amt = rng.randint(20, 60) * 100_000
            self.txn(when, shell_accts[2], shell_accts[3], amt, "RTGS", "PURCHASE OF GOODS")
            self.txn(when + timedelta(hours=20), shell_accts[3], shell_accts[4], amt * 0.98, "RTGS", "PURCHASE OF GOODS")
            self.txn(when + timedelta(hours=44), shell_accts[4], shell_accts[2], amt * 0.96, "RTGS", "ADVANCE REFUND")
        for k in range(16):
            when = self.ts(rng.randint(8, 170), 12)
            self.txn(when, shell_accts[2 + k % 3], shell_accts[5], rng.randint(25, 70) * 100_000, "RTGS", "SERVICE CHARGES")
        # trade-based laundering: S6 pays Dubai "import advances"; Dubai round-trips to S7 as share money
        for k in range(8):
            when = self.ts(rng.randint(10, 160), 13)
            amt = rng.randint(60, 140) * 100_000
            self.txn(when, shell_accts[5], dubai_acct, amt, "SWIFT", "IMPORT ADVANCE - TEXTILE MACHINERY", country="AE")
            self.txn(when + timedelta(days=rng.randint(9, 20)), dubai_acct, shell_accts[6], amt * 0.9, "SWIFT", "SHARE APPLICATION MONEY (FDI)", country="AE")
        # S6 cash-out through the hawala operator
        for k in range(12):
            when = self.ts(rng.randint(10, 150), 15)
            self.txn(when, shell_accts[5], hw_acct, rng.randint(15, 40) * 100_000, "NEFT", "PURCHASE OF FABRIC")
            self.txn(when + timedelta(hours=3), hw_acct, None, rng.randint(14, 38) * 100_000, "CASH", "SELF WITHDRAWAL")
        # integration: S7 -> family "loans" -> property, cars
        builder = self.org("Skyline Realty Developers LLP", "company", "Mumbai", capital=50_000_000)
        builder_acct = self.account(builder, "Skyline Realty Developers", kind="current", city="Mumbai")
        car_dealer = self.org("Prestige Motors (Luxury Cars)", "merchant", "Mumbai", capital=5_000_000)
        car_acct = self.account(car_dealer, "Prestige Motors", kind="current", city="Mumbai")
        for k in range(10):
            when = self.ts(rng.randint(5, 120), 12)
            tgt = [wife, brother, kingpin][k % 3]
            self.txn(when, shell_accts[6], tgt.accounts[0], rng.randint(30, 90) * 100_000, "RTGS", "UNSECURED LOAN")
        self.txn(self.ts(60, 14), wife.accounts[0], builder_acct, 2_40_00_000, "RTGS", "FLAT 2201 SEA BREEZE - CONSIDERATION")
        self.property_(wife.oid, "Mumbai", "Flat 2201, Sea Breeze Towers, Worli", 2_40_00_000, 58)
        self.property_(brother.oid, "Thane", "Bungalow 7, Upvan Lake Road, Thane", 1_10_00_000, 40, kind="bungalow")
        for who, mk, val in ((kingpin, "BMW X7", 1_25_00_000), (brother, "Mercedes-Benz GLS", 1_05_00_000)):
            self.txn(self.ts(rng.randint(20, 90), 13), who.accounts[0], car_acct, val, "RTGS", f"{mk.upper()} PURCHASE")
            self.vehicle(who.oid, who.city, mk, val)
        # communications and travel of the principals
        for d in range(60):
            t0 = self.ts(rng.randint(1, 200), rng.randint(8, 23))
            pair = rng.choice([(kingpin, ca), (kingpin, hawala), (ca, nominees[0]), (ca, nominees[1]), (kingpin, herder)])
            self.call(t0, pair[0].phones[0], pair[1].phones[0])
        for d in range(14):
            self.call(self.ts(rng.randint(1, 200), rng.randint(20, 23)), kingpin.phones[0], hd_number)
        for k in range(6):
            t0 = self.ts(30 + k * 28, 6)
            self.fly(kingpin, t0, "Mumbai", "Dubai")
            self.fly(kingpin, t0 + timedelta(days=rng.randint(2, 5)), "Dubai", "Mumbai")
        for k in range(3):
            t0 = self.ts(45 + k * 40, 7)
            self.fly(ca, t0, "Mumbai", "Dubai")
            self.fly(ca, t0 + timedelta(days=3), "Dubai", "Mumbai")
        # cases
        ecir = self.incident(f"ECIR/MBZO-II/{self.today.year}/31", "ecir", "ED", "Mumbai",
                             ["PMLA 2002 s.3", "PMLA 2002 s.4", "Scheduled offence: BNS 318(4), 319(2)"],
                             "Proceeds of crime from the cyber-fraud mule network routed through Zenova Trading and Bluepeak Consultancy; beneficial owners unknown.",
                             self.ts(25, 11), amount=48_00_00_000 / 10, source="ED-SYN")
        for sh in shells[:2]:
            self.s.upsert_link("accused_in", sh, ecir, source="ED-SYN", record="ECIR-31")
        for a in aggregators:
            self.s.upsert_link("mentions", ecir, a, source="ED-SYN", record="ECIR-31")
        str_ = self.incident(f"STR/FIU-IND/{self.today.year}/88412", "str", "FIU-IND", "Mumbai", ["PMLA Rule 3 (STR)"],
                             "Bank STR: structured cash deposits of Rs 47,500-49,900 into Zenova Trading and Bluepeak Consultancy current accounts.",
                             self.ts(70, 11), source="FIU-SYN")
        for a in shell_accts[:2]:
            self.s.upsert_link("mentions", str_, a, source="FIU-SYN", record="STR-88412")
        fir = self.incident(f"MH/NMB/CYB/{self.today.year}/0412", "fir", "State Police", "Navi Mumbai", ["BNS 318(4)", "BNS 111(2)(b)", "IT Act 66C, 66D"],
                            "Mule-account racket: SIM cards and bank kits procured from students and labourers on commission.", self.ts(35, 12))
        for m in mules[:4]:
            r = self.raw_record(m, "CCTNS-SYN", f"FIR412#{m.oid}")
            self.s.upsert_link("accused_in", r, fir, source="CCTNS-SYN", record="FIR-412")
        r = self.raw_record(herder, "CCTNS-SYN", f"FIR412#{herder.oid}", alias=f"Bunty {herder.surname}")
        self.s.upsert_link("accused_in", r, fir, source="CCTNS-SYN", record="FIR-412")
        t["MIRAGE"] = {"kingpin": kingpin.oid, "facilitator": ca.oid, "hawala": hawala.oid, "nominees": [n.oid for n in nominees],
                       "family": [wife.oid, brother.oid], "shells": shells, "shell_accounts": shell_accts, "dubai": dubai_co,
                       "ecir": ecir, "str": str_}
        t["MULE"] = {"herder": herder.oid, "fronts": [f.oid for f in fronts], "mules": [m.oid for m in mules],
                     "mule_accounts": mule_accts, "aggregators": aggregators, "complaints": complaints, "victims": [v.oid for v in victims],
                     "fir": fir, "handset": herder_handset}
        self.hawala = hawala
        self.hw_acct = hw_acct
        self.dubai_acct = dubai_acct
        self.hd_number = hd_number

    def op_sunrise(self) -> None:
        rng = self.rng
        promoter = self.make_person(city="Pune", gender="M", occupation="Company director", income=4_200_000, age=(48, 60), role="sunrise_promoter", rich=True)
        spouse = self.make_person(city="Pune", gender="F", occupation="Company director", income=1_200_000, age=(42, 55), surname=(promoter.surname, promoter.surname_native), community=promoter.community, role="sunrise_family")
        self.home(promoter, label="Bungalow 4, Koregaon Park Lane 6")
        self.home(spouse, share_with=promoter)
        self.s.upsert_link("relative_of", promoter.oid, spouse.oid, source="UIDAI-SYN", record="FAMILY:sunrise")
        relatives = [self.make_person(city="Pune", occupation=rng.choice(["Shop owner", "Sales executive", "Homemaker"]), income=rng.randint(200_000, 600_000),
                                      community=promoter.community, role="sunrise_relative") for _ in range(4)]
        manager = self.make_person(city="Pune", gender="M", occupation="Bank branch manager", income=1_500_000, age=(45, 55), role="sunrise_bank_manager")
        bil = self.make_person(city="Solapur", gender="M", occupation="Farmer", income=180_000, age=(38, 50), role="sunrise_conduit")
        for p in [promoter, spouse, manager, bil] + relatives:
            if not p.home:
                self.home(p)
            self.phone(p)
            p.accounts.append(self.account(p.oid, p.name, city=p.city))
        self.s.upsert_link("relative_of", manager.oid, bil.oid, source="UIDAI-SYN", record="FAMILY:manager")
        for r in relatives:
            self.s.upsert_link("relative_of", promoter.oid, r.oid, source="UIDAI-SYN", record=f"FAMILY:{r.oid}")
        bank = self.org("Indus Public Sector Bank, Pune Main Branch (synthetic)", "bank", "Pune")
        self.s.upsert_link("employee_of", manager.oid, bank, source="BANK-HR-SYN", record="EMP:manager")
        sunrise = self.org("Sunrise Infraprojects Pvt Ltd", "company", "Pune", incorporated_days_ago=3200, capital=25_00_00_000,
                           gst_turnover=40_00_00_000, address="Sunrise House, Baner Road, Pune")
        for d in (promoter, spouse):
            self.s.upsert_link("director_of", d.oid, sunrise, source="MCA-SYN", record=f"DIN:{d.oid}")
        loan = self.account(sunrise, "Sunrise Infraprojects (Term Loan)", kind="loan", bank=3, city="Pune", opened_days_ago=330)
        sun_acct = self.account(sunrise, "Sunrise Infraprojects", kind="current", bank=3, city="Pune", opened_days_ago=2900, signatory=promoter)
        related, rel_accts = [], []
        for i, nm in enumerate(["Sunrise Buildcon LLP", "Aryavart Contractors Pvt Ltd", "Shubh Labh Earthmovers", "Pranav Steel Traders"]):
            o = self.org(nm, "company", "Pune", incorporated_days_ago=rng.randint(400, 900), capital=500_000, gst_turnover=rng.randint(2, 9) * 1_000_000,
                         address="Office 5, Shivneri Complex, Wakad, Pune" if i < 2 else None)
            related.append(o)
            self.s.upsert_link("director_of", relatives[i].oid, o, source="MCA-SYN", record=f"DIN:{relatives[i].oid}")
            self.s.upsert_link("controls", promoter.oid, o, source="MCA-SYN", record=f"SBO:{nm}")
            rel_accts.append(self.account(o, nm, kind="current", bank=rng.randrange(3), city="Pune", signatory=relatives[i]))
        sg = self.org("Sunrise Global Holdings Pte Ltd", "foreign_company", "Singapore", country="SG", source="FIU-EGMONT-SYN")
        sg_acct = self.account(sg, "Sunrise Global Holdings", kind="current", city="Singapore", foreign=True)
        self.s.upsert_link("controls", promoter.oid, sg, source="FIU-EGMONT-SYN", record="EGMONT-SG")
        for k, amt in enumerate([80_00_00_000, 60_00_00_000, 40_00_00_000]):
            when = self.ts(320 - k * 30, 11)
            self.txn(when, loan, sun_acct, amt, "INTERNAL", f"TERM LOAN DISBURSEMENT TRANCHE {k + 1}")
            for i in range(4):
                self.txn(when + timedelta(days=rng.randint(2, 20)), sun_acct, rel_accts[i], round(amt * rng.uniform(0.12, 0.18), -5), "RTGS", "MOBILISATION ADVANCE")
        for i in range(4):
            for k in range(3):
                when = self.ts(rng.randint(200, 280), 12)
                self.txn(when, rel_accts[i], promoter.accounts[0] if k == 0 else spouse.accounts[0], rng.randint(150, 400) * 100_000, "RTGS", "REFUND OF ADVANCE")
        self.txn(self.ts(240, 12), promoter.accounts[0], sg_acct, 22_00_00_000, "SWIFT", "ODI - INVESTMENT IN SUBSIDIARY", country="SG")
        self.txn(self.ts(250, 15), rel_accts[2], bil.accounts[0], 45_00_000, "RTGS", "MACHINERY HIRE CHARGES")
        self.txn(self.ts(246, 11), bil.accounts[0], manager.accounts[0], 30_00_000, "NEFT", "LOAN REPAYMENT")
        car = self.org("Pune Auto Mall", "merchant", "Pune")
        car_acct = self.account(car, "Pune Auto Mall", kind="current", city="Pune")
        self.txn(self.ts(230, 13), manager.accounts[0], car_acct, 28_00_000, "RTGS", "TOYOTA FORTUNER PURCHASE")
        self.vehicle(manager.oid, "Pune", "Toyota Fortuner", 28_00_000)
        self.property_(spouse.oid, "Pune", "Villa 12, Lavasa Hillside", 9_50_00_000, 200, kind="bungalow")
        for d in range(25):
            self.call(self.ts(rng.randint(200, 330), rng.randint(9, 21)), promoter.phones[0], manager.phones[0])
        for k in range(2):
            t0 = self.ts(250 - k * 60, 9)
            self.fly(promoter, t0, "Pune", "Singapore")
            self.fly(promoter, t0 + timedelta(days=4), "Singapore", "Pune")
        self.s.upsert_object("BankAccount", {"account_no": self.s.get_object(loan)["props"]["account_no"], "status": "npa"},
                             source="BANK-SYN", record="NPA-classification", obj_id=loan, synthetic=True)
        rc = self.incident(f"RC/BSFC/{self.today.year}/E/0007", "cbi_rc", "CBI", "Pune", ["BNS 61(2)", "BNS 318(4)", "BNS 316(5)", "PC Act 1988 s.7, 13(2)"],
                           "Diversion of Rs 180 crore term loan by Sunrise Infraprojects through related parties; unknown bank officials.",
                           self.ts(30, 11), amount=180_00_00_000, source="CBI-SYN")
        self.s.upsert_link("accused_in", sunrise, rc, source="CBI-SYN", record="RC-7")
        self.s.upsert_link("accused_in", self.raw_record(promoter, "CBI-SYN", "RC7#A1"), rc, source="CBI-SYN", record="RC-7")
        self.s.upsert_link("mentions", rc, loan, source="CBI-SYN", record="RC-7")
        self.truth["operations"]["SUNRISE"] = {"promoter": promoter.oid, "spouse": spouse.oid, "relatives": [r.oid for r in relatives],
                                               "manager": manager.oid, "conduit": bil.oid, "company": sunrise, "related": related,
                                               "loan": loan, "rc": rc, "singapore": sg}

    def op_kestrel(self) -> None:
        rng = self.rng
        trust = self.org("Sahyog Seva Foundation (synthetic)", "trust", "Aurangabad", incorporated_days_ago=600, capital=100_000,
                         gst_turnover=0, address="Plot 22, MIDC Chikalthana, Aurangabad")
        ops = [self.make_person(city=c, gender="M", occupation=o, income=i, age=(24, 36), role="kestrel_operative")
               for c, o, i in (("Aurangabad", "Coaching centre owner", 360_000), ("Pune", "Electrician", 240_000), ("Nashik", "Delivery agent", 210_000))]
        for p in ops:
            self.home(p)
            self.phone(p)
            p.accounts.append(self.account(p.oid, p.name, city=p.city))
        leader = ops[0]
        trust_acct = self.account(trust, "Sahyog Seva Foundation", kind="current", city="Aurangabad", opened_days_ago=560, signatory=leader)
        self.s.upsert_link("director_of", leader.oid, trust, source="CHARITY-COMM-SYN", record="TRUSTEE-1")
        donors = rng.sample([p for p in self.people if p.role == "background" and p.accounts], 95)
        for k in range(150):
            d = donors[k % len(donors)]
            self.txn(self.ts(rng.randint(30, 300), rng.randint(8, 22)), d.accounts[0], trust_acct, rng.choice([500, 1000, 1100, 2000, 2100, 5000]), "UPI", "DONATION")
        for k in range(14):  # cash-out just under Rs 2 lakh (s.269ST limit) by the leader
            self.txn(self.ts(rng.randint(30, 280), 12), trust_acct, None, rng.choice([1_90_000, 1_95_000, 1_98_000]), "CASH", "SELF WITHDRAWAL")
        for k in range(6):  # to the hawala operator shared with MIRAGE
            self.txn(self.ts(rng.randint(30, 260), 14), trust_acct, self.hw_acct, rng.randint(3, 7) * 100_000, "NEFT", "PURCHASE OF CLOTH")
        handler_no, _ = self.phone(None, intl="+9779812345678", subscriber="unknown (Nepal)")
        for d in range(30):
            self.call(self.ts(rng.randint(5, 240), rng.randint(20, 23)), leader.phones[0], handler_no)
        for d in range(90):
            a, b = rng.sample(ops, 2)
            self.call(self.ts(rng.randint(5, 240), rng.randint(9, 23)), a.phones[0], b.phones[0])
        recce = self.tower("Mumbai", "Near Gateway / Colaba causeway", 0.0, 0.0)
        for day in (95, 64, 37):
            for p in ops:
                other = rng.choice([q for q in self.people[:300] if q.phones])
                self.call(self.ts(day, 16), p.phones[0], other.phones[0], tower=recce, dur=rng.randint(30, 120))
        handset = self.s.upsert_object("Device", {"imei": "86" + self.digits(13), "model": "Feature phone"}, source="TSP-SYN", record="IMEI:kestrel", synthetic=True)
        for p in ops[1:]:
            self.s.upsert_link("sim_in_device", p.phone_oids[0], handset, source="TSP-CDR-SYN", record=f"IMEI:{p.oid}")
        for k in range(2):
            t0 = self.ts(150 - k * 50, 8)
            self.fly(ops[1], t0, "Pune", "Kathmandu")
            self.fly(ops[1], t0 + timedelta(days=6), "Kathmandu", "Pune")
        case = self.incident(f"RC-04/{self.today.year}/NIA/MUM", "nia_case", "NIA", "Aurangabad",
                             ["UAPA 1967 s.17 (raising funds for terrorist act)", "UAPA s.18", "BNS 61(2)"],
                             "Arrest of the trustee of a front foundation for raising and moving funds for a terrorist act; associates and handler unidentified.",
                             self.ts(20, 9), source="NIA-SYN")
        self.s.upsert_link("accused_in", self.raw_record(leader, "NIA-SYN", "RC04#A1"), case, source="NIA-SYN", record="RC-04")
        self.s.upsert_link("mentions", case, leader.phone_oids[0], source="NIA-SYN", record="RC-04")
        self.s.upsert_link("mentions", case, trust, source="NIA-SYN", record="RC-04")
        self.truth["operations"]["KESTREL"] = {"leader": leader.oid, "operatives": [p.oid for p in ops], "trust": trust, "trust_account": trust_acct,
                                               "case": case, "donors": [d.oid for d in donors], "handler_phone": handler_no, "recce_tower": recce}

    def op_coastline(self) -> None:
        rng = self.rng
        coord = self.make_person(city="Panvel", gender="M", occupation="Transport contractor", income=650_000, age=(35, 48), role="coastline_coordinator", rich=True)
        couriers = [self.make_person(city=rng.choice(["Panvel", "Panaji", "Navi Mumbai"]), gender="M", occupation="Driver", income=200_000, age=(22, 35),
                                     role="coastline_courier") for _ in range(3)]
        for p in [coord] + couriers:
            self.home(p)
            self.phone(p)
            p.accounts.append(self.account(p.oid, p.name, city=p.city))
        truck = self.vehicle(coord.oid, "Panvel", "Tata Prima Truck", 38_00_000)
        plazas = [("Kharpada Toll Plaza", 18.78, 73.10), ("Kashedi Ghat Check", 17.92, 73.43), ("Hathkhamba Toll", 17.03, 73.38), ("Patradevi Border Check", 15.74, 73.87)]
        seizures = []
        for k, (day, port) in enumerate(((140, "JNPT, Nhava Sheva"), (88, "Mormugao Port, Goa"), (41, "JNPT, Nhava Sheva"))):
            when = self.ts(day, 4)
            for j, (pl, la, lo) in enumerate(plazas):
                self.tolls.append((f"TH{len(self.tolls):06d}", truck, self.iso(when - timedelta(hours=30 - j * 6)), pl, la, lo, "NETC-FASTAG-SYN"))
            city = "Navi Mumbai" if "JNPT" in port else "Panaji"
            s_ = self.incident(f"NCB/MZU/CR-{k + 21}/{self.today.year}", "seizure", "NCB", city, ["NDPS Act 1985 s.8(c), 21(c), 29"],
                               f"Seizure of commercial quantity of synthetic drugs concealed in a container at {port}; courier arrested.", when, source="NCB-SYN")
            seizures.append(s_)
            c = couriers[k]
            self.s.upsert_link("accused_in", self.raw_record(c, "NCB-SYN", f"SEIZ{k}#A"), s_, source="NCB-SYN", record=f"SEIZ-{k}")
            self.s.upsert_link("mentions", s_, c.phone_oids[0], source="NCB-SYN", record=f"SEIZ-{k}")
            self.txn(when - timedelta(days=3), coord.accounts[0], c.accounts[0], rng.choice([45_000, 60_000, 75_000]), "UPI", "TRANSPORT CHARGES")
            for _ in range(12):
                self.call(when - timedelta(hours=rng.uniform(1, 72)), coord.phones[0], c.phones[0])
        for k in range(8):
            self.txn(self.ts(rng.randint(30, 200), 13), coord.accounts[0], self.hw_acct, rng.randint(4, 12) * 100_000, "NEFT", "PURCHASE OF FABRIC")
            self.txn(self.ts(rng.randint(30, 200), 11), None, coord.accounts[0], rng.choice([4_90_000, 4_95_000, 9_80_000]), "CASH", "CASH DEPOSIT")
        for d in range(20):
            self.call(self.ts(rng.randint(10, 200), rng.randint(9, 22)), coord.phones[0], self.hawala.phones[0])
        colombo_no, _ = self.phone(None, intl="+94771234567", subscriber="unknown (Sri Lanka)")
        for d in range(12):
            self.call(self.ts(rng.randint(10, 200), rng.randint(20, 23)), coord.phones[0], colombo_no)
        self.fly(coord, self.ts(110, 6), "Mumbai", "Colombo")
        self.fly(coord, self.ts(105, 6), "Colombo", "Mumbai")
        self.truth["operations"]["COASTLINE"] = {"coordinator": coord.oid, "couriers": [c.oid for c in couriers], "truck": truck, "seizures": seizures}

    def background_crime(self) -> None:
        rng = self.rng
        pool = [p for p in self.people if p.role == "background"]
        offences = [(["BNS 303(2)"], "Theft of a two-wheeler from a housing society parking."), (["BNS 305"], "House-breaking by night; gold ornaments stolen."),
                    (["BNS 115(2)", "BNS 352"], "Quarrel over a parking spot; complainant assaulted."), (["BNS 318(4)"], "Advance taken for a job abroad, not returned."),
                    (["BNS 309(4)"], "Mobile phone snatched near the bus stand.")]
        for k in range(220):
            sec, summ = rng.choice(offences)
            acc = rng.choice(pool)
            when = self.ts(rng.randint(5, 360), rng.randint(0, 23))
            inc = self.incident(f"MH/{acc.district or '000'}/CTY/{k + 1:04d}/{when.year}", "fir", "State Police", acc.city, sec, summ, when)
            self.s.upsert_link("accused_in", self.raw_record(acc, "CCTNS-SYN", f"FIR{k}#A"), inc, source="CCTNS-SYN", record=f"FIR-{k}")
            vic = rng.choice(pool)
            self.s.upsert_link("complainant_in", vic.oid, inc, source="CCTNS-SYN", record=f"FIR-{k}")

    def canaries(self) -> None:
        for latin, native, gender in CANARIES:
            oid = self.s.upsert_object("Person", {"name": latin, "name_native": native, "gender": gender, "birth_year": 1979,
                                                  "district_lgd": self.district_code.get("Pune")},
                                       source="SYN-CANARY", record=latin, synthetic=True)
            self.s.execute("INSERT INTO canaries(object_id) VALUES(?) ON CONFLICT DO NOTHING", (oid,))
            self.truth["canaries"].append(oid)

    # ------------------------------------------------------------------ derived links + flush
    def flush_events(self) -> None:
        s = self.s
        s.executemany("INSERT INTO txns(id,ts,from_acct,to_acct,amount,channel,narration,ref,country,source) VALUES(?,?,?,?,?,?,?,?,?,?)", self.txns)
        s.executemany("INSERT INTO cdrs(id,ts,a_number,b_number,duration_s,call_type,tower_id,legal_order,source) VALUES(?,?,?,?,?,?,?,?,?)", self.cdrs)
        s.executemany("INSERT INTO travel VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", self.travel)
        s.executemany("INSERT INTO tollhits(id,vehicle_id,ts,plaza,lat,lon,source) VALUES(?,?,?,?,?,?,?)", self.tolls)
        s.executemany("INSERT INTO towers(id,label,lat,lon,district_lgd) VALUES(?,?,?,?,?)", list(self.towers.values()))
        merchants = set(self.merchant_accts)
        # money edges: aggregated, ignoring routine retail payments to merchants
        for r in s.query("""SELECT from_acct, to_acct, COUNT(*) n, SUM(amount) total, MIN(ts) first, MAX(ts) last FROM txns
                            WHERE from_acct IS NOT NULL AND to_acct IS NOT NULL GROUP BY from_acct, to_acct"""):
            if r["to_acct"] in merchants or r["total"] < 20_000:
                continue
            s.upsert_link("transferred_to", r["from_acct"], r["to_acct"], source="BANK-SYN", record="ledger",
                          props={"count": r["n"], "total": round(r["total"], 2), "first": r["first"], "last": r["last"]}, validate=False)
        phone_ids = {o["props"]["number"]: o["id"] for o in s.objects_of_type("Phone")}
        for r in s.query("SELECT a_number, b_number, COUNT(*) n, SUM(duration_s) secs, MIN(ts) first, MAX(ts) last FROM cdrs GROUP BY a_number, b_number"):
            if r["n"] < 3 or r["a_number"] not in phone_ids or r["b_number"] not in phone_ids:
                continue
            s.upsert_link("called", phone_ids[r["a_number"]], phone_ids[r["b_number"]], source="TSP-CDR-SYN", record="cdr",
                          props={"count": r["n"], "seconds": r["secs"], "first": r["first"], "last": r["last"]}, validate=False)
        self.stats.update(txns=len(self.txns), cdrs=len(self.cdrs), trips=len(self.travel), toll_hits=len(self.tolls))

    def run(self) -> dict[str, Any]:
        with self.s.tx():
            self.background()
            self.social()
            self.op_mule_and_mirage()
            self.op_sunrise()
            self.op_kestrel()
            self.op_coastline()
            self.background_crime()
            self.canaries()
            from .missions import Missions  # every agency's mission track, with benign look-alikes

            self.stats["missions"] = Missions(self, seed=2026 + 7 * self.seed).run()
            self.flush_events()
        self.s.set_meta("synthetic_truth", self.truth)
        return dict(self.stats)

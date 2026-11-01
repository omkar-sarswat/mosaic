"""Dense background for the synthetic world: what a state holds in thousands, not tens.

On top of a built world this adds, deterministically from a seed:

* 1,250 mobile cell sites (operator, 4G or 5G, cell global identity, site type, locality), and the cell each
  ordinary call used: home cell most of the time, a work cell on weekday hours, elsewhere in the city now and then;
* 1,050 ANPR junction cameras and some 70 highway toll plazas, with the reads of ordinary vehicles (city driving
  plus out-of-town journeys a real car could make);
* vehicles (to 1,600), a handset (IMEI) for every SIM, 1,150 licensed firearms, 1,100 crypto-exchange wallets;
* 1,250 FIRs and complaints across the 24 cities with place, police station and coordinates, and coordinates
  for the FIRs already on record;
* 1,150 registered businesses (GSTIN, CIN, address, proprietor or director), 1,050 registered properties,
  1,100 public tenders with competitive bids, and 1,200 domestic journeys.

Everything added is ordinary by construction. The planted operations, people in cases or on record, their
families and associates are left exactly as they were; nobody new shares a handset; bids are dispersed;
journeys are drivable; properties were bought long before any check period and within the owner's means;
complaints are dated away from the complainant's own transfers. The test suite rebuilds a world with this
background and checks that the pattern engine raises nothing new.
"""

from __future__ import annotations

import json
import math
import random
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable

from ..store import Store, make_id
from .places import FIR_UNIT, GST_STATE, HUB, LOCALITIES, ROUTES, RTO
from .world import AIRPORT, CITIES, CITY_WEIGHTS

TARGETS = {"towers": 1250, "cameras": 1050, "incidents": 1250, "businesses": 1150, "properties": 1050, "firearms": 1150,
           "wallets": 1100, "tenders": 1100, "vehicles_total": 1600, "journeys": 1200}
OPERATORS = [("Jio", "405-861"), ("Airtel", "404-90"), ("Vi", "404-20"), ("BSNL", "404-66")]
SUFFIX = ["Chowk", "Junction", "Signal", "Circle", "Naka", "Flyover", "Market Road", "Station Road"]
LINK_PERSON = ("accused_in", "complainant_in", "victim_in", "witness_in", "convicted_in", "history_sheeted_at", "employee_of",
               "director_of", "controls", "signatory_of")


def km(a: float, b: float, c: float, d: float) -> float:
    x = math.radians(d - b) * math.cos(math.radians((a + c) / 2))
    return 6371.0 * math.hypot(math.radians(c - a), x)


def luhn(body: str) -> str:
    total = 0
    for i, ch in enumerate(reversed(body)):
        n = int(ch)
        if i % 2 == 0:
            n *= 2
            n = n - 9 if n > 9 else n
        total += n
    return body + str((10 - total % 10) % 10)


class Enricher:
    def __init__(self, store: Store, *, seed: int = 29, now: datetime | None = None, targets: dict[str, int] | None = None, log: Callable = print):
        self.s = store
        self.rng = random.Random(seed)
        self.now = (now or datetime.now(timezone.utc)).replace(second=0, microsecond=0)
        self.t = {**TARGETS, **(targets or {})}
        self.log = log
        self.stats: Counter[str] = Counter()
        self.used: set[str] = set()

    # ------------------------------------------------------------------ helpers
    def uniq(self, fn: Callable[[], str]) -> str:
        for _ in range(1000):
            v = fn()
            if v not in self.used:
                self.used.add(v)
                return v
        raise RuntimeError("could not draw a unique value")

    def digits(self, n: int) -> str:
        return "".join(self.rng.choice("0123456789") for _ in range(n))

    def letters(self, n: int, alphabet: str = "ABCDEFGHJKLMNPRSTUVWXYZ") -> str:
        return "".join(self.rng.choice(alphabet) for _ in range(n))

    def iso(self, t: datetime) -> str:
        return t.isoformat(timespec="minutes")

    def jitter(self, lat: float, lon: float, sd_km: float) -> tuple[float, float]:
        return (round(lat + self.rng.gauss(0, sd_km / 111), 5),
                round(lon + self.rng.gauss(0, sd_km / (111 * math.cos(math.radians(lat)))), 5))

    def district(self, city: str) -> str | None:
        return self.district_of.get(city)

    def nearest_locality(self, city: str, lat: float, lon: float) -> str:
        locs = LOCALITIES.get(city) or [(city, *CITIES[city][1:3])]
        return min(locs, key=lambda x: km(lat, lon, x[1], x[2]))[0]

    def near_asset(self, lat: float, lon: float, within_km: float) -> str | None:
        best, name = within_km, None
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                for a_lat, a_lon, a_name in self.asset_grid.get((round(lat * 50) + dy, round(lon * 50) + dx), ()):
                    d = km(lat, lon, a_lat, a_lon)
                    if d < best:
                        best, name = d, a_name
        return name

    # ------------------------------------------------------------------ the world as it stands
    def load(self) -> None:
        s = self.s
        q = s.query
        self.district_of = {}
        for p in q("SELECT props FROM objects WHERE type='Person' AND props LIKE '%\"aadhaar\"%' LIMIT 4000"):
            pr = json.loads(p["props"])
            if pr.get("city") in CITIES and pr.get("district_lgd"):
                self.district_of.setdefault(pr["city"], pr["district_lgd"])
        self.asset_grid: dict[tuple[int, int], list[tuple[float, float, str]]] = defaultdict(list)
        for r in q("SELECT lat, lon, props FROM objects WHERE type='Asset' AND lat IS NOT NULL"):
            name = (json.loads(r["props"]).get("name") or "").split("|")[0].strip()
            if name:
                self.asset_grid[(round(r["lat"] * 50), round(r["lon"] * 50))].append((r["lat"], r["lon"], name))

        people: dict[str, dict[str, Any]] = {}
        for r in q("SELECT id, props FROM objects WHERE type='Person'"):
            pr = json.loads(r["props"])
            if pr.get("aadhaar") and pr.get("city") in CITIES:
                born = pr.get("birth_year") or 1985
                people[r["id"]] = {"id": r["id"], "name": pr.get("name", ""), "city": pr["city"], "district": pr.get("district_lgd"),
                                   "income": int(pr.get("declared_income") or 0), "occupation": pr.get("occupation") or "", "age": self.now.year - int(born),
                                   "gender": pr.get("gender"), "pan": pr.get("pan"), "home": None, "phones": [], "vehicles": [], "accounts": []}
        self.people = people
        for r in q("SELECT l.src, o.lat, o.lon FROM links l JOIN objects o ON o.id=l.dst WHERE l.type='resides_at' AND o.lat IS NOT NULL"):
            if r["src"] in people:
                people[r["src"]]["home"] = (r["lat"], r["lon"])
        users: dict[str, set[str]] = defaultdict(set)
        self.phone_info: dict[str, dict[str, Any]] = {}
        for r in q("SELECT l.src, o.id, o.props FROM links l JOIN objects o ON o.id=l.dst WHERE l.type='uses_phone'"):
            users[r["id"]].add(r["src"])
            pr = json.loads(r["props"])
            self.phone_info[r["id"]] = {"number": pr.get("number"), "operator": pr.get("operator")}
        self.owner_of_number: dict[str, str] = {}
        for ph, us in users.items():
            if len(us) == 1:
                (u,) = us
                if u in people:
                    people[u]["phones"].append(ph)
                    self.owner_of_number[self.phone_info[ph]["number"]] = u
        for r in q("SELECT src, dst FROM links WHERE type='owns' AND dst LIKE 'vehicle:%'"):
            if r["src"] in people:
                people[r["src"]]["vehicles"].append(r["dst"])
        for r in q("SELECT src, dst FROM links WHERE type='holds_account' AND dst LIKE 'bankaccount:%'"):
            if r["src"] in people:
                people[r["src"]]["accounts"].append(r["dst"])
        self.family: dict[str, set[str]] = defaultdict(set)
        for r in q("SELECT src, dst FROM links WHERE type IN ('relative_of','same_as')"):
            self.family[r["src"]].add(r["dst"])
            self.family[r["dst"]].add(r["src"])
        self.vehicle_count = q("SELECT COUNT(*) n FROM objects WHERE type='Vehicle'")[0]["n"]
        self.with_device = {r["src"] for r in q("SELECT src FROM links WHERE type='sim_in_device'")}
        self.read_vehicles = {r["vehicle_id"] for r in q("SELECT DISTINCT vehicle_id FROM tollhits")}
        self.incident_vehicles = {r["src"] for r in q("SELECT src FROM links WHERE type IN ('stolen_in','used_in','recovered_in','mentions')")} | \
                                 {r["dst"] for r in q("SELECT dst FROM links WHERE type='mentions'")}
        self.protect()

    def protect(self) -> None:
        """Who must stay exactly as built, and who may not take each kind of new record.

        * Untouched: people named in the planted operations and benign look-alikes, people in case scopes or in
          any lead, and their families. They get nothing new.
        * Calls left unlocated: every group a reconnaissance check would examine (people tied by 8+ calls, joint
          FIRs or a shared handset, in a component with someone on record).
        * No new property: public servants and their families (the disproportionate-assets check).
        * No new company: anyone who already directs, controls or signs for one (nominee and shell checks).
        """
        q = self.s.query
        core: set[str] = set()

        def walk(x: Any) -> None:
            if isinstance(x, str):
                if x.startswith("person:"):
                    core.add(x)
            elif isinstance(x, dict):
                for k, v in x.items():
                    walk(k)
                    walk(v)
            elif isinstance(x, (list, tuple, set)):
                for v in x:
                    walk(v)
        walk(self.s.get_meta("synthetic_truth") or {})
        core |= {r["object_id"] for r in q("SELECT object_id FROM case_objects WHERE object_id LIKE 'person:%'")}
        for r in q("SELECT subjects FROM pattern_hits"):
            core |= {x for x in json.loads(r["subjects"]) if x.startswith("person:")}
        for p, info in self.people.items():
            if set(info["vehicles"]) & self.read_vehicles:
                core.add(p)
        untouched = set(core)
        for c in core:
            untouched |= self.family.get(c, set())
        self.untouched = untouched
        self.on_record = {r["src"] for r in q("SELECT src FROM links WHERE type='accused_in' AND src LIKE 'person:%'")} | core
        pairs: Counter[tuple[str, str]] = Counter()
        self.foreign: set[str] = set()
        for r in q("SELECT a_number, b_number FROM cdrs"):
            a, b = self.owner_of_number.get(r["a_number"]), self.owner_of_number.get(r["b_number"])
            if a and b and a != b:
                pairs[(a, b) if a < b else (b, a)] += 1
            if a and r["b_number"].startswith("+"):
                self.foreign.add(a)
            if b and r["a_number"].startswith("+"):
                self.foreign.add(b)
        self.call_pairs = pairs
        self.directors = {r["src"] for r in q("SELECT src FROM links WHERE type IN ('director_of','controls','signatory_of') AND src LIKE 'person:%'")}
        servants = {r["src"] for r in q("SELECT src FROM links WHERE type='employee_of'")}
        self.no_assets = servants | {f for s in servants for f in self.family.get(s, set())}
        holders = {r["dst"]: r["src"] for r in q("SELECT src, dst FROM links WHERE type='holds_account' AND src LIKE 'person:%'")}
        self.pays_people = set()
        for r in q("SELECT DISTINCT from_acct, to_acct FROM txns WHERE from_acct IS NOT NULL AND to_acct IS NOT NULL"):
            if r["to_acct"] in holders and r["from_acct"] in holders:
                self.pays_people.add(holders[r["from_acct"]])
        self.complained = {r["src"] for r in q("SELECT src FROM links WHERE type IN ('complainant_in','victim_in') AND src LIKE 'person:%'")}
        self.new_accused: set[str] = set()
        self.free = [p for p in sorted(self.people) if p not in untouched and self.people[p]["home"]]
        self.stats["people_left_untouched"] = len(self.people) - len(self.free)

    def recce_groups(self) -> set[str]:
        """Everyone in a group the reconnaissance check would examine; their calls stay unlocated."""
        parent: dict[str, str] = {}

        def find(x: str) -> str:
            parent.setdefault(x, x)
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a: str, b: str) -> None:
            parent[find(a)] = find(b)
        for (a, b), n in self.call_pairs.items():
            if n >= 8 and b not in self.family.get(a, set()):
                union(a, b)
        by_incident: dict[str, list[str]] = defaultdict(list)
        for r in self.s.query("SELECT src, dst FROM links WHERE type='accused_in' AND src LIKE 'person:%'"):
            by_incident[r["dst"]].append(r["src"])
        for ps in by_incident.values():
            for x in ps[1:]:
                union(ps[0], x)
        by_device: dict[str, list[str]] = defaultdict(list)
        owner = {ph: p for p, info in self.people.items() for ph in info["phones"]}
        for r in self.s.query("SELECT src, dst FROM links WHERE type='sim_in_device'"):
            if r["src"] in owner:
                by_device[r["dst"]].append(owner[r["src"]])
        for ps in by_device.values():
            for x in ps[1:]:
                union(ps[0], x)
        marked = {find(p) for p in self.on_record | self.new_accused if p in parent}
        return {p for p in parent if find(p) in marked} | self.on_record | self.new_accused

    # ------------------------------------------------------------------ infrastructure
    def city_counts(self, total: int, floor: int) -> dict[str, int]:
        w = sum(CITY_WEIGHTS.values())
        return {c: max(floor, round(total * CITY_WEIGHTS[c] / w)) for c in CITIES}

    def point_in(self, city: str, spread_km: float = 1.0) -> tuple[float, float, str]:
        rng = self.rng
        _, clat, clon, _ = CITIES[city]
        if rng.random() < 0.6 and LOCALITIES.get(city):
            name, la, lo = rng.choice(LOCALITIES[city])
            lat, lon = self.jitter(la, lo, spread_km)
            return lat, lon, name
        lat = round(clat + rng.uniform(-0.055, 0.055), 5)
        lon = round(clon + rng.uniform(-0.055, 0.055), 5)
        return lat, lon, self.nearest_locality(city, lat, lon)

    def towers(self) -> None:
        rng = self.rng
        rows = []
        self.cells: dict[str, list[tuple[str, float, float, str]]] = defaultdict(list)  # city -> (id, lat, lon, operator)
        n = 0
        for city, count in self.city_counts(self.t["towers"], 18).items():
            code = AIRPORT.get(city, city[:3].upper())
            lac_base = 10000 + 97 * list(CITIES).index(city)
            for k in range(count):
                n += 1
                op, mccmnc = OPERATORS[k % 4]
                lat, lon, loc = self.point_in(city, 1.2)
                asset = self.near_asset(lat, lon, 0.45)
                site = rng.choices(["rooftop", "ground-based tower", "small cell", "in-building"], weights=[50, 30, 15, 5])[0]
                tid = f"TWR-{code}-{10000 + n}"
                label = f"{'Near ' + asset + ', ' if asset else ''}{loc} ({site}, {op})"
                cgi = f"{mccmnc}-{lac_base + k % 7}-{self.uniq(lambda: self.digits(5))}"
                rows.append((tid, label, lat, lon, self.district(city), op, rng.choices(["4G", "5G"], weights=[68, 32])[0], cgi, site, city))
                self.cells[city].append((tid, lat, lon, op))
        self.s.executemany("INSERT INTO towers(id,label,lat,lon,district_lgd,operator,technology,cgi,site_type,city) VALUES(?,?,?,?,?,?,?,?,?,?) "
                           "ON CONFLICT(id) DO NOTHING", rows)
        self.stats["cell_sites"] = len(rows)

    def checkpoints(self) -> None:
        rng = self.rng
        rows = []
        self.cams: dict[str, list[tuple[str, float, float]]] = defaultdict(list)  # city -> (label, lat, lon)
        labels: set[str] = set()
        n = 0
        for city, count in self.city_counts(self.t["cameras"], 14).items():
            for k in range(count):
                lat, lon, loc = self.point_in(city, 0.9)
                asset = self.near_asset(lat, lon, 0.35)
                base = f"{loc} {rng.choice(SUFFIX)}"
                label = f"ANPR {base}" + (f" (near {asset})" if asset else "")
                i = 2
                while label in labels:
                    label = f"ANPR {base} {i}" + (f" (near {asset})" if asset else "")
                    i += 1
                labels.add(label)
                n += 1
                rows.append((f"CAM-{FIR_UNIT[city]}-{n:05d}", "anpr", label, lat, lon, self.district(city), city, f"{loc} {rng.choice(['Road', 'Marg', 'Main Road'])}", "City traffic police"))
                self.cams[city].append((label, lat, lon))
        self.plazas: dict[tuple[str, str], list[tuple[str, float, float, float]]] = {}  # (a,b) -> [(label, lat, lon, km from a)]
        for a, b, road in ROUTES:
            _, la, lo, _ = CITIES[a]
            _, lb, lob, _ = CITIES[b]
            dist = km(la, lo, lb, lob)
            k = max(2, min(5, round(dist / 110)))
            stops = []
            for i in range(k):
                f = (i + 1) / (k + 1) + rng.uniform(-0.04, 0.04)
                lat, lon = round(la + (lb - la) * f + rng.uniform(-0.03, 0.03), 5), round(lo + (lob - lo) * f + rng.uniform(-0.03, 0.03), 5)
                label = f"{road} toll plaza, km {int(dist * 1.25 * f)} ({a}-{b})"
                rows.append((f"TOLL-{FIR_UNIT[a]}-{FIR_UNIT[b]}-{i + 1}", "toll", label, lat, lon, None, None, road, "NHAI concessionaire"))
                stops.append((label, lat, lon, km(la, lo, lat, lon)))
            self.plazas[(a, b)] = stops
            self.plazas[(b, a)] = [(lab, lat, lon, dist - d) for lab, lat, lon, d in reversed(stops)]
        self.s.executemany("INSERT INTO checkpoints(id,kind,label,lat,lon,district_lgd,city,road,operator) VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING", rows)
        self.stats["anpr_cameras"] = sum(1 for r in rows if r[1] == "anpr")
        self.stats["toll_plazas"] = sum(1 for r in rows if r[1] == "toll")

    def police_station(self, city: str, locality: str) -> tuple[str, str]:
        name = f"{locality} Police Station" if locality != city else f"{city} City Police Station"
        lat, lon = next(((la, lo) for n, la, lo in LOCALITIES.get(city, []) if n == locality), CITIES[city][1:3])
        oid = self.s.upsert_object("Organisation", {"name": name, "kind": "police_station", "city": city, "district_lgd": self.district(city),
                                                   "country": "IN"}, source="CCTNS-SYN", record=f"PS:{city}|{locality}", synthetic=True, lat=lat, lon=lon)
        return oid, name

    # ------------------------------------------------------------------ people's things
    def devices(self) -> None:
        rng = self.rng
        models = [("Samsung", "Galaxy A15", "smartphone", 3), ("Xiaomi", "Redmi Note 13", "smartphone", 3), ("Vivo", "Y28", "smartphone", 2),
                  ("Realme", "Narzo 70", "smartphone", 2), ("Oppo", "A79", "smartphone", 1), ("OnePlus", "Nord CE4", "smartphone", 1),
                  ("Apple", "iPhone 13", "smartphone", 1), ("Samsung", "Galaxy S23", "smartphone", 1), ("Motorola", "G54", "smartphone", 1),
                  ("Nokia", "105", "feature phone", 1), ("Jio", "Bharat V2", "feature phone", 1), ("itel", "it2163", "feature phone", 1)]
        n = 0
        for pid in self.free:
            p = self.people[pid]
            phones = [ph for ph in p["phones"] if ph not in self.with_device]
            if not phones:
                continue
            rich = p["income"] >= 1_500_000
            pool = [m for m in models if (m[1] in ("iPhone 13", "Galaxy S23", "Nord CE4")) == rich or rng.random() < 0.15]
            make, model, kind, _ = rng.choices(pool or models, weights=[m[3] for m in (pool or models)])[0]
            imei = self.uniq(lambda: luhn("35" + self.digits(12)))
            dev = self.s.upsert_object("Device", {"imei": imei, "model": f"{make} {model}", "make": make, "kind": kind},
                                       source="TSP-SYN", record=f"IMEI:{imei}", obj_id=make_id("Device", "imei", imei), synthetic=True)
            for ph in phones:  # dual-SIM: a person's own numbers share their own handset
                self.s.upsert_link("sim_in_device", ph, dev, source="TSP-SYN", record=f"IMEI:{imei}:{self.phone_info[ph]['number']}")
            n += 1
        self.stats["handsets"] = n

    def vehicles(self) -> None:
        rng = self.rng
        cars_hi = ["Hyundai Creta", "Kia Seltos", "Toyota Innova Crysta", "Mahindra Scorpio-N", "Maruti Brezza", "Honda City", "Tata Harrier"]
        cars = ["Maruti Swift", "Maruti Dzire", "Maruti WagonR", "Maruti Baleno", "Tata Punch", "Hyundai i20", "Tata Tiago"]
        bikes = ["Hero Splendor Plus", "Honda Activa 6G", "Bajaj Pulsar 150", "TVS Jupiter", "Suzuki Access 125", "Royal Enfield Classic 350", "Honda Shine"]
        need = self.t["vehicles_total"] - self.vehicle_count
        pool = [p for p in self.free if not self.people[p]["vehicles"] and self.people[p]["age"] >= 20 and p not in self.no_assets]
        rng.shuffle(pool)
        made = 0
        for pid in pool:
            if made >= need:
                break
            p = self.people[pid]
            inc, city = p["income"], p["city"]
            if p["occupation"] == "Driver" and rng.random() < 0.5:
                model, cls, val, fuel = rng.choice([("Bajaj RE auto-rickshaw", "3W (transport)", 280_000, "CNG"), ("Tata Ace", "LGV (goods)", 450_000, "Diesel"),
                                                    ("Mahindra Bolero Pickup", "LGV (goods)", 850_000, "Diesel")])
            elif inc >= 1_500_000:
                model, cls, val, fuel = rng.choice(cars_hi), "LMV", rng.randint(11, 24) * 100_000, rng.choice(["Petrol", "Diesel"])
            elif inc >= 500_000 and rng.random() < 0.6:
                model, cls, val, fuel = rng.choice(cars), "LMV", rng.randint(5, 9) * 100_000, rng.choice(["Petrol", "CNG", "Petrol"])
            else:
                model, cls, val, fuel = rng.choice(bikes), "MCWG", rng.randint(65, 190) * 1000, rng.choice(["Petrol", "Petrol", "Electric"])
            rto = RTO[city]
            series_len = 1 if rto.startswith("DL") else 2
            reg = self.uniq(lambda: f"{rto}{self.letters(series_len)}{rng.randint(1, 9999):04d}")
            year = rng.randint(2012, self.now.year)
            props = {"registration_no": reg, "make": model, "colour": rng.choice(["White", "Black", "Silver", "Red", "Grey", "Blue"]), "value": val,
                     "chassis_no": self.uniq(lambda: "MA" + self.letters(1) + self.digits(3) + self.letters(2) + self.digits(9)),
                     "engine_no": self.uniq(lambda: self.letters(2) + self.digits(8)), "status": "registered", "vehicle_class": cls,
                     "fuel": fuel, "year": year, "rto": f"{rto[:4]} {city}"}
            vid = self.s.upsert_object("Vehicle", props, source="VAHAN-SYN", record=f"RC:{reg}", obj_id=make_id("Vehicle", "reg", reg), synthetic=True)
            self.s.upsert_link("owns", pid, vid, source="VAHAN-SYN", record=f"RC:{reg}")
            p["vehicles"].append(vid)
            p.setdefault("new_vehicles", []).append((vid, val, cls))
            made += 1
        self.stats["vehicles_added"] = made

    def reads(self) -> None:
        """Ordinary driving: a handful of usual cameras near home, now and then an out-of-town journey along a highway."""
        rng = self.rng
        rows = []
        n = 0
        end = self.now - timedelta(hours=2)
        vals = {r["id"]: json.loads(r["props"]) for r in self.s.query("SELECT id, props FROM objects WHERE type='Vehicle'")}
        for pid in self.free:
            p = self.people[pid]
            hlat, hlon = p["home"]
            near = sorted((c for cs in self.cams.values() for c in cs if abs(c[1] - hlat) < 0.15 and abs(c[2] - hlon) < 0.15),
                          key=lambda c: km(hlat, hlon, c[1], c[2]))
            near = [c for c in near if km(hlat, hlon, c[1], c[2]) <= 12]
            if not near:
                continue
            for vid in p["vehicles"]:
                if vid in self.read_vehicles or vid in self.incident_vehicles:
                    continue
                pr = vals.get(vid, {})
                cls = pr.get("vehicle_class") or ("MCWG" if (pr.get("value") or 0) < 300_000 else "LMV")
                usual = near[:10]
                usual = rng.sample(usual, min(len(usual), rng.randint(3, 5)))
                k = {"MCWG": rng.randint(4, 14), "LMV": rng.randint(8, 26)}.get(cls, rng.randint(15, 36))
                trip_days: set[int] = set()
                trips = []
                hub = HUB.get(p["city"], p["city"])
                routes = [(a, b) for (a, b) in self.plazas if a == hub]
                if cls in ("LMV", "LGV (goods)") and routes and rng.random() < 0.3:
                    for _ in range(rng.randint(1, 3)):
                        d0 = rng.randint(4, 175)
                        stay = rng.randint(1, 5)
                        if any(d in trip_days for d in range(d0 - stay - 1, d0 + 2)):
                            continue
                        trip_days |= set(range(d0 - stay - 1, d0 + 2))
                        trips.append((d0, stay, rng.choice(routes)))
                days = [d for d in rng.sample(range(1, 180), min(k, 150)) if d not in trip_days]
                for d in days:
                    times = [rng.choices(range(7, 23), weights=[3, 6, 8, 6, 4, 4, 4, 4, 4, 5, 7, 8, 7, 5, 3, 2])[0]]
                    if rng.random() < 0.2:
                        times.append(min(22, times[0] + rng.randint(3, 8)))
                    for h in times:
                        cam = rng.choice(usual) if rng.random() < 0.8 else rng.choice(near)
                        t = (end - timedelta(days=d)).replace(hour=h, minute=rng.randint(0, 59))
                        n += 1
                        rows.append((f"AN{n:08d}", vid, self.iso(t), cam[0], cam[1], cam[2], "VAHAN-ANPR-SYN", "anpr"))
                for d0, stay, route in trips:
                    stops = self.plazas[route]
                    dep = (end - timedelta(days=d0)).replace(hour=rng.randint(6, 11), minute=rng.randint(0, 59))
                    for lab, lat, lon, dist in stops:
                        t = dep + timedelta(hours=dist * 1.25 / 55)
                        n += 1
                        rows.append((f"AN{n:08d}", vid, self.iso(t), lab, lat, lon, "NETC-FASTAG-SYN", "toll"))
                    back = self.plazas[(route[1], route[0])]
                    ret = (dep + timedelta(days=stay)).replace(hour=rng.randint(8, 14), minute=rng.randint(0, 59))
                    for lab, lat, lon, dist in back:
                        t = ret + timedelta(hours=dist * 1.25 / 55)
                        n += 1
                        rows.append((f"AN{n:08d}", vid, self.iso(t), lab, lat, lon, "NETC-FASTAG-SYN", "toll"))
        rows = [r for r in rows if r[2] <= self.iso(end)]
        self.s.executemany("INSERT INTO tollhits(id,vehicle_id,ts,plaza,lat,lon,source,kind) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING", rows)
        self.stats["plate_reads"] = len(rows)

    def locate_calls(self) -> None:
        """The cell each ordinary call went through: the home cell, a work cell on weekday hours, elsewhere now and then.

        People in a group the reconnaissance check examines are located only at their home cell, and only when they
        call from it on twelve or more days: an anchor in that check's own terms, so no visit can be read into it."""
        rng = self.rng
        cell_of: dict[str, dict[str, Any]] = {}
        quiet = self.recce_groups()
        days: dict[str, set[str]] = defaultdict(set)
        for r in self.s.query("SELECT a_number, ts FROM cdrs"):
            days[r["a_number"]].add(r["ts"][:10])
        home_only = 0
        for pid in self.free:
            p = self.people[pid]
            if pid in quiet:
                if pid in self.on_record or pid in self.new_accused:
                    continue
                if not all(len(days.get(self.phone_info[ph]["number"], ())) >= 12 for ph in p["phones"]):
                    continue
                home_only += 1
            hlat, hlon = p["home"]
            for ph in p["phones"]:
                op = self.phone_info[ph]["operator"]
                cells = [c for c in self.cells.get(p["city"], []) if c[3] == op] or self.cells.get(p["city"], [])
                if not cells:
                    continue
                by_dist = sorted(cells, key=lambda c: km(hlat, hlon, c[1], c[2]))
                home = by_dist[0][0]
                work_pool = [c[0] for c in by_dist if 2 <= km(hlat, hlon, c[1], c[2]) <= 9] or [c[0] for c in by_dist[1:6]] or [home]
                works = p["occupation"] not in ("Student", "Homemaker", "Retired", "Farmer", "") and pid not in quiet
                cell_of[self.phone_info[ph]["number"]] = {"home": home, "work": rng.choice(work_pool) if works else None,
                                                          "any": [home] if pid in quiet else [c[0] for c in by_dist[:25]]}
        updates = []
        for r in self.s.query("SELECT id, ts, a_number FROM cdrs WHERE tower_id IS NULL"):
            c = cell_of.get(r["a_number"])
            if not c:
                continue
            t = datetime.fromisoformat(r["ts"])
            roll = rng.random()
            if c["work"] and t.weekday() < 5 and 9 <= t.hour < 18 and roll < 0.75:
                tw = c["work"]
            elif roll < 0.93:
                tw = c["home"]
            else:
                tw = rng.choice(c["any"])
            updates.append((tw, r["id"]))
        self.s.executemany("UPDATE cdrs SET tower_id=? WHERE id=?", updates)
        self.stats["calls_located"] = len(updates)
        self.stats["people_located_at_home_only"] = home_only

    # ------------------------------------------------------------------ businesses, firearms, property, wallets
    def businesses(self) -> None:
        rng = self.rng
        prefixes = ["Shree", "Om Sai", "Jai Bhavani", "Mahalaxmi", "Sahyadri", "Deccan", "Konkan", "Vighnaharta", "Gajanan", "Siddhivinayak",
                    "Kalyani", "Navkar", "Balaji", "Trimurti", "Swami Samarth", "New India", "Sai Krupa", "Annapurna", "Vishal", "Sunrise",
                    "Pragati", "Prabhat", "Matoshree", "Ashtavinayak", "Shivneri", "Godavari", "Krishna", "Narmada", "Indrayani", "Kaveri",
                    "Ganga", "Yamuna", "Sapphire", "Silverline", "Evergreen", "Royal", "Unity", "Mangalam", "Shubh Labh", "Vardhaman"]
        kinds = [  # kind, constitution, cores, weight
            ("merchant", "Proprietorship", ["Traders", "Kirana Stores", "Hardware", "Electricals", "Mobile Shoppe", "Medical & General Stores",
                                            "Jewellers", "Sweets", "Steel Centre", "Tyres", "Auto Parts", "Opticals", "Textiles", "Footwear",
                                            "Furniture", "Bakery", "Paints", "Stationers"], 40),
            ("company", "Private limited company", ["Infrastructure Pvt Ltd", "Agro Industries Pvt Ltd", "Logistics Pvt Ltd", "Engineering Works Pvt Ltd",
                                                    "Builders & Developers Pvt Ltd", "Packaging Pvt Ltd", "Polymers Pvt Ltd", "Foods Pvt Ltd",
                                                    "Technologies Pvt Ltd", "Construction Pvt Ltd", "Fabricators Pvt Ltd", "Healthcare Services Pvt Ltd",
                                                    "Software Solutions Pvt Ltd", "Textiles Pvt Ltd", "Hospitality Pvt Ltd"], 32),
            ("company", "Partnership firm", ["Enterprises", "Associates", "Industries", "Builders", "Contractors", "Agencies"], 14),
            ("transport", "Proprietorship", ["Roadlines", "Transport Co.", "Carriers", "Cargo Movers", "Travels"], 8),
            ("other", "Private limited company", ["Security Services Pvt Ltd", "Protection Force Pvt Ltd", "Guarding Solutions Pvt Ltd"], 6),
        ]
        pool = [p for p in self.free if self.people[p]["age"] >= 24 and p not in self.directors and self.people[p]["income"] >= 250_000]
        rng.shuffle(pool)
        pool = pool + [p for p in pool if self.people[p]["income"] >= 600_000]  # a second business: a shop beside a company
        names: set[str] = set()
        self.firms: list[dict[str, Any]] = []
        self.security: list[dict[str, Any]] = []
        held: dict[str, set[str]] = defaultdict(set)
        for i in range(len(pool)):
            if len(self.firms) + len(self.security) >= self.t["businesses"]:
                break
            owner = self.people[pool[i]]
            city = owner["city"] if rng.random() < 0.8 else rng.choice(list(CITIES))
            kind, constitution, cores, _ = rng.choices(kinds, weights=[k[3] for k in kinds])[0]
            # never two companies (that is what a nominee looks like); a second business is a shop or a transport firm
            if held[owner["id"]] and ("company" in held[owner["id"]] or kind in ("company", "other")):
                kind, constitution, cores, _ = kinds[0] if "merchant" not in held[owner["id"]] else kinds[3]
            if kind in held[owner["id"]]:
                continue
            held[owner["id"]].add(kind if kind in ("merchant", "transport") else "company")
            name = ""
            for _ in range(50):
                name = f"{rng.choice(prefixes)} {rng.choice(cores)}"
                if name in names:
                    name = f"{name.split(' Pvt Ltd')[0]}, {city}" + (" Pvt Ltd" if "Pvt Ltd" in name else "")
                if name not in names:
                    break
            names.add(name)
            st = CITIES[city][3]
            years_ago = rng.randint(2, 30)
            inc_on = date(self.now.year - years_ago, rng.randint(1, 12), rng.randint(1, 28))
            if constitution == "Proprietorship":
                pan = owner["pan"] or ""
            else:
                pan = self.uniq(lambda: self.letters(3, "ABCDEFGHIJKLMNOPQRSTUVWXYZ") + ("C" if "limited" in constitution else "F") + name[0].upper() + self.digits(4) + self.letters(1))
            lat, lon, loc = self.point_in(city, 0.8)
            unit = rng.choice(["Shop No.", "Office", "Unit", "Gala No."])
            address = f"{unit} {rng.randint(1, 240)}, {rng.choice(['Shivam', 'Mangal', 'Om', 'Sai', 'Shanti', 'Prestige', 'Galaxy'])} {rng.choice(['Complex', 'Plaza', 'Arcade', 'Chambers', 'Industrial Estate'])}, {loc}, {city}"
            props: dict[str, Any] = {"name": name, "kind": kind, "constitution": constitution, "city": city, "country": "IN",
                                     "district_lgd": self.district(city), "incorporated_on": inc_on.isoformat(), "registered_address": address,
                                     "sector": rng.choice(cores).replace(" Pvt Ltd", "") if kind != "merchant" else "Retail trade",
                                     "employees": rng.randint(2, 15) if kind == "merchant" else rng.randint(8, 400),
                                     "gst_turnover": rng.randint(15, 900) * 100_000}
            if pan:
                props["pan"] = pan
                props["gstin"] = self.uniq(lambda: f"{GST_STATE.get(st, '27')}{pan}{rng.randint(1, 9)}Z{rng.choice('0123456789ABCDEFGHJK')}")
            if "limited" in constitution:
                props["cin"] = self.uniq(lambda: f"U{rng.randint(10000, 99999)}{st}{inc_on.year}PTC{self.digits(6)}")
                props["paid_up_capital"] = rng.choice([1, 5, 10, 25, 50, 100]) * 100_000
            source, record = ("MCA-SYN", f"ROC:{props['cin']}") if "cin" in props else ("GSTN-SYN", f"GST:{props.get('gstin', name)}")
            oid = self.s.upsert_object("Organisation", props, source=source, record=record, synthetic=True, lat=lat, lon=lon)
            loc_id = self.s.upsert_object("Location", {"label": address.split(f", {city}")[0], "address": address, "city": city,
                                                       "district_lgd": self.district(city), "country": "IN", "pin": None},
                                          source=source, record=f"ADDR:{address}", synthetic=True, lat=lat, lon=lon)
            self.s.upsert_link("registered_at", oid, loc_id, source=source, record=record)
            self.s.upsert_link("director_of" if "limited" in constitution else "controls", owner["id"], oid, source=source, record=record)
            firm = {"id": oid, "kind": kind, "city": city, "state": st, "name": name, "ip": None}
            (self.security if kind == "other" else self.firms).append(firm)
        self.stats["businesses"] = len(self.firms) + len(self.security)

    def firearms(self) -> None:
        rng = self.rng
        makes = [("Small Arms Factory, Kanpur", "revolver", ".32"), ("Rifle Factory Ishapore", "shotgun", "12 bore"),
                 ("Gun & Shell Factory, Cossipore", "pistol", ".32"), ("Ordnance Factory Tiruchirappalli", "rifle", ".315"),
                 ("Rifle Factory Ishapore", "rifle", ".22")]
        made = 0
        seq: Counter[str] = Counter()

        def gun(holder: str, city: str, choice: tuple[str, str, str], who: str) -> None:
            nonlocal made
            make, kind, calibre = choice
            st = CITIES[city][3]
            year = rng.randint(self.now.year - 12, self.now.year - 1)
            seq[f"{st}{city}{year}"] += 1
            lic = self.uniq(lambda: f"{st}/{FIR_UNIT[city]}/ARMS/{year}/{rng.randint(1000, 99999):05d}")
            serial = self.uniq(lambda: f"{kind[:1].upper()}{calibre.replace('.', '').replace(' ', '')[:3]}-{self.digits(6)}")
            fid = self.s.upsert_object("Firearm", {"serial_no": serial, "make": make, "kind": kind, "calibre": calibre, "licence_no": lic, "status": "licensed",
                                                   "licensing_authority": f"{'Commissioner of Police' if city in FIR_UNIT and FIR_UNIT[city] in ('MUM', 'PUNE', 'THN', 'NMB', 'NGP', 'NSK', 'DEL', 'HYD', 'BLR', 'KOL', 'CHN') else 'District Magistrate'}, {city}",
                                                   "licence_valid_until": date(self.now.year + rng.randint(0, 4), rng.randint(1, 12), rng.randint(1, 28)).isoformat()},
                                       source="ARMS-LICENCE-SYN", record=f"LIC:{lic}", obj_id=make_id("Firearm", "serial", serial), synthetic=True)
            self.s.upsert_link("licensed_to", fid, holder, source="ARMS-LICENCE-SYN", record=f"LIC:{lic}:{who}")
            made += 1

        for firm in self.security:
            for _ in range(rng.randint(6, 14)):
                if made >= self.t["firearms"]:
                    break
                gun(firm["id"], firm["city"], rng.choice([makes[1], makes[1], makes[0], makes[3]]), "agency")
        pool = [p for p in self.free if self.people[p]["age"] >= 25 and self.people[p]["occupation"] in
                ("Farmer", "Shop owner", "Contractor", "Doctor", "Chartered accountant", "Retired", "Software engineer")]
        rng.shuffle(pool)
        for pid in pool:
            if made >= self.t["firearms"]:
                break
            p = self.people[pid]
            choice = makes[1] if p["occupation"] == "Farmer" else rng.choice([makes[0], makes[2], makes[0]])
            gun(pid, p["city"], choice, "person")
        self.stats["firearms"] = made

    def properties(self) -> None:
        rng = self.rng
        societies = ["Shanti", "Gokul", "Vrindavan", "Nandanvan", "Sai Darshan", "Green Valley", "Silver Oak", "Royal Palms", "Lakeview", "Sunshine",
                     "Kalpataru", "Ganga", "Panchsheel", "Anand", "Mahavir"]
        first = [p for p in self.free if p not in self.no_assets and self.people[p]["income"] >= 300_000 and self.people[p]["age"] >= 25]
        rng.shuffle(first)
        pool = first + [p for p in first if self.people[p]["income"] >= 1_200_000]  # a second property only for higher incomes
        made = 0
        for pid in pool:
            if made >= self.t["properties"]:
                break
            p = self.people[pid]
            inc, city, occ = p["income"], p["city"], p["occupation"]
            lat, lon, loc = self.point_in(city, 0.9)
            if occ == "Farmer":
                kind, val, area = "land", rng.randint(3, 40) * 100_000, rng.randint(5, 80) * 1000
                label = f"Gat No. {rng.randint(10, 999)}, {loc} outskirts, {city}"
            elif occ in ("Shop owner",) and rng.random() < 0.5:
                kind, val, area = "shop", rng.randint(15, 90) * 100_000, rng.randint(150, 600)
                label = f"Shop {rng.randint(1, 60)}, {rng.choice(societies)} Market, {loc}, {city}"
            elif occ == "Contractor" and rng.random() < 0.4:
                kind, val, area = "warehouse", rng.randint(40, 180) * 100_000, rng.randint(2000, 12000)
                label = f"Godown {rng.randint(1, 40)}, {loc} industrial area, {city}"
            elif inc >= 3_000_000 and rng.random() < 0.3:
                kind, val, area = "bungalow", rng.randint(150, 600) * 100_000, rng.randint(2000, 5000)
                label = f"Bungalow {rng.randint(1, 80)}, {rng.choice(societies)} Housing Society, {loc}, {city}"
            else:
                kind = "flat"
                val = int(min(max(inc * rng.uniform(2.5, 6.0), 1_800_000), 25_000_000) // 100_000 * 100_000)
                area = rng.randint(450, 1600)
                label = f"Flat {rng.randint(1, 22)}{rng.randint(1, 8):02d}, {rng.choice(societies)} CHS, {loc}, {city}"
            label = self.uniq(lambda: label if label not in self.used else f"{label} ({self.digits(3)})")
            reg = (self.now - timedelta(days=rng.randint(420, 6500))).date()
            doc = f"{FIR_UNIT[city]}{rng.randint(1, 9)}-{rng.randint(1000, 99999)}-{reg.year}"
            prop = self.s.upsert_object("Property", {"label": label, "kind": kind, "value": val, "registered_on": reg.isoformat(), "city": city,
                                                     "district_lgd": self.district(city), "area_sqft": area, "doc_no": doc,
                                                     "sub_registrar": f"Sub-Registrar {loc}, {city}",
                                                     "survey_no": f"{'Gat' if kind == 'land' else 'CTS'} {rng.randint(10, 4999)}/{rng.randint(1, 40)}"},
                                        source="IGR-SYN", record=f"DEED:{doc}", synthetic=True, lat=lat, lon=lon)
            self.s.upsert_link("owns", pid, prop, source="IGR-SYN", record=f"DEED:{doc}")
            made += 1
        self.stats["properties"] = made

    def wallets(self) -> None:
        rng = self.rng
        exchanges = ["CoinSutra Exchange (synthetic)", "BharatBit (synthetic)", "Rupaya Crypto (synthetic)", "Sahyog Digital Assets (synthetic)"]
        b32, b58 = "qpzry9x8gf2tvdw0s3jn54khce6mua7l", "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
        first = [p for p in self.free if 18 <= self.people[p]["age"] <= 65 and (self.people[p]["income"] >= 150_000 or self.people[p]["occupation"] == "Student")]
        rng.shuffle(first)
        pool = first + [p for p in first if self.people[p]["income"] >= 800_000]  # a second wallet, on another chain, for higher incomes
        made = 0
        for pid in pool[: self.t["wallets"]]:
            chain = rng.choices(["BTC", "ETH", "USDT (TRC-20)"], weights=[4, 4, 3])[0]
            if chain == "BTC":
                addr = self.uniq(lambda: "bc1q" + "".join(rng.choice(b32) for _ in range(38)))
            elif chain == "ETH":
                addr = self.uniq(lambda: "0x" + "".join(rng.choice("0123456789abcdef") for _ in range(40)))
            else:
                addr = self.uniq(lambda: "T" + "".join(rng.choice(b58) for _ in range(33)))
            ex = rng.choice(exchanges)
            wid = self.s.upsert_object("CryptoWallet", {"address": addr, "chain": chain, "exchange": ex, "kyc_status": "full KYC",
                                                        "opened_on": (self.now - timedelta(days=rng.randint(60, 2200))).date().isoformat()},
                                       source="EXCHANGE-SYN", record=f"KYC:{addr[-10:]}", obj_id=make_id("CryptoWallet", "addr", addr), synthetic=True)
            self.s.upsert_link("holds_account", pid, wid, source="EXCHANGE-SYN", record=f"KYC:{addr[-10:]}")
            made += 1
        self.stats["crypto_wallets"] = made

    # ------------------------------------------------------------------ FIRs and complaints
    TEMPLATES = [  # kind, sections, years, summary, (amount lo, hi) or None, accused named probability, weight
        ("fir", ["BNS 303(2) theft"], 3, "Mobile phone stolen from the complainant's pocket in a crowded bus near {loc}.", (8_000, 60_000), 0.0, 14),
        ("fir", ["BNS 303(2) theft"], 3, "Two-wheeler parked outside the complainant's residence at {loc} found missing in the morning.", (40_000, 120_000), 0.0, 10),
        ("fir", ["BNS 304 snatching"], 3, "Gold chain snatched by two persons on a motorcycle while the complainant was walking near {loc}.", (60_000, 250_000), 0.0, 7),
        ("fir", ["BNS 331(4) house-breaking by night", "BNS 305 theft in a dwelling"], 10, "House locked for a family function at {loc} was broken into; cash and ornaments taken.", (50_000, 600_000), 0.0, 8),
        ("fir", ["BNS 331(4) house-breaking by night", "BNS 305 theft in a building"], 10, "Shutter of a shop at {loc} forced open at night; cash from the counter taken.", (20_000, 300_000), 0.0, 6),
        ("complaint", ["BNS 318(4) cheating", "IT Act 66D"], 7, "Complainant lost the amount to an online part-time job scheme contacted over a messaging app.", (20_000, 600_000), 0.0, 12),
        ("complaint", ["BNS 318(4) cheating", "IT Act 66C"], 7, "Complainant's card was used for purchases after a caller posing as bank staff obtained an OTP.", (5_000, 150_000), 0.0, 8),
        ("fir", ["BNS 318(4) cheating", "BNS 316(2) breach of trust"], 7, "Complainant paid an advance for a plot near {loc}; the seller had no title and stopped responding.", (200_000, 2_500_000), 0.8, 5),
        ("fir", ["BNS 115(2) voluntarily causing hurt", "BNS 352 intentional insult"], 1, "Quarrel over parking near {loc}; the complainant was assaulted with fists.", None, 0.85, 7),
        ("fir", ["BNS 351(2) criminal intimidation"], 2, "Complainant threatened over the repayment of a hand loan near {loc}.", None, 0.85, 5),
        ("fir", ["BNS 281 rash driving", "BNS 125(a) endangering life"], 1, "Collision between a car and a two-wheeler at a {loc} junction; the rider was injured.", None, 0.4, 8),
        ("fir", ["BNS 324(4) mischief"], 2, "Windscreens of cars parked in a society at {loc} damaged at night.", (10_000, 90_000), 0.0, 4),
        ("complaint", ["Missing person report"], 0, "Complainant reported a family member missing from {loc}; later traced.", None, 0.0, 6),
    ]

    def incidents(self) -> None:
        rng = self.rng
        weights = [t[6] for t in self.TEMPLATES]
        by_city: dict[str, list[str]] = defaultdict(list)
        for pid in self.free:
            if pid not in self.pays_people and pid not in self.complained and pid not in self.on_record:
                by_city[self.people[pid]["city"]].append(pid)
        acct_out: dict[str, list[str]] = defaultdict(list)
        mine = {a: pid for pid in self.free for a in self.people[pid]["accounts"]}
        for r in self.s.query("SELECT from_acct, ts FROM txns WHERE amount>=5000 AND to_acct IS NOT NULL AND from_acct IS NOT NULL"):
            if r["from_acct"] in mine:
                acct_out[mine[r["from_acct"]]].append(r["ts"])
        complaints: Counter[str] = Counter()
        accused_pool = [p for p in self.free if p not in self.foreign and p not in self.complained and p not in self.on_record]
        rng.shuffle(accused_pool)
        seq: Counter[str] = Counter()
        stations: dict[tuple[str, str], tuple[str, str]] = {}
        counts = self.city_counts(self.t["incidents"], 12)
        made = 0
        for city, n in counts.items():
            for _ in range(n):
                kind, sections, years, text, amt, p_named, _ = rng.choices(self.TEMPLATES, weights=weights)[0]
                lat, lon, loc = self.point_in(city, 0.7)
                when = self.now - timedelta(days=rng.choice([rng.randint(2, 365), rng.randint(2, 1095)]), hours=rng.randint(0, 23), minutes=rng.randint(0, 59))
                cands = [c for c in by_city.get(city, []) if complaints[c] < 2] or [c for cs in by_city.values() for c in cs if complaints[c] < 2]
                complainant = None
                for c in rng.sample(cands, min(12, len(cands))):
                    lo, hi = self.iso(when - timedelta(days=1)), self.iso(when + timedelta(days=3))
                    if not any(lo <= ts <= hi for ts in acct_out.get(c, ())):
                        complainant = c
                        break
                if not complainant:
                    continue
                if (city, loc) not in stations:
                    stations[(city, loc)] = self.police_station(city, loc)
                ps_id, ps_name = stations[(city, loc)]
                st = CITIES[city][3]
                code = "".join(ch for ch in loc.upper() if ch.isalpha())[:3]
                key = f"{FIR_UNIT[city]}{code}{when.year}"
                while True:  # one register per station and year, shared by cities under one commissionerate
                    seq[key] += 1
                    fir = f"{st}/{FIR_UNIT[city]}/{code}/{when.year}/{100 + seq[key]:04d}"
                    if fir not in self.used:
                        self.used.add(fir)
                        break
                named = rng.random() < p_named
                if kind == "complaint" and sections[0] == "Missing person report":
                    status = "closed"
                elif named:
                    status = rng.choices(["chargesheeted", "under_investigation", "closed"], weights=[50, 40, 10])[0]
                else:
                    status = rng.choices(["under_investigation", "closed", "chargesheeted"], weights=[45, 35, 20])[0]
                props: dict[str, Any] = {"fir_no": fir, "kind": kind, "agency": "I4C" if kind == "complaint" and "IT Act" in " ".join(sections) else "State Police",
                                         "sections": sections, "summary": text.format(loc=loc), "occurred_at": self.iso(when),
                                         "district_lgd": self.district(city), "status": status, "place": f"{loc}, {city}", "police_station": ps_name}
                if years:
                    props["max_punishment_years"] = years
                if amt:
                    props["amount"] = rng.randint(amt[0] // 1000, amt[1] // 1000) * 1000
                if status == "chargesheeted":
                    cs = when + timedelta(days=rng.randint(30, 150))
                    if cs < self.now:
                        props["chargesheeted_on"] = cs.date().isoformat()
                    else:
                        props["status"] = "under_investigation"
                iid = self.s.upsert_object("Incident", props, source="CCTNS-SYN" if props["agency"] == "State Police" else "I4C-SYN", record=fir,
                                           synthetic=True, lat=lat, lon=lon)
                self.s.upsert_link("reported_at", iid, ps_id, source="CCTNS-SYN", record=fir)
                self.s.upsert_link("complainant_in", complainant, iid, source="CCTNS-SYN", record=f"{fir}:complainant")
                complaints[complainant] += 1
                if named:
                    for a in accused_pool[:40]:
                        if a != complainant and a not in self.family.get(complainant, set()) and a not in self.new_accused and complaints[a] == 0:
                            self.s.upsert_link("accused_in", a, iid, source="CCTNS-SYN", record=f"{fir}:accused")
                            self.new_accused.add(a)
                            accused_pool.remove(a)
                            break
                made += 1
        self.stats["firs_added"] = made
        self.stats["firs_named_accused"] = len(self.new_accused)
        self.stats["police_stations_added"] = len(stations)
        # coordinates for FIRs already on record: their district's city, or the district's centre
        centre = {}
        for r in self.s.query("SELECT props, lat, lon FROM objects WHERE type='AdminUnit' AND lat IS NOT NULL"):
            pr = json.loads(r["props"])
            if pr.get("level") == "district":
                centre[pr.get("lgd_code")] = (r["lat"], r["lon"])
        city_of = {d: c for c, d in self.district_of.items()}
        fixed = []
        for r in self.s.query("SELECT id, props FROM objects WHERE type='Incident' AND lat IS NULL"):
            d = json.loads(r["props"]).get("district_lgd")
            if d in city_of:
                lat, lon, _ = self.point_in(city_of[d], 0.8)
            elif d in centre:
                lat, lon = self.jitter(*centre[d], 3.0)
            else:
                continue
            fixed.append((lat, lon, r["id"]))
        self.s.executemany("UPDATE objects SET lat=?, lon=? WHERE id=?", fixed)
        self.stats["firs_located"] = len(fixed)

    # ------------------------------------------------------------------ tenders and journeys
    def tenders(self) -> None:
        rng = self.rng
        if len(self.firms) < 8:
            return
        depts: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
        for city in CITIES:
            for name, code in ((f"Public Works Department, {city} Division", "PWD"), (f"{city} Municipal Corporation", "MC"),
                               (f"District Hospital, {city}", "DH")):
                oid = self.s.upsert_object("Organisation", {"name": name, "kind": "department", "city": city, "district_lgd": self.district(city),
                                                           "country": "IN"}, source="CPPP-SYN", record=f"DEPT:{name}", synthetic=True)
                depts[city].append((oid, name, code))
        works = ["Resurfacing of {loc} road, {km} km", "Construction of a storm-water drain at {loc}", "Repairs to the ward office at {loc}",
                 "Footpath and kerb work on {loc} Main Road", "Construction of a community hall at {loc}"]
        goods = ["Supply of {n} hospital beds", "Supply of LED street-light fittings ({n} nos.)", "Supply of school desks ({n} nos.)",
                 "Supply of medicines and consumables", "Supply of office computers ({n} nos.)"]
        services = ["Housekeeping services at {loc} ward office", "Security services at the {loc} hospital", "Hiring of {n} vehicles for field staff",
                    "Annual maintenance of water pumps at {loc}"]
        by_state: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for f in self.firms + self.security:
            f["ip"] = self.uniq(lambda: f"{rng.choice([49, 103, 106, 117, 122, 157, 182])}.{rng.randint(1, 254)}.{rng.randint(1, 254)}.{rng.randint(1, 254)}")
            by_state[f["state"]].append(f)
        bids_rows = []
        made = 0
        cities = list(CITIES)
        target = min(self.t["tenders"], len(self.firms) * 3)
        while made < target:
            city = rng.choices(cities, weights=[CITY_WEIGHTS[c] for c in cities])[0]
            firms = by_state.get(CITIES[city][3]) or self.firms
            if len(firms) < 3:
                firms = self.firms
            dept, dname, dcode = rng.choice(depts[city])
            cat = rng.choices(["Works", "Goods", "Services"], weights=[50, 30, 20])[0]
            loc = rng.choice(LOCALITIES[city])[0]
            title = rng.choice({"Works": works, "Goods": goods, "Services": services}[cat]).format(loc=loc, km=round(rng.uniform(0.6, 6.5), 1), n=rng.randint(20, 400))
            est = rng.randint(5, 1200) * 100_000
            pub = (self.now - timedelta(days=rng.randint(20, 720))).date()
            close = pub + timedelta(days=21)
            made += 1
            tid = f"{pub.year}_{dcode}{FIR_UNIT[city]}_{made:06d}_1"
            bidders = rng.sample(firms, min(len(firms), rng.randint(3, 6)))
            l1 = est * rng.uniform(0.70, 0.92)
            amounts, cur = [l1], l1
            for _ in bidders[1:]:
                cur *= 1 + rng.uniform(0.08, 0.20)  # dispersed: well clear of the 5% bid-rigging screen
                amounts.append(cur)
            closed = close < self.now.date()
            props = {"tender_id": tid, "title": title, "department": dname, "category": cat, "estimate": est, "published_on": pub.isoformat(),
                     "district_lgd": self.district(city), "closing_on": close.isoformat(), "status": "awarded" if closed else "bids under evaluation"}
            if closed:
                props["awarded_amount"] = round(l1, -3)
            t = self.s.upsert_object("Tender", props, source="CPPP-SYN", record=f"TENDER:{tid}", synthetic=True)
            self.s.upsert_link("issued_by", t, dept, source="CPPP-SYN", record=f"TENDER:{tid}")
            for f, amt in zip(bidders, amounts):
                sub = datetime.combine(pub + timedelta(days=rng.randint(3, 20)), datetime.min.time(), tzinfo=timezone.utc).replace(hour=rng.randint(9, 19), minute=rng.randint(0, 59))
                bids_rows.append((f"BIDE{len(bids_rows):07d}", t, f["id"], round(amt, -3), sub.isoformat(timespec="minutes"), f["ip"], "CPPP-SYN"))
                self.s.upsert_link("bid_on", f["id"], t, source="CPPP-SYN", record=f"BID:{tid}:{f['id']}")
            if closed:
                self.s.upsert_link("awarded_to", t, bidders[0]["id"], source="CPPP-SYN", record=f"AWARD:{tid}")
        self.s.executemany("INSERT INTO bids(id,tender_id,bidder_id,amount,submitted_at,submit_ip,source) VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING", bids_rows)
        self.stats["tenders"] = made
        self.stats["bids"] = len(bids_rows)

    def journeys(self) -> None:
        """Domestic journeys by rail, bus and air; no two travellers share a route on the same day (that would read as travelling together)."""
        rng = self.rng
        taken = {(r["ts"][:10], r["from_city"], r["to_city"]) for r in self.s.query("SELECT ts, from_city, to_city FROM travel")}
        pool = [p for p in self.free if self.people[p]["age"] >= 18]
        rng.shuffle(pool)
        rows = []
        n = 0
        for pid in pool:
            if len(rows) >= self.t["journeys"]:
                break
            p = self.people[pid]
            hub = HUB.get(p["city"], p["city"])
            dests = sorted({b for (a, b) in self.plazas if a == hub})
            air = p["income"] >= 600_000 and AIRPORT.get(p["city"])
            if air:
                dests = sorted(set(dests) | {c for c in ("New Delhi", "Bengaluru", "Hyderabad", "Chennai", "Kolkata", "Panaji", "Jaipur") if c != hub})
            if not dests:
                continue
            for _ in range(rng.randint(1, 2)):
                to = rng.choice(dests)
                mode = "air" if air and km(*CITIES[hub][1:3], *CITIES[to][1:3]) > 500 else rng.choice(["rail", "rail", "bus"])
                for _try in range(20):
                    out = (self.now - timedelta(days=rng.randint(5, 360))).replace(hour=rng.randint(5, 22), minute=rng.randint(0, 59))
                    back = out + timedelta(days=rng.randint(2, 9), hours=rng.randint(-4, 4))
                    k1, k2 = (out.date().isoformat(), p["city"], to), (back.date().isoformat(), to, p["city"])
                    if k1 not in taken and k2 not in taken and back < self.now:
                        break
                else:
                    continue
                taken |= {k1, k2}
                pnr = self.letters(6) if mode == "air" else (self.digits(10) if mode == "rail" else f"BUS{self.digits(8)}")
                for t, frm, dst in ((out, p["city"], to), (back, to, p["city"])):
                    n += 1
                    rows.append((f"TRE{n:07d}", pid, self.iso(t), mode, pnr, frm, "IN", CITIES[frm][1], CITIES[frm][2], dst, "IN", CITIES[dst][1], CITIES[dst][2],
                                 "PNR-SYN" if mode == "air" else ("IRCTC-SYN" if mode == "rail" else "BUS-OPERATOR-SYN")))
        self.s.executemany("INSERT INTO travel VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING", rows)
        self.stats["journeys"] = len(rows)

    # ------------------------------------------------------------------ run
    def run(self, *, force: bool = False) -> dict[str, Any]:
        done = self.s.get_meta("enrichment")
        if done and not force:
            return {"skipped": True, **done}
        with self.s.tx():
            self.load()
            self.towers()
            self.checkpoints()
            self.devices()
            self.vehicles()
            self.businesses()
            self.firearms()
            self.properties()
            self.wallets()
            self.incidents()
            self.tenders()
            self.journeys()
            self.reads()
            self.locate_calls()
        out = dict(self.stats) | {"at": self.now.isoformat(timespec="minutes")}
        self.s.set_meta("enrichment", out)
        return out


def enrich(store: Store, *, seed: int = 29, targets: dict[str, int] | None = None, force: bool = False, log: Callable = print) -> dict[str, Any]:
    return Enricher(store, seed=seed, targets=targets, log=log).run(force=force)

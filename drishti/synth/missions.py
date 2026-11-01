"""Planted networks for every agency mission track, each paired with benign look-alikes.

The pattern engine (drishti/patterns) must find the planted networks from the records alone
and must stay silent on the look-alikes: a family sharing a handset, a call centre, an old
business group with common directors, a senior officer whose home loan explains a flat, a
commuter crossing the same toll plaza every day, a person who changed their number. Ground
truth goes to meta `synthetic_truth.missions`; detectors never read it (tests check this).

Missions run after the original world is built and use their own random stream, so the
original operations (MIRAGE, MULE, SUNRISE, KESTREL, COASTLINE) are unchanged.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from ..store import make_id

if TYPE_CHECKING:  # pragma: no cover
    from .world import P, World

# Real Maharashtra toll plazas and ANPR points (approximate coordinates).
PLAZAS: dict[str, tuple[float, float, str]] = {
    "Vashi Toll Plaza": (19.072, 73.004, "toll"),
    "Mulund Check Naka": (19.172, 72.958, "toll"),
    "Kharpada Toll Plaza": (18.780, 73.100, "toll"),
    "Khalapur Toll (Expressway)": (18.832, 73.292, "toll"),
    "Talegaon Toll (Expressway)": (18.736, 73.672, "toll"),
    "Khed Shivapur Toll": (18.330, 73.866, "toll"),
    "Padgha Toll (Mumbai-Nashik)": (19.362, 73.178, "toll"),
    "Ghoti Toll (Mumbai-Nashik)": (19.712, 73.630, "toll"),
    "Bhiwandi Bypass ANPR": (19.283, 73.071, "anpr"),
    "Nashik Phata ANPR": (19.982, 73.789, "anpr"),
}
COMMUTE = {"Mumbai": "Mulund Check Naka", "Andheri": "Mulund Check Naka", "Thane": "Mulund Check Naka", "Navi Mumbai": "Vashi Toll Plaza",
           "Panvel": "Kharpada Toll Plaza", "Pune": "Talegaon Toll (Expressway)", "Nashik": "Ghoti Toll (Mumbai-Nashik)",
           "Bhiwandi": "Padgha Toll (Mumbai-Nashik)"}


class Missions:
    def __init__(self, w: World, seed: int = 2026):
        self.w = w
        self.s = w.s
        self.rng = random.Random(seed)
        self.truth: dict[str, Any] = {}
        self.reads: list[tuple] = []
        self.procs: list[tuple] = []
        self.bid_rows: list[tuple] = []

    # ------------------------------------------------------------------ helpers
    def person(self, **kw: Any) -> P:
        w = self.w
        opened = kw.pop("opened", None)
        p = w.make_person(**kw)
        w.home(p)
        w.phone(p)
        p.accounts.append(w.account(p.oid, p.name, city=p.city, opened_days_ago=opened))
        return p

    def read(self, vehicle: str, t: datetime, plaza: str, source: str = "NETC-FASTAG-SYN") -> None:
        lat, lon, kind = PLAZAS[plaza]
        self.reads.append((f"RD{len(self.reads):06d}", vehicle, t.isoformat(timespec="minutes"), plaza, lat, lon,
                           "VAHAN-ANPR-SYN" if kind == "anpr" else source, kind))

    def background(self, n: int, *, need_accounts: bool = True, exclude: set[str] | None = None) -> list[P]:
        pool = [p for p in self.w.people if p.role == "background" and (p.accounts or not need_accounts) and p.phones
                and p.oid not in (exclude or set())]
        return self.rng.sample(pool, n)

    def device(self, model: str, key: str) -> str:
        return self.s.upsert_object("Device", {"imei": "35" + self.w.digits(13), "model": model}, source="TSP-SYN",
                                    record=f"IMEI:{key}", synthetic=True)

    def sim_in(self, phone_oid: str, dev: str, key: str, **props: Any) -> None:
        self.s.upsert_link("sim_in_device", phone_oid, dev, source="TSP-CDR-SYN", record=f"IMEI:{key}", props=props or None)

    # ------------------------------------------------------------------ money: smurfing ring
    def anthill(self) -> None:
        """Nine smurfs deposit cash just under the Rs 50,000 PAN limit, two or three times each (under any
        per-account rule), and pass it on within hours to one collector, a third of them through a layer."""
        w, rng = self.w, self.rng
        collector = self.person(city="Bhiwandi", occupation="Commission agent", income=260_000, role="anthill_collector")
        layer = self.person(city="Thane", occupation="Labourer", income=140_000, role="anthill_layer")
        smurfs = [self.person(city=rng.choice(["Bhiwandi", "Thane", "Navi Mumbai", "Mumbai"]), occupation=rng.choice(["Student", "Labourer", "Driver"]),
                              income=rng.choice([0, 120_000, 160_000]), age=(19, 30), role="anthill_smurf") for _ in range(9)]
        jeweller = w.org("Rajmudra Gold Palace (synthetic)", "merchant", "Mumbai", capital=2_000_000)
        j_acct = w.account(jeweller, "Rajmudra Gold Palace", kind="current", city="Mumbai")
        for wave in (140, 70):
            for i, sm in enumerate(smurfs):
                for _ in range(rng.choice([2, 2, 3])):
                    t = w.ts(wave - rng.uniform(0, 18), rng.randint(10, 16))
                    amt = rng.choice([46_500, 47_900, 48_200, 48_800, 49_400, 49_900]) + rng.randint(0, 90)
                    w.txn(t, None, sm.accounts[0], amt, "CASH", "CASH DEPOSIT")
                    fwd = t + timedelta(hours=rng.uniform(3, 28))
                    if i % 3 == 0:
                        w.txn(fwd, sm.accounts[0], layer.accounts[0], round(amt * rng.uniform(0.96, 0.99), -1), "IMPS", rng.choice(["TRF", "SELF", "HELP"]))
                        w.txn(fwd + timedelta(hours=rng.uniform(2, 20)), layer.accounts[0], collector.accounts[0], round(amt * 0.95, -1), "IMPS", "TRF")
                    else:
                        w.txn(fwd, sm.accounts[0], collector.accounts[0], round(amt * rng.uniform(0.96, 0.995), -1), "IMPS", rng.choice(["TRF", "FAMILY SUPPORT", "RENT"]))
            for k in range(3):
                w.txn(w.ts(wave - 20 - k * 3, 13), collector.accounts[0], j_acct, rng.randint(25, 40) * 10_000, "RTGS", "GOLD PURCHASE")
        # benign look-alike: a self-help group whose members save cash near the limit in their own accounts and keep it
        savers = self.background(6)
        for p in savers:
            for _ in range(3):
                w.txn(w.ts(rng.uniform(30, 300), rng.randint(10, 15)), None, p.accounts[0], rng.choice([48_000, 49_000, 49_500]), "CASH", "CASH DEPOSIT")
        self.truth["SMURFING_RING"] = {"positives": [[collector.oid, layer.oid, *[s.oid for s in smurfs], collector.accounts[0]]],
                                       "benign": [[p.oid for p in savers]]}

    # ------------------------------------------------------------------ money: dormant accounts woken together
    def sleepers(self) -> None:
        w, rng = self.w, self.rng
        owners = []
        for _ in range(7):
            p = w.make_person(city=rng.choice(["Kolhapur", "Solapur", "Nashik", "Aurangabad"]), occupation=rng.choice(["Farmer", "Labourer", "Homemaker"]),
                              income=rng.choice([0, 90_000, 140_000]), role="sleeper_owner")
            w.home(p)
            w.phone(p)
            p.accounts.append(w.account(p.oid, p.name, city=p.city, opened_days_ago=rng.randint(1500, 3000)))
            for _ in range(rng.randint(2, 4)):
                w.txn(w.ts(rng.uniform(330, 356), 11), p.accounts[0], None, rng.choice([1500, 2000, 3000]), "ATM", "ATM WITHDRAWAL")
            owners.append(p)
        collectors = [self.person(city="Navi Mumbai", occupation="Event manager", income=420_000, role="sleeper_collector", opened=280),
                      self.person(city="Navi Mumbai", occupation="Mobile shop owner", income=380_000, role="sleeper_collector", opened=260)]
        payers = self.background(26)
        complaints = []
        for i, p in enumerate(owners):
            for k in range(rng.randint(3, 5)):
                payer = payers[(i * 5 + k) % len(payers)]
                t = w.ts(52 - rng.uniform(0, 9), rng.randint(10, 19))
                amt = rng.choice([35_000, 60_000, 85_000, 1_10_000, 1_45_000])
                w.txn(t, payer.accounts[0], p.accounts[0], amt, "IMPS", "INVESTMENT")
                w.txn(t + timedelta(hours=rng.uniform(1, 20)), p.accounts[0], collectors[i % 2].accounts[0], round(amt * 0.9, -1), "IMPS", "TRF")
                if k == 0 and i < 6:
                    inc = w.incident(f"I4C/{t.year}/{57000 + i}", "complaint", "I4C", payer.city, ["BNS 318(4)", "IT Act 66D"],
                                     f"Lured into a fake share-trading app; Rs {amt:,} paid to an account given by the 'advisor'.", t, amount=amt, source="I4C-SYN")
                    self.s.upsert_link("complainant_in", payer.oid, inc, source="I4C-SYN", record=f"NCRP:S{i}")
                    self.s.upsert_link("mentions", inc, p.accounts[0], source="I4C-SYN", record=f"NCRP:S{i}")
                    complaints.append(inc)
        for c in collectors:
            w.txn(w.ts(40, 12), c.accounts[0], None, 9_50_000, "CASH", "SELF")
        # benign: two dormant accounts woken by unrelated, explainable credits
        insurer = w.org("Sahyadri Life Insurance (synthetic)", "company", "Pune", incorporated_days_ago=8000, capital=500_000_000)
        ins_acct = w.account(insurer, "Sahyadri Life Insurance", kind="current", city="Pune")
        benign = []
        for k, (payer_acct, amt, note) in enumerate(((ins_acct, 4_20_000, "POLICY MATURITY"), (None, 18_00_000, "PROPERTY SALE"))):
            p = w.make_person(city=rng.choice(["Kolhapur", "Solapur"]), occupation="Retired", income=180_000, role="sleeper_benign")
            w.home(p)
            w.phone(p)
            p.accounts.append(w.account(p.oid, p.name, city=p.city, opened_days_ago=2500))
            w.txn(w.ts(345, 11), p.accounts[0], None, 2000, "ATM", "ATM WITHDRAWAL")
            if payer_acct is None:
                buyer = self.background(1)[0]
                payer_acct = buyer.accounts[0]
            w.txn(w.ts(48 + k * 2, 12), payer_acct, p.accounts[0], amt, "NEFT", note)
            for _ in range(4):
                w.txn(w.ts(rng.uniform(5, 45), 13), p.accounts[0], rng.choice(w.merchant_accts), rng.randint(5, 30) * 1000, "UPI", "UPI/shopping")
            benign.append(p.oid)
        self.truth["DORMANT_WAVE"] = {"positives": [[*[p.oid for p in owners], *[p.accounts[0] for p in owners], *[c.oid for c in collectors]]],
                                      "benign": [benign]}
        self.sleeper_collectors = [c.accounts[0] for c in collectors] + [c.oid for c in collectors]
        self.truth["sleeper_complaints"] = complaints

    # ------------------------------------------------------------------ money / terror: hawala without tell-tale narrations
    def orbit(self) -> None:
        w, rng = self.w, self.rng
        prop = self.person(city="Mumbai", occupation="Travel agent", income=650_000, role="orbit_proprietor")
        firm = w.org("Orbit Tours & Forex (synthetic)", "merchant", "Mumbai", capital=500_000, gst_turnover=1_200_000,
                     address="Shop 4, Crawford Market Lane, Mumbai")
        self.s.upsert_link("controls", prop.oid, firm, source="MCA-SYN", record="PROP:orbit")
        acct = w.account(firm, "Orbit Tours & Forex", kind="current", city="Mumbai", opened_days_ago=700, signatory=prop)
        gulf = w.org("Gulf Pearl General Trading (synthetic)", "foreign_company", "Dubai", country="AE", source="FIU-EGMONT-SYN")
        gulf_acct = w.account(gulf, "Gulf Pearl General Trading", kind="current", city="Dubai", foreign=True)
        payers = self.background(32)
        neutral = ["IMPS", "PAYMENT", "TRANSFER", "NA", "SETTLEMENT", "SELF"]
        for day in range(120, 5, -3):
            batch = rng.sample(payers, rng.randint(3, 6))
            total = 0.0
            for p in batch:
                amt = rng.choice([25_000, 50_000, 75_000, 1_00_000, 1_50_000, 2_00_000])
                w.txn(w.ts(day, rng.randint(10, 18)), p.accounts[0], acct, amt, rng.choice(["IMPS", "NEFT", "UPI"]), rng.choice(neutral))
                total += amt
            w.txn(w.ts(day - 1, 11), acct, None, round(total * rng.uniform(0.78, 0.9), -3), "CASH", rng.choice(neutral))
            if day % 15 == 0:
                w.txn(w.ts(day - 2, 15), acct, gulf_acct, round(total * 1.5, -3), "SWIFT", "SERVICES", country="AE")
        # benign: a real charity collects many small donations and spends them slowly on suppliers and staff
        trust = w.org("Asha Health Foundation (synthetic)", "trust", "Pune", incorporated_days_ago=3600, capital=1_000_000, gst_turnover=0)
        t_acct = w.account(trust, "Asha Health Foundation", kind="current", city="Pune", opened_days_ago=3500)
        for p in self.background(60, exclude={x.oid for x in payers}):
            for _ in range(rng.randint(1, 3)):
                w.txn(w.ts(rng.uniform(5, 350), rng.randint(8, 21)), p.accounts[0], t_acct, rng.choice([500, 1000, 2000, 5000]), "UPI", rng.choice(neutral))
        suppliers = [w.account(w.org(n, "company", "Pune", capital=2_000_000), n, kind="current", city="Pune")
                     for n in ("Medisure Supplies (synthetic)", "Clinic Linen Co (synthetic)", "Pune Diagnostics (synthetic)")]
        for m in range(12):
            for sup in suppliers:
                w.txn(w.ts(30 * m + 25, 12), t_acct, sup, rng.randint(15, 40) * 1000, "NEFT", "INVOICE")
        self.truth["HAWALA_CORRIDOR"] = {"positives": [[firm, acct, prop.oid], [self.w.truth["operations"]["MIRAGE"]["hawala"]]],
                                         "benign": [[trust, t_acct]]}

    # ------------------------------------------------------------------ money: benign business group (shell look-alike)
    def deccan_group(self) -> None:
        w, rng = self.w, self.rng
        promoters = [w.make_person(city="Pune", occupation="Company director", income=rng.randint(40, 90) * 100_000, rich=True, role="deccan_director") for _ in range(2)]
        for p in promoters:
            w.home(p)
            w.phone(p)
            p.accounts.append(w.account(p.oid, p.name, city="Pune"))
        group, accts = [], []
        for nm in ("Deccan Agro Industries Ltd (synthetic)", "Deccan Cold Chain Pvt Ltd (synthetic)", "Deccan Seeds Pvt Ltd (synthetic)", "Deccan Agri Logistics Pvt Ltd (synthetic)"):
            o = w.org(nm, "company", "Pune", incorporated_days_ago=rng.randint(4000, 7000), capital=rng.randint(5, 20) * 10_000_000,
                      gst_turnover=rng.randint(20, 60) * 10_000_000, address="Deccan House, Senapati Bapat Road, Pune")
            for p in promoters:
                self.s.upsert_link("director_of", p.oid, o, source="MCA-SYN", record=f"DIN:{p.oid}:{nm}")
            group.append(o)
            accts.append(w.account(o, nm, kind="current", city="Pune", opened_days_ago=3000))
        customers = self.background(20)
        for m in range(12):
            for a in accts:
                for c in rng.sample(customers, 3):
                    w.txn(w.ts(30 * m + rng.uniform(0, 25), 12), c.accounts[0], a, rng.randint(2, 8) * 100_000, "NEFT", "INVOICE")
            for a in accts[1:]:  # the holding company funds its subsidiaries; nothing flows back
                w.txn(w.ts(30 * m + 10, 12), accts[0], a, rng.randint(10, 30) * 100_000, "RTGS", "INTER-CORPORATE DEPOSIT")
        ops = self.w.truth["operations"]
        self.truth["SHELL_NETWORK"] = {"positives": [list(ops["MIRAGE"]["shells"]), [*ops["SUNRISE"]["related"]]], "benign": [group]}

    # ------------------------------------------------------------------ telecom: SIM-box gateways
    def dialtone(self) -> None:
        w, rng = self.w, self.rng
        tower = w.tower("Pune", "Hadapsar industrial estate", 0.03, 0.05)
        g1, g2 = self.device("GSM gateway, 16-port", "simbox-1"), self.device("GSM gateway, 8-port", "simbox-2")
        targets = [p.phones[0] for p in self.w.people if p.phones and p.role == "background"]
        sims = []
        for i in range(14):
            num, ph = w.phone(None, subscriber=f"Prepaid subscriber {i + 1} (KYC unverified)")
            sims.append(ph)
            self.sim_in(ph, g1 if i < 9 else g2, f"simbox-{i}")
            if i in (7, 8, 9):  # SIMs moved between the two gateways
                self.sim_in(ph, g2 if i < 9 else g1, f"simbox-{i}-b")
            start = 125 - i * 7
            for d in range(10):
                for _ in range(rng.randint(18, 26)):
                    w.call(w.ts(start - d, rng.randint(8, 21)), num, rng.choice(targets), tower=tower, dur=rng.randint(15, 110))
            if rng.random() < 0.3:
                w.call(w.ts(start - 3, 12), rng.choice(targets), num, dur=20)  # the caller's tower is not the gateway's
        # benign: a telemarketing call centre - one handset per SIM, real incoming traffic, longer calls
        cc = w.org("Prakash Telemarketing (synthetic)", "call_centre", "Pune", capital=1_500_000)
        cc_tower = w.tower("Pune", "Baner IT park", 0.05, -0.06)
        cc_phones = []
        for i in range(6):
            num, ph = w.phone(None, org=cc, subscriber="Prakash Telemarketing (synthetic)")
            self.sim_in(ph, self.device("Android handset", f"cc-{i}"), f"cc-{i}")
            cc_phones.append(ph)
            for d in range(20):
                for _ in range(rng.randint(14, 20)):
                    w.call(w.ts(60 - d, rng.randint(9, 19)), num, rng.choice(targets), tower=cc_tower, dur=rng.randint(60, 420))
                for _ in range(rng.randint(4, 8)):
                    w.call(w.ts(60 - d, rng.randint(9, 19)), rng.choice(targets), num, dur=rng.randint(60, 300))
        self.truth["SIM_BOX"] = {"positives": [[g1, g2, *sims]], "benign": [[cc, *cc_phones]]}

    # ------------------------------------------------------------------ organised crime: the Ironside gang
    def ironside(self) -> None:
        """A Pune gang with a ten-year record: four charge-sheeted FIRs shared among five members, a
        country-made pistol tied by ballistics to an unsolved murder, shared handsets, and a leader who
        switched to a new SIM the day his number appeared in an FIR."""
        w, rng = self.w, self.rng
        leader = w.make_person(city="Pune", gender="M", occupation="Real estate broker", income=600_000, age=(34, 44), role="ironside_leader")
        members = [w.make_person(city="Pune", gender="M", occupation=rng.choice(["Driver", "Gym trainer", "Shop owner", "Labourer"]),
                                 income=rng.randint(150_000, 350_000), age=(22, 38), role="ironside_member") for _ in range(4)]
        gang = [leader, *members]
        for p in gang:
            w.home(p)
            w.phone(p)
            p.accounts.append(w.account(p.oid, p.name, city="Pune"))
        ps = w.police_station("Pune", "Crime Branch")
        self.s.upsert_object("Person", {"name": leader.name, "history_sheet_no": "HS/PUNE/CB/2019/114"}, source="CCTNS-SYN",
                             record="HS-114", obj_id=leader.oid, synthetic=True)
        self.s.upsert_link("history_sheeted_at", leader.oid, ps, source="CCTNS-SYN", record="HS-114")
        adda = w.tower("Pune", "Kondhwa adda (gang meeting place)", -0.04, 0.02)
        for _ in range(160):  # frequent meetings at their usual place: an anchor, not a recce
            a, b = rng.sample(gang, 2)
            w.call(w.ts(rng.uniform(80, 360), rng.randint(11, 23)), a.phones[0], b.phones[0], tower=adda, dur=rng.randint(30, 300))
        family = [w.make_person(city="Pune", occupation="Homemaker", income=0, role="ironside_family") for _ in range(3)]
        for f in family:
            w.home(f)
            w.phone(f)
            self.s.upsert_link("relative_of", leader.oid, f.oid, source="PDS-SYN", record=f"RC:{f.oid}")
        others = self.background(4)
        contacts = [*members, *family, *others[:2]]
        for c in contacts:
            for _ in range(rng.randint(6, 12)):
                w.call(w.ts(rng.uniform(80, 340), rng.randint(9, 22)), leader.phones[0], c.phones[0], dur=rng.randint(30, 400))
        # FIRs over ten years; two via the CCTNS record spelling (entity resolution must link them)
        specs = [(2200, ["BNS 308(2) extortion"], [0, 1, 2], "Shopkeepers in Kondhwa threatened and made to pay weekly 'protection'.", 7, True),
                 (1500, ["BNS 309(4) robbery"], [0, 2, 3], "Cash van employee robbed at knife-point near Katraj.", 10, True),
                 (700, ["BNS 140(2) kidnapping for ransom", "Arms Act 1959 s.25"], [0, 1, 3, 4], "Builder's son abducted; released after ransom; country-made pistol recovered.", 14, False),
                 (75, ["BNS 308(5) extortion", "BNS 109 attempt to murder", "Arms Act 1959 s.27"], [0, 1, 4], "Shots fired at a hotel owner who refused to pay; prime accused absconding.", 14, False)]
        incidents = []
        for k, (days, sec, idx, summ, years, via_raw) in enumerate(specs):
            when = w.ts(days, 22)
            status = "chargesheeted" if days > 300 else "under_investigation"
            inc = w.incident(f"MH/PUNE/CB/{when.year}/{311 + k}", "fir", "State Police", "Pune", sec, summ, when, status=status)
            props = {"fir_no": f"MH/PUNE/CB/{when.year}/{311 + k}", "max_punishment_years": years}
            if status == "chargesheeted":
                props["chargesheeted_on"] = (when + timedelta(days=80)).date().isoformat()
            self.s.upsert_object("Incident", props, source="CCTNS-SYN", record=props["fir_no"], obj_id=inc, synthetic=True)
            for i in idx:
                who = gang[i]
                rec = w.raw_record(who, "CCTNS-SYN", f"IRON{k}#{i}") if via_raw else who.oid
                self.s.upsert_link("accused_in", rec, inc, source="CCTNS-SYN", record=f"IRON-{k}")
            incidents.append(inc)
        self.s.upsert_link("mentions", incidents[3], leader.phone_oids[0], source="CCTNS-SYN", record="IRON-3")
        # the weapon: recovered in FIR 3; FSL matched it to cartridges from an unsolved murder
        murder = w.incident(f"MH/PUNE/HDP/{w.ts(400).year}/0907", "fir", "State Police", "Pune", ["BNS 103(1) murder"],
                            "Body of a scrap dealer found near Hadapsar; two 7.65 mm cartridge cases recovered; accused unknown.", w.ts(400, 23))
        pistol = self.s.upsert_object("Firearm", {"serial_no": "CM-NO-SERIAL-PUNE-0331", "kind": "country_made", "calibre": "7.65 mm",
                                                  "status": "recovered", "ballistic_ref": "FSL-PUNE-BAL-2291"}, source="FSL-SYN", record="FIREARM:pistol", synthetic=True)
        self.s.upsert_link("recovered_in", pistol, incidents[2], source="CCTNS-SYN", record="IRON-2")
        cartridges = self.s.upsert_object("Firearm", {"serial_no": "UNRECOVERED-FSL-HDP-0907", "kind": "other", "calibre": "7.65 mm",
                                                      "status": "unlicensed", "ballistic_ref": "FSL-PUNE-BAL-2291"}, source="FSL-SYN", record="FIREARM:cartridges", synthetic=True)
        self.s.upsert_link("used_in", cartridges, murder, source="FSL-SYN", record="FSL-HDP-0907")
        licensed = self.s.upsert_object("Firearm", {"serial_no": "NPB-32-118842", "kind": "revolver", "calibre": ".32", "status": "licensed",
                                                    "licence_no": "ARMS/PUNE/2016/8841"}, source="ARMS-LICENCE-SYN", record="FIREARM:licensed", synthetic=True)
        self.s.upsert_link("licensed_to", licensed, others[3].oid, source="ARMS-LICENCE-SYN", record="LIC-8841")
        # shared handsets: two phones rotate five SIMs among four members
        h1, h2 = self.device("Feature phone", "iron-1"), self.device("Feature phone", "iron-2")
        for i, m in enumerate(members):
            self.sim_in(m.phone_oids[0], h1 if i < 2 else h2, f"iron-{i}")
        self.sim_in(members[1].phone_oids[0], h2, "iron-1b")
        # the leader's new SIM: old number silent from the day of FIR 4, new prepaid number calls the same people
        new_num, new_ph = w.phone(None, subscriber="Sunil K (prepaid, address unverified)")
        for c in contacts[:7]:
            for _ in range(rng.randint(3, 7)):
                w.call(w.ts(rng.uniform(5, 73), rng.randint(9, 22)), new_num, c.phones[0], dur=rng.randint(30, 300))
        # benign: two neighbours accused once together in a quarrel; never again
        quarrel = self.background(2)
        q = w.incident(f"MH/PUNE/CTY/{w.ts(200).year}/7781", "fir", "State Police", "Pune", ["BNS 115(2)", "BNS 352"],
                       "Neighbours quarrelled over a water tanker; complainant slapped.", w.ts(200, 19), status="chargesheeted")
        for p in quarrel:
            self.s.upsert_link("accused_in", p.oid, q, source="CCTNS-SYN", record="Q-7781")
        # benign: a family of three sharing one handset; a handset resold between strangers
        fam = self.background(1)[0]
        kin = [w.make_person(city=fam.city, surname=(fam.surname, fam.surname_native), community=fam.community) for _ in range(2)]
        for k_ in kin:
            w.home(k_, share_with=fam)
            w.phone(k_)
            self.s.upsert_link("relative_of", fam.oid, k_.oid, source="PDS-SYN", record=f"RC:{k_.oid}")
        home_dev = self.device("Android handset", "family-shared")
        for p in [fam, *kin]:
            self.sim_in(p.phone_oids[0], home_dev, f"fam-{p.oid}")
        a, b = self.background(2)
        resold = self.device("Android handset", "resold")
        self.sim_in(a.phone_oids[0], resold, "resold-a", first_seen=w.ts(340).date().isoformat(), last_seen=w.ts(250).date().isoformat())
        self.sim_in(b.phone_oids[0], resold, "resold-b", first_seen=w.ts(200).date().isoformat(), last_seen=w.ts(5).date().isoformat())
        # benign (not seeded): an ordinary person changes number and keeps calling the same people
        changer = self.background(1, exclude={a.oid, b.oid, fam.oid})[0]
        old = changer.phones[0]
        friends = self.background(6, exclude={changer.oid})
        for f in friends:
            for _ in range(4):
                w.call(w.ts(rng.uniform(160, 330), 12), old, f.phones[0])
        nn, nph = w.phone(None, subscriber=changer.name)
        for f in friends:
            for _ in range(4):
                w.call(w.ts(rng.uniform(5, 148), 12), nn, f.phones[0])
        gang_ids = [p.oid for p in gang]
        self.truth["CONTINUING_UNLAWFUL_ACTIVITY"] = {"positives": [gang_ids], "benign": [[p.oid for p in quarrel]]}
        self.truth["WEAPON_LINKAGE"] = {"positives": [[pistol, cartridges, incidents[2], murder]], "benign": [[licensed]]}
        ops = self.w.truth["operations"]
        self.truth["HANDSET_CREW"] = {"positives": [[m.oid for m in members], [ops["MULE"]["herder"], *ops["MULE"]["mules"]], ops["KESTREL"]["operatives"][1:]],
                                      "benign": [[fam.oid, *[k_.oid for k_ in kin]], [a.oid, b.oid]]}
        self.truth["BURNER_SUCCESSION"] = {"positives": [[leader.phone_oids[0], new_ph]], "benign": [[changer.phone_oids[0], nph]]}
        self.ironside_gang = gang
        self.adda = adda

    # ------------------------------------------------------------------ narcotics / terror: precursor registers
    def precursors(self) -> None:
        w, rng = self.w, self.rng
        dealers = [w.org(f"{n} (synthetic)", "chemical_dealer", c, capital=5_000_000) for n, c in
                   (("Shivam Fine Chemicals", "Mumbai"), ("Gujarat Chem Traders", "Ahmedabad"), ("Deccan Reagents", "Pune"), ("Konkan Industrial Chemicals", "Thane"))]
        for d in dealers:
            self.s.upsert_object("Organisation", {"name": self.s.get_object(d)["title"], "licence_no": f"NCB-CS-DLR-{rng.randint(1000, 9999)}",
                                                  "licensed_for": ["pseudoephedrine", "ephedrine", "acetic_anhydride"]}, source="NCB-CS-REG-SYN", record=f"LIC:{d}", obj_id=d, synthetic=True)
        ex_dealers = [w.org(f"{n} (synthetic)", "explosives_dealer", c, capital=3_000_000) for n, c in (("Sahyadri Explosives Depot", "Nashik"), ("Vidarbha Blasting Supplies", "Nagpur"))]
        for d in ex_dealers:
            self.s.upsert_object("Organisation", {"name": self.s.get_object(d)["title"], "licence_no": f"PESO-LE5-{rng.randint(1000, 9999)}",
                                                  "licensed_for": ["ammonium_nitrate"]}, source="PESO-SYN", record=f"LIC:{d}", obj_id=d, synthetic=True)

        def buyer(name: str, kind: str, city: str, substances: list[str] | None, age_days: int = 4000) -> str:
            o = w.org(f"{name} (synthetic)", kind, city, incorporated_days_ago=age_days, capital=rng.randint(1, 30) * 1_000_000)
            if substances:
                self.s.upsert_object("Organisation", {"name": f"{name} (synthetic)", "licence_no": f"LIC-{rng.randint(10000, 99999)}", "licensed_for": substances},
                                     source="NCB-CS-REG-SYN" if kind == "pharma" else "PESO-SYN", record=f"LIC:{o}", obj_id=o, synthetic=True)
            return o

        def buy(t: datetime, b: str, d: str, sub: str, regime: str, qty: float, licence: str | None) -> None:
            self.procs.append((f"PR{len(self.procs):06d}", t.isoformat(timespec="minutes"), b, d, sub, regime, round(qty, 1),
                               f"INV/{rng.randint(10000, 99999)}", licence, "DEALER-REGISTER-SYN"))

        def lic(o: str) -> str | None:
            return self.s.get_object(o)["props"].get("licence_no")

        pharma = [buyer(n, "pharma", c, ["pseudoephedrine", "ephedrine"]) for n, c in
                  (("Sanjeevani Formulations", "Mumbai"), ("Aarogya Labs", "Pune"), ("Medicore Pharma", "Thane"), ("Vedant Lifesciences", "Ahmedabad"),
                   ("Nirmal Healthcare", "Nashik"), ("Pratham Generics", "Aurangabad"), ("Shubh Pharma", "Navi Mumbai"), ("Sai Remedies", "Kolhapur"))]
        trend = buyer("Indus Cough Care", "pharma", "Pune", ["pseudoephedrine"])  # benign: steady growth
        for o in pharma + [trend]:
            base = rng.uniform(40, 320)
            dealer = rng.choice(dealers)
            for m in range(12, 0, -1):
                growth = (1.06 ** (12 - m)) if o == trend else 1.0
                buy(w.ts(30 * m - rng.uniform(0, 6), 11), o, dealer, "pseudoephedrine", "NDPS-CS", base * growth * rng.lognormvariate(0, 0.15), lic(o))
        quarries = [buyer(n, "company", c, ["ammonium_nitrate"]) for n, c in
                    (("Western Ghats Stone Crushers", "Nashik"), ("Godavari Quarry Works", "Aurangabad"), ("Satpura Mining", "Nagpur"), ("Konkan Aggregates", "Panvel"))]
        for o in quarries:  # benign: seasonal (monsoon) dip and recovery
            base = rng.uniform(300, 900)
            for m in range(12, 0, -1):
                monsoon = 0.35 if m in (4, 5, 6) else 1.0
                buy(w.ts(30 * m - rng.uniform(0, 6), 10), o, rng.choice(ex_dealers), "ammonium_nitrate", "EXPLOSIVES-AN", base * monsoon * rng.lognormvariate(0, 0.12), lic(o))
        # NCB plant: a licensed pharma firm diverts - volume jumps sixfold, split across every dealer in small orders
        vard = buyer("Vardhaman Remedies", "pharma", "Bhiwandi", ["pseudoephedrine"])
        for m in range(12, 2, -1):
            buy(w.ts(30 * m - rng.uniform(0, 6), 11), vard, dealers[0], "pseudoephedrine", "NDPS-CS", rng.uniform(30, 40), lic(vard))
        for m in (2, 1):
            for _ in range(rng.randint(8, 10)):
                buy(w.ts(30 * m - rng.uniform(0, 28), rng.randint(10, 17)), vard, rng.choice(dealers), "pseudoephedrine", "NDPS-CS", rng.uniform(18, 28), lic(vard))
        # NIA plant: a four-month-old trading company with no explosives licence buys ammonium nitrate from both depots,
        # quoting a licence number that is not its own; its director is in the Kestrel module
        ops = self.w.truth["operations"]["KESTREL"]
        balaji = w.org("Balaji Agri Traders (synthetic)", "company", "Nashik", incorporated_days_ago=130, capital=100_000)
        self.s.upsert_link("director_of", ops["operatives"][2], balaji, source="MCA-SYN", record="DIN:balaji")
        for k in range(6):
            buy(w.ts(60 - k * 6 - rng.uniform(0, 3), 12), balaji, ex_dealers[k % 2], "ammonium_nitrate", "EXPLOSIVES-AN", rng.uniform(40, 48), "LE-3/NSK/2019/0412")
        self.truth["PRECURSOR_DIVERSION"] = {"positives": [[vard], [balaji]], "benign": [[trend], quarries, pharma]}

    # ------------------------------------------------------------------ corruption: tender cartel
    def roadroller(self) -> None:
        w, rng = self.w, self.rng
        dept = w.org("Public Works Division, Pune (synthetic)", "department", "Pune", source="CPPP-SYN")
        fixer = w.make_person(city="Pune", occupation="Civil contractor", income=1_800_000, rich=True, role="roadroller_fixer")
        w.home(fixer)
        w.phone(fixer)
        cartel = [w.org(f"{n} (synthetic)", "company", "Pune", incorporated_days_ago=rng.randint(1500, 3000), capital=rng.randint(5, 20) * 1_000_000,
                        address=a) for n, a in (("Shree Ganesh Constructions", "Plot 9, Market Yard, Pune"), ("Mahalaxmi Infra", "Office 2, Swargate Chambers, Pune"),
                                                ("Om Sai Roadways", "Unit 5, Bibvewadi Complex, Pune"), ("Jai Bhavani Builders", "Unit 5, Bibvewadi Complex, Pune"))]
        self.s.upsert_link("director_of", fixer.oid, cartel[0], source="MCA-SYN", record="DIN:fixer:0")
        self.s.upsert_link("director_of", fixer.oid, cartel[1], source="MCA-SYN", record="DIN:fixer:1")
        _, shared_ph = w.phone(None, org=cartel[1], subscriber="Mahalaxmi Infra (synthetic)")
        self.s.upsert_link("uses_phone", cartel[2], shared_ph, source="GSTN-SYN", record="GST-CONTACT:omsai")
        independents = [w.org(f"{n} (synthetic)", "company", c, incorporated_days_ago=rng.randint(1500, 5000), capital=rng.randint(5, 30) * 1_000_000,
                              address=f"{rng.randint(1, 99)} {n.split()[0]} Road, {c}") for n, c in
                        (("Kalyani Civil Works", "Pune"), ("Sahyadri Engineers", "Kolhapur"), ("Bharat Pipes & Drains", "Pune"),
                         ("Patil Earthmovers", "Solapur"), ("Western Infra Projects", "Mumbai"), ("Nagpur Roadtech", "Nagpur"))]
        tenders = []

        def tender(k: int, title: str, cat: str, est: float, days: int) -> str:
            t = self.s.upsert_object("Tender", {"tender_id": f"PWD/PUNE/{w.today.year}/{k:03d}", "title": title, "department": "Public Works Division, Pune",
                                                "category": cat, "estimate": est, "published_on": w.ts(days).date().isoformat(),
                                                "district_lgd": w.district_code.get("Pune")}, source="CPPP-SYN", record=f"T{k}", synthetic=True)
            self.s.upsert_link("issued_by", t, dept, source="CPPP-SYN", record=f"T{k}")
            tenders.append(t)
            return t

        def bids(t: str, offers: list[tuple[str, float, str]], days: int) -> None:
            for org, amt, ip in offers:
                self.bid_rows.append((f"BID{len(self.bid_rows):05d}", t, org, round(amt, -3), w.ts(days - 10, rng.randint(10, 17)).isoformat(timespec="minutes"), ip, "CPPP-SYN"))
                self.s.upsert_link("bid_on", org, t, source="CPPP-SYN", record=f"BID:{t}:{org}")
            win = min(offers, key=lambda x: x[1])[0]
            self.s.upsert_link("awarded_to", t, win, source="CPPP-SYN", record=f"AWARD:{t}")

        for k in range(12):  # cartel market: rotation, cover bids a few percent above the designated winner
            days = 330 - k * 25
            est = rng.randint(12, 45) * 1_000_000
            t = tender(k + 1, f"Resurfacing of district road MDR-{40 + k}", "Road resurfacing", est, days)
            win = cartel[k % 4]
            wb = est * rng.uniform(0.985, 1.03)
            offers = [(win, wb, "103.21.44.17" if rng.random() < 0.7 else f"49.36.{rng.randint(1, 250)}.{rng.randint(1, 250)}")]
            for c in cartel:
                if c != win:
                    offers.append((c, wb * rng.uniform(1.025, 1.07), "103.21.44.17" if rng.random() < 0.6 else f"49.36.{rng.randint(1, 250)}.{rng.randint(1, 250)}"))
            bids(t, offers, days)
        for k in range(7):  # competitive market: independent bidders, dispersed bids
            days = 320 - k * 40
            est = rng.randint(8, 30) * 1_000_000
            t = tender(20 + k, f"Storm-water drain, ward {k + 3}", "Drainage works", est, days)
            offers = [(o, est * rng.uniform(0.80, 1.08), f"{rng.randint(11, 220)}.{rng.randint(1, 250)}.{rng.randint(1, 250)}.{rng.randint(1, 250)}")
                      for o in rng.sample(independents, rng.randint(4, 5))]
            bids(t, offers, days)
        self.truth["TENDER_COLLUSION"] = {"positives": [[*cartel, fixer.oid]], "benign": [independents]}

    # ------------------------------------------------------------------ corruption: disproportionate assets
    def ledgerbook(self) -> None:
        w, rng = self.w, self.rng
        dept = w.org("Department of Registration and Stamps, Pune (synthetic)", "department", "Pune", source="HRMS-SYN")
        dept_acct = w.account(dept, "Registration and Stamps Salary", kind="current", city="Pune")
        bank = w.org("Maharashtra Co-operative Bank, Housing Loans (synthetic)", "bank", "Pune")
        loan_acct = w.account(bank, "Housing loan disbursement", kind="current", city="Pune")
        builder = w.org("Riverfront Homes LLP (synthetic)", "company", "Pune", capital=50_000_000)
        b_acct = w.account(builder, "Riverfront Homes", kind="current", city="Pune")

        def servant(occ: str, monthly: int, role: str) -> P:
            p = w.make_person(city="Pune", occupation=occ, income=monthly * 12, age=(40, 56), role=role)
            w.home(p)
            w.phone(p)
            p.accounts.append(w.account(p.oid, p.name, city="Pune", opened_days_ago=4000))
            self.s.upsert_link("employee_of", p.oid, dept, source="HRMS-SYN", record=f"EMP:{p.oid}")
            for m in range(12):
                w.txn(w.ts(30 * m + 1, 10), dept_acct, p.accounts[0], monthly, "NEFT", "SALARY")
                for _ in range(3):
                    w.txn(w.ts(30 * m + rng.uniform(2, 28), 18), p.accounts[0], rng.choice(w.merchant_accts), rng.randint(5, 12) * 1000, "UPI", "UPI/shopping")
            return p

        sub = servant("Sub-Registrar (Class II officer)", 85_000, "da_subject")
        wife = w.make_person(city="Pune", gender="F", occupation="Homemaker", income=0, surname=(sub.surname, sub.surname_native), community=sub.community, role="da_family")
        w.home(wife, share_with=sub)
        wife.accounts.append(w.account(wife.oid, wife.name, city="Pune"))
        bil = w.make_person(city="Solapur", occupation="Farmer", income=150_000, role="da_relative")
        w.home(bil)
        bil.accounts.append(w.account(bil.oid, bil.name, city="Solapur"))
        for r in (wife, bil):
            self.s.upsert_link("relative_of", sub.oid, r.oid, source="PDS-SYN", record=f"RC:{r.oid}")
        for _ in range(16):  # unexplained cash
            w.txn(w.ts(rng.uniform(170, 340), rng.randint(10, 15)), None, wife.accounts[0], rng.randint(150, 240) * 1000, "CASH", "CASH DEPOSIT")
        w.txn(w.ts(150, 12), wife.accounts[0], b_acct, 72_00_000, "RTGS", "FLAT 1104 CONSIDERATION")
        w.property_(wife.oid, "Pune", "Flat 1104, Riverfront Homes, Kharadi", 72_00_000, 148)
        w.txn(w.ts(95, 12), wife.accounts[0], bil.accounts[0], 30_00_000, "RTGS", "FAMILY HELP")
        w.property_(bil.oid, "Solapur", "Agricultural land, Gat 221, Mohol", 45_00_000, 88, kind="land")
        car = w.org("Pune Motors (synthetic)", "merchant", "Pune")
        car_acct = w.account(car, "Pune Motors", kind="current", city="Pune")
        w.txn(w.ts(120, 12), sub.accounts[0], car_acct, 18_00_000, "RTGS", "SUV PURCHASE")
        w.vehicle(sub.oid, "Pune", "Mahindra XUV700", 18_00_000)
        w.property_(sub.oid, "Pune", "Ancestral flat, Sadashiv Peth", 25_00_000, 3600)
        # benign: a senior officer whose flat is paid for by a housing loan
        senior = servant("Joint Inspector General of Registration", 2_40_000, "da_benign")
        w.txn(w.ts(105, 11), loan_acct, senior.accounts[0], 85_00_000, "NEFT", "HOME LOAN DISBURSEMENT")
        w.txn(w.ts(104, 12), senior.accounts[0], b_acct, 1_10_00_000, "RTGS", "FLAT 1802 CONSIDERATION")
        w.property_(senior.oid, "Pune", "Flat 1802, Riverfront Homes, Kharadi", 1_10_00_000, 100)
        # benign: a clerk with inherited property
        clerk = servant("Senior clerk", 45_000, "da_benign")
        w.property_(clerk.oid, "Pune", "Inherited house, Kasba Peth", 90_00_000, 4200, kind="bungalow")
        self.truth["DISPROPORTIONATE_ASSETS"] = {"positives": [[sub.oid, wife.oid]], "benign": [[senior.oid], [clerk.oid]]}

    # ------------------------------------------------------------------ movement: convoys, cloned plates, stolen vehicles
    def movement(self) -> None:
        w, rng = self.w, self.rng
        ops = self.w.truth["operations"]["COASTLINE"]
        truck = ops["truck"]
        escort = self.person(city="Panvel", gender="M", occupation="Driver", income=220_000, role="coastline_escort")
        pilot = w.vehicle(escort.oid, "Panvel", "Mahindra Scorpio", 14_00_000)
        coord = w.by_oid[ops["coordinator"]]
        for _ in range(15):
            w.call(w.ts(rng.uniform(30, 150), rng.randint(9, 22)), coord.phones[0], escort.phones[0])
        for row in [r for r in w.tolls if r[1] == truck]:
            t = datetime.fromisoformat(row[2]) - timedelta(minutes=rng.randint(7, 16))
            self.reads.append((f"RD{len(self.reads):06d}", pilot, t.isoformat(timespec="minutes"), row[3], row[4], row[5], "NETC-FASTAG-SYN", "toll"))
        # benign: a transport company's two trucks travelling together - same owner, a fleet, not a convoy lead
        fleet = w.org("Sahyadri Roadlines (synthetic)", "transport", "Pune", capital=8_000_000)
        trucks = [w.vehicle(fleet, "Pune", "Ashok Leyland 1616", 30_00_000) for _ in range(2)]
        route = ["Talegaon Toll (Expressway)", "Khalapur Toll (Expressway)", "Vashi Toll Plaza"]
        for day in (200, 150, 90):
            t0 = w.ts(day, 5)
            for j, pl in enumerate(route):
                for k_, tr in enumerate(trucks):
                    self.read(tr, t0 + timedelta(hours=j * 1.3, minutes=k_ * 6), pl)
        # commuters: daily reads at one plaza (noise for convoy and plate checks)
        vehicles = [r["dst"] for r in self.s.query("SELECT l.src, l.dst FROM links l WHERE l.type='owns' AND l.dst LIKE 'vehicle:%' AND l.src LIKE 'person:%'")]
        owner = {r["dst"]: r["src"] for r in self.s.query("SELECT src, dst FROM links WHERE type='owns' AND dst LIKE 'vehicle:%'")}
        commuters = [v for v in vehicles if w.by_oid.get(owner.get(v, ""), None) and w.by_oid[owner[v]].role == "background"
                     and w.by_oid[owner[v]].city in COMMUTE]
        commuters = rng.sample(commuters, min(45, len(commuters)))
        for v in commuters:
            pl = COMMUTE[w.by_oid[owner[v]].city]
            for d in range(4, 40):
                if d % 7 in (0, 6):
                    continue
                self.read(v, w.ts(d, 8) + timedelta(minutes=rng.randint(0, 80)), pl)
                self.read(v, w.ts(d, 18) + timedelta(minutes=rng.randint(0, 100)), pl)
        # a plausible fast trip (Mumbai to Pune in two hours) - not a cloned plate
        fast = commuters[0]
        self.read(fast, w.ts(3, 6), "Vashi Toll Plaza")
        self.read(fast, w.ts(3, 6) + timedelta(minutes=125), "Talegaon Toll (Expressway)")
        # cloned plate: a Pune car is read in Nashik 30-40 minutes after a read in Talegaon, three times
        pune_cars = [v for v in commuters if COMMUTE[w.by_oid[owner[v]].city] == "Talegaon Toll (Expressway)" and v != fast]
        cloned = pune_cars[0]
        for d in (33, 26, 19):
            t = w.ts(d, 8) + timedelta(minutes=5)
            self.read(cloned, t, "Talegaon Toll (Expressway)")
            self.read(cloned, t + timedelta(minutes=rng.randint(30, 40)), "Nashik Phata ANPR")
        snatch = w.incident(f"MH/NSK/CTY/{w.ts(26).year}/1204", "fir", "State Police", "Nashik", ["BNS 304 snatching"],
                            "Chain snatched by two men in a white hatchback; witness noted a Pune (MH12) number plate.", w.ts(26, 9))
        # stolen vehicles: three are read after the theft heading to the same ANPR point; one goes elsewhere;
        # one was read only before it was stolen
        pool = [p for p in self.w.people if p.role == "background" and p.city in ("Mumbai", "Thane", "Navi Mumbai", "Pune")]
        stolen, fir_ids = [], []
        for k, (days, trail) in enumerate(((120, ["Padgha Toll (Mumbai-Nashik)", "Bhiwandi Bypass ANPR"]), (100, ["Bhiwandi Bypass ANPR"]),
                                           (90, ["Mulund Check Naka", "Bhiwandi Bypass ANPR"]), (70, ["Khed Shivapur Toll"]), (50, []))):
            own = rng.choice(pool)
            v = w.vehicle(own.oid, own.city, rng.choice(["Maruti Swift", "Hyundai i20", "Toyota Innova"]), rng.randint(6, 16) * 100_000)
            reg = self.s.get_object(v)["props"]["registration_no"]
            self.s.upsert_object("Vehicle", {"registration_no": reg, "status": "stolen", "chassis_no": f"MA3{w.letters(4)}{w.digits(10)}"},
                                 source="ZIPNET-SYN", record=f"STOLEN:{reg}", obj_id=v, synthetic=True)
            when = w.ts(days, 2)
            inc = w.incident(f"MH/{own.district or '000'}/VT/{when.year}/{500 + k}", "fir", "State Police", own.city, ["BNS 303(2) theft of vehicle"],
                             f"{reg} stolen from outside the owner's residence at night.", when)
            self.s.upsert_link("stolen_in", v, inc, source="CCTNS-SYN", record=f"VT-{k}")
            if k == 4:
                self.read(v, w.ts(days + 30, 9), COMMUTE.get(own.city, "Vashi Toll Plaza"))
            for j, pl in enumerate(trail):
                self.read(v, when + timedelta(hours=2 + j * 1.5), pl)
            stolen.append(v)
            fir_ids.append(inc)
        self.truth["CONVOY"] = {"positives": [[truck, pilot]], "benign": [trucks]}
        self.truth["CLONED_PLATE"] = {"positives": [[cloned]], "benign": [[fast]]}
        self.truth["STOLEN_VEHICLE_TRAIL"] = {"positives": [[v] for v in stolen[:4]], "benign": [[stolen[4]]]}
        self.truth["snatching_fir"] = snatch

    # ------------------------------------------------------------------ external / terror: foreign handlers
    def handlers(self) -> None:
        w, rng = self.w, self.rng
        k = self.w.truth["operations"]["KESTREL"]
        handler = k["handler_phone"]
        op1, op2 = w.by_oid[k["operatives"][1]], w.by_oid[k["operatives"][2]]
        for p, n in ((op1, 6), (op2, 4)):
            for _ in range(n):
                w.call(w.ts(rng.uniform(100, 200), rng.randint(20, 23)), handler, p.phones[0])
        for dep in (150, 100):  # op1 flies to Kathmandu twice; the handler called him days before each trip
            w.call(w.ts(dep + 3, 21), handler, op1.phones[0])
        c = self.w.truth["operations"]["COASTLINE"]
        colombo = "+94771234567"
        for s_id, cour in zip(c["seizures"], c["couriers"]):
            when = datetime.fromisoformat(self.s.get_object(s_id)["props"]["occurred_at"])
            for _ in range(2):
                w.call(when - timedelta(hours=rng.uniform(20, 60)), colombo, w.by_oid[cour].phones[0])
        # benign: families who call relatives working in the Gulf
        families = [hh for hh in self.w.households if len(hh) >= 2 and all(p.phones for p in hh)]
        self.gulf_numbers = []
        for hh in rng.sample(families, min(14, len(families))):
            num = f"+9715{w.digits(8)}"
            self.gulf_numbers.append(num)
            w.phone(None, intl=num, subscriber="unknown (UAE)")
            for p in hh[:2]:
                for _ in range(rng.randint(5, 12)):
                    w.call(w.ts(rng.uniform(5, 300), rng.randint(19, 23)), num, p.phones[0], dur=rng.randint(120, 1500))
        self.truth["FOREIGN_HANDLER"] = {"positives": [[make_phone_id(handler), k["leader"], *k["operatives"]],
                                                       [make_phone_id(colombo), c["coordinator"], *c["couriers"]]],
                                         "benign": [[make_phone_id(n)] for n in self.gulf_numbers]}
        self.truth["RECCE_REPETITION"] = {"positives": [[k["recce_tower"], *k["operatives"]]], "benign": [[self.adda]]}
        mule = self.w.truth["operations"]["MULE"]
        self.truth["VICTIM_CONVERGENCE"] = {"positives": [[*mule["aggregators"], mule["herder"], *mule["fronts"]], self.sleeper_collectors], "benign": []}

    # ------------------------------------------------------------------ run
    def run(self) -> dict[str, Any]:
        self.anthill()
        self.sleepers()
        self.orbit()
        self.deccan_group()
        self.dialtone()
        self.ironside()
        self.precursors()
        self.roadroller()
        self.ledgerbook()
        self.movement()
        self.handlers()
        s = self.s
        s.executemany("INSERT INTO tollhits(id,vehicle_id,ts,plaza,lat,lon,source,kind) VALUES(?,?,?,?,?,?,?,?)", self.reads)
        s.executemany("INSERT INTO procurements(id,ts,buyer_id,seller_id,substance,regime,quantity_kg,invoice,buyer_licence,source) VALUES(?,?,?,?,?,?,?,?,?,?)", self.procs)
        s.executemany("INSERT INTO bids(id,tender_id,bidder_id,amount,submitted_at,submit_ip,source) VALUES(?,?,?,?,?,?,?)", self.bid_rows)
        self.w.truth["missions"] = self.truth
        return {"anpr_toll_reads": len(self.reads), "procurements": len(self.procs), "bids": len(self.bid_rows), "scenarios": len(self.truth)}


def make_phone_id(number: str) -> str:
    return make_id("Phone", "msisdn", number)

"""Build the demo world end to end and open one case per agency."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .analytics.behaviour import run_behaviour
from .analytics.inference import run_inference
from .analytics.money import Ledger
from .analytics.typologies import run_typologies
from .connectors.lgd import Gazetteer, load_admin_units
from .connectors.osm import load_hospitals
from .connectors.sachet import ingest_sachet
from .guard import DEV_USERS, AuditLog, Guard
from .patterns.engine import run_patterns
from .patterns.evaluate import evaluate
from .resolve.service import run_resolution
from .store import Store
from .synth.world import World
from .vision.gallery import seed_faces, seed_portraits


def agency_cases(store: Store) -> list[str]:
    """Each case starts only from what that agency would actually have on file."""
    t = (store.get_meta("synthetic_truth") or {}).get("operations", {})
    if not t:
        return []
    g, audit = Guard(store), AuditLog(store)
    specs = [
        ("ed.dd", "money_laundering_investigation", "Operation Mirage: laundering of cyber-fraud proceeds",
         "ECIR/MBZO-II/31 under PMLA ss.3-4; scheduled offence BNS 318(4), 319(2); FIU-IND STR 88412",
         [t["MIRAGE"]["ecir"], t["MIRAGE"]["str"]], ["ed.jd", "ib.analyst"]),
        ("cyber.io", "cyber_fraud_investigation", "Navi Mumbai mule-account racket",
         "FIR MH/NMB/CYB/0412 u/s 318(4), 111(2)(b) BNS and 66C/66D IT Act; linked NCRP complaints",
         [t["MULE"]["fir"], *t["MULE"]["complaints"][:12]], ["ed.dd"]),
        ("cbi.dsp", "bank_fraud_investigation", "Sunrise Infraprojects: Rs 180 cr loan diversion",
         "CBI RC/BSFC/E/0007 u/s 61(2), 316(5), 318(4) BNS and ss.7, 13(2) PC Act on the bank's complaint",
         [t["SUNRISE"]["rc"]], ["ib.analyst"]),
        ("nia.sp", "terror_financing_investigation", "Module Kestrel: terror financing",
         "NIA RC-04/MUM u/s 17, 18 UAPA and 61(2) BNS, on MHA order under s.6(5) NIA Act",
         [t["KESTREL"]["case"]], ["nia.ig", "ib.analyst"]),
        ("ncb.io", "narcotics_investigation", "Operation Coastline: port seizures",
         "NCB/MZU CR-21, 22, 23 u/s 8(c), 21(c), 29 NDPS Act",
         t["COASTLINE"]["seizures"], ["ib.analyst"]),
    ]
    ids = []
    for uid, purpose, title, basis, seeds, members in specs:
        u = DEV_USERS[uid]
        cid = g.open_case(u, purpose=purpose, legal_basis=basis, fir_no=None, members=members, title=title, subjects=seeds)
        audit.append(user_id=u.id, role=u.primary_role, action="action:open_case", case_id=cid, purpose=purpose,
                     detail={"title": title, "demo": True}, object_ids=seeds)
        ids.append(cid)
    store.set_meta("agency_cases", ids)
    return ids


def lead_case_demo(store: Store) -> str | None:
    """Show the lead workflow once: a Crime Branch inspector asks for a case on the syndicate lead in
    Pune and the Superintendent approves it. Every other lead stays pseudonymous in the queue."""
    from .patterns import leads

    row = store.query("SELECT id FROM pattern_hits WHERE detector='CONTINUING_UNLAWFUL_ACTIVITY' AND status='open' ORDER BY id LIMIT 1")
    if not row:
        return None
    io, sp = DEV_USERS["crime.pi"], DEV_USERS["sp.pune"]
    audit = AuditLog(store)
    rid = leads.request_case(store, io, row[0]["id"], "organised_crime_investigation",
                             "Crime Branch Pune enquiry under BNS s.111 on the pattern lead; FIRs CB/311-314 and HDP/0907 (synthetic)",
                             "Kondhwa syndicate: continuing unlawful activity (lead)")
    audit.append(user_id=io.id, role=io.primary_role, action="action:request_case_from_lead", detail={"lead": row[0]["id"], "demo": True},
                 object_ids=[row[0]["id"]])
    out = leads.approve_case(store, Guard(store), sp, rid)
    audit.append(user_id=sp.id, role=sp.primary_role, action="action:approve_case_from_lead", case_id=out["case_id"],
                  purpose=out["purpose"], detail=out | {"demo": True}, object_ids=[row[0]["id"]])
    return out["case_id"]


def build_world(store: Store, reference_dir: Path, samples_dir: Path, *, live: bool = False, people: int = 1800, hospitals: bool = True,
                redteam: bool = False, portraits: bool = False, background: bool = True, log=print) -> dict[str, Any]:
    t0 = time.time()
    out: dict[str, Any] = {}
    out["lgd"] = load_admin_units(store, reference_dir)
    log("LGD admin units:", out["lgd"])
    out["hospitals"] = load_hospitals(store, reference_dir) if hospitals else {"hospitals": 0}
    log("OSM hospitals:  ", out["hospitals"])
    gaz = Gazetteer.load(reference_dir)
    try:
        out["sachet"] = ingest_sachet(store, gaz, sample_dir=None if live else samples_dir / "sachet")
    except OSError:
        out["sachet"] = ingest_sachet(store, gaz, sample_dir=samples_dir / "sachet")
    log("SACHET alerts:  ", out["sachet"])
    out["world"] = World(store, reference_dir, n_people=people).run()
    log("Synthetic world:", out["world"])
    if background:
        from .synth.enrich import enrich

        out["background"] = enrich(store, log=log)
        log("Background:     ", out["background"])
    out["resolution"] = run_resolution(store)
    log("Entity resolution:", {k: out["resolution"][k] for k in ("records", "auto_links", "sent_to_review", "resolved_entities")})
    ledger = Ledger(store)
    out["typologies"] = run_typologies(store, ledger)
    log("Typology alerts:", out["typologies"])
    out["inference"] = run_inference(store, ledger)
    log("Inferred links: ", out["inference"])
    out["behaviour"] = run_behaviour(store, ledger)
    log("Behaviour flags:", out["behaviour"])
    out["patterns"] = run_patterns(store, ledger)
    log("Pattern leads:  ", out["patterns"])
    out["pattern_eval"] = evaluate(store)["summary"]
    log("Pattern eval:   ", out["pattern_eval"])
    if redteam:
        from .patterns.redteam import run_redteam

        rt = run_redteam(store, log=lambda *a: None)
        out["redteam"] = {"closed": rt["closed"], "known_limits": rt["known_limits_confirmed"], "surprises": rt["surprises"]}
        log("Red team:       ", out["redteam"])
    out["cases"] = agency_cases(store)
    out["lead_case"] = lead_case_demo(store)
    log("Agency cases:   ", out["cases"], "| case opened from a lead:", out["lead_case"])
    out["faces"] = seed_faces(store, samples_dir)
    log("Photographs:    ", out["faces"])
    if portraits:
        out["portraits"] = seed_portraits(store, samples_dir, ledger)
        log("Portraits:      ", out["portraits"])
    out["seconds"] = round(time.time() - t0, 1)
    store.set_meta("build", json.loads(json.dumps(out, default=str)))
    return out

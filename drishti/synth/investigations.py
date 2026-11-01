"""Deterministic, explicitly synthetic case files across non-financial domains.

Fixture labels stay out of the algorithms. Source records can disagree on purpose;
the checks must discover disagreements from their data, not a planted answer key.
"""
from __future__ import annotations

import hashlib

from ..guard import DEV_USERS, AuditLog, Guard
from ..store import Store, utcnow


def seed_investigations(store: Store) -> dict:
    previous = store.get_meta("investigation_examples_v1")
    if previous:
        return previous
    guard, audit = Guard(store), AuditLog(store)
    specs = [
        ("ASTER", "Aster · missing engineer reconstruction", "missing_person_trace", "io.pune", "sp.pune", ["ib.analyst"],
         "Synthetic missing-person report MP/ASTER/2026; authorised review of supplied witness and transport records"),
        ("HARBOR", "Harbor · cargo chain of custody", "narcotics_investigation", "ncb.io", "ncb.supervisor", ["ib.analyst"],
         "Synthetic case HARBOR/2026; authorised examination of supplied seizure, seal and logistics records"),
        ("LANTERN", "Lantern · public works inspection", "procurement_vigilance", "cbi.dsp", "cbi.sp", ["ib.analyst", "ed.dd"],
         "Synthetic complaint LANTERN/2026; authorised review of tender, inspection and delivery records"),
        ("RELAY", "Relay · service outage evidence", "cyber_fraud_investigation", "cyber.io", "sp.pune", ["ib.analyst"],
         "Synthetic incident RELAY/2026; authorised review of provided system logs and response records"),
    ]
    cases = []
    with store.tx():
        for code, title, purpose, officer, supervisor, collaborators, basis in specs:
            cid = guard.open_case(DEV_USERS[officer], purpose=purpose, legal_basis=basis, fir_no=None,
                                  title=title, members=[supervisor, *collaborators])
            ids: list[str] = []
            source_agency = DEV_USERS[officer].agency

            def obj(kind: str, key: str, props: dict, source: str, **kwargs) -> str:
                oid = f"{kind.lower()}:example-{code.lower()}-{key}"
                result = store.upsert_object(kind, props, obj_id=oid, source=f"SYNTHETIC/{source_agency}/{source}",
                                             record=f"{code}/{key}", synthetic=True, origin_case=cid,
                                             district_lgd="490", **kwargs)
                ids.append(result)
                return result

            def edge(kind: str, a: str, b: str, source: str = "case-file", **kwargs):
                return store.upsert_link(kind, a, b, source=f"SYNTHETIC/{source_agency}/{source}",
                                         record=f"{code}/{a.rsplit('-', 1)[-1]}/{b.rsplit('-', 1)[-1]}", **kwargs)

            def document(key: str, title: str, text: str, date: str, refs: list[str], source: str) -> str:
                doc = obj("Document", key, {"title": title, "content": text, "reference": f"{code}-{key.upper()}",
                          "agency": source_agency, "authored_at": date, "category": source,
                          "sha256": hashlib.sha256(text.encode()).hexdigest()}, source)
                for ref in refs:
                    edge("documented_in", ref, doc, source)
                return doc

            person = obj("Person", "principal", {"name": {"ASTER": "Anaya Deshmukh", "HARBOR": "Vivek Salunkhe", "LANTERN": "Meera Kulkarni", "RELAY": "Rohan Bendre"}[code],
                         "birth_year": 1988, "occupation": {"ASTER": "Civil engineer", "HARBOR": "Logistics coordinator", "LANTERN": "Works inspector", "RELAY": "Systems engineer"}[code],
                         "city": "Pune", "email": f"{code.lower()}.contact@example.invalid"}, "submitted-statement")
            witness = obj("Person", "witness", {"name": "Kavya More", "birth_year": 1992, "occupation": "Records officer", "city": "Pune"}, "witness-statement")
            company = obj("Organisation", "company", {"name": "Sahyadri Field Services (synthetic)", "kind": "company",
                          "registration_no": f"DEMO-{code}-001", "registered_address": "12 Example Industrial Estate, Pune", "city": "Pune"}, "submitted-registry")
            place = obj("Location", "site", {"label": "Example field office", "address": "12 Example Industrial Estate, Pune", "city": "Pune"}, "site-plan", lat=18.5204, lon=73.8567)
            second_place = obj("Location", "depot", {"label": "Example depot", "city": "Pune", "address": "8 Demonstration Road"}, "site-plan", lat=18.5604, lon=73.8967)
            edge("employee_of", person, company)
            edge("registered_at", company, place)
            device = obj("Device", "device", {"imei": f"DEMO-{code}-DEVICE", "model": "Synthetic field terminal"}, "asset-register")
            edge("owns", company, device, "asset-register")
            activity = {
                "ASTER": ["Shift handover", "Shuttle departure", "Witness interview", "Transport record correction"],
                "HARBOR": ["Container received", "Seal inspection", "Transfer of custody", "Inventory reconciliation"],
                "LANTERN": ["Tender specification issued", "Delivery accepted", "Site inspection", "Inspection report filed"],
                "RELAY": ["Service degradation", "Log collection", "Configuration review", "Service restored"],
            }[code]
            events = []
            for i, label in enumerate(activity):
                timestamp = f"2026-10-{5+i:02d}T09:00:00+00:00"
                loc = place if i % 2 == 0 else second_place
                ev = obj("Event", f"event-{i}", {"title": label, "kind": code.lower(), "occurred_at": timestamp,
                         "summary": f"Supplied {code} case record: {label.lower()}. Synthetic demonstration.",
                         "agency": source_agency, "location": "Example field office" if i % 2 == 0 else "Example depot", "accuracy_m": 100},
                         "event-log", lat=18.5204 + (i % 2) * 0.04, lon=73.8567 + (i % 2) * 0.04)
                events.append(ev)
                edge("participated_in", person if i != 2 else witness, ev, "event-log")
                edge("event_at", ev, loc, "event-log")
                document(f"record-{i}", f"{code} · {label}",
                         f"SYNTHETIC CASE FILE {code}\n{label}\nReference: {code}/LOG/{i:03d}\n"
                         f"This submitted record concerns {store.get_object(person)['title']} and Sahyadri Field Services. "
                         f"Recorded activity: {label.lower()}. Source: supplied case file. No conclusion about wrongdoing is established.",
                         timestamp, [ev, person, company], "case-record")
            if code == "ASTER":
                vehicle = obj("Vehicle", "shuttle", {"registration_no": "MH12DE2026", "make": "Demo shuttle", "colour": "white"}, "transport-reply")
                edge("owns", company, vehicle)
                edge("participated_in", vehicle, events[1], "transport-reply")
                # A separate transport log has the same timestamp, but a different place.
                correction = obj("Event", "disputed-entry", {"title": "Duplicate shuttle entry", "kind": "transport",
                                 "occurred_at": "2026-10-06T09:00:00+00:00", "location": "Example field office",
                                 "summary": "Second source lists a different location; verify timezone and vehicle reference."}, "transport-reply")
                edge("participated_in", vehicle, correction, "transport-reply")
                edge("event_at", correction, place)
            elif code == "HARBOR":
                shipment = obj("Shipment", "consignment", {"reference": "DEMO-HARBOR-041", "description": "Sealed sample cargo for inventory verification",
                               "origin": "Example depot", "destination": "Example field office", "status": "under review"}, "cargo-manifest")
                edge("operates", company, shipment)
                for event in events:
                    edge("participated_in", shipment, event, "cargo-manifest")
                document("seal-report", "Seal inspection discrepancy", "Synthetic seal register lists SEAL-A; receiving note lists SEAL-B. Compare original photographs and custody records.",
                         "2026-10-07T10:00:00+00:00", [shipment, events[1]], "inspection-report")
            elif code == "LANTERN":
                other = obj("Organisation", "supplier", {"name": "Pravara Equipment (synthetic)", "kind": "company", "city": "Pune",
                            "registration_no": "DEMO-LANTERN-002", "registered_address": "12 Example Industrial Estate, Pune"}, "submitted-registry")
                edge("participated_in", other, events[1], "delivery-note")
                document("specification", "Equipment specification and delivery comparison", "Synthetic tender requests 24 calibrated sensors. Submitted delivery note lists 20 units. Inspector requests a reconciled inventory before acceptance.",
                         "2026-10-08T10:00:00+00:00", [other, company, events[2]], "inspection-report")
            else:
                artifact = obj("DigitalArtifact", "endpoint", {"value": "relay-demo.example.invalid", "kind": "hostname", "description": "Non-resolving synthetic endpoint in supplied service logs", "first_seen": "2026-10-05T09:00:00+00:00"}, "system-log")
                edge("operates", company, artifact)
                edge("participated_in", artifact, events[0], "system-log")
                edge("participated_in", device, events[1], "system-log")
                document("incident-review", "Service incident review", "Synthetic log excerpt: configuration revision 17 preceded the outage; rollback to revision 16 restored service. This is a configuration hypothesis, not attribution to an individual.",
                         "2026-10-08T10:00:00+00:00", [artifact, device, events[3]], "incident-review")
            now = utcnow()
            for oid in ids:
                store.execute("INSERT INTO case_objects(case_id,object_id,added_by,reason,added_at) VALUES(?,?,?,?,?)",
                              (cid, oid, supervisor, "Admitted synthetic source record for this demonstration case", now))
            request = guard.request_expansion(DEV_USERS[officer], guard.load_case(cid), 3, "Review paths between admitted synthetic case records")
            guard.approve_expansion(DEV_USERS[supervisor], request)
            audit.append(user_id=supervisor, role="supervisor", action="demo:case_admitted", case_id=cid, purpose=purpose,
                         object_ids=ids, detail={"example": code, "synthetic": True, "approved_depth": 3})
            cases.append({"id": cid, "code": code, "title": title, "officer": officer, "supervisor": supervisor, "records": len(ids)})
        result = {"cases": cases, "version": 1, "created_at": utcnow()}
        store.set_meta("investigation_examples_v1", result)
    return result

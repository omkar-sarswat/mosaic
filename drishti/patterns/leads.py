"""Lead workflow: who sees a lead, how it is shown, and how a case is opened on it.

  * A lead is visible to investigators and analysts of agencies whose mandate covers one of its
    tracks, and (for district-bound officers) only inside their districts.
  * Until a case is open on it, every party in a lead is a pseudonym ("Subject B, bank account").
    Pseudonyms are per lead, so two leads cannot be joined by their labels.
  * Opening a case on a lead takes two officers of the same agency: one requests (purpose, legal
    basis), a supervisor who is not the requester approves. Only then do the lead's subjects enter the
    case scope, where the ordinary Guard rules decide what each member may see.
  * Dismissing a lead needs a reason; dispositions feed detector evaluation.
"""

from __future__ import annotations

import json
import re
import secrets
from string import ascii_uppercase
from typing import Any

from ..guard import Guard, PolicyError, User
from ..store import Store, make_id, utcnow

TOKEN = re.compile(r"\[\[([^\]]+)\]\]")
TYPE_LABEL = {"Person": "person", "Organisation": "organisation", "BankAccount": "bank account", "Phone": "phone number",
              "Device": "handset", "Vehicle": "vehicle", "Incident": "case record", "Firearm": "firearm", "Property": "property",
              "CryptoWallet": "crypto wallet", "Tender": "tender", "Location": "place"}


def visible_tracks(store: Store, user: User) -> set[str]:
    if not user.has("io", "supervisor", "analyst"):
        return set()
    return set(store.ontology.agency_tracks(user.agency))


def can_see(store: Store, user: User, row: dict[str, Any]) -> bool:
    tracks = set(json.loads(row["tracks"])) if isinstance(row["tracks"], str) else set(row["tracks"])
    if not tracks & visible_tracks(store, user):
        return False
    d = row.get("district_lgd")
    return not d or "*" in user.districts or d in user.districts


def _label(i: int) -> str:
    return ascii_uppercase[i % 26] + (str(i // 26) if i >= 26 else "")


def render(store: Store, row: dict[str, Any], reveal: set[str], summarize, decide) -> dict[str, Any]:
    """Replace [[object]] tokens by names (objects in `reveal` that Guard allows) or per-lead pseudonyms."""
    subjects = json.loads(row["subjects"])
    tokens = list(dict.fromkeys(subjects + TOKEN.findall(row["title"]) + TOKEN.findall(row["summary"])))
    objs = store.get_objects(tokens)
    labels: dict[str, str] = {}
    parties = []
    for i, oid in enumerate(tokens):
        o = objs.get(oid)
        kind = TYPE_LABEL.get(o["type"], o["type"].lower()) if o else "party"
        shown = bool(o and oid in reveal and decide(o).allow)
        if shown:
            labels[oid] = summarize(o)["title"]
        else:
            labels[oid] = f"Subject {_label(i)} ({kind})"
        if oid in subjects:
            parties.append({"id": oid if shown else None, "label": labels[oid], "type": o["type"] if o else None, "revealed": shown,
                            "summary": summarize(o) if shown else None})
    sub = lambda text: TOKEN.sub(lambda m: labels.get(m.group(1), "a party"), text)  # noqa: E731
    revealed_any = any(p["revealed"] for p in parties)
    evidence = json.loads(row["evidence"])
    return {
        "id": row["id"], "detector": row["detector"], "version": row["version"], "tracks": json.loads(row["tracks"]),
        "severity": row["severity"], "title": sub(row["title"]), "summary": sub(row["summary"]), "parties": parties,
        "measurements": json.loads(row["measurements"]), "thresholds": json.loads(row["thresholds"]),
        "evidence_counts": {k: len(v) if isinstance(v, (list, dict)) else 1 for k, v in evidence.items()},
        "evidence": evidence if revealed_any else None,
        "window": [row["window_start"], row["window_end"]], "district": row["district_lgd"], "status": row["status"],
        "case_id": row["case_id"], "disposition": row["disposition"], "first_seen": row["first_seen"], "last_seen": row["last_seen"],
        "pseudonymous": not revealed_any,
    }


def get_row(store: Store, hit_id: str) -> dict[str, Any]:
    rows = store.query("SELECT * FROM pattern_hits WHERE id=?", (hit_id,))
    if not rows:
        raise PolicyError("no such lead")
    return dict(rows[0])


def request_case(store: Store, user: User, hit_id: str, purpose: str, legal_basis: str, title: str | None) -> str:
    row = get_row(store, hit_id)
    if not user.has("io", "supervisor"):
        raise PolicyError("only an investigating officer or supervisor can ask for a case on a lead")
    if not can_see(store, user, row):
        raise PolicyError("this lead is outside your agency's mission tracks or jurisdiction")
    if row["status"] != "open":
        raise PolicyError(f"lead is {row['status']}")
    if purpose not in store.ontology.agency_purposes(user.agency):
        raise PolicyError(f"{purpose} is outside the mandate of {user.agency}")
    if len(legal_basis.strip()) < 10:
        raise PolicyError("legal basis must cite the FIR / order and the provisions relied on")
    rid = make_id("leadrequest", hit_id, f"{user.id}|{utcnow()}|{secrets.token_hex(3)}")
    with store.tx() as conn:
        conn.execute("INSERT INTO lead_requests(id,hit_id,purpose,legal_basis,title,requested_by,agency,requested_at) VALUES(?,?,?,?,?,?,?,?)",
                     (rid, hit_id, purpose, legal_basis.strip(), title, user.id, user.agency, utcnow()))
    return rid


def approve_case(store: Store, guard: Guard, approver: User, request_id: str) -> dict[str, Any]:
    rows = store.query("SELECT * FROM lead_requests WHERE id=?", (request_id,))
    if not rows or rows[0]["status"] != "pending":
        raise PolicyError("no pending request with that id")
    req = dict(rows[0])
    if not approver.has("supervisor"):
        raise PolicyError("only a supervisor can approve a case on a lead")
    if approver.id == req["requested_by"]:
        raise PolicyError("two-person rule: the requester cannot approve their own request")
    if approver.agency != req["agency"]:
        raise PolicyError("the approving supervisor must belong to the requesting agency")
    row = get_row(store, req["hit_id"])
    if row["status"] != "open":
        raise PolicyError(f"lead is {row['status']}")
    subjects = [s for s in json.loads(row["subjects"]) if store.get_object(s)]
    # the approving supervisor opens the case; the requesting officer is a member from the start
    case_id = guard.open_case(approver, purpose=req["purpose"], legal_basis=req["legal_basis"], fir_no=None,
                              members=[req["requested_by"]], title=req["title"] or row["title"], subjects=subjects)
    now = utcnow()
    with store.tx() as conn:
        conn.execute("UPDATE case_objects SET reason=? WHERE case_id=?", (f"subject of pattern lead {row['id']} ({row['detector']}), approved by {approver.id}", case_id))
        conn.execute("UPDATE lead_requests SET status='approved', decided_by=?, decided_at=?, case_id=? WHERE id=?", (approver.id, now, case_id, request_id))
        conn.execute("UPDATE pattern_hits SET status='case_opened', case_id=?, decided_by=?, decided_at=? WHERE id=?", (case_id, approver.id, now, row["id"]))
    return {"case_id": case_id, "lead": row["id"], "subjects": len(subjects), "purpose": req["purpose"], "requested_by": req["requested_by"]}


def dismiss(store: Store, user: User, hit_id: str, reason: str) -> None:
    row = get_row(store, hit_id)
    if not user.has("io", "supervisor", "analyst") or not can_see(store, user, row):
        raise PolicyError("this lead is outside your agency's mission tracks or jurisdiction")
    if len(reason.strip()) < 10:
        raise PolicyError("give a reason (at least ten characters) for dismissing a lead")
    with store.tx() as conn:
        conn.execute("UPDATE pattern_hits SET status='dismissed', disposition=?, decided_by=?, decided_at=? WHERE id=?",
                     (reason.strip(), user.id, utcnow(), hit_id))

"""Guard: every read of non-public data passes through `Guard.decide`.

Rules (design doc 5.2 and 11.1), checked in order:

1. Separation of duties - auditors and admins never read operational data.
2. PUBLIC objects are readable by anyone (still audited).
3. Clearance - the user's clearance must be >= the object's sensitivity.
4. Purpose binding - a case must be active in the session (X-DRISHTI-Case).
5. The case must be open and the user must be a member of it.
6. Purpose limitation by record class - the case's purpose decides which record classes
   (financial, communications, movement, criminal background...) its members may read; an
   object admitted to the case scope through an audited action stays readable.
7. Jurisdiction (ABAC) - an object tied to a district must be in one of the user's
   districts, unless it is already inside the case scope (added through an audited
   add_to_case action). Place-less identifiers (phones, accounts) skip this check.

The same rules are written in Rego in policies/drishti.rego; set DRISHTI_OPA_URL and
Guard delegates every decision to OPA instead (fail-closed if OPA is unreachable).
"""

from __future__ import annotations

import json
import secrets
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from ..config import settings
from ..store import Store, make_id, normalize_identifier, utcnow
from .users import User

RETENTION_DAYS_AFTER_CLOSE = 365 * 2  # placeholder; set per statute / department policy


@dataclass(frozen=True)
class Decision:
    allow: bool
    reason: str


class PolicyError(PermissionError):
    pass


@dataclass
class CaseCtx:
    id: str
    purpose: str
    legal_basis: str
    status: str
    max_depth: int
    members: frozenset[str]
    scope: frozenset[str]
    record_classes: tuple[str, ...] = ()  # empty: derived from the purpose (ontology purpose_classes)

    def public(self) -> dict[str, Any]:
        return {"id": self.id, "purpose": self.purpose, "legal_basis": self.legal_basis, "status": self.status,
                "max_depth": self.max_depth, "members": sorted(self.members), "scope_size": len(self.scope),
                "record_classes": list(self.record_classes)}


class Guard:
    def __init__(self, store: Store):
        self.store = store
        self.ontology = store.ontology

    # ------------------------------------------------------------------ cases
    def load_case(self, case_id: str | None) -> CaseCtx | None:
        if not case_id:
            return None
        rows = self.store.query("SELECT * FROM cases WHERE id=?", (case_id,))
        if not rows:
            return None
        c = rows[0]
        members = frozenset(r["user_id"] for r in self.store.query("SELECT user_id FROM case_members WHERE case_id=?", (case_id,)))
        scope = frozenset(r["object_id"] for r in self.store.query("SELECT object_id FROM case_objects WHERE case_id=?", (case_id,)))
        return CaseCtx(c["id"], c["purpose"], c["legal_basis"], c["status"], c["max_depth"], members, scope,
                       self.ontology.purpose_classes(c["purpose"]))

    def cases_for(self, user: User) -> list[dict[str, Any]]:
        rows = self.store.query(
            "SELECT c.* FROM cases c JOIN case_members m ON m.case_id=c.id WHERE m.user_id=? ORDER BY c.opened_at DESC", (user.id,)
        )
        return [dict(r) for r in rows]

    def open_case(self, user: User, *, purpose: str, legal_basis: str, fir_no: str | None, members: list[str] | None = None,
                  title: str | None = None, subjects: list[str] | None = None) -> str:
        if not user.has("io", "supervisor"):
            raise PolicyError("only an IO or supervisor can open a case")
        if purpose not in self.ontology.purposes:
            raise PolicyError(f"purpose {purpose!r} is not an approved purpose")
        if self.ontology.agencies and purpose not in self.ontology.agency_purposes(user.agency):
            raise PolicyError(f"{purpose} is outside the mandate of {user.agency}")
        if len(legal_basis.strip()) < 10:
            raise PolicyError("legal basis must cite the FIR / order and the provisions relied on")
        case_id = f"CASE-{datetime.now(timezone.utc):%Y}-{secrets.token_hex(3).upper()}"
        now = utcnow()
        with self.store.tx() as conn:
            conn.execute(
                "INSERT INTO cases(id,purpose,legal_basis,fir_no,title,agency,opened_by,opened_at) VALUES(?,?,?,?,?,?,?,?)",
                (case_id, purpose, legal_basis.strip(), fir_no, title, user.agency, user.id, now),
            )
            for oid in subjects or []:
                conn.execute(
                    "INSERT INTO case_objects(case_id,object_id,added_by,reason,added_at) VALUES(?,?,?,?,?) ON CONFLICT DO NOTHING",
                    (case_id, oid, user.id, "named in the case record at opening", now),
                )
            for m in {user.id, *(members or [])}:
                conn.execute("INSERT INTO case_members(case_id,user_id) VALUES(?,?) ON CONFLICT DO NOTHING", (case_id, m))
            if fir_no:
                for r in conn.execute("SELECT object_id FROM identifiers WHERE kind='fir_no' AND value=?", (normalize_identifier(fir_no),)):
                    conn.execute(
                        "INSERT INTO case_objects(case_id,object_id,added_by,reason,added_at) VALUES(?,?,?,?,?) ON CONFLICT DO NOTHING",
                        (case_id, r["object_id"], user.id, "FIR named at case opening", now),
                    )
        return case_id

    def close_case(self, user: User, case: CaseCtx, outcome: str, retention_days: int | None = None) -> str:
        if user.id not in case.members or not user.has("io", "supervisor"):
            raise PolicyError("only a member IO or supervisor can close the case")
        days = RETENTION_DAYS_AFTER_CLOSE if retention_days is None else max(0, retention_days)
        until = (datetime.now(timezone.utc) + timedelta(days=days)).date().isoformat()
        with self.store.tx() as conn:
            conn.execute(
                "UPDATE cases SET status='closed', closed_at=?, outcome=?, retention_until=? WHERE id=?",
                (utcnow(), outcome, until, case.id),
            )
        return until

    def add_to_case(self, user: User, case: CaseCtx, object_id: str, reason: str) -> None:
        self._require_member(user, case)
        if len(reason.strip()) < 5:
            raise PolicyError("a reason is required to bring an object into the case")
        obj = self.store.get_object(object_id)
        if not obj:
            raise PolicyError("no such object")
        # Evidence rule: the object must be linked to something already in scope.
        linked = any(
            (l["src"] in case.scope or l["dst"] in case.scope) for l in self.store.links_for([object_id])
        ) or not case.scope
        if not linked:
            raise PolicyError("object has no recorded link to the case scope; attach evidence first")
        with self.store.tx() as conn:
            conn.execute(
                "INSERT INTO case_objects(case_id,object_id,added_by,reason,added_at) VALUES(?,?,?,?,?) ON CONFLICT DO NOTHING",
                (case.id, object_id, user.id, reason.strip(), utcnow()),
            )

    def request_expansion(self, user: User, case: CaseCtx, depth: int, reason: str) -> str:
        self._require_member(user, case)
        if depth not in (2, 3):
            raise PolicyError("expansion depth must be 2 or 3")
        req_id = make_id("expansion", case.id, f"{depth}|{utcnow()}|{secrets.token_hex(2)}")
        with self.store.tx() as conn:
            conn.execute(
                "INSERT INTO expansion_requests(id,case_id,depth,reason,requested_by,requested_at) VALUES(?,?,?,?,?,?)",
                (req_id, case.id, depth, reason, user.id, utcnow()),
            )
        return req_id

    def approve_expansion(self, user: User, request_id: str) -> dict[str, Any]:
        rows = self.store.query("SELECT * FROM expansion_requests WHERE id=?", (request_id,))
        if not rows or rows[0]["status"] != "pending":
            raise PolicyError("no pending request with that id")
        req = rows[0]
        if not user.has("supervisor"):
            raise PolicyError("only a supervisor can approve expansion")
        if req["requested_by"] == user.id:
            raise PolicyError("two-person rule: the requester cannot approve their own request")
        with self.store.tx() as conn:
            conn.execute("UPDATE expansion_requests SET status='approved', decided_by=?, decided_at=? WHERE id=?", (user.id, utcnow(), request_id))
            conn.execute(f"UPDATE cases SET max_depth={self.store.greatest('max_depth', 'CAST(? AS INTEGER)')} WHERE id=?",
                         (int(req["depth"]), req["case_id"]))
        return dict(req)

    def _require_member(self, user: User, case: CaseCtx | None) -> None:
        if case is None:
            raise PolicyError("no active case: select or open a case to state your purpose")
        if case.status != "open":
            raise PolicyError("case is closed")
        if user.id not in case.members:
            raise PolicyError("you are not a member of this case")

    # ------------------------------------------------------------------ decisions
    def decide(self, user: User, case: CaseCtx | None, obj: dict[str, Any]) -> Decision:
        if settings.opa_url:
            return self._decide_opa(user, case, obj)
        return self._decide_local(user, case, obj)

    def _decide_local(self, user: User, case: CaseCtx | None, obj: dict[str, Any]) -> Decision:
        if user.has("auditor", "admin") and not user.has("io", "supervisor", "analyst", "viewer", "operator", "collector"):
            if obj["sensitivity"] == 0:
                return Decision(True, "public")
            return Decision(False, "separation of duties: oversight and admin roles cannot read operational data")
        if obj["sensitivity"] == 0:
            return Decision(True, "public")
        if user.clearance < obj["sensitivity"]:
            return Decision(False, "clearance below object sensitivity")
        if case is None:
            return Decision(False, "purpose required: no active case")
        if case.status != "open":
            return Decision(False, "case is closed")
        if user.id not in case.members:
            return Decision(False, "not a member of the active case")
        if self.ontology.record_classes and obj["id"] not in case.scope:
            classes = case.record_classes or self.ontology.purpose_classes(case.purpose)
            if self.ontology.record_class_of(obj["type"]) not in classes:
                return Decision(False, "record class outside the case purpose")
        # Jurisdiction binds objects that are tied to a place. Identifiers with no district
        # (phone numbers, accounts, handsets) are governed by case membership and purpose alone.
        district = obj.get("district_lgd")
        if district and "*" not in user.districts and district not in user.districts and obj["id"] not in case.scope:
            return Decision(False, "outside jurisdiction and not in case scope")
        return Decision(True, "case member within clearance and jurisdiction")

    def opa_input(self, user: User, case: CaseCtx | None, obj: dict[str, Any]) -> dict[str, Any]:
        classes = list(case.record_classes or self.ontology.purpose_classes(case.purpose)) if case else []
        return {
            "user": {"id": user.id, "roles": sorted(user.roles), "clearance": user.clearance, "districts": list(user.districts)},
            "case": case.public() | {"scope_contains_object": obj["id"] in case.scope, "record_classes": classes} if case else None,
            "object": {"id": obj["id"], "type": obj["type"], "sensitivity": obj["sensitivity"], "district": obj.get("district_lgd"),
                       "record_class": self.ontology.record_class_of(obj["type"])},
        }

    def _decide_opa(self, user: User, case: CaseCtx | None, obj: dict[str, Any]) -> Decision:
        payload = {"input": self.opa_input(user, case, obj)}
        req = urllib.request.Request(
            settings.opa_url.rstrip("/") + "/v1/data/drishti/access/decision",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=2) as r:
                result = json.load(r).get("result") or {}
        except Exception:  # noqa: BLE001 - fail closed
            return Decision(False, "policy engine unreachable (fail-closed)")
        return Decision(bool(result.get("allow")), result.get("reason", "opa"))

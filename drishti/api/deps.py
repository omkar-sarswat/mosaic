"""Request context shared by every API module: services, the acting user, the active case."""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
from typing import Any

from fastapi import Header, HTTPException, Request

from ..config import settings
from ..guard import DEV_USERS, AuditLog, AuthError, CaseCtx, Decision, Guard, User, mask_object, verify_bearer
from ..store import Store


class Services:
    def __init__(self, store: Store):
        self.store = store
        self.guard = Guard(store)
        self.audit = AuditLog(store)
        self.ontology = store.ontology

    @cached_property
    def district_names(self) -> dict[str, str]:
        return {o["props"]["lgd_code"]: o["props"]["name"] for o in self.store.objects_of_type("AdminUnit") if o["props"].get("level") == "district"}


_services: Services | None = None


def services() -> Services:
    global _services
    if _services is None:
        _services = Services(Store(settings.db_target))
    return _services


def set_services(s: Services) -> None:
    """Used by tests to point the app at a temporary store."""
    global _services
    _services = s


@dataclass
class Ctx:
    svc: Services
    user: User
    case: CaseCtx | None
    client: str

    def decide(self, obj: dict[str, Any]) -> Decision:
        return self.svc.guard.decide(self.user, self.case, obj)

    def log(self, action: str, *, detail: dict[str, Any] | None = None, object_ids: list[str] | None = None, outcome: str = "ok") -> None:
        self.svc.audit.append(
            user_id=self.user.id, role=self.user.primary_role, action=action, outcome=outcome,
            case_id=self.case.id if self.case else None, purpose=self.case.purpose if self.case else None,
            detail=detail, object_ids=object_ids, client=self.client,
        )

    def require_role(self, *roles: str) -> None:
        if not self.user.has(*roles):
            self.log("role_check", detail={"needed": list(roles)}, outcome="denied")
            raise HTTPException(403, f"requires role: {' or '.join(roles)}")

    def summary(self, obj: dict[str, Any]) -> dict[str, Any]:
        m = mask_object(self.svc.ontology, obj, self.user.clearance)
        return {
            "id": m["id"], "type": m["type"], "title": m["title"], "district": m.get("district_lgd"),
            "district_name": self.svc.district_names.get(m.get("district_lgd") or ""), "sensitivity": m["sensitivity"],
            "synthetic": m["synthetic"], "masked": m["masked"], "props": {k: v for k, v in m["props"].items() if not k.startswith("_")}, "lat": m.get("lat"), "lon": m.get("lon"),
        }


def get_ctx(
    request: Request,
    x_drishti_user: str | None = Header(default=None),
    x_drishti_case: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> Ctx:
    svc = services()
    if settings.auth_mode == "oidc":
        if not authorization or not authorization.lower().startswith("bearer "):
            raise HTTPException(401, "bearer token required")
        try:
            user = verify_bearer(authorization.split(" ", 1)[1])
        except AuthError as exc:
            raise HTTPException(401, f"invalid token: {exc}") from None
    else:
        user = DEV_USERS.get(x_drishti_user or "")
        if user is None:
            raise HTTPException(401, "unknown user; dev mode expects X-DRISHTI-User (see /api/dev/users)")
    case = svc.guard.load_case(x_drishti_case) if x_drishti_case else None
    if x_drishti_case and case is None:
        raise HTTPException(404, "no such case")
    client = request.client.host if request.client else "unknown"
    return Ctx(svc, user, case, client)

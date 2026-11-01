"""Users and authentication.

dev  mode: a fixed roster of role-based demo users, picked with the X-DRISHTI-User header.
           Only ever used with open and synthetic data.
oidc mode: Keycloak (or any OIDC provider) issues RS256 JWTs; we verify signature, issuer,
           audience and expiry against the provider's JWKS and read roles and attributes
           (clearance, districts, agency) from token claims.
"""

from __future__ import annotations

import json
import time
import urllib.request
from dataclasses import dataclass, field

from ..config import settings


@dataclass(frozen=True)
class User:
    id: str
    name: str
    roles: frozenset[str]
    clearance: int  # 0 PUBLIC .. 3 SECRET
    districts: tuple[str, ...]  # LGD district codes, or ("*",) for statewide
    agency: str = "STATE-POLICE-MH"
    attrs: dict = field(default_factory=dict, hash=False, compare=False)

    @property
    def primary_role(self) -> str:
        for r in ("auditor", "admin", "supervisor", "io", "analyst", "collector", "operator", "viewer", "steward"):
            if r in self.roles:
                return r
        return next(iter(self.roles), "viewer")

    def has(self, *roles: str) -> bool:
        return bool(self.roles & set(roles))

    def public(self) -> dict:
        return {
            "id": self.id, "name": self.name, "roles": sorted(self.roles), "role": self.primary_role,
            "clearance": self.clearance, "districts": list(self.districts), "agency": self.agency,
        }


# Demo roster. Names are role titles, not real people. Central agencies have national
# jurisdiction ("*") and SECRET clearance; state users are bound to their districts.
DEV_USERS: dict[str, User] = {
    u.id: u
    for u in [
        User("ed.dd", "Deputy Director, ED Mumbai Zonal Office", frozenset({"io"}), 3, ("*",), agency="ED"),
        User("ed.jd", "Joint Director, ED (approving officer)", frozenset({"supervisor"}), 3, ("*",), agency="ED"),
        User("cbi.dsp", "DSP, CBI Bank Securities & Fraud Cell", frozenset({"io"}), 3, ("*",), agency="CBI"),
        User("cbi.sp", "Superintendent of Police, CBI (approving officer)", frozenset({"supervisor"}), 3, ("*",), agency="CBI"),
        User("ncb.supervisor", "Zonal Director, NCB (approving officer)", frozenset({"supervisor"}), 3, ("*",), agency="NCB"),
        User("nia.sp", "Superintendent of Police, NIA (Terror Financing)", frozenset({"io"}), 3, ("*",), agency="NIA"),
        User("nia.ig", "Inspector General, NIA (approving officer)", frozenset({"supervisor"}), 3, ("*",), agency="NIA"),
        User("ncb.io", "Intelligence Officer, NCB Mumbai Zonal Unit", frozenset({"io"}), 3, ("*",), agency="NCB"),
        User("ib.analyst", "Analyst, Intelligence Bureau (MAC)", frozenset({"analyst"}), 3, ("*",), agency="IB"),
        User("ib.ad", "Assistant Director, Intelligence Bureau", frozenset({"io"}), 3, ("*",), agency="IB"),
        User("ib.jd", "Joint Director, Intelligence Bureau (approving officer)", frozenset({"supervisor"}), 3, ("*",), agency="IB"),
        User("raw.io", "Deputy Secretary, R&AW cross-border desk", frozenset({"io"}), 3, ("*",), agency="RAW"),
        User("raw.director", "Joint Secretary, R&AW (approving officer)", frozenset({"supervisor"}), 3, ("*",), agency="RAW"),
        User("crime.pi", "Police Inspector, Crime Branch Pune (Anti-Extortion Cell)", frozenset({"io"}), 2, ("490",)),
        User("cyber.io", "Inspector, Maharashtra Cyber", frozenset({"io"}), 2, ("*",), agency="MAHARASHTRA-CYBER"),
        User("io.pune", "Investigating Officer, Pune Cyber PS", frozenset({"io"}), 2, ("490",)),
        User("sp.pune", "Superintendent of Police, Pune Rural", frozenset({"supervisor"}), 2, ("490", "487", "494")),
        User("analyst.scrb", "Analyst, SCRB Maharashtra", frozenset({"analyst"}), 2, ("*",)),
        User("constable.pune", "Constable, Pune", frozenset({"viewer"}), 1, ("490",)),
        User("operator.sdma", "Control-room operator, MSDMA", frozenset({"operator"}), 0, ("*",), agency="MSDMA"),
        User("auditor.oversight", "Oversight officer (independent)", frozenset({"auditor"}), 0, ("*",), agency="OVERSIGHT"),
        User("admin.it", "Platform administrator", frozenset({"admin"}), 0, ("*",), agency="STATE-IT"),
    ]
}


class AuthError(Exception):
    pass


_jwks_cache: dict = {"at": 0.0, "keys": None}


def _jwks() -> dict:
    if _jwks_cache["keys"] is None or time.time() - _jwks_cache["at"] > 600:
        url = settings.oidc_jwks_url or settings.oidc_issuer + "/protocol/openid-connect/certs"
        with urllib.request.urlopen(url, timeout=10) as r:
            _jwks_cache.update(keys=json.load(r), at=time.time())
    return _jwks_cache["keys"]


DRISHTI_ROLES = {"io", "supervisor", "analyst", "viewer", "operator", "collector", "auditor", "admin", "steward"}


def user_from_claims(claims: dict) -> User:
    roles = set(claims.get("realm_access", {}).get("roles", [])) & DRISHTI_ROLES
    if not roles:
        # least privilege: an account in the identity provider with no DRISHTI role gets no access at all
        raise AuthError("no Mosaic role assigned to this account")
    districts = claims.get("districts") or []
    if isinstance(districts, str):
        districts = [d.strip() for d in districts.split(",") if d.strip()]
    return User(
        id=claims.get("preferred_username") or claims["sub"],
        name=claims.get("name") or claims.get("preferred_username") or claims["sub"],
        roles=frozenset(roles),
        clearance=int(claims.get("clearance", 0)),
        districts=tuple(districts),
        agency=claims.get("agency", "UNKNOWN"),
    )


def verify_bearer(token: str, jwks: dict | None = None) -> User:
    import jwt  # PyJWT

    try:
        header = jwt.get_unverified_header(token)
        keys = (jwks or _jwks())["keys"]
        if jwks is None and not any(k.get("kid") == header.get("kid") for k in keys) and time.time() - _jwks_cache["at"] > 60:
            _jwks_cache["keys"] = None  # the provider rotated its signing key: fetch the key set again (at most once a minute)
            keys = _jwks()["keys"]
        jwk = next(k for k in keys if k.get("kid") == header.get("kid"))
        key = jwt.PyJWK(jwk).key
        claims = jwt.decode(token, key=key, algorithms=["RS256"], audience=settings.oidc_audience, issuer=settings.oidc_issuer,
                            options={"require": ["exp", "iss", "aud", "sub"]})
    except StopIteration:
        raise AuthError("unknown signing key") from None
    except jwt.PyJWTError as exc:
        raise AuthError(str(exc)) from None
    return user_from_claims(claims)

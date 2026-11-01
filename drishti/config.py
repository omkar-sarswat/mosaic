"""Runtime settings. Everything is overridable with DRISHTI_* environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# DRISHTI_HOME points at the folder holding ontology/, data/, policies/ and web/dist
# (the repo root in development, /app in the container).
ROOT = Path(os.environ.get("DRISHTI_HOME", Path(__file__).resolve().parents[1]))


@dataclass(frozen=True)
class Settings:
    db_path: Path = field(default_factory=lambda: Path(os.environ.get("DRISHTI_DB", ROOT / "var" / "drishti.db")))
    # PostgreSQL instead of the SQLite file: postgresql://user:password@host:port/db (optionally ?schema=name).
    # Files kept next to the database (evidence, media, exports, models) stay under db_path's folder.
    db_url: str | None = field(default_factory=lambda: os.environ.get("DRISHTI_DB_URL") or None)

    @property
    def db_target(self) -> Path | str:
        return self.db_url or self.db_path
    ontology_path: Path = field(default_factory=lambda: Path(os.environ.get("DRISHTI_ONTOLOGY", ROOT / "ontology" / "core.yaml")))
    reference_dir: Path = ROOT / "data" / "reference"
    samples_dir: Path = ROOT / "data" / "samples"
    web_dist: Path = ROOT / "web" / "dist"
    # "dev": users chosen with the X-DRISHTI-User header (synthetic data only).
    # "oidc": bearer JWTs from Keycloak verified against its JWKS.
    auth_mode: str = field(default_factory=lambda: os.environ.get("DRISHTI_AUTH", "dev"))
    oidc_issuer: str = field(default_factory=lambda: os.environ.get("DRISHTI_OIDC_ISSUER", "http://localhost:8080/realms/drishti"))
    oidc_audience: str = field(default_factory=lambda: os.environ.get("DRISHTI_OIDC_AUDIENCE", "drishti-api"))
    # the public client the web app signs in with (Authorization Code + PKCE)
    oidc_client_id: str = field(default_factory=lambda: os.environ.get("DRISHTI_OIDC_CLIENT_ID", "drishti-web"))
    # Inside docker compose the issuer (as browsers see it) and the JWKS host differ.
    oidc_jwks_url: str = field(default_factory=lambda: os.environ.get("DRISHTI_OIDC_JWKS_URL", ""))
    # Dev auth (users picked by header) answers only this machine unless this is set, e.g. inside a container
    # whose port is published on 127.0.0.1 only (deploy/docker-compose.yml).
    dev_auth_network: bool = field(default_factory=lambda: os.environ.get("DRISHTI_DEV_AUTH_NETWORK") == "1")
    # When set, Guard asks OPA for every decision instead of the built-in policy.
    opa_url: str | None = field(default_factory=lambda: os.environ.get("DRISHTI_OPA_URL"))
    # Hours (IST) treated as "after hours" by insider-threat analytics.
    after_hours: tuple[int, int] = (22, 6)
    # Resolver thresholds (Section 12.2 of the design doc).
    auto_link_threshold: float = 0.95
    review_threshold: float = 0.70
    # trained Fellegi-Sunter parameters (drishti train matcher --adopt); hand-set ones are used when absent
    matcher_params: Path = field(default_factory=lambda: Path(os.environ.get("DRISHTI_MATCHER_PARAMS", ROOT / "models" / "matcher.json")))


settings = Settings()

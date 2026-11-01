# Deployment and configuration

Mosaic ships a local demonstration and deployment building blocks. A production installation requires its own identity provider, access-policy review, database and backup configuration, network controls, and operational validation. The brochure’s deployment scenarios describe the intended product scope; this repository does not establish a certified or field-proven deployment.

## Configuration

Settings are read from environment variables in [`drishti/config.py`](../drishti/config.py). The application does not automatically load a root `.env` file; set variables in the shell, service manager, or container environment.

| Variable | Default / purpose |
| --- | --- |
| `DRISHTI_HOME` | Repository root; contains `ontology/`, `data/`, `policies/`, and `web/dist/`. |
| `DRISHTI_DB` | `var/drishti.db`; SQLite path and anchor for adjacent runtime files. |
| `DRISHTI_DB_URL` | Optional PostgreSQL connection URL. Takes precedence for database connections. |
| `DRISHTI_AUTH` | `dev` for synthetic local accounts; `oidc` for bearer-token identity. |
| `DRISHTI_DEV_AUTH_NETWORK` | Unset by default. `1` permits development identity mode beyond loopback; the Compose demo uses it inside the container while publishing only to localhost. |
| `DRISHTI_OIDC_ISSUER` | `http://localhost:8080/realms/drishti`. |
| `DRISHTI_OIDC_AUDIENCE` | `drishti-api`. |
| `DRISHTI_OIDC_CLIENT_ID` | `drishti-web`. |
| `DRISHTI_OIDC_JWKS_URL` | Optional internal JWKS URL when the provider has a different container hostname. |
| `DRISHTI_OPA_URL` | Optional Open Policy Agent endpoint. |
| `DRISHTI_ONTOLOGY` | Override the ontology YAML path. |
| `DRISHTI_MATCHER_PARAMS` | Override the matcher-parameter JSON path. |

## Local server

After building the frontend and creating the demo database:

```bash
drishti serve --host 127.0.0.1 --port 8000
```

The default host is loopback. Development identities are for synthetic demonstrations. For an operational installation, use OIDC and validate its role, agency, and clearance mappings before introducing institutional records.

## Containers

[`deploy/docker-compose.yml`](../deploy/docker-compose.yml) defines the app, Open Policy Agent, and an optional Keycloak profile. The app’s published port binds to localhost, and runtime data uses a named volume.

The Compose file contains a required `KEYCLOAK_ADMIN_PASSWORD` interpolation. Set it even when the optional SSO profile is not selected, because Compose implementations may validate it while loading the file. Supply a local password through your environment or a private Compose environment file; never commit it.

```bash
docker compose -f deploy/docker-compose.yml up --build
```

For the bundled development Keycloak instance, also set `DRISHTI_AUTH=oidc` and enable the profile:

```bash
docker compose -f deploy/docker-compose.yml --profile sso up --build
```

Review the imported [realm](../deploy/keycloak/drishti-realm.json) and provision appropriate accounts. The realm is configuration, not a set of live credentials. The included Keycloak command uses `start-dev`; production identity hosting needs a separate deployment configuration. See the existing [security assessment](research/11-security-review.md) for historical review scope and remaining infrastructure work.

## PostgreSQL

```bash
python -m pip install -e ".[postgres]"
```

Set `DRISHTI_DB_URL` to your provisioned connection string outside version control. Retain a dedicated `DRISHTI_DB` path for evidence, media, and other local files. The selected database must permit the schema and tables used by the storage layer.

For a **new disposable PostgreSQL demonstration database**, use explicit population commands:

```bash
drishti init
drishti seed
drishti resolve
drishti patterns run
drishti serve
```

These individual commands do not reproduce every enrichment and case-opening step in the complete SQLite demo pipeline. Inspect [`pipeline.py`](../drishti/pipeline.py) when preparing a full PostgreSQL demonstration. The `demo` command’s reuse and `--fresh` behaviour is based on a local SQLite path; do not treat it as a PostgreSQL reset or migration tool.

## Operational boundaries

- **External resources:** basemap tiles, live SACHET ingestion, model downloads, and remote OIDC require connectivity or local replacements.
- **Evidence exports:** the application can produce evidence packages and a draft BSA certificate. Review and signing are separate human steps; generating a file does not establish its legal acceptance.
- **Audit:** the chain supports detection of record changes. Protect the database, signing/seal workflow, backups, and administrators independently.
- **Capacity:** validate your workload on the chosen storage and infrastructure. Historical synthetic benchmarks do not establish state-scale service levels.
- **Maps:** the demonstration uses an external basemap. Select an appropriate basemap and boundary policy for the institution deploying it.

[Documentation index](README.md).

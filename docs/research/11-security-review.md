# 11 · Internal security review and the brief for an independent one

*16 October 2026. This is an internal review by the development team. It does not replace an independent assessment: Section 4 is the brief for that assessment, which a CERT-In-empanelled auditor should carry out before any real data is loaded.*

## 1. Scope and method

**What was reviewed:**
- authentication (dev mode and OIDC);
- token handling in the browser;
- every SQL statement built with string formatting;
- uploads and downloads (evidence, photographs, exports);
- HTTP response headers;
- HTML outputs (web UI, case report);
- outbound network calls;
- secrets in the repository and the deployment files;
- third-party packages.

**How each finding was checked:**
- with a regression test in `tests/test_security.py`;
- with a real Keycloak 26.4.2 and a headless browser (`scripts/oidc_login_check.py`);
- with dependency audits (`pip-audit`, `npm audit`).

## 2. Findings

| # | Finding | Severity | Status |
|---|---|---|---|
| 1 | **The realm file shipped a known password** ("demo-only-change-me") for every account. Keycloak's import does not force a change of a password marked temporary, so anyone with the public repository could sign in to a fresh deployment. | Critical | **Fixed.** No passwords in the realm. Every account must set a password and enrol an authenticator app (TOTP) at first sign-in. `scripts/keycloak_users.py` issues random one-time passwords through the admin API. Verified end to end. |
| 2 | **Dev auth trusts a header** (`X-DRISHTI-User`) to say who the user is. Served on a network address, anyone could act as any officer. | High | **Fixed.** In dev mode the API answers only this machine (403 otherwise). The container sets `DRISHTI_DEV_AUTH_NETWORK=1` because its port is published on 127.0.0.1 only. Test: `test_dev_auth_refuses_clients_on_the_network`. |
| 3 | **An identity-provider account with no DRISHTI role got "viewer" access.** | High | **Fixed.** No DRISHTI role means no access (least privilege). |
| 4 | **No security headers.** There was no Content-Security-Policy and no framing protection (clickjacking), and API responses carrying case data could be cached by browsers and proxies. | Medium | **Fixed.** Every response now carries: <ul><li>a strict CSP (`script-src 'self'`, `frame-ancestors 'none'`, only the map-tile host and the identity provider allowed);</li><li>`X-Frame-Options`, `nosniff`, `Referrer-Policy: no-referrer`, a Permissions-Policy and COOP;</li><li>HSTS behind HTTPS;</li><li>`Cache-Control: no-store` on `/api/`.</li></ul>All 10 main screens and the data studio load with no policy violations. |
| 5 | **Tokens without an expiry or subject** would have been accepted. Key rotation at the provider broke sign-in for up to 10 minutes. | Medium | **Fixed.** `exp`, `iss`, `aud` and `sub` are required. An unknown signing key triggers one key-set refresh, at most once a minute. |
| 6 | **Unbounded photograph uploads.** A 200 KB PNG can declare 64+ megapixels; OpenCV's own ceiling is 1 gigapixel (~3 GB decoded). | Medium | **Fixed.** 15 MB and 50 megapixels per photograph; refused cleanly (not as a server error). The test uses a valid 64 MP image of ~200 KB. |
| 7 | **No request-size limit** on JSON bodies. | Medium | **Fixed.** 25 MB (210 MB on the evidence route). Bodies sent without a declared length are bounded only by the evidence handler. Recommendation: enforce at the reverse proxy too. |
| 8 | **Download filenames were placed in `Content-Disposition` unescaped.** A stored name with quotes broke the header. | Low | **Fixed.** RFC 6266 form, with an ASCII fallback and `filename*`. |
| 9 | **Default Keycloak admin password** in docker-compose ("change-me-now"). | Medium | **Fixed.** No default; compose refuses to start without one. |
| 10 | **Weak realm policy.** No MFA, no password policy, 15-minute access tokens, refresh tokens reusable, no login events. | Medium | **Fixed.** <ul><li>TOTP required.</li><li>Password policy: 12+ characters with a digit, an upper-case letter and a special character; not the username; history of 5.</li><li>Brute-force lockout.</li><li>5-minute access tokens and refresh-token rotation.</li><li>30-minute idle and 10-hour maximum sessions.</li><li>Login and admin events kept for 90 days.</li><li>Implicit and password grants off.</li></ul> |
| 11 | **Known vulnerabilities in packages.** | Low | `pip` 24.2 (installer only) had 7 advisories; upgraded to 26.2.1. `pip-audit`: no known vulnerabilities. `npm audit --omit=dev`: 0. |
| — | **SQL injection** | — | **None found.** Every value travels as a parameter. String-formatted SQL only inserts fixed column names or `?` placeholder lists (checked line by line). |
| — | **Stored script injection** | — | **None found.** The web UI has no raw-HTML sinks (`dangerouslySetInnerHTML`, `setHTML`, `innerHTML`). The HTML case report escapes every text value. |
| — | **Path traversal** | — | **None found.** Evidence and photographs are stored under their SHA-256 hash. Export folders are named from a case ID that is checked against the caller's membership first. |
| — | **Tokens in the browser** | — | **Held in memory only.** Verified: nothing in `localStorage` or `sessionStorage` after sign-in. A reload returns through the provider's session cookie. |
| — | **Outbound requests (SSRF)** | — | **None from user input.** The only outbound fetch is the fixed NDMA SACHET feed (command line). |

## 3. What this review did not cover

- **Penetration testing, fuzzing and source review by an independent party.** Only that gives assurance; this review only reduces what it will find.
- **Infrastructure:**
  - TLS termination;
  - network segmentation;
  - database encryption at rest (PostgreSQL's TDE or disk encryption);
  - backups and key management;
  - operating-system hardening.
- **Rate limiting and denial-of-service resistance at the API.** Recommended at the reverse proxy: per-user request rate and connection limits.
- **Insider misuse beyond what the audit log, canaries, two-person rules and purpose binding already address.**
- **The face-recognition model's accuracy and bias.** That is a separate evaluation.

## 4. Brief for an independent assessment

**Engagement:** a CERT-In-empanelled organisation, or a state police IT security cell with equivalent standing, under a signed scope and rules of engagement. Use synthetic data only (`drishti demo`), never real records.

**System:**
- FastAPI service (`drishti serve`), React web app, Keycloak for identity, PostgreSQL 18 or SQLite, optional OPA for policy.
- Architecture: `docs/research/02`, `08`, `09`.
- Safeguards: purpose-bound case scoping, two-person rules for expansion, publishing and lead-to-case, a hash-chained append-only audit log, canary records, clearance masking.

**Test accounts:** created for the engagement with `scripts/keycloak_users.py`. They cover the roles investigating officer, supervisor, analyst, data steward and auditor, in two agencies and two districts.

**Priority test objectives:**
1. Reach another case's objects, another agency's leads or a higher-clearance property: horizontal and vertical access control.
2. Defeat a two-person rule: approve one's own expansion, publication or lead request.
3. Tamper with the audit or custody log without detection: `drishti audit verify` and the sealed daily roots.
4. Forge, replay or misuse tokens: audience, issuer, algorithm, expiry, revoked sessions.
5. Inject into intake files (CSV/XLSX/PDF), photographs and exports. Check formula injection in anything opened in a spreadsheet, and parser bombs.
6. Abuse dev mode or misconfiguration in the deployment files.
7. Extract data through search, the pattern engine's leads or the AI-assisted surfaces without a case and purpose.

**Deliverables:** findings with severity (CVSS 4.0), reproduction steps, and a retest after fixes. Publish the summary with the oversight body's agreement.

## 5. How to reproduce

- **Tests:** `pytest tests/test_security.py tests/test_oidc.py`
- **Browser check:**
  1. Start Keycloak with the realm (`deploy/keycloak`).
  2. Run `python scripts/keycloak_users.py --admin-password-file <file> --out <file> io.pune`.
  3. Serve DRISHTI with `DRISHTI_AUTH=oidc`.
  4. Run `python scripts/oidc_login_check.py <url> io.pune <one-time password> <new password>`.
- **Dependency audits:** `pip-audit --path .venv/Lib/site-packages` and `npm audit --omit=dev` in `web/`.

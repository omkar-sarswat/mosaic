# 06 · Lessons from the build: defects that only appeared end to end

Each defect below was found by running the real system: the live feed, the Docker stack, headless-browser walkthroughs, or the benchmark. Unit tests on isolated functions had passed. Each one teaches a rule for the team.

| # | Defect | How it was found | Fix | Rule |
|---|---|---|---|---|
| 1 | **Rego treated a JSON `null` district as "outside jurisdiction".** In Rego, `not x` is true only when `x` is undefined or `false`, and `null` is a value. Under OPA, every bank account, phone and handset (which have no district) would have been hidden from investigators, while the Python policy allowed them. | A parity test that runs `opa eval` on 144 user × case × object combinations against the Python policy | Added `in_jurisdiction if input.object.district == null` | When a policy exists in two languages, test them against each other on the same inputs |
| 2 | **Jurisdiction rule blocked place-less identifiers** in the Python policy too (before #1 existed) | API test: the case graph showed only the incident and the police station | Jurisdiction applies only to objects tied to a district | Write ABAC rules for every object type in the ontology, not just the ones you were thinking of |
| 3 | **MapLibre v6 could not start its web worker** in the production build: it resolves the worker relative to `import.meta.url`, which the bundler rewrites. The map was blank in every browser. | A headless Chrome walkthrough that read the console (`Worker failed to load`) | `setWorkerUrl()` with Vite's `?url` asset, and serve `.mjs` as `text/javascript` | Test the *built* artefact, not only the dev server |
| 4 | **Schwa deletion corrupted long vowels**: संगीता → "Sangit", because long ā had been folded to `a` before the schwa rule ran | Reading the review-queue screenshot | Run schwa deletion on IAST, fold to ASCII afterwards | Do linguistic rules in the representation that still carries the distinction |
| 5 | **A hand-set prior (1e-4) cut entity-resolution recall to 51%** | The benchmark against ground truth | Estimate the prior from data (Splink method) | Never hand-tune what can be estimated |
| 6 | **Term-frequency adjustment broke on tiny datasets**: one name appearing twice out of three records looked "very common" | A three-record unit test of an obvious match | Apply TF only with ≥100 records and ≥3 occurrences | Statistical corrections need a minimum sample size |
| 7 | **A contradicting initial was not a conflict**: "N. Y. Sayyed" auto-linked to "Rukhsar Yoosuf Sayyed" (p = 0.986) | Error analysis of auto-link false positives | An unexplained initial facing an unexplained given name is a contradiction | Look at the false positives one by one; they are the harm |
| 8 | **Search returned nothing in-jurisdiction** because the top 40 hits were taken *before* the policy filter | Manual API test as a Pune IO | Over-fetch candidates, filter by policy, then truncate | Ranking and access control interact; filter before you truncate |
| 9 | **The review queue tripped the "bulk personal lookup" insider alert** for every analyst who opened it | Oversight screenshot | Sanctioned bulk workflows are audited but excluded from volume rules | An alert that always fires gets ignored; tune insider rules against normal work |
| 10 | **Uniform synthetic population** left a Pune IO with almost no local results | Searching as the IO | Weight districts by approximate Census 2011 population | Synthetic data must match the real distribution the users will see |
| 11 | **SACHET polygons are not in the CAP file** and the polygon URL returns 403 | Fetching live alerts | Geocode from LGD codes, then the name gazetteer | Read the live feed before designing the connector |
| 12 | **One commit per statement made ingest 22× slower** (78 s → 3.5 s once batched) | Timing the generator | Re-entrant transactions around bulk loads | Measure before optimising, but measure |

## What the verification covered

- **61 automated tests:** names across 8 scripts, matcher levels, ontology patterns, policy rules, red-line purposes, the two-person rule, audit-chain tamper detection, canary alerts, connectors against the saved SACHET snapshot, OIDC token verification with local RSA keys, API end to end, and Rego/Python parity.
- **Docker:** the image builds (82 s). Compose ran the app with OPA as the decision engine. The case graph through OPA included accounts and phones. Without a case, the request was refused. With OPA stopped, personal data was refused (fail-closed) while public map data was still served. After restarting OPA, it recovered.
- **Headless-browser walkthrough** of all five apps as five different roles (`puppeteer-core` against the built UI).

Not verified in this session: the Keycloak realm import and an OIDC login flow in the UI (the UI has none yet); PostgreSQL/AGE (not yet implemented); performance at state scale.

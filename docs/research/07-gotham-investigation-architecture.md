# 07 · From financial dashboard to cross-domain investigations

Research date: 14 October 2026. This document separates **documented reference capabilities**, **observed repository gaps**, and **proposed DRISHTI engineering work**. Scope is a bounded, authorized case-evidence workspace and independent evaluation. It excludes indiscriminate personal tracking, biometric identification, population-wide behaviour scoring and automated judgments about guilt. Proposed acceptance criteria are targets, not test results. This research does not establish proprietary Gotham parity, production accreditation, or a claim that any model is the world's best.

## What the public Gotham material actually establishes

Palantir's service definition describes a common data foundation with permissioned collaboration. Browser presents objects, properties, relationships and change history; searches span integrated and federated data with source attribution. Custom Object Views can vary by team. Graph provides a shared investigative canvas with search-around, annotations, tables and timelines. Dossier can embed objects linked to their source. Gaia supplies collaborative geospatial views. These are connected workflows across domains, rather than a dashboard organised exclusively around financial transactions. [Palantir Gotham service definition, sections 1.2 and 1.4](https://assets.applytosupply.digitalmarketplace.service.gov.uk/g-cloud-14/documents/92736/801146272055049-service-definition-document-2024-11-26-1253.pdf)

The public object API represents instances of typed objects and supports property queries and links. This is the useful foundation for a person, organisation, vehicle, document, location or incident sharing one navigational model. [Object API](https://www.palantir.com/docs/gotham/api/v1/revdb-resources/objects/object-basics)

Federation queries configured external systems using their advertised query shapes. Federated results can expose properties and links but cannot be updated through that API. This is configured access, not a mechanism for discovering every record on the internet or accessing an unconnected agency. [Federated sources](https://www.palantir.com/docs/gotham/api/revdb-resources/federated-sources/federated-source-basics)

Gotham resolution combines objects while retaining constituent histories and supports reversing a mistaken resolution. The documentation establishes those semantics; it does not disclose a universally superior matching model. [Object resolution](https://www.palantir.com/docs/gotham/api/revdb-resources/resolution/resolution-basics)

Its Geotime API distinguishes a time/place observation from a track containing observations of an entity, and separates static from changing properties. [Observation API](https://www.palantir.com/docs/gotham/api/v1/geotime-resources/observations/observation-basics)

Palantir's platform security documentation describes mandatory and discretionary controls, lineage-propagated restrictions, markings and audit logging. Shared data therefore means appropriately authorised shared data; it does not mean every employee receives every source. [Platform security](https://www.palantir.com/docs/gotham)

## Concrete capability map for DRISHTI

The following design is our engineering proposal informed by those sources, not a description of hidden Palantir internals.

| Capability | Analyst interaction | Backend contract and completion evidence |
|---|---|---|
| Case discovery | Search a document term, record identifier, organisation or incident within an authorized case; filter by type, domain, source and date | Search case-authorized indexed objects; return explicit match reasons, source records and stable IDs; evaluate retrieval against a fixed query set |
| Entity workspace | Open any result without losing the query; inspect overview, relationships, events, map and sources | One dossier contract across ontology types, with optional type-specific sections; no person-only or bank-only route assumption |
| Source-aware assertions | Inspect why a property or relationship exists | Preserve source ID, source record key, ingest time, event/validity time, collector/version and access marking; distinguish a source claim from a verified fact |
| Relationship investigation | Expand selected objects and compare paths | Traverse the authorised graph with edge types, statuses, dates and depth bounds; candidate identities and contextual associations remain distinguishable |
| Event reconstruction | Examine an incident's linked records chronologically | Common event model spanning communications, travel, registry changes, shipments, documents, transactions and case actions; unknown dates remain unknown |
| Spatial reconstruction | See event locations and precision; move between map and dossier | Latitude/longitude, source precision and time interval; links to evidence; no inferred precise position from a district centroid |
| Evidence-quality findings | Inspect duplicate records, contradictory dates, missing provenance and inconsistent source values | Versioned check, parameters, input IDs, observed measurements, limitations and reviewer disposition; reproducible from authorised case data |
| Inter-agency collaboration | Open shared case context and request additional access | Owner and contributing agencies, case purpose, classification, grants, expiry and audit events; permissions re-evaluated for each recipient |
| Evidence handling | Save selected records/findings into a case and export a review packet | Content hashes, source references, acquisition details, transformations and custody events; tamper checks and manifest validation |
| Operational health | Inspect data freshness and coverage | Connector status, ingest errors, stale sources, truncated searches, model versions and explicit unavailable sections |

An empty dossier section is a coverage gap, not an invitation to invent information. A source marked synthetic must remain visibly synthetic through search, graphs, findings and exported evidence.

## Data model: objects, assertions, observations and cases

Use stable object IDs independent of human names. Keep source records immutable where practical. A canonical object is an interpretation over records; it should not destroy contradictory values or the ability to undo a merge.

Recommended common primitives:

- **Object:** ID, ontology type, display title and lifecycle state. Person, organisation, vehicle, device, identifier, account, address, place, document and incident are peers.
- **Assertion:** subject, predicate, value or object, source record, valid interval, recorded time, source confidence/quality and policy marking. Conflicting assertions can coexist.
- **Observation/event:** time interval, location/precision, participants with explicit roles, source and event type. A person being mentioned is different from being an author, owner or participant.
- **Resolution decision:** constituent IDs, feature comparisons, model/version, reviewer, reason, timestamp and reversible status. Matching records does not establish wrongdoing.
- **Finding:** detector ID/version, input snapshot, eligible population, measurements, thresholds, evidence IDs and review state. Separate findings from case allegations and adjudicated outcomes.
- **Case/workspace:** scope, purpose, assigned users, contributing agencies, grants, saved graph/timeline selections, notes and evidence references.

Represent time as UTC internally with explicit display timezone and source timezone when known. Represent uncertain dates as intervals. Store ingestion time separately: a document loaded today can describe an event from years ago. Record schema version and source record revision so replay and migration are testable.

## Algorithms that produce inspectable results

### Search and retrieval

Begin with indexed lexical retrieval and identifier normalization. Exact identifiers should rank above a fuzzy name resemblance when the type matches. Preserve original script; maintain normalized searchable variants separately. Explain which field matched. Apply authorisation before ranking/windowing where possible; otherwise continue fetching until the authorised result window is complete or explicitly truncated. A fixed over-fetch multiplier does not guarantee recall when most top candidates are inaccessible.

Evaluate hybrid semantic retrieval only against a measured lexical baseline. A vector similarity score is retrieval relevance, not identity confidence. A document summarizer must cite permitted source passages and disclose unavailable evidence. An LLM must not silently create ontology facts or infer guilt from narrative style.

### Entity resolution

Fellegi–Sunter linkage compares feature agreement under match/non-match hypotheses; Splink documents the model and its likelihood-ratio interpretation. [Splink model explanation](https://moj-analytical-services.github.io/splink/topic_guides/theory/fellegi_sunter.html)

DRISHTI's existing `drishti/resolve/matcher.py` implements that model family with hand-set `M_U` values and per-feature explanations. Those values are assumptions until estimated and validated on representative labelled data. Synthetic calibration does not establish real-world probability calibration.

Proposed progression: type-specific candidate blocking; source-aware identifier normalization; feature comparisons; estimates fitted on training data; calibrated thresholds selected on validation data; a locked test set; reversible human review. Use separate schemas for organisations, vehicles and locations rather than treating them as person names. Missing values are not disagreements. A shared household phone, common address or reused device needs contextual handling. Record hard identifier contradictions for review instead of silently absorbing them into a score.

### Graph and relationship analysis

Use breadth-first search for shortest hop paths; use weighted shortest paths only when costs have a documented meaning. Standard graph libraries expose these algorithm families. [NetworkX shortest paths](https://networkx.org/documentation/stable/reference/algorithms/shortest_paths.html)

For a bounded case, graph tools should expose documented relationships between already admitted records, with the actual path and source edges. Degree or betweenness measures structural position within the selected graph, not criminality. Prevent unrestricted expansion beyond case scope, and make filtering visible. An absent path means no path in the authorised, bounded query result; it does not prove two entities are unrelated. Do not turn graph association into a population-wide suspect ranking.

### Time and geography

For review of place-based evidence already attached to a case, spatial tools should preserve measurement units and precision. PostGIS `ST_DWithin` supports distance predicates; geography distances are in metres and spatial indexes can assist filtering. [PostGIS distance predicate](https://postgis.net/docs/ST_DWithin.html)

The appropriate workflow here is reviewing supplied evidence timestamps and recorded locations, with uncertainty visible. Two records in the same district are not evidence of a meeting. Missing locations and gaps must remain missing; do not fabricate continuous personal tracks. The prototype should not claim that it can find everyone or that a person cannot avoid identification.

### Anomaly models and evaluation

Isolation Forest is a possible baseline for multivariate event anomalies; the documented method isolates observations by randomized tree partitions. [scikit-learn Isolation Forest](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.IsolationForest.html)

For this scope, compare such a baseline only on data-quality tasks, such as unusual ingest volumes or malformed source records. Train on temporally earlier data, report minimum sample sizes, and test drift. Save fitted artifacts, feature schema, training-data fingerprint, seed, dependency versions, evaluation report and intended-use limitations. Do not display an arbitrary weighted sum as a trained AI model or use personal behaviour anomalies as a guilt score. A model should abstain when source coverage or sample size is inadequate.

## Permissioned sharing across agencies

Different agencies should have configurable case templates over the same ontology. Example templates can emphasise admitted incident evidence, corporate records, document review, source reconciliation and evidence custody. These are proposed software workflows, not claims about actual agency access rights or mandates. A shared ontology is not authorization to pool unrestricted personal records across agencies.

Use the intersection of user attributes, case purpose/scope, source restrictions and explicit sharing grants. Evaluate object, property and relationship visibility before producing derived results. Re-run policy when a collaborator opens a saved board or export. Revoking a source grant must invalidate affected derived caches and future exports. Do not reveal hidden object names through counts, faceted search, path explanations, autocomplete, errors or downloadable metadata.

PostgreSQL row security is useful defence in depth, but owners and roles with bypass privileges require special attention. The application should run under a deliberately restricted role; database policies do not replace API- and field-level authorization. [PostgreSQL row security](https://www.postgresql.org/docs/current/ddl-rowsecurity.html)

## Repository baseline and unresolved infrastructure

Observed by reading the repository during this research; code under active development may subsequently change. These are not integration test results.

| Area | Observed baseline | Work needed before claiming completion |
|---|---|---|
| Database abstraction | `drishti/db.py` contains SQLite/PostgreSQL adapters | Route Store access through the adapter and cover both dialects |
| Active Store | `drishti/store.py` directly constructs a SQLite connection | Migrate schema, full-text search, transactions and query code; test old-data upgrade and rollback |
| Dependencies | `pyproject.toml` has no PostgreSQL/psycopg extra at inspection | Declare and pin tested dependency versions through the project dependency workflow |
| Deployment | Compose defines the app, OPA and optional Keycloak; `deploy/db/Dockerfile` exists separately | Add an actual database service/profile, health checks, persistent storage, migrations and connection configuration |
| Graph database | Current graph builder traverses Store; adapter can load AGE | Implement and verify graph projection/query contract, consistency, permission enforcement and extension-unavailable behaviour |
| OIDC | `drishti/guard/users.py` verifies bearer tokens; `tests/test_oidc.py` tests locally generated tokens | Exercise an actual Keycloak browser login, callback, refresh, logout, revoked access and JWKS rotation |
| Model quality | Matching code contains hand-set model parameters | Publish held-out calibration and error analysis; make training and benchmark status explicit |

**AGE version nuance:** the project's setup page still lists PostgreSQL 11–15, but the official release feed contains an AGE 1.8.0 release for PG18 with a `PG18/v1.8.0-rc0` tag. Resolve compatibility from the selected release artifact and run build/integration checks; neither the stale overview nor a Dockerfile comment proves the deployed combination works. Also avoid the older research pack's categorical claim that 1.8 supports PG18 only: the current release feed includes a PG15 release. [AGE setup](https://age.apache.org/age-manual/master/intro/setup.html), [AGE releases](https://github.com/apache/age/releases)

Keycloak completion requires issuer/audience/signature/expiry validation, expected role/agency claim mapping, restrictive redirect URIs, browser state handling and real login lifecycle coverage. Use Authorization Code with PKCE for a browser client; the official JavaScript adapter documents S256 support. Keep development identity selection visibly separate from authenticated operation. [Keycloak OIDC guidance](https://www.keycloak.org/securing-apps/oidc-layers), [JavaScript adapter](https://www.keycloak.org/securing-apps/javascript-adapter)

For PostgreSQL, validate extensions in the running database, schema migrations, query equivalence, source/edge deletion, concurrent writers, backup/restore and query timeouts. Expose database/graph backend status honestly. If graph support is optional, show which operations use the fallback and which are unavailable.

## Measurable validation plan

These gates are proposed acceptance criteria. No numbers in this section should be reported as achieved without a dated run artifact.

| Test area | Dataset / procedure | Metric or acceptance gate |
|---|---|---|
| Cross-domain discovery | Fixed queries covering every supported object type, aliases, multilingual names, exact IDs and document terms | Recall@20 and nDCG@10 by type; all deterministic exact-ID fixtures retrieved; no denied IDs or source fields returned |
| Dossier correctness | Fixtures containing people, companies, vehicles, devices, incidents and conflicting source values | Every displayed claim has source lineage or a clear derived label; counts and graph links agree with authorised inputs |
| Resolution | Entity-disjoint train/validation/test splits; shared households, common names, transliteration, stale IDs and collisions | Precision/recall by source and script; false-merge count; candidate blocking recall; Brier score/calibration plot; reviewer workload |
| Detector quality | Injected positives plus realistic benign counterexamples, independently generated held-out scenarios | Precision, recall and false alerts per 1,000 eligible events per detector; disclose denominator and uncertainty |
| Time/space correctness | Missing times, offset timestamps, interval boundaries, coarse locations and long gaps | Expected associations only; no precise coordinates invented; deterministic handling of interval boundaries |
| Access control | Cross product of users, agencies, cases, source markings and endpoints | Zero unauthorized object/property/edge/metadata disclosures in the fixture matrix; permission revocation invalidates cached views |
| Evidence | Modify bytes, reorder manifests, remove a source and replay custody events | Verification detects alteration; authorized exports are reproducible; missing source material is explicit |
| Database parity | Same fixtures on SQLite and actual PostgreSQL/AGE | Equivalent authorised results; migration preserves IDs and evidence hashes; backup restore verified |
| Authentication | Browser + live Keycloak test realm | Login/refresh/logout succeed; invalid issuer/audience/expired token rejected; production mode rejects development identity headers |
| Performance | Publish hardware, corpus sizes, concurrency and cold/warm conditions | Report p50/p95 search, dossier and graph latency plus failures; suggested initial interactive p95 budget under 2 seconds on the declared test workload |
| Usability | Search → dossier → linked company → timeline/map → save evidence; repeat as another permitted agency user | Task completion recorded, broken actions enumerated, keyboard access and visible focus checked |

Keep synthetic ground truth outside production feature extraction: `_truth_id`, scenario names and generator-only labels must not become ranking or detector features. Split connected entities and scenario templates to avoid train/test leakage. A detector that recognises generator fingerprints has not demonstrated investigative capability.

## Implementation order and reporting discipline

1. Establish universal object search and a common dossier, including source and coverage explanations.
2. Unify graph, timeline, map and case navigation around the same object IDs and authorized observations.
3. Add explainable cross-domain evidence-quality checks with benign counterexamples and reproducible benchmark reports.
4. Complete source-level sharing and derived-data policy propagation; test collaborators with distinct permissions.
5. Finish PostgreSQL/AGE and real Keycloak integration with reproducible deployment and restoration checks.
6. Evaluate optional learned retrieval, extraction and anomaly models against the transparent baseline; promote only measured improvements.

Each release report should name what works, what was exercised end to end, dataset size, benchmark seed, known coverage gaps and unverified infrastructure. The product can be ambitious while keeping those distinctions exact.

# 04 · Technology stack: versions, breaking changes and alternatives (Oct 2026)

Design doc Section 9 chose the stack. This file pins it to what exists in October 2026 and records the surprises.

## Version check

*Measured* from PyPI, npm and the OPA binary on 14 Oct 2026, unless a source is given.

| Component | Latest seen | Used in v0.1 | Notes |
|---|---|---|---|
| Python | — | 3.12 | |
| FastAPI | 0.143.1 | ✓ | |
| Splink | **5.0.0** | not used (optional extra) | Stable in late Sept 2026. Breaking changes: inputs registered via `db_api.register()` before `Linker`; match weights (`mw_`) replace Bayes factors (`bf_`); lighter install (DuckDB, PyArrow, SQLGlot only); `predict()` chunking for very large jobs ([release PR #3327](https://github.com/moj-analytical-services/splink/pull/3327), [releases](https://github.com/moj-analytical-services/splink/releases), [blog](https://moj-analytical-services.github.io/splink/blog/index.html)) |
| DuckDB | 1.5.6 | — | Splink 5 backend |
| Apache AGE | 1.7.0 (Jan 2026), 1.7.0.1 (EDB, Mar 2026), 1.8.0 (EDB, Aug 2026) | — | 1.7.x supports PG17/18; **1.8.0 supports PG18 only** ([AGE release notes](https://age.apache.org/release-notes), [EDB 1.8.0](https://www.enterprisedb.com/docs/pg_extensions/apache_age/rel_notes/apache_age_1.8.0_rel_notes/), [EDB 1.7.0.1](https://www.enterprisedb.com/docs/pg_extensions/apache_age/rel_notes/apache_age_1.7.0.1_rel_notes)). For a new deployment, use **PostgreSQL 18 + AGE 1.8 + PostGIS**, not the design doc's PG16 |
| Open Policy Agent | **1.21.2** | ✓ (Docker + parity test) | Rego v1 syntax. Gotcha: `not x` is false when `x` is JSON `null` (see 06) |
| Keycloak | 26.x | realm file only | 26 enforces the declarative user profile; custom attributes (clearance, districts) need `unmanagedAttributePolicy` |
| indic-transliteration | 2.3.82 | ✓ | Pure Python, MIT. Use `TAMIL_SUB`, not `TAMIL`, for Tamil source text (see 05) |
| ai4bharat-transliteration (IndicXlit) | 1.1.3 | not used | Neural; ~26M training pairs (Aksharantar); the next step for rare names, Dravidian scripts and Urdu |
| React / Vite / TypeScript | 19.3 / 8.3 / 6.0 (TS 7.0 is the Go-native compiler) | ✓ | Vite's template still pins TS 6 |
| MapLibre GL JS | **6.14.0** | ✓ | v6 is ESM-only with **no default export**, and resolves its worker relative to `import.meta.url`, which breaks in bundled builds. Fix: `setWorkerUrl(<asset url>)` and serve `.mjs` as JavaScript (see 06) |
| Cytoscape.js | 3.34.3 | ✓ | |
| Blueprint | 6.21.0 | ✓ | npm reports a React 19 peer override; works. Licence is Apache-2.0 plus the "not Palantir's" clause |
| OpenFreeMap | styles `dark`, `positron`, `liberty`, `bright`, `fiord` | ✓ | Free, keyless OSM vector tiles; demo only (map-boundary rule in 03) |

## Storage: why v0.1 uses SQLite, and the path to PostgreSQL + AGE

- **Why SQLite now:** one file, zero services, works fully offline. That is exactly the edge-kit requirement (M12). The schema is a plain property graph (`objects`, `links`, `provenance`, `identifiers`) plus FTS5 for search, append-only triggers for audit, and recursive traversal in Python.
- **Measured performance:** the full demo (11,779 objects; 8,190 hospitals with point-in-polygon district assignment; 1,660 person records plus rings) builds in about 30 s on a laptop, and entity resolution runs in under 2 s.
- **Path:** the same tables port to PostgreSQL 18. AGE then exposes them to openCypher for multi-hop queries, PostGIS replaces `geo.py`, and OpenSearch replaces FTS5 when search load needs it. The `Store` class is the only module that touches SQL.

## Indian open-weight language models (for the M11 assistant)

| Model | Licence | Size / hardware | Notes |
|---|---|---|---|
| Sarvam 30B / Sarvam 105B | **Apache-2.0** | 105B needs ~106 GB GPU memory even at FP8 (≥2×80 GB GPUs) | Released Feb/Mar 2026 (sources differ); 22 Indian languages; weights on Hugging Face and AIKosh ([lilting.ch](https://lilting.ch/en/articles/sarvam-105b-30b-open-source-llm), [BuildFastWithAI](https://www.buildfastwithai.com/blogs/sarvam-105b-india-s-open-source-llm-for-22-indian-languages-2026)) |
| BharatGen Param2 (17B MoE) | Conflicting reports (non-commercial vs open) | 17B MoE | Unveiled at the AI Impact Summit 2026; check the model card ([Free Press Journal](https://www.freepressjournal.in/tech/ai-summit-2026-meet-the-3-sovereign-ai-llm-models-that-were-unveiled-in-delhi-to-rival-global-tech-giants), [AITechConnect](https://aitechconnect.in/news/indiaai-mission-12-llm-partners-sarvam-bharatgen)) |
| Krutrim-2 | reported open | — | secondary report only |

*Recommendation (inference):* prototype the assistant with **Sarvam 30B** on a single on-premises GPU server. It must use ontology-grounded tool calls (design doc 12.3), never retrieval over raw records. The assistant runs inside the same Guard check as every other request.

## Comparable open platforms: what to borrow

| Platform | State in 2026 | Borrow |
|---|---|---|
| **OpenAleph** (DARC) | Soft fork of OCCRP Aleph. OCCRP ended open-source maintenance after Dec 2025 to focus on the commercial *Aleph Pro*. The fork stays FollowTheMoney-compatible; there was a public dispute over stewardship of the FtM library ([OpenAleph blog](https://openaleph.org/blog/2025/openaleph-commits-to-the-commons/), [about](https://openaleph.org/about/), [Aleph forum](https://aleph.discourse.group/t/aleph-pro-launches-monday/325)) | FtM entity schema for companies and payments; cross-referencing UX; ingest of document dumps |
| **OpenCTI** (Filigran) | Apache-2.0 community edition; STIX 2.1 knowledge graph; GraphQL API; connector and worker architecture ([Wiz overview](https://www.wiz.io/academy/opencti-overview)) | The connector → bundle → worker pattern for M1; STIX for CERT-In / NCIIPC instances |
| **Neo4j + GraphAware Hume** | Neo4j announced the acquisition on 3 June 2026 as an "open-standard alternative to Palantir Gotham"; it **closed 5 Aug 2026**; Hume runs as a standalone unit ([Neo4j press release](https://neo4j.com/press-releases/neo4j-acquires-graphaware/), [GraphAware blog](https://graphaware.com/blog/neo4j-acquires-graphaware-13-years-of-innovation/), [GovConWire](https://www.govconwire.com/articles/neo4j-graphaware-acquisition-ai-intel-analysis)) | Validation of the market; keep queries in openCypher so a Neo4j backend stays possible |

## Licence notes

- geoBoundaries ADM2 is **ODbL** per its API metadata; derived databases must be shared under ODbL with attribution (see NOTICE). The same applies to OSM extracts.
- Wikidata (the LGD codes) is CC0.
- SACHET declares the feed public domain.
- The design doc lists MinIO as AGPLv3. If a department's lawyers dislike AGPL, SeaweedFS (Apache-2.0) is the drop-in alternative the doc already names.

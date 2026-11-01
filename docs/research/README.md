# DRISHTI research pack (October 2026)

This pack extends the research in the [design document](00-design-document.md) with what we learned building the v0.1 prototype. It is meant for the DRISHTI team and for anyone reviewing the design.

Four kinds of evidence are used, and each claim says which it is:

- **Measured:** observed directly in this build on 14 Oct 2026 (live feeds, downloaded data, benchmark runs).
- **Primary:** official text, a project's own release notes or repository, or a court record.
- **Secondary:** news, law-firm notes, explainers. Treat these as leads to confirm before relying on them.
- **Inference:** our reasoning from the above, marked as such.

| File | What it covers |
|---|---|
| [01-data-sources.md](01-data-sources.md) | SACHET CAP feed internals, LGD codes and why there is no public village API, boundaries, OSM, CWC, what each is actually like to ingest |
| [02-indian-systems-2026.md](02-indian-systems-2026.md) | NATGRID (incl. the October 2026 GST-data proposal), ICJS 2.0, CCTNS 2.0, the I4C Suspect Registry and Samanvaya, and where DRISHTI fits |
| [03-legal-2026.md](03-legal-2026.md) | DPDP Rules timeline and state-processing standards, the Data Protection Board, telecom interception rules, BSA s.63 certificates, BNSS s.94, CERT-In logging, map-boundary rules, the 2026 Supreme Court facial-recognition petition, Germany in 2026 |
| [04-technology-stack.md](04-technology-stack.md) | Version check of every component as of Oct 2026, breaking changes found, Indian open-weight LLMs, comparable open platforms |
| [05-entity-resolution.md](05-entity-resolution.md) | Indian-name matching: literature, the pipeline as built, benchmark iterations, error analysis, next steps |
| [06-lessons-from-the-build.md](06-lessons-from-the-build.md) | Defects that only appeared when the system was run end to end, and the rule each one teaches |
| [07-gotham-investigation-architecture.md](07-gotham-investigation-architecture.md) | What public Gotham material establishes, and the cross-domain investigation design that follows |
| [08-mission-tracks-pattern-engine.md](08-mission-tracks-pattern-engine.md) | Mission tracks for every agency, the 19-detector pattern engine, its threat model, evaluation on four worlds and adversary simulation |
| [09-data-studio.md](09-data-studio.md) | Governed intake: type detection, cleaning recipes, ontology mapping, identifier matching, interpretation lenses, revision cards, two-person publish and revert |
| [10-external-benchmarks.md](10-external-benchmarks.md) | Tests on public data DRISHTI did not generate: real Mafia and trafficking networks, Indian-script names (Aksharantar), FEBRL record linkage; IBM AML pending |

## The ten findings that matter most

1. **SACHET has no inline geometry.** Alert polygons sit behind a second URL that returned HTTP 403 to non-browser clients. Usable location comes from `<geocode>` "LGD District Code" values (IMD and some state disaster authorities) or from free-text area names. Our gazetteer placed 20 of 25 sampled alerts on districts (80%). *Measured.*
2. **LGD codes are the national join key, but there is no public API for villages.** data.gov.in lists the LGD village dataset without an API. Wikidata now carries official LGD codes (P12746/P12747/P12748), which gave us 36 states, 788 districts and 7,221 sub-districts under a CC0 licence. *Measured + secondary.*
3. **District names are not unique and keep changing.** Aurangabad, Bilaspur, Hamirpur and Pratapgarh each name districts in two states. Ahmednagar→Ahilyanagar, Aurangabad (MH)→Chhatrapati Sambhajinagar and Osmanabad→Dharashiv were renamed in 2023–24, and the open boundary file still uses the old names. Entity resolution applies to places, not just people. *Measured.*
4. **OSM cannot supply hospital capacity.** Only 2 of 8,190 Maharashtra hospitals in OSM have a bed count, and only 23 are tagged government-run. A disaster COP needs departmental data (NHM/HMIS or the ABDM Health Facility Registry). *Measured; HFR as a source is an inference to verify.*
5. **The DPDP state-processing rules bite on 13 May 2027.** Rules were notified on 13 Nov 2025 with an 18-month phase-in, and the Seventh Schedule (Rule 23) names who may call for information. The Data Protection Board was constituted in 2026 but, as of August, had no members appointed. Build to the full standard now. *Secondary, pending Gazette check.*
6. **NATGRID is widening fast.** SP-rank state officers have access, there are about 45,000 requests a month, and the GST Council considered API access to five categories of GST data on 8 Oct 2026; we found no record of the outcome. DRISHTI should treat NATGRID as a per-case response source, never a bulk feed. *Secondary.*
7. **Courts are actively testing police surveillance tech in 2026.** A July 2026 PIL challenging facial recognition at Jantar Mantar protests is before the Supreme Court, which agreed to hear it. Germany's Baden-Württemberg adopted Palantir from Q2 2026 while Lower Saxony refused. Purpose binding and no-protest-surveillance red lines are now active legal questions, not hypotheticals. *Secondary.*
8. **Splink 5.0.0 (Sept 2026) changed its API**, and Apache AGE 1.8 supports PostgreSQL 18 only. The design doc's stack needs version pins; see the table in 04. *Primary/secondary.*
9. **Indian open-weight LLMs now exist under Apache-2.0** (Sarvam 30B and 105B, 2026). The 105B needs about 106 GB of GPU memory even at FP8, so the 30B is the realistic on-premises assistant. *Secondary.*
10. **Running the system found defects that unit tests did not.** Examples: a Rego `null` semantics bug that would have hidden every bank account under OPA, MapLibre v6's worker path breaking in bundled builds, and schwa deletion turning "Sangita" into "Sangit". See 06. *Measured.*

## Corrections to the design document

| Design doc says | Research found | Done in v0.1 |
|---|---|---|
| Vehicle regex `^[A-Z]{2}[0-9]{1,2}[A-Z]{0,3}[0-9]{4}$` (7.5) | Rejects Bharat-series plates (`22BH1234AA`, since 2021) | Ontology accepts both; BH letters exclude I and O |
| SACHET gives "a `Hazard` object with a polygon" (4.4A) | No inline polygon; the polygon URL is blocked to scripts; LGD geocodes or text only | Four-step geocoder; unresolved alerts flagged as data-quality issues |
| "Mohd." listed as an honorific to strip (12.2) | It is an abbreviation of a real given name; stripping it loses a token | Canonicalised to `muhammad` with other variants |
| Matching thresholds >0.95 / 0.7–0.95 / <0.7 (12.2) | They work only with a data-estimated prior (Splink's method); a hand-set prior cut recall to 51% | Prior estimated per run; thresholds kept |
| Splink as the resolver (9.1) | Splink 5.0.0 changed the Linker API; also needs labelled Indian data to tune | Built-in Fellegi–Sunter with the same model; Splink 5 remains the scale path |
| Apache AGE + PostgreSQL 16 (9.1) | AGE 1.7.x supports PG17/18; 1.8 supports PG18 only | v0.1 uses SQLite (offline-capable); target PG18 + AGE 1.8 |
| Neo4j–GraphAware deal "June 2026" (9.1 note) | Announced 3 June 2026, closed 5 Aug 2026 | Noted |
| Maps: "MapLibre + OSM tiles" (9.1) | Political maps of India must use Survey of India boundaries (2021 guidelines) | OpenFreeMap for the demo only; README flags SoI/Bhuvan for deployments |
| Aleph as "OCCRP Aleph source code (worth studying)" (17) | OCCRP ended open-source Aleph maintenance after Dec 2025; the maintained fork is OpenAleph (DARC) | Study OpenAleph and FollowTheMoney |
| Audit: "append-only" (11.2) | Needs both DB-level refusal and a chain, plus external root publication; CERT-In wants 180-day log retention | Triggers + SHA-256 chain + daily seal; retention policy still to set |

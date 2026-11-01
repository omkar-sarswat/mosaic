# Project DRISHTI — Open-Source Gotham-Class Data Fusion Platform for India

Oct 14, 2026 · @omkar

## 1. Executive summary

DRISHTI is a proposed open-source, ontology-based data fusion and decision platform for Indian government departments, built entirely on free software and free infrastructure, and designed to be legally deployable under India's Digital Personal Data Protection Act, 2023.

**The one-line pitch:** India already has the data pipes (NATGRID, CCTNS, ICJS, e-Courts, Aadhaar-linked schemes, open data portals). What it lacks is a common *model of the world* on top of those pipes, one that lets an officer see people, places, events, vehicles, money and documents as connected objects, act on them, and leave an auditable trail. That model is what made Palantir Gotham valuable. DRISHTI rebuilds that idea for Indian data sources and Indian law, at zero licence cost.

**What we are solving**

- **Fragmentation:** each department keeps its own database, IDs and formats, so the same person appears as five unconnected records.
- **Search, not understanding:** existing grids answer "give me the record for X"; they rarely answer "how is X connected to Y, and what changed this week?"
- **Language:** source records arrive in many regional languages with inconsistent spellings; DRISHTI converts them to English so every officer works in one language.
- **Accountability:** powerful data access without purpose-binding and audit invites misuse and fails the Supreme Court's proportionality test.
- **Cost and lock-in:** proprietary platforms cost crores per year and keep the national data model in a vendor's format.

**What DRISHTI is not.** It is not a mass-surveillance or data-collection tool. It never gathers new personal data by itself; it connects data that a department already lawfully holds, for a recorded purpose, with every query logged. Section 5 makes this a hard design constraint, not a promise.

**Zero-cost approach.** Every component in Section 9 is free and open source (Apache 2.0, MIT, BSD, GPL or AGPL). Development runs on a student laptop plus free cloud tiers. The first real deployment uses only open government data (data.gov.in, NCRB tables, disaster feeds), so no legal permission is needed to build a working prototype.

**How to read this document.** Sections 2 to 5 are the research (what Gotham is, what India already has, the gaps, the law). Sections 6 to 12 are the design. Sections 13 and 14 are the plan to build it as a student team and take it to government. Section 15 is a 1,000-hour learning path, Section 16 is UI research on Gotham and similar products, and Section 17 lists sources.

## 2. What Palantir Gotham actually is

Gotham is not an AI model or a database; it is an **ontology** (a typed model of people, places, things, events and their links) with integration pipelines underneath, analyst tools on top, and fine-grained security wrapped around everything. Copy that architecture and you copy most of the value.

### 2.1 History and product family

- Founded in 2003 by Peter Thiel, Alex Karp and others after 9/11; its early customers were US intelligence agencies, introduced via the CIA's venture arm In-Q-Tel ([Investor's Podcast](https://intrinsicvalue.beehiiv.com/p/pltr)).
- **Gotham** (first product, \~2008): defence, intelligence and police investigations.
- **Foundry**: the same core for companies and civil government.
- **Apollo**: continuous-delivery system that pushes updates into customer environments, including air-gapped ones.
- **AIP**: the LLM layer that lets AI models reason and act over ontology objects ([Towards AI teardown](https://pub.towardsai.net/inside-palantir-aip-how-the-worlds-most-controversial-ai-platform-actually-works-9ec5b7a6c05a)).

### 2.2 The ontology: the real product

Palantir defines its ontology as an operational layer with **semantic** elements (object types, properties, links) and **kinetic** elements (actions, functions, dynamic security) ([Vocal summary of ex-Palantir engineer](https://vocal.media/01/why-a-2000yearold-philosophy-became-every-ctos-emergency-meeting)). In practice:

| Ontology element | Meaning | Indian police example |
| --- | --- | --- |
| Object type | A kind of real-world thing | Person, Vehicle, FIR, Phone number, Bank account, Location |
| Property | An attribute of an object | Person.name (in Devanagari and Latin), Vehicle.registration |
| Link type | A typed relationship | Person *accused\_in* FIR; Phone *registered\_to* Person |
| Action | A permitted change, with validation | "Mark suspect as cleared", "Request CDR under warrant" |
| Function | Computed logic | Risk of re-offence flag, duplicate-person score |
| Security | Who can see which object, property or link | Constable sees FIR summary; IO sees full case diary |

The ontology turns data into a *digital twin* of the organisation that both humans and AI can navigate, and every edit made through an action flows back as a recorded decision ([heise](https://www.heise.de/en/background/Missing-link-Power-center-Palantir-a-software-controls-organizations-10463503.html?view=print)).

### 2.3 What an analyst actually does in Gotham

1. **Search** across all integrated sources from one box.
2. **Graph / link analysis**: expand a person to their phones, vehicles, co-accused, addresses, and see hidden connections.
3. **Map (geospatial)**: plot events, movements and heatmaps.
4. **Timeline**: see everything about an entity in order.
5. **Dossier / case**: collect findings, annotate, share with a team.
6. **Alerts**: get notified when a watched object changes.
7. **Security and audit**: access controls at row, column and object level; every query logged. Gotham supports mandatory, discretionary and attribute-based access control.

### 2.3a Gotham's applications in detail, and what DRISHTI borrows

| Gotham app | What it does | DRISHTI design idea |
| --- | --- | --- |
| Graph | Shared link-analysis canvas: expand, filter, find paths, histograms of object types, presentation layout | Expansions capped by depth and row limits; **edges colour-coded by evidence strength** (green = two independent sources, amber = one source, red = AI-suggested) so courts and supervisors see how solid each link is |
| Gaia (map) | Radius, route, polygon and time-window geo-search; heatmaps; custom tile layers; live feeds | Time-slider playback; geofence alerts ("notify if a case vehicle appears in another district"); offline map packages (MBTiles) for field units |
| Object Explorer | Filter millions of records by any property, chart distributions, drill into outliers, send the set to Graph or Map | OpenSearch facets + embedded Superset charts; every object with a date gets a timeline strip |
| Browser (object view) | One object, every property, with the source of each attribute; **tagging** text in documents to create properties and links | Per-attribute provenance chips; a text-annotation tool where an analyst highlights words in an FIR narrative and proposes a link, which goes to a review queue before entering the graph |
| Dossier | Collaborative intelligence reports with live embedded graphs and maps; export with markings | Reports stored as structured blocks (so embedded views stay live); PDF export with a mandatory "sources and confidence" annexe |
| CDR analysis | Fuse call records, map towers, co-location, pattern of life | Only for records obtained under a lawful order and attached to a case; heavy rows live in Parquet/DuckDB, only derived links ("phone seen at tower at time") enter the graph; co-travel scored by overlap of tower-hour sets |
| Video | AI detections and heatmaps on video streams | **Out of scope** (see red lines in Section 5.3) |

### 2.4 Where it is used

| Customer | Use | Status / notes |
| --- | --- | --- |
| US DoD, intelligence community | Defence intelligence, targeting | Core market |
| US ICE | Investigative Case Management since \~2013; ImmigrationOS contract of $30M (2025–2027) ([American Immigration Council](https://www.americanimmigrationcouncil.org/blog/ice-immigrationos-palantir-ai-track-immigrants/)) | Highly controversial |
| Hesse police, Germany | "HessenDATA" since 2017 | Law struck down by Constitutional Court, Feb 2023 |
| Bavaria, NRW (Germany) | Framework deals of €25M and €20M+ ([Benzinga via Yahoo](https://hk.finance.yahoo.com/news/palantir-hits-roadblock-germany-february-134146186.html)) | Under constitutional challenge |
| LAPD | Operation LASER, 2011–2019 | Ended after bias criticism |
| Ontario Provincial Police, Calgary Police | Crime analysis ([The Logic](https://thelogic.co/news/exclusive/ontario-provincial-police-use-controversial-data-mining-platform-palantir-for-crime-analysis/)) | Ongoing |

### 2.5 The lessons from its controversies (these shape DRISHTI)

- **Germany, Feb 2023:** the Federal Constitutional Court ruled automated data analysis in Hesse and Hamburg unconstitutional because it violated informational self-determination; such tools are only permissible to protect very weighty interests like life, limb and liberty ([IndiaAI](https://indiaai.gov.in/news/the-german-federal-constitutional-court-nullify-palantir-s-ai-algorithm-for-policing)). The court specifically worried that innocent people linked to suspects could be pulled into investigations.
- **LAPD:** a points-based "LASER score" was ended in 2019 after documents showed over-policing of non-white communities ([Urban Legend News](https://www.urbanlegendnews.org/news/2026/03/13/palantir-secures-billions-in-government-contracts/)).
- **Sovereignty:** a 2026 analysis notes Germany's domestic intelligence agency picked a European alternative in May 2026, partly over US jurisdiction concerns ([European Cloud](https://european.cloud/2026/08/baden-wurttemberg-palantir/)).
- **Lock-in:** the ontology is proprietary, so migrating off it is very costly.

**Takeaway for India:** build the capability (integration, ontology, graph, map, audit), but avoid four mistakes: no person-level "risk scores", no vague legal basis, no foreign-controlled stack, and no closed data model.

## 3. The problem in India: many pipes, no common model

India has built strong *search-and-share* infrastructure since 26/11, but each system is a silo with its own IDs, schema and access rules, and none provides a shared ontology, link analysis across domains, entity resolution across inconsistent name spellings, or open, auditable architecture.

### 3.1 What already exists

| System | Owner | What it does | Scale / status |
| --- | --- | --- | --- |
| [NATGRID](https://bharatnotes.com/resources/key-terms/natgrid-national-intelligence-grid--21-intelligence-agencies-nia-natgrid/) | MHA | Middleware letting 11 central agencies (IB, R&AW, NIA, CBI, ED, NCB, FIU, DRI, CBDT, CBIC, DGGI) query 20+ data categories; a "master index", not a collector | Live since end-2020; \~45,000 requests/month by Dec 2025; access widened to SP rank in states |
| NATGRID–NPR link | MHA | NATGRID linked to National Population Register | Covers \~119 crore residents ([Padhai](https://padhai.ai/current-affairs/national-intelligence-grid-natgrid-npr-integration)) |
| [CCTNS](https://www.mha.gov.in/en/divisionofmha/women-safety-division/cctns) | MHA / NCRB | Common software linking police stations: FIRs, case diaries, citizen services | Started 2009; 16,390 police stations connected (per Amit Shah) |
| ICJS / ICJS 2.0 | NCRB, NIC, SC e-Committee | Integrates police (CCTNS), courts (e-Courts), prisons (e-Prisons), forensics, prosecution | Phase 2 targeted for 2026 at \~₹3,500 crore ([Madhyamam](https://english.madhyamam.com/india/integration-of-cbi-nia-ncb-data-with-cctns-a-must-shah-954571)) |
| Cri-MAC | NCRB | Shares information on heinous and inter-state crimes | All states/UTs |
| ICJS link-analysis module | NCRB | Criminal network link analysis | Exists, but scope limited to criminal-justice data |
| NAFIS | NCRB | National fingerprint database, linked with CCTNS backend | \~1 crore fingerprints registered |
| CMS, NETRA | Govt | Telecom / internet interception | Criticised as mass surveillance ([IAPP](https://iapp.org/news/a/india-s-surveillance-landscape-after-the-dpdpa)) |

Other national systems a DRISHTI deployment may need to read from, or must at least understand:

| System | Owner | What it holds | How DRISHTI relates |
| --- | --- | --- | --- |
| AFRS (Automated Facial Recognition System) | NCRB | Face matching against police photo records | DRISHTI does **not** build live facial recognition; it may store a match result an officer attaches to a case |
| NDSO | NCRB / MHA | National Database of Sexual Offenders | Read-only lookup inside authorised cases |
| I4C, cybercrime.gov.in, 1930 helpline | MHA | Cyber-fraud complaints, mule accounts, freeze requests | Main source for the cyber-fraud app (Section 4.3) |
| TrackChild / Khoya-Paya | Ministry of Women and Child Development | Missing and found children | Missing-persons matching workflow |
| VAHAN / SARATHI | MoRTH | Vehicle registrations, driving licences | Lookup under existing police access |
| MCA21 | Ministry of Corporate Affairs | Companies, directors, filings | Shell-company and procurement-fraud networks |
| DigiLocker | MeitY | Verifiable documents (licences, RCs, certificates) | Document verification by reference, never bulk copy |
| Account Aggregator / DEPA | RBI, NITI Aayog framework | Consent-based financial data sharing | Model for consent artefacts in welfare and finance apps |

### 3.2 The gaps DRISHTI fills

1. **No shared ontology.** NATGRID returns records; CCTNS stores FIRs; e-Courts stores cases. A "Person" in one is not the same object in another. Officers mentally stitch them together.
2. **Entity resolution is weak for Indian names.** "Mohd. Irfan Shaikh", "Mohammed Irfan S." and "मोहम्मद इरफान शेख" are one person; most systems treat them as three. Indian data also lacks consistent birth dates and addresses.
3. **Cross-domain link analysis is missing.** ICJS link analysis is confined to criminal-justice records; it does not connect, for example, disaster relief claims, GST invoices and land records for fraud detection.
4. **State-level integration is slow.** Central agencies are integrated, but bringing state police forces into NATGRID is slower and harder, and data quality varies across ministries ([IASGyan](https://www.iasgyan.in/daily-current-affairs/national-intelligence-grid-natgrid-explained)). Even CCTNS had issues: in Maharashtra, stations could not view pending cases of other stations due to technical problems (Indian Express, 2020, via [ecoi.net](https://www.ecoi.net/en/document/2054443.html)).
5. **Accountability is thin.** Critics note agencies can access vast data without an FIR, and intelligence failures often come from institutions, not missing data ([Shankar IAS](https://www.shankariasparliament.com/current-affairs/natgrid)).
6. **Closed, expensive, vendor-built.** Government systems are built by large integrators; states cannot easily reuse, audit, or extend them.
7. **Non-police departments are ignored.** District collectors, disaster authorities, health and welfare departments face the same silo problem but have no Gotham-like tool at all.

### 3.3 Where DRISHTI fits

DRISHTI is **not a replacement** for NATGRID or CCTNS. It is the *analysis and ontology layer* that a state, district or department runs on top of data it already lawfully holds, and it can consume NATGRID/ICJS responses as one more source when an authorised user requests them. Its fastest path to adoption is actually **civil governance** (disaster response, welfare leakage, district administration), where privacy risk is lower and the benefit is visible.

## 4. Use cases and personas

DRISHTI is one platform with many "apps"; each app is a set of object types, dashboards and actions for one department. Start with the low-risk civil use cases, then move to policing.

### 4.1 Priority use cases

| # | Use case | Department | Data needed | Risk level | Why it is a good start |
| --- | --- | --- | --- | --- | --- |
| 1 | Disaster common operating picture | SDMA / district collector | IMD warnings, rainfall, river gauges, shelters, roads, hospitals, relief stock | Low (mostly non-personal) | Life-saving, fully open data, impressive demo |
| 2 | District governance dashboard | Collectorate | Scheme progress, grievances (CPGRAMS), infrastructure projects | Low | Collectors are early adopters |
| 3 | Welfare leakage and duplicate beneficiary detection | Social welfare, food & civil supplies | Beneficiary lists, ration cards, bank seeding | Medium | Clear rupee savings |
| 4 | Crime analytics (aggregate) | State police, SCRB | NCRB/SCRB tables, FIR metadata | Low–medium | Hotspot and trend analysis without personal profiling |
| 5 | Case investigation workspace | Police investigating officer | FIRs, case diary, seized phones/CDRs obtained by warrant | High | The "true Gotham" use case; needs legal basis |
| 6 | Missing persons and unidentified bodies matching | Police, hospitals | Missing reports, UIDB records, photos | Medium | High public benefit |
| 7 | Financial fraud / cyber-fraud rings | Cyber cell, EOW | Complaints from cybercrime.gov.in, mule accounts, phone numbers | High | Massive volume of UPI fraud |
| 8 | GST / procurement fraud networks | Commercial tax, vigilance | Invoices, GSTINs, tender data | Medium | Link analysis catches shell firms |
| 9 | Public health surveillance | Health dept | IDSP outbreak data, hospital beds, lab results (aggregated) | Medium | Outbreak response |
| 10 | Border, coastal and critical infra monitoring | Defence, coast guard | AIS ship tracks, ADS-B flights, satellite imagery | Medium | Mostly open signals |

### 4.2 Personas

| Persona | Goal | What they see in DRISHTI |
| --- | --- | --- |
| District Collector | Know what is happening in the district today | Map dashboard, alerts, scheme KPIs |
| SDMA control-room operator | Coordinate relief during a flood | Live map of rainfall, shelters, rescue teams, road closures |
| Investigating Officer (IO) | Solve a case quickly and legally | Case workspace, link graph, timeline, evidence locker |
| SP / DCP | Allocate force, review cases | Crime heatmaps, case pendency, alerts on inter-district links |
| Analyst (SCRB / cyber cell) | Find patterns across cases | Graph exploration, pattern queries, reports |
| Data steward | Keep sources clean and lawful | Pipeline health, data quality, retention timers |
| Oversight officer / auditor | Check misuse | Full audit log, purpose records, anomaly reports on user behaviour |
| Citizen (indirect) | Know their rights | Public transparency report, grievance channel |

### 4.3 Walkthrough: a cyber-fraud investigation

1. A victim files a complaint on the cybercrime portal; it becomes a `Complaint` object linked to `Phone`, `BankAccount` and `UPI_ID` objects.
2. Entity resolution notices the same mule account appears in 37 other complaints across 4 districts.
3. The graph view shows a cluster: 12 mule accounts, 5 SIM numbers, 2 device IDs.
4. The IO opens a case, records the legal purpose ("Investigation of FIR 123/2026 u/s 318 BNS") and requests KYC details from banks through the existing legal channel; the response is attached as a new source.
5. Every view and query is logged against that purpose; the case closes and the derived data enters a retention timer.

### 4.4 More end-to-end workflows

**A. Flood response (Disaster COP)**

1. A SACHET CAP alert arrives for heavy rain in Nanded; it becomes a `Hazard` object with a polygon.
2. DRISHTI finds every `Asset` (hospitals, schools used as shelters) and `AdminUnit` (villages) inside the polygon.
3. The map shows shelter capacity, road closures and relief stock; the operator uses the `dispatch_resource` action.
4. Every dispatch is logged; after the event, a dossier summarises response times for the post-disaster review.

**B. Inter-state gang (organised crime)**

1. A Cri-MAC alert about a dacoity in another state is ingested as an `Incident`.
2. Entity resolution links accused names and shared phone numbers with three local FIRs.
3. The graph's centrality score highlights the person connecting the two groups (the broker); this is a lead for the IO, not a verdict.
4. An alert is set on the group's vehicles; ICJS status (bail, next hearing) is pulled per accused when the IO requests it.

**C. Shell-company / procurement fraud**

1. A vigilance complaint names a contractor.
2. MCA director data and public tender awards build an `Organisation` graph: shared directors, shared addresses, firms bidding against each other.
3. The Explorer timeline shows company incorporations clustered just before tender dates.
4. Findings are exported as a dossier with a sources annexe for the vigilance officer.

**D. Missing child**

1. A missing-child report is filed and linked to TrackChild.
2. DRISHTI matches attributes (age, place, date, clothing, photo reference) against found-children and unidentified-person records in other districts.
3. Candidate matches go to a human reviewer; confirmed matches alert both police stations.

In every workflow the same rules apply: a case or purpose is opened first, results are leads not conclusions, and every step lands in the audit log.

## 5. Legal, constitutional and ethical framework

DRISHTI must pass the Supreme Court's Puttaswamy proportionality test by design, because the German court struck down HessenDATA for exactly the gaps a careless Indian build would have. The rule is: **the software enforces the law, the law is not left to the user's discretion.**

### 5.1 The legal landscape (as of Oct 2026)

| Law / judgment | What it says | Design consequence |
| --- | --- | --- |
| K.S. Puttaswamy v. Union of India (2017) | Privacy is a fundamental right under Arts. 14, 19, 21; any infringement needs legality, legitimate aim, necessity / least-intrusive means, and procedural safeguards ([Lawful Legal](https://lawfullegal.in/the-right-to-privacy-in-the-age-of-surveillance/)) | Every query tied to a lawful purpose; minimise data; independent audit |
| Puttaswamy (Aadhaar, 2018) | Applied proportionality to Aadhaar; limits on profiling and retention | No central profile store; retention timers |
| Anuradha Bhasin (2020) | Proportionality applies to digital state action | Same test applies to DRISHTI's features |
| DPDP Act, 2023 | Section 7 allows state processing for offences, security, public order; Section 17 lets notified bodies skip many obligations ([MediaNama](https://www.medianama.com/2025/11/223-dpdp-framework-personal-data-companies-door-open-for-state/)) | Exemption ≠ licence: build to the full standard anyway, so a court challenge fails |
| DPDP Rules, 2025 | Notified 13 Nov 2025; Board rules live immediately; consent managers from 13 Nov 2026; most substantive rules (incl. state processing, security safeguards, breach intimation) from 13 May 2027 ([Storyboard18](https://www.storyboard18.com/digital/breaking-govt-notifies-final-dpdp-rules-sets-staggered-rollout-with-key-obligations-for-data-fiduciaries-84201.htm)) | Target May 2027 compliance from day one |
| IT Act 2000, s.69/69A/69B | Interception and monitoring only with written orders and review committees | DRISHTI never intercepts; it only ingests outputs of lawful orders, with the order ID attached |
| BNSS 2023 / BSA 2023 | New criminal procedure and evidence law | Evidence exports with hash and chain-of-custody so they are admissible |
| Germany BVerfG, 16 Feb 2023 | Automated analysis allowed only for very weighty interests, with clear limits on data sources and methods | Case-scoped analysis by default; no bulk "dragnet" mode |

### 5.2 Ten non-negotiable safeguards built into the code

1. **Purpose binding:** a user cannot run a query on personal data without selecting an open case or approved purpose; the purpose is stamped on every log line.
2. **Case scoping:** the graph expands only from case-linked entities; expanding to second- and third-degree links needs supervisor approval (this addresses the German court's "innocent contacts" concern).
3. **No person-level risk scores.** DRISHTI ranks *places and patterns*, never "likelihood a person will commit crime" (the LAPD LASER lesson).
4. **Data minimisation:** columns not needed for a purpose are masked (e.g., Aadhaar shown as XXXX-XXXX-1234).
5. **Retention timers:** derived data auto-expires when a case closes plus the statutory period.
6. **Immutable audit:** append-only, hash-chained logs readable by an independent oversight officer, not deletable by admins.
7. **Two-person rule** for sensitive actions (bulk export, adding a new personal-data source).
8. **Explainability:** every alert or match shows *why* (which records, which rule, what confidence).
9. **Bias testing:** quarterly report of alert rates by district and community proxies; human review of every automated flag.
10. **Transparency report:** aggregate statistics (number of queries, purposes, sources) published annually, as German and UK oversight bodies recommend.

### 5.3 Ethical red lines (the project will refuse to build these)

- Monitoring of journalists, activists, political opponents or religious groups as groups.
- Facial recognition on live public CCTV without a specific law.
- Social-media scraping of citizens' private accounts.
- Any selling or sharing of data with private parties.

> These red lines are also your strongest *sales* argument: an auditable, rights-respecting system is the one a court, a CAG audit and the Data Protection Board will not shut down.

## 6. System architecture

DRISHTI is a seven-layer stack: data flows up from sources, through ingestion and entity resolution, into storage and the ontology, and reaches users only after the Guard layer checks role, case and purpose.

&#91;embedded content: DRISHTI architecture · 7 layers, data flows upward\]

Read it bottom-up: Connect pulls data, Resolve merges duplicate records into single objects, storage holds records, graph, maps, text and files, and the ontology service exposes one typed API that every app uses. No app talks to a database directly.

### 6.1 How a single query flows

1. An IO searches "Ramesh Patil, Nanded" in the Explore app.
2. The request carries the IO's token (Keycloak) and the active case ID.
3. Guard asks OPA: does this user, for this case and purpose, have the right to see Person objects in Nanded with sensitivity RESTRICTED?
4. The ontology service queries OpenSearch for candidates, then Apache AGE for linked objects, applying row-level security.
5. Masked results return; the audit log records user, case, query and returned object IDs in a hash-chained row.

### 6.2 Deployment shapes

| Shape | Where | Hardware | Use |
| --- | --- | --- | --- |
| Dev | Student laptop | 16 GB RAM, Docker Compose | Building and testing |
| Demo | Free cloud VM | Arm VM, open + synthetic data only | Hackathons, public demo |
| District pilot | District NIC server / SDC VM | 8 vCPU, 32 GB RAM, 1 TB | One collectorate or SDMA |
| State | State Data Centre, Kubernetes | 3–10 nodes, HA Postgres | Statewide police or department use |
| Edge kit | Laptop in police station or flood zone | Single machine, offline sync | Low-connectivity operations |

## 7. Ontology design for Indian entities

The ontology is DRISHTI's core asset: a versioned, open YAML/JSON-Schema definition of about 25 object types and 40 link types that every department reuses, published openly so other states can adopt it. Start with a small core and let each app extend it.

### 7.1 Design principles

- **Reuse open standards** instead of inventing: [FollowTheMoney](https://followthemoney.tech/) (OCCRP's schema for people, companies, payments), NIEM (US justice data model) concepts, STIX 2.1 for cyber, GeoJSON for geography, LGD (Local Government Directory) codes for Indian administrative units.
- **Multi-script names:** every name property stores original script, ISO-15919 transliteration and a phonetic key.
- **Provenance on every property:** each value records source system, source record ID, ingestion time and confidence.
- **Time-aware:** properties and links carry `valid_from` / `valid_to` (a person's address changes).
- **Sensitivity labels** on types and properties drive access control (Section 11).

### 7.2 Core object types

| Object type | Key properties | Sensitivity | Example sources |
| --- | --- | --- | --- |
| Person | names\[\], dob/age range, gender, father/spouse name, identifiers (masked) | Personal | FIR, beneficiary list, voter roll (aggregate) |
| Organisation | name, type, CIN/GSTIN/registration, address | Public / business | MCA, GST portal, tenders |
| Location | lat/long, address, LGD village/ward code, PIN | Public | LGD, OSM, Bhuvan |
| AdminUnit | state, district, sub-district, village (LGD code), boundary | Public | LGD, Survey of India |
| Vehicle | registration no., make, model, colour, owner link | Personal | VAHAN (via legal request), FIR |
| Phone | number (hashed for display), operator, circle | Personal | Complaint, CDR (warrant) |
| BankAccount / UPI\_ID | IFSC, masked account no., VPA | Personal, financial | Cybercrime complaint, bank reply |
| Document | type, number, issuer, file hash | Varies | Uploaded evidence |
| Event | type, time, place, description | Varies | Disaster report, incident, protest permission |
| Incident (FIR / Complaint) | FIR no., police station, sections (BNS), status | Restricted | CCTNS export |
| Case | case ID, purpose, IO, legal basis, open/close dates | Restricted | Created in DRISHTI |
| CourtCase | CNR no., court, stage, next hearing | Public / restricted | e-Courts |
| Asset (infra) | type (hospital, shelter, bridge), capacity, status | Public | data.gov.in, PMGSY, NHM |
| Scheme / Beneficiary | scheme, beneficiary ID (masked), benefit amount | Personal | Department MIS |
| Transaction | amount, time, from/to accounts, channel | Financial | Bank statements (legal), GST invoices |
| Hazard / Alert | type, severity, area polygon, valid time | Public | IMD, CWC, NDMA SACHET (CAP) |
| Resource (relief) | type, quantity, location, owner unit | Public | SDMA stock registers |
| Media / Report | URL or file, language, extracted entities | Varies | News feeds, field reports |

### 7.3 Core link types (selection)

| Link | From → To | Notes |
| --- | --- | --- |
| accused\_in / victim\_in / witness\_in | Person → Incident | Role on the FIR |
| resides\_at / works\_at | Person → Location / Organisation | Time-bounded |
| owns / registered\_to | Person or Org → Vehicle, Phone, BankAccount | Source-attributed |
| transferred\_to | BankAccount → BankAccount (via Transaction) | Money-flow graph |
| director\_of / partner\_in | Person → Organisation | From MCA data |
| located\_in | Location → AdminUnit | LGD hierarchy |
| part\_of | Incident → Case | Case scoping boundary |
| same\_as (candidate) | Person → Person | Output of entity resolution, with score and reviewer |
| affects | Hazard → AdminUnit / Asset | Disaster impact |
| beneficiary\_of | Person → Scheme | Welfare analytics |

### 7.4 Actions (the "kinetic" layer)

Actions are the only way to change the ontology, and each is validated and logged:

- `open_case(purpose, legal_basis, approver)`
- `confirm_match(person_a, person_b, reason)` / `reject_match`
- `request_external_data(case, source, legal_order_id)`
- `flag_for_review(object, reason)`
- `dispatch_resource(resource, location)` (disaster app)
- `close_case(outcome)` → starts retention timer

### 7.5 Example (YAML definition)

```yaml
object_type: Vehicle
sensitivity: personal
properties:
  registration_no: {type: string, pattern: "^[A-Z]{2}[0-9]{1,2}[A-Z]{0,3}[0-9]{4}$", key: true}
  make: {type: string}
  colour: {type: string}
links:
  registered_to: {target: Person, cardinality: many, time_bounded: true}
  seen_at: {target: Location, via: Event}
provenance: required
retention: case_bound
```

## 8. Module-by-module functional spec

DRISHTI has 12 modules; the first five (Connect, Resolve, Ontology, Explore, Guard) make a usable minimum product, and the rest are added per use case.

| # | Module | What it does | Key features | MVP? |
| --- | --- | --- | --- | --- |
| M1 | **Connect** (ingestion) | Pulls data from files, APIs, databases, feeds | Connectors for CSV/Excel/PDF, REST/JSON, PostgreSQL/MySQL/Oracle, RSS, CAP alerts; schedules; schema mapping UI | Yes |
| M2 | **Resolve** (entity resolution) | Decides which records are the same real thing | Indic name normalisation, transliteration, phonetic keys, Splink probabilistic matching, human review queue | Yes |
| M3 | **Ontology** service | Stores objects, links, properties and versions | Schema registry, typed API (GraphQL + REST), provenance, time-travel queries | Yes |
| M4 | **Explore** (search + graph) | Find and expand entities | Full-text multilingual search, graph canvas with expand/filter, path finding between two entities | Yes |
| M5 | **Guard** (security + audit) | Controls who sees what and records everything | SSO, RBAC + ABAC, purpose binding, masking, hash-chained audit log, oversight console | Yes |
| M6 | **Map** | Geospatial analysis | Layers (admin boundaries, hazards, assets, incidents), heatmaps, draw-to-filter, time slider | Phase 2 |
| M7 | **Timeline** | Chronological view | Merged timeline of all events for an entity or case | Phase 2 |
| M8 | **Case** workspace | Run an investigation or operation | Case creation with legal basis, notes, evidence locker with SHA-256 hashes, tasking, BSA-compliant export | Phase 2 |
| M9 | **Alert** | Watch for changes | Rules ("notify if any vehicle in case X appears in a new FIR"), geofences, hazard triggers, delivery via email/SMS/Sandes | Phase 2 |
| M10 | **Dash** (dashboards) | KPIs for leaders | District dashboards, scheme KPIs, crime trends, built on Superset | Phase 2 |
| M11 | **AI Assist** | AI assistant and document understanding | Auto-translation of regional-language records to English, NER, OCR, English Q&A assistant over the ontology | Phase 3 |
| M12 | **Edge** (offline kit) | Works in a police station or flood zone with poor internet | Single-machine install, sync when online, encrypted USB transfer | Phase 3 |

### 8.1 Key user stories (acceptance criteria)

- [ ] As an IO, I can type a name in Marathi or English and get the same Person object with all linked FIRs in under 2 seconds.
- [ ] As an analyst, I can select two persons and see the shortest connection path, with the source record for every link.
- [ ] As a control-room operator, I can see all shelters within a flood polygon and their capacity on one map.
- [ ] As an auditor, I can list every query run on a given person, by whom, for which purpose.
- [ ] As a data steward, I can add a new CSV source and map it to ontology types without writing code.
- [ ] As an SP, I get an alert when an accused in my district appears in an FIR in another district.

### 8.2 Non-functional requirements

| Requirement | Target (state-level deployment) |
| --- | --- |
| Objects | 100 million+ |
| Search latency | < 1 s at p95 |
| Graph expansion (2 hops) | < 2 s |
| Concurrent users | 2,000 |
| Availability | 99.5% (on-prem, single region) |
| Data residency | 100% in India (MeghRaj / state data centre) |
| Languages in UI | English only |

### 8.3 Object Explorer: top-down analysis over millions of records

Object Explorer answers questions about whole populations of records, such as "which accounts received 20+ deposits just under ₹50,000 in 30 days?". The Graph answers questions about one subject; Explorer finds which subjects matter in the first place. It is the equivalent of Gotham's Object Explorer, and every result can be sent straight to Graph, Map or a case.

**Screen layout**

| Zone | What it shows |
| --- | --- |
| Top | Global search bar + object-type picker (FIRs, Persons, Phones, Vehicles, Transactions, Companies, Seizures, Vessels, Incidents) |
| Filter bar | Active filters as removable chips; save, share and "watch this exploration" buttons |
| Explore tab | A grid of charts, one per important property: bar charts for categories (state, section of law, bank), histograms for numbers (amount, quantity), a timeline for dates, a mini-map for locations. **Clicking any bar, range or region adds that filter**, and every other chart updates instantly |
| Results tab | Sortable table of matching objects, column picker, export |
| Right preview | Top 20 matching objects as cards; click one to open its profile |
| Pivot | Jump from the filtered set to linked objects (e.g. Seizures → their accused Persons → those persons' Phones) |
| Compare | Put two filtered sets side by side (this year vs last year, Maharashtra vs Gujarat) |
| Bulk actions | Add to graph, add to case, watch all, tag, export |

**Example explorations by agency**

| Agency | Exploration | Pivot / result |
| --- | --- | --- |
| NIA | UAPA FIRs, last 5 years, by state and month | Phones appearing in 2+ FIRs → open as graph |
| CBI | Bank NPA accounts above ₹50 crore | Directors common to 3+ borrower companies |
| ED / FIU | Cash deposits ₹45,000–49,999, 20+ per account in 30 days | Account holders → companies with nil GST returns |
| NCB / DRI | Seizures of mephedrone, Maharashtra + Gujarat, 2024–26 | Accused in 2+ seizures; clusters on the map |
| IB | Incident reports tagged with a threat category, by district | Districts with a sudden rise vs 12-month baseline |
| Army / Coast Guard | Vessel tracks with AIS gaps over 6 hours within 50 nm of the coast | Vessels repeating the pattern → watchlist |
| State police | Vehicle-theft FIRs + recovered vehicles | Common receivers and scrapyards |
| CERT-In | Phishing domains registered in the last 30 days | Shared hosting IPs → linked cyber-fraud FIRs |

**Behaviour and performance**

- Charts over 100 million rows return in under 1 second using OpenSearch aggregations; heavy joins run on DuckDB/Parquet. Approximate counts are labelled.
- Saved explorations refresh automatically and can raise an Inbox alert when new records match.
- Explorer shows counts and charts freely within the officer's clearance; opening an individual record is logged against the active case like any other view.
- Built with React + [Apache ECharts](https://echarts.apache.org/) (Apache 2.0) on the ontology API.

### 8.4 Dossier: live intelligence reports and chargesheet documents

Dossier turns analysis into the products agencies actually deliver: intelligence summaries, case diaries, chargesheet annexures, prosecution complaints and briefs for senior officers. It is the equivalent of Gotham's Dossier, with Indian legal templates built in.

**Core features**

- **Real-time co-editing** by several officers, with comments, suggestions and full version history.
- **Live objects:** @-mention any person, phone, vehicle or account and it becomes a card that updates when the underlying record changes.
- **Live exhibits:** drag in a graph clip, map snapshot, Explorer chart or timeline; it stays live while drafting and is frozen with a timestamp at export.
- **Source citations:** every fact inserted from the system carries its source (CCTNS, ICJS, NATGRID, legal order number), and an automatic "sources and evidence" annexure is generated.
- **Classification markings** per section and per paragraph; the document's overall marking is the highest one inside it.
- **Release copies:** one click creates a sanitised version for another agency, automatically removing paragraphs and objects above the recipient's clearance.
- **Review workflow:** Draft → Reviewed → Approved for release → Disseminated, with a distribution list and read receipts.
- **Export** to PDF and Word with agency letterhead, page numbers, annexure tables and an index of exhibits; every export is logged and watermarked.
- **Evidence pack** for court: SHA-256 hashes of every exhibit, chain-of-custody log, and a draft certificate for electronic records under Section 63 of the Bharatiya Sakshya Adhiniyam, 2023.

**Templates by agency**

| Agency | Templates |
| --- | --- |
| NIA | Chargesheet annexures (BNSS s.193), UAPA sanction request, intelligence summary |
| CBI | Preliminary enquiry report, chargesheet annexures, sanction-for-prosecution note |
| ED | Prosecution complaint annexures (PMLA), provisional attachment note, money-trail exhibit |
| NCB | Seizure and recovery summary, NDPS chargesheet annexures |
| IB / R&AW | Intelligence report, threat assessment, sanitised alert for state police |
| Army / Coast Guard | SITREP, INTSUM, incident report |
| State police | Case diary extract, chargesheet annexures, crime review brief |

**Technology:** TipTap/ProseMirror editor (MIT) + Yjs for live co-editing; templates in Jinja; export via LibreOffice (headless) or WeasyPrint; hashes and custody log written to the audit chain.

## 9. Zero-cost open-source technology stack

The whole platform can be built for ₹0 in licence fees using permissively licensed open-source software, and the prototype can run on one laptop plus a free cloud VM. Prefer Apache 2.0 / MIT / BSD components so government can adopt the code without legal friction.

### 9.1 Recommended stack

| Layer | Choice | Licence | Why | Alternative |
| --- | --- | --- | --- | --- |
| Core database | PostgreSQL 16 | PostgreSQL (permissive) | Mature, govt-familiar, runs everywhere | — |
| Graph | [Apache AGE](https://age.apache.org/) (Postgres extension) | Apache 2.0 | SQL + openCypher in one database; no separate graph DB to run | Neo4j Community (GPLv3), JanusGraph |
| Geospatial | PostGIS | GPLv2 | Spatial queries, polygons, distance | — |
| Search | OpenSearch | Apache 2.0 | Multilingual full-text, fuzzy matching, ICU analyzers for Indic scripts | Meilisearch (MIT) for small setups |
| Analytics / files | DuckDB + Parquet | MIT | Fast local analytics, cheap storage of raw data | ClickHouse |
| Object storage | MinIO (or SeaweedFS) | AGPLv3 / Apache 2.0 | Store documents, images, evidence | Local disk at MVP |
| Pipelines / ETL | Dagster | Apache 2.0 | Asset-based pipelines with lineage | Apache Airflow, Prefect |
| Streaming (later) | Apache Kafka | Apache 2.0 | Real-time feeds (alerts, AIS) | NATS (Apache 2.0) |
| Entity resolution | [Splink](https://github.com/moj-analytical-services/splink) | MIT | Fellegi–Sunter probabilistic linkage, unsupervised (no labels needed), \~1M records on a laptop in a minute | Zingg (AGPL), dedupe |
| Ontology API | Python FastAPI + Strawberry GraphQL | MIT | Typed, fast, easy for students | Hasura (Apache 2.0) |
| Identity / SSO | Keycloak | Apache 2.0 | Users, roles, MFA, LDAP/AD integration | Authentik |
| Policy engine | Open Policy Agent (OPA) | Apache 2.0 | Fine-grained ABAC rules as code | Cedar (Apache 2.0) |
| Audit log | Postgres append-only table + hash chain; optional immudb | Apache 2.0 | Tamper-evident logs | — |
| Frontend | React + TypeScript + Vite | MIT | Standard, big talent pool | SvelteKit |
| Graph visualisation | Cytoscape.js or Sigma.js | MIT | Interactive link charts | Reagraph |
| Maps | MapLibre GL JS + OpenStreetMap tiles; Bhuvan WMS layers | BSD / ODbL | No Google Maps fees | Leaflet |
| Dashboards | Apache Superset | Apache 2.0 | KPIs for collectors without coding | Metabase (AGPL) |
| Indic NLP | AI4Bharat IndicTrans2, IndicXlit, IndicNER | MIT / CC-BY | Translates source records to English; name transliteration | Bhashini APIs |
| LLM assistant | Open-weight model via Ollama / vLLM, run locally | Model-specific open licence | Data never leaves the server | — |
| OCR | Tesseract (Indic language packs) / docTR | Apache 2.0 | FIR scans, PDFs | — |
| Deployment | Docker Compose → Kubernetes (k3s) | Apache 2.0 | Laptop → data-centre with the same images | — |
| Observability | Prometheus + Grafana | Apache 2.0 / AGPL | Monitoring | — |
| CI / code hosting | GitHub (free) + GitHub Actions | — | Free for public repos | GitLab CE |

> Note on Neo4j: in June 2026 Neo4j acquired GraphAware (makers of the Hume investigative tool) to build an "open-standard alternative to Palantir Gotham" ([heise](https://heise.de/-11317197)). That validates the approach, but Neo4j Community is GPLv3 and its advanced features are commercial, so DRISHTI defaults to Apache AGE and keeps queries in openCypher so either works.

### 9.2 Free infrastructure for development

| Resource | What you get free | Use in DRISHTI |
| --- | --- | --- |
| Your laptop (16 GB RAM) | Docker Compose of the whole stack with sample data | Daily development |
| Oracle Cloud Always Free | Ampere A1 Arm VM; officially 4 OCPU / 24 GB plus 200 GB block storage ([Oracle docs](https://oracle.hydrogen.sagittarius.connect.product.adaptavist.com/iaas/Content/FreeTier/resourceref.htm)), though a 2026 report says new allocations were halved to 2 OCPU / 12 GB ([terminalbytes](https://terminalbytes.com/oracle-cloud-free-tier-changes-2026)) — check your console | Public demo server |
| Google Colab / Kaggle notebooks | Free GPU hours | Fine-tuning Indic NER, running IndicTrans2 batch jobs |
| GitHub Student Developer Pack | Free credits and tools | Domain, CI, cloud credits |
| Hugging Face | Free model hosting and Spaces | Host Indic models and a demo UI |
| AIKosh (IndiaAI) | Government catalogue of Indian datasets and models | Datasets and Bhashini models |

### 9.3 Why not just use Palantir-like commercial tools?

Commercial alternatives such as DataWalk advertise roughly a quarter of Gotham's licence price, citing $35K per server core versus a GSA list price of $141K per core for Gotham ([DataWalk brochure](https://www.dlt.com/sites/default/files/resource-attachments/2022-05/DataWalk-The-Palantir-Alternative.pdf)). A state-level deployment of 32–64 cores at those prices is roughly ₹9–75 crore in licences alone. DRISHTI's licence cost is zero, and the government owns the code and the ontology.

### 9.4 Scale-up path (state or national deployment)

The Section 9.1 stack fits a student team and a district pilot. If a state or NIC/C-DAC team takes DRISHTI to tens of crores of records, these swaps keep the same ontology and APIs:

| Component at pilot scale | Swap at state / national scale | Why |
| --- | --- | --- |
| PostgreSQL + Apache AGE | JanusGraph on Cassandra/ScyllaDB (Apache 2.0) | Graphs with billions of edges |
| DuckDB + Parquet files | MinIO + Apache Iceberg tables queried by Trino | Query large source copies in place without centralising them |
| Dagster batch jobs | Apache Kafka / NiFi streaming | Real-time feeds from many sources |
| Splink on DuckDB | Splink on Spark, or Zingg | Entity resolution over crore-scale records |
| OPA only | OPA + OpenFGA (relationship-based access) | Complex sharing rules between agencies |
| Environment variables | HashiCorp Vault / OpenBao | Secret and key management |

Because queries stay in openCypher/GraphQL and the ontology is defined as code, apps built at pilot scale keep working after the swap.

## 10. Data you can use legally for free

You can build and demo a convincing DRISHTI with zero personal data, using open government and open-source datasets; personal data enters only after a department signs an MoU and supplies it under its own legal authority.

### 10.1 Tier A: open data for the prototype (no permission needed)

| Source | What it gives | Access | Used by app |
| --- | --- | --- | --- |
| data.gov.in (OGD Platform) | 100,000+ API resources across ministries ([datagovindia on PyPI](https://pypi.org/project/datagovindia/0.4)); licensed under Government Open Data Licence – India | Free API key | All apps |
| NDMA SACHET | CAP 1.2 disaster alerts from IMD, CWC, INCOIS, state SDMAs via RSS ([thejeshgn](https://thejeshgn.com/2025/05/28/common-alerting-protocol-cap-in-the-indian-context/)) | Public RSS | Disaster COP |
| IMD | District forecasts, nowcasts, warnings | Public website / feeds | Disaster COP |
| CWC / India-WRIS | River levels, reservoir storage | Public portal | Flood monitoring |
| Local Government Directory (LGD) | Codes for every state, district, block, village, ward | Public download | Ontology AdminUnit backbone |
| Bhuvan (ISRO) | Satellite base maps, thematic layers (WMS) | Free with registration | Map module |
| OpenStreetMap | Roads, buildings, hospitals, schools | ODbL | Map, asset layers |
| NCRB *Crime in India* tables | District/state crime statistics by year | Public PDFs/Excel (also on data.gov.in) | Aggregate crime analytics |
| e-Courts / NJDG | Court case pendency statistics, case status by CNR | Public portal | Justice dashboard |
| MCA company master data | Companies, directors (DIN), registration | Public search | Fraud networks (organisations) |
| GeM / CPPP tenders | Public procurement awards | Public | Procurement fraud |
| OpenSanctions | Global sanctions and PEP lists in FollowTheMoney format | Open (non-commercial free) | Watchlist matching |
| GDELT | Global news events, geocoded | Free | Event monitoring |
| AIS (open feeds) / ADS-B Exchange / OpenSky | Ships and aircraft positions | Free tiers | Coastal / airspace app |
| Census 2011, NFHS, PLFS | Demographic and socio-economic baselines | Public | Context layers |
| AIKosh | Indian datasets and AI models catalogue | Free | NLP training |

### 10.2 Tier B: synthetic data for the police and fraud demos

Never use real FIRs or personal records in a student project. Instead:

- Generate synthetic Indian persons with a Faker-style generator using real name distributions by state, LGD addresses, realistic phone/vehicle number formats.
- Generate synthetic FIRs (BNS sections, police stations from LGD) and inject known "rings" (shared phones, vehicles) so you can prove entity resolution and link analysis find them.
- Publish the generator as open source; it becomes a benchmark dataset other researchers can use.

### 10.3 Tier C: real departmental data (only with a legal agreement)

| Source | Owner | How it would connect |
| --- | --- | --- |
| CCTNS exports | State police / SCRB | Read-only nightly export via state data centre |
| ICJS / NATGRID responses | NCRB / MHA | Attached per case by an authorised officer; never bulk-loaded |
| VAHAN / SARATHI | MoRTH | Lookup API under existing police access |
| Cybercrime complaints (I4C) | MHA | Complaint export for the state cyber cell |
| Welfare MIS (PDS, pensions, PM-KISAN) | State departments | Periodic de-identified extracts for leakage analysis |
| Hospital / IDSP | Health department | Aggregated counts only |

**Rule:** Tier C data stays on the department's own server (on-prem DRISHTI instance); the student team never receives it.

## 11. Security model, access control and audit

Security in DRISHTI is enforced at the data layer, not the UI: every object, property and link carries labels, and every query is checked by a policy engine against the user's role, clearance, case membership and declared purpose before any row leaves the database.

### 11.1 Access-control model

| Control | How it works | Tool |
| --- | --- | --- |
| Authentication | SSO with MFA; integrates with state LDAP / Parichay | Keycloak |
| Role-based (RBAC) | Roles: viewer, analyst, IO, supervisor, data steward, auditor, admin | Keycloak roles |
| Attribute-based (ABAC) | Rules on user attributes (district, rank, unit) × data attributes (sensitivity, district, case) | OPA policies (Rego) |
| Mandatory labels | Each object labelled PUBLIC / RESTRICTED / CONFIDENTIAL / SECRET; users need matching clearance | Postgres row-level security + OPA |
| Case membership | Personal data visible only to members of the case it belongs to | Ontology link `part_of` + policy |
| Purpose binding | Query rejected unless a purpose/case is active in the session | API middleware |
| Field masking | Aadhaar, phone, account numbers masked by default; unmask needs reason | Postgres views + policy |
| Separation of duties | Admins cannot read data or edit audit logs; auditors cannot change data | Role design |

### 11.2 Audit log design

- Every API call writes: user, role, purpose/case ID, query text, objects returned (IDs), timestamp, IP, client.
- Records are append-only; each row stores the SHA-256 hash of the previous row (hash chain), and a daily root hash is published to a separate system so tampering is detectable.
- An **oversight console** lets an independent officer search logs, see unusual patterns (e.g., one user querying many unrelated persons at midnight) and export reports.

### 11.3 Infrastructure security

- Encryption: TLS 1.3 in transit; disk and database encryption at rest; per-tenant keys.
- Deployment on government-owned infrastructure: state data centre or MeitY-empanelled sovereign cloud; no data to foreign clouds.
- Network segmentation: ingestion zone, core zone, user zone; no direct internet access for the core.
- Supply-chain security: pinned dependencies, SBOM (CycloneDX), signed container images (cosign), Dependabot.
- Testing: OWASP ASVS Level 2 checklist, annual third-party audit by a CERT-In empanelled auditor.
- Incident response aligned to CERT-In 6-hour reporting directions and DPDP breach intimation.

### 11.4 Example policy (OPA / Rego)

```rego
package drishti.access

default allow := false

allow if {
  input.user.clearance >= input.object.sensitivity
  input.session.purpose_id != ""
  input.object.case_id in input.user.cases
}

allow if {
  input.object.sensitivity == 0   # PUBLIC
}
```

### 11.5 Threat model

| Threat | Example | Defence in DRISHTI |
| --- | --- | --- |
| Hostile-state hacking | Attack aimed at stealing the whole fusion store | Assume breach: store only case-scoped data, encrypt everything, segment networks, and plant **canary records** (fake entries that trigger an alarm if they are ever queried or leave the system) |
| Insider curiosity or vendetta | Officer looks up an ex-spouse's vehicle or a neighbour | Purpose binding plus **insider-threat analytics on the audit log**: alerts for unusual volume, queries outside the user's district, searches on VIP or colleague records, late-night bulk lookups |
| Sale of access | Account used to sell data to private parties | Two-person rule for bulk export, rate limits, device binding, export watermarking |
| Supply-chain compromise | Malicious package in a dependency | SBOM, pinned and vendored dependencies, signed images, code review gates |
| Mission creep | Platform reused to watch protesters or opponents | Hard-coded purpose list that excludes such use, external oversight board, published transparency report |
| Legal challenge | Petition under Puttaswamy | Keep a litigation-ready evidence pack: policies, audit samples, DPIAs, proportionality notes per data source |

### 11.6 Scenario planning

- **States refuse to connect their data** → offer free analytics back to them (heatmaps and pendency dashboards for DGPs); keep data custody with the state.
- **Analysts do not use it** → embed it in existing workflows (Cri-MAC alerts, Zero FIR transfers); track weekly active users; fix what they complain about every week.
- **Political turnover** → institutional home (NCRB/SCRB or C-DAC maintenance) and open code that any NIC engineer can maintain.

## 12. AI layer (English-only interface)

DRISHTI's interface, search, reports and AI assistant work in English only. Source records written in regional languages (FIRs, statements, seized documents) are converted to English automatically when they are ingested, so every officer sees and searches one language, and the original stays attached as evidence.

### 12.1 Building blocks

| Need | Model / tool | Role in DRISHTI |
| --- | --- | --- |
| Translation at ingestion | [IndicTrans2](https://github.com/AI4Bharat/IndicTrans2) | Converts regional-language source text to English once, in the background; INT8 builds run offline on CPU |
| Transliteration | IndicXlit | Converts names in other scripts to English spelling so one person is not split into several records |
| Named-entity recognition | English NER (spaCy / fine-tuned transformer) | Extracts persons, places, organisations, phones, vehicles and amounts from English text |
| OCR | Tesseract / docTR | Scanned FIRs, seized documents and PDFs |
| Embeddings / semantic search | Sentence-embedding model | Finds related documents by meaning, not just keywords |
| LLM assistant | Locally hosted open-weight model | Runs on-premises; data never leaves the agency |

### 12.2 Indian name matching pipeline (core of the Resolve module)

1. **Detect script** and language.
2. **Transliterate** every name to a common Latin form (ISO-15919) and also keep the native form.
3. **Normalise**: strip honorifics (Shri, Smt, Mohd., Dr.), expand abbreviations, handle initials ("R. K. Patil").
4. **Split** into given / father / surname parts using Indian naming patterns (Maharashtrian three-part names, South Indian initial-first names, single names).
5. **Phonetic keys**: an Indic-aware Soundex/Metaphone variant (e.g., merge "v/w", "sh/s", "z/j", aspirated pairs).
6. **Compare** with Splink using name similarity (Jaro–Winkler on transliterated form), father's name, age band, district, phone, address tokens.
7. **Score and route**: >0.95 auto-link as candidate, 0.7–0.95 to human review queue, <0.7 reject. Humans confirm via the `confirm_match` action, which trains the next model run.

Two further rules for Resolve:

- **Every merge is reversible.** A `same_as` link never overwrites the original records; un-merging restores both objects with full history.
- **Data-quality feedback to source agencies.** DRISHTI reports duplicate rates, empty fields and spelling inconsistencies back to the department that owns each source, so it also improves CCTNS and departmental MIS data at the origin.

### 12.3 The DRISHTI assistant (Ontology-Augmented Generation)

Instead of letting an LLM read raw documents (RAG), the assistant answers by calling ontology functions, so every answer is grounded, permission-checked and cited:

- Officer: "When were P1 and P2 in the same tower sector in the last 30 days, and did truck MH-04-XX-7781 cross a toll before each meeting?"
- Assistant → calls `colocation(P1, P2, 30d)` and `toll_hits(vehicle, window)` with the officer's permissions → returns a table of times, the gap to each toll crossing, and the source rows.
- The assistant can **propose** actions ("create a lead for a search authorisation") but an officer decides; this mirrors how Palantir AIP routes LLM output through ontology actions.

### 12.4 AI guardrails

- The LLM never sees data the user is not allowed to see (it runs inside the same policy check).
- No generative output is treated as evidence; it is labelled "AI-generated summary".
- Every AI suggestion stores the prompt, tools called and outputs in the audit log.
- Model cards and evaluation results, including translation accuracy, are published.

## 13. Build roadmap and team plan

A team of 4–6 students can reach a working MVP in about 5 months and a district pilot in about 12, spending nothing, if scope is held tight; the gate that matters most is a signed MoU with a district or SDMA.

&#91;embedded content: Build roadmap · 4 phases, 4 gates, Nov 2026 to Oct 2027\]

Each phase ends at a gate; do not start the next phase until the gate's demo works end-to-end on open or synthetic data.

### 13.1 Team roles

| Role | Owns | Key skills to learn |
| --- | --- | --- |
| Tech lead / architect | Ontology schema, API design, code reviews | Postgres, GraphQL, system design |
| Data engineer | Connect module, Dagster pipelines, open-data connectors | Python, SQL, ETL |
| ML / NLP engineer | Resolve module, IndicXlit, Splink, AI assistant | Record linkage, transformers |
| Frontend engineer | Explore, Map, Case UIs | React, Cytoscape.js, MapLibre |
| Security engineer | Guard: Keycloak, OPA, audit chain | IAM, Rego, threat modelling |
| Policy / outreach lead (can be part-time) | Legal framework, MoUs, pitches, documentation | DPDP Act, government process |

### 13.2 First 30 days (concrete tasks)

- [ ] Create a public GitHub repo with Apache 2.0 licence, README, code of conduct, architecture doc (this document).
- [ ] Write `ontology/core.yaml` with Person, Organisation, Location, AdminUnit, Event, Hazard, Asset and 10 link types.
- [ ] Docker Compose: Postgres + AGE + PostGIS, OpenSearch, Keycloak, FastAPI skeleton, React skeleton.
- [ ] Load LGD codes and district boundaries for one state (Maharashtra) as AdminUnit objects.
- [ ] Build a SACHET CAP RSS connector that turns alerts into Hazard objects linked to districts.
- [ ] Load hospitals and schools from OpenStreetMap as Asset objects.
- [ ] Build a synthetic persons + FIR generator with 3 planted fraud rings.
- [ ] Run Splink on the synthetic persons and measure precision and recall.
- [ ] Show a map: live hazard polygons over Maharashtra with hospitals inside them.
- [ ] Record a 3-minute demo video.

### 13.3 Success metrics per gate

| Gate | Metric |
| --- | --- |
| Laptop demo | Full stack starts with one command; 1 state of open data loaded |
| Hackathon-ready MVP | Entity resolution F1 ≥ 0.9 on synthetic data; graph path query < 2 s; every query audited |
| District MoU signed | Signed letter from a Collector / SDMA; data-sharing scope written down |
| Pilot review | 20+ officials using it weekly; documented decisions it supported; independent security audit passed |

### 13.4 Zero-budget rules

- Only open-source components with permissive or OSI licences; no paid SaaS in the core path.
- Host demos on free tiers; host pilots on the department's own servers (their cost, not yours).
- Use free GPU notebooks for model work; run inference on CPU with INT8 ONNX models.
- Apply to hackathons, IndiaAI and incubators for prize money and credits instead of spending.

## 14. Go-to-government path, risks and comparison

The realistic route for a student team is: open-source prototype on open data → hackathon / academic recognition → pilot with one district or SDMA under an MoU → state adoption; police use comes last, after the civil pilot proves trust.

### 14.1 Channels into government (zero cost to enter)

| Channel | What it gives you | Fit |
| --- | --- | --- |
| Smart India Hackathon | Problem statements from ministries, police and DRDO; visibility to officials | Pitch DRISHTI modules against relevant problem statements |
| District Collector / SDMA directly | A real user and real (non-personal) data | Best first pilot: disaster COP or district dashboard |
| State police innovation cells / cyber hackathons | Access to SCRB and cyber cell officers | Synthetic-data demo of fraud-ring detection |
| iDEX (Innovations for Defence Excellence) | Defence challenges and grants for startups | Later, for coastal / border awareness app |
| IndiaAI / AIKosh, Bhashini | Models, datasets, compute schemes | Indic layer; potential compute support |
| MeitY Startup Hub, Startup India (DPIIT recognition) | Incubation, credibility | When you form a company |
| GeM | Government procurement marketplace, startup-friendly categories | For selling support/services around the open code |
| Govt. of India Open Source Policy (2015) | Requires departments to prefer open source | Key argument in every pitch |

**Business model if it becomes a startup:** the code stays open source (Apache 2.0); revenue comes from deployment, customisation, training, ontology design and annual support contracts, which is how Red Hat-style open-source companies work and how Palantir actually earns (forward-deployed engineers).

### 14.2 Risks and mitigations

| Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- |
| Misuse for mass surveillance | Medium | Very high | Hard-coded safeguards (Section 5), refuse such deployments, public transparency report |
| Legal challenge (Puttaswamy, DPDP) | Medium | High | Build to full DPDP standard; case-scoping; legal review before any personal-data pilot |
| No access to real data | High | Medium | Start with open data and synthetic data; civil use cases first |
| Data quality in source systems | High | High | Data-quality dashboards, provenance, human review of matches |
| Entity resolution errors linking innocent people | Medium | Very high | Never auto-merge; candidate links only; human confirmation; explainability |
| Security breach | Medium | Very high | Defence-in-depth, audits, on-prem only |
| Team burnout / student turnover | High | Medium | Good docs, modular code, small scope per semester |
| Competition from large integrators | High | Medium | Open source + Indian data integration + low cost as differentiators |
| Procurement complexity | High | Medium | Pilot through MoU and hackathons before formal tenders |

### 14.3 Comparison: Gotham vs NATGRID vs DRISHTI

| Capability | Palantir Gotham | NATGRID | DRISHTI (proposed) |
| --- | --- | --- | --- |
| Ontology / object model | Yes, proprietary | No (record lookup) | Yes, open YAML schema |
| Link / graph analysis | Yes | Limited | Yes |
| Geospatial | Yes | Not core | Yes (MapLibre, PostGIS, Bhuvan) |
| Regional-language source data | Weak | Unknown | Regional-language records auto-translated to English |
| Entity resolution for Indian names | Generic | Unknown | Purpose-built |
| Purpose binding and audit | Strong audit | Agency-level | Enforced per query, independent oversight console |
| Civil use cases (disaster, welfare) | Via Foundry | No | Yes |
| Licence cost | Very high (\~$141K/core list) | Govt-built (₹ crores) | ₹0 |
| Data sovereignty | US company | Indian | Indian, open code |
| Who can audit the code | No one outside vendor | Restricted | Anyone |

### 14.4 Honest limits

A student team will not match Gotham's 20 years of engineering, forward-deployed staff or classified integrations. The goal of Year 1 is a credible, working, open core with two strong apps (disaster COP and synthetic investigation workspace) and a published ontology, which is enough to win hackathons, academic credit and a first district pilot.

### 14.5 Lessons from other countries

| Country | What happened | Lesson for DRISHTI |
| --- | --- | --- |
| United Kingdom | NHS England signed a £330M Federated Data Platform contract with Palantir in 2023; by June 2026, 170 trusts had signed up, but the contract is under review before its initial term ends in March 2027 ([Digital Health](https://www.digitalhealth.net/2026/06/fdp-here-to-stay-says-patel-as-palantir-contract-faces-review/)) | A platform can be useful and still lose public trust over vendor and privacy concerns; open code and Indian ownership remove that risk |
| Germany | Constitutional Court struck down police data-analysis laws (Section 2.5) | Clear legal basis and case scoping are mandatory |
| United States | LAPD's LASER scoring ended over bias | No person-level risk scores |
| Estonia / Finland | X-Road, the national data-exchange layer, is open source under the MIT licence; each provider keeps its own data and exchanges it directly ([Interoperable Europe](https://interoperable-europe.ec.europa.eu/collection/ict-security/solution/x-road-data-exchange-layer)) | Proof that a federated, open-source exchange layer can run a whole country; DRISHTI applies the same idea to analysis |

### 14.6 KPIs

| KPI | What it measures |
| --- | --- |
| Time-to-fuse | Minutes from opening a case to a resolved entity graph (baseline: days of manual work) |
| Alert usefulness | % of alerts an officer marks as actionable |
| Cross-district leads | Links found across district or state lines per 1,000 cases |
| Source data quality | Duplicate rate and field completeness per source, tracked monthly |
| Weekly active users | Officers using DRISHTI each week |
| Audit coverage | 100% of queries logged; unauthorised-access incidents: zero |
| Disaster response | Time from alert to first resource dispatch |

### 14.7 FAQ

**Isn't this just NATGRID 2.0?** No. NATGRID is a query grid that fetches records between agencies. DRISHTI is the analysis workspace and ontology that turns lawfully obtained records into graphs, maps, timelines and reports. They work together.

**Isn't this mass surveillance?** The design is the opposite: no new data collection, case-scoped queries, minimal caching, purpose binding, independent audit and published statistics.

**Why not just buy Palantir?** Cost, data sovereignty and fit: Gotham does not natively handle regional-language records, Indian names, LGD codes or Indian legal workflows.

**Who maintains it after the students leave?** The code is open, documented and designed for NIC, C-DAC or a state IT cell to maintain, the way C-DAC maintains CCTNS components.

**Could a future government misuse it?** Any capability can be misused; DRISHTI's safeguards are built into the code (purpose binding, audit chain, insider analytics, transparency reports), not left as promises.

### 14.8 One-page pitch (for a Collector, SDMA or SP)

- **What:** DRISHTI, an open-source data-fusion and decision platform built in India for Indian data and law.
- **Cost:** zero licence fees; runs on the department's existing server.
- **Ask:** a letter of support, one non-personal dataset (e.g., shelter list, relief stock, scheme progress), and one officer for weekly feedback.
- **In 90 days you get:** a live map dashboard of your district, alerts from SACHET and IMD, and a report generator.
- **Safeguards:** no personal data in the pilot; every query audited; code open for your IT team to inspect.

## 15. The 1,000-hour learning path

This curriculum turns the research in this document into skills: 1,000 hours is about 12 months at 20 hours a week, split across a team or done by one person, and each module ends in a deliverable that is also a piece of DRISHTI.

| # | Module | Hours | What to learn | Deliverable | Feeds phase |
| --- | --- | --- | --- | --- | --- |
| 1 | Problem space and intelligence analysis | 100 | Intelligence cycle; 26/11 and 9/11 as fusion failures; link charts, timelines, analysis of competing hypotheses | A 15-page fusion-gap analysis of 26/11 from public sources | 0 |
| 2 | Indian law and ethics | 80 | Puttaswamy (2017, 2018), DPDP Act and Rules, IT Act s.69, BNSS/BSA evidence rules, German 2023 ruling | Proportionality checklist used before adding any data source | 0 |
| 3 | India's data estate | 80 | CCTNS, ICJS, NATGRID, VAHAN, MCA21, LGD, SACHET, data.gov.in; MHA and NCRB reports | Source registry with a feasibility score per source | 0 |
| 4 | Data engineering | 140 | PostgreSQL, PostGIS, DuckDB/Parquet, Dagster, OpenSearch, data contracts, lineage | Three open datasets ingested with full lineage | 0–1 |
| 5 | Graph and ontology engineering | 150 | Property graphs, openCypher on Apache AGE, ontology patterns, time-aware modelling, provenance (W3C PROV), centrality and community detection | Ontology v1 as code + a 1-crore-edge synthetic graph with 3-hop queries under 2 s | 1 |
| 6 | Entity resolution for Indian names | 110 | Blocking, Indic phonetics, transliteration (IndicXlit), Splink, evaluation with precision and recall | Resolver with a published confusion matrix on synthetic data | 1 |
| 7 | Investigative UX | 130 | React, Cytoscape.js, MapLibre, time sliders, large-graph rendering; user research with real officers | Explore, Map and Case apps tested with 5 users | 2 |
| 8 | Security, governance and audit | 90 | Keycloak, OPA/Rego, row-level security, hash-chained logs, insider-threat analytics, threat modelling | Guard module + red-team report on your own alpha | 1–2 |
| 9 | AI and LLMs | 90 | IndicTrans2, IndicNER, OCR, local LLM serving, ontology-grounded assistants, prompt-injection defences | Assistant passing a 50-question benchmark with human review | 3 |
| 10 | Delivery and government process | 30 | CCTNS/NATGRID histories, GFR and GeM procurement, 2015 open-source policy, writing a pitch and MoU | 10-slide pitch deck + draft MoU for a district | 2–3 |
|  | **Total** | **1,000** |  |  |  |

## 16. UI research: how Gotham and similar products actually look

Every serious investigation platform (Gotham, i2 Analyst's Notebook, Maltego, Linkurious, Aleph) has converged on the same screen grammar: a dense desktop workspace with a central canvas (graph or map), a left panel for search, layers or an entity palette, a right panel for the selected object and "helpers", a bottom panel for time, a tool strip on top, and objects that can be dragged from one app to another.

### 16.1 Palantir Gotham today (2024–2026)

The current Gotham is a browser-based "Palantir Workspace" of tightly linked apps where you open several app instances at once and drag objects between them (for example, a network in Graph → dragged into Gaia to see where members travelled → dragged into Dossier to write the report). Source: Palantir's 2024 G-Cloud 14 service definition ([Digital Marketplace](https://assets.applytosupply.digitalmarketplace.service.gov.uk/g-cloud-14/documents/92736/801146272055049-service-definition-document-2024-11-26-1253.pdf)) unless noted.

| App | What the modern interface does |
| --- | --- |
| **Graph** | A shared **Canvas**, edited live by several analysts at once. Helpers beside it: **Histogram** (frequency of object types, properties, relationships, events per entity, notes, tags), **Selection** (a mini Browser for the selected item), **History** (who changed the graph and when), **Table** (tabular view, exportable), **Search Around** (visual query that can return whole sub-graphs), **Timeline** (time ranges of objects and links). Graphs export as interactive HTML |
| **Gaia** | Collaborative geospatial command-and-control map: geo-search by radius, route, polygon, time, type, property or keyword; heatmaps; SHP/KMZ/KML/LYR layers; live feeds; shared operation planning. Palantir is now building **3D Gaia**, a globe powered by its own Three.js library "Zodiac", with satellite orbits, sensor swaths, lines of sight, time-filterable and animated tracks ([Palantir blog, Apr 2026](https://blog.palantir.com/frontend-engineering-at-palantir-plotlines-in-three-js-c0c47f310715)) |
| **Browser + Custom Object Views** | Object page with properties, notes and change history; teams build no-code dashboard tabs per object type, with tabs locked by permission |
| **Object Explorer** | Top-down analysis over millions of records with charts as filters, timelines, and subscribable object alerts |
| **Inbox** | One triage screen for all alerts, grouped into channels: search feeds, object watches, **geofence alerts** drawn in Gaia, sharing alerts; each alert links straight to the app that resolves it |
| **Chat** | Built-in, classification-aware messaging; drag objects into a chat; content auto-redacted for members without access |
| **Dossier** | Real-time collaborative editor; @-mention objects, drop in live graphs and maps that keep updating; templates; export to Word/PDF |
| **Slides** | Briefing decks backed by live data, collaborative editing, live "broadcast" presenting; embedded graph clips open back in Graph |
| **Video** | Live or archived video with map layers and AI detections as **AR overlays**; one-click tagging creates objects; detections confirmed or dismissed by the user |
| **AIP Assist / AIP Threads** | LLM side-panel assistant: natural-language questions, answers grounded in the ontology, proposed courses of action the user approves ([Maven one-pager](https://assets.ctfassets.net/xrfr7uokpv1b/25muZs93DY5XOUBtuh68yn/b40d9784f69917219f972890ceede986/Maven_One_Pager.pdf)) |

**Maven Smart System (2026), the most advanced public example.** Public demos show a fused map on a globe with all layers on one surface; computer-vision detections that keep one stable ID across satellite, drone and CCTV views; a **Kanban board** where detections are "nominated" and move across columns representing each team's stage; the system recommends a plan and a human approves it ([Spatial Intelligence](https://www.spatialintelligence.ai/p/inside-palantirs-maven-smart-system)). Its UX idea is "one screen, few clicks": the Pentagon's AI chief described it as left click, right click, left click.

**What changed since the old 2013 interface.** The 2013 police training guide ([DocumentCloud](https://s3.documentcloud.org/documents/21583103/palantir_1013_-_graph.pdf)) shows a desktop-style tool with a coloured app bar and helper menus. The 2024–2026 platform keeps the same object-and-helper model but adds: real-time multi-user editing, history on every artefact, a unified alert inbox, built-in chat, live-data briefings, 3D globe rendering, AI assistants in a side panel, and Kanban-style operational workflows.

Palantir's current public docs show the same pattern in its newer apps:

| App | Layout documented by Palantir |
| --- | --- |
| Map ([docs](https://palantir.com/docs/foundry/map/map-overview/)) | Left panels: Layers, Find, Histogram, Info. Right panels: Selection, Time Selection. Bottom-right: Series panel for time. Top toolbar: Select, Search Around, Draw, Capture, Measure, Annotate, Delete |
| Vertex graph ([docs](https://palantir.com/docs/foundry/vertex/explore-object-relationships/)) | Search Around panel in the right-side tabs (multi-step, filtered, saveable); histogram filters that group nodes; results auto-grouped above a size limit; time series at the bottom |
| Object Explorer ([docs](https://www.palantir.com/docs/foundry/object-explorer/explore-charts/)) | Global search bar; an "Explore" view that is a grid of charts, one per property, used as clickable filters; a Results table tab; a preview list of up to 20 results on the right |

**The visual toolkit:** Palantir open-sourced [Blueprint](https://github.com/palantir/blueprint), its React UI toolkit built for complex, data-dense desktop web apps, with light and dark themes. Its licence is Apache 2.0 plus one clause: derivative products must not be passed off as Palantir's.

### 16.2 Similar products

| Product | Signature UI elements |
| --- | --- |
| i2 Analyst's Notebook | Ribbon toolbar; association charts and timeline charts; maps, network and time in one workbench; charts shareable through a free Chart Reader ([i2 Group](https://i2group.com/hubfs/Products/i2-Analysts-Notebook.pdf)) |
| Maltego | Entity palette on the left, graph in the centre, overview minimap, detail/property view of the selection; layouts (block, hierarchical, circular, organic); list view; node size by rank; browser version toggles graph, map and table views ([Maltego docs](https://docs.maltego.com/en/support/solutions/articles/15000059532-navigate-the-interface)) |
| Linkurious Enterprise | Timeline panel opened from a clock icon: histogram of date properties with drag handles to filter, plus counts of missing and invalid values ([manual](https://doc.linkurious.com/user-manual/3.1/timeline)); geo-mode puts nodes on a map; comments and @mentions on visualisations |
| OCCRP Aleph | "Investigations" workspaces; network diagrams with an add-entities toolbar on the left; timelines; cross-referencing lists against all datasets; transliterated search ([Aleph docs](https://docs.aleph.occrp.org/users/investigations/network-diagrams)) |

&#91;embedded content: Converged investigation workspace layout · 6 zones\]

This is the layout Gotham's Map and Graph, Maltego, i2 and Linkurious all share. The highlighted node is the current selection; the two handles on the timeline filter what the canvas shows. The purpose banner is the one zone DRISHTI adds.

### 16.3 What DRISHTI adopts

1. **Same screen grammar:** app bar → tool strip → left panel → central canvas → right selection/helper panel → bottom time panel.
2. **Built on Blueprint** (with our own name, logo and colours, as its licence requires) plus Cytoscape.js for graphs and MapLibre for maps.
3. **Dark theme by default** for control rooms; light theme for office use.
4. **Helpers everywhere:** Selection, Histogram, Timeline, Timewheel (hour-of-day × day-of-week) and Heatmap open beside Graph, Map and Explorer.
5. **One selection colour** across all apps, and drag-and-drop of objects between apps.
6. **Provenance chips** on every property and edge, plus the evidence-strength edge colours from Section 2.3a.
7. **DRISHTI-specific additions Gotham does not emphasise:** a permanent **purpose banner** under the app bar showing the active case and legal purpose (red when none is set), a **classification banner**, an English-only interface with regional-language sources auto-translated, and an "AI-suggested" marker on anything the assistant produced.

**To meet the 2024–2026 standard, DRISHTI also needs these modern features (all buildable free):**

| Modern Gotham / Maven feature | DRISHTI equivalent | Free tool |
| --- | --- | --- |
| Real-time multi-user canvas and editor | Live cursors and shared edits in Graph and Dossier | Yjs (CRDT) + WebSockets |
| History on every artefact | "Who changed what" timeline on graphs, objects, dossiers | Postgres event log |
| 3D globe (3D Gaia) | 2D/3D toggle with terrain, tracks and time slider | CesiumJS (Apache 2.0) or deck.gl GlobeView + MapLibre |
| Inbox for all alerts | One alert inbox with channels: search feeds, object watches, geofences, shares | Built on Postgres + WebSocket push |
| Built-in classification-aware chat | Case chat where dropped objects are redacted for users without access | Matrix/Element-style or custom on WebSockets |
| AIP Assist side panel | AI assistant docked on the right, answers with clickable object citations, proposes actions for approval | Local open-weight LLM via Ollama |
| Kanban operational board | Case and task board (e.g., Reported → Verified → Assigned → Resolved) for disaster tasks or leads | React DnD-kit |
| Live-data briefing slides | Dossier "present" mode with live embedded maps and graphs | reveal.js-style renderer |
| Command palette / quick search | Ctrl+K palette to search any object or run any action | cmdk (MIT) |

UX principles taken from these products: one screen per job, very few clicks to act, every AI output needs human approval, everything is draggable between apps, and the time slider controls every view at once.

### 16.4 How agencies actually work in Gotham (workflow evidence)

The real day-to-day job is **investigation and targeting**, not dashboards: an officer starts from one identifier, builds the subject's network, places it in space and time, moves a lead through approvals, and writes it up.

| Source | What it shows about real use |
| --- | --- |
| LAPD Gotham user manual (via records request) ([Vice](https://www.vice.com/en/article/revealed-this-is-palantirs-top-secret-user-manual-for-cops/)) | Start from a **name, phone number, licence plate or case dates**; results pull from every connected record system; then move to chart, map or Object Explorer; click a person for the full record; plot addresses, crime locations and plate-reader travel history; finish with a "Virtual Dossier". The plate-reader map search **requires a search purpose (case number)**, centre, radius, plate and date range |
| LAPD training courses ([BuzzFeed News](https://www.buzzfeednews.com/article/carolinehaskins1/training-documents-palantir-lapd)) | Two 8-hour courses for crime-intelligence officers; data: incidents, arrests, warrants, bookings, recovered vehicles, field interviews, plate reads, phone records with tower locations; \~5,000 accounts and \~60,000 searches supporting 10,000+ cases in 2016 |
| Palantir Target Workbench brief ([Palantir](https://palantir.com/assets/xrfr7uokpv1b/1IqzwzpemtBSm98TNCczao/49bbc30cbec4d2d4d189ab27bd07376c/Palantir_Target_Workbench___1_.pdf)) | A **Kanban board mapped to lifecycle stages** (renameable by the agency), columns visible by security marking, real-time multi-user work, **approvals required before action** on sensitive targets, and a target record holding stage, profile, location, attached intelligence, an activity log, security marking, and "intelligence decay" time |
| Hesse and Bavaria police ([heise](https://heise.de/-10453589)) | HessenDATA: about 2,000 officials, up to 15,000 uses a year; Bavaria restricts VeRA to specially trained investigators; data protection officers warn routine use exposes innocent people |

**Indian translation of these workflows (what DRISHTI's screens must support):**

1. **Subject-centric search:** name (any script), mobile number, vehicle registration, FIR number, PAN/GSTIN or bank account, always inside an open case with a stated purpose.
2. **Subject profile:** linked FIRs and chargesheets (CCTNS), court status and bail (ICJS/e-Courts), vehicles (VAHAN), companies (MCA), travel and financial responses obtained through NATGRID or legal orders, each with provenance.
3. **Network building:** Search Around across phones, vehicles, accounts, companies and co-accused; centrality to find brokers; evidence-strength colouring.
4. **Spatio-temporal analysis:** toll (FASTag/NETC) or checkpoint hits for case vehicles, tower locations from call records obtained under a legal order, seizure locations, co-location of two numbers.
5. **Lead and action workbench:** lead → investigation → sent for approval (SP / legal) → action authorised → outcome, for actions like search warrants, account freezes, look-out circulars and arrests.
6. **Dossier for prosecution:** exportable with sources and chain of custody under the BSA.

**What DRISHTI deliberately does not copy:** searches by race, caste, religion, tattoos-plus-demographics, or gang-membership labels without a case; "likely offender" lists; and plate or phone searches without a recorded purpose.

### 16.5 Design decisions after review: access, agencies, auto-graph

**A. Access: instant by default, approval only where the law demands it.** If a source is connected and the officer's clearance and case cover it, results appear immediately, with no request and no waiting. The system logs every view silently. Approval remains only where Indian law itself requires a prior authorisation, so it can't be designed away:

| Situation | DRISHTI behaviour | Why |
| --- | --- | --- |
| Records in connected databases (CCTNS, ICJS, VAHAN, MCA, GST, NATGRID-federated categories) within the officer's clearance | **Instant**, auto-queried when an object opens | Clearance + case = authority; audit is silent |
| Data above the officer's classification or outside their agency | Hidden or shown as "exists, request share" | Need-to-know; each agency owns its data |
| New call records, interception, bank statements not yet held | Needs the legal order (Telecom Act 2023 / BNSS) | The law requires an order before the data is created or released |
| Real-world actions: search, arrest, freeze, look-out circular | Approval in the workbench | Required by NDPS, PMLA, UAPA, BNSS procedures |
| People with no link to the case (family, neighbours) | Shown as counts, not identities, until linked by evidence | The German court ruling: innocent contacts must not be swept in |

**B. Built for the whole national security system, not one police unit.** DRISHTI is one product with a shared ontology, deployed as separate sovereign instances per agency, joined by a federation layer:

| Agency | Mission app emphasis | Deployment | Classification ceiling |
| --- | --- | --- | --- |
| NIA | Terror and narco-terror investigations, UAPA cases, chargesheet dossiers | On-prem, NIA data centre | Secret |
| CBI | Corruption, bank fraud, economic offences; money trail and document analysis | On-prem | Secret |
| ED / FIU-IND | PMLA money trails, shell-company graphs, property attachment | On-prem | Confidential–Secret |
| NCB / DRI | Narcotics and smuggling networks, seizure analytics, ports | On-prem | Confidential |
| IB / R&AW | Threat assessment, all-source intelligence fusion | Air-gapped enclave | Top Secret |
| Army / Navy / Air Force | Sector situational picture, ISR fusion, logistics, edge kits | Air-gapped, tactical edge | Top Secret |
| Coast Guard / Navy | Maritime domain awareness: AIS gaps, vessel tracks | Air-gapped + edge | Secret |
| CERT-In / NCIIPC | Cyber threat graphs, incident response | On-prem | Confidential |
| State police / ATS | FIR-linked investigations, inter-state alerts | State data centre | Restricted–Confidential |

Cross-agency sharing happens object by object through the federation layer: markings travel with the data, sharing follows MoUs, and both sides log it. NATGRID remains the legal channel for categories it covers.

**C. The graph builds itself.** Opening or selecting any object (a person, phone, vehicle, company, account) automatically builds its connected graph: all first-degree links appear instantly, grouped by type, with large groups collapsed into one node with a count. A second ring adds linked suspects, objects tied to other cases, and money or communication paths. Links are ranked by evidence strength, and the assistant summarises what is new. The analyst never builds the graph step by step. Manual Search Around remains only as an advanced tool for custom queries.

We copy layout patterns, which are industry conventions, not Palantir's branding or exact visual design.

## 17. Sources and further reading

**Palantir and Gotham**

- [Inside Palantir AIP: technical teardown (Towards AI)](https://pub.towardsai.net/inside-palantir-aip-how-the-worlds-most-controversial-ai-platform-actually-works-9ec5b7a6c05a)
- [Missing link: Power center Palantir (heise)](https://www.heise.de/en/background/Missing-link-Power-center-Palantir-a-software-controls-organizations-10463503.html?view=print)
- [Why a 2000-year-old philosophy… (ex-Palantir engineer on Ontology, Vocal)](https://vocal.media/01/why-a-2000yearold-philosophy-became-every-ctos-emergency-meeting)
- [Palantir intrinsic value explainer](https://intrinsicvalue.beehiiv.com/p/pltr)
- [Palantir Ontology docs](https://www.palantir.com/docs/foundry/ontology/overview/)
- [ICE ImmigrationOS (American Immigration Council)](https://www.americanimmigrationcouncil.org/blog/ice-immigrationos-palantir-ai-track-immigrants/)
- [Ontario Provincial Police and Gotham (The Logic)](https://thelogic.co/news/exclusive/ontario-provincial-police-use-controversial-data-mining-platform-palantir-for-crime-analysis/)
- [German Constitutional Court ruling (IndiaAI)](https://indiaai.gov.in/news/the-german-federal-constitutional-court-nullify-palantir-s-ai-algorithm-for-policing)
- [GFF on automated data analysis](https://freiheitsrechte.org/en/themen/freiheit-im-digitalen-zeitalter/automatisierte-datenanalyse)
- [Palantir roadblock in Germany (Benzinga)](https://hk.finance.yahoo.com/news/palantir-hits-roadblock-germany-february-134146186.html)
- [Baden-Württemberg and Palantir (European Cloud)](https://european.cloud/2026/08/baden-wurttemberg-palantir/)
- [Neo4j acquires GraphAware as Gotham alternative (heise)](https://heise.de/-11317197)
- [DataWalk: The Palantir Alternative (pricing brochure)](https://www.dlt.com/sites/default/files/resource-attachments/2022-05/DataWalk-The-Palantir-Alternative.pdf)

* [NHS Federated Data Platform contract under review (Digital Health, June 2026)](https://www.digitalhealth.net/2026/06/fdp-here-to-stay-says-patel-as-palantir-contract-faces-review/)
* [X-Road data exchange layer (Interoperable Europe)](https://interoperable-europe.ec.europa.eu/collection/ict-security/solution/x-road-data-exchange-layer)

- [Palantir Graph training guide (DocumentCloud)](https://s3.documentcloud.org/documents/21583103/palantir_1013_-_graph.pdf) · [Palantir Gotham law-enforcement product description (DocumentCloud)](https://s3.documentcloud.org/documents/810526/1035-palantir-product-description-gotham.pdf)
- [Palantir Map interface overview](https://palantir.com/docs/foundry/map/map-overview/) · [Vertex: explore object relationships](https://palantir.com/docs/foundry/vertex/explore-object-relationships/) · [Object Explorer charts](https://www.palantir.com/docs/foundry/object-explorer/explore-charts/)
- [Blueprint UI toolkit (GitHub)](https://github.com/palantir/blueprint)
- [Maltego: navigate the interface](https://docs.maltego.com/en/support/solutions/articles/15000059532-navigate-the-interface) · [Linkurious timeline](https://doc.linkurious.com/user-manual/3.1/timeline) · [Aleph network diagrams](https://docs.aleph.occrp.org/users/investigations/network-diagrams) · [i2 Analyst's Notebook brochure](https://i2group.com/hubfs/Products/i2-Analysts-Notebook.pdf)

* [Palantir Gotham G-Cloud 14 service definition, 2024](https://assets.applytosupply.digitalmarketplace.service.gov.uk/g-cloud-14/documents/92736/801146272055049-service-definition-document-2024-11-26-1253.pdf) · [Palantir blog: 3D Gaia with Three.js (2026)](https://blog.palantir.com/frontend-engineering-at-palantir-plotlines-in-three-js-c0c47f310715) · [Maven Smart System one-pager](https://assets.ctfassets.net/xrfr7uokpv1b/25muZs93DY5XOUBtuh68yn/b40d9784f69917219f972890ceede986/Maven_One_Pager.pdf) · [Inside Palantir's Maven Smart System (Spatial Intelligence, 2026)](https://www.spatialintelligence.ai/p/inside-palantirs-maven-smart-system)

**Indian systems**

- [NATGRID overview (Bharat Notes)](https://bharatnotes.com/resources/key-terms/natgrid-national-intelligence-grid--21-intelligence-agencies-nia-natgrid/)
- [NATGRID–NPR linkage (Padhai)](https://padhai.ai/current-affairs/national-intelligence-grid-natgrid-npr-integration)
- [NATGRID concerns (Shankar IAS)](https://www.shankariasparliament.com/current-affairs/natgrid)
- [NATGRID explained (IASGyan)](https://www.iasgyan.in/daily-current-affairs/national-intelligence-grid-natgrid-explained)
- [MHA: CCTNS and ICJS](https://www.mha.gov.in/en/divisionofmha/women-safety-division/cctns)
- [CCTNS / ICJS 2.0 integration (Madhyamam)](https://english.madhyamam.com/india/integration-of-cbi-nia-ncb-data-with-cctns-a-must-shah-954571)
- [CCTNS implementation status (ecoi.net / IRB Canada)](https://www.ecoi.net/en/document/2054443.html)
- [SACHET and CAP in India (thejeshgn)](https://thejeshgn.com/2025/05/28/common-alerting-protocol-cap-in-the-indian-context/)

**Law**

- [India's surveillance landscape after the DPDPA (IAPP)](https://iapp.org/news/a/india-s-surveillance-landscape-after-the-dpdpa)
- [Right to privacy in the age of surveillance (Lawful Legal)](https://lawfullegal.in/the-right-to-privacy-in-the-age-of-surveillance/)
- [DPDP framework and state exemptions (MediaNama)](https://www.medianama.com/2025/11/223-dpdp-framework-personal-data-companies-door-open-for-state/)
- [DPDP Rules notified, phased rollout (Storyboard18)](https://www.storyboard18.com/digital/breaking-govt-notifies-final-dpdp-rules-sets-staggered-rollout-with-key-obligations-for-data-fiduciaries-84201.htm)
- [IFF statement on DPDP Rules (Newsclick)](https://www.newsclick.in/dpdp-rules-narrow-down-state-exemptions-surveillance-powers-says-iff)

**Open-source building blocks**

- [Apache AGE](https://age.apache.org/)
- [Splink](https://github.com/moj-analytical-services/splink)
- [AI4Bharat](https://ai4bharat.iitm.ac.in/?p=8) · [IndicTrans2](https://github.com/AI4Bharat/IndicTrans2) · [AIKosh](https://aikosh.indiaai.gov.in/home/models/details/indic_trans2.html)
- [FollowTheMoney schema](https://followthemoney.tech/)
- [datagovindia (OGD API wrapper)](https://pypi.org/project/datagovindia/0.4)
- [Oracle Always Free resources](https://oracle.hydrogen.sagittarius.connect.product.adaptavist.com/iaas/Content/FreeTier/resourceref.htm) · [2026 free-tier change report](https://terminalbytes.com/oracle-cloud-free-tier-changes-2026)

**Further reading to deepen the research**

- Full text of *K.S. Puttaswamy v. Union of India* (2017) 10 SCC 1 and the 2018 Aadhaar judgment.
- German Federal Constitutional Court judgment of 16 Feb 2023 on automated data analysis (Hesse and Hamburg police laws).
- Palantir Foundry and Gotham public documentation (palantir.com/docs).
- OCCRP Aleph source code (an open-source investigative data platform worth studying).
- NCRB annual *Crime in India* reports and CCTNS technical documents.

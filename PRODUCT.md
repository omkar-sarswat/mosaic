# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

**Primary: the investigating officer (IO).** A sub-inspector or inspector at a police station, or in the field, works one case at a time on a laptop or tablet. The IO looks people, phones, vehicles and accounts up quickly, follows a lead, attaches evidence, and asks the supervising SP for approvals: wider network expansion, opening a case from a lead, publishing an intake. The redesign is built around this person's working day first.

Other confirmed roles, all served by the same application:
- **Supervisor (SP / DCP):** approves expansions, lead-to-case requests and intake publications under two-person rules.
- **Analyst (SCRB, cyber cell, agency analysis wings):** works across leads, networks, money trails and the data studio.
- **Data steward:** reviews record-matching proposals and intake quality.
- **Oversight auditor:** reviews who saw what, through the hash-chained audit log; has no case data access.
- **Agencies modelled:** state police, NIA, CBI, ED, NCB, IB, R&AW and SDMA control rooms (disaster mode). Each sees only its own mission tracks and cases.

## Product Purpose

DRISHTI is an open-source investigation workspace for Indian agencies. It fuses records from many sources (registries, FIRs, bank statements, call records, toll reads, travel, procurement), resolves which records are the same person across Indian scripts and spellings, and surfaces patterns as leads for a person to evaluate. It does all this inside legal safeguards: every look-up is tied to a case and a recorded purpose.

Success for the IO: get from a name, number or plate to the relevant people, links, money and evidence of the case in the fewest steps, with each finding's source and reasoning visible. Get the supervisor's approval without leaving the flow.

## Positioning

- **Safeguards are the product.** Purpose-bound case scoping, two-person rules, clearance masking, canary records and a tamper-evident audit log are built in, not configured on.
- **Leads, not verdicts.** The pattern engine and the record matcher propose; a person decides. Every lead and match shows its evidence, measurements and thresholds. There is no person scoring, and protected attributes are never inputs.
- **Built for India.** Names compare across Devanagari, Gurmukhi, Gujarati, Bengali, Tamil, Telugu, Urdu and Latin. Detectors encode Indian law and typologies (BNS s.111, PMLA, NDPS precursors, the s.269ST and PAN cash limits).
- **Open and auditable,** with published evaluation on public benchmarks (docs/research/10), including where it falls short.

## Operating Context

- **Where and on what:** police stations and field work on a laptop or tablet; analysts at desks; SDMA control rooms.
- **One active case at a time.** The case carries its purpose, legal basis and member officers, and every request is made in that case's context.
- **The IO's main flow:**
  1. search or open an entity dossier;
  2. explore the network, money trail and timeline;
  3. attach evidence to the locker, with chain of custody;
  4. request expansions or actions;
  5. export reports (case report PDF, evidence pack, draft BSA s.63 certificate).
- **What the platform does alongside:**
  - the pattern engine raises leads per mission track, which are routed to the right agency;
  - the data studio cleans and maps a new extract, and publishes it after a second officer approves.
- **Sign-in:** through Keycloak (OIDC with an authenticator app) in deployment; a user picker in synthetic dev mode.

## Capabilities and Constraints

- **Applications:**
  - Home;
  - Search and dossier;
  - Network (graph);
  - Money trail;
  - Timeline;
  - Geospatial (map);
  - Leads (pattern engine);
  - Cases (members, approvals, evidence locker, exports);
  - Alerts;
  - Review (record matching);
  - Data studio (intake);
  - Connect (find links between two entities);
  - Face search (case-bound, with human confirmation);
  - Oversight (audit).
- **Stack:** React + TypeScript with Blueprint, MapLibre and Cytoscape; served by FastAPI; SQLite or PostgreSQL 18.
- **Data:** synthetic only today. A real-data district pilot needs a legal agreement and audited labels.
- **Interface language:** English only for now. Records keep showing names in their original Indian scripts.
- **Machine-proposed links** (suggested) must stay visually distinct from corroborated and single-source facts. Masked fields must read as masked, not as missing.
- **Open decisions** (not confirmed as requirements):
  - GIGW 3.0 / WCAG 2.1 AA conformance;
  - support for low-end district machines and 1366x768 screens;
  - a light theme for daylight rooms;
  - Hindi and regional interface languages.

## Brand Commitments

- **Name:** DRISHTI, Sanskrit for sight.
- **Mark:** the existing eye mark is kept. The redesign may refine how it is drawn.

## Evidence on Hand

- **Measured results:** in `docs/research/` (05 entity resolution, 08 pattern engine, 09 data studio, 10 external benchmarks, 11 security review), with numbers reproducible from `bench/`.
- **Demo data:** synthetic worlds with planted networks (`drishti demo`).
- **What does not exist yet:** real deployments, users, testimonials or field results. These must not be fabricated or implied.

## Product Principles

1. **The case is the unit of work.** Everything the officer sees and does belongs to an open case with a stated purpose, and the interface makes that context plain.
2. **Show the evidence with the claim.** Every lead, match and link carries its sources and reasoning one step away. Uncertainty is shown, not smoothed over.
3. **A person decides.** The system proposes; approvals, confirmations and rejections are explicit human acts, and the second officer in a two-person rule is visible.
4. **Fewest steps for the officer in the field.** The IO's common path (look up, follow, attach, ask approval) is short and works on a laptop or tablet.
5. **Accountability is part of the flow,** not a hidden log: who saw what, under which purpose, is recorded and inspectable.

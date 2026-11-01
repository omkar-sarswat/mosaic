# 02 · India's data estate in 2026: what changed and where DRISHTI fits

Design doc Section 3 described NATGRID, CCTNS, ICJS and related systems. This update covers developments through October 2026. Most sources here are **secondary** (news and explainers); official MHA, NCRB or I4C documents should be checked before a pitch relies on any figure.

## NATGRID

| Development | Detail | Source |
|---|---|---|
| State police access | SP rank and above can query NATGRID; about 45,000 requests a month; MHA urging wider state use | [IASGyan](https://www.iasgyan.in/daily-current-affairs/natgrid-to-have-access-to-database-that-links-around-14000-police-stations), [Insights](https://www.insightsonindia.com/2026/01/08/natgrid-and-the-architecture-of-surveillance/), Jan 2026 |
| Claimed safeguards | End-to-end encryption, two-factor authentication, role-based access, every search logged to one officer | [Organiser](https://organiser.org/2026/01/14/334982/bharat/natgrid-redefines-data-architecture-for-indias-counter-terror-strategy-and-internal-security/), Jan 2026 |
| Criticism | No statutory basis, no independent oversight; NPR linkage enables population-scale identity checks ("the search engine of digital authoritarianism", *The Hindu* op-ed) | [Civilsdaily summary](https://www.civilsdaily.com/news/8th-jaunary-2026-the-hindu-oped-natgrid-the-search-engine-of-digital-authoritarianism/) |
| GST data | The 57th GST Council meeting (8 Oct 2026, Bharat Mandapam) was to consider API access for NATGRID user agencies and state/UT police to five categories of GST data, including registration details, e-way bills and e-commerce supplies. GSTN warned that unrestricted API access would expose "the entire universe" of registration and e-way-bill data. MoSPI separately sought full datasets. **We found no report of the decision**; the post-meeting summaries we saw cover refunds and decriminalisation only. | [MediaNama](https://www.medianama.com/2026/10/223-gst-council-natgrid-taxpayer-data/), [BusinessToday](https://www.businesstoday.in/latest/economy/story/who-can-access-gst-data-council-to-consider-requests-from-natgrid-mospi-559812-2026-10-06), [TaxGuru](https://taxguru.in/goods-and-service-tax/57th-gst-council-meeting-rescheduled-8-october-2026-bharat-mandapam.html), [TaxO](https://taxo.online/latest-news/09-10-2026-57th-gst-council-meeting-key-highlights/) |

**What this means for DRISHTI:** NATGRID is becoming the default lookup channel. DRISHTI should not copy it. It should **attach NATGRID responses to a case as a source** (provenance: `NATGRID`, the request ID, the legal order) and analyse them under the same purpose binding. The GSTN's own concern, unrestricted API access exposing the whole dataset, is exactly the "dragnet" pattern DRISHTI's case scoping exists to prevent. That is a useful argument in a pitch.

## ICJS 2.0 and CCTNS 2.0

- **ICJS 2.0**: MHA's target is to fully operationalise it by 2026, linking police, courts, prosecution, prisons, forensics and fingerprints. NCRB ranks states monthly; Uttarakhand was first at 93.46 in early 2026 ([Business Standard](https://www.business-standard.com/india-news/uttarakhand-police-tops-icjs-2-0-rankings-sdrf-praised-for-mahakumbh-role-126010800123_1.html)).
- **CCTNS 2.0** was still *under development* per the MHA Annual Report 2024-25, as cited by [Innefu Labs](https://innefu.com/cctns-explained-cctns-2-0/), a vendor source. A December 2024 [PIB release](https://www.pib.gov.in/PressReleasePage.aspx?PRID=2087523) records the Home Minister reviewing CCTNS 2.0 integration with ICJS 2.0.
- *Inference:* while CCTNS 2.0 is in flux, DRISHTI's CCTNS connector should target the **ICJS 2.0 data exchange** and state SCRB exports rather than CCTNS 1.0 internals, and keep its ontology mapping in configuration so it survives the migration.

## I4C: Suspect Registry, Samanvaya, mule accounts

| Item | Detail | Source |
|---|---|---|
| Suspect Registry | Launched 10 Sept 2024 by I4C; identifiers (phones, accounts, UPI IDs) of suspected cyber-criminals, shared between law enforcement and banks | [Policy Edge](https://www.policyedge.in/p/ministry-of-home-affairs-strengthening-the-indian-cyber-crime-coordination-centre-i4c) |
| Scale | Figures conflict: 1.843 million suspect identifiers and 2.467 million "Layer 1" mule accounts (Dec 2025) vs 27.37 lakh mule accounts identified (other source) | [MediaNama](https://www.medianama.com/2025/12/223-samanvaya-portal-tracks-1-8m-suspects-raises-privacy-concerns/) |
| Samanvaya | National MIS and data repository linking crimes and criminals across states; its *Pratibimb* module maps offenders' locations, criticised for profiling risk | MediaNama (above) |
| I4C–RBIH MoU (12–13 May 2026) | Shares mule-account intelligence and Suspect Registry identifiers with the RBI Innovation Hub's **MuleHunter.AI** | [News on AIR](https://newsonair.gov.in/cyber-crime-coordination-sign-mou-with-rbi-to-curtail-mule-accounts/), [ETV Bharat](https://www.etvbharat.com/amp/en/bharat/ai-will-detect-mule-accounts-as-i4c-rbih-sign-cyber-fraud-enn26051204987) |
| Field use | Pune Police traced five cases and about ₹3.6 crore through Samanvaya (July 2026) | [Bridge Chronicle](https://www.thebridgechronicle.com/amp/story/pune/pune-cyber-fraud-samnvay-portal-uncovers-five-cases-rs36-crore-money-trail-agn97) |

**What this means for DRISHTI:** the cyber-fraud workflow (design doc 4.3) is already partly served nationally. DRISHTI's added value is at the **state cyber cell**: fusing I4C complaints with local FIRs, CCTNS accused records and bank replies inside one case, with entity resolution across the spellings in those systems. Our synthetic ring R1 (12 mules, 5 SIMs, 2 handsets, 37 complaints, 4 districts) reproduces this pattern. Pratibimb-style offender *location mapping* is close to the "person-level profiling" DRISHTI refuses to build (safeguard 3); keep to place- and pattern-level analytics.

## Where DRISHTI sits, as of October 2026

```
national rails (do not duplicate)          DRISHTI (state / district / department instance)
──────────────────────────────────         ─────────────────────────────────────────────────
NATGRID  ─── per-case responses ────────►  Connect  ─► Resolve ─► Ontology ─► Explore / Map / Graph
ICJS 2.0 ─── SCRB exports / status ─────►     ▲                                  │
I4C / Samanvaya ── complaint exports ───►     │                                  ▼
SACHET / IMD / CWC ── open feeds ───────►     │                    Guard: purpose · case · audit
LGD ── codes (via Wikidata / downloads) ─►    │
departmental MIS (PDS, pensions, NHM) ──►  (on the department's own server, under its MoU)
```

The first deployable value is still civil (the disaster COP, the welfare-duplicate check). Police use follows once a district pilot has shown the audit and purpose controls work.

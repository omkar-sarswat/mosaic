# 08 · Mission tracks and the pattern engine

*A design note in the form of a systems paper. Build and measurements: 15 October 2026. All data synthetic.*

## Abstract

DRISHTI now serves the mission of every agency in its pilot (NIA, NCB, CBI, IB, R&AW, ED, state police and state cyber cells) over one ontology, rather than one financial dashboard. Three things were added.

1. **Mission tracks and mandates in the ontology.** There are eight tracks. Agencies are bound to the purposes they may open a case for. A case's purpose decides which of 15 record classes its members may read.
2. **A pattern engine of 19 detectors.** Each implements a published method and is declared with what it reads, the evasion it is built to defeat, the look-alikes it must ignore, and its blind spots.
3. **A lead workflow.** Leads stay pseudonymous until two officers of the same agency open a case on them.

On four independently generated synthetic worlds of 700 to 1,800 people, the detectors find **120 of 120 planted networks**. Every lead touches a planted network: **no look-alike fires and no false lead falls on the background population.** Until 16 October 2026 the figure was 117 of 120: one planted operation was scored against the wrong detector (Section 7). Running the engine on a 10,000-person world then exposed two real weaknesses that the small worlds had hidden. Both are fixed (Section 8). An adversary simulator rewrote the planted networks twelve ways an informed adversary would. Nine tactics failed against the detectors (the loophole is closed). Three succeeded exactly where documented limits say they would. These are synthetic results. They show the detectors do what they are designed to do. They are not real-world accuracy (Section 9).

## 1. Problem and operating principle

The requirement was to catch criminal and hostile networks early, for every agency, without becoming a population-surveillance or prediction system. The operating principle, unchanged from the design document:

> Compute over everything lawfully held; reveal only what the requester's authorised case and clearance unlock; log every read and every action.

Three consequences shape every design choice.

- **Patterns, not predictions.** A detector fires on a pattern that has already happened in the records (a ring of deposits, a SIM rotation, a cartel's bids) and shows that evidence. Nothing estimates a person's likelihood of future crime. No score is stored on a person.
- **Leads, not findings.** A hit is a reason for an officer to look. It opens nothing by itself: a case needs a purpose, a legal basis and a second officer.
- **Inquiry-bound where the conduct is ordinary.** Changing your number, calling a relative abroad, or meeting friends are ordinary acts. Detectors that look at them (successor SIM, foreign handler, recce) are seeded. They start only from numbers or people already named in an FIR, an open case, or a crew found from records. They never scan the population.

## 2. Threat model

Two adversaries are considered.

**The network under investigation**, assumed to know the rules. The evasions this design treats as given:

| Evasion | Example | Countermeasure in DRISHTI |
|---|---|---|
| Threshold gaming | Deposits of Rs 46,500-49,900 to avoid the Rs 50,000 PAN rule | Banded detection at 88-100% of every statutory threshold, aggregated across people |
| Splitting across people | Nine smurfs, two or three deposits each | Aggregation at the account where the money converges, not where it entered |
| Layering | One or more pass-through accounts | Time-respecting multi-hop traces at two scales |
| Waiting | Cash held for days before moving | Second scale: 7-day hops, requiring a larger ring |
| Label disguise | Collector registered as a "merchant" or "travel agent" | Hubs recognised by behaviour (50+ payers, money stays), never by self-declared type |
| Narration laundering | "PAYMENT" instead of "PURCHASE OF FABRIC" | No detector reads a narration; verified by a metamorphic test |
| Identity fragmentation | "Sawant Pravin Nilesh" in CCTNS vs "Pravin Nilesh Sawant" on Aadhaar | Entity resolution before any graph is built (and a resolver bug fixed, Section 8) |
| SIM rotation | New SIM per few days, SIMs moved between gateways | SIM-handset graph; gateway signature by vote (4 of 5 signs), so faking one sign does not hide it |
| Burner switch | Old number silent the day it appears in an FIR | Contact-set fingerprint with IDF weighting, seeded from the FIR's numbers |
| Fronts and nominees | Low-income directors on several boards | Nominee indicator; ownership ties through directors, signatories, addresses and contact numbers |
| Spreading shells | Each shell at a different address | Officers and signatories still connect them |
| Convoy spacing | Pilot car 25-30 minutes ahead | Second scale: 60-minute window, requiring 4+ plazas on 3+ journeys with the same leader |
| Cloned plates | A real car's number on a second car | Physical speed bound on reads of the same plate |
| Dealer splitting | Precursor bought in small lots from every dealer | Per-buyer monthly aggregation; dealer-count and lot-size shift |
| Licence borrowing | Quoting another firm's licence on invoices | Invoice licence checked against the buyer's own licence record |
| Bid rotation | Cartel members take turns to win | Rotation is itself a marker; bid-spread screens; shared officers and IP addresses |

**The system itself**, assumed capable of misuse: drift into population surveillance, profiling by community, fishing expeditions, leaks between agencies. Countermeasures:

- purpose classes;
- agency mandates;
- pseudonymous leads with per-lead labels (two leads cannot be joined by their labels);
- the two-person rule;
- protected-attribute isolation, enforced in code and tested;
- seeded scope;
- deconfliction counts instead of cross-agency content;
- the hash-chained audit.

## 3. Architecture

```
 sources ──> ontology store (objects, links, provenance)   event tables: txns, cdrs, travel, tollhits/ANPR,
              │  record class for every type                  procurements (NDPS/explosives registers), bids
              ▼
   entity resolution (Fellegi-Sunter) ── Resolver: one identity per person cluster
              ▼
   Context: shared read-only feature plane, built once per run
     identities · accounts by identity · families/households · accused/victims · SIM-handset graph ·
     phone owners · CDR stream · reads · behavioural hubs   (Person attributes only via an allow-list)
              ▼
   detector registry  ── declared: question, inputs, algorithm, evasion, look-alikes, blind spots, refs
     population detectors ─┐
     seeded detectors ─────┼─> hits (stable ids) ──> pattern_hits (leads) ──> pattern_runs (fingerprint, versions)
     compound detectors ───┘        depend on earlier hits (crews feed handler and recce detectors)
              ▼
   lead workflow: track-bound visibility → pseudonymous rendering → request (IO) → approve (other supervisor,
                  same agency) → case scope → ordinary Guard rules (clearance, purpose classes, jurisdiction)
              ▼
   evaluation harness (planted truth + look-alikes, 4 classes of hit) · adversary simulator (12 tactics)
```

Design rules that recur across detectors:

1. **Behaviour over labels.** Self-declared attributes (business type, payment narration, registered name) are cheap for an adversary to change. Detectors measure what money, calls and vehicles did.
2. **Resolve first, then aggregate.** Every detector works on resolved identities, so splitting across records or spellings does not split the evidence.
3. **Time-respecting paths.** A transfer counts as onward movement only if it left after the money arrived. Static cycles and static paths overstate links.
4. **Votes, not conjunctions.** A signature that needs every sign to hold can be beaten by faking one. Where signs are independent, the rule needs most of them.
5. **Multi-scale with stricter evidence at wider scales.** Wider windows and more hops are allowed only for bigger, more repeated structures, so stretching time or adding layers does not buy invisibility.
6. **Look-alikes are fixtures, not afterthoughts.** Every detector has benign cases planted to tempt it, and the tests require silence on them.

## 4. Mission tracks, mandates and purpose classes

Tracks and the agencies whose officers see their leads (configurable templates, not statements of legal powers):

| Track | Lead agency | Detectors |
|---|---|---|
| terror | NIA | hawala collection, handset crew, successor SIM, foreign handler, recce repetition, weapon linkage, precursor diversion (explosives), convoy |
| narcotics | NCB | precursor diversion, convoy, handset crew, successor SIM, foreign handler |
| corruption | CBI | tender collusion, disproportionate assets, shell network |
| internal_security | IB | SIM box, handset crew, foreign handler, recce repetition |
| external | R&AW | foreign handler, hawala collection |
| money | ED | smurfing ring, victim convergence, dormant wave, hawala, shell network, dense money block |
| organised_crime | State police | continuing unlawful activity (BNS s.111), weapon linkage, convoy, cloned plate, stolen-vehicle trail, handset crew, successor SIM, smurfing |
| cyber_fraud | State cyber | victim convergence, dormant wave, smurfing, SIM box, dense money block |

The 15 record classes are: identity, criminal background, travel/immigration, communications, movement, property/assets, corporate, financial, procurement/licensing, schemes/benefits, digital artifacts, documents, biometrics, geography and casework. Each purpose lists the classes it may read. Two examples:

- A cross-border case (R&AW) reads travel, communications, money and corporate records. It does not read FIRs, land or vehicle records unless one is admitted to the case scope by an audited action.
- A disaster-response case reads identity, schemes and geography only.

The dossier follows the same rule: a section outside the purpose is listed as withheld, never shown empty. The rule is enforced identically in Python and in Rego. The parity test runs the full matrix of users × cases × objects against OPA 1.4.2 (Section 7).

Social-media handles and posts can exist only as sealed exhibits. The ontology refuses a `social_handle` or `social_post` without an exhibit hash and a legal order. Nothing is collected in bulk.

## 5. Detectors

Each row names the method and the reference it implements. Full declarations, including inputs and blind spots, are in the code and in the UI's Detectors tab.

| Detector | Method | Reference |
|---|---|---|
| Smurfing ring | Banded sub-threshold deposits; time-respecting forward trace at two scales; convergence by distinct depositor identity | FATF structuring typologies; IT Rules r.114B, s.269ST, PML Rules |
| Victim convergence | Victim-set propagation along time-respecting transfers from each complaint's fraud window; convergence ≥ 3 victims | I4C CFCFRMS practice; Holme & Saramäki (2012) temporal networks |
| Dormant wave | Reactivation after 180+ idle days; union of reactivations within 21 days sharing a counterparty | RBI KYC direction (inoperative accounts) |
| Hawala collection | FIFO pass-through, payer independence, outflow concentration, round-figure share, throughput vs declared; retail and wholesale tiers; narration-blind | FATF (2013) hawala report |
| Shell network | Officer/address/signatory/contact graph; 7 indicators incl. 2SCENT-style temporal cycles | Kumar & Calders (2018); FATF/Egmont (2018) |
| Dense money block | Fraudar greedy peeling with log-degree column weights; pass-through requirement | Hooi et al., KDD 2016 |
| SIM box | Per-SIM signature by 4-of-5 vote; grouping by IMEI and tower; rotation schedule | GSMA FF.21; DoT advisories |
| Handset crew | SIM-IMEI bipartite components with overlapping use; family and resale excluded | CEIR / IMEI linking practice |
| Successor SIM | Seeded; silence detection; IDF-weighted Jaccard of contact sets | de Montjoye et al. (2013) on trace uniqueness |
| Foreign handler | Compound; unrelated on-record contacts; pre-incident contact; travel within 10 days of a call | Krebs (2002) covert networks |
| Recce repetition | Compound; anchor towers (8+ days) excluded; joint presence on 2+ days; circular s.d. of hour | Fisher (1993) circular statistics |
| Convoy | Plaza sweep; journeys; leader consistency; two scales; fleets excluded | Jeung et al., VLDB 2008 |
| Cloned plate | Implied speed ≥ 180 km/h over ≥ 30 km with 5-min skew allowance | ANPR consistency checking |
| Stolen-vehicle trail | Seeded by theft FIRs; post-theft reads; common last-seen point | ZIPNET/CCTNS practice |
| Precursor diversion | Robust z (median/MAD) + Page CUSUM on log ratio; dealer and lot-size shift; licence checks; ramp guard | NDPS Act s.9A and RCS Order 2013; Ammonium Nitrate Rules 2012; Page (1954) |
| Continuing unlawful activity | Co-offending graph; Louvain with Leiden-style connectivity refinement; statutory charge-sheet test | BNS 2023 s.111; MCOCA s.2(1)(d); Blondel (2008), Traag (2019) |
| Weapon linkage | Union of firearm records by serial or FSL ballistic signature; unsolved incidents inherit leads | Arms Act 1959; NIBIN-style practice |
| Tender collusion | Imhof screens (CV, relative distance, winner vs estimate); co-bidding groups; rotation; shared officers, addresses, contacts, IPs | Imhof, Karagök & Rutz (2018); OECD bid-rigging guidelines; Competition Act s.3(3)(d) |
| Disproportionate assets | Check-period cash-flow method; relatives' assets only with no independent means and a money trail; loans and salary as known income; 10% tolerance | PC Act s.13(1)(b); Krishnanand Agnihotri v. State of M.P. (1977) |

The legal tests in the syndicate and DA detectors are patterns to check, not determinations. Their summaries say so.

## 6. Lead workflow

- **Visibility.** A lead is shown to investigators, supervisors and analysts of agencies whose mandate covers one of its tracks. District-bound officers see only leads inside their districts. Oversight sees evaluation and aggregates, never lead content.
- **Pseudonymity.** Every party is rendered "Subject B (bank account)". Labels are assigned per lead, so the same person carries different labels in different leads, and an analyst cannot assemble a profile by joining leads. Evidence lists are withheld; counts are shown.
- **Case from lead.** An investigating officer requests a case with a purpose from their agency's mandate and a legal basis. A supervisor of the same agency who is not the requester approves; the supervisor opens the case and the requester joins it. Only then do the lead's subjects enter case scope. From that point the ordinary Guard rules decide what each member sees (clearance, purpose classes, jurisdiction).
- **Dismissal.** A dismissal needs a reason. It persists across reruns because lead ids are stable, and it feeds evaluation as a reviewer disposition.
- **Deconfliction.** A dossier shows how many leads in other agencies' tracks involve the same entity, by track, without their content.

## 7. Evaluation

**Method.** The generator plants each network with benign look-alikes designed to tempt the same detector:

- a self-help group saving cash near the limit;
- dormant accounts woken by an insurance maturity or a property sale;
- a real charity;
- an old business group with common directors and one address;
- a call centre;
- a family sharing a handset, and a resold handset;
- a person who changes number;
- Gulf-worker families calling home;
- a gang's usual meeting place;
- a transport fleet, commuters, and a fast but possible trip;
- a vehicle read only before it was stolen;
- a steadily growing pharma buyer and monsoon-seasonal quarries;
- a competitive tender market;
- a senior officer with a home loan, and an inherited house.

Hits are classed as planted (this detector's network), cross (another track's planted network: a correct lead), look-alike, or background. Detectors never read the ground truth or generator roles; a test checks the source.

**Results across four worlds** (seeds 11, 23, 47, 91; 700, 1,200, 1,800 and 1,500 people), measured 15 Oct 2026:

| Detector | Planted found | Precision | Look-alikes fired | Background false leads | Eligible (sum of 4 worlds) |
|---|---|---|---|---|---|
| Smurfing ring | 4/4 | 1.00 | 0 | 0 | 899 accounts with cash deposits |
| Victim convergence | 8/8 | 1.00 | 0 | 0 | 8,944 accounts |
| Dormant wave | 4/4 | 1.00 | 0 | 0 | 8,944 accounts |
| Hawala collection | 8/8 | 1.00 | 0 | 0 | 3,655 accounts with credits |
| Shell network | 12/12 | 1.00 | 0 | 0 | 566 organisations |
| Dense money block | 4/4 | 1.00 | 0 | 0 | 8,944 accounts |
| SIM box | 4/4 | 1.00 | 0 | 0 | 6,495 SIMs |
| Handset crew | 12/12 | 1.00 | 0 | 0 | 56 handsets |
| Successor SIM | 4/4 | 1.00 | 0 | 0 | 6,495 SIMs |
| Foreign handler | 8/8 | 1.00 | 0 | 0 | 12 foreign numbers |
| Recce repetition | 4/4 | 1.00 | 0 | 0 | 16 towers |
| Convoy | 4/4 | 1.00 | 0 | 0 | 216 vehicles read |
| Cloned plate | 4/4 | 1.00 | 0 | 0 | 216 vehicles read |
| Stolen-vehicle trail | 16/16 | 1.00 | 0 | 0 | 20 stolen vehicles |
| Precursor diversion | 8/8 | 1.00 | 0 | 0 | 60 buyer-substance series |
| Continuing unlawful activity | 4/4 | 1.00 | 0 | 0 | 980 accused records |
| Weapon linkage | 4/4 | 1.00 | 0 | 0 | 12 firearm records |
| Tender collusion | 4/4 | 1.00 | 0 | 0 | 40 bidders |
| Disproportionate assets | 4/4 | 1.00 | 0 | 0 | 12 public servants |

**Target assignment, corrected 16 Oct 2026.** The earlier table scored MIRAGE's shell accounts against the dense-block detector and counted three permanent misses (5/8). MIRAGE's money graph is two collector accounts paying three shells, which pass money round a time-respecting cycle and on to an exit. Two payers is below Fraudar's declared minimum of three. The structure is a shell network, and the shell-network detector reports it in every world: all 7 companies and all 7 accounts, 7 of 7 indicators. The evaluation now scores each planted operation against the detector built for its structure. No detector was changed to obtain this. The pattern test now fails on any miss by any detector.

All 19 detectors together run in 0.4-1.0 s per world on a laptop, and in 8 s on a 10,000-person world (Section 7.1).

### 7.1 Scale: 2.4 million records

`drishti scale --people 30000` (seed 101, distinct from every evaluation world's seed) builds a world and runs every stage. It then reports volume, stage timings, detection quality and query latency. Measured 16 Oct 2026 on a laptop (16 GB RAM, one core per stage), with the database on E:.

**Volume.**
- **2,408,321 records:** objects, links and events, plus 1,717,388 index rows.
- **Objects:** 33,338 people, 48,226 bank accounts, 34,705 phones and 15,332 vehicles.
- **Events:** 1,245,154 transactions and 697,526 call records.

**Time.** Build and full analysis took 1,076 s.

| Stage | Seconds |
|---|---|
| World | 335 |
| Entity resolution (old two-pass scoring) | 505 |
| Ledger | 15 |
| Typologies | 139 |
| Inference | 10 |
| Behaviour | 9 |
| Patterns | 23 |
| Evaluation | 30 |

After this run, two changes lowered stage times further. The typology stage scanned every account for every person; it now uses an index, taking 142 s to 0.5 s with identical alerts. Resolution now scores in one pass, 1.6x faster with identical results.

**Detection.** 30 of 30 planted networks found, precision 1.00. No look-alike was raised and there were 0 false leads per 100,000 people. Detection does not degrade with population.

| Query | Median | p95 |
|---|---|---|
| Name search | 4.1 ms | 9.6 ms |
| Identifier lookup | 0.25 ms | 0.5 ms |
| Two-hop neighbourhood | 0.45 ms | 0.7 ms |
| Data-studio KYC preview (one run) | 2.9 s | |

**Entity resolution at this size** (hand-set parameters). Automatic links have precision 0.9957 and recall 0.917; with the review queue worked, recall is 0.986.

**Adversary simulation** (700-person world). Each tactic copies the database, rewrites the planted networks, re-runs everything, and compares recall with the original.

| Tactic | Attacks | Before → after | Outcome |
|---|---|---|---|
| Neutral payment references (31,267 rewritten) | narration-keyed rules | 9/10 → 9/10 | still caught |
| Shuffle name, gender, age, city, nationality, occupation, address of every person | (fairness) dependence on who someone is | 29/30 → 29/30, identical lead set | still caught |
| Re-register shells, hawala front and collector as merchants | label-based trace exemptions | 7/7 → 7/7 | still caught |
| One extra layer account on every smurf and mule transfer | one-hop rules | 3/3 → 3/3 | still caught |
| 15% staged incoming calls on the SIM box | all-signs gateway rules | 1/1 → 1/1 | still caught |
| Shells moved to separate addresses | address-keyed shell rules | 2/2 → 2/2 | still caught |
| Two extra layer accounts | fixed two-hop traces | 1/1 → 1/1 | still caught |
| Cash held four days before moving | fixed 72-hour windows | 1/1 → 1/1 | still caught |
| Pilot car 25-30 minutes ahead | fixed 20-minute convoy window | 1/1 → 1/1 | still caught |
| Cash held twelve days | *known limit:* 7-day wide-scale hops | 1/1 → 0/1 | evades, as documented |
| Pilot car over an hour ahead | *known limit:* 60-minute wide window | 1/1 → 0/1 | evades, as documented |
| Successor SIM calls mostly new people | *known limit:* succession found through shared contacts | 1/1 → 0/1 | evades, as documented |

No tactic created a false lead among the background population. The first version of the simulator found two real loopholes, the merchant-label exemption and the SIM-box conjunction. Fixing them, and adding the wide scales, moved three tactics from "evades" to "caught".

## 8. What building it found

| Finding | Effect | Fix |
|---|---|---|
| The `Resolver` union-find left each cluster's root out of the cluster, so a person and one of their raw records were treated as two identities | The syndicate detector missed the planted gang (its older FIRs sat on a raw CCTNS record); behaviour flags and inferred associations were split the same way | All members, roots included, are clustered (analytics/inference.py) |
| CCTNS-style names are surname-first | Resolution must be order-insensitive | The matcher was already order-insensitive; the resolver bug above was the real cause |
| Money traces stopped at any account labelled "merchant" | Registering the collector as a shop would hide a ring | Hubs defined by behaviour; regulated institutions only by kind |
| The SIM-box rule needed all six signs | A few staged incoming calls defeated it | 4-of-5 vote |
| The Fraudar detector excluded salary by narration | Contradicted the narration-blind rule; and a business group's customers formed a dense block | Narration removed; a pass-through requirement added |
| Incoming calls in the generator carried the receiver's tower | Placed random callers at the call centre and produced false recce leads | Caller towers fixed; recce now needs joint presence on two days |
| The inferred-association convoy basis counted one plaza twice | Commuters at the same toll plaza at rush hour would be "in convoy" | Requires two or more different plazas |
| Two views imported by the UI were missing | The UI could not be built | Connections and Face search views written |
| **(at 10,000 people)** The syndicate test ran on Louvain communities of the co-offending graph | On a 14-person graph the modularity partition cut the five-member gang 4 + 1, so no member kept two joint charge-sheets inside its community, and the statutory test failed | The graph is built only from FIRs that can count towards s.111. Each connected group of three or more is tested whole, and only groups above 30 are split |
| **(at 10,000 people)** The precursor guard against steady growth compared the recent month with month 2 only | A diversion that began two months ago had already raised month 2, so the 6x jump measured 2.03x against a 2.5x bar and the buyer was missed | The guard now looks for an abrupt step anywhere in the last quarter: a month at least twice the median of the three before it. A steady ramp still has no step |
| The full-text index row was deleted by an unindexed column (`DELETE FROM objects_fts WHERE id=?`) | Every object update scanned the whole index, so building the world was quadratic: a 10,000-person world took more than 25 minutes | The index row now shares the object's rowid, giving a keyed delete, plus a one-time migration. The 10,000-person world builds in 88 s and the 30,000-person world in 335 s |
| `identifiers` had no index on `object_id` | The same quadratic delete on every update | Index added |
| Resolution blocks grew with the population (surname + initial) | 1.46 million candidate pairs at 11,000 records; resolution took more than 8 minutes | Adaptive blocking: a small block is compared as it is, and a large one is split by overlapping birth windows, then district, then gender. 690,000 pairs at the same pair completeness (99.92%), with name comparisons cached; resolution runs in under 2 minutes |

## 9. What is deliberately not built

- **Radicalisation indicators from speech, religion or ideology.** Automated inference from content or belief is the most error-prone and discriminatory form of profiling, and it fails the proportionality test of *K.S. Puttaswamy v. Union of India* (2017). Incitement or material support, when it exists, enters through a sealed lawful exhibit reviewed by an officer. The terror track works on conduct: money, handsets, contacts with handlers, repeated site visits, precursor purchases, weapons.
- **Person risk scores and predictions.** None is computed or stored. Severity belongs to a pattern, not a person.
- **Bulk social-media collection.** Handles exist only as sealed exhibits with a hash and an order.
- **Population-wide face search.** The existing face module searches only case evidence, one face per search with a reason, and needs a second officer to confirm.
- **"No criminal can hide."** No system achieves this, and claiming it would be wrong. Section 7 shows the documented limits succeeding where expected. Some networks leave no trace in these records at all: cash carried by hand, internet calling, hawala with no banked leg, places without toll plazas or ANPR.

## 10. Limits of this evaluation

1. **The planted networks and the detectors were written by the same author.** Perfect precision on synthetic data shows the detectors implement their specification and ignore the look-alikes that were thought of. It says nothing about look-alikes nobody thought of. Real accuracy needs labelled pilot data, held out, with reviewer dispositions.
2. **Thresholds are set from statute, published screens or judgement, not fitted.** On real data they must be calibrated per district and per bank, with false leads per 1,000 eligible records tracked over time.
3. **Bias audit.** The protected-attribute scramble shows no detector reads those attributes. It does not show the data itself is unbiased. Who gets an FIR, a history-sheet or a CDR request reflects prior policing, and seeded detectors inherit that. A real deployment needs disparity monitoring of leads by district and community, done by an independent body under a lawful basis.
4. **Scale.** The in-memory ledger and CDR stream are fine to about a million rows. Above that, the same algorithms need partitioned execution (DuckDB/Parquet, or PostgreSQL with AGE; see 04 and 07).
5. **Legal review.** Mandates, purpose classes and the two-person rule are configurable templates written for a pilot. Each agency's actual legal powers and the DPDP Act s.17 exemptions need review by its legal advisers.

## 11. Reproducing

```bash
drishti demo --fresh --no-serve       # builds the world, runs detectors, evaluation and the red team
drishti patterns eval                 # per-detector table
drishti patterns redteam              # adversary simulation
drishti patterns catalog              # every detector's question and tracks
pytest tests/test_patterns.py         # detection, look-alikes, fairness, evasion, lead workflow
```

In the UI: **Leads** (rail) shows the queue for the acting agency, the Detectors catalogue and the Robustness tab. A dossier's **Record & patterns** tab shows FIR roles, communications, movement, purchase registers, tenders, weapons and findings, within the case's purpose.

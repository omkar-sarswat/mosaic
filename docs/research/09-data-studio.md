# 09 · Data studio: governed intake, cleaning and interpretation

*How a messy source extract becomes ontology records without anyone overwriting the record, and how the
same extract can be read in several ways before it is published.*

## What it is for

Agencies receive data as extracts: a bank's KYC export in reply to a BNSS s.94 notice, an RTO register,
hotel guest registers, pages of a seized diary. These files are messy. Names come in four orders and
three cases. Mobiles arrive with `+91`, a leading `0` or dashes. Dates arrive as `16/06/1991`,
`16-Jun-1991` or `1991-06-16`. Cities arrive as "Bombay", "Poona" or "Thana". Identifiers are typed
by hand. The data studio turns an extract into a reviewable proposal:

```
Extract → Detect → Transform → Quarantine → Dedupe → (Parse) → Map → Match → Lenses → Proposal → Review → Publish
```

The design follows the published descriptions of Palantir Gotham / Foundry:
- the ontology mapping principle: dataset → object type, row → object, column → property, cell → value,
  join → link type;
- CEDT intake (crawl, extract, detect, transform) with a lineage view;
- the revisioning database (every change is a card with who, when, source and security);
- private workspaces that are published only after review.

Sources: Wei et al., *A Brief Analysis of Palantir Gotham* (IEEE BigDIA 2024,
doi:10.1109/BigDIA63733.2024.10808897), and Palantir's platform overview (2009, National Security
Archive). DRISHTI differs from those systems in four ways:
- the proposal is case-bound and purpose-limited;
- the reviewer must be a different supervisor;
- existing values are never overwritten;
- every interpretation lens carries its innocent explanation.

## Stages

| Stage | What happens | Where |
|---|---|---|
| Detect | Each column is typed by voting over its values (PAN, IFSC, Aadhaar, account, registration, mobile, date, email, amount, city, person name, identity document, category). The header is ignored. The profile shows completeness, distinct values, value shapes with examples, how many cells the suggested steps would change or reject, and how many dates read both ways (dd/mm vs mm/dd). | `intake/clean.py: profile, detect_type` |
| Transform | A recipe is an ordered list of (column, step). Steps are pure functions value → (value, reason). There are 20 of them, including placeholders → empty, mobile to 10 digits, registration to canonical form, PAN/IFSC validation, Aadhaar masked to its last four digits, dates to ISO (day-first or month-first), city to its LGD name, amounts in lakh/crore, colour and account-type codes. Every changed cell is listed with before, after and why. | `STEPS`, `apply_recipe` |
| Quarantine | A row whose required column is empty or rejected is held back with its reasons. Nothing is dropped silently. | `apply_recipe` |
| Dedupe | Exact duplicates on the key columns after cleaning. The first row is kept and the rest are reported. | `dedupe` |
| Parse (free text) | Spans are tagged in priority order and never overlap: account numbers after "A/c", registrations, PAN, IFSC, mobiles, amounts, dates, places, then capitalised names. A written name is tied to a person only when an identifier on the same page is on record for someone of that name. | `extract_entities`, `pipeline.tag_notes` |
| Map | The column → `Type.property` mapping is editable and validated against the ontology. "geo.city" places a row on the map; "context" keeps a column in lineage only. A switch maps one column by another: hotel ID numbers go to PAN or driving licence according to the ID-type column, while Aadhaar only compares its last four digits. A full Aadhaar can never be mapped. | `SPECS`, `validate_mapping`, `row_props` |
| Match | All identifier hits are gathered: the record key, PAN, driving licence and mobile. Agreeing identifiers decide. Disagreeing identifiers are reported as a clash and never resolved silently. Two independent identifiers that agree on one person are accepted even when the name is written oddly. A name-and-city resemblance alone is only "probable". It becomes a new record plus a resolver candidate in Resolve. Rows not on record are resolved among themselves: by the same PAN, by the same mobile with a compatible name, or by the same full name and date of birth. | `match_row`, `resolve_new` |
| Plan | For a record already on record, each incoming value is classed as fill (a gap), corroborate (the same value, so only provenance is added), conflict (different, so it is not applied and goes to the reviewer) or alias (a new spelling of the name). Several rows about one record yield one operation; a later row that disagrees with an earlier row's fill becomes a conflict. A document that belongs to someone else (a borrowed PAN) is never proposed as a correction to the guest's record. | `plan`, `_diff` |

## Lenses: reading one extract in different ways

The lenses run on the cleaned, matched extract before anything is published. Each pattern carries its
evidence rows, its parties and a "could also be" explanation. Each can be marked checked or dismissed,
and those marks travel with the proposal in its note.

| Lens | What it finds | Innocent explanation shown |
|---|---|---|
| Shared identifier | One mobile behind several different people (the mule-account pattern); one PAN behind several names; one chassis or engine number on two registrations (a cloned vehicle) | Family or office line; data-entry error |
| Many records | One person with three or more accounts across branches, or three or more vehicles | Business owners, families |
| Document mismatch | A guest shows a PAN that is on record for a different person; Aadhaar last four digits differ from the record | Typing error; a relative's document |
| Record conflict | Values that disagree with the record, counted by property | Address change, transliteration, error in either source |
| Repeat co-stay | Two people at the same hotel at overlapping times on two or more occasions, with whether they are already linked on record. Single overlaps are counted but not raised. | Colleagues on travel, family |
| Recurring identifier (notes) | The same number, vehicle or account on several pages, flagged when it is not on record | A shop, a driver, a common contact |
| Geography | Rows per place over district boundaries, with the share not yet on record | — |
| Link graph | Only the parts of the extract that form a pattern, so the chart stays legible | — |

## Governance

- **Case-bound and purpose-limited.** Preview and proposal need an open case. The user must be a
  member, and the case purpose must cover every record class the source touches. For example, a
  flood-relief (disaster_response) case cannot take a bank KYC extract.
- **Withholding.** The extract's own values are the case's material and are shown. A matched person's
  record is revealed only when the guard allows it for this case. Otherwise the row says it matched,
  but not whom.
- **Two-person rule.** An investigator or analyst proposes. A supervisor who is a member of the case,
  and not the proposer, approves or rejects, with a reason. The proposal freezes the recipe, the mapping
  and the exact operations (with a fingerprint), so what is reviewed is what is published.
- **Provenance.** Created records carry `origin_case`, `legal_order` and the source `INTAKE/<source>`,
  so they are purged with the case and destroyed if the order is set aside. Every applied operation
  writes a revision card (`revisions` table): object, property, operation, old value, new value,
  source row, proposal, actor and time. `GET /api/intake/history/{id}` returns an object's cards,
  guarded like any read.
- **Revert.** A supervisor can revert a publish card by card:
  - created records are removed;
  - filled values are cleared, but only if nobody has changed them since;
  - learned aliases are removed;
  - the intake's evidence entry is taken off shared links;
  - pending resolver candidates are withdrawn.
- **Audit.** Every preview, proposal, approval, rejection and revert is written to the hash-chained
  audit log.

## Verified behaviour (tests/test_intake.py, 25 tests)

The extracts are generated from the synthetic world, with planted patterns whose truth is used only by
the tests:
- **Detection and cleaning:** column types are detected as listed above; quarantine and duplicate
  counts are exact; no full Aadhaar number appears anywhere in a preview.
- **Planted patterns:** each is found, and only the planted ones are raised for review. These are the
  4-customer mule mobile, the 3-branch account holder, the cloned chassis, the borrowed PAN, the
  3-time co-stay pair and the number recurring on 4 diary pages.
- **Conflicts:** planted date-of-birth conflicts are proposed as conflicts, never as fills, and a
  publish leaves the recorded values unchanged.
- **Interpretation:** switching the date reading to month-first changes ambiguous dates; mapping the
  city to "context" removes the geography lens and every city operation.
- **Governance:**
  - a preview without a case, or on a disaster-response case, is refused;
  - self-approval is refused;
  - a proposal writes nothing until it is approved;
  - after approval the new records carry the case and the order, and the history endpoint returns
    their cards;
  - a revert restores the object count exactly.

## What it does not do

- It does not read real bank, RTO or hotel systems. The connectors would replace `sources.generate`.
  The pipeline after extraction is unchanged.
- Names written alone in free text are not resolved without a corroborating identifier on the same page.
  This is deliberate: a first name is not an identity.
- Conflicts are surfaced, not settled. Settling a conflict is a separate, audited edit on the record.

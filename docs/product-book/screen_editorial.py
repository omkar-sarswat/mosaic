"""Formal figure titles and explanations. Original control coverage is retained."""

TITLES = dict(line.split('|', 1) for line in '''01-overview|Workspace overview
01-search|Global record search
01-search-script|Search across scripts and spellings
01-open-case|Case creation
02-overview-crime|Investigating officer’s work queue
02-overview-supervisor|Supervisory decisions
01-light-theme|Workspace appearance
01-account-menu|Identity and session controls
01-role-refused|Role-based access refusal
03-case-board|Case board
03-case-suspect-open|Case-priority explanation
03-case-leads-board|Case lead progression
03-case-board-5|Case alerts and chronology
03-case-close|Case closure and legal holds
03-case-network|Case network
03-case-evidence-form|Exhibit registration
03-case-evidence|Evidence locker and custody
03-case-evidence-exports|Evidence release and export
03-case-reports-list|Report templates
03-report-editor|Structured report composition
03-report-editor-2|Report content selection
03-report-editor-3|Draft management
03-report-export|Recipient-specific report release
19-report-page-1|Exported case report
19-certificate-page-1|Draft evidence certificate
04-leads-ncb|Detector finding and evidence
04-leads-ncb-request|Case request and lead disposition
04-leads-syndicate|Approved lead in case context
05-alerts|Financial typology alerts
05-alerts-filtered|Transaction-path examination
06-watchlist|Entity-watch activity
06-watchlist-area|Geographic watch
06-watch-dialog|Watch configuration
06-watchlist-search|Saved-search review
07-network|Network workspace
07-network-list|Network record list
07-network-types|Layouts and relationship filters
07-network-analysis|Structural analysis
07-network-community|Communities and connectivity
07-network-money|Financial-flow layout
07-network-inspector|Record inspection and path analysis
08-dossier-overview|Dossier overview
08-dossier-overview-2|Case assessment and actions
08-dossier-unmask|Protected-field access
08-dossier-record|Case history and pattern findings
08-dossier-financials|Accounts and transaction history
08-dossier-network|Entity relationship network
08-dossier-comms|Communication-record analysis
08-dossier-assets|Travel and asset records
08-dossier-timeline|Chronological record view
08-dossier-sources|Source provenance
09-money|Outward financial trace
09-money-in|Inward financial trace
09-money-accounts|Account-level financial trace
10-connect-start|Relationship-enquiry setup
10-connect|Connections between records
11-globe|Geographic overview
11-globe-zoom|Local geographic examination
11-area-panel|Area-search parameters
11-area-results|Area observations
11-area-results-2|Observation details and coverage
12-explore|Incident overview and record access
12-explore-results|Filtered record exploration
13-studio-columns|Extract profiling
13-studio-cleanup|Cleaning and quarantine
13-studio-fields|Field and relationship mapping
13-studio-matching|Incoming-record matching
13-studio-checks|Pre-publication checks
13-studio-changes|Proposed record changes
13-studio-tagging|Narrative tagging
13-studio-diary|Document-reference inspection
13-studio-proposed|Submission for review
13-studio-review|Publication decision
13-studio-published|Published intake
14-review|Identity-review queue
14-review-pair|Record-pair comparison
15-faces-empty|Probe-image registration
15-faces-found|Face selection and search purpose
15-faces-candidates|Candidate comparison
15-faces-confirm|Independent candidate review
16-cop|Disaster-alert overview
16-cop-flood|Alert detail and affected area
16-cop-dispatch|Resource-dispatch record
17-oversight|Audit and oversight workspace
17-oversight-filtered|Targeted audit examination
17-transparency|Transparency and retention
18-admin-library|Detector documentation
18-admin-quality|Source-quality register'''.splitlines())

# Replace the original short, promotional narration with operational explanations.
TEXT = {
'01-overview': 'The overview brings the active case, navigation and work queue into one operating context. Before opening records, the officer can confirm the case purpose and identify outstanding work. The queue routes requests, approvals, watched activity and other relevant items to the appropriate screen. The case summary provides direct access to its records and analytical views.',
'01-search': 'Global search locates permitted records from a name or supported identifier. Results are grouped by record type, with contextual details such as district to help distinguish similar names. Selecting a result opens its associated record view. Withheld counts distinguish restricted matches from a search with no matching records, without exposing the restricted material. The active identity and case govern the result set.',
'01-search-script': 'Name search compares supported Indian scripts and English transliterations. The illustrated enquiry returns spelling variants associated with the same search term, helping an officer locate records whose source systems use different conventions. The matching process accommodates initials, common honorifics and surname-first arrangements. A search match is a retrieval aid: the officer must inspect the identifying details and provenance before concluding that two records describe the same person.',
'01-open-case': 'Case creation establishes the context for subsequent record access. The officer provides a title, selects an approved purpose and records the basis for the investigation, including the applicable reference or order. Where an FIR number is supplied, matching records can be associated with the case. The resulting case carries its purpose into later searches, views and exports, allowing those actions to be reviewed against the context in which they were performed.',
'02-overview-crime': 'The investigating officer’s queue presents available updates associated with the case. The illustrated scenario includes watched activity, area observations and detector leads. Priority and category controls help the officer select the items requiring examination, while each entry provides a route to its supporting record. The adjoining case panel retains the principal case details so that opening a queue item does not detach it from the investigation.',
'02-overview-supervisor': 'The supervisory view concentrates requests and decisions that the acting user is eligible to review. A decision card presents the request with its context and provides the applicable approval or refusal action. Recording the reason preserves the basis of the decision and makes its outcome available to the requesting officer. The surrounding case information helps the supervisor assess the request within the investigation rather than as an isolated task.',
'01-light-theme': 'The workspace provides light and dark appearance options. The illustrated light view presents navigation, record details and analytical material on a consistent light surface while retaining the same case context and controls. Appearance preferences are separate from access rights: the acting identity, role and case continue to govern available records and actions. The account menu provides a visible reference for checking the user’s current operating identity.',
'03-case-board': 'The case board assembles the investigation’s purpose, legal basis, team and available record summaries. It provides an overview of the case network and routes the officer to detailed evidence, financial activity and reports. Case-specific prioritisation directs attention to supporting facts; the officer can inspect its explanation before adopting a line of enquiry.',
'03-case-suspect-open': 'Expanding a prioritised person exposes the evidence behind their position on the case board. The explanation identifies the relevant accounts, transfers and other facts, allowing the officer to assess both the relationship and its significance. Dossier, money-trail and network actions provide alternative views of the supporting material. Adding a lead records a line of enquiry for further work; the priority itself is not an established finding about the person.',
'03-case-leads-board': 'The lead board coordinates lines of enquiry across five states: Lead, Investigating, Awaiting approval, Action authorised and Closed. Cards retain the item as it progresses, allowing the case team to distinguish active examination from a request awaiting a decision. Moving into Action authorised is restricted to a supervisor. This makes authorisation a separate recorded step, while the remaining board states communicate the progress of the investigation.',
'03-case-board-5': 'The lower case-board views combine financial alerts with chronological events. Alerts expose the relevant finding and amount; the timeline orders available transfers, travel and filings by date. Each entry links to its supporting record. Reading these views together helps the officer examine whether an apparent sequence is supported by the recorded dates, and identify which source material needs further review before a narrative is included in the case report.',
'03-case-network': 'The case network brings its available people, accounts, phones, companies, places and relationships into a common graph. It provides the layout, filter and analysis tools used in the main Network workspace while retaining the selected case. The officer can move from a case summary to relationship examination, select a record and inspect its supporting context. The illustrated neighbourhood view focuses on the selected company and its directly linked case records. The graph describes the material available to the case rather than all relationships that may exist outside it.',
'03-case-evidence-form': 'Exhibit registration associates an uploaded file with its description, origin and handling context. The form captures available device details, including make, model, serial number, IMEI or MAC address, together with the person or source that produced the material and the relevant order. Mosaic computes a SHA-256 fingerprint and stores the file through its write-once evidence workflow. Subsequent verification compares stored bytes with that recorded fingerprint.',
'03-case-evidence-exports': 'The evidence-release view combines export selection with a named recipient and release clearance. The officer can produce a case report or an evidence pack containing the relevant files and supporting records. Custody information and fingerprints provide references for checking the released material. The release context should be reviewed together with the selected content so that the exported copy reflects the intended recipient and handling conditions.',
'03-case-reports-list': 'The report list provides three starting templates: case diary, charge-sheet annexure and intelligence summary. Each organises the relevant case material for a different reporting purpose. Creating a draft supplies structured sections and available records, after which the officer selects content and writes the analysis. A template assists preparation; the officer remains responsible for reviewing the facts, narrative and suitability of the completed document before release.',
'03-report-editor': 'The editor combines authored narrative with structured case material. The insertion panel provides records, exhibits, pattern leads, area searches and relationships that can be added as report blocks. Those blocks retain references to the underlying material and refresh their facts when the draft is opened. The officer can therefore review current source-backed content alongside their interpretation before producing a fixed export.',
'03-report-export': 'The export dialog identifies the intended reader and release clearance before producing the PDF. The document carries the applicable handling information and a watermark tied to the release context. Export creates a fixed representation of the reviewed draft, while the editable report remains available for subsequent work. The officer should confirm the recipient, selected content and narrative before releasing that version.',
'19-report-page-1': 'The exported case report presents the reviewed draft as a fixed document. It combines selected record facts with the officer’s narrative and the source references included by the report workflow. The illustrated page shows the resulting document hierarchy and handling context. It should be read as an example of the export format; the synthetic names, amounts and case details do not describe an operational investigation.',
'19-certificate-page-1': 'The evidence pack includes a draft certificate populated from the information held in the case workflow. It connects the exhibit details and recorded handling information with a document prepared for review. The illustration shows the generated format, not a completed or independently validated certification. The responsible officer must review the source information, complete the applicable requirements and assess the document’s suitability for its intended use.',
'04-leads-ncb': 'A detector finding presents the question, measurements and supporting records that prompted the lead. The officer can inspect the pattern in its mission context and compare the evidence with the stated thresholds. The accompanying explanation includes possible ordinary interpretations, helping the reviewer identify what further information is needed. Pre-case presentation preserves the permitted level of identity access until the relevant request has been approved.',
'04-leads-ncb-request': 'The lead can be submitted as a case request with a title, purpose and recorded legal basis. An eligible supervisor reviews the request separately from the proposing officer. Alternatively, dismissal records the reason for not proceeding with that lead. Both actions preserve a disposition rather than leaving the finding without an explanation. The request workflow establishes whether the proposed work should enter an authorised case context.',
'04-leads-syndicate': 'After an approved request establishes the case context, the lead can be examined with the identity and record information the case is permitted to access. The officer reviews the participating records and supporting relationships, then continues through the dossier, network or case workflow. Approval authorises the relevant case work; it does not establish that the detector’s interpretation is correct. The supporting evidence remains subject to examination.',
'05-alerts': 'The alert list organises financial findings from the implemented typology rules. Each entry identifies the applicable rule, severity and supporting context. Filters help the officer narrow the list to a particular kind of pattern before opening its detail. The selected alert then provides a route to the relevant accounts, parties and transaction analysis. Severity prioritises review of findings and should not be read as a general assessment of a person.',
'05-alerts-filtered': 'The filtered view isolates a particular financial typology and presents its selected finding. For a potential circular transfer pattern, the officer examines the path, amount and participating accounts, then checks the underlying transactions and their chronology. Dossier, money-trail and network links provide supporting views. The structure of a path is only part of the assessment; source coverage, timing and the purpose of transfers remain relevant to the interpretation.',
'06-watchlist': 'The entity-watch view groups new activity associated with records followed by the case. Each item provides its category and review status, allowing the team to distinguish new material from entries already examined. Importance and activity filters organise the queue, while the underlying record provides the evidence for follow-up. A watch preserves the investigative interest and its reason; it does not grant additional access to restricted sources.',
'06-watchlist-area': 'A geographic watch retains a defined area and its case context. Newly ingested vehicle or communication observations within the area can appear when they are visible to the case. The illustrated scenario uses a circular area and distinguishes relevant recorded activity for review. An observation must still be interpreted according to its source, time and relationship to a person; proximity alone does not establish participation in an event.',
'06-watch-dialog': 'The watch dialog records why the case is following the selected record and defines the history to include. The officer can begin from the current point or include the supported 30-day or 90-day interval. The reason remains available to the case team when reviewing subsequent activity. Saved searches provide a related workflow for retaining a query; they are re-evaluated when the work queue loads, using the records available to the case.',
'07-network': 'The network represents available records as nodes and relationships as links. Money transfers, calls, shared devices, directorships, addresses and family relationships can be examined in the same working view. The presentation distinguishes recorded relationships from machine suggestions. Layout and filtering controls help the officer select the structure relevant to the question while retaining access to the supporting record inspector.',
'07-network-analysis': 'The analysis panel examines structural properties of the loaded graph. Community detection groups records with stronger internal connectivity; centrality and articulation measures identify positions connecting other parts of the graph. Components, bridges, dense cores and directed cycles provide additional perspectives. Selecting a result directs the officer to records that merit inspection. These measures describe the graph presented to the analysis and do not determine the intent or conduct of its participants.',
'07-network-money': 'The financial-flow layout arranges the relevant accounts and transfer relationships to make direction easier to follow. Links are sized according to the represented amounts, helping the analyst compare routes without reconstructing the structure from separate statements. The officer should inspect the underlying transactions and selected scope when interpreting the visual. Aggregated transfers describe the available records; they do not resolve the purpose or ultimate control of the funds.',
'07-network-inspector': 'Selecting a record opens its available details and related evidence. From the selection controls, the officer can inspect the record, expand its neighbourhood or compare paths between selected endpoints. Supported methods include shortest paths, alternative routes, directed paths and money-only examination. A maximum-flow result is a capacity calculation over the loaded graph, not a statement of actual transferred value. Path findings require inspection of their component relationships.',
'08-dossier-overview': 'The dossier assembles the authorised records associated with the selected entity. Its overview provides identifying information, case context and routes to deeper examination. Eight tabs organise the overview, record and patterns, financials, network, communications, travel and assets, timeline and sources. Each tab offers a different perspective on the available material while retaining the selected record.',
'08-dossier-record': 'Record and patterns brings together the available incident history and detector findings associated with the selected person. Entries retain the recorded role, reference, legal sections and status where present. Other available material can include a history sheet, recurring contacts, tower information and weapon references. The officer should distinguish a person’s recorded involvement or allegation from an established outcome and inspect the source of each entry before using it in analysis.',
'08-dossier-financials': 'The financial view lists the available accounts and summarises inflows and outflows over time. Transaction rows retain channel, narration and counterparty details so that the officer can move from a monthly pattern to an individual transfer. Account and amount filters narrow the working set. The onward-trace action opens financial tracing from the current entity, preserving a route between the summary and the transaction relationships requiring examination.',
'08-dossier-comms': 'The communications view summarises the available call records by contact, duration and time. Contact entries include call counts, minutes and the first and last recorded interaction, together with subscriber information where available. The hourly distribution helps the officer examine timing within the loaded material. Call metadata establishes a recorded connection between identifiers; it does not reveal conversation content or independently establish who used a device at that moment.',
'08-dossier-assets': 'Travel and assets groups the available journey, booking and ownership records associated with the entity. Routes, dates and booking references provide a basis for chronological comparison. Vehicle, property, firearm or wallet records are shown where the permitted source material supports them, including relevant family context. Ownership, booking and actual use should be assessed separately. Any comparison with declared income requires examination of the underlying dates, values and sources.',
'08-dossier-timeline': 'The timeline orders available dated events for the selected record, including transactions, calls, travel, incidents and filings. Each event links to the record from which it was derived, and paging provides access to further entries. This common chronology supports comparison across different source types. The officer should consider the meaning of each timestamp, source coverage and any gaps before presenting the sequence as an explanation of events.',
'08-dossier-sources': 'Sources provides the route from a consolidated dossier back to its available origins. Property-level information identifies the source system, record reference, ingestion context and matching information where recorded. The original source rows provide context for values that agree or conflict. This view is essential when an officer needs to explain why a fact appears in the dossier or assess whether a proposed identity association is adequately supported.',
'09-money': 'An outward trace starts from the selected person, company or account and follows available transfers in the direction of movement. Hop and amount controls set the extent of the query, while party or account presentation changes the level of aggregation. The flow and endpoint details help the officer identify routes requiring further examination. The result is limited by the query and the records available to the active case.',
'10-connect': 'The two-record view examines the available connections between selected endpoints. The displayed chain can include direct relationships, intermediate records and inferred associations, each of which requires assessment of its supporting source. The officer can open the linked dossiers to inspect identity and activity in greater detail. A path establishes a connection in the available record model; its significance must be explained through the specific relationships it contains.',
'11-globe': 'The geographic overview combines the selected scope with layers for records and relationships. The officer can examine the active case or other permitted flagged material, switch relevant layers and select a mapped item for context. Financial and travel links show available movement or relationships across places. Map position must be interpreted according to its source: a registered address, a transaction endpoint and an observed location represent different kinds of information.',
'11-area-results': 'Area search returns available observations matching the selected place, radius and time interval. Vehicle, phone and travel results provide recorded times and locations, with routes to owner records and further analysis. Registered residents are treated separately from observations. The officer should use the source and timing to assess whether a result is relevant to the enquiry and check the coverage information before interpreting an absence of results.',
'12-explore-results': 'Explorer narrows the available records through search and object-type filters. Selecting a result exposes its properties, links, handling context and provenance. This supports direct examination of a known reference as well as discovery within a filtered collection. Permitted actions include adding a record to the active case, requesting a protected value with a reason and saving a query for later review through the work queue.',
'13-studio-columns': 'Extract profiling examines the incoming material before it becomes shared case data. The studio identifies column characteristics from their values and presents the received rows with the available source context. The officer can inspect the structure, completeness and proposed interpretation before moving to cleaning and mapping. Progress information distinguishes received, typed, cleaned, quarantined, deduplicated, matched and proposed material so preparation remains visible throughout the workflow.',
'13-studio-cleanup': 'Cleaning applies an ordered recipe to the incoming extract while preserving the source as the reference. The preview exposes changed cells, duplicate handling and quarantined rows so the officer can inspect the result of each transformation. Controls allow the recipe to be applied or reset. Incomplete identifiers require explicit treatment rather than unsupported reconstruction. The prepared values feed the later matching and proposal stages, where their effect can be reviewed before publication.',
'13-studio-fields': 'Field mapping defines how the extract is represented in the record model. A dataset is associated with an object type, rows become objects, columns become properties and joins establish relationships. The officer reviews the suggested mapping, adjusts it where needed and applies the result. Unmapped fields and policy-blocked record classes remain visible so the proposal does not conceal information that could not be represented or was not permitted.',
'13-studio-matching': 'The matching stage compares prepared rows with existing records and classifies them as on record, probable or new. The explanation identifies supporting agreement, such as an account number, PAN or phone reference. The officer can filter the categories or use a check-generated lens to inspect a relevant subset. This stage makes the proposed association available for review before the extract changes shared case records.',
'13-studio-checks': 'Pre-publication checks identify patterns, discrepancies and relationships within the proposed extract. The view provides the supporting rows and possible ordinary explanations so the reviewer can assess why an item requires attention. The proposal can also be examined as links or places. Existing values and incoming information remain distinguishable: new material can fill a gap, corroborate a value or create a conflict requiring review rather than silently replacing the record.',
'13-studio-tagging': 'Narrative tagging identifies supported references in document text, including accounts, phones, vehicles, amounts, dates and places. Highlighted spans retain their location in the source so the officer can examine the surrounding wording. Linking a written name to a person requires a supporting identifier on the same page that agrees with the recorded individual. This condition reduces the risk of associating an unrelated person solely because the name is similar.',
'13-studio-published': 'The published view records the outcome of the separately reviewed intake. Approval applies the proposed operations with their order and decision context. The case team can inspect the publication, review resulting changes and use the recorded revert workflow if an error is identified. Pattern analysis can subsequently be rerun against the updated records. Publication establishes that the proposal was approved; the source material and its quality remain relevant to later interpretation.',
'14-review': 'The review queue contains record pairs for which identity requires a human decision. Selecting a pair exposes the original information and the reasons for the proposed association. The reviewer compares agreement and conflict across the fields, then records whether the sources describe the same person or different people. The reason should identify the evidence that supports the decision. An uncertain proposal is not accepted merely because it appears in the queue.',
'15-faces-candidates': 'Candidate results show the photographs returned for the selected probe face, together with similarity and available source information. The officer examines the resemblance in the context of the evidence image and the candidate’s record. A proposed match is then subject to review by another officer of the same case. The search output remains a set of candidates until that explicit human decision is recorded.',
'16-cop': 'The disaster overview presents ingested alert material alongside district boundaries and hospitals. The list retains sender, status and geographic context, while the map uses the available official codes, alert geometry, names or gauge references to place the affected area. Unmapped alerts remain visible in the list. The operator should check effective and expiry times and the mapping basis before using the view for response planning.',
'16-cop-flood': 'The selected flood alert combines its issued details with the available affected districts, gauge information and nearby hospitals. This gives the operator a common context for examining severity, timing and geographic extent. The dispatch function records resources allocated to the relevant district and adds the entry to the log. The illustrated data represents the ingested demonstration scenario rather than confirmation of a current emergency or a completed delivery.',
'17-oversight': 'The oversight workspace combines audit-chain status, recorded events and activity requiring further review. The auditor can inspect who performed an action, its case and purpose, and the resulting outcome without receiving the investigative record workspace. Filters support a focused enquiry, while the daily-root action provides a seal for independent publication. Transparency summaries expose aggregate activity separately from detailed audit inspection.',
'18-admin-library': 'The detector library documents each analytical method’s question, inputs, operating scope and implementation context. It covers patterns across financial records, communications, movement, assets and other supported sources. Expanded entries explain the method, possible evasion, ordinary look-alikes, limitations and references. This documentation supports informed interpretation of detector findings and provides maintainers with a structured account of what each method is intended to examine.',
}

CONTROLS = {
'01-overview': [
 '<b>Navigation.</b> Workspace, Investigation, Records, Operations and Governance organise the available tools by function and role.',
 '<b>Global search.</b> Ctrl+K opens search for names, phones, PANs, accounts, vehicles, companies and case references.',
 '<b>Case context.</b> The selected case supplies the purpose for personal-record access. Switching case updates the working context.',
 '<b>Work queue.</b> Category and text filters narrow new activity, requests, approvals, matches and decisions.',
 '<b>Case summary.</b> Purpose, officers, evidence and legal basis remain accessible beside links to the network, money trail and map.',
 '<b>Handling information.</b> The strip identifies the highest marking currently displayed and reminds the user that access is recorded.'],
'03-case-board': [
 '<b>Case identity.</b> Title, agency, purpose, status and the recorded basis identify the investigation.',
 '<b>Four views.</b> Case board, Network, Evidence and exports, and Reports organise the case workflow.',
 '<b>Summary measures.</b> Available records, people, accounts, alerts and financial endpoints describe the loaded case material.',
 '<b>Priority and reasons.</b> Relevant accounts, transfers, signatories, directors and other links support the case-specific ordering.',
 '<b>Case connections.</b> Shared people and links open other cases only where the officer has access.',
 '<b>Lifecycle.</b> Closure records the outcome; configured retention and legal holds govern subsequent handling.'],
'07-network': [
 '<b>Layouts.</b> Structure, money flow, record type, community, neighbourhood and force-directed views organise the graph.',
 '<b>Analysis.</b> The loaded graph can be examined for communities, centrality, connectivity, dense cores and cycles.',
 '<b>Filters.</b> Relationship layers and record families narrow the displayed material.',
 '<b>Selection.</b> Click selects, Shift-click adds records, double-click expands and right-click opens dossier access.',
 '<b>Inspector.</b> Selected-record details and related evidence provide context for the visual connection.',
 '<b>Scope.</b> Graph exploration remains subject to permissions and the permitted case context.'],
'08-dossier-overview': [
 '<b>Identity.</b> Available names, original scripts, birth details, family, occupation, income and address identify the record.',
 '<b>Photograph.</b> The image retains its available source reference.',
 '<b>Case assessment.</b> Priority, relevant alerts and supporting facts connect the entity to the active investigation.',
 '<b>Follow-up.</b> Actions open the network, connections, money trail or map, and can create a watch or case lead.',
 '<b>Protected fields.</b> Masked values remain subject to permission and a recorded reveal reason.',
 '<b>Summaries.</b> Counts and financial totals describe available accounts, phones, relationships, cases, alerts and journeys.'],
'06-watchlist': [
 'Select an entity watch to inspect the available new activity and its underlying records.',
 'Filter by activity kind and importance to organise the items requiring review.',
 'Mark reviewed records that the item has been examined; Stop watching requires a recorded reason.'],
'14-review': [
 'Compare original-script names, family details, birth information, gender, district and identifiers where available.',
 'Examine the explanation of agreement and disagreement, including the distinguishing value of common names.',
 'Record a reason before choosing Same person or Different people.'],
'16-cop-flood': [
 'Check the sender, effective and expiry times, severity and named area.',
 'Read gauge levels against their warning and danger marks where available.',
 'Inspect affected districts and hospital references before recording a resource allocation.'],
'17-oversight': [
 'Verify the audit-chain status and inspect the recorded head fingerprint.',
 'Filter by user or record to examine time, action, case, purpose, record count and outcome.',
 'Seal the daily root when required; independent publication is a separate step.',
 'Review insider-threat alerts in context and consult the aggregate transparency view.'],
}

def apply_editorial(p):
    p = dict(p)
    key = p['image']
    p['title'] = TITLES[key]
    p['intro'] = ''
    if key in TEXT:
        p['text'] = TEXT[key]
    if key in CONTROLS:
        p['items'] = CONTROLS[key]
    # Remove repeated generic examples; precise, screen-specific examples remain.
    from details import ADDITIONS
    specific = {row[0]: row[4] for row in ADDITIONS}
    p['note'] = specific.get(key, '')
    return p

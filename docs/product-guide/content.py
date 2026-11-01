"""Editable narrative for the separate Mosaic product and capabilities guide.

Descriptions follow the inspected application and the approved reference book. Screens show synthetic
demonstration records. Mark the phrase that carries a paragraph with **double asterisks**; it prints in bold.
`keys` are the three points printed in the highlight strip under each lead.
"""

def page(title, lead, blocks, image=None, visual=None, group='Capabilities', outcome=None, keys=None, quote=None):
    return dict(title=title, lead=lead, blocks=blocks, image=image,
                visual=visual, group=group, outcome=outcome, keys=keys, quote=quote)

PAGES = [
# ------------------------------------------------------------------------------------------------ purpose
page('What Mosaic does',
 'Mosaic is Weirwood’s investigation and intelligence workspace. It brings an agency’s authorised records into **one connected picture**, and carries every finding through review, evidence and reporting, with each step recorded.', [
 ('One place to begin any enquiry', 'An enquiry usually starts with a single reference: a name, an account, a phone number, a vehicle or an FIR. In Mosaic, **that one reference opens everything connected to it**: the person’s dossier, their accounts and calls, the companies they control and the cases they appear in. The officer follows the thread in minutes, not weeks.'),
 ('Many views of the same records', 'People, organisations, accounts, phones, vehicles, properties, places, documents and events live in **one connected record model**. Dossiers describe one entity. Networks show relationships, Money trail follows funds, maps place activity and timelines put events in order. Each view asks a different question of the same records, without starting the investigation again.'),
 ('From information to action', 'Mosaic also runs the work around the analysis. **Data studio** prepares incoming extracts for review. **Leads, alerts and watches** surface what needs attention. **Case boards** track progress, supervisors record their decisions, the **evidence locker** preserves exhibits with their custody history, and reports turn selected facts into documents ready for release.'),
 ('Accountable by design', 'Every action is tied to an identity, a role, an agency, a case and a lawful purpose. **Source references, review decisions and a tamper-evident audit trail** let a colleague, a supervisor or an oversight officer see exactly what was examined, and why.'),
 ('How to read this guide', 'The guide explains why Mosaic was built and how it serves government agencies, then walks through **all 17 main capability areas**, with further sections on evidence, reporting and data publication. Screens are real captures of the application with synthetic records; the companion product book is the screen-by-screen reference.')],
 visual='model', group='Purpose and institutional value',
 quote='The full picture in minutes, and **the reasoning behind it**.',
 keys=['One connected picture of people, money, phones, places and events',
       'Every finding traceable to the record it came from',
       'Leads, decisions, evidence and reports in the same case']),

page('Why Mosaic was built',
 'Investigations rarely fail for lack of data. They slow down because the data sits in many systems, and **the link between a source record, a finding and the action it supports is easily lost**.', [
 ('Fragmented records mean repeated work', 'Bank statements, call records, FIRs, identity documents and field observations arrive in **different formats, with different identifiers**. Before anyone can ask the real question, dates, spellings and account numbers must be reconciled by hand, often separately by every officer on the team. Mosaic turns that preparation into **a shared, reviewed step**, done once for the whole case and visible to everyone working on it, so the next officer starts from clean, trusted records.'),
 ('A similar name is not an answer', 'The same person can appear in Devanagari, Urdu and English, with initials and changed numbers, while two different people can share one name. Mosaic separates **finding candidates**, **proposing a match** and a **recorded human decision**, so that uncertainty stays visible instead of disappearing inside a merged record that nobody can later explain.'),
 ('A picture needs its proof', 'A graph makes a connection easy to see, but a shared address, account or phone can mean many different things. In Mosaic **every link on a graph opens the records behind it**: the transaction, the subscriber, the registration. The officer checks the basis of a connection before calling it significant in a lead or a report.'),
 ('Handover needs the reasoning', 'Supervisors and courts need more than a conclusion. They need the records examined, the question being asked and the reason for each decision. Leads, intake proposals, custody chains and report drafts give that reasoning **a structured home**, so nobody has to reconstruct an investigation from notebooks, messages and disconnected files.'),
 ('What changes for the team', 'Less repeated searching. Evidence that is easier to inspect. **A clear view of what is waiting and who must decide it.** Mosaic is built so that the time an officer saves on assembling information is spent where it matters most: on judgement, on the people in the case and on the next lawful step.')],
 visual='problem', group='Purpose and institutional value',
 quote='The real cost of fragmented records is not only time. It is **the connection nobody saw**.',
 keys=['Records arrive in many formats from many offices',
       'One person can appear under many spellings and scripts',
       'A conclusion without its reasoning cannot be reviewed']),

page('How government agencies benefit',
 'One shared record and case model serves very different missions: a crime branch tracing a syndicate, a financial investigator following laundered proceeds, a narcotics unit watching a precursor route and **a state control room managing a flood**.', [
 ('Policing and organised crime', 'A crime-branch team brings FIRs, accused persons, phones, vehicles, travel and places into one case. **The board shows who matters and why**; dossiers, networks and area searches answer the next question; sealed exhibits and drafted reports carry the work towards the charge-sheet. Each person’s recorded role stays visible, so an allegation is never mistaken for an established outcome.'),
 ('Financial crime and cyber fraud', 'Accounts and transactions are examined alongside companies, directors, phones and case evidence. **Sixteen money-laundering typologies** flag shell companies, mule accounts, round-tripping and cash structuring. Money trail follows the funds hop by hop to their end points, and every figure links back to the statement it came from.'),
 ('Narcotics and specialist intelligence', 'Pattern detectors combine movement, communications, money and assets to raise leads such as **convoy vehicles, burner-phone switches and precursor diversion**. Parties stay pseudonymous until two officers of the same agency open a case, giving intelligence work a disciplined route from a first indication to an authorised enquiry.'),
 ('Control rooms and disaster response', 'Operators see official SACHET alerts, the affected districts, river gauges and nearby hospitals on one map, and **record resource dispatches in the same place**. Everyone in the control room works from one picture of what has been issued, where it applies and what has already been sent.'),
 ('Supervision, stewardship and oversight', 'Supervisors approve requests and publications, data stewards resolve source-quality issues, and an **independent oversight officer** reviews who accessed what, and why. Accountability is not a separate system added afterwards; it is part of the same workspace that the investigators use every day.')],
 visual='missions', group='Purpose and institutional value',
 quote='Different missions. **One workspace, one record model and one standard of accountability.**',
 keys=['Policing, financial crime, narcotics, intelligence and disaster response',
       'Each agency sees only its own mission tracks and cases',
       'Supervision and oversight built into every workflow']),

page('The operating model',
 'Every investigation in Mosaic moves through **five connected stages**. New evidence or a supervisor’s decision can send the team back to any earlier stage, without losing what has already been done.', [
 ('1  Establish the working context', 'The officer signs in and opens the case, with its **purpose, legal basis and team**. The work queue shows new activity and the decisions that are waiting. From then on, the case travels with the officer into every search, dossier and analysis, so it is always clear which material this enquiry is entitled to examine.'),
 ('2  Prepare and publish sources', 'Data studio profiles a new extract, cleans it in visible steps, maps its columns to records and proposes matches with existing people and accounts. The proposal is **frozen with its legal order** and published only after **a different supervisor approves it**. Nothing already on record is silently overwritten.'),
 ('3  Examine and develop a question', 'Work starts from a search, a pattern lead, an alert or a watched update. Dossiers give context; **networks, money trails and maps answer specific questions**; timelines put events in order. A good lead states exactly what needs investigating and which facts support it, so a colleague can pick it up without a briefing.'),
 ('4  Coordinate decisions and preserve evidence', 'The leads board tracks progress and **supervisory authorisation**. Identity and face matches carry their own review decisions. Files become **sealed exhibits with fingerprints and custody history**. Anyone reviewing the case can see what was proposed, what was decided and which evidence went with it.'),
 ('5  Report, close and account', 'Reports combine case facts with the officer’s narrative and are released to a **named recipient at their clearance**. Closing a case records its outcome; retention and legal holds govern what happens to the data next; and oversight can inspect every access and decision made along the way.')],
 visual='workflow', group='Purpose and institutional value',
 quote='Five stages, one case, and **a record of every decision made along the way**.',
 keys=['Establish, prepare, examine, coordinate, report',
       'The active case carries purpose and authority throughout',
       'Every stage leaves a record that can be reviewed']),

# ------------------------------------------------------------------------------------------------ capabilities
page('Workspace, search and daily work',
 'Every working day starts in the same place: **the officer’s own work queue**, inside the active case, with search one keystroke away.', [
 ('The case comes first', 'The active case shows its **purpose, legal basis and team**, and switching case changes the context of every screen at once. Five sections, Workspace, Investigation, Records, Operations and Governance, offer only the tools the officer’s role may use.'),
 ('One queue for the day', 'New pattern leads, activity on watched people, saved-search results, requests and approvals arrive in **a single work queue**, filtered by kind. An investigator follows an update straight into the case; a supervisor approves or refuses with a reason, in place.'),
 ('Search that understands India', 'Press **Ctrl + K** anywhere to search a name, phone, PAN, account, vehicle, company or case number. Names match **across scripts and spellings** and keep their original form, while districts and identifiers help tell similar names apart.'),
 ('Identity and roles', 'The account menu shows the acting officer, agency and role. A screen outside a role is **refused by the interface and the server alike**, so a copied link cannot open what a role should not see.'),
 ('Built for long shifts', 'Light and dark themes suit day offices and night-shift control rooms, and the foot of the screen always shows **the highest security marking on display**.')],
 image='01-overview',
 keys=['The case and its purpose are always on screen',
       'Search any name, number or ID in any script',
       'One queue for leads, activity and decisions']),

page('Case management and coordination',
 'The case is the unit of work. It connects the **reason for the enquiry** with the team, the records, the leads, the timeline and, finally, the recorded outcome.', [
 ('A board that builds itself', 'Opening a case records its title, purpose and legal basis. The board then assembles itself from the case records: **people, accounts, alerts, money traced onward, sent abroad and withdrawn in cash**, all at a glance.'),
 ('Suspects ranked by evidence', 'Mosaic follows the money from the case records and adds account holders, signatories, directors, call contacts and shared handsets. **Every rank is explained, fact by fact**, and is presented as a lead for the officer, never as a finding about a person.'),
 ('Leads that reach a decision', 'Each line of enquiry is a card on the **leads board**: Lead, Investigating, Awaiting approval, Action authorised, Closed. Officers move the cards; **only a supervisor can authorise action**, so no step rests on one person’s word.'),
 ('Network and chronology', 'The case network uses the same layouts and analysis as the Network workspace, within case scope. Alerts and the **case timeline** put transfers, trips and filings in order, each linked to its record.'),
 ('Closure with a clear trail', 'Closing records the outcome, such as a charge-sheet filed. **Retention and legal holds** are separate, recorded steps, so the institution can always show why a case ended and what it still holds.')],
 image='03-case-board',
 keys=['Every rank explained, fact by fact',
       'Only a supervisor can authorise action',
       'Outcome, retention and legal hold all recorded']),

page('Evidence registration and custody',
 'Evidence is sealed the moment it arrives. Each file keeps its **description, source, fingerprint and handling history** together, ready for inspection and for court.', [
 ('Register a distinguishable exhibit', 'The officer adds the file with a description, who produced it and the **legal order** it came under, plus device details such as make, model, serial number and IMEI, so it can never be confused with a similar file.'),
 ('Fingerprinted and write-once', 'Mosaic computes a **SHA-256 fingerprint** and stores the exhibit write-once. Verification at any later date compares the stored bytes with the registered value, proving the file is **exactly the one that was received**.'),
 ('A custody chain that keeps itself', 'Every view, download and verification is **added to the exhibit’s custody history automatically**. The fingerprint proves the bytes are unchanged; the custody chain shows who handled them, when and why.'),
 ('Court evidence packs', 'One click builds a pack for a **named recipient at their clearance**: the exhibits, their custody chains, a hash manifest and a **draft certificate under BSA s.63(4)**, prefilled with the exhibit, device, order and hash values.'),
 ('Ready to verify and sign', 'The certificate is a draft for the officer and the expert to check and sign. Keeping it with its exhibits and manifest gives the court **every reference needed to test the package**.')],
 image='03-case-evidence',
 keys=['SHA-256 fingerprint on arrival, stored write-once',
       'Custody history recorded automatically',
       'Court pack with a draft BSA s.63(4) certificate']),

page('Reports and controlled release',
 'Reports draw their facts straight from the case, so **the document always matches the evidence**, and every released copy is fixed, fingerprinted and addressed to a named reader.', [
 ('Templates for the documents that matter', 'Three starting points: the **case diary** (BNSS s.192), the **charge-sheet annexure** with the accused’s profile (BNSS s.193) and the **intelligence summary**. Each opens with the case’s people already in place.'),
 ('Facts inserted, not retyped', 'The officer inserts records, exhibits, pattern leads, area searches and the links between records as structured blocks. **Each block keeps its reference to the source**, so the reader can see exactly where every fact came from.'),
 ('The officer’s judgement, clearly marked', 'Authored text explains what the facts mean. **The difference between what a source records and what the investigation concludes stays visible** on every page.'),
 ('Drafts that stay current', 'Inserted facts **refresh from the records each time the draft opens**, so after a correction the narrative is revised, not contradicted.'),
 ('A fixed copy for each reader', 'Export names the **recipient and their clearance**. Anything above that clearance is left out, the copy is fixed and fingerprinted, and **later edits never change a released document**.')],
 image='03-report-editor',
 keys=['Case diary, charge-sheet annexure, intelligence summary',
       'Every fact keeps its source reference',
       'Released copies are fixed, logged and clearance-aware']),

page('Investigative leads',
 'Mosaic’s pattern engine watches the records with **19 detectors written around Indian law and crime typologies**, and raises each finding as a lead an officer can check, pursue or dismiss.', [
 ('Patterns across every source', 'Detectors read money, calls, movement, assets and criminal history together to find **burner-phone switches, convoys, hawala points, handset-sharing crews, precursor diversion and more**, each routed to the right agency.'),
 ('The evidence behind every lead', 'Opening a lead shows the **numbers, contacts, dates and measurements** that formed the pattern, how the detector works, what it deliberately ignores and the **innocent explanations to rule out** before acting.'),
 ('Pseudonymous until a case opens', 'Parties appear as Subject A, Subject B and so on. **Names are revealed only to members of a case** opened on the lead, protecting people who turn out to be uninvolved.'),
 ('Two officers decide', 'Asking for a case needs a title, a purpose and a legal basis, and **a supervisor of the same agency, not the requester, must approve**. A lead that does not hold up is dismissed with a reason, so it is not chased twice.'),
 ('From pattern to proof', 'Inside the case, the lead is tested against dossiers, networks, transactions and timelines. **The detector proposes; the officer establishes**, and the record shows how the pattern became evidence, or did not.')],
 image='04-leads-ncb',
 keys=['19 detectors across 8 agency mission tracks',
       'Names hidden until two officers open a case',
       'Every lead shows its evidence and innocent explanations']),

page('Financial alerts and typologies',
 'Mosaic watches every account in a case for **sixteen known shapes of money laundering**, and explains each alert in plain words, with the exact path the money took.', [
 ('Sixteen typologies watched', 'Fraud proceeds, mule pass-through, **shell companies**, high-risk remittances, income mismatch, rapid layering, diverted loans, crypto off-ramps, **round-tripping**, cash-outs below the s.269ST limit, **structuring below the PAN limit**, hawala and more.'),
 ('Read the structure, not just the rule', 'Each alert lays out the **accounts, amounts, dates and direction** involved: for example, three companies passing ₹6.60 crore round a closed cycle back to the start. The officer sees the pattern itself, not just its name.'),
 ('One click to the next view', 'From any alert, **open the dossier, trace the funds or see the network**. The same concern can be examined from the party’s profile, the financial route and the ownership links, all within the active case.'),
 ('Severity sets the order of work', 'A score shows which alert to read first. It **organises the queue; it is not a verdict** on a person, and the officer weighs ordinary business explanations before drawing a conclusion.'),
 ('Useful output', 'A finished review names the transactions examined, the concern, the evidence and **the questions still open**, ready to become a case lead, a request for further records or a section of a report.')],
 image='05-alerts',
 keys=['16 typologies, including s.269ST and PAN-limit structuring',
       'The exact money path spelled out',
       'One click to dossier, money trail or network']),

page('Watches and saved searches',
 'A watch keeps an eye on a person, number, vehicle, account or **place**, and brings anything new straight back to the case team’s work queue.', [
 ('Watch a person or record', 'The officer records **why the watch is needed**, chooses whether to include the last 30 or 90 days, and Mosaic then reports new calls, FIRs, leads and sightings as they arrive.'),
 ('Watch a place', 'An area watch covers a circle around a meeting place or scene. **Every number-plate read and every call through a tower inside it** lands on the watchlist, with people already named in an FIR flagged first.'),
 ('Read what matters first', 'Updates are sorted into **read first, worth a look and routine**, and filtered by kind. Marking items reviewed tells the whole team what has been seen, so nothing is read twice or missed.'),
 ('Searches that keep running', 'A search saved in the Explorer **runs again by itself** each time the queue loads, and new results reach the team, so a question asked once keeps working for the case.'),
 ('Ending a watch properly', 'Stopping a watch or a saved search **needs a reason**, recorded for the case. Watching someone is a serious step, and Mosaic makes sure it is always justified and never forgotten.')],
 image='06-watchlist',
 keys=['People, numbers, vehicles, accounts and places',
       'Updates ranked: read first, worth a look, routine',
       'Every watch starts and ends with a reason']),

page('Exploring records as a network',
 'The network shows the case as **people and things joined by what links them**: money, calls, shared handsets, directorships, addresses and family. Every link opens the records behind it.', [
 ('Start from what matters', 'Selecting a record brings its connections and details into focus. **The inspector shows identity documents, money in and out and the evidence for each link**, with routes to the dossier, the money trail or a wider neighbourhood.'),
 ('A layout for every question', 'Structure, money flow, by record type, **by community**, neighbourhood or free-form. Relationship layers separate **money, calls and devices, and property, vehicles and companies**, so one kind of link can be examined at a time.'),
 ('Readable at any size', 'Find any record in the list, group similar ones, hide what is not relevant, fit, zoom and rearrange. **Changing the layout never changes the evidence**; it only makes it easier to read.'),
 ('Recorded and inferred, never confused', 'Links from source records are drawn solid; associations a machine suggests are drawn differently. **The officer always knows which is which** before writing either into a lead.'),
 ('Safe to explore', 'Expanding the graph **never widens anyone’s permissions**. Reaching beyond the case scope needs a supervisor’s approval, so curiosity never becomes unauthorised access.')],
 image='07-network',
 keys=['Every link opens the records behind it',
       'Six layouts and three relationship layers',
       'Recorded and machine-suggested links drawn apart']),

page('Structural analysis and paths',
 'One click on Analyze answers the questions investigators ask of every network: **which groups, which go-betweens, which weak points and which routes**.', [
 ('Groups and separate parts', 'Community detection finds records **more tied to each other than to anyone else**; connected components show the parts of the network with no link between them. Each group opens with its members and links.'),
 ('Go-betweens and weak points', 'Betweenness finds the **intermediaries** on routes between otherwise separate people: an accountant, a shared account, a common handset. **Cut points and bridges** show the single record or link whose removal would split the network.'),
 ('Paths between two records', 'Find **the shortest connection, three alternative routes, the path that follows the arrows, or the money-only path**. The officer chooses the method that matches the question being asked.'),
 ('Money flow and loops', 'The money-flow layout lays accounts out in the direction funds moved, sized by amount; **maximum flow** shows how much could have moved between two points, and **loop detection** finds money that came back round.'),
 ('From structure to a question', 'Every result is **a starting point for enquiry, never proof of guilt**. The analyst returns to the transactions and records behind it, and turns the structure into an explained lead.')],
 image='07-network-analysis',
 keys=['Communities, intermediaries, cut points and bridges',
       'Shortest, alternative, directed and money paths',
       'Maximum flow and money that comes back round']),

page('Entity dossiers and provenance',
 'The dossier is **everything the case may know about one person, on one page**: identity, documents, roles, money, calls, travel, assets and the source of every fact.', [
 ('Identity at a glance', 'Photograph on record, name in English and in its **original script**, date of birth, father, occupation, declared income and address, with **role and rank in the case, typology alerts and conduct flags** beside them.'),
 ('Documents with built-in checks', 'PAN, passport, driving licence, voter ID and mobile number from each issuing system, with **format checks such as a valid PAN, an individual holder and a matching surname initial**.'),
 ('Protected by default', 'Aadhaar shows only its last digits. **Unmasking needs a written reason**, which is recorded and still subject to the case’s access rules, so sensitive identifiers are seen only when there is cause.'),
 ('Eight tabs, one person', 'Overview, Record and patterns, Financials, Network, Communications, Travel and assets, Timeline and Sources. **Actions on every dossier**: network, connections, follow the money, show on map, watch or add as a lead.'),
 ('Every fact has a source', 'The Sources tab shows **the system, record, arrival time and match confidence of every value**, and the separate source records resolved into this person. Nothing is merged without a trace, and any link can be undone.')],
 image='08-dossier-overview',
 keys=['Names in English and in their original script',
       'Aadhaar masked; unmasking needs a recorded reason',
       'The source of every fact, one tab away']),

page('Activity, communications and time',
 'The dossier’s specialist tabs show **what a person did, with whom and when**, so money, calls, travel and events can be read side by side.', [
 ('Financials', 'Every account, with **money in and out month by month** on one chart and every transaction listed with its channel, narration and counterparty. Flagged transfers are marked, and **Trace onward** opens the money trail from here.'),
 ('Communications', 'Top contacts with **call counts, minutes, first and last call** and the subscriber behind each number. A chart of calls by hour shows the person’s routine, and the days on which it changed.'),
 ('Travel and assets', 'Every journey with its route, date and booking reference, beside **vehicles, property, licensed firearms and crypto wallets** held by the person and their family: what someone owns, set against what they declare.'),
 ('Timeline', 'Every dated event in one stream, newest first: **transfers, calls, trips, FIRs and filings**, each linked to its record. Reading a life in order is often how the decisive moment in a case is found.'),
 ('Testing an explanation', 'An unusual transfer can be checked against the calls that week and the trips around it. **Supporting and conflicting facts are both kept**, so the conclusion shows its strength and its open questions.')],
 image='08-dossier-financials',
 keys=['Money in and out, month by month',
       'Who they call, how often and when',
       'Travel, assets and every event in order']),

page('Following the money trail',
 'Start from any person, company or account, and Mosaic follows the transfers **hop by hop**, onward to where the money ended or back to where it came from.', [
 ('Choose the question', 'Trace **where the money went or where it came from**. Set how many hops to follow and which small transfers to ignore, so the trail answers a focused question instead of drawing everything.'),
 ('By party or by account', 'Combine all of a person’s accounts into one bar, or **keep every account apart** to see exactly which instrument was used. Comparing the two views shows both the people and the accounts behind a flow.'),
 ('Read the flow at a glance', 'Bars are people or accounts; **lanes are transfers sized by amount**. Hovering isolates one party’s flows, and a click opens the dossier. A layering chain that takes an afternoon in spreadsheets is visible at once.'),
 ('Where it ended', '**End points show how much went abroad, in cash or at retail**, and recipients are ranked by the value traced to them, each with its typology flags. The officer checks whether a trail truly ends or simply stops at the chosen limits.'),
 ('An explained finding', 'The trace points to the exact accounts, transactions and dates; **every figure links back to its statement**, ready to be written into a report with its evidence.')],
 image='09-money',
 keys=['Onward to the end points, or back to the sources',
       'By person or by individual account',
       'Every figure linked to its bank statement']),

page('Examining a specific connection',
 'Pick any two people and ask **how they are connected**. Mosaic draws the network between them and spells out the chain of records that joins them.', [
 ('Begin with one subject', 'Choose a person to see their **associates, conduct flags and the evidence behind each association**: shared devices, accounts, money, calls, addresses and travel, each with its stated basis, so the officer can weigh how strong each association really is.'),
 ('Add the second person', 'Search for a second record, and Mosaic shows **the chain of records within the case’s reach**, such as ‘signatory of’, ‘sent money to’, ‘held by’, in three steps.'),
 ('Read each step', 'An ownership link, a transfer, a call and a shared address mean very different things. **Each step opens its records and dates**, so the officer judges the chain one link at a time.'),
 ('Conduct flags with context', 'Flags such as **directing a flagged company or repeated short trips to financial hubs** appear with the facts behind them, as reasons to look closer rather than labels attached to a person.'),
 ('A precise next step', 'The result is an explained connection: **which links are proven, the period they cover and what is still needed**, giving the team a clear route for follow-up and a paragraph that can go straight into a report.')],
 image='10-connect',
 keys=['The chain between any two people',
       'Associates with the evidence for each',
       'Conduct flags shown with their facts']),

page('Geographic and area investigation',
 'The map places the case where it happened. **Area search answers the question every investigator asks: who was there?**', [
 ('The case on a map', 'People, companies, money flows, relationships and travel, from a street to a free zone abroad. **Clusters open as you zoom**, and selecting anyone brings their money and relationships forward.'),
 ('Define the area and the time', 'Choose a toll plaza, camera, tower or point on the map, set a **radius and a period**, and write the reason, which is recorded with the case. The scope is explicit, so every reviewer knows exactly what was asked.'),
 ('Who was inside the circle', 'Mosaic lists **every vehicle read at a toll plaza or ANPR camera, every phone that used a tower inside the circle and every traveller booked from or to it**, with people already in an FIR flagged first.'),
 ('Presence is not residence', 'People registered as living in the area are **shown separately**, because an address does not place someone at the scene. Areas without camera or tower coverage are flagged, so an empty result is never misread.'),
 ('Keep watching the place', 'An area search can become a **watch**, so new presence in the same circle reaches the work queue, or be inserted into a report with its scope, its reason and its results, exactly as they were found.')],
 image='11-area-results',
 keys=['Vehicles, phones and travellers inside any circle',
       'Residents shown apart from people seen there',
       'Every area search recorded with its reason']),

page('Exploring the record collection',
 'The Explorer is for **searching and browsing every kind of record at once**, in any script, within what the role and case may see.', [
 ('Search every record type', 'Start from a name, number or category and narrow by type. Each result shows its **security marking**, and results the case may not see are counted as withheld, not silently dropped.'),
 ('Inspect any record', 'Choosing a record shows **its properties, the source of every value and its links**, so the officer can check what a source actually says before opening a dossier or analysis.'),
 ('Crime figures for police roles', 'Aggregate incident figures **by month, district, section of law and kind of offence**, where clicking any bar filters the rest: a fast route from a trend to the incidents behind it.'),
 ('Bring records into the case', 'A relevant record is **added to the case with a recorded reason**, and protected values are unmasked only with justification, keeping the case focused and its scope defensible.'),
 ('Save a search that keeps working', 'A useful search is **saved with its reason** and runs again by itself, so new matches reach the work queue without anyone having to remember to look.')],
 image='12-explore-results',
 keys=['All record types, any script, one search',
       'The source of every value, visible',
       'Crime trends by month, district and section']),

page('Preparing incoming information',
 'New material, such as a bank’s reply to a notice, is prepared in **Data studio**, in visible steps, **before anything reaches the shared records**.', [
 ('Know what arrived', 'Each extract is tied to the **case and the order it came under**. Profiling reads every column **from its values, not its header**, and shows the formats seen and how much any clean-up would change.'),
 ('Clean up in visible steps', 'Suggested steps remove placeholders and standardise names, PAN, phone numbers and dates. **Source rows are never touched**, every changed cell is listed, and **Aadhaar is masked on clean-up and never stored in full**.'),
 ('Map columns to records', 'A dataset becomes a type of record, a row a record, a column a property, and a column pointing to someone else **becomes a link**. Mosaic proposes the mapping; the officer corrects it in a click.'),
 ('Match rows to known people', 'Every row is labelled **on record, probable or new**, with the basis shown: the same account number, PAN or mobile. The reviewer sees how the intake would change existing records before anything is published.'),
 ('Read free text too', 'Seized diaries and letters are tagged for **accounts, phones, vehicles, amounts, dates and places**. A written name is tied to a person **only when an identifier on the same page confirms it**.')],
 image='13-studio-fields',
 keys=['Profile, clean, map and match in visible steps',
       'Source rows never touched; Aadhaar never stored in full',
       'Free text tagged and linked with care']),

page('Reviewing and publishing changes',
 'Publishing new data is a **separate decision by a second officer**. Data studio shows exactly what an intake would change, then freezes it for independent review.', [
 ('Checks with innocent explanations', 'Before publishing, Mosaic points out what deserves a second look, such as **one person with three accounts in an extract**, each with an ordinary explanation to consider. It also shows **the links the extract would add** and maps where its rows sit, so surprises are caught before they spread.'),
 ('See every change in advance', 'The Changes view counts **new records, gaps filled, values corroborated, conflicts and new spellings learned**. Existing values are never overwritten; a conflict is kept for a person to settle.'),
 ('A frozen, documented proposal', 'Submitting records the **legal order and the preparer’s note** and freezes the operations, so the supervisor reviews exactly what would be published, nothing more and nothing less, even if the extract changes later.'),
 ('A second officer approves', 'A supervisor of the case, **who is not the proposer**, reviews the proposal and approves or rejects it with a reason. **Nobody can approve their own intake.**'),
 ('Reversible and re-analysed', 'Approved changes go live with the order attached, and **can be reverted card by card** if a mistake is found. The pattern engine can then run again over the new records, so fresh leads appear the same day.')],
 image='13-studio-review',
 keys=['Every change counted before publication',
       'A different supervisor approves, with a reason',
       'Any publication can be reverted card by card']),

page('Reviewing uncertain identities',
 'When Mosaic is not sure two records describe the same person, **it asks a person**. Nothing is merged until someone decides, and every decision can be undone.', [
 ('A queue of doubtful pairs', 'Pairs that may be one person wait for review, each showing **how likely the match is**, so reviewers can work through the queue in a sensible order, the clearest cases first and the hardest given the most care.'),
 ('Side by side, in the original script', 'Both records appear together: **original script, father or spouse, birth year, gender and district**, so the reviewer compares the evidence, not just two similar names. **Nothing is lost in transliteration.**'),
 ('Why they were paired', 'Mosaic explains **what agrees, how strongly it counts and what differs**. **Common names count for less than rare ones**, and conflicting details are shown, never hidden.'),
 ('An explicit, recorded decision', 'The reviewer chooses **same person or different people**, with a reason. Opening a pair accepts nothing, and the reason lets another reviewer understand the call, and challenge it if new evidence arrives.'),
 ('Undo when the facts change', 'Identity links shape every dossier and network. **Every decision can be reversed** when better evidence arrives, keeping the record model honest and every dossier built on it trustworthy.')],
 image='14-review-pair',
 keys=['Nothing merged without a human decision',
       'Original scripts compared side by side',
       'Every match decision recorded and reversible']),

page('Face-search and candidate review',
 'Face search is **bound to the case and to a second officer**. A still becomes sealed evidence first; results are candidates, never identifications.', [
 ('Evidence before search', 'The officer adds the still with the **legal order or seizure memo** it came under. **It is sealed as case evidence before any face is read**, so every comparison traces back to a registered exhibit.'),
 ('One face, one reason', 'When a still holds several faces, the officer **chooses one and records why** it is being searched. If no face is found, a clearer image is needed. **One face per search** keeps every comparison specific and accountable.'),
 ('Candidates with their sources', 'Results show **similarity and the source of each photograph**, such as a bank’s KYC photo or an arrest record, for the officer to assess alongside other identity evidence.'),
 ('A second officer confirms', 'A match counts **only when another officer of the case confirms it with a reason**. The searching officer **can never confirm their own search**.'),
 ('A result that can be reviewed', 'The probe, the candidate, the reasons and the confirmation **stay linked in the case record**, so any later reviewer, supervisor or court can see exactly how an identification was reached, and by whom.')],
 image='15-faces-candidates',
 keys=['The still is sealed as evidence first',
       'Candidates, not identifications',
       'Only a second officer can confirm a match']),

page('Disaster-response operations',
 'For state control rooms, Mosaic brings **official alerts, affected districts, river gauges, hospitals and dispatches** into one shared operational picture.', [
 ('Alerts as they are issued', 'Official **NDMA SACHET** alerts for floods, cyclones, heavy rain and thunderstorms appear with their **sender, severity, effective and expiry times**, beside the map, updated as new alerts are ingested.'),
 ('Placed precisely', 'Each alert is mapped by **official district code, polygon, place name or river gauge**, and says which method was used. Alerts that cannot be placed stay in the list, never lost.'),
 ('Flood context', 'River gauges show **current level against warning and danger marks**, with district boundaries and nearby hospitals, so operators judge the threat and plan casualty care together.'),
 ('Dispatch and log', 'Record a resource, such as relief kits, with **quantity and destination district**. The dispatch log shows every operator what has already been sent, and where.'),
 ('One picture for the room', 'Everyone in the control room works from **the same view of what was issued, where it applies and what has been dispatched**, alongside the state’s established response procedures, so decisions are faster and nothing is sent twice.')],
 image='16-cop-flood',
 keys=['Official SACHET alerts on one map',
       'River levels against warning and danger marks',
       'Every dispatch logged for the whole room']),

page('Oversight, transparency and retention',
 'An **independent oversight officer** sees who accessed what, under which case and why, without ever seeing the case data itself.', [
 ('Every access, recorded', 'Each event shows **officer, time, action, case, purpose, records and outcome**. Filter by officer, or by person: **who looked at this person, and why?** Refused requests are recorded too.'),
 ('Insider-threat alerts', 'Bulk look-ups of personal records and the opening of **planted canary records** raise alerts for review against the officer’s stated purpose and duties. **Misuse is detected, not just discouraged.**'),
 ('A tamper-evident chain', 'The audit log is **hash-chained and cannot be edited**. The day’s root hash can be **sealed and published outside Mosaic**, so any later rewrite would show.'),
 ('Public transparency', 'Aggregate figures by action, outcome, purpose and source **can be read by anyone**, without exposing any investigative detail, as international oversight bodies recommend.'),
 ('Retention and legal holds', 'Cases due for deletion, scheduled and held are listed. **A legal hold keeps its own reason**, and every purge is recorded with its manifest, so data is kept exactly as long as the law allows.')],
 image='17-oversight',
 keys=['Who looked at this person, and why',
       'Hash-chained audit, root hash published outside',
       'Retention and legal holds tracked and recorded']),

page('Administration and source quality',
 'Administrators see **exactly how every detector works** and where incoming data needs correcting, so Mosaic’s results can always be explained.', [
 ('Every detector documented', 'The library describes each detector’s **question, method, records read, mission tracks and scope**, with its version, so any finding can be traced to the logic that produced it.'),
 ('Built to resist evasion', 'Documentation explains **how each detector stays effective against an adversary who knows it exists**, the ordinary activity that resembles it and its known blind spots.'),
 ('Nineteen detectors, one library', 'Burner SIM switches, **cloned number plates, convoys, hawala points, shell companies, smurfing, SIM-box gateways**, bid-rigging, disproportionate assets, precursor diversion, repeated reconnaissance and more.'),
 ('A source-quality register', 'Problems found while loading data are **listed against the record and source** that caused them, so stewards can report them to the owning agency and get them fixed at the source.'),
 ('The right remedy', 'A surprising result can come from data, configuration or logic. **Clear documentation and source references show which**, so the fix lands in the right place.')],
 image='18-admin-library',
 keys=['Every detector’s logic open to inspection',
       'How each resists deliberate evasion',
       'Source problems traced to their owner']),

# ------------------------------------------------------------------------------------------------ institutional operation
page('Access, deployment and integration',
 'Mosaic is **open, standards-based and built for government infrastructure**, from a single offline laptop at a police station to a state data centre serving thousands of officers.', [
 ('Sign-in and permissions', 'Officers sign in through **OpenID Connect**, with a ready Keycloak configuration and authenticator-app login. The institution maps its users, roles, agencies and case responsibilities to Mosaic’s access model, and **every access decision can be checked by Open Policy Agent**, with an identical built-in policy as standard.'),
 ('Controls where decisions happen', 'Access rules apply at the point of use: to records, to masked fields, to case work and to reviews. **Sensitive steps need a reason and a second officer.** An investigator, supervisor, data steward, administrator and oversight officer each do different work, and exploring a graph or changing a layout never creates extra authority.'),
 ('Open and portable', 'A **React and TypeScript** web application on a **Python FastAPI** service, running on **SQLite** in the field or **PostgreSQL** at state scale. The source is open under **Apache 2.0**, so agencies, auditors and courts can examine exactly how Mosaic works.'),
 ('Connected to India’s data', 'Records arrive through authorised extracts and configured connectors: FIRs, cyber complaints, bank KYC and statements, call records, FASTag and ANPR reads, travel, company and land registers. **Official LGD codes** cover every state and district, SACHET supplies disaster alerts, and maps use the **Survey of India or Bhuvan** basemap in deployment.'),
 ('Hardened by default', 'The audit log is protected by **database triggers that block any edit or deletion**, and its hash chain is verified on demand. Secrets are kept outside the code, demonstration sign-in answers only the local machine, and every request carries the acting officer and case, so **no screen, link or export works outside the rules**.'),
 ('Ready to run as an institution', 'A deployment plan names who supplies each source, who prepares and approves intakes, who resolves quality issues, how identities are provisioned, how releases are authorised and who performs oversight. **Mosaic provides the workflow for each of these responsibilities**, so the software and the institution work as one.')],
 visual='deployment', group='Institutional operation',
 quote='From one offline laptop to a whole state, **the same safeguards travel with the software**.',
 keys=['Single offline laptop to state data centre',
       'OpenID Connect sign-in; Open Policy Agent checks',
       'Open source under Apache 2.0']),

page('An investigation from start to finish',
 'This illustrative financial-crime enquiry shows **how the capabilities work together**, from the first extract to the court pack and the closed case.', [
 ('1  Establish and prepare', 'A team opens a case with its **purpose, legal basis and officers**. A bank’s reply to a notice is profiled, cleaned and mapped in Data studio; matches with existing account holders are checked; and **a different supervisor approves the intake**. The new records join the case, each with its source reference.'),
 ('2  Locate and understand', 'An officer searches the account holder and opens the dossier. Financials show the suspicious months; a **round-tripping alert** explains the pattern; the Network and Connections views reveal the **shell companies and the people who control them**. Each link is checked against its records before it becomes a lead.'),
 ('3  Test the explanation', '**Money trail follows the funds** to their end points, by party and by account. Calls, travel and an **area search** around a cash withdrawal add context. An uncertain identity goes to **match review**; a watch keeps the key suspects under notice as new records arrive.'),
 ('4  Coordinate and document', 'The lead moves across the leads board to **Action authorised by a supervisor**. Seized ledgers and statements are **sealed as exhibits** with fingerprints and custody history. The case diary combines selected records, links and exhibits with the officer’s narrative, ready for review.'),
 ('5  Close and keep the memory', 'A **court evidence pack** with its draft BSA s.63 certificate goes to the Special Court at the right clearance. The case is closed with its outcome; retention and legal holds take over; and the institution keeps **a complete, connected account** of what was examined, what was decided and why. Months later, a new officer, an auditor or a court can follow every step without asking anyone to remember it.')],
 visual='workflow', group='Institutional operation',
 quote='**Every step reviewed, recorded and linked**, from the first extract to the final judgement.',
 keys=['From a bank extract to a court evidence pack',
       'Every step reviewed, recorded and linked',
       'A complete institutional memory of the case']),
]

# Every illustrated workflow in the approved 88-screen reference has an owner.
def coverage_page(image):
    if image.startswith(('01-', '02-')): return 7
    if image.startswith('03-'):
        if 'evidence' in image: return 9
        if 'report' in image: return 10
        return 8
    if image.startswith('19-certificate'): return 9
    if image.startswith('19-report'): return 10
    prefix=image[:2]
    if prefix=='07': return 15 if image in ('07-network-analysis','07-network-community','07-network-money') else 14
    if prefix=='08': return 17 if image in ('08-dossier-financials','08-dossier-comms','08-dossier-assets','08-dossier-timeline') else 16
    if prefix=='13': return 23 if image in ('13-studio-checks','13-studio-changes','13-studio-proposed','13-studio-review','13-studio-published') else 22
    return {'04':11,'05':12,'06':13,'09':18,'10':19,'11':20,'12':21,'14':24,'15':25,'16':26,'17':27,'18':28}[prefix]

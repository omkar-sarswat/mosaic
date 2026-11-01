"""Mosaic product brochure: "The file on Mosaic".

A4 print-and-screen PDF in the world of an Indian government case file: a kraft jacket front and back, white noting
sheets inside with punch holes and a ruled margin, numbered paras, green-ink notings, violet stamps for every state,
screenshots as numbered enclosures, and index tabs A-G on the fore-edge.

    python build.py        # writes ../Mosaic-Brochure.pdf
"""
import html
import re
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
SHOTS = HERE.parent / "product-book" / "shots"
OUT = HERE.parent / "Mosaic-Brochure.pdf"
FILE_NO = "WW/MOSAIC/2026"


def uri(p):
    return Path(p).resolve().as_uri()


LOGO, KRAFT = uri(HERE / "brand/weirwood-logo-512.png"), uri(HERE / "brand/kraft-board.jpg")

SECTIONS = [  # flag letter, title
    ("A", "Who we are"),
    ("B", "Introducing Mosaic"),
    ("C", "Why you need Mosaic"),
    ("D", "What we deliver"),
    ("E", "Advantages"),
    ("F", "Capabilities"),
    ("G", "Technology"),
]
SEC = {s[0]: s for s in SECTIONS}


# ------------------------------------------------------------------------------------------------ parts
def lbl(en):
    return f'<span class="lbl">{en}</span>'


def typed(t):
    return f'<span class="typed">{t}</span>'


def stamp(text, sub="", rot=-5, cls=""):
    sub = f'<span class="st-sub">{sub}</span>' if sub else ""
    return f'<div class="stamp {cls}" style="--rot:{rot}deg"><span class="st-main">{text}</span>{sub}</div>'


def noting(text, rot=-2.2):
    return f'<p class="noting" style="--rot:{rot}deg">{text}</p>'


def paras(items, start=1, cls=""):
    out = []
    for i, (head, text) in enumerate(items, start):
        head = f'<span class="rh">{head}.</span> ' if head else ""
        out.append(f'<div class="para"><span class="pn">{i}.</span><p>{head}{text}</p></div>')
    return f'<div class="paras {cls}">{"".join(out)}</div>'


ENCL = [0]


SHOT_TEXT = {   # screenshot -> (caption title, explanation shown under the screen)
    "01-overview": ("The Mosaic workspace",
        "This is where an officer’s day begins. The work queue on the left lists everything that needs a decision, with its "
        "reference, status and the time it arrived. The active case stays on the right, with its legal basis, its people and a "
        "direct route to the case board, network, money trail and map."),
    "02-overview-supervisor": ("A supervisor’s queue",
        "A supervisor’s work queue lists the decisions waiting for them, here eleven: leads, watchlist activity and matches to "
        "confirm, each saying what happened and when it arrived. Approvals that need a second officer reach the supervisor here."),
    "01-open-case": ("Opening a case",
        "Every investigation in Mosaic starts as a case with a title, a lawful purpose and a legal basis, such as an FIR, ECIR "
        "or court order. Every look-up made afterwards is recorded against this case and its purpose, which is what makes the "
        "work accountable later."),
    "02-overview-crime": ("The work queue",
        "The work queue of a Police Inspector in a Crime Branch anti-extortion cell. New activity on watched people, leads "
        "proposed by the pattern engine and items awaiting review are listed in one place, each saying what happened, who it "
        "concerns and when. The active case, its people and its evidence sit alongside."),
    "01-search-script": ("Search in any script",
        "A name typed in Devanagari finds the same people recorded in English, with every spelling the records hold. Phones, "
        "accounts and assets that match appear in the same list, so one search covers every kind of record."),
    "01-search": ("Search by name",
        "Searching a surname returns 17 results grouped as people, phones and assets, each with its place. Choosing a result "
        "opens it inside the active case; records outside the officer’s access never appear."),
    "03-case-board": ("The case board",
        "The case board opens on the case’s legal basis and its key figures: records in the network, people, accounts, alerts "
        "and the money traced onward, abroad and withdrawn in cash. Below, suspects are ranked by the evidence that ties them to "
        "the money, and the destinations of the funds are listed with their amounts."),
    "03-case-suspect-open": ("Why a suspect ranks where they do",
        "Opening a suspect lists the facts behind the rank: each account, each cycle of transfers and each cash deposit, with "
        "amounts and dates. Every line comes from the records, and the rank is a lead for the investigating officer to test, "
        "not a finding."),
    "03-case-leads-board": ("The leads board",
        "Every lead moves across the board from proposal to investigating, awaiting approval, action authorised and closed. Only "
        "a supervisor can move a lead to Action authorised. The alerts raised in the case network and the case timeline sit "
        "below, so evidence and sequence stay together."),
    "08-dossier-overview": ("The dossier",
        "Everything the case may know about one person: name in English and in the original script, date of birth, address, "
        "rank in the case and identity documents. Aadhaar stays masked; each document shows whether its format is valid. From "
        "here the officer can follow the money, open the network or start a watch."),
    "08-dossier-financials": ("Financials",
        "Money in and out is charted month by month, then every transaction is listed with its amount, channel, counterparty "
        "and any flag. Unusual movements stand out against the person’s normal pattern."),
    "08-dossier-timeline": ("Timeline",
        "Every recorded event for the person in date order: transfers in and out with their channel and stated purpose, and "
        "journeys such as a Dubai to Mumbai flight with its booking reference. Months of activity read as one story."),
    "07-network": ("The case network",
        "The people, companies, accounts and phones around a case, and how they connect. Selecting a record opens it in the "
        "inspector on the right, and every line opens the evidence behind it. Links suggested by the machine are drawn apart "
        "from recorded ones."),
    "07-network-analysis": ("Network structure",
        "Structure analysis finds the groups in a network, the intermediaries who connect them and the weak points where a group "
        "would split. Each result lists its members, so an analyst can explain why a person matters."),
    "07-network-money": ("Money-flow layout",
        "The same network redrawn as money: from the start, through each hop, to the end points, with each band as wide as the "
        "amount it carries. Here funds move from a trading company through a commodities firm to accounts held by the main "
        "suspect."),
    "09-money": ("The money trail",
        "Funds are followed hop by hop from a starting point. The end points show how much ended abroad, in cash or at retail; "
        "recipients are ranked by the value traced to them, and accounts on the trail that carry alerts are flagged."),
    "10-connect": ("Connections",
        "Connections finds the chain of records between two people, step by step: shared phones, accounts, addresses or "
        "companies. Each step names the record that links them, so the chain can be checked and cited."),
    "09-money-accounts": ("Tracing by account",
        "Each account is followed on its own rather than merged with its holder’s other accounts. Here ₹12.30 crore from four "
        "accounts is traced to its end points, with every flagged account and its typology listed."),
    "11-area-results": ("Area search",
        "A circle and a period around a toll plaza, camera, tower or any point, and the list of who was inside: vehicles from "
        "toll and ANPR reads, phones and travellers. People already named in FIRs are listed first."),
    "11-globe": ("Across borders",
        "The case map can show money and relationships beyond India. Lines show flows between India and other countries, with "
        "counts on each cluster, so the foreign links of a case are visible at a glance."),
    "11-area-panel": ("Setting an area search",
        "Before a search runs, the officer sets the centre, the radius and the period, and writes the reason. The search will "
        "not run without a reason, and the reason is kept in the audit trail."),
    "04-leads-ncb": ("Pattern leads",
        "Leads for the Narcotics Control Bureau, filtered to its mission tracks. Each lead names its pattern, such as a successor "
        "SIM, a convoy or a precursor purchase, with its severity and when it was last seen. People appear only as Subject A or "
        "B until a case is opened."),
    "05-alerts": ("Financial alerts",
        "Each money-laundering typology found in the records, such as shell companies or rapid layering, is listed with its "
        "subject, amount and the finding in plain words. Selecting an alert shows the money path behind it."),
    "04-leads-ncb-request": ("Asking for a case",
        "To act on a lead, the officer asks for a case: the type of investigation, a title and the legal basis. A supervisor of "
        "the same agency who is not the requester must approve before any names are shown. A lead can also be dismissed, with "
        "the reason kept."),
    "04-leads-syndicate": ("Leads with their evidence",
        "Leads across every mission track, each with its pattern, severity and tracks. People stay pseudonymous, and the panel "
        "on the right shows the evidence behind the selected lead: phones, shared contacts and the period it covers."),
    "06-watchlist": ("The watchlist",
        "Each person, place and saved search the case is following, with its updates ranked as read first, worth a look or "
        "routine. Every update says what happened and which record it came from."),
    "12-explore-results": ("The Explorer",
        "The Explorer searches every record type in the agency’s authorised data. Results come with crime trends by month and "
        "by district, so an officer can see whether an incident belongs to a wider pattern."),
    "06-watch-dialog": ("Starting a watch",
        "Watching a person starts from the dossier. The officer must say why the person needs watching and how far back to "
        "include activity; the reason is recorded in the audit trail and shown to the case team."),
    "13-studio-fields": ("Mapping a new source",
        "A bank’s KYC extract is read column by column. Mosaic detects what each column holds and proposes the record field it "
        "maps to, and the data steward confirms every mapping before anything is proposed for publication."),
    "14-review-pair": ("Match review",
        "Two records that may describe the same person are set side by side, in their original scripts, with what agrees and "
        "what differs. A person decides, and the decision and its reason are recorded. Nothing is merged automatically."),
    "13-studio-matching": ("Matching to existing records",
        "Each incoming row is tied to people and accounts already on record, with the basis shown, such as the same account "
        "number and PAN. Here 123 of 143 rows matched existing records; new and doubtful rows go to review."),
    "03-report-editor": ("Writing the case diary",
        "Reports are written inside the case. The case diary inserts facts straight from the records, each carrying its source, "
        "so the report always matches the evidence."),
    "03-report-export": ("Exporting a report",
        "An export asks who the copy is for and at what clearance. Facts above the reader’s clearance are left out, and the copy "
        "carries its marking and a watermark naming the recipient."),
    "03-case-evidence": ("The evidence locker",
        "Each exhibit is recorded with its device, the legal order it was seized under and its SHA-256 fingerprint. Every view, "
        "download and verification is added to its custody chain, and exports for prosecution are made from here."),
    "19-certificate-page-1": ("Draft BSA s.63(4)(c) certificate",
        "The court evidence pack includes a draft certificate under section 63(4)(c) of the Bharatiya Sakshya Adhiniyam, filled "
        "from the exhibit’s details and hash values. Part A is for the party producing the record and Part B for the expert; "
        "both are verified and signed before filing."),
    "15-faces-candidates": ("Face-search candidates",
        "One face from a sealed still is compared with the photographs available to the case. Results are candidates, each with "
        "its similarity and the source of the photograph; a candidate is never an identification."),
    "15-faces-found": ("Choosing a face",
        "The still is first added to the case as evidence under its legal order. Then the officer chooses one face and writes "
        "why it is being searched; the reason stays in the audit log."),
    "15-faces-confirm": ("Second-officer confirmation",
        "Candidates wait in a queue for a second officer, who confirms or rejects each one with a reason. No officer can confirm "
        "a match from their own search."),
    "16-cop-flood": ("A flood alert",
        "An official CWC flood alert for the Bagmati at Benibad, with its sender, validity and affected district, the river "
        "level against its warning and danger marks, and the hospitals in the area."),
    "16-cop": ("Alerts across India",
        "SACHET alerts from IMD, CWC and state authorities are placed on the map by official district code, polygon or place "
        "name, so the control room sees every active warning at once."),
    "16-cop-dispatch": ("Dispatching relief",
        "From an alert, the control room sends relief: the resource, the quantity and the destination district. Each dispatch "
        "is logged and visible to the whole room."),
    "17-oversight": ("The oversight console",
        "An independent officer sees every access by officer, case, purpose and outcome, checks the hash-chained audit log and "
        "reviews insider-threat alerts such as bulk look-ups, without seeing case data."),
    "18-admin-library": ("The pattern library",
        "Each pattern detector is documented: the question it asks, how it works, the records it uses and its limits, so anyone "
        "reviewing a lead can see exactly why it was raised."),
    "17-transparency": ("The transparency report",
        "Aggregate figures published for anyone to read: actions by type, outcomes allowed and denied, and cases by purpose. "
        "The audit log itself stays readable only by the oversight officer."),
    "08-dossier-unmask": ("Unmasking a protected value",
        "Seeing a masked value, such as a full Aadhaar number, needs a written reason. The reason is recorded in the audit log "
        "and visible to oversight."),
}


def enclosure(name, cls="wide"):
    """A screenshot attached to the file as a numbered enclosure: always the whole screen, inside the main column, with its
    title above and its explanation below. Where a sheet is tight the build narrows it slightly (see main)."""
    ENCL[0] += 1
    title, explanation = SHOT_TEXT[name]
    return (f'<figure class="encl {cls}"><figcaption>{typed(f"Encl. {ENCL[0]}")}<span class="ecap">{title}</span></figcaption>'
            f'<div class="crop"><img src="{uri(SHOTS / (name + ".png"))}"></div><p class="eexp">{explanation}</p></figure>')


def row(margin, main, cls=""):
    return f'<div class="row {cls}"><aside class="m">{margin}</aside><div class="c">{main}</div></div>'


# ------------------------------------------------------------------------------------------------ pages
PAGES = []      # dicts: kind, sec, body, start


def sheet(sec, body, start=False):
    PAGES.append(dict(kind="sheet", sec=sec, body=body, start=start))


def divider(sec, question):
    """A kraft divider leaf in front of each flag: its cut tab, a pasted label with the flag's title, the question
    the flag answers and what it contains."""
    PAGES.append(dict(kind="divider", sec=sec, start=True, question=question))


def signoff():
    return f"""<div class="signoff"><p class="sign">For Weirwood</p>
          <div>{typed("Product team, Weirwood")}</div><div>{lbl("Date")} {typed("22.10.2026")}</div></div>"""


def jacket(body, cls):
    PAGES.append(dict(kind="jacket", sec=None, body=body, cls=cls))


def heading(text, lead=""):
    lead = f'<p class="lead">{lead}</p>' if lead else ""
    return f'<h2 class="title">{text}</h2>{lead}'


def seal(key, cls=""):
    """Weirwood's round company seal, in violet stamp ink."""
    return f"""<svg class="seal {cls}" viewBox="0 0 100 100" aria-hidden="true">
  <defs><path id="seal-top-{key}" d="M15 50a35 35 0 1 1 70 0"/><path id="seal-bot-{key}" d="M9 50a41 41 0 0 0 82 0"/></defs>
  <circle cx="50" cy="50" r="47.5" fill="none" stroke="currentColor" stroke-width="2"/>
  <circle cx="50" cy="50" r="44.2" fill="none" stroke="currentColor" stroke-width=".7"/>
  <circle cx="50" cy="50" r="28" fill="none" stroke="currentColor" stroke-width=".7"/>
  <text class="ring"><textPath href="#seal-top-{key}" startOffset="50%" text-anchor="middle">WEIRWOOD · INDIA</textPath></text>
  <text class="ring"><textPath href="#seal-bot-{key}" startOffset="50%" text-anchor="middle">PRODUCT FILE · 2026</textPath></text>
  <text class="core" x="50" y="54" text-anchor="middle">MOSAIC</text>
</svg>"""


# 1 cover -----------------------------------------------------------------------------------------
jacket(f"""
<div class="jk-top">
  <div class="jk-org"><img src="{LOGO}"><span>WEIRWOOD</span></div>
  <div class="jk-fileno">{lbl("File no.")}{typed(FILE_NO)}</div>
</div>
<div class="jk-subject">
  <div class="jk-sublbl">{lbl("Subject")}</div>
  <div class="jk-subval"><div class="jk-title">Mosaic</div>
  <p class="jk-typed">Investigation and intelligence platform for India’s police, investigation, intelligence and disaster-management agencies.</p></div>
</div>
<div class="tape"></div>
<div class="jk-rows">
  <div>{lbl("Issued by")}{typed("Weirwood")}</div>
  <div>{lbl("Purpose")}{typed("Product brochure")}</div>
  <div>{lbl("Edition")}{typed("2026")}</div>
</div>
{seal("front")}""", "cover")

# 2 note and index ----------------------------------------------------------------------------------
INDEX_SLOT = "__INDEX__"
sheet(None, row(noting("Read the flags in order; each one answers a question an agency will ask.", -3),
                heading("A note on this file",
                        "This file introduces Weirwood and Mosaic, our investigation and intelligence platform, to everyone who "
                        "will decide on it, use it or hold it to account.")
                + paras([
                    ("", "It explains who we are, what Mosaic is, why agencies need it, what we deliver to government, why "
                         "agencies choose it, and then each capability in turn, with the product’s own screens attached as enclosures."),
                    ("In brief", "The records an investigation needs sit in many systems, under many names, and are still "
                                 "joined by hand. Mosaic connects them into one picture, raises leads with their evidence and "
                                 "records every step, so investigations are faster, better founded and able to stand up in "
                                 "court and before oversight."),
                    ("", "Every person, number, account, company and case in the enclosures is synthetic, created for "
                         "demonstration."),
                ]))
      + row("", INDEX_SLOT)
      + row("", signoff()))

# A who we are ------------------------------------------------------------------------------------
divider("A", "Who is Weirwood, and why trust it with this work?")
sheet("A", row(noting("An Indian company, built for India’s institutions.", -2.5),
               heading("We help the people who protect India see the whole picture.",
                       "Weirwood is an Indian technology company. We build investigation and intelligence software for "
                       "government, defence and police agencies, designed around India’s laws, languages and institutions."))
      + row("", paras([
          ("Why we exist", "Every serious investigation depends on information that sits in many places: police records, "
                           "bank statements, call records, travel bookings, company registers and the evidence officers "
                           "collect in the field. Weirwood exists to bring that information together, so officers spend "
                           "their time on judgement rather than on assembling files."),
          ("How we build", "To the standard public institutions must meet: every action tied to a lawful purpose, every "
                           "decision recorded, every fact traceable to its source."),
      ], start=1))
      + row(noting("Particulars of the company.", -2), "<h3>Company particulars</h3>" + f"""<div class="form particulars">
          <div class="fr">{lbl("Name")}<p>Weirwood</p></div>
          <div class="fr">{lbl("Nature")}<p>Indian technology company</p></div>
          <div class="fr">{lbl("Product")}<p>Mosaic, an investigation and intelligence platform</p></div>
          <div class="fr">{lbl("Serves")}<p>Police, investigation, intelligence and disaster-management agencies</p></div>
          <div class="fr">{lbl("Mission")}<p>Give every officer the full picture in minutes, with every step accountable.</p></div>
          <div class="fr">{lbl("Commitment")}<p>Powerful tools, built with safeguards that earn public trust.</p></div>
          <div class="fr">{lbl("Licence")}<p>Open source, Apache 2.0</p></div></div>"""),
      start=True)

MARK_ARROWS = ('<svg class="annos" viewBox="0 0 142 86" aria-hidden="true">'
               '<path d="M37 55c6-1 10-4 13-9"/><path d="M47.6 44.4l2.6 1.4.4 3"/>'
               '<path d="M106 21c-6-2-11-1-15 3"/><path d="M93.6 21.6l-2.8 2.6 2.4 2.2"/></svg>')
sheet("A", row(noting("Every tile is a record; the picture is the case.", -3),
               heading("A name and a mark with a purpose."))
      + row("", f"""<div class="markspec"><img src="{LOGO}">{MARK_ARROWS}
          <p class="anno a1">six tiles, six pieces of information</p>
          <p class="anno a2">one red tile: the lead that breaks the case</p></div>""")
      + row("", paras([
                   ("The name", "In a well-known story, a weirwood is an ancient tree through which one can see everything "
                                "that happens across the land, past and present. It stands for what our software gives an "
                                "investigator: sight across every record that matters."),
                   ("The mark", "A tree built from six tiles. Each tile is one piece of information; one tile is red, the "
                                "piece of evidence that breaks a case open. The product is named Mosaic for the same reason: "
                                "intelligence work has long followed the mosaic method, fitting small pieces together until the "
                                "whole picture appears."),
               ]))
      + row(noting("These four decide every design choice.", 2), "<h3>The principles we build by</h3>" + paras([
          ("See the whole picture", "Bring every authorised source into one view, so nothing important is lost between departments."),
          ("A person always decides", "The software proposes; officers decide. Every lead, match and approval is a human act, recorded."),
          ("Safeguards come first", "Purpose, case scope, masking and audit are designed in from the first line of code."),
          ("Built for India", "Indian scripts, Indian laws, Indian identifiers and Indian institutions, from the ground up."),
      ], start=3)))

# B introducing mosaic ------------------------------------------------------------------------------
divider("B", "What is Mosaic, and what does it do?")
LEADERS = "".join(f'<div class="lr"><span>{k}</span><i></i>{typed(v)}</div>' for k, v in [
    ("Integrated modules", "17"), ("Types of records connected", "23"), ("Pattern detectors, written around Indian law", "19"),
    ("Money-laundering typologies", "16"), ("Scripts understood, eight Indian and English", "9"), ("Agency mission tracks", "8")])
sheet("B", row(noting("From one name or number to the whole case.", -2.5),
               heading("One platform for every investigation.",
                       "Mosaic connects an agency’s authorised records into one picture of people, money, phones, places and "
                       "events, and carries every finding from the first search to the court-ready report."))
      + row(stamp("Synthetic records", "for demonstration", -4, "corner"),
            enclosure("01-overview", "wide"))
      + row(noting("Particulars of the platform.", -2), f'<h3>Mosaic at a glance</h3><div class="form leaders">{LEADERS}</div>'),
      start=True)

sheet("B", row(noting("Six capabilities, one file.", 2.5), heading("What Mosaic does.") + paras([
          ("Connect", "Brings in FIRs, bank statements, call records, travel, registries and seized documents, cleaned and approved before they enter."),
          ("Resolve", "Recognises the same person across scripts, spellings and changed numbers, and shows the reasons."),
          ("Investigate", "Dossiers, networks, money trails, maps and timelines: the case laid out the way investigators think."),
          ("Detect", "Pattern detectors built on Indian law raise leads with their evidence, for the agency that owns the mission."),
          ("Account", "Every look-up tied to a case and its lawful purpose, in a tamper-evident record."),
          ("Deliver", "Sealed evidence, case diaries and court packs with a draft BSA s.63 certificate, in one step."),
      ]))
      + row(noting("Every look-up is tied to a case and its purpose.", -2),
            enclosure("01-open-case", "wide")))

# C why you need mosaic -----------------------------------------------------------------------------
divider("C", "Why does an agency need it now?")
def exhibit_names():
    """An authored enclosure: one synthetic person as six source systems record the name."""
    ENCL[0] += 1
    slips = [
        ("FIR register", "Nitin Ramesh Salunkhe", "Accused, PS Kondhwa"),
        ("Bank KYC", "N R SALUNKHE", "Savings account ending 4471"),
        ("Call records", "Nitin Salunke", "Subscriber, prepaid SIM"),
        ("Rail reservation", "SALUNKHE NITIN", "Pune to Patna, sleeper"),
        ("Company register", "NITIN R SALUNKHE", "Director of two companies"),
        ("Vehicle register", "Salunke N. R.", "Owner of a two-wheeler"),
    ]
    cards = "".join(f'<div class="slip" style="--rot:{r}deg">{lbl(en)}<p class="slip-name">{typed(name)}</p>'
                    f'<p class="slip-note">{note}</p></div>'
                    for (en, name, note), r in zip(slips, [-.7, .5, -.3, .6, -.5, .4]))
    return (f'<figure class="encl exhibit"><figcaption>{typed(f"Encl. {ENCL[0]}")}<span class="ecap">One person, as six '
            f'systems record the name. A synthetic example.</span></figcaption><div class="slips">{cards}</div></figure>')



sheet("C", row(noting("Every agency holds the records; nobody sees them together.", -2.5),
               heading("Why agencies need Mosaic.",
                       "Agencies hold more data than ever. Yet the records an investigation needs sit in different systems, in "
                       "different formats, under different names, and joining them still happens by hand."))
      + row("", paras([
          ("Records in silos", "FIRs, bank replies, call records, toll reads and registries each arrive from a different office, in a different format."),
          ("One person, many names", "The same suspect appears in Devanagari, Urdu and English, with initials and changed numbers."),
          ("Patterns between sources", "Mule networks, burner phones and convoys appear only when money, calls and movement are seen together."),
          ("Time works against you", "While files are assembled by hand, money moves abroad and suspects change numbers."),
          ("Every step must stand up", "Courts and oversight bodies ask why each record was opened, by whom, and under which order."),
          ("Conclusions without reasons", "Findings passed between officers lose the records and reasoning that support them."),
      ]))
      + row(noting("Same person? Today an officer decides by eye, one file at a time.", -3), exhibit_names()), start=True)

sheet("C", row(noting("The same eight tasks, done in one place.", -2.5),
               heading("Before and after Mosaic.",
                       "What changes for an investigating team when every record, decision and piece of evidence lives in one platform."))
      + row("", f"""<table class="register compare">
<thead><tr><th>{lbl("Task")}</th><th>{lbl("As it stands")}</th><th>{lbl("With Mosaic")}</th></tr></thead><tbody>
<tr><td>Gathering records</td><td>Letters to each department; spreadsheets assembled by hand</td><td>Authorised sources prepared once and shared by the whole case</td></tr>
<tr><td>Identifying people</td><td>Names compared by eye across scripts and spellings</td><td>Cross-script matching, with every doubtful case decided by a person</td></tr>
<tr><td>Finding connections</td><td>Links found by chance, if at all</td><td>Networks, paths and shared records shown with their evidence</td></tr>
<tr><td>Following money</td><td>Bank statements traced line by line</td><td>Funds traced hop by hop to their end points</td></tr>
<tr><td>Spotting patterns</td><td>Depends on an officer remembering a similar case</td><td>19 detectors and 16 typologies at work continuously</td></tr>
<tr><td>Handling evidence</td><td>Files copied between folders and drives</td><td>Sealed on arrival, with a fingerprint and custody history</td></tr>
<tr><td>Writing reports</td><td>Facts retyped; reports drift from the evidence</td><td>Facts inserted from the case, each with its source</td></tr>
<tr><td>Oversight</td><td>Access rarely recorded; reviews reconstruct events</td><td>Every look-up recorded in a tamper-evident trail</td></tr>
</tbody></table>"""))

# D what we deliver ---------------------------------------------------------------------------------
divider("D", "What exactly does the agency receive?")
sheet("D", row(noting("Installed, configured, trained and supported.", -2.5),
               heading("A complete platform, delivered and supported.",
                       "Weirwood delivers Mosaic as a working capability for the agency, from installation and data "
                       "onboarding to training, governance and continuing support."))
      + row("", paras([
          ("The Mosaic platform", "All seventeen modules: workspace, cases, leads, alerts, watchlist, explorer, network, dossier, money trail, connections, map, data studio, match review, face search, disaster map, oversight and administration."),
          ("Deployment on your terms", "On a single offline laptop, in a district office or in a state data centre, on the agency’s own infrastructure."),
          ("Data onboarding", "The agency’s sources mapped into Mosaic through the data studio, every intake reviewed and approved by its own officers."),
          ("Governance set-up", "Roles, agencies, lawful purposes, approvals and oversight configured to the institution’s rules."),
          ("Training", "Hands-on training for investigating officers, supervisors, analysts, data stewards and oversight officers."),
          ("Support and updates", "Continuing support, improvements and new detectors as crime patterns and laws evolve."),
      ]))
      + row(noting("Every role, one application.", 2), "<h3>Every role, one application</h3>" + paras([
          ("Investigating officers", "Search, follow leads, seal evidence and write the case diary."),
          ("Supervisors", "Approve cases, publications and matches as the second officer."),
          ("Analysts", "Work across networks, money trails and patterns."),
          ("Oversight officers", "Review who saw what, and why, without seeing case data."),
      ], start=7)), start=True)

sheet("D", row(noting("Each agency sees only its own mission.", -2.5),
               heading("Built for every agency.",
                       "One platform serves very different missions from the same foundation, with access separated by agency, role and case."))
      + row("", f"""<table class="register agencies">
<thead><tr><th>{lbl("Agency")}</th><th>{lbl("Mission")}</th></tr></thead><tbody>
<tr><td>State police and crime branches</td><td>Gangs, organised crime, arms, vehicle-theft rings and kidnapping, from FIR to charge-sheet</td></tr>
<tr><td>State cyber cells</td><td>Cyber fraud and mule-account networks, from complaint to cash-out</td></tr>
<tr><td>National Investigation Agency</td><td>Terror, terror financing and explosives, across states and borders</td></tr>
<tr><td>Narcotics Control Bureau</td><td>Narcotics, precursor diversion, couriers and convoy vehicles</td></tr>
<tr><td>Central Bureau of Investigation</td><td>Corruption, tender rigging and assets disproportionate to income</td></tr>
<tr><td>Enforcement Directorate</td><td>Money laundering, hawala routes and shell-company networks</td></tr>
<tr><td>Intelligence Bureau</td><td>Internal-security network mapping</td></tr>
<tr><td>Research and Analysis Wing</td><td>Cross-border handlers, money and travel</td></tr>
<tr><td>State disaster-management authorities</td><td>Alerts, affected districts, hospitals and relief dispatch</td></tr>
</tbody></table>"""))

# E advantages --------------------------------------------------------------------------------------
divider("E", "Why choose Mosaic over the way things are done today?")
sheet("E", row(noting("Power and discipline in the same tool.", -2.5),
               heading("Why agencies choose Mosaic.",
                       "Mosaic combines the analytical power investigators need with the discipline public institutions require."))
      + row("", paras([
          ("Built for India", "Eight Indian scripts and English, Indian identifiers, official LGD codes, and detectors written around BNS, PMLA and NDPS."),
          ("Safeguards built in", "Purpose-bound cases, two-officer approvals, masked identifiers and a tamper-evident audit trail."),
          ("Evidence with every lead", "Every lead and match shows its evidence and its innocent explanations. No person is ever scored."),
          ("Court-ready by design", "Sealed exhibits, custody chains and a draft BSA s.63 certificate, produced in one step."),
          ("Runs anywhere", "Fully offline on a laptop in the field, or at state scale in a government data centre."),
          ("Open and auditable", "Open source under Apache 2.0, so agencies, auditors and courts can examine exactly how it works."),
      ]))
      + row(noting("A lead is a question for an officer to answer.", -2.5),
            enclosure("04-leads-syndicate", "wide")),
      start=True)

sheet("E", row(noting("Every decision has a name and a reason.", -2.5),
               heading("Safeguards built into every step.",
                       "Mosaic is designed so that the most powerful investigative tools are also the most accountable."))
      + row("", paras([
          ("Purpose-bound access", "Every case states its lawful purpose; the purpose decides which records its officers may read."),
          ("Two-officer approval", "Opening cases from leads, publishing data and confirming face matches always need a second officer."),
          ("Masked by default", "Aadhaar is never stored in full. Seeing a protected value needs a written, recorded reason."),
          ("Tamper-evident audit", "Every view, search and action enters a hash-chained log that cannot be edited."),
          ("Insider-threat alarms", "Bulk look-ups and planted canary records alert an independent oversight officer."),
          ("Retention and legal hold", "Closing a case sets when its data must be let go; a legal hold stops the clock."),
      ]))
      + row(stamp("Red lines", "will not be crossed", -3, "corner"), paras([
          ("Red lines", "Mosaic has no purpose for watching journalists, activists, protesters, political opponents or "
                        "religious groups, and refuses to open such a case."),
      ], start=7))
      + row(noting("Unmasking needs a written reason.", -2.5),
            enclosure("08-dossier-unmask", "wide")))

# F capabilities ------------------------------------------------------------------------------------
divider("F", "What does Mosaic do, screen by screen?")
CAPS = []      # (title, page number) filled as pages are added


THIRD = {   # the second screen on each capability's continuation sheet
    "Workspace and search": "01-search",
    "Cases and leads board": "03-case-leads-board",
    "Entity dossiers": "08-dossier-timeline",
    "Network analysis": "07-network-money",
    "Money trail and connections": "09-money-accounts",
    "Map and area search": "11-area-panel",
    "Pattern leads and alerts": "04-leads-ncb-request",
    "Watchlist and explorer": "06-watch-dialog",
    "Data studio and record matching": "13-studio-matching",
    "Evidence and court-ready reports": "03-case-evidence",
    "Face search": "15-faces-confirm",
    "Disaster operations": "16-cop-dispatch",
    "Oversight and administration": "17-transparency",
}


def capability(title, promise, shot, items, note, second, mark=None):
    """Two sheets per capability, every screen whole and at full width: the promise, the main screen and the numbered
    paras; then a continuation sheet carrying two more screens."""
    CAPS.append((title, len(PAGES) + 1, ENCL[0] + 1))
    sheet("F", row(noting(note, -2.4), heading(title, promise))
          + row("", enclosure(shot))
          + row(mark or "", paras(items)))
    sheet("F", row("", f'<p class="contd">{title} {typed("contd.")}</p>')
          + row("", enclosure(second))
          + row("", enclosure(THIRD[title])))


capability("Workspace and search",
           "Every day starts in one place: the officer’s work queue, inside the active case, with search one keystroke away.",
           "02-overview-crime", [
               ("The case comes first", "The active case, its purpose and legal basis are always on screen."),
               ("One work queue", "Leads, watched activity, requests and approvals in one prioritised list."),
               ("Search in any script", "Ctrl + K finds any name, phone, PAN, account, vehicle or case number."),
               ("Access by role", "Each officer sees only the screens and records their role allows."),
           ], "Fewest steps for the officer in the field.",
           "01-search-script")
capability("Cases and leads board",
           "A case board that builds itself from the case records, ranks suspects by evidence and tracks every lead to a decision.",
           "03-case-board", [
               ("Suspects ranked by evidence", "Money, calls, directorships and shared handsets, every rank explained."),
               ("Where the money went", "Destinations, sources and the amounts sent abroad or withdrawn in cash."),
               ("Leads to decisions", "A lead moves to Action authorised only with a supervisor’s approval."),
               ("Close with a clear trail", "Outcome, retention and legal hold are all recorded."),
           ], "No step rests on one officer’s word.",
           "03-case-suspect-open",
           stamp("Action authorised", "supervisor", -6, "corner"))
capability("Entity dossiers",
           "Everything the case may know about one person, on one page, with the source of every fact.",
           "08-dossier-overview", [
               ("Identity at a glance", "Name in English and in its original script, documents, address and role in the case."),
               ("Protected by default", "Aadhaar masked; unmasking needs a recorded reason."),
               ("Money, calls and travel", "Accounts, transactions, top contacts, trips and assets in dedicated tabs."),
               ("Every fact sourced", "The system, record and arrival time behind every value."),
           ], "The whole person, with every source.",
           "08-dossier-financials")
capability("Network analysis",
           "See how people, accounts, phones and companies connect, and why, with every link opening its records.",
           "07-network", [
               ("Six layouts", "Structure, money flow, by type, by community, neighbourhood and free-form."),
               ("Find the go-betweens", "Groups, intermediaries, weak points and loops, in one step."),
               ("Paths between records", "Shortest, alternative, directed and money-only routes."),
               ("Recorded or inferred", "Machine-suggested links are always drawn apart from recorded ones."),
           ], "Every line opens the records behind it.",
           "07-network-analysis")
capability("Money trail and connections",
           "Follow funds hop by hop to their end points, and find the chain of records between any two people.",
           "09-money", [
               ("Onward or back to source", "Trace where money went, or where it came from, hop by hop."),
               ("By party or by account", "Combine a person’s accounts, or keep each instrument apart."),
               ("End points", "How much ended abroad, in cash or at retail, with ranked recipients."),
               ("Connections", "The chain between two people, step by step, with its evidence."),
           ], "Every figure links back to its statement.",
           "10-connect")
capability("Map and area search",
           "Place the case on the map, and answer the question every investigator asks: who was there?",
           "11-area-results", [
               ("The case on a map", "People, companies, money flows, relationships and travel."),
               ("Search any area", "A radius and a period around a toll plaza, camera, tower or point."),
               ("Who was inside", "Vehicles, phones and travellers, with people in FIRs first."),
               ("Keep watching", "An area search becomes a watch that reports new presence."),
           ], "Who was there, and when.",
           "11-globe")
capability("Pattern leads and alerts",
           "Nineteen detectors and sixteen laundering typologies watch the records and explain every finding.",
           "04-leads-ncb", [
               ("19 pattern detectors", "Burner SIMs, convoys, hawala points, handset sharing, precursor diversion and more."),
               ("Pseudonymous leads", "Names stay hidden until two officers of the agency open a case."),
               ("16 laundering typologies", "Shell companies, round-tripping, mule accounts and cash structuring."),
               ("Evidence with every alert", "The exact accounts, amounts, dates and path, in plain words."),
           ], "Each lead arrives with its evidence.",
           "05-alerts")
capability("Watchlist and explorer",
           "Follow people, numbers and places, and keep useful searches running for the case.",
           "06-watchlist", [
               ("Watch anything", "People, phones, vehicles, accounts and places, each with a reason."),
               ("Read what matters first", "Updates ranked: read first, worth a look and routine."),
               ("Searches that keep running", "Saved searches report new results to the work queue."),
               ("Explore all records", "Every record type, with crime trends by month and district."),
           ], "Every watch starts and ends with a reason.",
           "12-explore-results")
capability("Data studio and record matching",
           "New records come in safely: profiled, cleaned, matched and approved by a second officer before publication.",
           "13-studio-fields", [
               ("Profile and clean", "Every column read from its values, cleaned in visible steps."),
               ("Map and match", "Columns mapped to records; rows matched to people already known."),
               ("Second-officer approval", "A different supervisor approves every publication."),
               ("Human match review", "Doubtful identities decided by a person, side by side."),
           ], "Nothing enters the record unseen.",
           "14-review-pair",
           stamp("Approved", "second officer", -5, "corner"))
capability("Evidence and court-ready reports",
           "Evidence is sealed on arrival and keeps its custody chain; reports are written from the facts and always match them.",
           "03-report-editor", [
               ("Sealed on arrival", "SHA-256 fingerprint, write-once storage and device details."),
               ("Custody chain", "Every view, download and verification recorded automatically."),
               ("Reports from the facts", "Case diary, charge-sheet annexure and intelligence summary."),
               ("Court evidence pack", "Exhibits, custody, manifest and a draft BSA s.63(4) certificate."),
           ], "Fit for the court from the first upload.",
           "03-report-export",
           stamp("Sealed", "SHA-256", -6, "corner"))
sheet("F", row("", f'<p class="contd">Evidence and court-ready reports {typed("contd.")}</p>')
      + row("", enclosure("19-certificate-page-1", "doc")))
capability("Face search",
           "A case-bound face search: the still is sealed as evidence first, and only a second officer can confirm a match.",
           "15-faces-candidates", [
               ("Evidence before search", "The still is sealed under its legal order before any face is read."),
               ("One face, one reason", "Each search is specific, and its reason recorded."),
               ("Candidates only", "Similarity and the source of every photograph."),
               ("Second-officer confirmation", "No one can confirm their own search."),
           ], "Every comparison traces back to a sealed exhibit.",
           "15-faces-found",
           stamp("Confirmation", "by second officer", -5, "corner"))
capability("Disaster operations",
           "One operational picture for the state control room, from the official alert to the dispatch log.",
           "16-cop-flood", [
               ("Official alerts", "NDMA SACHET alerts with sender, severity and validity."),
               ("Mapped precisely", "By district code, polygon, place name or river gauge."),
               ("Flood context", "River levels against warning and danger marks."),
               ("Dispatch log", "Resources, quantities and destinations, visible to the whole room."),
           ], "One picture for the whole control room.",
           "16-cop")
capability("Oversight and administration",
           "Independent oversight of who saw what and why, and an open record of how every detector works.",
           "17-oversight", [
               ("Who looked, and why", "Every access by officer, case, purpose and outcome."),
               ("Tamper-evident chain", "A hash-chained log, with the daily root hash sealed."),
               ("Insider-threat alerts", "Bulk look-ups and canary records flagged for review."),
               ("Documented detectors", "Each detector’s question, method, inputs and limits."),
           ], "Every access is visible to oversight.",
           "18-admin-library",
           stamp("Audited", "hash-chained", -5, "corner"))

# G technology --------------------------------------------------------------------------------------
divider("G", "What is it built on, and where does it run?")
ARROW = '<svg viewBox="0 0 40 12"><path d="M0 6h36M30 1l6 5-6 5" fill="none" stroke="currentColor" stroke-width="1.2"/></svg>'
sheet("G", row(noting("The same safeguards travel with the software.", -2.5),
               heading("Open, standards-based and ready for government infrastructure.",
                       "From a single offline laptop at a police station to a state data centre serving thousands of officers."))
      + row("", f"""<div class="arch">
  <div class="a-col"><div class="a-h">Sources</div><div class="a-i">FIRs and complaints</div><div class="a-i">Bank KYC and statements</div><div class="a-i">Call records</div><div class="a-i">FASTag and ANPR reads</div><div class="a-i">Travel, company and land registers</div><div class="a-i">Disaster alerts</div></div>
  <div class="a-arrow">{ARROW}</div>
  <div class="a-core"><div class="a-h">Mosaic</div><div class="a-blk">Data studio and record matching</div><div class="a-blk">Connected record model</div><div class="a-blk">Pattern engine</div><div class="a-blk">Investigation workspace</div><div class="a-guard">Access policy, masking and audit chain around every request</div></div>
  <div class="a-arrow">{ARROW}</div>
  <div class="a-col"><div class="a-h">Users</div><div class="a-i">Investigating officers</div><div class="a-i">Supervisors</div><div class="a-i">Analysts</div><div class="a-i">Data stewards</div><div class="a-i">Oversight officers</div><div class="a-i">Control-room operators</div></div>
</div>""")
      + row("", paras([
          ("Open technology", "A React and TypeScript web application on a Python FastAPI service, open source under Apache 2.0."),
          ("Your choice of database", "SQLite for offline field use; PostgreSQL for state-scale deployments."),
          ("Government sign-in", "OpenID Connect with Keycloak and authenticator-app login; every access decision can be checked by Open Policy Agent."),
          ("Indian geography", "Official LGD codes for every state and district, and the Survey of India or Bhuvan basemap in deployment."),
      ]))
      + row(noting("End of file. A demonstration request follows.", -2), signoff()), start=True)

# back cover ----------------------------------------------------------------------------------------
jacket(f"""
<div class="jk-top"><div class="jk-org"><img src="{LOGO}"><span>WEIRWOOD</span></div>
  <div class="jk-fileno">{lbl("File no.")}{typed(FILE_NO)}</div></div>
<div class="tape back"></div>
<div class="request">
  <h2>Request a demonstration</h2>
  <p class="req-lead">See Mosaic at work on your agency’s questions, with your own officers at the controls.</p>
</div>
<div class="about"><p><b>Weirwood</b> is an Indian technology company. It builds investigation and intelligence software for
the institutions that protect India.</p><p><b>Mosaic</b>, its platform, connects an agency’s authorised records into one
accountable picture, from the first search to the court-ready report.</p></div>
<div class="jk-foot"><span>Weirwood · Mosaic product brochure · Edition 2026</span><span>All records shown in this brochure are synthetic, created for demonstration.</span></div>""", "back")


# ------------------------------------------------------------------------------------------------ assembly
def first_page_of(sec):
    return next(i for i, p in enumerate(PAGES, 1) if p.get("sec") == sec and p.get("start"))


def tabs(current):
    out = []
    for i, (letter, en) in enumerate(SECTIONS):
        on = " on" if letter == current else ""
        out.append(f'<a class="tab{on}" href="#p{first_page_of(letter)}" style="top:{34 + i * 33}mm"><b>{letter}</b><span>{en}</span></a>')
    return f'<nav class="tabs">{"".join(out)}</nav>'


def index_table():
    rows = "".join(f'<tr><td>{typed("Flag " + l)}</td><td>{en}</td><td>{typed(f"{first_page_of(l):02d}")}</td></tr>'
                   for l, en in SECTIONS)
    return f'<h3>Flags in this file</h3><table class="index"><tbody>{rows}</tbody></table>'


def flag_contents(letter):
    """What a flag holds: the capability enclosures for F, the sheet titles for every other flag."""
    if letter == "F":
        rows = "".join(f'<tr><td>{typed(f"Encl. {e}")}</td><td>{t}</td><td>{typed(f"{p:02d}")}</td></tr>' for t, p, e in CAPS)
        return f'<table class="index contents"><tbody>{rows}</tbody></table>'
    rows = "".join(f'<tr><td>{re.search(r"<h2 class=.title.>(.*?)</h2>", p["body"]).group(1).rstrip(".")}</td><td>{typed(f"{n:02d}")}</td></tr>'
                   for n, p in enumerate(PAGES, 1) if p["kind"] == "sheet" and p["sec"] == letter)
    return f'<table class="index contents two"><tbody>{rows}</tbody></table>'


def render_divider(n, p):
    letter, en = SEC[p["sec"]]
    step = [s[0] for s in SECTIONS].index(letter)
    return (f'<section class="page jacket divider" id="p{n}"><img class="board" src="{KRAFT}">'
            f'<div class="jk-top"><div class="jk-org"><img src="{LOGO}"><span>WEIRWOOD</span></div>'
            f'<div class="jk-fileno">{lbl("File no.")}{typed(FILE_NO)}</div></div>'
            f'<div class="dtab" style="top:{34 + step * 33}mm"><b>{letter}</b><span>{en}</span></div>'
            f'<div class="dlabel">{typed("Flag " + letter)}<h1 class="d-en">{en}</h1>'
            f'<p class="d-q">{p["question"]}</p>{flag_contents(letter)}</div></section>')


def render_page(n, p):
    if p["kind"] == "jacket":
        return f'<section class="page jacket {p["cls"]}" id="p{n}"><img class="board" src="{KRAFT}">{p["body"]}</section>'
    if p["kind"] == "divider":
        return render_divider(n, p)
    body = p["body"].replace(INDEX_SLOT, index_table())
    sec = p["sec"]
    section_name = SEC[sec][1] if sec else "Note"
    start = " start" if p.get("start") else ""
    return (f'<section class="page sheet{start}" id="p{n}"><div class="holes"><i></i><i></i></div><div class="mrule"></div>'
            f'<header class="fhead"><div>{lbl("File no.")}{typed(FILE_NO)}</div>'
            f'<div>{lbl("Page")}{typed(f"{n:02d}")}</div></header>'
            f'{tabs(sec)}<div class="body">{body}</div>'
            f'<footer class="ffoot"><span>Weirwood · Mosaic</span><span>{html.escape(section_name)}</span></footer></section>')


def main():
    faces = (HERE / "fonts/faces.css").read_text(encoding="utf-8").replace("FONTS/", uri(HERE / "fonts") + "/")
    css = (HERE / "brochure.css").read_text(encoding="utf-8").replace("url('brand/", f"url('{uri(HERE / 'brand')}/")
    doc = (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Mosaic — The file on Mosaic</title>'
           f'<style>{faces}{css}</style></head><body>{"".join(render_page(n, p) for n, p in enumerate(PAGES, 1))}</body></html>')
    page_html = HERE.parents[1] / "var" / "tmp" / "brochure.html"    # intermediate, kept out of the source tree
    page_html.parent.mkdir(parents=True, exist_ok=True)
    page_html.write_text(doc, encoding="utf-8")
    with sync_playwright() as pw:
        b = pw.chromium.launch(channel="chrome")
        pg = b.new_page(viewport={"width": 794, "height": 1123})
        pg.goto(page_html.as_uri(), wait_until="load")
        pg.evaluate("document.fonts.ready")
        pg.wait_for_timeout(900)
        # Free space above the folio, per sheet, in mm; then let the screenshots take what the text leaves.
        pg.evaluate("""() => { const MM = 96 / 25.4;
            window.slack = p => { const limit = p.querySelector('.ffoot').getBoundingClientRect().top - 8; let worst = 0;
                for (const e of p.querySelectorAll('.body *')) {
                    if (e.parentElement.closest('.crop')) continue;      // a cropped screenshot ends at its crop
                    const b = e.getBoundingClientRect(); if (b.height) worst = Math.max(worst, b.bottom); }
                return (limit - worst) / MM; };
            // a sheet that runs over narrows its screenshots slightly (kept whole); never below 85% of their width
            for (const p of document.querySelectorAll('.page.sheet'))
                for (const fig of p.querySelectorAll('.encl.wide, .encl.doc')) {
                    const over = 2 - slack(p); if (over <= 0) break;
                    const w = fig.getBoundingClientRect().width, h = fig.querySelector('.crop').getBoundingClientRect().height;
                    fig.style.maxWidth = Math.max(0.85 * w, w * (h - over * MM) / h) + 'px';
                } }""")
        room = pg.evaluate("[...document.querySelectorAll('.page.sheet')].map(p => [p.id, Math.round(slack(p))])")
        over = [r for r in room if r[1] < 0]
        print("free space (mm):", " ".join(f"{i}:{s}" for i, s in room))
        broken = pg.evaluate("[...document.images].filter(i => !i.complete || !i.naturalWidth).map(i => i.src)")
        fonts = pg.evaluate("['700 20px Mukta','400 12px Martel','400 12px \"Courier Prime\"'].map(f => document.fonts.check(f))")
        print("overflow:", over or "none", "| broken images:", broken or "none", "| fonts:", fonts)
        pg.pdf(path=str(OUT), width="210mm", height="297mm", print_background=True, prefer_css_page_size=True,
               outline=True, tagged=True)
        b.close()
    print(f"Built {OUT} — {len(PAGES)} pages, {OUT.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()

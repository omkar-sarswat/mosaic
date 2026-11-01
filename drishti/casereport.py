"""Report builder: case diary entries, chargesheet annexures and intelligence summaries.

A report is a list of blocks. Text and headings are what the officer writes. Every other block is a
reference (a record, an exhibit, a pattern lead, an area search, the links between the people in the
report), and references are read afresh, through the access rules, each time the report is opened or
exported. A record that is corrected after the report was drafted therefore prints corrected, and a
record the reader may not open is replaced by a note saying it was withheld and why.

Every fact a record block prints carries the source register and record it came from. In the PDF the
citations are numbered and listed in a sources annex, so each line can be checked against its origin.
"""

from __future__ import annotations

import json
import secrets
from collections import defaultdict
from typing import Any, Callable

from .guard.masking import mask_object
from .monitor import Gate, area_search
from .patterns import leads as L
from .report import MARKINGS, _PDF, _watermark
from .sources import source_name
from .store import Store, utcnow

TEMPLATES: dict[str, dict[str, str]] = {
    "case_diary": {
        "title": "Case diary",
        "basis": "Diary of proceedings in investigation (s.192 BNSS 2023)",
        "description": "One day's proceedings: where the officer went, whom they examined, what was found, and what happens next.",
    },
    "accused_profile": {
        "title": "Chargesheet annexure: accused profile",
        "basis": "Annexure to the police report (s.193 BNSS 2023)",
        "description": "Identity, addresses, phones, accounts, vehicles and criminal history of each accused, every fact with its source.",
    },
    "intel_summary": {
        "title": "Intelligence summary",
        "basis": "Internal assessment, not for production in court",
        "description": "Key judgements with the people, leads and places behind them, for a supervisor or a partner agency.",
    },
}
BLOCK_TYPES = ("heading", "text", "record", "exhibit", "lead", "area", "relations")
SHOW = ("identity", "links", "history")
MAX_BLOCKS, MAX_TEXT = 200, 20000

PERSON_FIELDS = [("name", "Name"), ("name_native", "Name (native script)"), ("alias", "Also known as"), ("father_name", "Father's name"),
                 ("gender", "Gender"), ("dob", "Date of birth"), ("birth_year", "Year of birth"), ("nationality", "Nationality"),
                 ("occupation", "Occupation"), ("address", "Address"), ("city", "City"), ("aadhaar", "Aadhaar"), ("pan", "PAN"),
                 ("passport_no", "Passport"), ("dl_no", "Driving licence"), ("voter_id", "Voter ID (EPIC)"), ("email", "Email"),
                 ("declared_income", "Declared income")]
HIDDEN_PROPS = {"district_lgd", "name_key", "phonetic"}
GENDER = {"M": "Male", "F": "Female", "T": "Transgender"}
LINK_GROUP = {"uses_phone": "Phones", "holds_account": "Bank accounts", "signatory_of": "Bank accounts (signatory)", "resides_at": "Addresses",
              "registered_at": "Addresses", "director_of": "Companies (director)", "controls": "Companies (controls)", "employee_of": "Employment",
              "relative_of": "Relatives", "sim_in_device": "Handsets", "history_sheeted_at": "History sheet opened at"}
HISTORY = {"accused_in": "Accused", "complainant_in": "Complainant", "stolen_in": "Reported stolen", "used_in": "Used in", "recovered_in": "Recovered in",
           "mentions": "Mentioned"}
NOT_FACT = {"same_as", "inferred_association"}  # machine inferences: shown on screens as such, never printed as fact


def block_id() -> str:
    return "b" + secrets.token_hex(4)


def _fmt(prop: str, v: Any) -> str:
    if isinstance(v, list):
        return ", ".join(str(x) for x in v)
    if prop == "gender":
        return GENDER.get(str(v), str(v))
    if prop in ("declared_income", "amount", "value") and isinstance(v, (int, float)):
        return f"₹{v:,.0f}"
    return str(v)


def _label(prop: str) -> str:
    return prop.replace("_", " ").capitalize()


def _cite(source: str, record: str | None) -> dict[str, Any]:
    return {"source": source, "source_name": source_name(source), "record": record}


# ---------------------------------------------------------------------------------------------- templates

def starter_blocks(store: Store, case_id: str, template: str) -> list[dict[str, Any]]:
    people = [r["object_id"] for r in store.query(
        "SELECT co.object_id FROM case_objects co JOIN objects o ON o.id=co.object_id WHERE co.case_id=? AND o.type='Person' ORDER BY co.added_at, o.title",
        (case_id,))]
    h = lambda t: {"id": block_id(), "type": "heading", "text": t}  # noqa: E731
    t = lambda hint, text="": {"id": block_id(), "type": "text", "text": text, "hint": hint}  # noqa: E731
    rec = lambda oid, show=list(SHOW): {"id": block_id(), "type": "record", "object_id": oid, "show": show, "note": ""}  # noqa: E731
    if template == "case_diary":
        return [h("Proceedings"), t("Date and hour of each step, places visited, and what was done."),
                h("Persons examined"), t("Who was examined, where, and the substance of what they said. Insert their records below."),
                h("Evidence collected"), t("Exhibits seized or received today. Insert them from the case's evidence register."),
                h("Circumstances ascertained"), t("What the day's work established, and what it did not."),
                h("Further action"), t("Next steps, with the officer responsible.")]
    if template == "accused_profile":
        accused = {r["src"] for r in store.query(
            "SELECT src FROM links WHERE type='accused_in' AND dst IN (SELECT object_id FROM case_objects WHERE case_id=?)", (case_id,))}
        named = [p for p in people if p in accused] or people
        out = [h("Accused persons"), t("One profile per accused. Each fact is printed with the register it came from.")]
        out += [rec(p) for p in named[:12]]
        out += [h("Links between the accused"), {"id": block_id(), "type": "relations"}, h("Role of each accused"),
                t("The part each accused played in the offence, with the evidence for it.")]
        return out
    leads = [r["id"] for r in store.query("SELECT id FROM pattern_hits WHERE case_id=? ORDER BY severity, id LIMIT 5", (case_id,))]
    out = [h("Key judgements"), t("What we assess, how sure we are, and what would change the assessment."),
           h("Subjects"), *[rec(p, ["identity", "links"]) for p in people[:5]]]
    if leads:
        out += [h("Patterns behind the case"), *[{"id": block_id(), "type": "lead", "lead_id": x, "note": ""} for x in leads]]
    out += [h("Links between the subjects"), {"id": block_id(), "type": "relations"},
            h("Sources and reliability"), t("Which registers the assessment rests on, and any gaps or doubts about them.")]
    return out


def clean_blocks(blocks: Any) -> list[dict[str, Any]]:
    """Keep only what a block of each type may hold; reject anything malformed."""
    if not isinstance(blocks, list) or len(blocks) > MAX_BLOCKS:
        raise ValueError(f"a report holds at most {MAX_BLOCKS} blocks")
    out = []
    for b in blocks:
        if not isinstance(b, dict) or b.get("type") not in BLOCK_TYPES:
            raise ValueError("unknown block type")
        bid = str(b.get("id") or block_id())[:24]
        t = b["type"]
        if t in ("heading", "text"):
            text = str(b.get("text") or "")
            if len(text) > MAX_TEXT:
                raise ValueError("a text block holds at most 20,000 characters")
            out.append({"id": bid, "type": t, "text": text[:200] if t == "heading" else text, **({"hint": str(b.get("hint") or "")[:200]} if t == "text" else {})})
        elif t == "record":
            show = [s for s in (b.get("show") or SHOW) if s in SHOW]
            out.append({"id": bid, "type": t, "object_id": str(b.get("object_id") or ""), "show": show or list(SHOW), "note": str(b.get("note") or "")[:4000]})
        elif t == "exhibit":
            out.append({"id": bid, "type": t, "evidence_id": str(b.get("evidence_id") or ""), "note": str(b.get("note") or "")[:4000]})
        elif t == "lead":
            out.append({"id": bid, "type": t, "lead_id": str(b.get("lead_id") or ""), "note": str(b.get("note") or "")[:4000]})
        elif t == "area":
            out.append({"id": bid, "type": t, "search_id": str(b.get("search_id") or ""), "note": str(b.get("note") or "")[:4000]})
        else:
            out.append({"id": bid, "type": t})
    return out


# ---------------------------------------------------------------------------------------------- resolution

class Reader:
    """Reads a report's references for one person under one case, masking to `clearance` (theirs, or a recipient's)."""

    def __init__(self, store: Store, case_id: str, user, decide: Callable[[dict[str, Any]], Any], clearance: int):
        self.store, self.case_id, self.user, self._decide, self.clearance = store, case_id, user, decide, clearance
        self.ontology = store.ontology
        self.gate = Gate(store, self.allowed, self.show)
        self.marking = 1  # nothing personal prints below RESTRICTED
        self.held_back: set[str] = set()  # records the recipient's clearance does not reach

    @property
    def above(self) -> int:
        return len(self.held_back)

    def allowed(self, obj: dict[str, Any]):
        d = self._decide(obj)
        if d.allow and obj["sensitivity"] > self.clearance:
            self.held_back.add(obj["id"])
            return type(d)(False, "above the recipient's clearance")
        return d

    def show(self, obj: dict[str, Any]) -> dict[str, Any]:
        m = mask_object(self.ontology, obj, self.clearance)
        self.marking = max(self.marking, int(obj["sensitivity"]))
        return {"id": m["id"], "type": m["type"], "title": m["title"], "sensitivity": m["sensitivity"], "masked": m["masked"], "props": m["props"]}

    # -- records
    def record(self, oid: str, show: list[str]) -> dict[str, Any]:
        obj = self.store.get_object(oid)
        if not obj:
            return {"missing": "the record no longer exists"}
        d = self.allowed(obj)
        if not d.allow:
            return {"withheld": d.reason}
        rec = self.show(obj)
        prov: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for p in self.store.provenance(oid):
            prov[p["prop"]].append(_cite(p["source"], p["record"]))
        facts = []
        if "identity" in show:
            props = rec["props"]
            fields = PERSON_FIELDS if obj["type"] == "Person" else [(k, _label(k)) for k in props if k not in HIDDEN_PROPS]
            for k, label in fields:
                v = props.get(k)
                if v in (None, "", []) or (k == "birth_year" and props.get("dob")):
                    continue
                facts.append({"label": label, "value": _fmt(k, v), "masked": k in rec["masked"], "cites": prov.get(k, [])})
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        history: list[dict[str, Any]] = []
        if "links" in show or "history" in show:
            links = [x for x in self.store.links_for([oid]) if x["type"] not in NOT_FACT]
            others = self.gate.many({x["dst"] if x["src"] == oid else x["src"] for x in links})
            for x in links:
                other_id = x["dst"] if x["src"] == oid else x["src"]
                o = others.get(other_id)
                if not o:
                    continue
                cites = [_cite(s["source"], s.get("record")) for s in x["sources"]]
                if o["type"] == "Incident" and x["type"] in HISTORY:
                    if "history" in show:
                        p = o["props"]
                        history.append({"id": o["id"], "label": o["title"], "role": HISTORY[x["type"]], "at": str(p.get("occurred_at") or "")[:10],
                                        "detail": " · ".join(filter(None, [p.get("agency"), ", ".join(p.get("sections") or []), str(p.get("status") or "").replace("_", " ")])),
                                        "cites": cites})
                elif "links" in show:
                    group = LINK_GROUP.get(x["type"]) or {"Vehicle": "Vehicles", "Property": "Properties", "Organisation": "Organisations",
                                                          "Person": "People"}.get(o["type"], _label(x["type"]))
                    label = (o["props"].get("address") or o["title"]) if o["type"] == "Location" else o["title"]
                    groups[group].append({"id": o["id"], "label": label, "detail": "" if o["type"] == "Location" else _detail(o), "cites": cites})
        history.sort(key=lambda h: h["at"], reverse=True)
        return {"record": rec, "facts": facts, "groups": [{"label": k, "items": v} for k, v in groups.items()], "history": history}

    # -- exhibits, leads, areas
    def exhibit(self, eid: str) -> dict[str, Any]:
        rows = self.store.query("SELECT * FROM evidence WHERE id=? AND case_id=?", (eid, self.case_id))
        if not rows:
            return {"missing": "no such exhibit in this case"}
        e = dict(rows[0])
        n = self.store.query("SELECT COUNT(*) n FROM custody WHERE evidence_id=?", (eid,))[0]["n"]
        return {"exhibit": {k: e[k] for k in ("id", "filename", "description", "source_type", "sha256", "size", "seized_from", "legal_order", "collected_at",
                                              "uploaded_by", "uploaded_at", "status", "device_make", "device_model", "device_serial")} | {"custody_events": n}}

    def lead(self, hid: str) -> dict[str, Any]:
        rows = self.store.query("SELECT * FROM pattern_hits WHERE id=?", (hid,))
        if not rows:
            return {"missing": "the lead no longer exists"}
        r = dict(rows[0])
        if not L.can_see(self.store, self.user, r):
            return {"withheld": "this lead is outside your agency's mission tracks"}
        reveal = {x["object_id"] for x in self.store.query("SELECT object_id FROM case_objects WHERE case_id=?", (self.case_id,))}
        shown = L.render(self.store, r, reveal, self.show, self.allowed)
        counts = {k: len(v) if isinstance(v, list) else v for k, v in json.loads(r["evidence"]).items() if isinstance(v, (list, int))}
        return {"lead": {"id": r["id"], "title": shown["title"], "summary": shown["summary"], "severity": r["severity"], "status": r["status"],
                         "window": [r["window_start"], r["window_end"]], "evidence_counts": counts}}

    def area(self, sid: str) -> dict[str, Any]:
        rows = self.store.query("SELECT * FROM area_searches WHERE id=? AND case_id=?", (sid, self.case_id))
        if not rows:
            return {"missing": "no such area search in this case"}
        q = dict(rows[0])
        found = area_search(self.store, self.gate, q["lat"], q["lon"], q["radius_km"], q["start_ts"], q["end_ts"])
        brief = lambda xs: [{"id": x["record"]["id"], "label": x["record"]["title"], "type": x["record"]["type"], "count": x.get("count"),  # noqa: E731
                             "first": x.get("first"), "last": x.get("last"), "places": x.get("places") or [], "owner": (x.get("owner") or {}).get("label"),
                             "cites": [_cite(r["source"], r["record"]) for r in x.get("reads", [])[:1]]} for x in xs[:15]]
        return {"area": {"id": sid, "label": q["label"], "lat": q["lat"], "lon": q["lon"], "radius_km": q["radius_km"], "start": q["start_ts"],
                         "end": q["end_ts"], "reason": q["reason"], "searched_by": q["searched_by"], "searched_at": q["searched_at"],
                         "counts_then": json.loads(q["counts"]), "counts_now": found["counts"], "vehicles": brief(found["vehicles"]),
                         "phones": brief(found["phones"]), "travellers": brief(found["travellers"])}}

    def relations(self, ids: list[str]) -> dict[str, Any]:
        """Direct links between the report's records, and the phones, accounts, addresses and FIRs two of them share."""
        shown = self.gate.many(ids)
        ids = list(shown)
        if len(ids) < 2:
            return {"pairs": [], "note": "Insert at least two records to see how they connect."}
        links = [x for x in self.store.links_for(ids) if x["type"] not in NOT_FACT]
        pairs = []
        held: dict[str, list[tuple[str, dict[str, Any]]]] = defaultdict(list)
        for x in links:
            a, b = x["src"], x["dst"]
            cites = [_cite(s["source"], s.get("record")) for s in x["sources"]]
            if a in shown and b in shown:
                pairs.append({"a": shown[a]["title"], "b": shown[b]["title"], "how": _label(x["type"]), "cites": cites})
            for me, other in ((a, b), (b, a)):
                if me in shown and other not in shown:
                    held[other].append((me, {"type": x["type"], "cites": cites}))
        common = self.gate.many(k for k, v in held.items() if len({m for m, _ in v}) >= 2)
        for oid, via in held.items():
            if oid not in common:
                continue
            who = sorted({m for m, _ in via})
            for i in range(len(who)):
                for j in range(i + 1, len(who)):
                    pair = [l for m, l in via if m in (who[i], who[j])]
                    cites = [c for l in pair for c in l["cites"]]
                    pairs.append({"a": shown[who[i]]["title"], "b": shown[who[j]]["title"], "how": _shared({l["type"] for l in pair}, common[oid]),
                                  "cites": cites})
        return {"pairs": pairs[:60]}


def _shared(types: set[str], o: dict[str, Any]) -> str:
    """How two records are joined through a third, in the words a charge-sheet would use."""
    t = o["title"]
    if types == {"accused_in"}:
        return f"Co-accused in FIR {t}"
    if "uses_phone" in types:
        return f"Both used phone {t}"
    if types & {"holds_account", "signatory_of"}:
        return f"Both operate account {t}"
    if types & {"resides_at", "registered_at"}:
        return f"Same address: {t}"
    if types & {"director_of", "controls", "employee_of"}:
        return f"Both connected to {t}"
    if o["type"] == "Incident":
        return f"Both named in FIR {t}"
    return f"Both linked to {o['type'].lower()} {t}"


def _detail(o: dict[str, Any]) -> str:
    p = o["props"]
    if o["type"] == "Phone":
        return " · ".join(filter(None, [p.get("operator"), p.get("subscriber_name") and f"subscriber {p['subscriber_name']}"]))
    if o["type"] == "BankAccount":
        return " · ".join(filter(None, [p.get("bank"), p.get("ifsc"), p.get("kind")]))
    if o["type"] == "Vehicle":
        return " · ".join(filter(None, [p.get("make"), p.get("colour")]))
    if o["type"] == "Organisation":
        return " · ".join(filter(None, [str(p.get("kind") or "").replace("_", " "), p.get("cin")]))
    return ""


def resolve(reader: Reader, blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    record_ids = [b["object_id"] for b in blocks if b["type"] == "record" and b.get("object_id")]
    out = []
    for b in blocks:
        t = b["type"]
        view: dict[str, Any] = {}
        if t == "record":
            view = reader.record(b["object_id"], b.get("show") or list(SHOW))
        elif t == "exhibit":
            view = reader.exhibit(b["evidence_id"])
        elif t == "lead":
            view = reader.lead(b["lead_id"])
        elif t == "area":
            view = reader.area(b["search_id"])
        elif t == "relations":
            view = reader.relations(record_ids)
        out.append(b | ({"view": view} if view else {}))
    return out


# ---------------------------------------------------------------------------------------------- PDF

def report_pdf(store: Store, report: dict[str, Any], resolved: list[dict[str, Any]], *, marking_level: int, user: str, user_name: str,
               recipient: str, export_id: str, withheld_above: int) -> bytes:
    case = dict(store.query("SELECT * FROM cases WHERE id=?", (report["case_id"],))[0])
    tpl = TEMPLATES.get(report["template"], {"title": report["template"], "basis": ""})
    marking = MARKINGS.get(marking_level, "RESTRICTED")
    pdf = _PDF(marking, _watermark(user, recipient, export_id))
    pdf.alias_nb_pages()
    pdf.add_page()
    cites: dict[tuple[str, str | None], int] = {}

    def ref(cs: list[dict[str, Any]]) -> str:
        nums = []
        for c in cs:
            key = (c["source"], c.get("record"))
            if key not in cites:
                cites[key] = len(cites) + 1
            nums.append(cites[key])
        return (" [" + ", ".join(str(n) for n in sorted(set(nums))) + "]") if nums else ""

    pdf.set_font("Noto", "", 9)
    pdf.cell(0, 5, f"{case.get('agency') or ''} · {tpl['title'].upper()}", new_x="LMARGIN", new_y="NEXT")
    pdf.h1(report["title"])
    pdf.kv("Case", f"{case['id']} · {case.get('title') or ''}")
    pdf.kv("Legal basis", case["legal_basis"])
    if tpl.get("basis"):
        pdf.kv("Document", tpl["basis"])
    pdf.kv("Prepared by", f"{user_name} on {utcnow()[:16].replace('T', ' ')} UTC")
    if recipient:
        pdf.kv("Copy for", recipient)
    if withheld_above:
        pdf.kv("Withheld", f"{withheld_above} record(s) above the recipient's clearance were left out")
    pdf.ln(2)

    for b in resolved:
        t, v = b["type"], b.get("view") or {}
        if t == "heading":
            pdf.h2(b["text"] or "Untitled section")
            continue
        if t == "text":
            if b["text"].strip():
                pdf.para(b["text"], 9.5)
                pdf.ln(1)
            continue
        if v.get("withheld") or v.get("missing"):
            pdf.para(f"[A {t} reference was left out: {v.get('withheld') or v.get('missing')}.]", 8)
            continue
        if t == "record":
            r = v["record"]
            pdf.set_font("Noto", "B", 10.5)
            pdf.cell(0, 6, f"{r['title']}  ({r['type'].lower()} · {MARKINGS.get(r['sensitivity'], '')})", new_x="LMARGIN", new_y="NEXT")
            if v["facts"]:
                pdf.table(["Particular", "Detail", "Source"], [[f["label"], f["value"] + (" (masked)" if f["masked"] else ""), ref(f["cites"]).strip()]
                                                                for f in v["facts"]], [45, 105, 30])
            for g in v["groups"]:
                pdf.para(f"{g['label']}: " + "; ".join(f"{i['label']}{' (' + i['detail'] + ')' if i['detail'] else ''}{ref(i['cites'])}" for i in g["items"][:12]), 8.5)
            if v["history"]:
                pdf.ln(1)
                pdf.table(["Record", "Role", "Date", "Particulars", "Source"],
                          [[h["label"], h["role"], h["at"], h["detail"], ref(h["cites"]).strip()] for h in v["history"]], [42, 22, 20, 70, 26])
            if b.get("note"):
                pdf.para(b["note"], 9)
            pdf.ln(2)
        elif t == "exhibit":
            e = v["exhibit"]
            pdf.set_font("Noto", "B", 10)
            pdf.cell(0, 6, f"Exhibit: {e['filename']}", new_x="LMARGIN", new_y="NEXT")
            pdf.kv("Description", e["description"] or "-")
            pdf.kv("SHA-256", e["sha256"])
            pdf.kv("Seized from", e["seized_from"] or "-")
            pdf.kv("Order", e["legal_order"] or "-")
            pdf.kv("Custody", f"{e['custody_events']} recorded event(s); status {e['status']}")
            if b.get("note"):
                pdf.para(b["note"], 9)
        elif t == "lead":
            ld = v["lead"]
            pdf.set_font("Noto", "B", 10)
            pdf.multi_cell(0, 5.5, f"Pattern lead: {ld['title']}", new_x="LMARGIN", new_y="NEXT")
            pdf.para(ld["summary"], 8.5)
            pdf.para("A pattern lead is an investigative pointer found in the data, not a finding. " +
                     ", ".join(f"{k.replace('_', ' ')}: {n}" for k, n in ld["evidence_counts"].items()), 8)
            if b.get("note"):
                pdf.para(b["note"], 9)
        elif t == "area":
            a = v["area"]
            pdf.set_font("Noto", "B", 10)
            pdf.multi_cell(0, 5.5, f"Area search: {a['radius_km']:g} km around {a['label']}, {a['start'][:10]} to {a['end'][:10]}", new_x="LMARGIN", new_y="NEXT")
            pdf.para(f"Asked by {a['searched_by']} on {a['searched_at'][:10]}: {a['reason']}", 8)
            rows = [[x["label"], {"Vehicle": "vehicle", "Phone": "phone", "Person": "traveller"}.get(x["type"], x["type"].lower()), str(x["count"] or ""),
                     f"{(x['first'] or '')[:16].replace('T', ' ')} to {(x['last'] or '')[:16].replace('T', ' ')}", ", ".join(x["places"][:3]) + ref(x["cites"])]
                    for k in ("vehicles", "phones", "travellers") for x in a[k]]
            if rows:
                pdf.table(["Record", "Kind", "Reads", "First and last", "Where"], rows, [36, 20, 14, 52, 58])
            else:
                pdf.para("Nothing visible to the reader was inside the area in that window.", 8.5)
            if b.get("note"):
                pdf.para(b["note"], 9)
        elif t == "relations":
            if v.get("pairs"):
                pdf.table(["Between", "And", "How", "Source"], [[p["a"], p["b"], p["how"], ref(p["cites"]).strip()] for p in v["pairs"]], [40, 40, 72, 28])
            else:
                pdf.para(v.get("note") or "No recorded link between the records in this report.", 8.5)

    if cites:
        pdf.h2("Sources")
        pdf.table(["#", "Register", "Record reference"], [[str(n), f"{source_name(s)} ({s})", r or "-"] for (s, r), n in sorted(cites.items(), key=lambda x: x[1])],
                  [10, 100, 70])
    pdf.ln(3)
    pdf.para("Facts are printed as held in the source registers on the date of printing. Machine-inferred associations are not printed as fact. "
             "Masked identifiers are masked under the access rules for the reader of this copy.", 7.5)
    return bytes(pdf.output())

"""Case reports and court evidence packs.

* `case_report_pdf` / `case_report_html`: intelligence summary for a case: suspects with their
  evidence, money trail, alerts, profiles, exhibits, timeline and a sources annex. Every page
  carries the classification marking and a watermark naming who exported it, when, for whom.
* Release copies: `recipient_clearance` removes or masks what the recipient may not see.
* `evidence_pack_zip`: report + draft BSA 2023 s.63(4) certificate (Part A filled with hash
  values and device details, Part B left for the expert) + custody logs + exhibits + a SHA-256
  manifest of every file in the pack.
"""

from __future__ import annotations

import hashlib
import html
import io
import json
import secrets
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fpdf import FPDF

from .analytics.money import Ledger
from .analytics.network import build_network, case_seeds, rank_suspects
from .evidence import custody_append, custody_log, list_evidence, read_evidence
from .guard.masking import mask_object
from .store import Store, utcnow

FONTS = Path(__file__).parent / "assets" / "fonts"
MARKINGS = {0: "UNCLASSIFIED", 1: "RESTRICTED", 2: "CONFIDENTIAL", 3: "SECRET"}


def inr(v: float | None) -> str:
    if v is None:
        return "-"
    if abs(v) >= 1e7:
        return f"₹{v / 1e7:,.2f} Cr"
    if abs(v) >= 1e5:
        return f"₹{v / 1e5:,.2f} L"
    return f"₹{v:,.0f}"


def assemble(store: Store, case_id: str, *, recipient_clearance: int = 3, top: int = 15) -> dict[str, Any]:
    case = dict(store.query("SELECT * FROM cases WHERE id=?", (case_id,))[0])
    L = Ledger(store)
    seeds = case_seeds(store, case_id)
    net = build_network(store, seeds, L)
    sus = rank_suspects(store, net, L)[:top]
    objs = store.get_objects(list(net["nodes"]) + seeds)
    ont = store.ontology
    withheld = 0

    def visible(o: dict[str, Any]) -> bool:
        nonlocal withheld
        if o["sensitivity"] > recipient_clearance:
            withheld += 1
            return False
        return True

    def show(o: dict[str, Any]) -> dict[str, Any]:
        return mask_object(ont, o, recipient_clearance)

    profiles = []
    for s in sus[:6]:
        o = objs.get(s["id"]) or store.get_object(s["id"])
        if not o or not visible(o):
            continue
        m = show(o)
        links = store.links_for([s["id"]])
        others = store.get_objects({l["dst"] if l["src"] == s["id"] else l["src"] for l in links})
        groups: dict[str, list[str]] = {}
        for x in others.values():
            if x["type"] in ("BankAccount", "Phone", "Organisation", "Vehicle", "Property", "CryptoWallet") and visible(x):
                groups.setdefault(x["type"], []).append(show(x)["title"])
        trips = store.query("SELECT from_city, to_city, ts FROM travel WHERE person_id=? ORDER BY ts DESC", (s["id"],))
        profiles.append({"suspect": s, "props": m["props"], "masked": m["masked"], "groups": groups,
                         "trips": [f"{t['ts'][:10]} {t['from_city']}→{t['to_city']}" for t in trips[:8]]})
    alerts = []
    for r in store.query("SELECT * FROM alerts ORDER BY score DESC"):
        if r["subject_id"] in net["nodes"]:
            alerts.append(dict(r))
    tr = net["traced"]
    timeline = []
    for x in net["nodes"]:
        o = objs.get(x)
        if o and o["type"] == "Incident":
            timeline.append((o["props"].get("occurred_at", ""), f"{o['props'].get('agency', '')} {o['title']}: {o['props'].get('summary', '')}"))
    timeline.sort(reverse=True)
    sources: dict[str, int] = {}
    ids = [s["id"] for s in sus]
    if ids:
        for r in store.query(f"SELECT source, COUNT(*) n FROM provenance WHERE object_id IN ({','.join('?' * len(ids))}) GROUP BY source", ids):
            sources[r["source"]] = r["n"]
    return {
        "case": case, "seeds": [show(objs[s]) for s in seeds if s in objs and visible(objs[s])], "suspects": sus,
        "profiles": profiles, "alerts": alerts[:25], "beneficiaries": tr["out"]["beneficiaries"][:10], "sources_money": tr["in"]["beneficiaries"][:10],
        "sinks": tr["out"]["sinks"], "timeline": timeline[:30], "evidence": list_evidence(store, case_id), "provenance": sources,
        "network_size": len(net["nodes"]), "withheld": withheld, "recipient_clearance": recipient_clearance,
    }


class _PDF(FPDF):
    def __init__(self, marking: str, watermark: str):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.marking, self.watermark = marking, watermark
        self.add_font("Noto", "", str(FONTS / "NotoSans-Regular.ttf"))
        self.add_font("Noto", "B", str(FONTS / "NotoSans-Bold.ttf"))
        self.add_font("NotoDeva", "", str(FONTS / "NotoSansDevanagari-Regular.ttf"))
        self.set_fallback_fonts(["NotoDeva"])
        try:
            self.set_text_shaping(True)
        except Exception:  # noqa: BLE001 - shaping needs uharfbuzz; plain text still renders
            pass
        self.set_auto_page_break(True, margin=18)
        self.set_margins(15, 18, 15)

    def header(self) -> None:
        self.set_font("Noto", "B", 8)
        self.set_text_color(160, 20, 20)
        self.cell(0, 5, self.marking, align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(0, 0, 0)
        self.ln(2)

    def footer(self) -> None:
        self.set_y(-14)
        self.set_font("Noto", "", 7)
        self.set_text_color(110, 110, 110)
        self.cell(0, 4, self.watermark, align="L")
        self.cell(0, 4, f"{self.marking}  ·  page {self.page_no()}/{{nb}}", align="R")
        self.set_text_color(0, 0, 0)

    def h1(self, t: str) -> None:
        self.set_font("Noto", "B", 16)
        self.multi_cell(0, 8, t, new_x="LMARGIN", new_y="NEXT")

    def h2(self, t: str) -> None:
        self.ln(3)
        self.set_font("Noto", "B", 11)
        self.set_fill_color(235, 240, 245)
        self.cell(0, 7, t, fill=True, new_x="LMARGIN", new_y="NEXT")
        self.ln(1)

    def para(self, t: str, size: int = 9) -> None:
        self.set_font("Noto", "", size)
        self.multi_cell(0, 4.6, t, new_x="LMARGIN", new_y="NEXT")

    def kv(self, k: str, v: str) -> None:
        self.set_font("Noto", "B", 9)
        self.cell(48, 5, k)
        self.set_font("Noto", "", 9)
        self.multi_cell(0, 5, v, new_x="LMARGIN", new_y="NEXT")

    def table(self, head: list[str], rows: list[list[str]], widths: list[float]) -> None:
        self.set_font("Noto", "B", 8)
        self.set_fill_color(225, 230, 236)
        for h, w in zip(head, widths):
            self.cell(w, 6, h, border=1, fill=True)
        self.ln()
        self.set_font("Noto", "", 7.5)
        for r in rows:
            y0 = self.get_y()
            if y0 > 265:
                self.add_page()
                y0 = self.get_y()
            x0 = self.get_x()
            heights = []
            for c, w in zip(r, widths):
                lines = self.multi_cell(w, 4, c, dry_run=True, output="LINES")
                heights.append(max(1, len(lines)) * 4)
            hgt = max(heights) + 1
            for c, w in zip(r, widths):
                x = self.get_x()
                self.rect(x, y0, w, hgt)
                self.multi_cell(w, 4, c, new_x="RIGHT", new_y="TOP", max_line_height=4)
                self.set_xy(x + w, y0)
            self.set_xy(x0, y0 + hgt)


def _watermark(user: str, recipient: str, export_id: str) -> str:
    return f"Mosaic export {export_id} · by {user} · {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC · copy for {recipient or 'internal file'}"


def case_report_pdf(store: Store, case_id: str, *, user: str, recipient: str = "", recipient_clearance: int = 3, export_id: str | None = None) -> bytes:
    d = assemble(store, case_id, recipient_clearance=recipient_clearance)
    export_id = export_id or secrets.token_hex(4).upper()
    c = d["case"]
    marking = MARKINGS.get(min(recipient_clearance, 3), "RESTRICTED")
    pdf = _PDF(marking, _watermark(user, recipient, export_id))
    pdf.alias_nb_pages()
    pdf.add_page()
    pdf.set_font("Noto", "", 9)
    pdf.cell(0, 5, f"{c.get('agency') or ''} · INTELLIGENCE SUMMARY / CASE REPORT", new_x="LMARGIN", new_y="NEXT")
    pdf.h1(c.get("title") or c["id"])
    pdf.kv("Case", c["id"])
    pdf.kv("Purpose", c["purpose"].replace("_", " "))
    pdf.kv("Legal basis", c["legal_basis"])
    pdf.kv("Opened", f"{c['opened_at'][:16]} by {c['opened_by']}")
    pdf.kv("Prepared", f"{utcnow()[:16]} by {user}" + (f" · release copy for {recipient} (clearance {MARKINGS[recipient_clearance]})" if recipient else ""))
    pdf.kv("Case records", ", ".join(s["title"] for s in d["seeds"]))
    pdf.kv("Network examined", f"{d['network_size']} objects; {len(d['suspects'])} ranked persons; {len(d['alerts'])} typology alerts")
    if d["withheld"]:
        pdf.kv("Withheld", f"{d['withheld']} item(s) above the recipient's clearance were removed")
    pdf.para("Scores below rank leads by evidence found in the data (money, records, communications, control of companies). "
             "They are investigative leads for the officer, not findings of guilt. Every fact is traceable to its source system (annex).", 8)

    pdf.h2("1. Persons of interest, ranked by evidence")
    pdf.table(["#", "Name", "Role", "Score", "Principal evidence"],
              [[str(i + 1), s["name"], s["role"], f"{s['score']:.0f}", "; ".join(s["evidence"][:3])] for i, s in enumerate(d["suspects"])],
              [7, 34, 38, 12, 89])
    pdf.h2("2. Money trail")
    pdf.para("Funds traced onward from the case accounts ended with: " + ", ".join(f"{k} {inr(v)}" for k, v in d["sinks"].items()) + ".")
    pdf.table(["Recipient (onward)", "Traced value"], [[b["name"], inr(b["amount"])] for b in d["beneficiaries"]], [130, 50])
    pdf.ln(2)
    pdf.table(["Originator (sources)", "Traced value"], [[b["name"], inr(b["amount"])] for b in d["sources_money"]], [130, 50])
    pdf.h2("3. Typology alerts in the network")
    pdf.table(["Typology", "Finding", "Amount"],
              [[a["rule"].replace("_", " ").title(), a["summary"], inr(a["amount"])] for a in d["alerts"]], [40, 115, 25])
    pdf.h2("4. Profiles")
    for p in d["profiles"]:
        s, pr = p["suspect"], p["props"]
        pdf.set_font("Noto", "B", 10)
        pdf.cell(0, 6, f"{s['name']}  ({s['role']}, score {s['score']:.0f})", new_x="LMARGIN", new_y="NEXT")
        ident = [f"{k.upper()}: {pr[k]}" for k in ("aadhaar", "pan", "passport_no", "dl_no", "voter_id") if pr.get(k)]
        pdf.para(" · ".join(filter(None, [pr.get("name_native"), pr.get("occupation"), pr.get("city"), f"DOB {pr.get('dob')}" if pr.get("dob") else ""])))
        if ident:
            pdf.para("Identifiers: " + " · ".join(ident), 8)
        for k, v in p["groups"].items():
            pdf.para(f"{k}: " + ", ".join(v[:8]), 8)
        if p["trips"]:
            pdf.para("Travel: " + "; ".join(p["trips"]), 8)
        pdf.para("Evidence: " + " | ".join(s["evidence"][:6]), 8)
        pdf.ln(1)
    pdf.h2("5. Exhibits held (evidence register)")
    if d["evidence"]:
        pdf.table(["Exhibit", "Description / device", "SHA-256", "Order", "Custody"],
                  [[e["filename"], f"{e.get('description') or ''} {e.get('device_make') or ''} {e.get('device_model') or ''}".strip(),
                    e["sha256"], e.get("legal_order") or "", str(e["custody_events"])] for e in d["evidence"]], [32, 45, 62, 26, 15])
    else:
        pdf.para("No exhibits uploaded to the case locker.")
    pdf.h2("6. Chronology")
    for t, txt in d["timeline"]:
        pdf.para(f"{t[:16]}  {txt}", 8)
    pdf.h2("Annex: sources")
    pdf.para("Facts in this report were drawn from the following source systems (number of property values on the persons above): "
             + ", ".join(f"{k} ({v})" for k, v in sorted(d["provenance"].items())) + ". "
             "Every query that produced this report is recorded in the Mosaic audit chain under the case above.", 8)
    return bytes(pdf.output())


def case_report_html(store: Store, case_id: str, *, user: str, recipient: str = "", recipient_clearance: int = 3) -> str:
    d = assemble(store, case_id, recipient_clearance=recipient_clearance)
    c, e = d["case"], html.escape
    rows = "".join(f"<tr><td>{i + 1}</td><td>{e(s['name'])}</td><td>{e(s['role'])}</td><td>{s['score']:.0f}</td><td>{e('; '.join(s['evidence'][:3]))}</td></tr>"
                   for i, s in enumerate(d["suspects"]))
    al = "".join(f"<tr><td>{e(a['rule'])}</td><td>{e(a['summary'])}</td><td>{inr(a['amount'])}</td></tr>" for a in d["alerts"])
    marking = MARKINGS.get(min(recipient_clearance, 3), "RESTRICTED")
    return f"""<!doctype html><html lang="en"><meta charset="utf-8"><title>{e(c.get('title') or c['id'])}</title>
<style>body{{font:13px system-ui,sans-serif;max-width:960px;margin:24px auto;color:#111}}.mk{{text-align:center;color:#a00;font-weight:700}}
table{{border-collapse:collapse;width:100%;margin:8px 0}}td,th{{border:1px solid #ccc;padding:4px 6px;vertical-align:top}}th{{background:#eef}}</style>
<div class="mk">{marking}</div><h1>{e(c.get('title') or '')}</h1><p><b>{e(c['id'])}</b> · {e(c['purpose'])} · {e(c['legal_basis'])}</p>
<p>Prepared by {e(user)} at {utcnow()[:16]} UTC{(' for ' + e(recipient)) if recipient else ''}. Scores are leads, not findings.</p>
<h2>Persons of interest</h2><table><tr><th>#</th><th>Name</th><th>Role</th><th>Score</th><th>Evidence</th></tr>{rows}</table>
<h2>Typology alerts</h2><table><tr><th>Rule</th><th>Finding</th><th>Amount</th></tr>{al}</table><div class="mk">{marking}</div></html>"""


def s63_certificate_pdf(store: Store, case_id: str, *, user: str, user_name: str, export_id: str) -> bytes:
    """Draft certificate under s.63(4)(c) BSA 2023 for each held exhibit: Part A completed from the
    locker metadata, Part B left blank for the expert. A DRAFT: an officer must check, complete and sign."""
    ev = [e for e in list_evidence(store, case_id) if e["status"] == "held"]
    pdf = _PDF("DRAFT CERTIFICATE - TO BE VERIFIED AND SIGNED", _watermark(user, "court filing", export_id))
    pdf.alias_nb_pages()
    for e in ev:
        pdf.add_page()
        pdf.set_font("Noto", "B", 12)
        pdf.multi_cell(0, 6, "CERTIFICATE UNDER SECTION 63(4)(c) OF THE BHARATIYA SAKSHYA ADHINIYAM, 2023", align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Noto", "B", 10)
        pdf.cell(0, 6, "PART A (to be filled by the party)", align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)
        pdf.para(f"I, {user_name}, do hereby solemnly affirm and sincerely state and submit as follows:")
        pdf.para(f"I have produced the electronic record / output of the digital record '{e['filename']}' ({e.get('description') or 'no description'}), "
                 f"taken from the following device / digital record source:")
        for t in ("Computer / storage media", "DVR", "Mobile phone", "Flash drive", "CD / DVD", "Server", "Cloud", "Other"):
            mark = "☒" if (e.get("source_type") or "").lower().startswith(t.lower().split(" ")[0]) else "☐"
            pdf.para(f"   {mark} {t}")
        pdf.kv("Make and model", f"{e.get('device_make') or '________'} {e.get('device_model') or ''}")
        pdf.kv("Serial number", e.get("device_serial") or "________")
        pdf.kv("IMEI / UIN / UID / MAC / Cloud ID", e.get("device_id") or "________")
        pdf.kv("Seized from / custody", e.get("seized_from") or "________")
        pdf.kv("Legal order", e.get("legal_order") or "________")
        pdf.para("The digital device or the digital record source was under the lawful control for regularly creating, storing or processing "
                 "information for the purposes of carrying out regular activities, and during this period the computer or communication device "
                 "was working properly and the relevant information was regularly fed into it during the ordinary course of business. "
                 "If the computer / digital device was not working properly at any time, that did not affect the electronic / digital record or its accuracy.", 8.5)
        pdf.para("The digital device or the source of the electronic record is: ☐ owned  ☐ maintained  ☐ managed  ☐ operated by me (select as applicable).", 8.5)
        pdf.para("I state that the hash value(s) of the electronic / digital record(s) is/are:", 9)
        pdf.set_font("Noto", "B", 8.5)
        pdf.multi_cell(0, 5, f"SHA-256: {e['sha256']}\nMD5:     {e['md5']}", new_x="LMARGIN", new_y="NEXT")
        pdf.para("obtained through the following algorithm: ☐ SHA1  ☒ SHA256  ☒ MD5  ☐ Other (legally acceptable standard). "
                 "(Hash report to be enclosed with the certificate.)", 8.5)
        pdf.ln(4)
        pdf.para("Date (DD/MM/YYYY): __________      Place: __________      Name and signature: ______________________")
        pdf.ln(6)
        pdf.set_font("Noto", "B", 10)
        pdf.cell(0, 6, "PART B (to be filled by the expert)", align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.para("I, ______________________, son / daughter / spouse of ______________, residing / employed at ______________________, "
                 "do hereby solemnly affirm and sincerely state and submit that the produced electronic record / output of the digital record "
                 "was obtained from the device described above, and that its hash value(s) is/are:")
        pdf.para("SHA-256 / MD5 (to be computed independently by the expert): ____________________________________________")
        pdf.ln(4)
        pdf.para("Date (DD/MM/YYYY): __________      Place: __________      Name, designation and signature: ______________________")
        pdf.ln(3)
        pdf.para(f"Mosaic exhibit {e['id']} · uploaded {e['uploaded_at'][:16]} by {e['uploaded_by']} · {len(custody_log(store, e['id']))} custody events recorded. "
                 "This draft was generated from the evidence locker; the signatories must verify every statement before signing.", 7)
    if not ev:
        pdf.add_page()
        pdf.para("No exhibits are held in this case's locker.")
    return bytes(pdf.output())


def evidence_pack_zip(store: Store, case_id: str, *, user: str, user_name: str, recipient: str, recipient_clearance: int) -> tuple[bytes, str]:
    export_id = secrets.token_hex(4).upper()
    files: dict[str, bytes] = {
        "01_case_report.pdf": case_report_pdf(store, case_id, user=user, recipient=recipient, recipient_clearance=recipient_clearance, export_id=export_id),
        "02_case_report.html": case_report_html(store, case_id, user=user, recipient=recipient, recipient_clearance=recipient_clearance).encode(),
        "03_certificate_s63_BSA_draft.pdf": s63_certificate_pdf(store, case_id, user=user, user_name=user_name, export_id=export_id),
    }
    custody = {}
    for e in list_evidence(store, case_id):
        if e["status"] != "held":
            continue
        meta, data = read_evidence(store, e["id"], user, purpose="exported")
        files[f"exhibits/{e['id'].split(':')[1]}_{meta['filename']}"] = data
        custody[e["id"]] = custody_log(store, e["id"])
    files["04_chain_of_custody.json"] = json.dumps(custody, indent=2).encode()
    manifest = {"export_id": export_id, "case_id": case_id, "exported_by": user, "exported_at": utcnow(), "recipient": recipient,
                "recipient_clearance": recipient_clearance, "files": {k: hashlib.sha256(v).hexdigest() for k, v in files.items()}}
    files["00_manifest.json"] = json.dumps(manifest, indent=2).encode()
    files["README.txt"] = (f"Mosaic court evidence pack {export_id} for case {case_id}.\n"
                           "00_manifest.json lists the SHA-256 of every file. The certificate is a DRAFT: verify, complete and sign it.\n").encode()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in sorted(files.items()):
            z.writestr(name, data)
    for eid in custody:
        custody_append(store, eid, user, "included_in_export", {"export_id": export_id, "recipient": recipient})
    return buf.getvalue(), export_id

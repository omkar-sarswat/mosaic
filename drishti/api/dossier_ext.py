"""Dossier sections beyond the financial core: criminal background with roles, movement, communications,
purchase registers, tenders, weapons and pattern findings.

Each section is shown only when the active case's purpose covers its record class (ontology
`purpose_classes`); otherwise the dossier says the section exists but is outside this case's purpose,
so an empty section is never mistaken for absence of records."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from typing import Any

from ..patterns import leads as L
from .deps import Ctx

ROLE = {"accused_in": "accused", "victim_in": "victim", "complainant_in": "complainant", "witness_in": "witness", "convicted_in": "convicted"}


def _classes(c: Ctx) -> set[str]:
    return set(c.case.record_classes or c.svc.ontology.purpose_classes(c.case.purpose)) if c.case else set()


def extend(c: Ctx, out: dict[str, Any], obj: dict[str, Any], cluster: list[str]) -> list[str]:
    """Add sections to a dossier; returns object ids shown (for the audit record)."""
    s = c.svc.store
    allowed = _classes(c)
    withheld: list[str] = []
    shown: list[str] = []
    q = ",".join("?" * len(cluster))

    def gate(cls: str, label: str) -> bool:
        if cls in allowed:
            return True
        withheld.append(label)
        return False

    # ---- travel is an event table: gate it like the object classes
    if out.get("travel") and not gate("travel_immigration", "Travel and immigration"):
        out["travel"] = []
        out["timeline"] = [e for e in out.get("timeline", []) if e.get("kind") != "travel"]
    # ---- criminal background: every FIR with the person's role in it
    if obj["type"] in ("Person", "Organisation") and gate("criminal_background", "Criminal background"):
        rows = s.query(f"SELECT l.type, l.dst FROM links l WHERE l.src IN ({q}) AND l.type IN ('accused_in','victim_in','complainant_in','witness_in','convicted_in')", cluster)
        incs = s.get_objects([r["dst"] for r in rows])
        crim = []
        for r in rows:
            o = incs.get(r["dst"])
            if not o or not c.decide(o).allow:
                continue
            p = o["props"]
            co = [x["src"] for x in s.query("SELECT src FROM links WHERE type='accused_in' AND dst=? AND src NOT IN (" + q + ")", (o["id"], *cluster))]
            crim.append({"id": o["id"], "title": o["title"], "role": ROLE[r["type"]], "agency": p.get("agency"), "kind": p.get("kind"),
                         "sections": p.get("sections", []), "status": p.get("status"), "occurred_at": p.get("occurred_at"),
                         "chargesheeted_on": p.get("chargesheeted_on"), "summary": p.get("summary"), "co_accused": len(co)})
            shown.append(o["id"])
        hs = next((v for rid in cluster if (v := (s.get_object(rid) or {}).get("props", {}).get("history_sheet_no"))), None)
        out["criminal"] = {"records": sorted(crim, key=lambda x: str(x["occurred_at"] or ""), reverse=True), "history_sheet": hs,
                           "roles": dict(Counter(x["role"] for x in crim))}
    # ---- movement: toll and ANPR reads of vehicles owned
    vehicles = [r["dst"] for r in s.query(f"SELECT dst FROM links WHERE type='owns' AND src IN ({q}) AND dst LIKE 'vehicle:%'", cluster)]
    if obj["type"] == "Vehicle":
        vehicles = [obj["id"]]
    if vehicles and gate("movement", "Movement (toll / ANPR reads)"):
        vq = ",".join("?" * len(vehicles))
        reads = [dict(r) for r in s.query(f"SELECT id, vehicle_id, ts, plaza, lat, lon, kind FROM tollhits WHERE vehicle_id IN ({vq}) ORDER BY ts DESC LIMIT 300", vehicles)]
        out["movement"] = {"reads": reads[:120], "total": len(reads), "places": dict(Counter(r["plaza"] for r in reads).most_common(12))}
        for r in reads[:40]:
            out.setdefault("timeline", []).append({"at": r["ts"], "kind": "movement", "title": f"Vehicle read at {r['plaza']}",
                                                   "detail": (r["kind"] or "toll").upper(), "id": r["vehicle_id"]})
    # ---- communications: monthly activity, regular contacts, towers
    phones = [p["id"] for p in out.get("phones", [])] if obj["type"] != "Phone" else [obj["id"]]
    if phones and gate("communications", "Communications (call records)"):
        nums = [n for n in (json.loads(r["props"]).get("number") for r in s.query(f"SELECT props FROM objects WHERE id IN ({','.join('?' * len(phones))})", phones)) if n]
        nq = ",".join("?" * len(nums))
        rows = s.query(f"SELECT ts, a_number, b_number, duration_s, tower_id FROM cdrs WHERE a_number IN ({nq}) OR b_number IN ({nq})", [*nums, *nums]) if nums else []
        monthly: Counter = Counter(r["ts"][:7] for r in rows)
        contacts: Counter = Counter(r["b_number"] if r["a_number"] in nums else r["a_number"] for r in rows)
        towers: Counter = Counter(r["tower_id"] for r in rows if r["tower_id"] and r["a_number"] in nums)
        tw = {r["id"]: r["label"] for r in s.query("SELECT id, label FROM towers")}
        top = []
        for num, n in contacts.most_common(12):
            ph = s.find_identifier(num)
            label = "foreign number" if num.startswith("+") and not num.startswith("+91") else "number"
            owner = None
            if ph:
                u = s.query("SELECT src FROM links WHERE type='uses_phone' AND dst=? LIMIT 1", (ph[0],))
                if u:
                    o = s.get_object(u[0]["src"])
                    if o and c.decide(o).allow:
                        owner = c.summary(o)["title"]
                        shown.append(o["id"])
            top.append({"label": owner or label, "calls": n, "foreign": label == "foreign number"})
        out["comms"] = {"calls": len(rows), "monthly": [{"month": m, "calls": n} for m, n in sorted(monthly.items())], "top_contacts": top,
                        "towers": [{"tower": tw.get(t, t), "calls": n} for t, n in towers.most_common(8)],
                        "first": min((r["ts"] for r in rows), default=None), "last": max((r["ts"] for r in rows), default=None)}
    # ---- purchase registers (organisations)
    if obj["type"] == "Organisation":
        if gate("procurement_licensing", "Controlled-substance / explosives purchase registers"):
            rows = [dict(r) for r in s.query("SELECT ts, seller_id, substance, regime, quantity_kg, buyer_licence FROM procurements WHERE buyer_id=? ORDER BY ts", (obj["id"],))]
            if rows:
                monthly = defaultdict(float)
                for r in rows:
                    monthly[(r["ts"][:7], r["substance"])] += r["quantity_kg"]
                out["procurement"] = {"orders": len(rows), "dealers": len({r["seller_id"] for r in rows}),
                                      "monthly": [{"month": m, "substance": sub, "kg": round(v, 1)} for (m, sub), v in sorted(monthly.items())],
                                      "licence_on_record": obj["props"].get("licence_no"), "licensed_for": obj["props"].get("licensed_for", []),
                                      "licences_quoted": sorted({r["buyer_licence"] for r in rows if r["buyer_licence"]})}
        if gate("corporate", "Tenders and bids"):
            rows = [dict(r) for r in s.query("SELECT b.tender_id, b.amount, b.submitted_at, o.props FROM bids b JOIN objects o ON o.id=b.tender_id WHERE b.bidder_id=?", (obj["id"],))]
            if rows:
                won = {r["src"] for r in s.query("SELECT src FROM links WHERE type='awarded_to' AND dst=?", (obj["id"],))}
                out["tenders"] = [{"tender": json.loads(r["props"]).get("tender_id"), "title": json.loads(r["props"]).get("title"),
                                   "estimate": json.loads(r["props"]).get("estimate"), "bid": r["amount"], "at": r["submitted_at"], "won": r["tender_id"] in won}
                                  for r in rows]
    # ---- weapons tied to the person's incidents or licensed to them
    if obj["type"] in ("Person", "Incident") and "criminal_background" in allowed:
        ids = [obj["id"]] if obj["type"] == "Incident" else [x["id"] for x in out.get("criminal", {}).get("records", [])] + cluster
        if ids:
            iq = ",".join("?" * len(ids))
            fr = s.query(f"SELECT DISTINCT src FROM links WHERE type IN ('used_in','recovered_in','licensed_to') AND dst IN ({iq})", ids)
            arms = s.get_objects([r["src"] for r in fr])
            out["firearms"] = [c.summary(a) for a in arms.values() if c.decide(a).allow]
    # ---- pattern findings: leads about this entity in the user's tracks; other tracks only as a count
    rows = [dict(r) for r in s.query("SELECT * FROM pattern_hits WHERE status != 'dismissed'")]
    mine, others = [], Counter()
    reveal = set(c.case.scope) | set(cluster) if c.case else set(cluster)
    for r in rows:
        subj = set(json.loads(r["subjects"]))
        if not subj & set(cluster):
            continue
        if L.can_see(s, c.user, r):
            mine.append(L.render(s, r, reveal, c.summary, c.decide))
        else:
            for t in json.loads(r["tracks"]):
                others[t] += 1
    out["findings"] = mine
    out["deconfliction"] = {"other_track_leads": sum(others.values()), "tracks": dict(others)}
    out["withheld_sections"] = withheld
    if "timeline" in out:
        out["timeline"] = sorted([e for e in out["timeline"] if e.get("at")], key=lambda e: e["at"], reverse=True)
    return shown

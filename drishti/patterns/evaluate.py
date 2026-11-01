"""Score every detector against the planted ground truth and its benign look-alikes.

Only this module reads `synthetic_truth`; detectors never do (tests check). Each hit is classed as:
  hit         - touches a network planted for this detector;
  cross       - touches a network planted for another track (a correct lead, counted separately);
  benign      - touches a look-alike planted to tempt this detector (a designed-for false positive);
  background  - touches only the synthetic background population (an unplanned false positive).
Precision = (hit + cross) / all hits; recall = planted networks found / planted networks.
Synthetic results show the detectors behave as designed; they are not real-world accuracy.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from ..store import Store
from .engine import REGISTRY, Context, detect

DENOMINATORS = {
    "SMURFING_RING": ("SELECT COUNT(DISTINCT to_acct) n FROM txns WHERE from_acct IS NULL", "accounts with cash deposits"),
    "VICTIM_CONVERGENCE": ("SELECT COUNT(*) n FROM objects WHERE type='BankAccount'", "accounts"),
    "DORMANT_WAVE": ("SELECT COUNT(*) n FROM objects WHERE type='BankAccount'", "accounts"),
    "HAWALA_CORRIDOR": ("SELECT COUNT(DISTINCT to_acct) n FROM txns", "accounts with credits"),
    "SHELL_NETWORK": ("SELECT COUNT(*) n FROM objects WHERE type='Organisation'", "organisations"),
    "DENSE_MONEY_BLOCK": ("SELECT COUNT(*) n FROM objects WHERE type='BankAccount'", "accounts"),
    "SIM_BOX": ("SELECT COUNT(*) n FROM objects WHERE type='Phone'", "SIMs"),
    "HANDSET_CREW": ("SELECT COUNT(*) n FROM objects WHERE type='Device'", "handsets"),
    "BURNER_SUCCESSION": ("SELECT COUNT(*) n FROM objects WHERE type='Phone'", "SIMs"),
    "FOREIGN_HANDLER": ("SELECT COUNT(DISTINCT b_number) n FROM cdrs WHERE b_number LIKE '+%'", "foreign numbers"),
    "RECCE_REPETITION": ("SELECT COUNT(*) n FROM towers", "towers"),
    "CONVOY": ("SELECT COUNT(DISTINCT vehicle_id) n FROM tollhits", "vehicles read"),
    "CLONED_PLATE": ("SELECT COUNT(DISTINCT vehicle_id) n FROM tollhits", "vehicles read"),
    "STOLEN_VEHICLE_TRAIL": ("SELECT COUNT(*) n FROM links WHERE type='stolen_in'", "stolen vehicles"),
    "PRECURSOR_DIVERSION": ("SELECT COUNT(DISTINCT buyer_id || substance) n FROM procurements", "buyer-substance series"),
    "CONTINUING_UNLAWFUL_ACTIVITY": ("SELECT COUNT(DISTINCT src) n FROM links WHERE type='accused_in'", "accused records"),
    "WEAPON_LINKAGE": ("SELECT COUNT(*) n FROM objects WHERE type='Firearm'", "firearm records"),
    "TENDER_COLLUSION": ("SELECT COUNT(DISTINCT bidder_id) n FROM bids", "bidders"),
    "DISPROPORTIONATE_ASSETS": ("SELECT COUNT(*) n FROM links l JOIN objects o ON o.id=l.dst WHERE l.type='employee_of' "
                                "AND {json:o.props:kind}='department'", "public servants"),
}


def _flatten(x: Any) -> set[str]:
    out: set[str] = set()
    if isinstance(x, str):
        if ":" in x and not x.startswith(("http", "+")):
            out.add(x)
    elif isinstance(x, dict):
        for v in x.values():
            out |= _flatten(v)
    elif isinstance(x, (list, tuple, set)):
        for v in x:
            out |= _flatten(v)
    return out


def evaluate(store: Store, ctx: Context | None = None) -> dict[str, Any]:
    truth = store.get_meta("synthetic_truth") or {}
    missions = dict(truth.get("missions", {}))
    ops = truth.get("operations", {})
    if ops:
        # Each planted operation is scored against the detector built for its structure. The MULE ring (many
        # payers into a few aggregators) is a dense bipartite block. MIRAGE's shell money is two collectors into
        # a three-company round trip, below Fraudar's declared minimum of three payers; it is a shell network
        # (shared officers, nominees, cycles, money abroad) and is scored there. Until 2026-10-16 MIRAGE was
        # scored as a dense block and counted as that detector's one permanent miss.
        missions.setdefault("DENSE_MONEY_BLOCK", {"positives": [[*ops["MULE"]["mule_accounts"], *ops["MULE"]["aggregators"]]], "benign": []})
        shell = dict(missions.get("SHELL_NETWORK", {"positives": [], "benign": []}))
        if ops.get("MIRAGE", {}).get("shells"):
            shell["positives"] = [*shell.get("positives", []), list(ops["MIRAGE"]["shells"])]
        missions["SHELL_NETWORK"] = shell
    if ctx is None:
        ctx, timings = detect(store)
    else:
        timings = {}
    R = ctx.R
    canon = lambda ids: {R(i) for i in ids} | set(ids)  # noqa: E731
    planted = canon(_flatten(ops) | _flatten({k: v.get("positives", []) for k, v in missions.items() if isinstance(v, dict)}))
    rows = []
    for det_id, spec in REGISTRY.items():
        m = missions.get(det_id, {})
        units = [canon(u) for u in m.get("positives", [])]
        benign = [canon(u) for u in m.get("benign", [])]
        hits = ctx.hits.get(det_id, [])
        found = [False] * len(units)
        cls = {"hit": 0, "cross": 0, "benign": 0, "background": 0}
        examples: dict[str, list[str]] = {"benign": [], "background": []}
        for h in hits:
            subj = canon(h.subjects)
            matched = [i for i, u in enumerate(units) if subj & u]
            for i in matched:
                found[i] = True
            if matched:
                cls["hit"] += 1
            elif any(subj & b for b in benign):
                cls["benign"] += 1
                examples["benign"].append(h.title)
            elif subj & planted:
                cls["cross"] += 1
            else:
                cls["background"] += 1
                examples["background"].append(h.title)
        q, label = DENOMINATORS.get(det_id, ("SELECT 0 n", "records"))
        q = q.replace("{json:o.props:kind}", store.json_text("o.props", "kind"))
        eligible = store.query(q)[0]["n"] or 0
        fp = cls["benign"] + cls["background"]
        rows.append({
            "detector": det_id, "title": spec.title, "tracks": list(spec.tracks), "scope": spec.scope, "hits": len(hits), **cls,
            "planted": len(units), "found": sum(found), "recall": round(sum(found) / len(units), 3) if units else None,
            "precision": round((cls["hit"] + cls["cross"]) / len(hits), 3) if hits else None,
            "benign_lookalikes": len(benign), "eligible": eligible, "eligible_label": label,
            "false_leads_per_1000": round(1000 * fp / eligible, 3) if eligible else None,
            "seconds": timings.get(det_id), "examples": {k: v[:3] for k, v in examples.items() if v},
        })
    total_units = sum(r["planted"] for r in rows)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "detectors": rows,
        "summary": {
            "detectors": len(rows), "planted_networks": total_units, "found": sum(r["found"] for r in rows),
            "hits": sum(r["hits"] for r in rows), "benign_fired": sum(r["benign"] for r in rows),
            "background_false_leads": sum(r["background"] for r in rows),
            "recall": round(sum(r["found"] for r in rows) / total_units, 3) if total_units else None,
            "precision": round(sum(r["hit"] + r["cross"] for r in rows) / max(1, sum(r["hits"] for r in rows)), 3),
        },
        "caveat": "Synthetic data with planted networks; shows designed behaviour, not real-world accuracy.",
    }
    store.set_meta("pattern_evaluation", json.loads(json.dumps(report, default=str)))
    return report


def markdown(report: dict[str, Any]) -> str:
    lines = ["| Detector | Tracks | Planted found | Hits | Hit / cross / benign / background | Precision | False leads per 1,000 eligible |",
             "|---|---|---|---|---|---|---|"]
    for r in report["detectors"]:
        precision = "-" if r["precision"] is None else f"{r['precision']:.2f}"
        flp = "-" if r["false_leads_per_1000"] is None else r["false_leads_per_1000"]
        lines.append(f"| {r['title']} | {', '.join(r['tracks'])} | {r['found']}/{r['planted']} | {r['hits']} | "
                     f"{r['hit']} / {r['cross']} / {r['benign']} / {r['background']} | {precision} | {flp} ({r['eligible']:,} {r['eligible_label']}) |")
    s = report["summary"]
    lines.append(f"\n**Overall:** {s['found']}/{s['planted_networks']} planted networks found (recall {s['recall']}), "
                 f"precision {s['precision']} over {s['hits']} leads; {s['benign_fired']} benign look-alike(s) fired, "
                 f"{s['background_false_leads']} background false lead(s).")
    return "\n".join(lines)

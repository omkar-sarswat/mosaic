"""Adversary simulator: does a pattern survive the evasion a real network would try?

Each tactic copies the database, rewrites the planted networks the way an adversary who knows the
detector's description would (renaming payment references, registering the collector as a shop,
adding a layer account, staging incoming calls on a SIM box, spreading companies across addresses,
waiting longer before moving money, keeping a convoy further apart...), re-runs every detector and
compares recall with the untouched data. Some tactics are expected to fail against the detector
(the loophole is closed); others are expected to succeed (a known blind spot with its parameter)
and are reported as such. A tactic also must not create false leads among the background population.

Like evaluate.py, this reads the planted truth: it plays the adversary, who knows their own network.
"""

from __future__ import annotations

import hashlib
import json
import random
import gc
import tempfile
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from ..pgcompat import split_target
from ..store import Store
from .engine import detect
from .evaluate import evaluate

NEUTRAL = ["IMPS", "NEFT", "PAYMENT", "TRANSFER", "NA", "SELF", "MISC", "REF 1", "UPI"]


def _shift(ts: str, **kw: float) -> str:
    return (datetime.fromisoformat(ts) + timedelta(**kw)).isoformat(timespec="minutes")


def _accounts_of(conn: Any, persons: list[str]) -> list[str]:
    q = ",".join("?" * len(persons))
    return [r[0] for r in conn.execute(f"SELECT dst FROM links WHERE type='holds_account' AND src IN ({q})", persons)] if persons else []


def _missions(conn: Any) -> dict[str, Any]:
    row = conn.execute("SELECT value FROM meta WHERE key='synthetic_truth'").fetchone()
    return json.loads(row[0]) if row else {}


# ---------------------------------------------------------------------------- tactics
def narration_rewrite(conn: Any, truth: dict) -> str:
    rows = conn.execute("SELECT id FROM txns").fetchall()
    conn.executemany("UPDATE txns SET narration=? WHERE id=?",
                     [(NEUTRAL[int(hashlib.sha1(r[0].encode()).hexdigest(), 16) % len(NEUTRAL)], r[0]) for r in rows])
    return f"rewrote {len(rows):,} payment references to neutral words"


def protected_scramble(conn: Any, truth: dict) -> str:
    rng = random.Random(5)
    rows = [(r[0], json.loads(r[1])) for r in conn.execute("SELECT id, props FROM objects WHERE type='Person'")]
    keys = ["name", "name_native", "father_name", "gender", "dob", "birth_year", "city", "nationality", "occupation", "address"]
    pools = {k: [p.get(k) for _, p in rows] for k in keys}
    for k in keys:
        rng.shuffle(pools[k])
    upd = []
    for i, (oid, p) in enumerate(rows):
        for k in keys:
            if pools[k][i] is not None:
                p[k] = pools[k][i]
        upd.append((json.dumps(p, ensure_ascii=False), oid))
    conn.executemany("UPDATE objects SET props=? WHERE id=?", upd)
    return f"shuffled name, gender, age, city, nationality, occupation and address across {len(rows):,} person records"


def merchant_disguise(conn: Any, truth: dict) -> str:
    ops = truth.get("operations", {})
    m = truth.get("missions", {})
    orgs = set(ops.get("MIRAGE", {}).get("shells", [])) | {x for u in m.get("HAWALA_CORRIDOR", {}).get("positives", []) for x in u if x.startswith("organisation:")}
    hw = conn.execute("SELECT dst FROM links WHERE type='controls' AND src=?", (ops.get("MIRAGE", {}).get("hawala"),)).fetchall()
    orgs |= {r[0] for r in hw}
    n = 0
    for oid in orgs:
        r = conn.execute("SELECT props FROM objects WHERE id=?", (oid,)).fetchone()
        if r:
            p = json.loads(r[0])
            p["kind"] = "merchant"
            conn.execute("UPDATE objects SET props=? WHERE id=?", (json.dumps(p), oid))
            n += 1
    return f"re-registered {n} shell, hawala and collector companies as merchants"


def _insert_layers(conn: Any, txn_ids: list[str], layers: int, delay_h: float, tag: str) -> int:
    n = 0
    for tid in txn_ids:
        r = conn.execute("SELECT ts, from_acct, to_acct, amount, channel FROM txns WHERE id=?", (tid,)).fetchone()
        if not r or not r[2]:
            continue
        ts, frm, to, amt, ch = r
        hops = [f"bankaccount:{tag}-{tid}-{k}" for k in range(layers)]
        conn.execute("UPDATE txns SET to_acct=? WHERE id=?", (hops[0], tid))
        t = ts
        for k, acct in enumerate(hops):
            nxt = hops[k + 1] if k + 1 < len(hops) else to
            t = _shift(t, hours=delay_h)
            amt = round(amt * 0.98, -1)
            conn.execute("INSERT INTO txns(id,ts,from_acct,to_acct,amount,channel,narration,ref,country,source) VALUES(?,?,?,?,?,?,?,?,?,?)",
                         (f"{tid}-{tag}{k}", t, acct, nxt, amt, ch, "TRF", None, "IN", "REDTEAM"))
        n += 1
    return n


def _smurf_forwards(conn: Any, truth: dict) -> tuple[list[str], str]:
    unit = truth.get("missions", {}).get("SMURFING_RING", {}).get("positives", [[]])[0]
    persons = [x for x in unit if x.startswith("person:")]
    collector = next((x for x in unit if x.startswith("bankaccount:")), None)
    smurf_accts = set(_accounts_of(conn, persons)) - {collector}
    q = ",".join("?" * len(smurf_accts))
    ids = [r[0] for r in conn.execute(f"SELECT id FROM txns WHERE from_acct IN ({q}) AND to_acct IS NOT NULL", sorted(smurf_accts))] if smurf_accts else []
    return ids, collector or ""


def extra_layer(conn: Any, truth: dict) -> str:
    ids, _ = _smurf_forwards(conn, truth)
    mule = truth.get("operations", {}).get("MULE", {})
    q = ",".join("?" * len(mule.get("mule_accounts", [])))
    aggs = mule.get("aggregators", [])
    mids = [r[0] for r in conn.execute(f"SELECT id FROM txns WHERE from_acct IN ({q}) AND to_acct IN ({','.join('?' * len(aggs))})",
                                       [*mule.get("mule_accounts", []), *aggs])] if aggs else []
    n = _insert_layers(conn, ids, 1, 6, "L") + _insert_layers(conn, mids, 1, 6, "L")
    return f"routed {n} transfers through one extra layer account each (6 hours later)"


def two_extra_layers(conn: Any, truth: dict) -> str:
    ids, _ = _smurf_forwards(conn, truth)
    return f"routed {_insert_layers(conn, ids, 2, 6, 'LL')} smurf transfers through two extra layer accounts each"


def slow_forward(conn: Any, truth: dict, days: int = 4) -> str:
    ids, _ = _smurf_forwards(conn, truth)
    for tid in ids:
        ts = conn.execute("SELECT ts FROM txns WHERE id=?", (tid,)).fetchone()[0]
        conn.execute("UPDATE txns SET ts=? WHERE id=?", (_shift(ts, days=days), tid))
    # money the smurfs passed to a layer also leaves the layer later
    return f"held the cash {days} days before passing it on ({len(ids)} transfers)"


def sim_camouflage(conn: Any, truth: dict) -> str:
    unit = truth.get("missions", {}).get("SIM_BOX", {}).get("positives", [[]])[0]
    nums = [json.loads(r[0])["number"] for r in conn.execute(f"SELECT props FROM objects WHERE id IN ({','.join('?' * len(unit))})", unit)
            if "number" in json.loads(r[0])]
    callers = [r[0] for r in conn.execute("SELECT DISTINCT a_number FROM cdrs WHERE a_number NOT LIKE '+%' LIMIT 400")]
    rng = random.Random(3)
    rows = []
    for num in nums:
        out = conn.execute("SELECT ts FROM cdrs WHERE a_number=?", (num,)).fetchall()
        for k, (ts,) in enumerate(out[: max(1, len(out) * 15 // 100)]):
            rows.append((f"RT-{num}-{k}", _shift(ts, minutes=7), rng.choice(callers), num, rng.randint(200, 600), "voice", None, "", "REDTEAM"))
    conn.executemany("INSERT INTO cdrs(id,ts,a_number,b_number,duration_s,call_type,tower_id,legal_order,source) VALUES(?,?,?,?,?,?,?,?,?)", rows)
    return f"staged {len(rows)} incoming calls (15% of traffic) on {len(nums)} gateway SIMs"


def address_spread(conn: Any, truth: dict) -> str:
    shells = truth.get("operations", {}).get("MIRAGE", {}).get("shells", [])
    for oid in shells:
        conn.execute("DELETE FROM links WHERE type='registered_at' AND src=?", (oid,))
    return f"moved {len(shells)} shell companies to separate, unlinked addresses"


def convoy_gap(conn: Any, truth: dict, minutes: int = 15) -> str:
    unit = truth.get("missions", {}).get("CONVOY", {}).get("positives", [[None, None]])[0]
    pilot = unit[1]
    rows = conn.execute("SELECT id, ts FROM tollhits WHERE vehicle_id=?", (pilot,)).fetchall()
    for rid, ts in rows:
        conn.execute("UPDATE tollhits SET ts=? WHERE id=?", (_shift(ts, minutes=-minutes), rid))
    return f"kept the pilot car {minutes} minutes further ahead ({len(rows)} reads)"


def burner_new_circle(conn: Any, truth: dict) -> str:
    unit = truth.get("missions", {}).get("BURNER_SUCCESSION", {}).get("positives", [[None, None]])[0]
    r = conn.execute("SELECT props FROM objects WHERE id=?", (unit[1],)).fetchone()
    if not r:
        return "no successor"
    num = json.loads(r[0])["number"]
    strangers = [x[0] for x in conn.execute("SELECT DISTINCT b_number FROM cdrs WHERE b_number NOT LIKE '+%' LIMIT 500 OFFSET 200")]
    rows = conn.execute("SELECT id FROM cdrs WHERE a_number=?", (num,)).fetchall()
    rng = random.Random(9)
    for k, (cid,) in enumerate(rows):
        if k % 10 < 8:
            conn.execute("UPDATE cdrs SET b_number=? WHERE id=?", (rng.choice(strangers), cid))
    return f"successor SIM called mostly new people ({len(rows)} calls, 80% re-pointed)"


TACTICS: list[dict[str, Any]] = [
    {"id": "narration_rewrite", "fn": narration_rewrite, "expect": "caught", "targets": ["HAWALA_CORRIDOR", "SHELL_NETWORK", "SMURFING_RING", "VICTIM_CONVERGENCE", "DORMANT_WAVE", "DENSE_MONEY_BLOCK"],
     "label": "Neutral payment references", "loophole": "rules keyed to words like 'FABRIC' or 'CONSULTANCY'"},
    {"id": "protected_scramble", "fn": protected_scramble, "expect": "caught", "targets": "all",
     "label": "Scramble protected attributes", "loophole": "(fairness check) a detector that depends on who someone is"},
    {"id": "merchant_disguise", "fn": merchant_disguise, "expect": "caught", "targets": ["HAWALA_CORRIDOR", "SHELL_NETWORK", "VICTIM_CONVERGENCE", "SMURFING_RING"],
     "label": "Register the front as a shop", "loophole": "traces that stop at any account labelled 'merchant'"},
    {"id": "extra_layer", "fn": extra_layer, "expect": "caught", "targets": ["SMURFING_RING", "VICTIM_CONVERGENCE"],
     "label": "One more layer account", "loophole": "one-hop rules (deposit -> collector)"},
    {"id": "sim_camouflage", "fn": sim_camouflage, "expect": "caught", "targets": ["SIM_BOX"],
     "label": "Staged incoming calls on a SIM box", "loophole": "all-signs-must-hold gateway rules"},
    {"id": "address_spread", "fn": address_spread, "expect": "caught", "targets": ["SHELL_NETWORK"],
     "label": "Spread shells across addresses", "loophole": "shell rules keyed to a shared address"},
    {"id": "two_extra_layers", "fn": two_extra_layers, "expect": "caught", "targets": ["SMURFING_RING"],
     "label": "Two more layer accounts", "loophole": "fixed two-hop traces"},
    {"id": "slow_forward", "fn": slow_forward, "expect": "caught", "targets": ["SMURFING_RING"],
     "label": "Wait four days before moving cash", "loophole": "fixed 72-hour hop windows"},
    {"id": "convoy_gap", "fn": convoy_gap, "expect": "caught", "targets": ["CONVOY"],
     "label": "Pilot car 25-30 minutes ahead", "loophole": "fixed 20-minute convoy windows"},
    {"id": "slow_forward_long", "fn": lambda c, t: slow_forward(c, t, days=12), "expect": "evades", "targets": ["SMURFING_RING"],
     "label": "Wait twelve days before moving cash", "loophole": "known limit: seven-day hops at the wide scale"},
    {"id": "convoy_far", "fn": lambda c, t: convoy_gap(c, t, minutes=75), "expect": "evades", "targets": ["CONVOY"],
     "label": "Pilot car over an hour ahead", "loophole": "known limit: 60-minute wide window"},
    {"id": "burner_new_circle", "fn": burner_new_circle, "expect": "evades", "targets": ["BURNER_SUCCESSION"],
     "label": "Successor SIM calls new people", "loophole": "known limit: succession is found through shared contacts"},
]


def _recall(rep: dict, targets: list[str] | str) -> tuple[int, int, dict[str, str]]:
    found = planted = 0
    per = {}
    for r in rep["detectors"]:
        if targets == "all" or r["detector"] in targets:
            if r["planted"]:
                found += r["found"]
                planted += r["planted"]
                per[r["detector"]] = f"{r['found']}/{r['planted']}"
    return found, planted, per


def _scratch_target(store: Store, tmp: str, tag: str) -> Path | str:
    """A throwaway copy for one tactic: a file (SQLite) or a schema in the same database (PostgreSQL)."""
    if store.dialect == "sqlite":
        return Path(tmp) / f"{tag}.db"
    url, _ = split_target(store.target)
    return f"{url}?schema=rt_{hashlib.sha1(f'{store.schema}|{tag}'.encode()).hexdigest()[:12]}"


def run_redteam(store: Store, tactics: list[str] | None = None, log: Callable[..., Any] = print) -> dict[str, Any]:
    base = evaluate(store, detect(store)[0])
    out = []
    # ignore_cleanup_errors: on Windows a SQLite handle can outlive close() until its cursors are collected
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        for t in TACTICS:
            if tactics and t["id"] not in tactics:
                continue
            s2 = store.copy_to(_scratch_target(store, tmp, t["id"]))
            truth = _missions(s2.conn)
            s2.conn.execute("DELETE FROM pattern_hits")
            note = t["fn"](s2.conn, truth)
            rep = evaluate(s2, detect(s2)[0])
            s2.close()
            if s2.schema:
                store.conn.execute(f"DROP SCHEMA IF EXISTS {s2.schema} CASCADE")
            del s2
            gc.collect()  # release cursor-held handles so the tactic's database can be deleted
            b_found, b_planted, b_per = _recall(base, t["targets"])
            a_found, a_planted, a_per = _recall(rep, t["targets"])
            new_fp = rep["summary"]["background_false_leads"] - base["summary"]["background_false_leads"]
            outcome = "caught" if a_found == b_found else ("partly caught" if a_found else "evades")
            row = {"id": t["id"], "label": t["label"], "loophole": t["loophole"], "change": note, "expected": t["expect"], "outcome": outcome,
                   "as_designed": (outcome == "caught") == (t["expect"] == "caught"), "before": f"{b_found}/{b_planted}", "after": f"{a_found}/{a_planted}",
                   "per_detector_after": a_per, "per_detector_before": b_per, "new_background_false_leads": new_fp}
            out.append(row)
            log(f"{t['label']:42s} {row['before']:>6s} -> {row['after']:<6s} {outcome:14s} (expected {t['expect']}) {note}")
    report = {"tactics": out, "closed": sum(1 for r in out if r["expected"] == "caught" and r["outcome"] == "caught"),
              "known_limits_confirmed": sum(1 for r in out if r["expected"] == "evades" and r["outcome"] != "caught"),
              "surprises": [r["id"] for r in out if not r["as_designed"]]}
    store.set_meta("pattern_redteam", report)
    return report

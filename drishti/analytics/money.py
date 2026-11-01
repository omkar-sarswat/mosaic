"""Follow the money: account summaries, ledgers and multi-hop fund tracing.

Tracing follows funds hop by hop in time order. From an account, only transfers made after
the money arrived (and within a window) are followed, and value is apportioned: if an account
received Rs 10 lakh and sent out Rs 40 lakh, a quarter of each onward transfer is attributed
to the traced funds. Sinks end a path: cash withdrawal, retail spend, crypto exchange, or
an account abroad.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from ..store import Store

SINK_ORG_KINDS = {"merchant", "crypto_exchange"}


class Ledger:
    """In-memory view of the transaction table (fine to ~1M rows; DuckDB/Parquet beyond)."""

    def __init__(self, store: Store):
        self.store = store
        self.out: dict[str, list[tuple]] = defaultdict(list)
        self.inc: dict[str, list[tuple]] = defaultdict(list)
        self.by_id: dict[str, tuple] = {}
        for r in store.query("SELECT id, ts, from_acct, to_acct, amount, channel, narration, country FROM txns ORDER BY ts"):
            row = (r["id"], r["ts"], r["from_acct"], r["to_acct"], r["amount"], r["channel"], r["narration"], r["country"])
            self.by_id[row[0]] = row
            if r["from_acct"]:
                self.out[r["from_acct"]].append(row)
            if r["to_acct"]:
                self.inc[r["to_acct"]].append(row)
        self.holder: dict[str, str] = {}
        self.signatories: dict[str, list[str]] = defaultdict(list)
        for r in store.query("SELECT src, dst, type FROM links WHERE type IN ('holds_account','signatory_of')"):
            if r["type"] == "holds_account":
                self.holder[r["dst"]] = r["src"]
            else:
                self.signatories[r["dst"]].append(r["src"])
        self.kind: dict[str, str] = {}
        self.names: dict[str, str] = {}
        self.types: dict[str, str] = {}
        for r in store.query("SELECT id, type, title, props FROM objects WHERE type IN ('Person','Organisation','BankAccount','CryptoWallet')"):
            self.names[r["id"]] = r["title"]
            self.types[r["id"]] = r["type"]
            if r["type"] == "Organisation":
                self.kind[r["id"]] = json.loads(r["props"]).get("kind", "")
            elif r["type"] == "BankAccount":
                p = json.loads(r["props"])
                self.kind[r["id"]] = f"account:{p.get('country', 'IN')}:{p.get('account_type', '')}"

    def holder_of(self, acct: str) -> str | None:
        return self.holder.get(acct)

    def is_sink(self, acct: str | None) -> str | None:
        if acct is None:
            return "cash"
        h = self.holder.get(acct)
        if h and self.kind.get(h) in SINK_ORG_KINDS:
            return "crypto" if self.kind.get(h) == "crypto_exchange" else "retail"
        if self.kind.get(acct, "").startswith("account:") and not self.kind[acct].startswith("account:IN"):
            return "foreign"
        return None

    def label(self, acct: str | None) -> str:
        if acct is None:
            return "Cash"
        h = self.holder.get(acct)
        tail = self.names.get(acct, "")[-4:]
        return f"{self.names.get(h, '?')} ·{tail}" if h else acct


def entity_accounts(store: Store, oid: str, *, include_signatory: bool = True) -> list[str]:
    types = ("holds_account", "signatory_of") if include_signatory else ("holds_account",)
    q = ",".join("?" * len(types))
    return [r["dst"] for r in store.query(f"SELECT dst FROM links WHERE src=? AND type IN ({q})", (oid, *types))
            if r["dst"].startswith(("bankaccount:", "cryptowallet:"))]


def account_summary(ledger: Ledger, acct: str) -> dict[str, Any]:
    ins, outs = ledger.inc.get(acct, []), ledger.out.get(acct, [])
    cash_in = sum(t[4] for t in ins if t[2] is None)
    cash_out = sum(t[4] for t in outs if t[3] is None)
    monthly: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
    for t in ins:
        monthly[t[1][:7]][0] += t[4]
    for t in outs:
        monthly[t[1][:7]][1] += t[4]
    cps_in = defaultdict(float)
    for t in ins:
        cps_in[t[2] or "CASH"] += t[4]
    cps_out = defaultdict(float)
    for t in outs:
        cps_out[t[3] or "CASH"] += t[4]

    def top(d: dict[str, float]) -> list[dict[str, Any]]:
        return [{"account": k if k != "CASH" else None, "label": ledger.label(None if k == "CASH" else k),
                 "holder": ledger.holder.get(k), "amount": round(v, 2)} for k, v in sorted(d.items(), key=lambda kv: -kv[1])[:8]]

    return {
        "account": acct, "in_total": round(sum(t[4] for t in ins), 2), "out_total": round(sum(t[4] for t in outs), 2),
        "in_count": len(ins), "out_count": len(outs), "cash_in": round(cash_in, 2), "cash_out": round(cash_out, 2),
        "first": min([t[1] for t in ins + outs], default=None), "last": max([t[1] for t in ins + outs], default=None),
        "monthly": [{"month": m, "in": round(v[0], 2), "out": round(v[1], 2)} for m, v in sorted(monthly.items())],
        "top_senders": top(cps_in), "top_receivers": top(cps_out),
    }


def trace(ledger: Ledger, seeds: list[str], *, direction: str = "out", hops: int = 5, min_amount: float = 10_000,
          window_days: int = 60, max_links: int = 160) -> dict[str, Any]:
    fwd = direction == "out"
    window = timedelta(days=window_days)
    frontier: dict[str | None, tuple[float, str | None]] = {}
    for s in seeds:
        flows = (ledger.out if fwd else ledger.inc).get(s, [])
        amt = sum(t[4] for t in flows if t[4] >= min_amount)
        if amt:
            frontier[s] = (amt, None)
    edges: dict[tuple[str, str], list[float]] = defaultdict(lambda: [0.0, 0])
    sinks: dict[str, float] = defaultdict(float)
    depth: dict[str, int] = {s: 0 for s in frontier if s}
    for hop in range(1, hops + 1):
        nxt: dict[str | None, tuple[float, str | None]] = {}
        for acct, (avail, t0) in frontier.items():
            # cash, retail spend and crypto end a path; accounts abroad do not (round trips come back)
            if acct is None or (hop > 1 and ledger.is_sink(acct) in ("cash", "retail", "crypto")):
                continue
            rows = (ledger.out if fwd else ledger.inc).get(acct, [])
            sel = []
            for t in rows:
                if t[4] < min_amount:
                    continue
                if t0:
                    if fwd and not (t0 <= t[1] <= _plus(t0, window)):
                        continue
                    if not fwd and not (_minus(t0, window) <= t[1] <= t0):
                        continue
                sel.append(t)
            total = sum(t[4] for t in sel)
            if not total:
                continue
            ratio = min(1.0, avail / total)
            for t in sel:
                cp = t[3] if fwd else t[2]
                flow = t[4] * ratio
                key = (acct, cp or "CASH") if fwd else (cp or "CASH", acct)
                edges[key][0] += flow
                edges[key][1] += 1
                sink = ledger.is_sink(cp) if fwd else (None if cp else "cash")
                if sink:
                    sinks[sink] += flow
                if cp is not None and not (fwd and sink in ("cash", "retail", "crypto")):
                    prev = nxt.get(cp)
                    start = t[1] if prev is None or prev[1] is None else (min(prev[1], t[1]) if fwd else max(prev[1], t[1]))
                    nxt[cp] = ((prev[0] if prev else 0) + flow, start)
                    depth.setdefault(cp, hop)
        frontier = nxt
        if not frontier:
            break
    top_edges = sorted(edges.items(), key=lambda kv: -kv[1][0])[:max_links]
    nodes: dict[str, dict[str, Any]] = {}
    for (a, b), _ in top_edges:
        for n in (a, b):
            if n not in nodes:
                acct = None if n == "CASH" else n
                h = ledger.holder.get(acct) if acct else None
                nodes[n] = {"id": n, "label": ledger.label(acct), "holder": h, "holder_name": ledger.names.get(h, "") if h else "Cash",
                            "holder_type": ledger.types.get(h, "") if h else "", "kind": ledger.is_sink(acct) or "account",
                            "hop": depth.get(n, hops + 1)}
    links = [{"source": a, "target": b, "value": round(v[0], 2), "count": int(v[1])} for (a, b), v in top_edges]
    # where the money ended up, by holder
    ends: dict[str, float] = defaultdict(float)
    for (a, b), v in edges.items():
        n = b if fwd else a
        if n == "CASH":
            continue
        h = ledger.holder.get(n)
        if h:
            ends[h] += v[0]
    beneficiaries = [{"id": h, "name": ledger.names.get(h, h), "type": ledger.types.get(h, ""), "amount": round(v, 2)}
                     for h, v in sorted(ends.items(), key=lambda kv: -kv[1])[:15]]
    return {"direction": direction, "seeds": seeds, "nodes": list(nodes.values()), "links": links,
            "sinks": {k: round(v, 2) for k, v in sinks.items()}, "beneficiaries": beneficiaries,
            "traced_total": round(sum(v[0] for (a, b), v in edges.items() if a in seeds or b in seeds), 2),
            "accounts_reached": len({x for e in edges for x in e if x != "CASH"})}


def _plus(ts: str, d: timedelta) -> str:
    return (datetime.fromisoformat(ts) + d).isoformat(timespec="minutes")


def _minus(ts: str, d: timedelta) -> str:
    return (datetime.fromisoformat(ts) - d).isoformat(timespec="minutes")

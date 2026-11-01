"""Money-laundering and fraud typology detectors (FATF / FIU-IND / PMLA red flags).

Each rule produces explained alerts: which rule, why (numbers), and the evidence transactions.
Thresholds follow Indian reporting law where one exists:
  * Rs 50,000  PAN required for cash deposits (Income-tax Rule 114B) -> structuring just below it
  * Rs 2 lakh  cash receipt limit (Income-tax Act s.269ST)          -> cash-outs just below it
  * Rs 10 lakh monthly cash, Cash Transaction Report (PMLA Rules)    -> integrated cash
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from ..store import Store, utcnow
from .money import Ledger

SEVERITY_SCORE = {"high": 80, "medium": 55, "low": 30}
RULES = {
    "STRUCTURING_BELOW_PAN_LIMIT": "Repeated cash deposits just under Rs 50,000 (PAN threshold) - structuring",
    "CASH_OUT_BELOW_269ST": "Repeated cash withdrawals just under Rs 2 lakh (s.269ST limit)",
    "MULE_PASS_THROUGH": "New / min-KYC account receives from many senders and forwards almost everything within hours",
    "RAPID_LAYERING": "Large inflows leave the account within 72 hours (pass-through layering)",
    "ROUND_TRIPPING": "Funds return to the originating account through a chain of accounts",
    "CROWD_COLLECTION_CASH_OUT": "Many small credits from many people, then cash-out / onward transfer",
    "SHELL_COMPANY": "Company shows shell indicators (new, tiny capital, shared address/directors, nominee directors, flows far above turnover)",
    "INCOME_MISMATCH": "Money moved or assets held far exceed declared income",
    "HIGH_RISK_REMITTANCE": "Large cross-border transfers to / from a financial hub, including round trips",
    "CRYPTO_OFF_RAMP": "Transfers to a crypto exchange",
    "FRAUD_PROCEEDS": "Account named in fraud complaints or cases",
    "HAWALA_PATTERN": "Receives from many unrelated payers under trade narrations and withdraws the cash",
    "LOAN_DIVERSION": "Loan disbursed and diverted to related parties within weeks",
    "THIRD_PARTY_CONDUIT": "Low-income relative receives a large sum and passes it on to a family member",
    "RECEIVED_DIVERTED_LOAN": "Received funds diverted from a borrower's loan",
    "HIGH_VALUE_CASH_DEPOSITS": "Repeated high-value cash deposits inconsistent with the customer profile",
}


def _aid(rule: str, subject: str) -> str:
    return "alert:" + hashlib.sha1(f"{rule}|{subject}".encode()).hexdigest()[:16]


def _dt(ts: str) -> datetime:
    return datetime.fromisoformat(ts)


class Detector:
    def __init__(self, store: Store, ledger: Ledger | None = None):
        self.s = store
        self.L = ledger or Ledger(store)
        self.alerts: list[dict[str, Any]] = []
        self.objs = {r["id"]: (r["type"], json.loads(r["props"])) for r in store.query(
            "SELECT id, type, props FROM objects WHERE type IN ('BankAccount','Organisation','Person','CryptoWallet')")}

    def add(self, rule: str, subject: str, severity: str, summary: str, *, amount: float | None = None,
            evidence: list[str] | None = None, window: tuple[str, str] | None = None, extra: dict | None = None, bump: float = 0) -> None:
        self.alerts.append({
            "id": _aid(rule, subject), "rule": rule, "severity": severity, "subject_id": subject,
            "subject_type": self.objs.get(subject, ("?",))[0], "score": min(99.0, SEVERITY_SCORE[severity] + bump),
            "amount": round(amount, 2) if amount else None, "window_start": window[0] if window else None,
            "window_end": window[1] if window else None, "summary": summary,
            "details": {"rule_text": RULES[rule], "evidence_txns": (evidence or [])[:25], **(extra or {})},
        })

    # ------------------------------------------------------------------ account rules
    def run_accounts(self) -> None:
        L = self.L
        mentions = defaultdict(int)
        for r in self.s.query("SELECT l.dst FROM links l JOIN objects o ON o.id=l.src WHERE l.type='mentions' AND o.type='Incident'"):
            mentions[r["dst"]] += 1
        accounts = [k for k, v in self.objs.items() if v[0] == "BankAccount"]
        for a in accounts:
            props = self.objs[a][1]
            ins, outs = L.inc.get(a, []), L.out.get(a, [])
            holder = L.holder.get(a)
            hkind = L.kind.get(holder, "") if holder else ""
            if hkind in ("merchant", "department", "crypto_exchange") or props.get("account_type") == "loan" and not outs:
                continue
            # structuring
            cash_all = [t for t in ins if t[2] is None]
            cash_dep = [t for t in cash_all if 45_000 <= t[4] < 50_000]
            dense = max((sum(1 for u in cash_dep if timedelta(0) <= _dt(u[1]) - _dt(t[1]) <= timedelta(days=30)) for t in cash_dep), default=0)
            if len(cash_dep) >= 5 and dense >= 4 and len(cash_dep) >= 0.4 * len(cash_all):
                self.add("STRUCTURING_BELOW_PAN_LIMIT", a, "high",
                         f"{len(cash_dep)} cash deposits between Rs 45,000 and Rs 49,999 totalling Rs {sum(t[4] for t in cash_dep):,.0f}",
                         amount=sum(t[4] for t in cash_dep), evidence=[t[0] for t in cash_dep], window=(cash_dep[0][1], cash_dep[-1][1]),
                         bump=min(15, len(cash_dep) / 5))
            big_cash = [t for t in cash_all if t[4] >= 4_50_000]
            holder_income = self.objs.get(holder or "", ("", {}))[1].get("declared_income") if holder else None
            if len(big_cash) >= 3 and holder_income is not None and holder_income < 10_00_000:
                self.add("HIGH_VALUE_CASH_DEPOSITS", a, "medium",
                         f"{len(big_cash)} cash deposits of Rs 4.5 lakh+ (Rs {sum(t[4] for t in big_cash):,.0f}) against declared income Rs {holder_income:,.0f}",
                         amount=sum(t[4] for t in big_cash), evidence=[t[0] for t in big_cash], bump=5)
            cash_wd = [t for t in outs if t[3] is None and 1_80_000 <= t[4] < 2_00_000]
            if len(cash_wd) >= 4:
                self.add("CASH_OUT_BELOW_269ST", a, "high" if len(cash_wd) >= 8 else "medium",
                         f"{len(cash_wd)} cash withdrawals between Rs 1.8 and 2 lakh totalling Rs {sum(t[4] for t in cash_wd):,.0f}",
                         amount=sum(t[4] for t in cash_wd), evidence=[t[0] for t in cash_wd])
            # pass-through (mule) and rapid layering
            if ins:
                fwd_val, fwd_ev = 0.0, []
                outs_sorted = outs
                for t in ins:
                    t_in = _dt(t[1])
                    for o in outs_sorted:
                        dt = _dt(o[1]) - t_in
                        if timedelta(0) <= dt <= timedelta(hours=24) and o[4] >= 0.5 * t[4]:
                            fwd_val += min(o[4], t[4])
                            fwd_ev += [t[0], o[0]]
                            break
                tot_in = sum(t[4] for t in ins)
                senders = {t[2] for t in ins if t[2]}
                young = props.get("opened_on", "1900") >= (datetime.now() - timedelta(days=400)).date().isoformat()
                if len(ins) >= 3 and len(senders) >= 3 and tot_in and fwd_val / tot_in >= 0.75 and (young or props.get("kyc") == "min"):
                    self.add("MULE_PASS_THROUGH", a, "high",
                             f"{len(senders)} senders, Rs {tot_in:,.0f} in; {fwd_val / tot_in:.0%} forwarded within 24 h; account opened {props.get('opened_on')}, KYC {props.get('kyc')}",
                             amount=tot_in, evidence=fwd_ev, bump=10)
                big_in = [t for t in ins if t[4] >= 5_00_000]
                if sum(t[4] for t in big_in) >= 50_00_000:
                    moved = 0.0
                    for t in big_in:
                        t_in = _dt(t[1])
                        moved += min(t[4], sum(o[4] for o in outs if timedelta(0) <= _dt(o[1]) - t_in <= timedelta(hours=72)))
                    ratio = moved / sum(t[4] for t in big_in)
                    if ratio >= 0.6:
                        self.add("RAPID_LAYERING", a, "high" if ratio >= 0.8 else "medium",
                                 f"Rs {sum(t[4] for t in big_in):,.0f} of large credits; {ratio:.0%} moved out within 72 h",
                                 amount=sum(t[4] for t in big_in), evidence=[t[0] for t in big_in], bump=ratio * 10)
            # crowd collection
            small = [t for t in ins if t[4] <= 5000 and t[2]]
            if len(small) >= 40 and len({t[2] for t in small}) >= 30:
                cash_out = sum(t[4] for t in outs if t[3] is None) + sum(t[4] for t in outs if t[3] and self._is_flagged_hawala(t[3]))
                self.add("CROWD_COLLECTION_CASH_OUT", a, "high",
                         f"{len(small)} small credits from {len({t[2] for t in small})} people (Rs {sum(t[4] for t in small):,.0f}); Rs {cash_out:,.0f} cashed out or sent onward",
                         amount=sum(t[4] for t in small), evidence=[t[0] for t in small], bump=12)
            # remittance, crypto
            foreign_out = [t for t in outs if t[7] not in (None, "IN")]
            foreign_in = [t for t in ins if t[7] not in (None, "IN")]
            if sum(t[4] for t in foreign_out) >= 1_00_00_000 or sum(t[4] for t in foreign_in) >= 1_00_00_000:
                rt = bool(foreign_out and foreign_in) or any("SHARE APPLICATION" in (t[6] or "") for t in foreign_in)
                self.add("HIGH_RISK_REMITTANCE", a, "high",
                         f"Rs {sum(t[4] for t in foreign_out):,.0f} sent abroad, Rs {sum(t[4] for t in foreign_in):,.0f} received from abroad"
                         + (" (round trip as investment)" if rt else ""),
                         amount=sum(t[4] for t in foreign_out + foreign_in), evidence=[t[0] for t in foreign_out + foreign_in], bump=10 if rt else 0)
            crypto = [t for t in outs if t[3] and L.kind.get(L.holder.get(t[3], ""), "") == "crypto_exchange"]
            if sum(t[4] for t in crypto) >= 10_00_000:
                self.add("CRYPTO_OFF_RAMP", a, "medium", f"Rs {sum(t[4] for t in crypto):,.0f} sent to a crypto exchange in {len(crypto)} transfers",
                         amount=sum(t[4] for t in crypto), evidence=[t[0] for t in crypto])
            if mentions.get(a):
                n = mentions[a]
                self.add("FRAUD_PROCEEDS", a, "high" if n >= 2 else "medium", f"Named in {n} complaint(s) / case(s)",
                         amount=sum(t[4] for t in ins), bump=min(15, n))
            # hawala: many payers, trade narrations, cash out
            trade = [t for t in ins if t[2] and any(w in (t[6] or "") for w in ("FABRIC", "CLOTH", "GOODS"))]
            if len({t[2] for t in trade}) >= 3 and sum(t[4] for t in outs if t[3] is None) >= 0.5 * max(1, sum(t[4] for t in trade)):
                self.add("HAWALA_PATTERN", a, "high",
                         f"{len({t[2] for t in trade})} unrelated payers sent Rs {sum(t[4] for t in trade):,.0f} under trade narrations; "
                         f"Rs {sum(t[4] for t in outs if t[3] is None):,.0f} withdrawn in cash",
                         amount=sum(t[4] for t in trade), evidence=[t[0] for t in trade], bump=12)
            if props.get("account_type") == "loan" and outs:
                self._loan_diversion(a, outs)

    def _is_flagged_hawala(self, acct: str) -> bool:
        h = self.L.holder.get(acct, "")
        return self.L.kind.get(h) == "hawala_operator"

    def _loan_diversion(self, loan: str, disb: list[tuple]) -> None:
        L = self.L
        borrower = L.holder.get(loan)
        related = {r["dst"] for r in self.s.query("SELECT dst FROM links WHERE type='controls' AND src IN (SELECT src FROM links WHERE type='director_of' AND dst=?)", (borrower,))}
        related_accts = {a for a, h in L.holder.items() if h in related}
        total, diverted, ev = 0.0, 0.0, []
        for d in disb:
            total += d[4]
            t0 = _dt(d[1])
            for o in L.out.get(d[3], []):
                if o[3] in related_accts and timedelta(0) <= _dt(o[1]) - t0 <= timedelta(days=30):
                    diverted += o[4]
                    ev.append(o[0])
        recv: dict[str, float] = defaultdict(float)
        for d in disb:
            t0 = _dt(d[1])
            for o in L.out.get(d[3], []):
                if o[3] in related_accts and timedelta(0) <= _dt(o[1]) - t0 <= timedelta(days=30):
                    recv[o[3]] += o[4]
        for acct, amt in recv.items():
            self.add("RECEIVED_DIVERTED_LOAN", acct, "high", f"Received Rs {amt:,.0f} out of {self.L.names.get(borrower, 'the borrower')}'s loan within 30 days of disbursement",
                     amount=amt, bump=8)
        if total and diverted / total >= 0.3:
            self.add("LOAN_DIVERSION", loan, "high", f"Rs {total:,.0f} disbursed; Rs {diverted:,.0f} ({diverted / total:.0%}) moved to related parties within 30 days",
                     amount=diverted, evidence=ev, bump=15)
            if borrower:
                self.add("LOAN_DIVERSION", borrower, "high", f"Borrower diverted Rs {diverted:,.0f} of its term loan to related parties",
                         amount=diverted, evidence=ev, bump=15)

    # ------------------------------------------------------------------ entity rules
    def run_entities(self) -> None:
        s, L = self.s, self.L
        # accounts per holder, built once (scanning every account per entity was quadratic: 1.6 billion steps at 33k people)
        accounts_of: dict[str, list[str]] = defaultdict(list)
        for a, h in L.holder.items():
            accounts_of[h].append(a)
        directors = defaultdict(set)
        for r in s.query("SELECT src, dst FROM links WHERE type='director_of'"):
            directors[r["dst"]].add(r["src"])
        companies_of = defaultdict(set)
        for o, ds in directors.items():
            for d in ds:
                companies_of[d].add(o)
        addr_orgs = defaultdict(set)
        for r in s.query("SELECT src, dst FROM links WHERE type='registered_at'"):
            addr_orgs[r["dst"]].add(r["src"])
        org_addr = {o: a for a, os_ in addr_orgs.items() for o in os_}
        for oid, (typ, p) in self.objs.items():
            if typ != "Organisation" or p.get("kind") not in ("company", "shell_company", "trust"):
                continue
            ind, why = 0, []
            inc = p.get("incorporated_on", "1900-01-01")
            if inc >= (datetime.now() - timedelta(days=730)).date().isoformat():
                ind += 1
                why.append(f"incorporated {inc}")
            if (p.get("paid_up_capital") or 10**9) <= 1_00_000:
                ind += 1
                why.append(f"paid-up capital Rs {p.get('paid_up_capital'):,}")
            peers = addr_orgs.get(org_addr.get(oid, ""), set()) - {oid}
            if len(peers) >= 2:
                ind += 1
                why.append(f"shares its registered address with {len(peers)} other companies")
            ds = directors.get(oid, set())
            overlap = {c for d in ds for c in companies_of[d]} - {oid}
            if len(overlap) >= 2:
                ind += 1
                why.append(f"directors sit on {len(overlap)} other boards")
            nominee = [d for d in ds if (self.objs.get(d, ("", {}))[1].get("declared_income") or 0) < 3_00_000]
            if nominee:
                ind += 1
                why.append(f"{len(nominee)} director(s) with declared income under Rs 3 lakh (possible nominees)")
            credits = sum(t[4] for a in accounts_of.get(oid, ()) for t in L.inc.get(a, []))
            turnover = p.get("gst_turnover") or 0
            if credits >= 1_00_00_000 and credits > 20 * max(turnover, 1):
                ind += 1
                why.append(f"bank credits Rs {credits:,.0f} vs GST turnover Rs {turnover:,.0f}")
            if ind >= 3:
                self.add("SHELL_COMPANY", oid, "high" if ind >= 4 else "medium", "; ".join(why), amount=credits or None, bump=ind * 3,
                         extra={"indicators": ind})
        # people: income vs money and assets
        assets = defaultdict(float)
        for r in s.query("SELECT l.src, o.props FROM links l JOIN objects o ON o.id=l.dst WHERE l.type='owns' AND o.type IN ('Property','Vehicle')"):
            assets[r["src"]] += json.loads(r["props"]).get("value") or 0
        for oid, (typ, p) in self.objs.items():
            if typ != "Person" or "aadhaar" not in p:
                continue
            income = p.get("declared_income") or 0
            accts = accounts_of.get(oid, [])
            credits = sum(t[4] for a in accts for t in L.inc.get(a, []) if (t[6] or "") not in ("SALARY", "PENSION"))
            a_val = assets.get(oid, 0)
            if credits >= 50_00_000 and credits > 10 * max(income, 1):
                self.add("INCOME_MISMATCH", oid, "high", f"Rs {credits:,.0f} credited in a year against declared income Rs {income:,.0f}",
                         amount=credits, bump=min(15, credits / max(income, 1) / 10))
            elif a_val >= 50_00_000 and a_val > 20 * max(income, 1):
                self.add("INCOME_MISMATCH", oid, "high", f"Assets worth Rs {a_val:,.0f} against declared income Rs {income:,.0f}", amount=a_val, bump=8)
        # third-party conduit: low-income relative receives a large sum and passes it to family within a week
        rel = defaultdict(set)
        for r in s.query("SELECT src, dst FROM links WHERE type='relative_of'"):
            rel[r["src"]].add(r["dst"])
            rel[r["dst"]].add(r["src"])
        for oid, (typ, p) in self.objs.items():
            if typ != "Person" or (p.get("declared_income") or 0) > 3_00_000 or not rel.get(oid):
                continue
            for a in accounts_of.get(oid, []):
                for t in L.inc.get(a, []):
                    if t[4] < 10_00_000:
                        continue
                    for o in L.out.get(a, []):
                        if L.holder.get(o[3] or "") in rel[oid] and timedelta(0) <= _dt(o[1]) - _dt(t[1]) <= timedelta(days=7):
                            self.add("THIRD_PARTY_CONDUIT", oid, "high",
                                     f"Received Rs {t[4]:,.0f} ({t[6]}) and passed Rs {o[4]:,.0f} to a relative within {(_dt(o[1]) - _dt(t[1])).days} days",
                                     amount=o[4], evidence=[t[0], o[0]], bump=10)
                            self.add("THIRD_PARTY_CONDUIT", L.holder.get(o[3]), "high",
                                     f"Received Rs {o[4]:,.0f} from a low-income relative who had just been paid Rs {t[4]:,.0f}",
                                     amount=o[4], evidence=[t[0], o[0]], bump=12)

    # ------------------------------------------------------------------ cycles
    def run_cycles(self, max_len: int = 4, min_value: float = 5_00_000) -> None:
        graph = defaultdict(dict)
        for a, rows in self.L.out.items():
            for t in rows:
                if t[3] and t[4] >= min_value:
                    graph[a][t[3]] = graph[a].get(t[3], 0) + t[4]
        found: set[tuple[str, ...]] = set()
        for start in list(graph):
            stack = [(start, [start])]
            while stack:
                node, path = stack.pop()
                for nxt in graph.get(node, {}):
                    if nxt == start and len(path) >= 2:
                        cyc = tuple(path)
                        k = min(range(len(cyc)), key=lambda i: cyc[i])
                        found.add(cyc[k:] + cyc[:k])
                    elif nxt not in path and len(path) < max_len:
                        stack.append((nxt, path + [nxt]))
        for cyc in found:
            value = min(graph[cyc[i]][cyc[(i + 1) % len(cyc)]] for i in range(len(cyc)))
            names = " -> ".join(self.L.label(a) for a in cyc + (cyc[0],))
            for a in cyc:
                self.add("ROUND_TRIPPING", a, "high", f"Cycle of {len(cyc)} accounts moving at least Rs {value:,.0f}: {names}",
                         amount=value, bump=10, extra={"cycle": list(cyc)})

    def run(self) -> list[dict[str, Any]]:
        self.run_accounts()
        self.run_entities()
        self.run_cycles()
        merged: dict[str, dict[str, Any]] = {}
        for a in self.alerts:
            if a["subject_id"] is None:
                continue
            if a["id"] in merged:
                merged[a["id"]]["score"] = max(merged[a["id"]]["score"], a["score"])
                continue
            merged[a["id"]] = a
        return list(merged.values())


def run_typologies(store: Store, ledger: Ledger | None = None) -> dict[str, Any]:
    alerts = Detector(store, ledger).run()
    now = utcnow()
    with store.tx():
        store.execute("DELETE FROM alerts")
        store.executemany(
            "INSERT INTO alerts(id,rule,severity,subject_id,subject_type,score,amount,window_start,window_end,summary,details,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            [(a["id"], a["rule"], a["severity"], a["subject_id"], a["subject_type"], a["score"], a["amount"], a["window_start"],
              a["window_end"], a["summary"], json.dumps(a["details"]), now) for a in alerts])
    by_rule: dict[str, int] = defaultdict(int)
    for a in alerts:
        by_rule[a["rule"]] += 1
    return {"alerts": len(alerts), "by_rule": dict(by_rule)}

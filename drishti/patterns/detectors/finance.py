"""Money patterns: smurfing rings, victim-money convergence, dormant-account waves, hawala
corridors without tell-tale narrations, shell networks, and dense money blocks.

None of these read a narration. Words in a payment reference cost nothing to change, so a rule
that depends on "FABRIC" or "CONSULTANCY" is a rule a launderer can switch off. Every detector
here works on who paid whom, when, how much, and how fast it moved on."""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from statistics import median
from typing import Any

from ..algorithms import UnionFind, fraudar, temporal_cycles
from ..engine import Context, Hit, detector, dt, money, ref

# Reporting thresholds people structure around (Indian law): the band below each one is watched.
BANDS = [(50_000, "Income-tax Rule 114B: PAN required for cash deposits of Rs 50,000 or more"),
         (2_00_000, "Income-tax Act s.269ST: cash receipts of Rs 2 lakh or more barred"),
         (10_00_000, "PMLA Rules: Cash Transaction Report for Rs 10 lakh or more in a month")]
BAND_LOW = 0.88


def _band(amount: float) -> int | None:
    for t, _ in BANDS:
        if BAND_LOW * t <= amount < t:
            return t
    return None


# Scales: (hops, hours per hop, min depositors, min deposits). The wide scale needs a bigger ring, so
# waiting longer or adding layers does not hide a ring unless it is also small.
SMURF_SCALES = [(2, 72, 4, 8), (4, 24 * 7, 6, 10)]


@detector(
    id="SMURFING_RING", version="1.0", title="Smurfing ring", tracks=["money", "cyber_fraud", "organised_crime"], scope="population",
    question="Do several people each deposit cash just under a reporting threshold and pass it, within hours, to the same place?",
    inputs=["txns.amount", "txns.ts", "txns.from_acct", "txns.to_acct", "holds_account", "signatory_of", "same_as", "Organisation.kind"],
    algorithm=("Mark cash deposits in the band 88-100% of each statutory threshold. From each one, follow the money forward in time, "
               "each hop carrying at least half the deposit, at two scales: 2 hops within 72 hours a hop (ring of 4+ depositors and 8+ "
               "deposits) and 4 hops within 7 days a hop (6+ depositors, 10+ deposits). Aggregate at every account reached by distinct "
               "depositor identity, split into waves by gaps over 21 days; accounts joined by traced flows form one ring, and the account "
               "where most deposits converge is the collector."),
    evasion=["Splitting the deposits across many people so no single account crosses a per-account rule",
             "Adding layer accounts between the depositors and the collector (up to four hops at the wide scale)",
             "Waiting days before moving the cash (seven-day hops at the wide scale)",
             "Varying the amounts inside the band instead of repeating one figure",
             "Using different branches and cities (the ring is found by where money converges, not where it entered)"],
    benign=["People saving cash near the limit in their own accounts and keeping it (no convergence)",
            "Shopkeepers depositing takings (amounts spread across the range; no forward)"],
    blind_spots=["Cash carried physically to the collector never enters the banking trail",
                 "Rings that wait more than seven days a hop or use five or more layers", "Rings of three or fewer depositors"],
    references=["FATF, Money laundering through structuring (typology reports)", "Income-tax Rules 1962 r.114B; Income-tax Act s.269ST; PML (Maintenance of Records) Rules 2005"],
    complexity="O(D * b^h) for D banded deposits, branching b inside the hop window, h <= 4",
)
def smurfing_ring(ctx: Context) -> list[Hit]:
    seen: set[str] = set()
    hits = []
    for hops, hours, min_dep, min_n in SMURF_SCALES:
        for h in _smurfing_at(ctx, hops, hours, min_dep, min_n):
            if not set(h.subjects) & seen:
                hits.append(h)
                seen |= set(h.subjects)
    return hits


def _smurfing_at(ctx: Context, hops: int, hours: int, min_dep: int, min_n: int) -> list[Hit]:
    L, hub = ctx.L, ctx.hub_accounts
    reached: dict[str, list[dict[str, Any]]] = defaultdict(list)
    flow_edges: set[tuple[str, str]] = set()
    for acct, rows in L.inc.items():
        if acct in hub:
            continue
        for t in rows:
            if t[2] is not None or t[3] is None:
                continue
            thr = _band(t[4])
            if not thr:
                continue
            depositor = ctx.acct_identity(acct) or acct
            frontier = [(acct, dt(t[1]), t[4], [t[0]])]
            for _hop in range(hops):
                nxt = []
                for a, t0, amt, path in frontier:
                    for o in L.out.get(a, ()):
                        if o[3] is None or o[3] in hub or o[4] < 0.5 * amt:
                            continue
                        to = dt(o[1])
                        if timedelta(0) < to - t0 <= timedelta(hours=hours):
                            nxt.append((o[3], to, min(o[4], amt), path + [o[0]]))
                            flow_edges.add((a, o[3]))
                for a, _t1, _amt, path in nxt:
                    reached[a].append({"depositor": depositor, "account": acct, "deposit": t[0], "ts": t[1], "amount": t[4],
                                       "threshold": thr, "path": path})
                frontier = nxt
    candidates: dict[str, dict[str, Any]] = {}
    for a, items in reached.items():
        items.sort(key=lambda i: i["ts"])
        waves, cur = [], [items[0]]
        for i in items[1:]:
            if dt(i["ts"]) - dt(cur[-1]["ts"]) > timedelta(days=21):
                waves.append(cur)
                cur = [i]
            else:
                cur.append(i)
        waves.append(cur)
        good = []
        for wv in waves:
            uniq = {i["deposit"]: i for i in wv}
            deps = {i["depositor"] for i in uniq.values()} - {ctx.acct_identity(a) or a}
            if len(deps) >= min_dep and len(uniq) >= min_n and sum(i["amount"] for i in uniq.values()) >= 3_00_000:
                good.append(list(uniq.values()))
        if good:
            candidates[a] = {"waves": good}
    if not candidates:
        return []
    uf = UnionFind(candidates)
    for a, b in flow_edges:
        if a in candidates and b in candidates:
            uf.union(a, b)
    hits = []
    for grp in uf.groups():
        inner_sources = {x for x, y in flow_edges if x in grp and y in grp}
        # the collector is where most deposits converge; ties go to the account that passes nothing on inside the ring
        collector = max(grp, key=lambda a: (sum(len(w) for w in candidates[a]["waves"]), a not in inner_sources, a))
        waves = candidates[collector]["waves"]
        items = [i for w in waves for i in w]
        deps = sorted({i["depositor"] for i in items})
        dep_accts = sorted({i["account"] for i in items})
        per_acct: dict[str, int] = defaultdict(int)  # most banded deposits by one account within one wave
        for w in waves:
            counts: dict[str, int] = defaultdict(int)
            for i in w:
                counts[i["account"]] += 1
            for k, v in counts.items():
                per_acct[k] = max(per_acct[k], v)
        mids = sorted({x for i in items for x in _path_accounts(L, i["path"])} - set(dep_accts) - {collector})
        total = sum(i["amount"] for i in items)
        thr = items[0]["threshold"]
        coll_id = ctx.acct_identity(collector)
        hits.append(Hit(
            "SMURFING_RING", key=f"collector:{collector}", severity="high" if len(deps) >= 6 or total >= 10_00_000 else "medium",
            title=f"Smurfing ring: {len(deps)} depositors feeding one collector",
            summary=(f"{len(items)} cash deposits of {money(BAND_LOW * thr)}-{money(thr - 1)} (just under the {money(thr)} threshold) by "
                     f"{len(deps)} different people reached {ref(collector)}" + (f" held by {ref(coll_id)}" if coll_id else "")
                     + f" within {hours} hours a hop over at most {hops} hops, in {len(waves)} wave(s); {money(total)} in all. No depositor made "
                     f"more than {max(per_acct.values())} such deposits in a wave, so no per-account rule would fire"
                     + (f"; {len(mids)} intermediate account(s) were used as layers." if mids else ".")),
            subjects=[x for x in dict.fromkeys([coll_id, collector, *mids, *[ctx.acct_identity(m) for m in mids], *deps]) if x],
            evidence={"txns": sorted({p for i in items for p in i["path"]})[:150], "accounts": dep_accts},
            measurements={"depositors": len(deps), "banded_deposits": len(items), "total": round(total), "waves": len(waves),
                          "max_per_account": max(per_acct.values()), "layer_accounts": len(mids), "scale": f"{hops} hops x {hours} h"},
            thresholds={"band": f"{int(BAND_LOW * 100)}-100% of {thr}", "scales": [list(x) for x in SMURF_SCALES], "min_total": 300000},
            window=(items[0]["ts"], items[-1]["ts"])))
    return hits


def _path_accounts(L, path: list[str]) -> list[str]:
    """Accounts the money passed through on a traced path (the receivers of every hop but the last)."""
    out = []
    for tid in path[1:]:
        t = L.by_id.get(tid)
        if t and t[3]:
            out.append(t[3])
    return out[:-1]


@detector(
    id="VICTIM_CONVERGENCE", version="1.0", title="Victim money convergence", tracks=["cyber_fraud", "money"], scope="seeded",
    question="Where does money taken from different complainants end up together?",
    inputs=["complainant_in", "victim_in", "Incident.occurred_at", "txns", "holds_account", "signatory_of", "Organisation.kind"],
    algorithm=("Seed with each complainant's outgoing transfers in the reported fraud window (one day before to three days after the "
               "complaint's time). Propagate a victim set forward along time-respecting transfers (up to five hops, seven days a hop, "
               "each hop carrying at least 30% of what arrived). An account reached by three or more different victims is a convergence "
               "point; points joined by traced flows form one network. Regulated institutions and accounts that behave like shops (50+ "
               "payers, money stays) are not followed; a 'merchant' label alone does not stop the trace."),
    evasion=["Rotating mule accounts so each receives from only one or two victims", "Adding hops between mules and the collector",
             "Mixing victim money with ordinary credits (only flows that leave after the victim money arrived are followed)",
             "Registering the collecting account as a merchant (hubs are recognised by behaviour, not by label)"],
    benign=["A shop where victims also buy groceries (outside the fraud window, and shop-like by behaviour)"],
    blind_spots=["Victims who have not complained", "Cash withdrawn by the first mule ends the trail"],
    references=["I4C / NCRP Citizen Financial Cyber Fraud Reporting System (golden-hour tracing)", "Time-respecting paths: Holme & Saramaki, Temporal networks (2012)"],
    complexity="O(V * E_window) victim-set propagation, bounded by 5 hops",
)
def victim_convergence(ctx: Context) -> list[Hit]:
    L, hub = ctx.L, ctx.hub_accounts
    reach: dict[str, dict[str, tuple]] = defaultdict(dict)  # acct -> victim -> (arrival, amount, txn)
    edges: set[tuple[str, str]] = set()
    victim_accts: set[str] = set()
    frontier = []
    for v, incs in ctx.victims.items():
        accts = ctx.accounts_of.get(v, set())
        victim_accts |= accts
        for inc in incs:
            t_inc = ctx.incident_time(inc)
            if not t_inc:
                continue
            for a in accts:
                for o in L.out.get(a, ()):
                    if o[3] and o[3] not in hub and o[3] not in accts and o[4] >= 5_000:
                        if -timedelta(days=1) <= dt(o[1]) - t_inc <= timedelta(days=3):
                            frontier.append((o[3], v, dt(o[1]), o[4], o[0], a))
    for _hop in range(5):
        nxt = []
        for acct, v, t0, amt, tid, src in frontier:
            if v in reach[acct]:
                continue
            reach[acct][v] = (t0, amt, tid)
            edges.add((src, acct))
            for o in L.out.get(acct, ()):
                if o[3] is None or o[3] in hub:
                    continue
                to = dt(o[1])
                if timedelta(0) < to - t0 <= timedelta(days=7) and o[4] >= max(5_000, 0.3 * amt):
                    nxt.append((o[3], v, to, min(amt, o[4]), o[0], acct))
        frontier = nxt
    conv = {a for a, vs in reach.items() if len(vs) >= 3 and a not in victim_accts}
    if not conv:
        return []
    uf = UnionFind(conv)
    for a, b in edges:
        if a in conv and b in conv:
            uf.union(a, b)
    hits = []
    for grp in uf.groups():
        victims = {v for a in grp for v in reach[a]}
        first = sorted(a for a in grp if not any(x in grp for x, y in edges if y == a))
        deepest = max(grp, key=lambda a: (len(reach[a]), a))
        txns = sorted({reach[a][v][2] for a in grp for v in reach[a]})
        holders = sorted({h for h in (ctx.acct_identity(a) for a in grp) if h})
        value = sum(max(x[1] for x in (reach[a][v] for a in grp if v in reach[a])) for v in victims)
        first_seen = min(reach[a][v][0] for a in grp for v in reach[a])
        last_seen = max(reach[a][v][0] for a in grp for v in reach[a])
        hits.append(Hit(
            "VICTIM_CONVERGENCE", key="conv:" + ",".join(sorted(grp))[:400], severity="high" if len(victims) >= 5 else "medium",
            title=f"Money from {len(victims)} complainants converges",
            summary=(f"Money from {len(victims)} different complainants, traced forward in time, converges in {len(grp)} account(s) held by "
                     f"{len(holders)} party(ies); the largest point, {ref(deepest)} held by {ref(ctx.acct_identity(deepest))}, received from "
                     f"{len(reach[deepest])} victims. About {money(value)} of reported losses passed through."),
            subjects=[*holders, *sorted(grp)],
            evidence={"txns": txns[:150], "first_convergence_accounts": first, "victims": sorted(victims)[:60]},
            measurements={"victims": len(victims), "convergence_accounts": len(grp), "max_victims_at_one_account": len(reach[deepest]),
                          "value": round(value)},
            thresholds={"min_victims_at_account": 3, "hop_window_days": 7, "max_hops": 5, "min_share_per_hop": 0.3},
            window=(first_seen.isoformat(timespec="minutes"), last_seen.isoformat(timespec="minutes"))))
    return hits


@detector(
    id="DORMANT_WAVE", version="1.0", title="Dormant accounts woken together", tracks=["cyber_fraud", "money"], scope="population",
    question="Do several long-idle accounts come alive in the same weeks and pay the same people?",
    inputs=["txns", "holds_account", "Organisation.kind"],
    algorithm=("Find reactivations: an idle gap of 180+ days followed by Rs 1 lakh+ of credits within 14 days. Link two reactivations when "
               "they are within 21 days of each other and share a counterparty (a payer or a receiver within 30 days). Report linked "
               "groups of three or more accounts."),
    evasion=["Renting old, KYC-clean accounts instead of opening new ones (new-account rules miss them)",
             "Spreading the group across cities and banks (linked by shared counterparties, not location)"],
    benign=["A single dormant account woken by an insurance maturity or a property sale, with its own counterparties"],
    blind_spots=["Rented accounts used one at a time, months apart", "Counterparties that are themselves rotated"],
    references=["RBI Master Direction on KYC (2016, updated): inoperative accounts", "FIU-IND red flag indicators for banks"],
    complexity="O(A log A + R^2) for A accounts and R reactivations (R is small)",
)
def dormant_wave(ctx: Context) -> list[Hit]:
    L, hub = ctx.L, ctx.hub_accounts
    events = []
    for acct in set(L.inc) | set(L.out):
        if acct in hub:
            continue
        ins, outs = L.inc.get(acct, []), L.out.get(acct, [])
        seq = sorted([t[1] for t in ins] + [t[1] for t in outs])
        for prev, nxt in zip(seq, seq[1:]):
            gap = (dt(nxt) - dt(prev)).days
            if gap < 180:
                continue
            t0 = dt(nxt)
            credits = [t for t in ins if timedelta(0) <= dt(t[1]) - t0 <= timedelta(days=14)]
            if sum(t[4] for t in credits) < 1_00_000:
                continue
            outs30 = [t for t in outs if timedelta(0) <= dt(t[1]) - t0 <= timedelta(days=30)]
            cps = {t[2] for t in credits if t[2]} | {t[3] for t in outs30 if t[3]}
            events.append({"acct": acct, "t": t0, "gap": gap, "in": sum(t[4] for t in credits), "out": sum(t[4] for t in outs30),
                           "cps": cps - hub, "txns": [t[0] for t in credits + outs30]})
            break
    uf = UnionFind(range(len(events)))
    for i, a in enumerate(events):
        for j in range(i + 1, len(events)):
            b = events[j]
            if abs((a["t"] - b["t"]).days) <= 21 and a["cps"] & b["cps"]:
                uf.union(i, j)
    hits = []
    for grp in uf.groups():
        if len(grp) < 3:
            continue
        ev = [events[i] for i in sorted(grp)]
        shared = set.intersection(*[e["cps"] for e in ev]) if len(ev) > 1 else set()
        common = defaultdict(int)
        for e in ev:
            for c in e["cps"]:
                common[c] += 1
        hubs_of_group = sorted([c for c, n in common.items() if n >= 2], key=lambda c: -common[c])[:5]
        owners = sorted({h for h in (ctx.acct_identity(e["acct"]) for e in ev) if h})
        recv = sorted({h for h in (ctx.acct_identity(c) for c in hubs_of_group) if h})
        t1, t2 = min(e["t"] for e in ev), max(e["t"] for e in ev)
        hits.append(Hit(
            "DORMANT_WAVE", key="wave:" + ",".join(sorted(e["acct"] for e in ev)), severity="high" if len(ev) >= 5 else "medium",
            title=f"{len(ev)} dormant accounts woke within {(t2 - t1).days + 1} days",
            summary=(f"{len(ev)} accounts idle for {min(e['gap'] for e in ev)}-{max(e['gap'] for e in ev)} days received {money(sum(e['in'] for e in ev))} "
                     f"between {t1:%d %b} and {t2:%d %b %Y} and passed {money(sum(e['out'] for e in ev))} on; they share "
                     f"{len(hubs_of_group)} counterpart account(s), chiefly {ref(hubs_of_group[0]) if hubs_of_group else 'none'}"
                     + (f" held by {ref(recv[0])}" if recv else "") + "."),
            subjects=[*recv, *hubs_of_group, *owners, *[e["acct"] for e in ev]],
            evidence={"txns": [t for e in ev for t in e["txns"]][:150], "shared_counterparties": hubs_of_group},
            measurements={"accounts": len(ev), "credited": round(sum(e["in"] for e in ev)), "forwarded": round(sum(e["out"] for e in ev)),
                          "span_days": (t2 - t1).days, "common_to_all": len(shared)},
            thresholds={"idle_days": 180, "credit_within_14d": 100000, "co_wake_days": 21, "min_accounts": 3},
            window=(t1.isoformat(timespec="minutes"), t2.isoformat(timespec="minutes"))))
    return hits


def _pass_through(ins: list[tuple], outs: list[tuple], hours: int = 72) -> float:
    """Share of inflow matched, first in first out, by outflow leaving within `hours` of its arrival."""
    if not ins:
        return 0.0
    window = timedelta(hours=hours)
    queue = [[dt(t[1]), t[4]] for t in sorted(ins, key=lambda t: t[1])]
    head, matched = 0, 0.0
    for o in sorted(outs, key=lambda t: t[1]):
        to, need = dt(o[1]), o[4]
        while head < len(queue) and (to - queue[head][0] > window or queue[head][1] <= 0):
            head += 1
        k = head
        while need > 0 and k < len(queue) and queue[k][0] <= to:
            if to - queue[k][0] <= window and queue[k][1] > 0:
                take = min(need, queue[k][1])
                queue[k][1] -= take
                need -= take
                matched += take
            k += 1
    return matched / sum(t[4] for t in ins)


@detector(
    id="HAWALA_CORRIDOR", version="1.0", title="Hawala collection point", tracks=["money", "terror", "external"], scope="population",
    question="Does an account take money from many unrelated payers and turn it straight into cash or a few onward transfers?",
    inputs=["txns.amount", "txns.ts", "txns.from_acct", "txns.to_acct", "txns.country", "holds_account", "relative_of", "resides_at",
            "Organisation.gst_turnover", "Person.declared_income", "BankAccount.branch"],
    algorithm=("For every account, whatever business it claims to be: distinct paying identities, share of inflow matched FIFO by "
               "outflow within 72 hours, share of outflow that is cash or goes to three or fewer counterparties, share of round-figure "
               "credits, and throughput against declared turnover or income. A retail collection point needs 10+ unrelated payers, 70%+ "
               "pass-through and two of the other three signs; a wholesale cash-out point needs 3+ payers, Rs 50 lakh+, 60%+ cash and 60%+ "
               "pass-through. The corridor is reported as payer cities -> collector -> where the money went."),
    evasion=["Neutral payment references ('IMPS', 'PAYMENT') instead of trade words - the detector never reads narrations",
             "Registering the collector as a merchant or travel agent - business type is ignored, behaviour is measured",
             "Many small payers instead of a few large ones (payer count is a signal, not a hiding place)"],
    benign=["A charity collecting small donations and paying suppliers and staff over weeks",
            "A shop with many customers and no matching outflows"],
    blind_spots=["Pure hawala with no banked leg on either side", "Settlement by mis-invoiced trade in goods that never touches these accounts"],
    references=["FATF (2013), The role of hawala and other similar service providers in ML/TF", "RBI / FIU-IND: indicators for unregistered money transfer"],
    complexity="O(T log T) over all transactions",
)
def hawala_corridor(ctx: Context) -> list[Hit]:
    L = ctx.L
    hits = []
    acct_branch = {k: v.get("branch") for k, v in ctx.props("BankAccount").items()}
    acct_country = {k: v.get("country", "IN") for k, v in ctx.props("BankAccount").items()}
    for acct, ins_all in L.inc.items():
        ins = [t for t in ins_all if t[2]]
        if len(ins) < 3:
            continue
        outs = L.out.get(acct, [])
        if not outs:
            continue
        me = ctx.acct_identity(acct)
        payers = {ctx.acct_identity(t[2]) or t[2] for t in ins} - {me}
        if len(payers) < 3:
            continue
        total_in = sum(t[4] for t in ins)
        total_out = sum(t[4] for t in outs)
        pt = _pass_through(ins, outs)
        cash = sum(t[4] for t in outs if t[3] is None)
        by_cp = defaultdict(float)
        for t in outs:
            if t[3]:
                by_cp[t[3]] += t[4]
        top3 = sum(sorted(by_cp.values(), reverse=True)[:3])
        concentrated = (cash + top3) / total_out if total_out else 0.0
        cash_share = cash / total_out if total_out else 0.0
        roundness = sum(1 for t in ins if t[4] % 5000 == 0) / len(ins)
        holder = L.holder.get(acct)
        declared = (ctx.org_attr(holder, "gst_turnover") if holder and holder.startswith("organisation:") else
                    ctx.person_attr(ctx.R(holder), "declared_income") if holder else None) or 0
        mismatch = total_in / max(float(declared), 1.0)
        fam_pairs = sum(1 for p in payers if ctx.family.get(p, set()) & payers)
        unrelated = 1 - fam_pairs / max(len(payers), 1)
        retail = len(payers) >= 10 and unrelated >= 0.8 and pt >= 0.7 and sum([concentrated >= 0.8, roundness >= 0.6, mismatch >= 3]) >= 2
        wholesale = len(payers) >= 3 and total_in >= 50_00_000 and cash_share >= 0.6 and pt >= 0.6 and mismatch >= 3
        if not (retail or wholesale):
            continue
        cities = defaultdict(float)
        for t in ins:
            cities[acct_branch.get(t[2]) or "?"] += t[4]
        dests = defaultdict(float)
        for t in outs:
            dests["cash" if t[3] is None else (acct_country.get(t[3]) if acct_country.get(t[3], "IN") != "IN" else acct_branch.get(t[3]) or "?")] += t[4]
        corridor = (" + ".join(c for c, _ in sorted(cities.items(), key=lambda x: -x[1])[:3]) + f" -> {acct_branch.get(acct) or '?'} -> "
                    + " + ".join(d for d, _ in sorted(dests.items(), key=lambda x: -x[1])[:3]))
        controllers = [ctx.R(a) for a, b, _ in [*ctx.links.get("controls", []), *ctx.links.get("signatory_of", [])] if b in (holder, acct)]
        hits.append(Hit(
            "HAWALA_CORRIDOR", key=f"collector:{acct}", severity="high",
            title=("Retail hawala collection point" if retail else "Wholesale cash-out point") + f" ({corridor})",
            summary=(f"{ref(acct)} held by {ref(holder)} took {money(total_in)} from {len(payers)} paying parties "
                     f"({unrelated:.0%} unrelated to each other); {pt:.0%} of it left within 72 hours, {cash_share:.0%} of outflow as cash"
                     f"{'' if retail else ''}. Throughput is {mismatch:.1f}x the declared {'turnover' if holder and holder.startswith('organisation:') else 'income'}"
                     f"{'' if declared else ' (none declared)'}; {roundness:.0%} of credits are round figures. Corridor: {corridor}."),
            subjects=[x for x in dict.fromkeys([holder, *controllers, acct]) if x],
            evidence={"txns": [t[0] for t in ins][:80] + [t[0] for t in outs][:80], "payers": sorted(payers)[:60]},
            measurements={"payers": len(payers), "unrelated_share": round(unrelated, 2), "inflow": round(total_in), "pass_through_72h": round(pt, 2),
                          "cash_share": round(cash_share, 2), "concentrated_outflow": round(concentrated, 2), "round_share": round(roundness, 2),
                          "throughput_vs_declared": round(mismatch, 1), "tier": "retail" if retail else "wholesale", "corridor": corridor},
            thresholds={"retail": "payers>=10, unrelated>=80%, pass-through>=70%, 2 of {concentrated>=80%, round>=60%, mismatch>=3x}",
                        "wholesale": "payers>=3, inflow>=Rs 50 lakh, cash>=60%, pass-through>=60%, mismatch>=3x"},
            window=(min(t[1] for t in ins), max(t[1] for t in outs))))
    return hits


SHELLISH = {"company", "shell_company", "trust", "foreign_company", "merchant", "hawala_operator", "other", "transport"}


@detector(
    id="SHELL_NETWORK", version="1.0", title="Shell-company network", tracks=["money", "corruption"], scope="population",
    question="Is a cluster of companies tied together by the same people and addresses moving money in ways their size cannot explain?",
    inputs=["director_of", "controls", "registered_at", "signatory_of", "uses_phone", "Organisation.incorporated_on",
            "Organisation.paid_up_capital", "Organisation.gst_turnover", "Person.declared_income", "txns"],
    algorithm=("Build the company graph from shared directors, controllers, signatories, registered addresses and contact numbers; take "
               "components of three or more companies. Score seven indicators: young, thin capital, shared addresses, nominee directors "
               "(low-income people on two or more boards), credits over ten times declared turnover, time-respecting money cycles among the "
               "companies and their controllers (each hop within the 60-day window, keeping half the value), and money sent abroad. Report "
               "components with three or more indicators of which at least one is about money."),
    evasion=["Spreading companies across addresses (directors and signatories still connect them)",
             "Nominee directors (low income on several boards is itself an indicator)",
             "Round trips through several companies (cycles are found at any length up to five, in time order)"],
    benign=["A long-established business group with common directors and one address, large capital, turnover that matches its "
            "bank credits, and money flowing one way from parent to subsidiaries"],
    blind_spots=["Companies with no common officers, address or contact in the registry", "Cycles that close after more than 60 days"],
    references=["MCA / SFIO shell-company indicators", "Kumar & Calders (2018) 2SCENT temporal cycle enumeration", "FATF/Egmont (2018) Concealment of beneficial ownership"],
    complexity="O(E) graph build + bounded temporal DFS per component",
)
def shell_network(ctx: Context) -> list[Hit]:
    kinds = ctx.org_kind
    orgs = {o for o, k in kinds.items() if k in SHELLISH}
    uf = UnionFind(orgs)
    officers: dict[str, set[str]] = defaultdict(set)
    for t in ("director_of", "controls"):
        for p, o, _ in ctx.links.get(t, ()):
            if o in orgs:
                officers[ctx.R(p)].add(o)
    for p, os_ in officers.items():
        os_ = sorted(os_)
        for o in os_[1:]:
            uf.union(os_[0], o)
    by_addr: dict[str, list[str]] = defaultdict(list)
    for o, loc, _ in ctx.links.get("registered_at", ()):
        if o in orgs:
            by_addr[loc].append(o)
    for os_ in by_addr.values():
        for o in os_[1:]:
            uf.union(os_[0], o)
    signers: dict[str, set[str]] = defaultdict(set)
    for p, a, _ in ctx.links.get("signatory_of", ()):
        h = ctx.L.holder.get(a)
        if h in orgs:
            signers[ctx.R(p)].add(h)
    for os_ in signers.values():
        os_ = sorted(os_)
        for o in os_[1:]:
            uf.union(os_[0], o)
    phones: dict[str, list[str]] = defaultdict(list)
    for o, ph, _ in ctx.links.get("uses_phone", ()):
        if o in orgs:
            phones[ph].append(o)
    for os_ in phones.values():
        for o in os_[1:]:
            uf.union(os_[0], o)
    hits = []
    oprops = ctx.props("Organisation")
    acct_country = {k: v.get("country", "IN") for k, v in ctx.props("BankAccount").items()}
    for comp in uf.groups():
        if len(comp) < 3:
            continue
        comp = sorted(comp)
        ages = [(ctx.today.date() - dt(oprops[o]["incorporated_on"]).date()).days for o in comp if oprops[o].get("incorporated_on")]
        caps = [oprops[o].get("paid_up_capital") for o in comp if oprops[o].get("paid_up_capital") is not None]
        people = {p for p, os_ in officers.items() if set(os_) & set(comp)} | {p for p, os_ in signers.items() if set(os_) & set(comp)}
        nominees = [p for p in people if len(officers.get(p, set()) & set(comp)) >= 2 and (ctx.person_attr(p, "declared_income") or 0) < 3_00_000]
        accts = {a for a, h in ctx.L.holder.items() if h in comp}
        ctrl_accts = {a for p in people for a in ctx.accounts_of.get(p, set())}
        credits = sum(t[4] for a in accts for t in ctx.L.inc.get(a, []) if t[2] not in accts)
        turnover = sum(oprops[o].get("gst_turnover") or 0 for o in comp)
        edges = [(t[2], t[3], t[1], t[4], t[0]) for a in accts | ctrl_accts for t in ctx.L.out.get(a, []) if t[3] in accts | ctrl_accts]
        cycles = temporal_cycles(edges, max_len=5, window=timedelta(days=60), min_amount=5_00_000, retain=0.5, limit=60)
        abroad = sum(t[4] for a in accts | ctrl_accts for t in ctx.L.out.get(a, []) if t[3] and acct_country.get(t[3], "IN") != "IN")
        foreign_cos = [o for o in comp if kinds.get(o) == "foreign_company"]
        shared_addr = max((len([o for o in os_ if o in comp]) for os_ in by_addr.values()), default=0)
        ind = {
            "young": bool(ages) and median(ages) < 3 * 365,
            "thin_capital": bool(caps) and median(caps) <= 5_00_000,
            "shared_address": shared_addr >= 2,
            "nominee_directors": bool(nominees),
            "credits_over_turnover": credits >= 1_00_00_000 and credits > 10 * max(turnover, 1),
            "time_respecting_cycles": bool(cycles),
            "money_abroad": abroad >= 50_00_000 or (bool(foreign_cos) and abroad > 0),
        }
        money_signs = ind["credits_over_turnover"] or ind["time_respecting_cycles"] or ind["money_abroad"]
        n = sum(ind.values())
        if n < 3 or not money_signs:
            continue
        cyc_txt = ""
        if cycles:
            c0 = cycles[0]
            cyc_txt = f" One round trip: {' -> '.join(ref(e[0]) for e in c0)} -> {ref(c0[0][0])} in {(dt(c0[-1][2]) - dt(c0[0][2])).days} days."
        hits.append(Hit(
            "SHELL_NETWORK", key="shells:" + ",".join(comp)[:400], severity="high" if n >= 5 else "medium",
            title=f"Shell network: {len(comp)} linked companies, {n} of 7 indicators",
            summary=(f"{len(comp)} companies tied by {len(people)} common officer(s)/signatories and shared addresses. Indicators: "
                     + ", ".join(k.replace("_", " ") for k, v in ind.items() if v)
                     + f". Bank credits {money(credits)} against declared turnover {money(turnover)}; {money(abroad)} sent abroad; "
                     f"{len(cycles)} time-respecting cycle(s).{cyc_txt}"),
            subjects=[*comp, *sorted(people)],
            evidence={"txns": sorted({e[4] for c in cycles for e in c})[:60], "nominees": sorted(nominees), "accounts": sorted(accts)},
            measurements={"companies": len(comp), "indicators": n, **{k: bool(v) for k, v in ind.items()}, "credits": round(credits),
                          "declared_turnover": round(turnover), "abroad": round(abroad), "cycles": len(cycles),
                          "median_age_days": int(median(ages)) if ages else None},
            thresholds={"min_companies": 3, "min_indicators": 3, "money_indicator_required": True, "cycle_window_days": 60}))
    return hits


@detector(
    id="DENSE_MONEY_BLOCK", version="1.0", title="Dense money block (Fraudar)", tracks=["money", "cyber_fraud"], scope="population",
    question="Is there a group of accounts paying a small set of accounts far more densely than ordinary customers do?",
    inputs=["txns.from_acct", "txns.to_acct", "txns.amount", "Organisation.kind"],
    algorithm=("Account-to-account transfer graph (hub accounts excluded, pairs with Rs 20,000+). Fraudar greedy peeling with column "
               "weights 1/log(in-degree + 5) finds the densest block; its edges are removed and the search repeats (up to five blocks). A "
               "block is reported when it has three or more paying and two or more receiving accounts, an average weight per node of 0.5+, "
               "at least three distinct holders, and money that moves on: the median payer or receiver passes 60%+ of its credits on "
               "within 72 hours."),
    evasion=["Camouflage: adding transfers to popular, ordinary accounts to look normal (popular columns are down-weighted)",
             "Splitting across many mule accounts (density is measured on the block, not per account)"],
    benign=["Many customers paying one merchant or charity (a star, not a dense block, and popular receivers weigh little)",
            "A business group's regular customers (dense, but the money stays)"],
    blind_spots=["Sparse layering where each account is used once", "Blocks smaller than three payers"],
    references=["Hooi, Song, Beutel, Shah, Shin & Faloutsos (2016), FRAUDAR: Bounding graph fraud in the face of camouflage, KDD"],
    complexity="O(E log V) per block",
)
def dense_money_block(ctx: Context) -> list[Hit]:
    L, hub = ctx.L, ctx.hub_accounts
    agg: dict[tuple[str, str], float] = defaultdict(float)
    for a, rows in L.out.items():
        if a in hub:
            continue
        for t in rows:
            if t[3] and t[3] not in hub and t[3] != a:
                agg[(a, t[3])] += t[4]
    edges = [(a, b, v) for (a, b), v in agg.items() if v >= 20_000]
    hits = []
    for k in range(5):
        res = fraudar(edges, min_rows=3, min_cols=2)
        if not res["rows"] or res["score"] < 0.5:
            break
        rows, cols = set(res["rows"]), set(res["cols"])
        holders = {ctx.acct_identity(x) or x for x in rows | cols}
        block_edges = [(a, b, v) for a, b, v in edges if a in rows and b in cols]
        edges = [e for e in edges if not (e[0] in rows and e[1] in cols)]
        if len(holders) < 3:
            continue
        # density alone also describes a group's regular customers; laundering money also moves on fast
        pt_rows = median([_pass_through([t for t in L.inc.get(x, []) if t[2]], L.out.get(x, [])) for x in rows])
        pt_cols = median([_pass_through([t for t in L.inc.get(x, []) if t[2]], L.out.get(x, [])) for x in cols])
        if max(pt_rows, pt_cols) < 0.6:
            continue
        value = sum(v for _, _, v in block_edges)
        hits.append(Hit(
            "DENSE_MONEY_BLOCK", key="block:" + ",".join(sorted(rows | cols))[:400], severity="medium",
            title=f"Dense money block: {len(rows)} payers x {len(cols)} receivers",
            summary=(f"{len(rows)} accounts paid {len(cols)} accounts {len(block_edges)} times over ({money(value)}), a block {res['score']:.2f} "
                     f"dense under camouflage-resistant weighting; {len(holders)} distinct holders. Receivers include "
                     + ", ".join(ref(c) for c in sorted(cols)[:3]) + "."),
            subjects=[*sorted({ctx.acct_identity(c) for c in cols} - {None}), *sorted(cols), *sorted(rows)],
            evidence={"accounts": sorted(rows | cols)},
            measurements={"payers": len(rows), "receivers": len(cols), "edges": len(block_edges), "value": round(value), "density": res["score"],
                          "holders": len(holders), "block_rank": k + 1, "payer_pass_through": round(pt_rows, 2), "receiver_pass_through": round(pt_cols, 2)},
            thresholds={"min_density": 0.5, "min_payers": 3, "min_receivers": 2, "min_holders": 3, "pair_min_value": 20000,
                        "min_pass_through_72h": 0.6}))
    return hits

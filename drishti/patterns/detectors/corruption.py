"""Corruption patterns: bid-rigging cartels in public procurement, and assets disproportionate to
a public servant's known income."""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from statistics import mean, pstdev

from ..algorithms import UnionFind
from ..engine import Context, Hit, detector, dt, money


def _screens(amounts: list[float], estimate: float | None) -> dict[str, float]:
    b = sorted(amounts)
    m = mean(b)
    cv = pstdev(b) / m if m else 0.0
    losing = b[1:]
    sd_l = pstdev(losing) if len(losing) >= 2 else 0.0
    rd = (b[1] - b[0]) / sd_l if sd_l else 0.0
    return {"cv": round(cv, 4), "rd": round(rd, 3), "gap": round((b[1] - b[0]) / b[0], 4), "win_vs_estimate": round(b[0] / estimate, 3) if estimate else 0.0}


@detector(
    id="TENDER_COLLUSION", version="1.0", title="Bid-rigging cartel", tracks=["corruption"], scope="population",
    question="Do the same firms keep bidding against each other with bids too close together, taking turns to win at the estimate?",
    inputs=["bids.amount", "bids.tender_id", "bids.bidder_id", "bids.submit_ip", "Tender.estimate", "director_of", "controls",
            "registered_at", "uses_phone"],
    algorithm=("Statistical screens per tender (Imhof, Karagok & Rutz 2018): coefficient of variation of bids, relative distance between the "
               "two lowest bids (gap over the spread of losing bids), and winning bid against the estimate. A tender is screen-positive with "
               "CV of 5% or less and either a relative distance of 1.2+ or a winning bid at 95%+ of the estimate. Firms that meet in two or "
               "more screen-positive tenders are grouped; a group of three or more with four or more such tenders is reported when it also "
               "shows rotation (wins spread across members), common officers/addresses/contacts, or bids from the same IP address."),
    evasion=["Different company names and directors for each cartel member (bidding behaviour and shared IPs/addresses still link them)",
             "Letting each member win in turn (rotation is itself a marker)"],
    benign=["Competitive tenders with dispersed bids and winners well below the estimate"],
    blind_spots=["Cartels that include genuinely independent outsiders in every tender", "Single-bidder tenders (no bid spread to screen)"],
    references=["Imhof, Karagok & Rutz (2018), Screening for bid rigging - does it work? J. Competition Law & Economics",
                "OECD (2009, rev. 2025), Guidelines for fighting bid rigging in public procurement",
                "Competition Act 2002 s.3(3)(d); CVC guidelines on tendering"],
    complexity="O(B) over bids + O(F^2) within co-bidding groups",
)
def tender_collusion(ctx: Context) -> list[Hit]:
    tenders = ctx.props("Tender")
    bids: dict[str, list[dict]] = defaultdict(list)
    for r in ctx.s.query("SELECT * FROM bids"):
        bids[r["tender_id"]].append(dict(r))
    positive: dict[str, dict] = {}
    for t, bs in bids.items():
        if len(bs) < 3:
            continue
        sc = _screens([b["amount"] for b in bs], tenders.get(t, {}).get("estimate"))
        if sc["cv"] <= 0.05 and (sc["rd"] >= 1.2 or sc["win_vs_estimate"] >= 0.95):
            positive[t] = sc
    meet: dict[tuple[str, str], int] = defaultdict(int)
    for t in positive:
        firms = sorted({b["bidder_id"] for b in bids[t]})
        for i, a in enumerate(firms):
            for b in firms[i + 1:]:
                meet[(a, b)] += 1
    uf = UnionFind()
    for (a, b), n in meet.items():
        if n >= 2:
            uf.union(a, b)
    officers: dict[str, set[str]] = defaultdict(set)
    for t in ("director_of", "controls"):
        for p, o, _ in ctx.links.get(t, ()):
            officers[o].add(ctx.R(p))
    addr: dict[str, str] = {o: loc for o, loc, _ in ctx.links.get("registered_at", ())}
    phones: dict[str, set[str]] = defaultdict(set)
    for o, ph, _ in ctx.links.get("uses_phone", ()):
        phones[o].add(ph)
    hits = []
    for grp in uf.groups():
        if len(grp) < 3:
            continue
        joint = sorted(t for t in positive if len({b["bidder_id"] for b in bids[t]} & grp) >= 3)
        if len(joint) < 4:
            continue
        winners = defaultdict(int)
        for t in joint:
            winners[min(bids[t], key=lambda b: b["amount"])["bidder_id"]] += 1
        rotation = len(winners) >= min(3, len(grp)) and max(winners.values()) / len(joint) <= 0.6
        links_found = []
        g = sorted(grp)
        for i, a in enumerate(g):
            for b in g[i + 1:]:
                if officers[a] & officers[b]:
                    links_found.append(("common officer", a, b, sorted(officers[a] & officers[b])))
                if addr.get(a) and addr.get(a) == addr.get(b):
                    links_found.append(("same registered address", a, b, [addr[a]]))
                if phones[a] & phones[b]:
                    links_found.append(("same contact number", a, b, sorted(phones[a] & phones[b])))
        same_ip = 0
        for t in joint:
            ips = defaultdict(set)
            for b in bids[t]:
                if b["bidder_id"] in grp and b["submit_ip"]:
                    ips[b["submit_ip"]].add(b["bidder_id"])
            same_ip += any(len(v) >= 2 for v in ips.values())
        if not (rotation or links_found or same_ip):
            continue
        people = sorted({p for kind, a, b, x in links_found if kind == "common officer" for p in x})
        value = sum(min(b["amount"] for b in bids[t]) for t in joint)
        avg = {k: round(mean(positive[t][k] for t in joint), 3) for k in ("cv", "rd", "win_vs_estimate")}
        hits.append(Hit(
            "TENDER_COLLUSION", key="cartel:" + ",".join(g), severity="high" if links_found and same_ip else "medium",
            title=f"Possible bid-rigging cartel: {len(grp)} firms, {len(joint)} tenders",
            summary=(f"{len(grp)} firms bid together in {len(joint)} tenders worth {money(value)} whose bids were tightly bunched (mean CV "
                     f"{avg['cv']:.1%}, winner {avg['win_vs_estimate']:.0%} of the estimate). "
                     + (f"Wins rotated among {len(winners)} of them. " if rotation else "")
                     + (f"{len(links_found)} ownership/contact tie(s) between them" + (f", through " + ", ".join(f"[[{p}]]" for p in people) if people else "") + ". " if links_found else "")
                     + (f"In {same_ip} tender(s) two or more of them bid from the same IP address." if same_ip else "")),
            subjects=[*g, *people],
            evidence={"tenders": joint, "ties": [f"{k}: {a} / {b}" for k, a, b, _ in links_found]},
            measurements={"firms": len(grp), "tenders": len(joint), "value": round(value), "rotation": rotation, "winners": len(winners),
                          "ties": len(links_found), "same_ip_tenders": same_ip, **{f"mean_{k}": v for k, v in avg.items()}},
            thresholds={"cv_max": 0.05, "rd_min": 1.2, "or_win_vs_estimate_min": 0.95, "min_firms": 3, "min_tenders": 4}))
    return hits


@detector(
    id="DISPROPORTIONATE_ASSETS", version="1.0", title="Assets disproportionate to known income", tracks=["corruption"], scope="population",
    question="Did a public servant's household acquire and spend more in the check period than their known lawful income?",
    inputs=["employee_of", "Organisation.kind", "relative_of", "resides_at", "owns", "Property.value", "Property.registered_on",
            "txns", "Person.declared_income"],
    algorithm=("Public servants are people employed by a government department. Check period: the last 365 days of records. Household: "
               "the servant plus relatives with no independent means for an asset (declared income under a quarter of its value) whose "
               "purchase was at least a quarter funded from household accounts within 90 days before registration. Disproportion = assets "
               "registered in the period + large payments and spending (excluding payments that match a registered asset) - known income "
               "(salary from the employer, loans from banks, declared income). Reported above 10% of known income and Rs 10 lakh."),
    evasion=["Registering property in a relative's name (relatives' assets count when the money trail leads back to the household)",
             "Depositing bribe cash into a spouse's account (cash of unknown origin is not income)"],
    benign=["A senior officer whose flat is paid for by a housing loan", "Property inherited or bought before the check period"],
    blind_spots=["Assets held by front persons with no money trail to the household", "Cash spending that never touches a bank"],
    references=["Prevention of Corruption Act 1988 s.13(1)(b) (as amended 2018)",
                "Krishnanand Agnihotri v. State of M.P. (1977) 1 SCC 816 - small disproportion given the benefit of doubt"],
    complexity="O(P * T_p) for P public servants",
)
def disproportionate_assets(ctx: Context) -> list[Hit]:
    kinds = ctx.org_kind
    employers: dict[str, set[str]] = defaultdict(set)
    for p, o, _ in ctx.links.get("employee_of", ()):
        if kinds.get(o) == "department":
            employers[ctx.R(p)].add(o)
    if not employers:
        return []
    start = ctx.today - timedelta(days=365)
    props = ctx.props("Property")
    owned: dict[str, list[str]] = defaultdict(list)
    for o, x, _ in ctx.links.get("owns", ()):
        if x in props:
            owned[ctx.R(o)].append(x)
    L = ctx.L
    hits = []
    for servant, depts in employers.items():
        dept_accts = {a for a, h in L.holder.items() if h in depts}
        household = {servant}
        rel = ctx.family.get(servant, set())
        own_accts = set(ctx.accounts_of.get(servant, set()))
        for r in rel:
            if (ctx.person_attr(r, "declared_income") or 0) < 3_00_000:
                household.add(r)
        hh_accts = {a for p in household for a in ctx.accounts_of.get(p, set())} | own_accts
        assets, attributed = [], []
        for p in household | rel:
            for x in owned.get(p, []):
                reg = props[x].get("registered_on")
                if not reg or dt(reg) < start:
                    continue
                val = props[x].get("value") or 0
                if p == servant:
                    assets.append((x, val, p))
                    continue
                inc = ctx.person_attr(p, "declared_income") or 0
                funded = sum(t[4] for a in ctx.accounts_of.get(p, set()) for t in L.inc.get(a, [])
                             if t[2] in hh_accts - ctx.accounts_of.get(p, set()) and timedelta(0) <= dt(reg) - dt(t[1]) <= timedelta(days=90))
                if p in household and (p in ctx.family.get(servant, set())) and (inc < 0.25 * val) and (funded >= 0.25 * val or p in _spouses(ctx, servant)):
                    assets.append((x, val, p))
                    attributed.append(x)
        asset_total = sum(v for _, v, _ in assets)
        asset_vals = [v for _, v, _ in assets]
        spend, income, cash_in = 0.0, 0.0, 0.0
        for a in hh_accts:
            for t in L.out.get(a, []):
                if dt(t[1]) < start or t[3] in hh_accts:
                    continue
                if any(abs(t[4] - v) <= 0.1 * v for v in asset_vals):
                    continue
                spend += t[4]
            for t in L.inc.get(a, []):
                if dt(t[1]) < start:
                    continue
                if t[2] in dept_accts or (t[2] and kinds.get(L.holder.get(t[2], "")) == "bank"):
                    income += t[4]
                elif t[2] is None:
                    cash_in += t[4]
        declared = sum(ctx.person_attr(p, "declared_income") or 0 for p in household)
        known = max(income, declared)
        da = asset_total + spend - known
        if known <= 0 or da < 10_00_000 or da / known < 0.10:
            continue
        hits.append(Hit(
            "DISPROPORTIONATE_ASSETS", key=f"da:{servant}", severity="high" if da / known >= 1 else "medium",
            title=f"Assets {da / known:.0%} above known income (public servant)",
            summary=(f"In the 365-day check period the household of [[{servant}]] (employed by "
                     + ", ".join(f"[[{d}]]" for d in sorted(depts)) + f") acquired assets worth {money(asset_total)}"
                     + (f" ({len(attributed)} held by relatives with no independent means, funded from the household)" if attributed else "")
                     + f" and paid out {money(spend)}, against known lawful income of {money(known)}. Disproportion {money(da)} "
                     f"({da / known:.0%}). {money(cash_in)} was deposited in cash of unknown origin. Verify sources before any inference."),
            subjects=[servant, *sorted(household - {servant}), *[x for x, _, _ in assets]],
            evidence={"assets": [x for x, _, _ in assets], "attributed_to_household": attributed, "departments": sorted(depts)},
            measurements={"assets_acquired": round(asset_total), "expenditure": round(spend), "known_income": round(known),
                          "disproportion": round(da), "disproportion_pct": round(100 * da / known, 1), "cash_deposits": round(cash_in)},
            thresholds={"check_period_days": 365, "min_pct": 10, "min_amount": 1000000, "relative_funding_share": 0.25},
            window=(start.isoformat(timespec="minutes"), ctx.today.isoformat(timespec="minutes"))))
    return hits


def _spouses(ctx: Context, p: str) -> set[str]:
    """Relatives who also share the servant's address (a spouse or dependant living in the household)."""
    at: dict[str, set[str]] = defaultdict(set)
    for who, loc, _ in ctx.links.get("resides_at", ()):
        at[loc].add(ctx.R(who))
    mine = {loc for loc, ps in at.items() if p in ps}
    rel = {ctx.R(b) for a, b, _ in ctx.links.get("relative_of", ()) if ctx.R(a) == p} | {ctx.R(a) for a, b, _ in ctx.links.get("relative_of", ()) if ctx.R(b) == p}
    return {q for loc in mine for q in at[loc] if q in rel}

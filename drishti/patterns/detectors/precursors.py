"""Controlled-substance and explosives-precursor purchase registers: diversion by licensed buyers
and purchases by unlicensed ones."""

from __future__ import annotations

from collections import defaultdict
from math import log
from statistics import median

from ..algorithms import page_cusum, robust_z
from ..engine import Context, Hit, detector, dt

REGIME_LABEL = {"NDPS-CS": "NDPS controlled substance", "EXPLOSIVES-AN": "ammonium nitrate (explosives precursor)"}


@detector(
    id="PRECURSOR_DIVERSION", version="1.1", title="Precursor diversion", tracks=["narcotics", "terror"], scope="population",
    question="Is a buyer of a controlled precursor buying far more than its own history, splitting orders across dealers, or buying without a licence?",
    inputs=["procurements", "Organisation.licence_no", "Organisation.licensed_for", "Organisation.incorporated_on", "Organisation.kind",
            "director_of", "controls"],
    algorithm=("Monthly quantity per buyer and substance (month 0 = the last 30 days). Baseline: months 3-11 (median and MAD). A spike is a "
               "recent month at three times the median or more with a robust z of 4+; a one-sided CUSUM on log(quantity / median) (k = 0.5, "
               "h = 1.5) confirms a sustained shift. Splitting: three or more dealers in recent months where the baseline used at most two, "
               "or orders three times as frequent at half the size. Licence: the buyer has no licence for the substance, or the licence "
               "quoted on the invoice is not its own. New buyer: first purchase within 180 days and 100 kg or more. Steady growth (a ramp, "
               "not a jump) is not a spike: some month in the last quarter must be at least twice the median of the three months before "
               "it (an abrupt step). The step is looked for anywhere in the quarter, so a diversion that began two months ago, and "
               "has already raised month 2, is still a step and not mistaken for a ramp."),
    evasion=["Splitting purchases across dealers and small orders to stay under per-order scrutiny (aggregated per buyer per month)",
             "Using a licensed front company (its own history is the baseline)", "Quoting another firm's licence number (checked against the register)"],
    benign=["A manufacturer growing steadily month on month", "Quarries whose purchases dip in the monsoon and recover"],
    blind_spots=["Diversion that grows slowly over many months", "Purchases from unlicensed sellers who keep no register"],
    references=["NDPS Act 1985 s.9A and the NDPS (Regulation of Controlled Substances) Order 2013",
                "Ammonium Nitrate Rules 2012 (Explosives Act 1884)", "Page (1954) CUSUM; Iglewicz & Hoaglin (1993) robust z",
                "INCB Precursors Report (annual): diversion through licensed companies"],
    complexity="O(P) over purchase-register rows",
    depends=["HANDSET_CREW", "CONTINUING_UNLAWFUL_ACTIVITY"],
)
def precursor_diversion(ctx: Context) -> list[Hit]:
    orgs = ctx.props("Organisation")
    rows = [dict(r) for r in ctx.s.query("SELECT * FROM procurements ORDER BY ts")]
    series: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        series[(r["buyer_id"], r["substance"])].append(r)
    officers: dict[str, set[str]] = defaultdict(set)
    for t in ("director_of", "controls"):
        for p, o, _ in ctx.links.get(t, ()):
            officers[o].add(ctx.R(p))
    crews = {s for s in ctx.subjects_of("HANDSET_CREW", "CONTINUING_UNLAWFUL_ACTIVITY") if s.startswith("person:")} | set(ctx.accused)
    hits = []
    for (buyer, sub), rs in series.items():
        bp = orgs.get(buyer, {})
        month: dict[int, float] = defaultdict(float)
        orders: dict[int, int] = defaultdict(int)
        dealers: dict[int, set[str]] = defaultdict(set)
        for r in rs:
            m = (ctx.today - dt(r["ts"])).days // 30
            month[m] += r["quantity_kg"]
            orders[m] += 1
            dealers[m].add(r["seller_id"])
        base_months = [m for m in range(3, 12) if month.get(m)]
        base = [month[m] for m in base_months]
        recent = max(month.get(0, 0.0), month.get(1, 0.0))
        signs: list[str] = []
        meas: dict = {"recent_monthly_kg": round(recent, 1), "orders_recent": orders.get(0, 0) + orders.get(1, 0)}
        licensed_for = bp.get("licensed_for") or []
        if not bp.get("licence_no") or sub not in licensed_for:
            signs.append("no licence for this substance")
        own = bp.get("licence_no")
        quoted = {r["buyer_licence"] for r in rs if r["buyer_licence"]}
        if quoted and own and quoted - {own} or (quoted and not own):
            signs.append("licence quoted on invoices is not the buyer's own")
        if len(base) >= 4:
            med, mad, z = robust_z(recent, base)
            # largest abrupt step in the last quarter: a month against the median of the three before it
            jump = max(month.get(m, 0.0) / max(median([month.get(m + 1, 0.0), month.get(m + 2, 0.0), month.get(m + 3, 0.0)]), 1e-9) for m in (0, 1, 2))
            alarm, path = page_cusum([log(max(month.get(m, 0.0), 0.1) / max(med, 0.1)) for m in range(11, -1, -1)], target=0.0, k=0.5, h=1.5)
            meas |= {"baseline_median_kg": round(med, 1), "robust_z": round(z, 1), "ratio_to_baseline": round(recent / max(med, 1e-9), 2),
                     "cusum_alarm_month": None if alarm is None else 11 - alarm, "largest_step_last_quarter": round(jump, 2)}
            if recent >= 3 * med and z >= 4 and jump >= 2.0 and alarm is not None and 11 - alarm <= 2:
                signs.append(f"volume {recent / med:.1f}x its own baseline")
            base_dealers = set().union(*(dealers[m] for m in base_months)) if base_months else set()
            rec_dealers = dealers.get(0, set()) | dealers.get(1, set())
            base_orders = median([orders[m] for m in base_months])
            base_size = median([month[m] / orders[m] for m in base_months])
            rec_n = max(orders.get(0, 0), orders.get(1, 0))
            rec_size = recent / max(rec_n, 1)
            meas |= {"dealers_recent": len(rec_dealers), "dealers_baseline": len(base_dealers)}
            if (len(rec_dealers) >= 3 and len(base_dealers) <= 2) or (rec_n >= 3 * base_orders and rec_size <= 0.5 * base_size):
                signs.append(f"orders split across {len(rec_dealers)} dealers / smaller lots")
        else:
            first = min(dt(r["ts"]) for r in rs)
            total = sum(r["quantity_kg"] for r in rs)
            inc = bp.get("incorporated_on")
            if (ctx.today - first).days <= 180 and total >= 100:
                signs.append(f"new buyer: {total:.0f} kg since {first:%d %b %Y}" + (f", company incorporated {inc}" if inc else ""))
            meas |= {"total_kg": round(total, 1), "dealers": len({r['seller_id'] for r in rs})}
        strong = [s for s in signs if s.startswith(("no licence", "licence quoted"))]
        if not strong and len(signs) < 2:
            continue
        people = sorted(officers.get(buyer, set()))
        on_record = sorted(set(people) & crews)
        hits.append(Hit(
            "PRECURSOR_DIVERSION", key=f"precursor:{buyer}:{sub}", severity="high",
            title=f"{REGIME_LABEL.get(rs[0]['regime'], sub)}: {sub.replace('_', ' ')} bought by [[{buyer}]]",
            summary=(f"[[{buyer}]] bought {sub.replace('_', ' ')} ({REGIME_LABEL.get(rs[0]['regime'], rs[0]['regime'])}): " + "; ".join(signs)
                     + "." + (f" Its director(s) " + ", ".join(f"[[{p}]]" for p in on_record) + " are already on record in an FIR or a crew." if on_record else "")),
            subjects=[buyer, *people],
            evidence={"procurements": [r["id"] for r in rs][-40:], "dealers": sorted({r["seller_id"] for r in rs})},
            measurements=meas | {"signs": len(signs), "directors_on_record": len(on_record)},
            thresholds={"spike_ratio": 3, "robust_z": 4, "step_in_last_quarter": 2, "cusum": "k=0.5, h=1.5 on log ratio", "split_dealers": 3, "new_buyer_kg": 100, "new_buyer_days": 180},
            window=(rs[0]["ts"], rs[-1]["ts"])))
    return hits

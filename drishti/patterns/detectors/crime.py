"""Criminal-record patterns: organised-crime syndicates under the statutory test, and crimes
linked by the same weapon."""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

from ..algorithms import UnionFind, louvain
from ..engine import Context, Hit, detector, dt

CHARGED = {"chargesheeted", "convicted"}


@detector(
    id="CONTINUING_UNLAWFUL_ACTIVITY", version="1.1", title="Organised-crime syndicate (statutory test)", tracks=["organised_crime"],
    scope="population",
    question="Does a group of people accused together meet the 'continuing unlawful activity' test: more than one charge-sheet each in ten years?",
    inputs=["accused_in", "same_as", "Incident.status", "Incident.chargesheeted_on", "Incident.occurred_at", "Incident.max_punishment_years",
            "Incident.sections", "Person.history_sheet_no"],
    algorithm=("Co-offending graph over resolved people, built only from FIRs that can count towards the statute: charge-sheeted "
               "(or convicted), punishable with three years or more, within the last ten years, with two or more accused. Each connected "
               "group of three or more people is tested as it stands, so a modularity partition can never cut a syndicate across a "
               "boundary; only a group larger than 30 is split into Louvain communities (each split into connected parts, Leiden's "
               "guarantee). Per member, count the qualifying charge-sheets in which another member of the group is co-accused. A group "
               "where two or more members have more than one meets the statutory pattern."),
    evasion=["Different spellings of names in different FIRs (records are resolved to one person before the graph is built)",
             "Rotating which members are named in each FIR (the community, not a fixed pair, carries the history)"],
    benign=["Two neighbours accused together once in a quarrel (one FIR, two people)", "Single-accused FIRs (no co-offending)"],
    blind_spots=["Members never named in an FIR", "FIRs where charge-sheet status is not updated in CCTNS"],
    references=["Bharatiya Nyaya Sanhita 2023 s.111 (organised crime; 'continuing unlawful activity')",
                "Maharashtra Control of Organised Crime Act 1999 s.2(1)(d)",
                "Blondel et al. (2008); Traag et al. (2019) - community detection", "Sarnecki (2001), Delinquent networks"],
    complexity="O(E α(V)) union-find over qualifying co-accusations; Louvain only inside groups larger than 30",
)
def continuing_unlawful_activity(ctx: Context) -> list[Hit]:
    ten_years = ctx.today - timedelta(days=3653)

    def qualifies(inc: str) -> bool:
        p = ctx.incidents.get(inc, {})
        when = p.get("chargesheeted_on") or p.get("occurred_at")
        return p.get("status") in CHARGED and bool(when) and dt(when) >= ten_years and (p.get("max_punishment_years") or 3) >= 3

    qualifying = {inc: ps for inc, ps in ctx.incident_accused.items() if len(ps) >= 2 and qualifies(inc)}
    if not qualifying:
        return []
    uf = UnionFind()
    edges: dict[tuple[str, str], float] = defaultdict(float)
    for ps in qualifying.values():
        ps_sorted = sorted(ps)
        for i, a in enumerate(ps_sorted):
            for b in ps_sorted[i + 1:]:
                edges[(a, b)] += 1.0
                uf.union(a, b)
    components: dict[str, set[str]] = defaultdict(set)
    for x in {x for e in edges for x in e}:
        components[uf.find(x)].add(x)
    groups: list[set[str]] = []
    for comp in sorted(components.values(), key=lambda c: sorted(c)):
        if len(comp) <= 30:
            groups.append(comp)
            continue
        comm = louvain(comp, [(a, b, w) for (a, b), w in edges.items() if a in comp])
        parts: dict[int, set[str]] = defaultdict(set)
        for n, c in comm.items():
            parts[c].add(n)
        groups.extend(parts.values())
    hits = []
    for members in groups:
        if len(members) < 3:
            continue
        joint = {inc for inc, ps in ctx.incident_accused.items() if len(ps & members) >= 2}
        qual: dict[str, list[str]] = defaultdict(list)
        for inc in joint:
            if inc not in qualifying:
                continue
            for m in ctx.incident_accused[inc] & members:
                qual[m].append(inc)
        meets = sorted(m for m, incs in qual.items() if len(incs) >= 2)
        if len(meets) < 2:
            continue
        sheets = [m for m in members if ctx.person_attr(m, "history_sheet_no")]
        pending = sorted(i for i in joint if ctx.incidents.get(i, {}).get("status") not in CHARGED)
        sections = sorted({s for i in joint for s in ctx.incidents.get(i, {}).get("sections", [])})
        first = min((ctx.incidents[i].get("occurred_at") for i in joint if ctx.incidents[i].get("occurred_at")), default=None)
        last = max((ctx.incidents[i].get("occurred_at") for i in joint if ctx.incidents[i].get("occurred_at")), default=None)
        district = next((ctx.incidents[i].get("district_lgd") for i in sorted(joint) if ctx.incidents[i].get("district_lgd")), None)
        hits.append(Hit(
            "CONTINUING_UNLAWFUL_ACTIVITY", key="syndicate:" + ",".join(sorted(members)), severity="high",
            title=f"Possible organised-crime syndicate: {len(members)} people, {len(joint)} joint FIRs",
            summary=(f"{len(members)} people were accused together across {len(joint)} FIRs ({len(joint) - len(pending)} charge-sheeted, "
                     f"{len(pending)} pending). {len(meets)} of them have more than one charge-sheet in ten years for offences punishable with "
                     f"three years or more, jointly with others in the group: " + ", ".join(f"[[{m}]]" for m in meets)
                     + f". This matches the pattern of 'continuing unlawful activity' (BNS s.111); whether the statutory test is met is "
                     f"for the investigating officer and prosecutor to decide." + (f" {len(sheets)} member(s) are history-sheeted." if sheets else "")),
            subjects=[*meets, *sorted(members - set(meets)), *sorted(joint)],
            evidence={"incidents": sorted(joint), "qualifying": {m: sorted(v) for m, v in qual.items()}, "sections": sections},
            measurements={"members": len(members), "joint_firs": len(joint), "chargesheeted": len(joint) - len(pending),
                          "members_meeting_test": len(meets), "history_sheeted": len(sheets)},
            thresholds={"min_members": 3, "charge_sheets_per_member": ">1 in 10 years", "min_punishment_years": 3, "members_meeting": 2},
            window=(first, last), district=district))
    return hits


@detector(
    id="WEAPON_LINKAGE", version="1.0", title="Crimes linked by one weapon", tracks=["organised_crime", "terror"], scope="population",
    question="Does the same firearm (by serial number or ballistic signature) appear in more than one incident?",
    inputs=["Firearm.serial_no", "Firearm.ballistic_ref", "used_in", "recovered_in", "mentions", "accused_in"],
    algorithm=("Group firearm records that share a serial number or an FSL ballistic signature (a weapon recovered in one case and cartridge "
               "cases from another are one weapon if the signatures match). Report every group linked to two or more incidents; an "
               "incident with no accused gains the accused of the linked cases as a lead."),
    evasion=["Removing the serial number (the ballistic signature links the cases)"],
    benign=["A licensed weapon with no incidents"],
    blind_spots=["Weapons never recovered and cartridges never examined", "Ballistic matches not yet entered by the FSL"],
    references=["NIBIN-style ballistic linkage practice; Arms Act 1959", "State FSL ballistic division reports"],
    complexity="O(F) over firearm records",
)
def weapon_linkage(ctx: Context) -> list[Hit]:
    arms = ctx.props("Firearm")
    uf = UnionFind(arms)
    by_key: dict[str, list[str]] = defaultdict(list)
    for fid, p in arms.items():
        for k in ("serial_no", "ballistic_ref"):
            if p.get(k) and not str(p[k]).startswith("UNRECOVERED"):
                by_key[f"{k}:{p[k]}"].append(fid)
    for ids in by_key.values():
        for x in ids[1:]:
            uf.union(ids[0], x)
    incs: dict[str, set[str]] = defaultdict(set)
    for t in ("used_in", "recovered_in"):
        for f, inc, _ in ctx.links.get(t, ()):
            if f in arms:
                incs[f].add(inc)
    for inc, f, _ in ctx.links.get("mentions", ()):
        if f in arms:
            incs[f].add(inc)
    hits = []
    for grp in uf.groups():
        linked = set().union(*(incs.get(f, set()) for f in grp))
        if len(linked) < 2:
            continue
        unsolved = sorted(i for i in linked if not ctx.incident_accused.get(i))
        accused = sorted({p for i in linked for p in ctx.incident_accused.get(i, ())})
        refs = sorted({arms[f].get("ballistic_ref") for f in grp if arms[f].get("ballistic_ref")})
        hits.append(Hit(
            "WEAPON_LINKAGE", key="weapon:" + ",".join(sorted(grp)), severity="high" if unsolved else "medium",
            title=f"One weapon in {len(linked)} incidents" + (f" ({len(unsolved)} unsolved)" if unsolved else ""),
            summary=(f"Firearm record(s) " + ", ".join(f"[[{f}]]" for f in sorted(grp)) + f" share a serial number or ballistic signature "
                     f"({', '.join(refs) or 'serial'}) and appear in {len(linked)} incidents: " + ", ".join(f"[[{i}]]" for i in sorted(linked))
                     + (f". {len(unsolved)} of them have no accused; the accused in the linked case(s) are a lead: "
                        + ", ".join(f"[[{p}]]" for p in accused[:6]) if unsolved and accused else "") + "."),
            subjects=[*sorted(grp), *sorted(linked), *accused],
            evidence={"incidents": sorted(linked), "ballistic_refs": refs},
            measurements={"incidents": len(linked), "unsolved": len(unsolved), "firearm_records": len(grp)},
            thresholds={"min_incidents": 2}))
    return hits

"""Communications patterns: SIM-box gateways, handset-sharing crews, burner succession, foreign
handlers, and repeated reconnaissance visits.

Two of these are seeded, not population-wide: burner succession starts only from numbers named in an
FIR or held by an accused person, and the handler and recce detectors look only around people already
on record (accused, or in a crew found from records). Anyone can change their number or call a
relative abroad; those detectors do not look at people who are not already part of a lawful inquiry."""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from statistics import mean
from typing import Any

from ..algorithms import UnionFind, circular_std_hours, idf_weights, weighted_jaccard
from ..engine import Context, Hit, detector, dt

COUNTRY_CODES = {"+977": ("NP", "Nepal"), "+94": ("LK", "Sri Lanka"), "+971": ("AE", "UAE"), "+65": ("SG", "Singapore"),
                 "+852": ("HK", "Hong Kong"), "+66": ("TH", "Thailand"), "+44": ("GB", "United Kingdom"), "+92": ("PK", "Pakistan"),
                 "+880": ("BD", "Bangladesh"), "+86": ("CN", "China"), "+1": ("US", "USA/Canada"), "+966": ("SA", "Saudi Arabia")}


def country_of(number: str) -> tuple[str, str]:
    for code in sorted(COUNTRY_CODES, key=len, reverse=True):
        if number.startswith(code):
            return COUNTRY_CODES[code]
    return ("??", "abroad")


@detector(
    id="SIM_BOX", version="1.0", title="SIM-box gateway", tracks=["internal_security", "cyber_fraud"], scope="population",
    question="Are SIMs behaving like the ports of a GSM gateway: many short outgoing calls to strangers, no incoming calls, never moving?",
    inputs=["cdrs.a_number", "cdrs.b_number", "cdrs.ts", "cdrs.duration_s", "cdrs.tower_id", "sim_in_device"],
    algorithm=("Per SIM: outgoing calls, distinct called numbers, incoming calls, towers used, mean duration, calls per active day. "
               "A SIM with 100+ outgoing calls is gateway-like when at least four of five signs hold: incoming under 3% of outgoing, 85%+ "
               "distinct callees, at most two towers, mean call under 150 s, 15+ calls a day. Gateway-like SIMs are grouped by shared handset (IMEI) or by sharing one tower; "
               "a group of three or more is reported with its rotation schedule."),
    evasion=["Rotating SIMs every few days to stay under per-SIM volume limits (grouped by handset and tower, not judged one by one)",
             "Moving SIMs between gateways (the SIM-handset graph joins them)",
             "Staging fake incoming calls or longer calls (four of five signs suffice, so faking one sign does not hide a gateway)"],
    benign=["A call centre: one handset per SIM, real incoming traffic, longer calls"],
    blind_spots=["Gateways that spoof IMEIs and spread SIMs across many towers", "VoIP traffic that never touches a SIM"],
    references=["DoT / TRAI advisories on illegal telephone exchanges (SIM boxes)", "GSMA FF.21 Fraud manual: interconnect bypass"],
    complexity="O(C) aggregation over call records",
)
def sim_box(ctx: Context) -> list[Hit]:
    stats: dict[str, dict[str, Any]] = defaultdict(lambda: {"out": 0, "inc": 0, "b": set(), "towers": set(), "dur": 0, "days": set(), "first": None, "last": None})
    for cid, ts, a, b, dur, tower in ctx.cdrs:
        s = stats[a]
        s["out"] += 1
        s["b"].add(b)
        s["dur"] += dur
        s["days"].add(ts[:10])
        if tower:
            s["towers"].add(tower)
        s["first"] = s["first"] or ts
        s["last"] = ts
        stats[b]["inc"] += 1
    boxy = {}
    for num, s in stats.items():
        if s["out"] < 100 or not s["towers"]:
            continue
        sig = {"incoming_ratio": s["inc"] / s["out"], "distinct_callees": len(s["b"]) / s["out"], "towers": len(s["towers"]),
               "mean_duration_s": s["dur"] / s["out"], "calls_per_day": s["out"] / max(1, len(s["days"]))}
        votes = [sig["incoming_ratio"] <= 0.03, sig["distinct_callees"] >= 0.85, sig["towers"] <= 2, sig["mean_duration_s"] <= 150,
                 sig["calls_per_day"] >= 15]
        # four of five: faking one dimension (e.g. a few staged incoming calls) does not hide a gateway
        if sum(votes) >= 4 and sig["towers"] <= 3:
            boxy[num] = sig | {"out": s["out"], "first": s["first"], "last": s["last"], "tower_ids": sorted(s["towers"]), "signs": sum(votes)}
    if not boxy:
        return []
    uf = UnionFind(boxy)
    dev_of: dict[str, set[str]] = defaultdict(set)
    for ph, dev, _ in ctx.links.get("sim_in_device", ()):
        num = ctx.phone_number.get(ph)
        if num in boxy:
            dev_of[dev].add(num)
    for nums in dev_of.values():
        nums = sorted(nums)
        for n in nums[1:]:
            uf.union(nums[0], n)
    by_tower: dict[str, list[str]] = defaultdict(list)
    for num, sig in boxy.items():
        for t in sig["tower_ids"]:
            by_tower[t].append(num)
    for nums in by_tower.values():
        for n in nums[1:]:
            uf.union(nums[0], n)
    hits = []
    for grp in uf.groups():
        if len(grp) < 3:
            continue
        sims = sorted(grp, key=lambda n: boxy[n]["first"])
        devices = sorted(d for d, nums in dev_of.items() if nums & grp)
        towers = sorted({t for n in grp for t in boxy[n]["tower_ids"]})
        span = (dt(boxy[sims[-1]]["last"]) - dt(boxy[sims[0]]["first"])).days
        life = mean((dt(boxy[n]["last"]) - dt(boxy[n]["first"])).days + 1 for n in sims)
        tw = ctx.towers.get(towers[0], {}) if towers else {}
        phone_ids = [ctx.number_phone[n] for n in sims if n in ctx.number_phone]
        hits.append(Hit(
            "SIM_BOX", key="simbox:" + ",".join(sorted(devices) or sims[:3]), severity="high" if len(grp) >= 6 else "medium",
            title=f"SIM-box gateway: {len(grp)} SIMs in {len(devices) or 'unknown'} handset(s)",
            summary=(f"{len(grp)} SIMs made {sum(boxy[n]['out'] for n in grp):,} outgoing calls from {len(towers)} tower(s) near "
                     f"{tw.get('label', 'one site')} with almost no incoming calls; each SIM lived about {life:.0f} days before the next took over "
                     f"(rotation over {span} days)" + (f", moving between {len(devices)} gateway handsets" if len(devices) > 1 else "") + "."),
            subjects=[*devices, *phone_ids],
            evidence={"phones": phone_ids, "devices": devices, "towers": towers},
            measurements={"sims": len(grp), "devices": len(devices), "outgoing_calls": sum(boxy[n]["out"] for n in grp),
                          "mean_incoming_ratio": round(mean(boxy[n]["incoming_ratio"] for n in grp), 3),
                          "mean_distinct_callees": round(mean(boxy[n]["distinct_callees"] for n in grp), 2),
                          "mean_duration_s": round(mean(boxy[n]["mean_duration_s"] for n in grp)), "sim_life_days": round(life, 1),
                          "rotation_span_days": span},
            thresholds={"min_out": 100, "signs_required": "4 of 5", "max_incoming_ratio": 0.03, "min_distinct_callees": 0.85, "max_towers": 2,
                        "max_mean_duration_s": 150, "min_calls_per_day": 15, "min_sims": 3},
            window=(boxy[sims[0]]["first"], boxy[sims[-1]]["last"]), district=tw.get("district_lgd")))
    return hits


@detector(
    id="HANDSET_CREW", version="1.0", title="Handset-sharing crew", tracks=["organised_crime", "terror", "narcotics", "internal_security"],
    scope="population",
    question="Are unrelated people putting their SIMs in the same handsets at the same time?",
    inputs=["sim_in_device", "uses_phone", "same_as", "relative_of", "resides_at"],
    algorithm=("Bipartite SIM-handset graph from IMEI records. Two people are tied when their SIMs were in one handset during "
               "overlapping periods (when the record has periods). Ties between relatives or people registered at the same address are "
               "dropped. Components of two or more people are reported; rotation (one SIM in several handsets) raises severity."),
    evasion=["Registering each SIM in a different name (people are resolved, and the handset is shared regardless of the name)",
             "Swapping handsets around the group (rotation joins the handsets into one component)"],
    benign=["A family sharing one phone", "A second-hand handset used by two strangers months apart"],
    blind_spots=["Handsets with IMEI spoofing", "Crews that never share hardware"],
    references=["CEIR (Central Equipment Identity Register), DoT", "Investigative practice: IMEI-based linking of SIM cards"],
    complexity="O(L) over SIM-handset links",
)
def handset_crew(ctx: Context) -> list[Hit]:
    by_dev: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    for ph, dev, props in ctx.links.get("sim_in_device", ()):
        by_dev[dev].append((ph, props))
    uf = UnionFind()
    tie_devices: dict[frozenset, set[str]] = defaultdict(set)
    rotation = defaultdict(int)
    for ph, _dev, _ in ctx.links.get("sim_in_device", ()):
        rotation[ph] += 1
    for dev, sims in by_dev.items():
        for i, (p1, pr1) in enumerate(sims):
            for p2, pr2 in sims[i + 1:]:
                if pr1.get("first_seen") and pr2.get("first_seen") and pr1.get("last_seen") and pr2.get("last_seen"):
                    if pr1["last_seen"] < pr2["first_seen"] or pr2["last_seen"] < pr1["first_seen"]:
                        continue  # resale: never in the handset at the same time
                for a in ctx.phone_users.get(p1, ()):
                    for b in ctx.phone_users.get(p2, ()):
                        if a != b and not ctx.related(a, b):
                            uf.union(a, b)
                            tie_devices[frozenset((a, b))].add(dev)
    hits = []
    for grp in uf.groups():
        if len(grp) < 2:
            continue
        devs = sorted({d for k, ds in tie_devices.items() if k <= grp for d in ds})
        sims = sorted({ph for d in devs for ph, _ in by_dev[d]})
        rot = [ph for ph in sims if rotation[ph] >= 2]
        people = sorted(grp)
        hits.append(Hit(
            "HANDSET_CREW", key="crew:" + ",".join(people), severity="high" if len(grp) >= 3 or rot else "medium",
            title=f"Handset-sharing crew: {len(grp)} unrelated people, {len(devs)} handset(s)",
            summary=(f"{len(grp)} people who are not relatives or housemates used {len(sims)} SIMs in {len(devs)} shared handset(s)"
                     + (f"; {len(rot)} SIM(s) moved between handsets" if rot else "") + ". Members: "
                     + ", ".join(f"[[{p}]]" for p in people[:8]) + ("..." if len(people) > 8 else "") + "."),
            subjects=[*people, *devs],
            evidence={"devices": devs, "phones": sims},
            measurements={"people": len(grp), "handsets": len(devs), "sims": len(sims), "rotating_sims": len(rot)},
            thresholds={"min_people": 2, "family_ties_excluded": True, "non_overlapping_use_excluded": True}))
    return hits


def _seed_phones(ctx: Context) -> dict[str, str]:
    """Numbers named in incidents or used by accused people, or in an open case's scope -> why."""
    seeds: dict[str, str] = {}
    for inc, ph, _ in ctx.links.get("mentions", ()):
        if ph.startswith("phone:"):
            seeds[ph] = "named in an FIR / complaint"
    for p in ctx.accused:
        for ph in ctx.person_phones.get(p, ()):
            seeds.setdefault(ph, "used by a person accused in an FIR")
    for r in ctx.s.query("SELECT co.object_id FROM case_objects co JOIN cases c ON c.id=co.case_id WHERE c.status='open' AND co.object_id LIKE 'phone:%'"):
        seeds.setdefault(r["object_id"], "in an open case's scope")
    return seeds


@detector(
    id="BURNER_SUCCESSION", version="1.0", title="Successor SIM (burner switch)", tracks=["organised_crime", "terror", "narcotics"],
    scope="seeded",
    question="After a number named in an FIR goes silent, does a new number start calling the same people?",
    inputs=["mentions", "accused_in", "uses_phone", "cdrs.a_number", "cdrs.b_number", "cdrs.ts", "case_objects"],
    algorithm=("Seeds: numbers named in an FIR or complaint, numbers of accused people, numbers in an open case. A seed is silent if it "
               "has 10+ calls and none in the last 14 days. Candidates are numbers first seen between seven days before and 45 days after "
               "the silence and never seen before it. Contact sets are compared with an IDF-weighted Jaccard index (contacts who call "
               "everyone count for little). A successor needs three or more shared contacts and a similarity of 0.3 or more."),
    evasion=["Switching to a SIM registered in someone else's name (the successor is found by who it calls, not by the name on it)",
             "Dropping a few old contacts (similarity, not identity, of contact sets)"],
    benign=["An ordinary person who changes number (never seeded: the detector only follows numbers already on record)"],
    blind_spots=["A successor that calls a completely new set of people", "Switching to internet calling apps that leave no CDR"],
    references=["Contact-set (social fingerprint) linkage of successive identifiers, e.g. de Montjoye et al. (2013) on uniqueness in mobility/communication traces"],
    complexity="O(C) inverted index + O(S * K) comparisons for S seeds and K candidates sharing contacts",
)
def burner_succession(ctx: Context) -> list[Hit]:
    seeds = _seed_phones(ctx)
    contacts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    first: dict[str, str] = {}
    last: dict[str, str] = {}
    for _id, ts, a, b, _d, _t in ctx.cdrs:
        contacts[a][b] += 1
        contacts[b][a] += 1
        for n in (a, b):
            first.setdefault(n, ts)
            last[n] = ts
    degree = {n: len(c) for n, c in contacts.items()}
    w = idf_weights(degree)
    index: dict[str, set[str]] = defaultdict(set)
    for n, cs in contacts.items():
        for c in cs:
            index[c].add(n)
    hits = []
    cutoff = ctx.today - timedelta(days=14)
    for ph, why in seeds.items():
        num = ctx.phone_number.get(ph)
        if not num or num not in last or sum(contacts[num].values()) < 10 or dt(last[num]) > cutoff:
            continue
        silent = dt(last[num])
        mine = {c for c, k in contacts[num].items() if k >= 2}
        cand_count: dict[str, int] = defaultdict(int)
        for c in mine:
            for n in index[c]:
                if n != num:
                    cand_count[n] += 1
        best = None
        for n, shared in cand_count.items():
            if shared < 3:
                continue
            f = dt(first[n])
            if not (silent - timedelta(days=7) <= f <= silent + timedelta(days=45)):
                continue
            theirs = set(contacts[n])
            sim = weighted_jaccard(mine, theirs, w)
            if sim >= 0.3 and (best is None or sim > best[1]):
                best = (n, sim, sorted(mine & theirs), f)
        if not best:
            continue
        n, sim, common, f = best
        succ = ctx.number_phone.get(n)
        owner = next(iter(ctx.phone_users.get(ph, ())), None)
        hits.append(Hit(
            "BURNER_SUCCESSION", key=f"succ:{ph}->{n}", severity="high" if len(common) >= 5 else "medium",
            title="Successor SIM after a number on record went silent",
            summary=(f"{ref_phone(ph)} ({why}) went silent on {silent:%d %b %Y}. {ref_phone(succ) if succ else 'A new number'} first appeared "
                     f"on {f:%d %b %Y} and calls {len(common)} of its {len(mine)} regular contacts (weighted similarity {sim:.2f})."
                     + (f" The old number was used by [[{owner}]]." if owner else "")),
            subjects=[x for x in (owner, ph, succ) if x],
            evidence={"phones": [ph, *( [succ] if succ else [])], "shared_contacts": [ctx.number_phone.get(c, c) for c in common]},
            measurements={"shared_contacts": len(common), "seed_contacts": len(mine), "similarity": round(sim, 3),
                          "gap_days": (f - silent).days, "seed_reason": why},
            thresholds={"silent_days": 14, "min_seed_calls": 10, "min_shared": 3, "min_similarity": 0.3, "successor_window_days": [-7, 45]},
            window=(silent.isoformat(timespec="minutes"), f.isoformat(timespec="minutes"))))
    return hits


def ref_phone(ph: str | None) -> str:
    return f"[[{ph}]]" if ph else "an unknown number"


def _context_people(ctx: Context) -> set[str]:
    """People already on record: accused in an FIR, or members of a crew found from records."""
    return set(ctx.accused) | {s for s in ctx.subjects_of("HANDSET_CREW", "CONTINUING_UNLAWFUL_ACTIVITY", "CONVOY") if s.startswith("person:")}


@detector(
    id="FOREIGN_HANDLER", version="1.0", title="Foreign handler", tracks=["external", "terror", "internal_security", "narcotics"],
    scope="compound", depends=["HANDSET_CREW", "CONTINUING_UNLAWFUL_ACTIVITY", "CONVOY"],
    question="Is one unidentified foreign number in regular contact with several unrelated people already on record, especially just before incidents?",
    inputs=["cdrs", "uses_phone", "accused_in", "relative_of", "resides_at", "Incident.occurred_at", "travel.to_country", "travel.ts"],
    algorithm=("For each foreign number, find the people (resolved) whose phones exchanged two or more calls with it. Report it when two or "
               "more of them are unrelated to each other and at least one is accused in an FIR or in a crew found by another detector. "
               "Two further signs are measured: calls within 72 hours before an incident in which a contact is accused, and a contact "
               "travelling to the number's country within ten days after a call."),
    evasion=["Using one handler number per operative (the handler is still one number in contact with several people on record)",
             "Calling from abroad only at night (time of day is not used; contact structure is)"],
    benign=["Families calling a relative working abroad (contacts are one household: excluded)"],
    blind_spots=["Handlers using internet calling apps", "Handlers who use a different number for every contact"],
    references=["Telecommunications Act 2023 s.20(2) / IT Act s.69 lawful interception (records obtained under order)",
                "Network analysis of covert organisations: Krebs (2002), Mapping networks of terrorist cells"],
    complexity="O(C) over call records",
)
def foreign_handler(ctx: Context) -> list[Hit]:
    on_record = _context_people(ctx)
    calls: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for _id, ts, a, b, _d, _t in ctx.cdrs:
        for f, other in ((a, b), (b, a)):
            if f.startswith("+") and not f.startswith("+91"):
                p = ctx.owner_of_number(other)
                if p:
                    calls[f][p].append(ts)
    trips: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for r in ctx.s.query("SELECT person_id, ts, to_country FROM travel"):
        trips[ctx.R(r["person_id"])].append((r["ts"], r["to_country"]))
    hits = []
    for f, by_person in calls.items():
        contacts = {p for p, ts in by_person.items() if len(ts) >= 2}
        if len(contacts) < 2:
            continue
        unrelated = any(not ctx.related(a, b) for a in contacts for b in contacts if a < b)
        flagged = contacts & on_record
        if not unrelated or not flagged:
            continue
        code, cname = country_of(f)
        pre = []
        for p in contacts:
            for inc in ctx.accused.get(p, ()):
                t_inc = ctx.incident_time(inc)
                if t_inc and any(timedelta(0) < t_inc - dt(ts) <= timedelta(hours=72) for ts in by_person[p]):
                    pre.append((p, inc))
        travel_sync = []
        for p in contacts:
            for tts, ccode in trips.get(p, ()):
                if ccode == code and any(timedelta(0) <= dt(tts) - dt(ts) <= timedelta(days=10) for ts in by_person[p]):
                    travel_sync.append((p, tts[:10]))
        ph = ctx.number_phone.get(f)
        sev = "high" if pre or travel_sync or len(flagged) >= 2 else "medium"
        hits.append(Hit(
            "FOREIGN_HANDLER", key=f"handler:{f}", severity=sev,
            title=f"Foreign number ({cname}) in contact with {len(contacts)} people on record",
            summary=(f"An unidentified {cname} number {ref_phone(ph)} exchanged {sum(len(by_person[p]) for p in contacts)} calls with "
                     f"{len(contacts)} unrelated people, {len(flagged)} of them already on record ("
                     + ", ".join(f"[[{p}]]" for p in sorted(flagged)[:5]) + ")"
                     + (f"; it called {len({p for p, _ in pre})} of them within 72 hours before {len({i for _, i in pre})} incident(s) they are accused in" if pre else "")
                     + (f"; {len(travel_sync)} trip(s) to {cname} followed a call within ten days" if travel_sync else "") + "."),
            subjects=[x for x in [ph, *sorted(flagged), *sorted(contacts - flagged)] if x],
            evidence={"incidents": sorted({i for _, i in pre}), "travel": [f"{p}:{d}" for p, d in travel_sync]},
            measurements={"contacts": len(contacts), "on_record": len(flagged), "calls": sum(len(by_person[p]) for p in contacts),
                          "pre_incident_contacts": len(pre), "travel_after_call": len(travel_sync), "country": cname},
            thresholds={"min_contacts": 2, "min_calls_per_contact": 2, "family_only_excluded": True, "pre_incident_hours": 72, "travel_days": 10}))
    return hits


@detector(
    id="RECCE_REPETITION", version="1.0", title="Repeated reconnaissance visits", tracks=["terror", "internal_security"],
    scope="compound", depends=["HANDSET_CREW", "CONTINUING_UNLAWFUL_ACTIVITY"],
    question="Does a group already on record keep visiting, together and briefly, a place none of them lives or works near?",
    inputs=["cdrs.tower_id", "cdrs.ts", "cdrs.a_number", "uses_phone", "accused_in", "sim_in_device", "relative_of", "towers"],
    algorithm=("Groups: people tied by shared handsets, joint FIRs or frequent calls (8+, non-family), restricted to components containing "
               "someone on record. Each member's anchor towers are those seen on eight or more distinct days (home, work, usual meeting "
               "place). A recce site is a non-anchor tower where two or more members are present within three hours of each other on two or "
               "more days; consistency of the hour of day (circular standard deviation) is reported."),
    evasion=["Spacing visits weeks apart (any two joint days count, however far apart)", "Switching phones (handset-sharing ties the group)"],
    benign=["The group's own usual meeting place (an anchor: frequent, not repeated short visits)", "Groups with nobody on record (not examined)"],
    blind_spots=["Visits made with phones switched off", "Locations covered by the same tower as an anchor"],
    references=["Pre-attack surveillance indicators: US DHS / NCTC 'Terrorist attack cycle' guidance",
                "Circular statistics for time of day: Fisher (1993), Statistical analysis of circular data"],
    complexity="O(C) over located call records for group members",
)
def recce_repetition(ctx: Context) -> list[Hit]:
    on_record = _context_people(ctx)
    pair_calls: dict[tuple[str, str], int] = defaultdict(int)
    located: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for _id, ts, a, b, _d, tower in ctx.cdrs:
        pa, pb = ctx.owner_of_number(a), ctx.owner_of_number(b)
        if pa and pb and pa != pb:
            pair_calls[(pa, pb) if pa < pb else (pb, pa)] += 1
        if pa and tower:
            located[pa].append((ts, tower))
    uf = UnionFind()
    for (a, b), n in pair_calls.items():
        if n >= 8 and not ctx.related(a, b):
            uf.union(a, b)
    for inc, ps in ctx.incident_accused.items():
        ps = sorted(ps)
        for p in ps[1:]:
            uf.union(ps[0], p)
    for s in ctx.subjects_of("HANDSET_CREW"):
        if s.startswith("person:"):
            uf.find(s)
    for h in ctx.hits.get("HANDSET_CREW", []):
        ps = [s for s in h.subjects if s.startswith("person:")]
        for p in ps[1:]:
            uf.union(ps[0], p)
    hits = []
    for grp in uf.groups():
        if len(grp) < 2 or not grp & on_record:
            continue
        anchors: dict[str, set[str]] = {}
        for p in grp:
            days: dict[str, set[str]] = defaultdict(set)
            for ts, tw in located.get(p, ()):
                days[tw].add(ts[:10])
            anchors[p] = {tw for tw, ds in days.items() if len(ds) >= 8}
        all_anchor = set().union(*anchors.values()) if anchors else set()
        visits: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for p in grp:
            for ts, tw in located.get(p, ()):
                if tw not in all_anchor:
                    visits[tw].append((ts, p))
        for tw, vs in visits.items():
            people = {p for _, p in vs}
            if len(people) < 2:
                continue
            by_day: dict[str, list[tuple[str, str]]] = defaultdict(list)
            for ts, p in vs:
                by_day[ts[:10]].append((ts, p))
            joint_days = [d for d, xs in by_day.items()
                          if any(p1 != p2 and abs((dt(t1) - dt(t2)).total_seconds()) <= 3 * 3600 for t1, p1 in xs for t2, p2 in xs)]
            if len(joint_days) < 2:
                continue
            hours = [dt(ts).hour + dt(ts).minute / 60 for ts, _ in vs]
            spread = circular_std_hours(hours)
            info = ctx.towers.get(tw, {})
            hits.append(Hit(
                "RECCE_REPETITION", key=f"recce:{tw}:" + ",".join(sorted(people)), severity="high" if len(joint_days) >= 3 else "medium",
                title=f"Repeated visits by a group on record to {info.get('label', tw)}",
                summary=(f"{len(people)} members of a group with someone on record were at {info.get('label', tw)} on {len(by_day)} different days "
                         f"({len(joint_days)} of them together within three hours), at about the same time of day (spread {spread:.1f} h). "
                         f"None of them lives, works or usually meets near this tower. Members present: "
                         + ", ".join(f"[[{p}]]" for p in sorted(people)) + "."),
                subjects=sorted(people),
                evidence={"towers": [tw], "dates": sorted(by_day)},
                measurements={"members_present": len(people), "days": len(by_day), "joint_days": len(joint_days), "hour_spread_h": round(spread, 2),
                              "group_size": len(grp)},
                thresholds={"anchor_days": 8, "joint_window_h": 3, "min_joint_days": 2},
                window=(min(ts for ts, _ in vs), max(ts for ts, _ in vs)), district=info.get("district_lgd")))
    return hits

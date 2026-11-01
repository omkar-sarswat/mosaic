"""Vehicle patterns from FASTag toll reads and ANPR cameras: convoys and pilot cars, cloned number
plates, and stolen vehicles still on the road."""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from statistics import mean

from ..algorithms import UnionFind, haversine_km
from ..engine import Context, Hit, detector, dt


# Scales: (window minutes, min distinct plazas per journey, min journeys, leader consistency).
CONVOY_SCALES = [(20, 3, 2, 0.8), (60, 4, 3, 1.0)]


@detector(
    id="CONVOY", version="1.0", title="Convoy / pilot car", tracks=["narcotics", "organised_crime", "terror"], scope="population",
    question="Do two vehicles from different owners repeatedly travel the same route together, one leading the other?",
    inputs=["tollhits.vehicle_id", "tollhits.ts", "tollhits.plaza", "owns"],
    algorithm=("Sweep each plaza's reads in time order and record every pair of vehicles close in time, with which one was ahead; split "
               "each pair's co-occurrences into journeys (gaps over 12 hours). Two scales: within 20 minutes, three or more plazas with the "
               "same leader 80% of the time on two or more journeys; or within 60 minutes, four or more plazas with the same leader every "
               "time on three or more journeys. Vehicles of the same owner (a fleet) are excluded."),
    evasion=["Keeping a gap between the vehicles (up to an hour at the wide scale, which demands a longer, repeated shared route)",
             "Switching which vehicle leads now and then (80% consistency, not 100%)",
             "Different owners on paper (ownership is used only to excuse a fleet, never to require a link)"],
    benign=["Commuters crossing the same plaza at rush hour (one plaza, not a route)", "A transport company's trucks travelling together (same owner)"],
    blind_spots=["Routes with fewer than three instrumented plazas", "Gaps over an hour", "Convoys that travel on different days and meet at the destination"],
    references=["Jeung, Yiu, Zhou, Jensen & Shen (2008), Discovery of convoys in trajectory databases, VLDB"],
    complexity="O(R * k) for R reads and k vehicles inside a 20-minute window",
)
def convoy(ctx: Context) -> list[Hit]:
    by_plaza: dict[str, list[dict]] = defaultdict(list)
    for r in ctx.reads:
        by_plaza[r["plaza"]].append(r)
    for rs in by_plaza.values():
        rs.sort(key=lambda r: r["ts"])
    pairs: dict[tuple[str, str], tuple[list, tuple]] = {}
    for window, min_plazas, min_trips, consistency in CONVOY_SCALES:
        co: dict[tuple[str, str], list[tuple]] = defaultdict(list)
        for plaza, rs in by_plaza.items():
            for i, r1 in enumerate(rs):
                t1 = dt(r1["ts"])
                for r2 in rs[i + 1:]:
                    t2 = dt(r2["ts"])
                    if t2 - t1 > timedelta(minutes=window):
                        break
                    if r1["vehicle_id"] == r2["vehicle_id"]:
                        continue
                    a, b = sorted((r1["vehicle_id"], r2["vehicle_id"]))
                    co[(a, b)].append((t1, plaza, r1["vehicle_id"], (t2 - t1).total_seconds() / 60, r1["id"], r2["id"]))
        for (a, b), evs in co.items():
            if (a, b) in pairs:
                continue
            oa, ob = ctx.vehicle_owner.get(a), ctx.vehicle_owner.get(b)
            if oa and oa == ob:
                continue
            evs.sort()
            trips, cur = [], [evs[0]]
            for e in evs[1:]:
                if e[0] - cur[-1][0] > timedelta(hours=12):
                    trips.append(cur)
                    cur = [e]
                else:
                    cur.append(e)
            trips.append(cur)
            good = []
            for tr in trips:
                plazas = {e[1] for e in tr}
                lead = max(sum(1 for e in tr if e[2] == v) for v in (a, b)) / len(tr)
                if len(plazas) >= min_plazas and lead >= consistency:
                    good.append(tr)
            if len(good) >= min_trips:
                pairs[(a, b)] = (good, (window, min_plazas, min_trips, consistency))
    uf = UnionFind()
    for a, b in pairs:
        uf.union(a, b)
    hits = []
    for grp in uf.groups():
        trips = [tr for (a, b), (trs, _) in pairs.items() if a in grp for tr in trs]
        scale = min(sc for (a, b), (_, sc) in pairs.items() if a in grp)
        lead_counts: dict[str, int] = defaultdict(int)
        for tr in trips:
            for e in tr:
                lead_counts[e[2]] += 1
        leader = max(lead_counts, key=lead_counts.get)
        owners = sorted({o for v in grp if (o := ctx.vehicle_owner.get(v))})
        vehicles = sorted(grp)
        gap = mean(e[3] for tr in trips for e in tr)
        hits.append(Hit(
            "CONVOY", key="convoy:" + ",".join(vehicles), severity="high" if len(trips) >= 3 else "medium",
            title=f"Convoy: {len(vehicles)} vehicles, {len(trips)} journeys together",
            summary=(f"{' and '.join(f'[[{v}]]' for v in vehicles)} passed {max(len({e[1] for e in tr}) for tr in trips)} toll plazas together on "
                     f"{len(trips)} separate journeys, about {gap:.0f} minutes apart, with [[{leader}]] in front each time (a pilot or escort "
                     f"pattern). Owners: " + ", ".join(f"[[{o}]]" for o in owners) + "."),
            subjects=[*vehicles, *owners],
            evidence={"reads": sorted({x for tr in trips for e in tr for x in (e[4], e[5])})[:120]},
            measurements={"vehicles": len(vehicles), "journeys": len(trips), "mean_gap_min": round(gap, 1),
                          "plazas_per_journey": max(len({e[1] for e in tr}) for tr in trips), "scale_window_min": scale[0]},
            thresholds={"scales": [list(x) for x in CONVOY_SCALES], "same_owner_excluded": True},
            window=(min(e[0] for tr in trips for e in tr).isoformat(timespec="minutes"),
                    max(e[0] for tr in trips for e in tr).isoformat(timespec="minutes"))))
    return hits


@detector(
    id="CLONED_PLATE", version="1.0", title="Cloned number plate", tracks=["organised_crime"], scope="population",
    question="Is one registration number being read in two places no single vehicle could connect in the time between?",
    inputs=["tollhits.vehicle_id", "tollhits.ts", "tollhits.lat", "tollhits.lon"],
    algorithm=("For each registration, compare reads within six hours of each other. With five minutes allowed for clock skew, an implied "
               "road speed of 180 km/h or more over 30 km or more is physically impossible. Two impossible pairs (or one over 400 km/h) "
               "mean two vehicles carry the same plate."),
    evasion=["Using a real, registered car's number (the genuine owner's ordinary trips expose the clone)",
             "Cloning a car from another district (distance makes the clash obvious)"],
    benign=["A fast but possible journey (Mumbai to Pune in two hours)", "Two nearby plazas read minutes apart"],
    blind_spots=["A clone that never shares a road network with the original", "Plates read only once"],
    references=["Physical speed-bound consistency checking of ANPR reads (cloned-plate detection practice in ANPR systems)"],
    complexity="O(R log R) per registration",
)
def cloned_plate(ctx: Context) -> list[Hit]:
    by_v: dict[str, list[dict]] = defaultdict(list)
    for r in ctx.reads:
        if r["lat"] is not None:
            by_v[r["vehicle_id"]].append(r)
    hits = []
    for v, rs in by_v.items():
        rs.sort(key=lambda r: r["ts"])
        bad = []
        for i, r1 in enumerate(rs):
            for r2 in rs[i + 1:]:
                hrs = (dt(r2["ts"]) - dt(r1["ts"])).total_seconds() / 3600
                if hrs > 6:
                    break
                km = haversine_km(r1["lat"], r1["lon"], r2["lat"], r2["lon"])
                speed = km / max(hrs - 5 / 60, 1 / 60)
                if km >= 30 and speed >= 180:
                    bad.append((r1, r2, km, speed))
        if len(bad) >= 2 or any(b[3] >= 400 for b in bad):
            places = sorted({b[0]["plaza"] for b in bad} | {b[1]["plaza"] for b in bad})
            hits.append(Hit(
                "CLONED_PLATE", key=f"clone:{v}", severity="high",
                title="Cloned number plate: one registration, two vehicles",
                summary=(f"[[{v}]] was read {len(bad)} time(s) at places it could not have reached in time, e.g. {bad[0][0]['plaza']} then "
                         f"{bad[0][1]['plaza']} ({bad[0][2]:.0f} km in {(dt(bad[0][1]['ts']) - dt(bad[0][0]['ts'])).total_seconds() / 60:.0f} min, "
                         f"{bad[0][3]:.0f} km/h). Another vehicle is carrying this number; the registered owner may be unaware."),
                subjects=[v],
                evidence={"reads": [x for b in bad for x in (b[0]["id"], b[1]["id"])], "places": places,
                          "registered_owner": [o] if (o := ctx.vehicle_owner.get(v)) else []},
                measurements={"impossible_pairs": len(bad), "max_speed_kmh": round(max(b[3] for b in bad)), "max_km": round(max(b[2] for b in bad))},
                thresholds={"min_km": 30, "min_speed_kmh": 180, "clock_skew_min": 5, "min_pairs": 2, "or_speed_kmh": 400},
                window=(bad[0][0]["ts"], bad[-1][1]["ts"])))
    return hits


@detector(
    id="STOLEN_VEHICLE_TRAIL", version="1.0", title="Stolen vehicle still moving", tracks=["organised_crime"], scope="seeded",
    question="Has a vehicle reported stolen been read on the road after the theft, and do several stolen vehicles end up at the same place?",
    inputs=["stolen_in", "Incident.occurred_at", "tollhits"],
    algorithm=("Seed with vehicles linked to a theft FIR. Report every read after the theft time (a recovery lead), and group stolen "
               "vehicles whose last post-theft reads are at the same plaza or within 5 km: a common destination suggests a chop shop or a "
               "re-registration route."),
    evasion=["Driving at night (reads do not depend on time of day)", "Changing plates after the first read (the first reads still show the route)"],
    benign=["A vehicle read before it was stolen (only reads after the theft time count)"],
    blind_spots=["Vehicles moved on trucks or kept off instrumented roads", "Immediate re-plating before any read"],
    references=["ZIPNET / CCTNS stolen-vehicle registers", "VAHAN and NETC FASTAG data for recovery"],
    complexity="O(S * R_v) for S stolen vehicles",
)
def stolen_vehicle_trail(ctx: Context) -> list[Hit]:
    thefts: dict[str, list[str]] = defaultdict(list)
    for v, inc, _ in ctx.links.get("stolen_in", ()):
        thefts[v].append(inc)
    by_v: dict[str, list[dict]] = defaultdict(list)
    for r in ctx.reads:
        if r["vehicle_id"] in thefts:
            by_v[r["vehicle_id"]].append(r)
    hits, last_seen = [], {}
    for v, incs in thefts.items():
        times = [t for i in incs if (t := ctx.incident_time(i))]
        if not times:
            continue
        stolen_at = min(times)
        after = sorted((r for r in by_v.get(v, []) if dt(r["ts"]) > stolen_at), key=lambda r: r["ts"])
        if not after:
            continue
        last_seen[v] = after[-1]
        hits.append(Hit(
            "STOLEN_VEHICLE_TRAIL", key=f"stolen:{v}", severity="high",
            title=f"Stolen vehicle read {len(after)} time(s) after the theft",
            summary=(f"[[{v}]], reported stolen in [[{incs[0]}]] on {stolen_at:%d %b %Y}, was read {len(after)} time(s) afterwards; last at "
                     f"{after[-1]['plaza']} on {dt(after[-1]['ts']):%d %b %Y %H:%M}."),
            subjects=[v, *incs],
            evidence={"reads": [r["id"] for r in after], "route": [r["plaza"] for r in after]},
            measurements={"reads_after_theft": len(after), "hours_to_first_read": round((dt(after[0]["ts"]) - stolen_at).total_seconds() / 3600, 1),
                          "last_place": after[-1]["plaza"]},
            thresholds={"reads_after_theft": 1},
            window=(stolen_at.isoformat(timespec="minutes"), after[-1]["ts"])))
    uf = UnionFind(last_seen)
    vs = sorted(last_seen)
    for i, a in enumerate(vs):
        for b in vs[i + 1:]:
            ra, rb = last_seen[a], last_seen[b]
            if ra["plaza"] == rb["plaza"] or haversine_km(ra["lat"], ra["lon"], rb["lat"], rb["lon"]) <= 5:
                uf.union(a, b)
    for grp in uf.groups():
        if len(grp) < 2:
            continue
        place = last_seen[sorted(grp)[0]]["plaza"]
        hits.append(Hit(
            "STOLEN_VEHICLE_TRAIL", key="sink:" + ",".join(sorted(grp)), severity="high",
            title=f"{len(grp)} stolen vehicles last seen at the same place",
            summary=(f"{len(grp)} vehicles stolen in separate incidents were last read at or near {place}: "
                     + ", ".join(f"[[{v}]]" for v in sorted(grp)) + ". A common destination suggests a dismantling yard or a re-registration route nearby."),
            subjects=sorted(grp),
            evidence={"reads": [last_seen[v]["id"] for v in grp], "place": [place]},
            measurements={"vehicles": len(grp), "place": place},
            thresholds={"same_plaza_or_km": 5, "min_vehicles": 2}))
    return hits

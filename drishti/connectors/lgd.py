"""LGD connector: states and districts as AdminUnit objects, plus a gazetteer for geocoding.

Sources: data/reference/lgd_*.csv (official LGD codes via Wikidata, CC0) and
maharashtra_districts.geojson (geoBoundaries ADM2, ODbL). Run
scripts/fetch_reference_data.py to refresh them.
"""

from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from ..geo import centroid, point_in_geometry
from ..store import Store

SOURCE = "LGD"

# Renamed districts: old / colloquial name -> LGD code. Source text and older datasets keep
# using the old names for years, so the gazetteer must know both.
ALIASES = {
    "ahmednagar": "466", "ahmadnagar": "466", "chhatrapati sambhajinagar": "469", "sambhajinagar": "469",
    "osmanabad": "488", "bid": "470", "buldana": "472", "gondiya": "476", "mumbai": "482",
}
# Alias -> canonical name, resolved through the district table (covers other states without
# hard-coding their codes).
NAME_ALIASES = {
    "gurgaon": "gurugram", "allahabad": "prayagraj", "faizabad": "ayodhya", "hoshangabad": "narmadapuram",
    "pondicherry": "puducherry", "pauri": "pauri garhwal", "nellore": "sri potti sriramulu nellore",
    "kadapa": "y s r", "cuddapah": "y s r",
}
DISTRICT_ABBREV = {
    # Andhra Pradesh SDMA prefixes seen in SACHET areaDesc ("nlr-chillakur Mandal")
    "nlr": "nellore", "tpt": "tirupati", "ysr": "kadapa", "elr": "eluru", "plv": "polavaram",
    "egd": "east godavari", "wgd": "west godavari", "vsp": "visakhapatnam", "ksl": "kurnool", "atp": "anantapur",
}


def adminunit_id(level: str, code: str) -> str:
    return f"adminunit:lgd-{level[0]}-{code}"


def norm(s: str) -> str:
    s = s.lower().replace("&", "and")
    s = re.sub(r"\b(district|districts|mandal|mandals|taluka|tehsil|block|of|the)\b", " ", s)
    return re.sub(r"[^a-z]+", " ", s).strip()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


@dataclass
class Gazetteer:
    states: dict[str, str]  # norm name -> state code
    districts: dict[str, list[tuple[str, str]]]  # norm name -> [(district code, state code)]
    subdistricts: dict[str, list[str]]  # norm name -> [district code]
    district_state: dict[str, str]
    district_name: dict[str, str]

    @classmethod
    def load(cls, reference_dir: Path) -> "Gazetteer":
        states = {norm(r["name"]): r["lgd_code"] for r in read_csv(reference_dir / "lgd_states.csv")}
        states.update({"puducherry": states.get("puducherry", "34"), "pondicherry": states.get("puducherry", "34")})
        districts: dict[str, list[tuple[str, str]]] = defaultdict(list)
        district_state, district_name = {}, {}
        for r in read_csv(reference_dir / "lgd_districts.csv"):
            districts[norm(r["name"])].append((r["lgd_code"], r["state_lgd_code"]))
            district_state[r["lgd_code"]] = r["state_lgd_code"]
            district_name[r["lgd_code"]] = r["name"]
        for alias, code in ALIASES.items():
            districts[norm(alias)].append((code, district_state.get(code, "")))
        for alias, canonical in NAME_ALIASES.items():
            if norm(canonical) in districts and norm(alias) not in districts:
                districts[norm(alias)] = list(districts[norm(canonical)])
        subs: dict[str, list[str]] = defaultdict(list)
        path = reference_dir / "lgd_subdistricts.csv"
        if path.exists():
            for r in read_csv(path):
                if r["district_lgd_code"]:
                    subs[norm(r["name"])].append(r["district_lgd_code"])
        return cls(states, dict(districts), dict(subs), district_state, district_name)

    def resolve(self, area_desc: str) -> tuple[list[str], str]:
        """Map free-text area description to LGD district codes. Returns (codes, method)."""
        text = area_desc.strip()
        parts = [p for p in re.split(r",|\band\b|\n", text) if p.strip()]
        state = None
        for p in parts:
            m = re.search(r"of\s+([A-Za-z &]+)$", p.strip())
            cand = norm(m.group(1)) if m else norm(p)
            if cand in self.states:
                state = self.states[cand]
        found: list[str] = []
        method = "unresolved"
        for p in parts:
            n = norm(re.sub(r"^\s*(isolated places over|parts of)\s+", "", p, flags=re.I))
            if not n or n in self.states:
                continue
            abbrev = re.match(r"^([a-z]{3})\s+(.+)$", n)  # "nlr chillakur" (from "nlr-chillakur")
            if abbrev and abbrev.group(1) in DISTRICT_ABBREV:
                n = abbrev.group(2)
            hit = [c for c, s in self.districts.get(n, []) if state is None or s == state]
            if hit:
                found.append(hit[0])
                method = "district_name"
                continue
            sub = [c for c in self.subdistricts.get(n, []) if state is None or self.district_state.get(c) == state]
            if sub:
                found.append(sub[0])
                method = "subdistrict_name" if method == "unresolved" else method
                continue
            # space-separated lists ("pauri almora chamoli")
            for tok in n.split():
                hit = [c for c, s in self.districts.get(tok, []) if state is None or s == state]
                if hit:
                    found.append(hit[0])
                    method = "district_token"
        return list(dict.fromkeys(found)), method


def load_admin_units(store: Store, reference_dir: Path) -> dict[str, int]:
    """Create state and district AdminUnits (all India) and attach polygons where we have them."""
    polygons: dict[str, dict] = {}
    gj = reference_dir / "maharashtra_districts.geojson"
    if gj.exists():
        for f in json.loads(gj.read_text(encoding="utf-8"))["features"]:
            polygons[f["properties"]["lgd_code"]] = f["geometry"]
    issues = []
    n_states = n_districts = 0
    with store.tx():
        for r in read_csv(reference_dir / "lgd_states.csv"):
            store.upsert_object("AdminUnit", {"name": r["name"], "level": "state", "lgd_code": r["lgd_code"]},
                                source=SOURCE, record=f"state:{r['lgd_code']}", obj_id=adminunit_id("state", r["lgd_code"]))
            n_states += 1
        for r in read_csv(reference_dir / "lgd_districts.csv"):
            code = r["lgd_code"]
            geom = polygons.get(code)
            lon = float(r["lon"]) if r["lon"] else None
            lat = float(r["lat"]) if r["lat"] else None
            if geom:
                if lon is not None and not point_in_geometry(lon, lat, geom):
                    issues.append({"source": "Wikidata P625", "object": r["name"], "lgd_code": code,
                                   "issue": f"coordinate ({lat:.2f}N, {lon:.2f}E) lies outside the district polygon"})
                lon, lat = centroid(geom)
            if r.get("coord_variants") not in (None, "", "0"):
                issues.append({"source": "Wikidata P625", "object": r["name"], "lgd_code": code,
                               "issue": f"{r['coord_variants']} conflicting coordinates recorded"})
            oid = store.upsert_object(
                "AdminUnit", {"name": r["name"], "level": "district", "lgd_code": code, "state_lgd_code": r["state_lgd_code"]},
                source=SOURCE, record=f"district:{code}", obj_id=adminunit_id("district", code),
                district_lgd=code, lat=lat, lon=lon, geom=geom,
            )
            if r["state_lgd_code"]:
                store.upsert_link("located_in", oid, adminunit_id("state", r["state_lgd_code"]), source=SOURCE, record=f"district:{code}")
            n_districts += 1
    store.set_meta("data_quality_lgd", issues)
    return {"states": n_states, "districts": n_districts, "district_polygons": len(polygons), "data_quality_issues": len(issues)}

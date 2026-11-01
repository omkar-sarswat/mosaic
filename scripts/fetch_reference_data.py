"""Fetch the open reference data DRISHTI needs and write it to data/reference/.

Every source here is open and needs no permission:

* Wikidata (CC0)            - official LGD codes for states, districts and sub-districts
* geoBoundaries IND ADM2    - district polygons (ODbL 1.0, derived from lgdirectory.gov.in)
* OpenStreetMap / Overpass  - hospitals in Maharashtra (ODbL 1.0)
* NDMA SACHET CAP feed      - a snapshot of live disaster alerts (feed declares "public domain")

Run:  python scripts/fetch_reference_data.py [--skip-osm] [--skip-sachet]
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REF = ROOT / "data" / "reference"
SAMPLES = ROOT / "data" / "samples"
UA = "DRISHTI-open-source/0.1 (https://github.com/; research prototype)"

SPARQL = "https://query.wikidata.org/sparql"
GEOB_API = "https://www.geoboundaries.org/api/current/gbOpen/IND/ADM2/"
OVERPASS_MIRRORS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
)
SACHET_RSS = "https://sachet.ndma.gov.in/cap_public_website/rss/rss_india.xml"
SACHET_CAP = "https://sachet.ndma.gov.in/cap_public_website/FetchXMLFile?identifier={}"

MAHARASHTRA_LGD = "27"

# geoBoundaries (2021 snapshot) still uses pre-rename or variant spellings.
# Keys are geoBoundaries shapeName, values are the LGD district code.
GEOB_TO_LGD_MH = {
    "Ahmadnagar": "466",  # renamed Ahilyanagar (2024)
    "Akola": "467",
    "Amravati": "468",
    "Aurangabad": "469",  # renamed Chhatrapati Sambhajinagar (2023); also a Bihar district of the same old name
    "Bid": "470",  # Beed
    "Bhandara": "471",
    "Buldana": "472",  # Buldhana
    "Chandrapur": "473",
    "Dhule": "474",
    "Gadchiroli": "475",
    "Gondiya": "476",  # Gondia
    "Hingoli": "477",
    "Jalgaon": "478",
    "Jalna": "479",
    "Kolhapur": "480",
    "Latur": "481",
    "Mumbai": "482",  # Mumbai City
    "Mumbai Suburban": "483",
    "Nagpur": "484",
    "Nanded": "485",
    "Nandurbar": "486",
    "Nashik": "487",
    "Osmanabad": "488",  # renamed Dharashiv (2023)
    "Parbhani": "489",
    "Pune": "490",
    "Raigarh": "491",  # Raigad (Maharashtra); Raigarh is also a Chhattisgarh district
    "Ratnagiri": "492",
    "Sangli": "493",
    "Satara": "494",
    "Sindhudurg": "495",
    "Solapur": "496",
    "Thane": "497",
    "Wardha": "498",
    "Washim": "499",
    "Yavatmal": "500",
    "Palghar": "665",
}
MH_BBOX = (72.5, 15.5, 81.0, 22.2)  # lon_min, lat_min, lon_max, lat_max


def http_get(url: str, *, accept: str = "*/*", timeout: int = 120, data: bytes | None = None) -> bytes:
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, "Accept": accept})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def sparql(query: str) -> list[dict]:
    url = SPARQL + "?" + urllib.parse.urlencode({"query": query})
    body = http_get(url, accept="application/sparql-results+json", timeout=180)
    rows = json.loads(body)["results"]["bindings"]
    return [{k: v["value"] for k, v in r.items()} for r in rows]


def qid(uri: str) -> str:
    return uri.rsplit("/", 1)[-1]


def parse_point(wkt: str | None) -> tuple[float, float] | tuple[None, None]:
    if not wkt:
        return None, None
    m = re.match(r"Point\(([-\d.]+) ([-\d.]+)\)", wkt)
    return (float(m.group(1)), float(m.group(2))) if m else (None, None)


def strip_suffix(label: str) -> str:
    return re.sub(r"\s+(district|subdivision|tehsil|taluka|taluk|mandal|block|circle)$", "", label, flags=re.I).strip()


def fetch_lgd() -> None:
    print("Wikidata: LGD states ...")
    states = sparql(
        'SELECT ?s ?sLabel ?code WHERE { ?s wdt:P12747 ?code . '
        'SERVICE wikibase:label { bd:serviceParam wikibase:language "en". } }'
    )
    state_rows = {}
    for r in states:
        state_rows.setdefault(r["code"], {"lgd_code": r["code"], "name": r["sLabel"], "wikidata": qid(r["s"])})
    write_csv(REF / "lgd_states.csv", sorted(state_rows.values(), key=lambda r: int(r["lgd_code"])))

    print("Wikidata: LGD districts ...")
    districts = sparql(
        "SELECT DISTINCT ?d ?dLabel ?code ?scode ?coord WHERE { ?d wdt:P12746 ?code . "
        "OPTIONAL { ?d wdt:P131+ ?st . ?st wdt:P12747 ?scode . } OPTIONAL { ?d wdt:P625 ?coord } "
        'SERVICE wikibase:label { bd:serviceParam wikibase:language "en". } }'
    )
    drows: dict[str, dict] = {}
    for r in districts:
        lon, lat = parse_point(r.get("coord"))
        row = drows.setdefault(
            r["code"],
            {
                "lgd_code": r["code"],
                "name": strip_suffix(r["dLabel"]),
                "state_lgd_code": r.get("scode", ""),
                "state_name": state_rows.get(r.get("scode", ""), {}).get("name", ""),
                "wikidata": qid(r["d"]),
                "lon": lon,
                "lat": lat,
                "coord_variants": 0,
            },
        )
        if lon is not None and (row["lon"], row["lat"]) != (lon, lat):
            row["coord_variants"] += 1  # several conflicting coordinates on Wikidata: a data-quality signal
    write_csv(REF / "lgd_districts.csv", sorted(drows.values(), key=lambda r: int(r["lgd_code"])))

    print("Wikidata: LGD sub-districts ...")
    subs = sparql(
        "SELECT DISTINCT ?s ?sLabel ?code ?dcode WHERE { ?s wdt:P12748 ?code . "
        "OPTIONAL { ?s wdt:P131+ ?d . ?d wdt:P12746 ?dcode . } "
        'SERVICE wikibase:label { bd:serviceParam wikibase:language "en". } }'
    )
    srows: dict[str, dict] = {}
    for r in subs:
        srows.setdefault(
            r["code"],
            {"lgd_code": r["code"], "name": strip_suffix(r["sLabel"]), "district_lgd_code": r.get("dcode", ""), "wikidata": qid(r["s"])},
        )
    write_csv(REF / "lgd_subdistricts.csv", sorted(srows.values(), key=lambda r: int(r["lgd_code"])))
    print(f"  states={len(state_rows)} districts={len(drows)} subdistricts={len(srows)}")


def ring_centroid(geom: dict) -> tuple[float, float]:
    polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    xs, ys = [], []
    for p in polys:
        for x, y in p[0]:
            xs.append(x)
            ys.append(y)
    return sum(xs) / len(xs), sum(ys) / len(ys)


def fetch_boundaries() -> None:
    print("geoBoundaries: IND ADM2 ...")
    meta = json.loads(http_get(GEOB_API))
    gj = json.loads(http_get(meta["simplifiedGeometryGeoJSON"], timeout=300))
    names = {r["lgd_code"]: r["name"] for r in read_csv(REF / "lgd_districts.csv")}
    feats = []
    for f in gj["features"]:
        name = f["properties"]["shapeName"]
        if name not in GEOB_TO_LGD_MH:
            continue
        x, y = ring_centroid(f["geometry"])
        lon0, lat0, lon1, lat1 = MH_BBOX
        if not (lon0 < x < lon1 and lat0 < y < lat1):
            continue  # same old name in another state (Aurangabad, Bihar; Raigarh, Chhattisgarh)
        code = GEOB_TO_LGD_MH[name]
        feats.append(
            {
                "type": "Feature",
                "properties": {"lgd_code": code, "name": names.get(code, name), "source_name": name, "centroid": [round(x, 4), round(y, 4)]},
                "geometry": f["geometry"],
            }
        )
    missing = set(GEOB_TO_LGD_MH.values()) - {f["properties"]["lgd_code"] for f in feats}
    if missing:
        print("  WARNING: no polygon for LGD codes", sorted(missing))
    out = {
        "type": "FeatureCollection",
        "name": "maharashtra_districts",
        "license": meta.get("boundaryLicense"),
        "attribution": "geoBoundaries (wmgeolab), source: " + meta.get("boundarySource", ""),
        "features": sorted(feats, key=lambda f: f["properties"]["lgd_code"]),
    }
    (REF / "maharashtra_districts.geojson").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(f"  wrote {len(feats)} Maharashtra districts")


def fetch_osm_hospitals() -> None:
    print("Overpass: hospitals in Maharashtra ...")
    q = (
        '[out:json][timeout:180];area["ISO3166-2"="IN-MH"][admin_level=4]->.mh;'
        '(node["amenity"="hospital"](area.mh);way["amenity"="hospital"](area.mh);relation["amenity"="hospital"](area.mh););'
        "out center tags;"
    )
    body = None
    for url in OVERPASS_MIRRORS:  # the public instances shed load; try mirrors before failing
        try:
            body = http_get(url, data=urllib.parse.urlencode({"data": q}).encode(), timeout=300)
            break
        except Exception as exc:  # noqa: BLE001
            print(f"  {url}: {exc}; trying next mirror")
            time.sleep(5)
    if body is None:
        raise RuntimeError("all Overpass mirrors failed")
    elements = json.loads(body)["elements"]
    feats = []
    for e in elements:
        lon = e.get("lon", e.get("center", {}).get("lon"))
        lat = e.get("lat", e.get("center", {}).get("lat"))
        if lon is None:
            continue
        t = e.get("tags", {})
        feats.append(
            {
                "type": "Feature",
                "properties": {
                    "osm_id": f"{e['type']}/{e['id']}",
                    "name": t.get("name") or t.get("name:en") or "Unnamed hospital",
                    "name_local": t.get("name:mr") or t.get("name:hi") or "",
                    "operator_type": t.get("operator:type", ""),
                    "beds": t.get("beds", ""),
                    "emergency": t.get("emergency", ""),
                    "healthcare": t.get("healthcare", ""),
                },
                "geometry": {"type": "Point", "coordinates": [round(lon, 6), round(lat, 6)]},
            }
        )
    out = {"type": "FeatureCollection", "license": "ODbL 1.0", "attribution": "© OpenStreetMap contributors", "features": feats}
    (REF / "osm_maharashtra_hospitals.geojson").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(f"  wrote {len(feats)} hospitals")


def fetch_sachet_snapshot(n_cap: int = 25) -> None:
    print("SACHET: snapshot of the national CAP feed ...")
    dest = SAMPLES / "sachet"
    dest.mkdir(parents=True, exist_ok=True)
    rss = http_get(SACHET_RSS, timeout=60)
    (dest / "rss_india.xml").write_bytes(rss)
    ids = re.findall(rb"identifier=(\d+)", rss)
    seen: list[bytes] = []
    for i in ids:
        if i not in seen:
            seen.append(i)
    for i in seen[:n_cap]:
        try:
            (dest / f"cap_{i.decode()}.xml").write_bytes(http_get(SACHET_CAP.format(i.decode()), timeout=60))
            time.sleep(0.3)
        except Exception as exc:  # noqa: BLE001 - snapshot is best-effort
            print("  skip", i, exc)
    print(f"  wrote rss + {min(n_cap, len(seen))} CAP files")


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--skip-osm", action="store_true")
    ap.add_argument("--skip-sachet", action="store_true")
    ap.add_argument("--only", choices=["lgd", "boundaries", "osm", "sachet"], help="run a single step")
    args = ap.parse_args()
    REF.mkdir(parents=True, exist_ok=True)
    if args.only:
        {"lgd": fetch_lgd, "boundaries": fetch_boundaries, "osm": fetch_osm_hospitals, "sachet": fetch_sachet_snapshot}[args.only]()
        return 0
    fetch_lgd()
    fetch_boundaries()
    if not args.skip_osm:
        fetch_osm_hospitals()
    if not args.skip_sachet:
        fetch_sachet_snapshot()
    return 0


if __name__ == "__main__":
    sys.exit(main())

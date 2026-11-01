"""OpenStreetMap connector: hospitals as Asset objects located in LGD districts.

Data: data/reference/osm_maharashtra_hospitals.geojson (Overpass extract, ODbL,
© OpenStreetMap contributors). Re-fetch with scripts/fetch_reference_data.py --only osm.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..geo import PolygonIndex
from ..store import Store
from .lgd import adminunit_id

SOURCE = "OSM"


def load_hospitals(store: Store, reference_dir: Path) -> dict[str, int]:
    path = reference_dir / "osm_maharashtra_hospitals.geojson"
    if not path.exists():
        return {"hospitals": 0}
    districts = [(d["props"]["lgd_code"], d["geom"]) for d in store.objects_of_type("AdminUnit", with_geom=True) if d.get("geom")]
    index = PolygonIndex(districts)
    n = located = 0
    with store.tx():
        for f in json.loads(path.read_text(encoding="utf-8"))["features"]:
            p = f["properties"]
            lon, lat = f["geometry"]["coordinates"]
            code = index.lookup(lon, lat)
            beds = int(p["beds"]) if str(p.get("beds", "")).isdigit() else None
            oid = store.upsert_object(
                "Asset",
                {"name": p["name"], "asset_type": "hospital", "capacity": beds, "status": "unknown", "district_lgd": code,
                 "osm_id": p["osm_id"], "operator_type": p.get("operator_type") or None, "emergency": p.get("emergency") or None},
                source=SOURCE, record=p["osm_id"], lat=lat, lon=lon,
            )
            n += 1
            if code:
                store.upsert_link("located_in", oid, adminunit_id("district", code), source=SOURCE, record=p["osm_id"])
                located += 1
    return {"hospitals": n, "located_in_district": located}

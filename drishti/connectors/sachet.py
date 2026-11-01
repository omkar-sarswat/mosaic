"""NDMA SACHET connector: CAP 1.2 disaster alerts -> Hazard objects linked to districts.

Findings from the live feed (Oct 2026) that shape this connector:

* The national RSS (rss_india.xml) lists ~100 current alerts; each <link> points to a
  CAP 1.2 XML file (FetchXMLFile?identifier=...).
* Alerts usually carry two <info> blocks: en-IN plus a regional language (TL, HI ...).
  We keep the English block for display and store the regional headline as the original.
* Geometry is NOT inline. Many alerts carry <geocode> "LGD District Code" values (IMD,
  several SDMAs); others only a "Polygon URL" parameter (FetchPolygonXMLFile), which
  returned HTTP 403 to non-browser clients during our tests; the rest give free text such
  as "nlr-chillakur Mandal" or "pauri almora chamoli".
* Geocoding order: LGD geocode -> inline polygon -> gazetteer on areaDesc -> unresolved.
* CWC flood alerts embed gauge readings in a fixed sentence; we parse level, warning
  level and danger level into the Hazard.
"""

from __future__ import annotations

import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..store import Store
from .lgd import Gazetteer, adminunit_id

SOURCE = "NDMA-SACHET"
RSS_URL = "https://sachet.ndma.gov.in/cap_public_website/rss/rss_india.xml"
UA = "Mosaic/0.1 (Weirwood; open-source research prototype)"
NS = {"cap": "urn:oasis:names:tc:emergency:cap:1.2"}
CWC_RE = re.compile(
    r"River (?P<river>.+?) at (?P<station>.+?) in (?P<district>.+?) district of (?P<state>[A-Za-z ]+?) .*?"
    r"level of (?P<level>[\d.]+) m with (?P<trend>\w+) trend.*?Warning Level of (?P<warning>[\d.]+) m.*?Danger Level of (?P<danger>[\d.]+) m",
    re.S,
)
SEVERITIES = {"Extreme", "Severe", "Moderate", "Minor", "Unknown"}


def _get(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def parse_rss(xml: bytes) -> list[dict[str, str]]:
    root = ET.fromstring(xml)
    out = []
    for item in root.iter("item"):
        out.append({k: (item.findtext(k) or "").strip() for k in ("title", "link", "author", "guid", "pubDate", "category")})
    return out


def _t(el: ET.Element, path: str) -> str:
    return (el.findtext(path, namespaces=NS) or "").strip()


def parse_cap(xml: bytes) -> dict[str, Any]:
    root = ET.fromstring(xml)
    alert = {k: _t(root, f"cap:{k}") for k in ("identifier", "sender", "sent", "status", "msgType", "scope")}
    infos = []
    for info in root.findall("cap:info", NS):
        areas = []
        for area in info.findall("cap:area", NS):
            areas.append({
                "areaDesc": _t(area, "cap:areaDesc"),
                "polygons": [p.text.strip() for p in area.findall("cap:polygon", NS) if p.text],
                "circles": [c.text.strip() for c in area.findall("cap:circle", NS) if c.text],
                "geocodes": [(_t(g, "cap:valueName"), _t(g, "cap:value")) for g in area.findall("cap:geocode", NS)],
            })
        infos.append({
            **{k: _t(info, f"cap:{k}") for k in ("language", "category", "event", "urgency", "severity", "certainty",
                                                 "effective", "onset", "expires", "headline", "description", "instruction", "senderName")},
            "parameters": {_t(p, "cap:valueName"): _t(p, "cap:value") for p in info.findall("cap:parameter", NS)},
            "areas": areas,
        })
    alert["infos"] = infos
    return alert


def _polygon_geojson(cap_polygon: str) -> dict:
    # CAP polygons are "lat,lon lat,lon ..." -> GeoJSON [lon, lat]
    ring = [[float(p.split(",")[1]), float(p.split(",")[0])] for p in cap_polygon.split()]
    return {"type": "Polygon", "coordinates": [ring]}


def ingest_alert(store: Store, gaz: Gazetteer, alert: dict[str, Any], district_polygons: dict[str, dict]) -> dict[str, Any]:
    infos = alert["infos"]
    en = next((i for i in infos if i["language"].lower().startswith("en")), None)
    other = next((i for i in infos if not i["language"].lower().startswith("en")), None)
    info = en or infos[0]
    headline = info["headline"] or info["description"][:200]
    props: dict[str, Any] = {
        "headline": headline,
        "event": info["event"],
        "severity": info["severity"] if info["severity"] in SEVERITIES else "Unknown",
        "urgency": info["urgency"],
        "certainty": info["certainty"],
        "sender": alert["sender"],
        "effective": info["effective"] or alert["sent"],
        "expires": info["expires"],
        "description": info["description"],
        "instruction": info["instruction"],
        "cap_identifier": alert["identifier"],
        "area_desc": "; ".join(a["areaDesc"] for a in info["areas"]),
        "translation_status": "source_english" if en else "pending",
    }
    if other and other["headline"]:
        props["headline_original"] = other["headline"]
        props["original_language"] = other["language"]
    if "Polygon URL" in info["parameters"]:
        props["polygon_url"] = info["parameters"]["Polygon URL"]
    m = CWC_RE.search(info["description"] or "")
    if m:
        props.update({
            "river": m["river"], "gauge_station": m["station"], "water_level_m": float(m["level"]), "trend": m["trend"],
            "warning_level_m": float(m["warning"]), "danger_level_m": float(m["danger"]),
            "above_danger": float(m["level"]) >= float(m["danger"]),
        })

    codes: list[str] = []
    method = "unresolved"
    geom = None
    for a in info["areas"]:
        lgd = [v for n, v in a["geocodes"] if "lgd" in n.lower() and "district" in n.lower()]
        if lgd:
            codes += lgd
            method = "cap_geocode_lgd"
        elif a["polygons"]:
            geom = _polygon_geojson(a["polygons"][0])
            method = "cap_polygon"
        else:
            found, how = gaz.resolve(a["areaDesc"])
            if found:
                codes += found
                method = how if method == "unresolved" else method
    if m and not codes:
        found, how = gaz.resolve(f"{m['district']}, {m['state']}")
        codes, method = found, how
    props["geocode_method"] = method
    hid = store.upsert_object("Hazard", props, source=SOURCE, record=alert["identifier"], geom=geom,
                              confidence={"cap_geocode_lgd": 1.0, "cap_polygon": 1.0, "district_name": 0.85}.get(method, 0.7))
    linked = 0
    for code in dict.fromkeys(codes):
        target = adminunit_id("district", code)
        if store.get_object(target):
            store.upsert_link("affects", hid, target, source=SOURCE, record=alert["identifier"],
                              confidence=1.0 if method == "cap_geocode_lgd" else 0.8, props={"method": method})
            linked += 1
    # centroid of affected districts for the map pin
    pts = [store.get_object(adminunit_id("district", c)) for c in codes]
    pts = [p for p in pts if p and p["lon"] is not None]
    if pts:
        lon = sum(p["lon"] for p in pts) / len(pts)
        lat = sum(p["lat"] for p in pts) / len(pts)
        with store.tx() as conn:
            conn.execute("UPDATE objects SET lon=?, lat=? WHERE id=?", (lon, lat, hid))
    return {"id": hid, "method": method, "districts": linked}


def ingest_sachet(store: Store, gaz: Gazetteer, *, sample_dir: Path | None = None, limit: int = 80) -> dict[str, Any]:
    """Ingest from the live feed, or from a saved snapshot when sample_dir is given."""
    caps: list[bytes] = []
    if sample_dir:
        caps = [p.read_bytes() for p in sorted(Path(sample_dir).glob("cap_*.xml"))][:limit]
    else:
        items = parse_rss(_get(RSS_URL))
        seen = set()
        for it in items:
            m = re.search(r"identifier=(\d+)", it["link"])
            if not m or m.group(1) in seen:
                continue
            seen.add(m.group(1))
            try:
                caps.append(_get(it["link"]))
            except Exception:  # noqa: BLE001 - a single bad alert must not stop ingestion
                continue
            if len(caps) >= limit:
                break
    methods: dict[str, int] = {}
    errors = 0
    with store.tx():
        for xml in caps:
            try:
                r = ingest_alert(store, gaz, parse_cap(xml), {})
                methods[r["method"]] = methods.get(r["method"], 0) + 1
            except ET.ParseError:
                errors += 1
    store.set_meta("sachet_last_run", {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "alerts": len(caps), "methods": methods})
    return {"alerts": len(caps), "geocode_methods": methods, "parse_errors": errors}

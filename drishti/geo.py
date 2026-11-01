"""Small dependency-free geometry helpers (PostGIS replaces these at state scale)."""

from __future__ import annotations

from typing import Iterable

Ring = list[list[float]]


def _rings(geom: dict) -> Iterable[list[Ring]]:
    if geom["type"] == "Polygon":
        yield geom["coordinates"]
    elif geom["type"] == "MultiPolygon":
        yield from geom["coordinates"]


def _in_ring(x: float, y: float, ring: Ring) -> bool:
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def point_in_geometry(lon: float, lat: float, geom: dict) -> bool:
    for poly in _rings(geom):
        if _in_ring(lon, lat, poly[0]) and not any(_in_ring(lon, lat, hole) for hole in poly[1:]):
            return True
    return False


def bbox(geom: dict) -> tuple[float, float, float, float]:
    xs, ys = [], []
    for poly in _rings(geom):
        for x, y in poly[0]:
            xs.append(x)
            ys.append(y)
    return min(xs), min(ys), max(xs), max(ys)


def centroid(geom: dict) -> tuple[float, float]:
    """Area-weighted centroid of the outer rings (good enough for labels and map pins)."""
    ax = ay = area_total = 0.0
    for poly in _rings(geom):
        ring = poly[0]
        a = cx = cy = 0.0
        for i in range(len(ring) - 1):
            x0, y0 = ring[i][0], ring[i][1]
            x1, y1 = ring[i + 1][0], ring[i + 1][1]
            cross = x0 * y1 - x1 * y0
            a += cross
            cx += (x0 + x1) * cross
            cy += (y0 + y1) * cross
        if a:
            ax += cx / 3.0
            ay += cy / 3.0
            area_total += a
    if not area_total:
        x0, y0, x1, y1 = bbox(geom)
        return (x0 + x1) / 2, (y0 + y1) / 2
    return ax / area_total, ay / area_total


class PolygonIndex:
    """Point-in-polygon lookup with a bounding-box prefilter."""

    def __init__(self, items: Iterable[tuple[str, dict]]):
        self._items = [(key, geom, bbox(geom)) for key, geom in items]

    def lookup(self, lon: float, lat: float) -> str | None:
        for key, geom, (x0, y0, x1, y1) in self._items:
            if x0 <= lon <= x1 and y0 <= lat <= y1 and point_in_geometry(lon, lat, geom):
                return key
        return None

import { useEffect, useMemo, useState } from 'react'
import type { Feature, FeatureCollection, Geometry, Position } from 'geojson'
import { api } from '../api'

// Where the extract's rows sit, drawn over district boundaries (public LGD geometry) with a local
// equirectangular projection. No tile server is needed, so it works on an isolated network.
type Place = { city: string; lat: number | null; lon: number | null; rows: number; existing?: number; probable?: number; new?: number }

let cache: Promise<FeatureCollection> | null = null

function rings(g: Geometry): Position[][] {
  if (g.type === 'Polygon') return g.coordinates
  if (g.type === 'MultiPolygon') return g.coordinates.flat()
  return []
}

export default function PlacesMap({ places, height = 300 }: { places: Place[]; height?: number }) {
  const [fc, setFc] = useState<FeatureCollection | null>(null)
  useEffect(() => {
    if (!cache) cache = api.districts()
    cache.then(setFc).catch(() => setFc(null))
  }, [])
  const placed = places.filter((p) => p.lat != null && p.lon != null) as (Place & { lat: number; lon: number })[]
  const W = 520, H = height
  const proj = useMemo(() => {
    if (!placed.length) return null
    const lats = placed.map((p) => p.lat), lons = placed.map((p) => p.lon)
    const pad = 0.9
    const [y0, y1, x0, x1] = [Math.min(...lats) - pad, Math.max(...lats) + pad, Math.min(...lons) - pad, Math.max(...lons) + pad]
    const k = Math.cos(((y0 + y1) / 2) * Math.PI / 180)
    const s = Math.min((W - 40) / ((x1 - x0) * k), (H - 40) / (y1 - y0))
    const ox = (W - (x1 - x0) * k * s) / 2, oy = (H - (y1 - y0) * s) / 2
    return { f: (lon: number, lat: number) => [ox + (lon - x0) * k * s, oy + (y1 - lat) * s] as [number, number], box: [x0, x1, y0, y1] }
  }, [placed, H])
  const paths = useMemo(() => {
    if (!fc || !proj) return []
    const [x0, x1, y0, y1] = proj.box
    return fc.features.flatMap((ft: Feature) => {
      if (!ft.geometry) return []
      const rs = rings(ft.geometry)
      const inside = rs.some((r) => r.some(([x, y]) => x >= x0 && x <= x1 && y >= y0 && y <= y1))
      if (!inside) return []
      return [rs.map((r) => 'M' + r.map(([x, y]) => proj.f(x, y).map((v) => v.toFixed(1)).join(',')).join('L') + 'Z').join(' ')]
    })
  }, [fc, proj])
  if (!places.length) return <p className="muted small">The mapping places no row on the map. Map a column to geo.city to see where the rows sit.</p>
  const max = Math.max(...placed.map((p) => p.rows), 1)
  const unplaced = places.filter((p) => p.lat == null)
  // greedy label placement, busiest places first: right, left, above, below; a label that would collide is left to the tooltip
  const labels = new Map<string, { x: number; y: number; anchor: 'start' | 'end' | 'middle' }>()
  if (proj) {
    const boxes: [number, number, number, number][] = placed.map((p) => {
      const [x, y] = proj.f(p.lon, p.lat)
      const r = 4 + 14 * Math.sqrt(p.rows / max)
      return [x - r, y - r, x + r, y + r]
    })
    const hit = (b: [number, number, number, number]) => b[0] < 2 || b[2] > W - 2 || b[1] < 2 || b[3] > H - 2 || boxes.some((o) => b[0] < o[2] && b[2] > o[0] && b[1] < o[3] && b[3] > o[1])
    for (const p of [...placed].sort((a, b) => b.rows - a.rows)) {
      const [x, y] = proj.f(p.lon, p.lat)
      const r = 4 + 14 * Math.sqrt(p.rows / max)
      const w = (p.city.length + String(p.rows).length + 3) * 6.1, h = 13
      const tries: [number, number, number, number, number, number, 'start' | 'end' | 'middle'][] = [
        [x + r + 3, y - h / 2, x + r + 3 + w, y + h / 2, x + r + 4, y + 4, 'start'],
        [x - r - 3 - w, y - h / 2, x - r - 3, y + h / 2, x - r - 4, y + 4, 'end'],
        [x - w / 2, y - r - 3 - h, x + w / 2, y - r - 3, x, y - r - 5, 'middle'],
        [x - w / 2, y + r + 3, x + w / 2, y + r + 3 + h, x, y + r + 14, 'middle'],
      ]
      const ok = tries.find(([a, b, c, d]) => !hit([a, b, c, d]))
      if (ok) {
        labels.set(p.city, { x: ok[4], y: ok[5], anchor: ok[6] })
        boxes.push([ok[0], ok[1], ok[2], ok[3]])
      }
    }
  }
  return (
    <div>
      {proj && (
        <svg className="places-map" viewBox={`0 0 ${W} ${H}`} width="100%" style={{ maxHeight: H }} role="img" aria-label="Rows by place">
          <g className="districts">{paths.map((d, i) => <path key={i} d={d} />)}</g>
          {placed.map((p) => {
            const [x, y] = proj.f(p.lon, p.lat)
            const r = 4 + 14 * Math.sqrt(p.rows / max)
            const newShare = (p.new ?? 0) + (p.probable ?? 0)
            return (
              <g key={p.city}>
                <circle cx={x} cy={y} r={r} className="place-dot" />
                {newShare > 0 && <circle cx={x} cy={y} r={Math.max(2.5, r * Math.sqrt(newShare / p.rows))} className="place-new" />}
                {labels.has(p.city) && <text x={labels.get(p.city)!.x} y={labels.get(p.city)!.y} textAnchor={labels.get(p.city)!.anchor} className="place-label">{p.city} · {p.rows}</text>}
                <title>{`${p.city}: ${p.rows} rows (${p.existing ?? 0} on record, ${p.probable ?? 0} probable, ${p.new ?? 0} new)`}</title>
              </g>
            )
          })}
        </svg>
      )}
      <div className="small muted" style={{ marginTop: 4 }}>
        Circle area ∝ rows; the inner disc is the share not yet on record. Labels that would overlap are in the tooltip.{unplaced.length > 0 && ` Not placed (no coordinates on record): ${unplaced.map((p) => p.city).join(', ')}.`}
      </div>
    </div>
  )
}

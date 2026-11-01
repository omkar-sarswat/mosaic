import { Checkbox, Spinner, Tag } from '@blueprintjs/core'
import { Button } from '../components/Button'
import type { FeatureCollection } from 'geojson'
import * as maplibregl from 'maplibre-gl'
import type { GeoJSONSource } from 'maplibre-gl'
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url'
import { useEffect, useRef, useState } from 'react'
import { intel, type GlobeData } from '../api'
import { inr } from "../lib/format"
import type { Nav } from './nav'
import { colours, moneyColours, theme as currentTheme, typeColour } from '../lib/palette'
import { SegmentedControl } from '@mantine/core'
import { AreaItemPanel, AreaSearch, type AreaPick } from '../components/AreaSearch'

maplibregl.setWorkerUrl(workerUrl)

// great-circle points between two lon/lat pairs, lifted into a visible arc
function arc(a: [number, number], b: [number, number], n = 48): [number, number][] {
  const toR = Math.PI / 180
  const [l1, p1] = [a[0] * toR, a[1] * toR]
  const [l2, p2] = [b[0] * toR, b[1] * toR]
  const d = 2 * Math.asin(Math.sqrt(Math.sin((p2 - p1) / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin((l2 - l1) / 2) ** 2)) || 1e-9
  const out: [number, number][] = []
  for (let i = 0; i <= n; i++) {
    const f = i / n
    const A = Math.sin((1 - f) * d) / Math.sin(d)
    const B = Math.sin(f * d) / Math.sin(d)
    const x = A * Math.cos(p1) * Math.cos(l1) + B * Math.cos(p2) * Math.cos(l2)
    const y = A * Math.cos(p1) * Math.sin(l1) + B * Math.cos(p2) * Math.sin(l2)
    const z = A * Math.sin(p1) + B * Math.sin(p2)
    out.push([Math.atan2(y, x) / toR, Math.atan2(z, Math.sqrt(x * x + y * y)) / toR])
  }
  return out
}

/** A slim chevron, outlined so it reads on top of its own line; one per money line shows which way the money went. */
function chevronImage(colour: string, halo: string) {
  const size = 32
  const canvas = document.createElement('canvas')
  canvas.width = canvas.height = size
  const g = canvas.getContext('2d')!
  g.lineCap = 'round'
  g.lineJoin = 'round'
  for (const [stroke, width] of [[halo, 9], [colour, 4.5]] as const) {
    g.strokeStyle = stroke
    g.lineWidth = width
    g.beginPath()
    g.moveTo(12, 8)
    g.lineTo(21, 16)
    g.lineTo(12, 24)
    g.stroke()
  }
  return g.getImageData(0, 0, size, size)
}

/** The point a share `f` of the way along a line, and the compass bearing of the line there. */
function along(coords: [number, number][], f: number): { at: [number, number]; bearing: number } {
  const seg = coords.slice(1).map((b, i) => {
    const a = coords[i]
    const k = Math.cos(((a[1] + b[1]) / 2) * Math.PI / 180)
    return Math.hypot((b[0] - a[0]) * k, b[1] - a[1])
  })
  let goal = seg.reduce((x, y) => x + y, 0) * f
  for (let i = 0; i < seg.length; i++) {
    if (goal <= seg[i] || i === seg.length - 1) {
      const a = coords[i]
      const b = coords[i + 1]
      const t = seg[i] ? Math.min(1, goal / seg[i]) : 0
      const k = Math.cos(a[1] * Math.PI / 180)
      return { at: [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t], bearing: (Math.atan2((b[0] - a[0]) * k, b[1] - a[1]) * 180) / Math.PI }
    }
    goal -= seg[i]
  }
  return { at: coords[0], bearing: 0 }
}

const kmBetween = (a: [number, number], b: [number, number]) =>
  Math.hypot((b[0] - a[0]) * Math.cos(((a[1] + b[1]) / 2) * Math.PI / 180), b[1] - a[1]) * 111

/** A line between two places: a great circle when far apart; a gentle bow when close, bowing to the right of travel so
 * money going each way between two parties draws as two separate lines. */
function link(a: [number, number], b: [number, number]): [number, number][] {
  const km = Math.hypot((b[0] - a[0]) * Math.cos(((a[1] + b[1]) / 2) * Math.PI / 180), b[1] - a[1]) * 111
  if (km > 400) return arc(a, b)
  const [dx, dy] = [b[0] - a[0], b[1] - a[1]]
  const c: [number, number] = [(a[0] + b[0]) / 2 + dy * 0.18, (a[1] + b[1]) / 2 - dx * 0.18]
  const out: [number, number][] = []
  for (let i = 0; i <= 24; i++) {
    const t = i / 24
    out.push([(1 - t) ** 2 * a[0] + 2 * (1 - t) * t * c[0] + t ** 2 * b[0], (1 - t) ** 2 * a[1] + 2 * (1 - t) * t * c[1] + t ** 2 * b[1]])
  }
  return out
}

export default function Globe({ caseId, nav }: { caseId: string | null; nav: Nav }) {
  const el = useRef<HTMLDivElement>(null)
  const map = useRef<maplibregl.Map | null>(null)
  const [data, setData] = useState<GlobeData | null>(null)
  const [scope, setScope] = useState<'case' | 'all'>(caseId ? 'case' : 'all')
  const [layers, setLayers] = useState({ money: true, ties: true, inferred: false, travel: true, entities: true, incidents: true })
  // with a case open the map goes straight to the case; the turning globe is only for the national picture
  const [spin, setSpin] = useState(!(caseId || nav.caseId))
  const [sel, setSel] = useState<GlobeData['entities'][number] | null>(null)
  // a watched area opens here as `area:lat,lon,radius,label`
  const opened = nav.focus?.startsWith('area:') ? nav.focus.slice(5).split(',') : null
  const initialArea = opened && opened.length >= 4 ? { lat: +opened[0], lon: +opened[1], radius: +opened[2], label: opened.slice(3).join(',') } : undefined
  const [mode, setMode] = useState<'overview' | 'area'>(initialArea ? 'area' : 'overview')
  const [mapReady, setMapReady] = useState(false)
  const [areaPick, setAreaPick] = useState<AreaPick>(null)
  const ready = useRef(false)
  const canSearchArea = !!nav.caseId && !!nav.me?.roles.some((r) => ['io', 'supervisor', 'analyst'].includes(r))

  useEffect(() => {
    setData(null)
    intel.globe(scope === 'case' && (caseId || nav.caseId) ? caseId || nav.caseId : undefined).then(setData).catch((e) => nav.setError(e.message))
  }, [scope, caseId, nav])

  useEffect(() => {
    if (!el.current) return
    const m = new maplibregl.Map({
      container: el.current,
      style: `https://tiles.openfreemap.org/styles/${currentTheme() === 'dark' ? 'dark' : 'positron'}`,
      center: [70, 20],
      zoom: 2.1,
      attributionControl: { compact: true },
    })
    m.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), 'top-right')
    m.on('styleimagemissing', (e) => { if (!m.hasImage(e.id)) m.addImage(e.id, { width: 1, height: 1, data: new Uint8Array(4) }) })
    m.on('style.load', () => {
      m.setProjection({ type: 'globe' })
      try {
        m.setSky({ 'atmosphere-blend': ['interpolate', ['linear'], ['zoom'], 0, 1, 5, 1, 7, 0] } as never)
      } catch {
        /* older styles */
      }
      for (const id of ['money', 'money-heads', 'ties', 'travel', 'incidents']) m.addSource(id, { type: 'geojson', data: { type: 'FeatureCollection', features: [] } })
      // recorded ties (director, owner, family, shared phone) as hairlines; machine-inferred ones dotted, and only on request
      m.addLayer({ id: 'ties', type: 'line', source: 'ties', filter: ['!', ['get', 'inferred']],
        paint: { 'line-color': colours().slate, 'line-width': 1, 'line-opacity': 0.45 }, layout: { 'line-cap': 'round' } })
      m.addLayer({ id: 'ties-inferred', type: 'line', source: 'ties', filter: ['get', 'inferred'],
        paint: { 'line-color': colours().slate, 'line-width': 1, 'line-opacity': 0.45, 'line-dasharray': [0.6, 2.6] }, layout: { 'line-cap': 'round' } })
      // people and companies close together gather into a numbered circle that opens on click
      m.addSource('entities', { type: 'geojson', data: { type: 'FeatureCollection', features: [] }, cluster: true, clusterRadius: 34, clusterMaxZoom: 13 })
      if (!m.hasImage('chevron-foreign')) m.addImage('chevron-foreign', chevronImage(moneyColours().foreign, colours().surface), { pixelRatio: 2 })
      if (!m.hasImage('chevron-domestic')) m.addImage('chevron-domestic', chevronImage(moneyColours().domestic, colours().surface), { pixelRatio: 2 })
      m.addLayer({ id: 'money', type: 'line', source: 'money', paint: { 'line-color': ['case', ['get', 'intl'], moneyColours().foreign, moneyColours().domestic], 'line-width': ['get', 'w'], 'line-opacity': 0.7 }, layout: { 'line-cap': 'round', 'line-join': 'round' } })
      m.addLayer({ id: 'money-heads', type: 'symbol', source: 'money-heads', layout: { 'icon-image': ['case', ['get', 'intl'], 'chevron-foreign', 'chevron-domestic'], 'icon-size': 0.8,
        'icon-rotate': ['get', 'rot'], 'icon-rotation-alignment': 'map', 'icon-allow-overlap': true, 'icon-ignore-placement': true } })
      m.addLayer({ id: 'travel', type: 'line', source: 'travel', paint: { 'line-color': colours().slate, 'line-width': 1.3, 'line-dasharray': [2, 2], 'line-opacity': 0.8 } })
      m.addLayer({ id: 'incidents', type: 'circle', source: 'incidents', paint: { 'circle-radius': 6, 'circle-color': ['get', 'colour'], 'circle-stroke-color': colours().surface, 'circle-stroke-width': 2 } })
      m.addLayer({ id: 'entity-clusters', type: 'circle', source: 'entities', filter: ['has', 'point_count'],
        paint: { 'circle-radius': ['step', ['get', 'point_count'], 13, 5, 16, 15, 20], 'circle-color': colours().ink, 'circle-stroke-color': colours().surface, 'circle-stroke-width': 2 } })
      m.addLayer({ id: 'entity-cluster-count', type: 'symbol', source: 'entities', filter: ['has', 'point_count'],
        layout: { 'text-field': ['get', 'point_count_abbreviated'], 'text-font': ['Noto Sans Bold'], 'text-size': 12, 'text-allow-overlap': true },
        paint: { 'text-color': colours().surface } })
      m.addLayer({ id: 'entities', type: 'circle', source: 'entities', filter: ['!', ['has', 'point_count']],
        paint: { 'circle-radius': ['interpolate', ['linear'], ['get', 'score'], 0, 5, 100, 9], 'circle-color': ['get', 'colour'], 'circle-stroke-color': colours().surface, 'circle-stroke-width': 1.5 } })
      m.addLayer({ id: 'entity-selected', type: 'circle', source: 'entities', filter: ['==', ['get', 'id'], ''],
        paint: { 'circle-radius': 13, 'circle-color': 'rgba(0,0,0,0)', 'circle-stroke-color': colours().buff, 'circle-stroke-width': 2.5 } })
      m.addLayer({ id: 'entity-labels', type: 'symbol', source: 'entities', filter: ['!', ['has', 'point_count']],
        layout: { 'text-field': ['get', 'label'], 'text-font': ['Noto Sans Regular'], 'text-size': 11.5, 'text-variable-anchor': ['top', 'bottom', 'left', 'right'],
          'text-radial-offset': 0.9, 'text-justify': 'auto', 'text-optional': true },
        paint: { 'text-color': colours().text, 'text-halo-color': colours().surface, 'text-halo-width': 1.6 } })
      // one click does one thing: the topmost of a group circle, a person, a case record, a money line
      m.on('click', (e) => {
        const order = ['entity-clusters', 'entities', 'incidents', 'money', 'ties', 'ties-inferred'].filter((l) => m.getLayer(l) && m.getLayoutProperty(l, 'visibility') !== 'none')
        const hits = m.queryRenderedFeatures(e.point, { layers: order })
        const f = order.map((l) => hits.find((h) => h.layer.id === l)).find(Boolean)
        if (!f) {
          setSel(null)
          return
        }
        const p = f.properties as Record<string, string>
        if (f.layer.id === 'entity-clusters') {
          ;(m.getSource('entities') as GeoJSONSource).getClusterExpansionZoom(Number(p.cluster_id)).then((z) =>
            m.easeTo({ center: (f.geometry as GeoJSON.Point).coordinates as [number, number], zoom: z + 0.3, duration: 600 }))
        } else if (f.layer.id === 'entities') {
          setSel({ id: p.id, type: p.type, label: p.label, lon: 0, lat: 0, score: Number(p.score), role: p.role, city: p.city, place: p.place })
        } else if (f.layer.id === 'incidents') {
          nav.openEntity(p.id)
        } else {
          const box = document.createElement('div')
          const head = document.createElement('b')
          if (f.layer.id === 'money') {
            head.textContent = `${p.from} to ${p.to}`
            box.append(head, document.createElement('br'), `${inr(Number(p.amount))} in ${p.count} transfer${String(p.count) === '1' ? '' : 's'}`)
          } else {
            head.textContent = `${p.a_label} and ${p.b_label}`
            box.append(head, document.createElement('br'), `${String(p.inferred) === 'true' ? 'Machine-inferred: ' : ''}${JSON.parse(String(p.kinds)).join(', ')}`)
          }
          new maplibregl.Popup({ closeButton: false, className: 'map-popup' }).setLngLat(e.lngLat).setDOMContent(box).addTo(m)
        }
      })
      for (const l of ['entities', 'incidents', 'entity-clusters', 'money', 'ties', 'ties-inferred'])
        (m.on('mouseenter', l, () => (m.getCanvas().style.cursor = 'pointer')), m.on('mouseleave', l, () => (m.getCanvas().style.cursor = '')))
      ready.current = true
      setMapReady(true)
      setData((d) => (d ? { ...d } : d))
    })
    m.on('mousedown', () => setSpin(false))
    map.current = m
    return () => {
      ready.current = false
      setMapReady(false)
      m.remove()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // an area search works at street level: the case-wide layers step back and the globe stops turning
  useEffect(() => {
    const m = map.current
    if (!m || !mapReady) return
    for (const id of ['money', 'money-heads', 'ties', 'ties-inferred', 'travel', 'entities', 'entity-labels', 'entity-clusters', 'entity-cluster-count', 'entity-selected', 'incidents'])
      if (m.getLayer(id)) m.setLayoutProperty(id, 'visibility', mode === 'area' ? 'none' : 'visible')
    if (mode === 'area') setSpin(false)
  }, [mode, mapReady])

  // slow rotation until the user takes over
  useEffect(() => {
    if (!spin) return
    const t = setInterval(() => {
      const m = map.current
      if (m && m.isStyleLoaded() && m.getZoom() < 3.5) m.easeTo({ center: [m.getCenter().lng + 1.2, m.getCenter().lat], duration: 1000, easing: (x) => x })
    }, 1000)
    return () => clearInterval(t)
  }, [spin])

  // Lines are drawn between what is on screen. While several people share one numbered circle, their lines are
  // merged into one per pair of circles (amounts summed); opening the circle splits them again. Lines inside one circle wait.
  const regroup = useRef<() => void>(() => undefined)
  regroup.current = () => {
    const m = map.current
    if (!m || !ready.current || !data || !m.getSource('entities')) return
    const src = m.getSource('entities') as GeoJSONSource
    const fc = (features: GeoJSON.Feature[]): FeatureCollection => ({ type: 'FeatureCollection', features })
    type Node = { key: string; coord: [number, number]; label: string }
    const where = new Map<string, Node>()
    const seen = new Set<number>()
    const pending: Promise<void>[] = []
    for (const f of m.querySourceFeatures('entities')) {
      const p = f.properties as Record<string, unknown>
      const coord = (f.geometry as GeoJSON.Point).coordinates as [number, number]
      if (p.cluster) {
        const cid = Number(p.cluster_id)
        if (seen.has(cid)) continue
        seen.add(cid)
        pending.push(src.getClusterLeaves(cid, 1000, 0).then((leaves) => {
          for (const l of leaves) where.set(String(l.properties?.id), { key: `c${cid}`, coord, label: `${p.point_count} people and firms` })
        }).catch(() => undefined))
      } else if (p.id) where.set(String(p.id), { key: String(p.id), coord, label: String(p.label) })
    }
    void Promise.all(pending).then(() => {
      const node = (id: string | undefined, coord: [number, number], label: string): Node => (id && where.get(id)) || { key: id || label, coord, label }
      const money = new Map<string, { a: Node; b: Node; amount: number; count: number; intl: boolean; ids: Set<string> }>()
      if (layers.money) for (const x of data.arcs) {
        const a = node(x.from_id, x.from_coord, x.from)
        const b = node(x.to_id, x.to_coord, x.to)
        if (a.key === b.key) continue
        const g = money.get(`${a.key}>${b.key}`) ?? { a, b, amount: 0, count: 0, intl: false, ids: new Set<string>() }
        g.amount += x.amount
        g.count += x.count
        g.intl ||= x.international
        if (x.from_id) g.ids.add(x.from_id)
        if (x.to_id) g.ids.add(x.to_id)
        money.set(`${a.key}>${b.key}`, g)
      }
      const max = Math.max(1, ...[...money.values()].map((g) => g.amount))
      const lines = [...money.values()].map((g) => {
        const coords = link(g.a.coord, g.b.coord)
        const head = along(coords, 0.58)
        const props = { intl: g.intl, w: 1.1 + 2.4 * Math.sqrt(g.amount / max), amount: g.amount, from: g.a.label, to: g.b.label, count: g.count,
          ids: `|${[...g.ids].join('|')}|`, km: kmBetween(g.a.coord, g.b.coord) }
        return { coords, head, props }
      })
      const ties = new Map<string, { a: Node; b: Node; kinds: Set<string>; inferred: boolean; ids: Set<string> }>()
      if (layers.ties) for (const t of data.ties ?? []) {
        if (t.inferred && !layers.inferred) continue
        const a = node(t.a, t.a_coord, t.a_label)
        const b = node(t.b, t.b_coord, t.b_label)
        if (a.key === b.key) continue
        const k = a.key < b.key ? `${a.key}|${b.key}` : `${b.key}|${a.key}`
        const g = ties.get(k) ?? { a, b, kinds: new Set<string>(), inferred: true, ids: new Set<string>() }
        t.kinds.forEach((x) => g.kinds.add(x))
        g.inferred &&= t.inferred
        g.ids.add(t.a)
        g.ids.add(t.b)
        ties.set(k, g)
      }
      ;(m.getSource('money') as GeoJSONSource).setData(fc(lines.map((l) => ({ type: 'Feature', properties: l.props, geometry: { type: 'LineString', coordinates: l.coords } }))))
      ;(m.getSource('money-heads') as GeoJSONSource).setData(fc(lines.map((l) => ({ type: 'Feature', properties: { ...l.props, rot: l.head.bearing - 90 },
        geometry: { type: 'Point', coordinates: l.head.at } }))))
      ;(m.getSource('ties') as GeoJSONSource).setData(fc([...ties.values()].map((g) => ({ type: 'Feature',
        properties: { a_label: g.a.label, b_label: g.b.label, kinds: JSON.stringify([...g.kinds]), inferred: g.inferred, ids: `|${[...g.ids].join('|')}|`,
          km: kmBetween(g.a.coord, g.b.coord) }, geometry: { type: 'LineString', coordinates: [g.a.coord, g.b.coord] } }))))
    })
  }

  useEffect(() => {
    const m = map.current
    if (!m || !mapReady) return
    let t: ReturnType<typeof setTimeout> | undefined
    const later = () => { clearTimeout(t); t = setTimeout(() => regroup.current(), 120) }
    const onData = (e: { sourceId?: string; isSourceLoaded?: boolean }) => { if (e.sourceId === 'entities' && e.isSourceLoaded) later() }
    m.on('moveend', later)
    m.on('sourcedata', onData)
    return () => { clearTimeout(t); m.off('moveend', later); m.off('sourcedata', onData) }
  }, [mapReady])

  useEffect(() => {
    const m = map.current
    if (!m || !ready.current || !data) return
    const fc = (features: GeoJSON.Feature[]): FeatureCollection => ({ type: 'FeatureCollection', features })
    ;(m.getSource('travel') as GeoJSONSource).setData(
      fc(layers.travel ? data.trips.map((t) => ({ type: 'Feature', properties: {}, geometry: { type: 'LineString', coordinates: arc(t.from_coord, t.to_coord) } })) : []),
    )
    ;(m.getSource('entities') as GeoJSONSource).setData(
      fc(
        layers.entities
          ? data.entities.map((e) => ({
              type: 'Feature',
              properties: { ...e, score: e.score ?? 10, colour: typeColour(e.type) },
              geometry: { type: 'Point', coordinates: [e.lon, e.lat] },
            }))
          : [],
      ),
    )
    ;(m.getSource('incidents') as GeoJSONSource).setData(
      fc(layers.incidents ? data.incidents.map((i) => ({ type: 'Feature', properties: { ...i, colour: data.agency_colours[i.agency] ?? colours().slate }, geometry: { type: 'Point', coordinates: [i.lon, i.lat] } })) : []),
    )
    regroup.current()
  }, [data, layers])

  // a case opens framed on its own records, not on the whole planet
  useEffect(() => {
    const m = map.current
    if (!m || !mapReady || !data?.bounds || mode !== 'overview') return
    const [w, s, e, n] = data.bounds
    setSpin(false)
    m.fitBounds([[w, s], [e, n]], { padding: { top: 70, bottom: 70, left: 70, right: 70 }, maxZoom: 11, duration: 1200 })
  }, [data, mapReady, mode])

  // fewer lines at once: short lines inside a city wait until the city is zoomed open, and a selected person's lines
  // come forward while the rest step back
  useEffect(() => {
    const m = map.current
    if (!m || !mapReady || !m.getLayer('entity-selected')) return
    m.setFilter('entity-selected', ['==', ['get', 'id'], sel?.id ?? ''])
    const id = sel?.id ?? ''
    const mine = (_a: string, _b: string) => ['in', `|${id || '~'}|`, ['get', 'ids']]
    const near = ['<', ['get', 'km'], 40]
    const fade = (normal: number) => (id ? 0.1 : normal)
    const opacity = (a: string, b: string, normal: number) => ['interpolate', ['linear'], ['zoom'],
      7, ['case', mine(a, b), 0.95, near, 0, fade(normal)],
      9.5, ['case', mine(a, b), 0.95, fade(normal)]]
    m.setPaintProperty('money', 'line-opacity', opacity('from_id', 'to_id', 0.7) as never)
    m.setPaintProperty('money-heads', 'icon-opacity', opacity('from_id', 'to_id', 0.9) as never)
    m.setPaintProperty('ties', 'line-opacity', opacity('a', 'b', 0.45) as never)
    m.setPaintProperty('ties-inferred', 'line-opacity', opacity('a', 'b', 0.45) as never)
  }, [sel, mapReady])

  const intl = data ? data.arcs.filter((a) => a.international) : []
  return (
    <div className="workspace" style={{ gridTemplateColumns: '300px 1fr 320px' }}>
      <aside className="panel">
        {canSearchArea && (
          <div className="section globe-mode">
            <SegmentedControl fullWidth size="xs" value={mode} onChange={(v) => setMode(v as 'overview' | 'area')} aria-label="Map mode"
              data={[{ value: 'overview', label: 'Case overview' }, { value: 'area', label: 'Search an area' }]} />
          </div>
        )}
        {mode === 'area' ? <AreaSearch map={map.current} ready={mapReady} nav={nav} picked={areaPick} onPick={setAreaPick} initial={initialArea} /> : <>
        <div className="section">
          <h3>Scope</h3>
          <div className="row">
            <Button small active={scope === 'case'} disabled={!(caseId || nav.caseId)} onClick={() => setScope('case')}>
              Active case
            </Button>
            <Button small active={scope === 'all'} onClick={() => setScope('all')}>
              Everything flagged
            </Button>
            {!data && <Spinner size={14} />}
          </div>
        </div>
        <div className="section">
          <h3>Layers</h3>
          <Checkbox checked={layers.money} label={`Money flows (${data?.arcs.length ?? 0})`} onChange={() => setLayers({ ...layers, money: !layers.money })} />
          {(data?.ties?.length ?? 0) > 0 && <Checkbox checked={layers.ties} label={`Relationships (${(data?.ties ?? []).filter((t) => !t.inferred).length})`} onChange={() => setLayers({ ...layers, ties: !layers.ties })} />}
          {(data?.ties ?? []).some((t) => t.inferred) && layers.ties && <Checkbox className="sub-check" checked={layers.inferred}
            label={`Machine-inferred links (${(data?.ties ?? []).filter((t) => t.inferred).length})`} onChange={() => setLayers({ ...layers, inferred: !layers.inferred })} />}
          <Checkbox checked={layers.travel} label={`Travel (${data?.trips.length ?? 0})`} onChange={() => setLayers({ ...layers, travel: !layers.travel })} />
          <Checkbox checked={layers.entities} label={`People & companies (${data?.entities.length ?? 0})`} onChange={() => setLayers({ ...layers, entities: !layers.entities })} />
          <Checkbox checked={layers.incidents} label={`Agency cases (${data?.incidents.length ?? 0})`} onChange={() => setLayers({ ...layers, incidents: !layers.incidents })} />
          <Checkbox checked={spin} label="Rotate the globe" onChange={() => setSpin(!spin)} />
          <div className="legend-line" aria-label="Map key">
            <span><i className="ln" style={{ background: moneyColours().foreign }} />Cross-border money</span>
            <span><i className="ln" style={{ background: moneyColours().domestic }} />Domestic money</span>
            <span><i className="ln dashed" style={{ color: colours().slate }} />Travel</span>
            <span><i className="ln" style={{ background: colours().slate, height: 2 }} />Relationship</span>
            <span><i className="ln dotted" style={{ color: colours().slate }} />Inferred link</span>
          </div>
        </div>
        <div className="section">
          <h3>Cross-border flows</h3>
          {intl.slice(0, 12).map((a, i) => (
            <div key={i} className="kv-row small">
              <span>{a.from} to {a.to}</span><span className="amount">{inr(a.amount)}</span>
            </div>
          ))}
          {!intl.length && <p className="muted small">None in this scope.</p>}
        </div>
        </>}
      </aside>
      <main className="canvas">
        <div ref={el} className="map" />
      </main>
      <aside className="panel right">
        {mode === 'area' && (areaPick ? <AreaItemPanel pick={areaPick} nav={nav} /> : <div className="panel-empty"><h3>Nothing selected</h3><p>Choose a vehicle, phone or traveller from the results to see the reads that place them in the area.</p></div>)}
        {mode === 'overview' && !sel && <div className="panel-empty"><h3>Nothing selected</h3><p>Select a person or company to bring their money and relationships forward. A numbered circle holds several close together: select it to open it. Lines inside a city appear as you zoom in.</p></div>}
        {mode === 'overview' && sel && (
          <div className="section">
            <Tag minimal>{sel.type}</Tag>
            <h2>{sel.label}</h2>
            {sel.role && sel.role !== 'null' && <p className="globe-role">{sel.role}</p>}
            {(sel.place || sel.city) && <div className="muted small">{sel.place && sel.place !== 'null' ? sel.place : sel.city}</div>}
            <div className="row" style={{ marginTop: 12 }}>
              <Button small icon="person" onClick={() => nav.openEntity(sel.id)}>
                Dossier
              </Button>
              <Button small icon="bank-account" onClick={() => nav.openTrace(sel.id)}>
                Money trail
              </Button>
              <Button small icon="graph" onClick={() => nav.openGraph(sel.id)}>
                Network
              </Button>
            </div>
          </div>
        )}
      </aside>
    </div>
  )
}

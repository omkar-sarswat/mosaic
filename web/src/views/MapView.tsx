import { Checkbox, HTMLSelect, InputGroup, NumericInput } from '@blueprintjs/core'
import { Button } from '../components/Button'
import * as maplibregl from 'maplibre-gl'
import type { FeatureCollection } from 'geojson'
// MapLibre v6 locates its worker relative to its own module URL, which a bundler rewrites;
// hand it the URL of the worker file that Vite emits instead.
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url'
import type { GeoJSONSource, StyleSpecification } from 'maplibre-gl'
import { useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../api'
import { type Shared, shortDate } from './shared'
import { colours, severityColours, theme as currentTheme } from '../lib/palette'

type Impact = Awaited<ReturnType<typeof api.impact>>
type HazardProps = { id: string; event: string; severity: string; headline: string; sender: string; expires: string; expired: boolean; districts: string[]; geocode_method: string; river?: string; water_level_m?: number; danger_level_m?: number }

// OpenFreeMap: free, keyless vector tiles from OSM. For official deployments in India use a
// Survey of India / Bhuvan basemap so international boundaries follow the Government of India.
maplibregl.setWorkerUrl(workerUrl)

const STYLE = (dark: boolean) => `https://tiles.openfreemap.org/styles/${dark ? 'dark' : 'positron'}`
const OFFLINE: StyleSpecification = { version: 8, sources: {}, layers: [{ id: 'bg', type: 'background', paint: { 'background-color': colours().surface } }] }
// How an alert's area text was placed on the map, in words an operator reads at a glance.
const GEOCODE: Record<string, string> = {
  cap_geocode_lgd: 'Mapped by LGD code', cap_polygon: 'Mapped by polygon', cap_circle: 'Mapped by circle', district_name: 'Mapped by district name',
  subdistrict_name: 'Mapped by sub-district name', area_text: 'Mapped from area text', gauge_station: 'Mapped by river gauge', unresolved: 'Not mapped', none: 'Not mapped',
}
const SEV_COLOUR = () => ['match', ['get', 'severity'], 'Extreme', severityColours().Extreme, 'Severe', severityColours().Severe, 'Moderate', severityColours().Moderate, severityColours().other] as unknown as maplibregl.ExpressionSpecification

export default function MapView(shared: Shared) {
  const el = useRef<HTMLDivElement>(null)
  const map = useRef<maplibregl.Map | null>(null)
  const [hazards, setHazards] = useState<HazardProps[]>([])
  const [sel, setSel] = useState<string | null>(null)
  const [impact, setImpact] = useState<Impact | null>(null)
  const [layers, setLayers] = useState({ districts: true, hazards: true, hospitals: false })
  const [offline, setOffline] = useState(false)
  const [hospitalCount, setHospitalCount] = useState(0)
  const dark = currentTheme() === 'dark'
  const coords = useRef(new Map<string, [number, number]>())
  // data loads independently of the WebGL map, so the alert list works even where the map cannot render
  const data = useRef<Promise<[FeatureCollection, FeatureCollection]> | null>(null)
  if (!data.current) data.current = Promise.all([api.districts(), api.hazards()])

  useEffect(() => {
    data.current!.then(([, hz]) => {
      for (const f of hz.features) if (f.geometry?.type === 'Point') coords.current.set(String(f.properties?.id), f.geometry.coordinates as [number, number])
      setHazards(hz.features.map((f) => f.properties as HazardProps))
    }).catch((e) => shared.setError(e.message))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (!el.current) return
    let cancelled = false
    const start = (style: string | StyleSpecification) => {
      const m = new maplibregl.Map({ container: el.current!, style, center: [78.9, 21.5], zoom: 4.2, attributionControl: { compact: true } })
      m.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right')
      m.addControl(new maplibregl.ScaleControl(), 'bottom-right')
      // the hosted dark style names a POI sprite it does not ship; a blank stand-in keeps the console clean
      m.on('styleimagemissing', (e) => { if (!m.hasImage(e.id)) m.addImage(e.id, { width: 1, height: 1, data: new Uint8Array(4) }) })
      map.current = m
      m.on('load', async () => {
        const [districts, hz] = await data.current!
        if (cancelled) return
        m.addSource('districts', { type: 'geojson', data: districts, promoteId: 'lgd_code' })
        m.addLayer({ id: 'district-fill', type: 'fill', source: 'districts', paint: { 'fill-color': ['case', ['boolean', ['feature-state', 'hit'], false], colours().tape, colours().inkSoft], 'fill-opacity': ['case', ['boolean', ['feature-state', 'hit'], false], 0.35, 0.06] } })
        m.addLayer({ id: 'district-line', type: 'line', source: 'districts', paint: { 'line-color': colours().inkSoft, 'line-width': 0.8, 'line-opacity': 0.6 } })
        m.addSource('hospitals', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } })
        m.addLayer({ id: 'hospitals', type: 'circle', source: 'hospitals', layout: { visibility: 'none' }, paint: { 'circle-radius': 2.6, 'circle-color': colours().approve, 'circle-opacity': 0.8 } })
        m.addSource('hazards', { type: 'geojson', data: { ...hz, features: hz.features.filter((f) => f.geometry) } })
        m.addLayer({ id: 'hazard-halo', type: 'circle', source: 'hazards', paint: { 'circle-radius': 14, 'circle-color': SEV_COLOUR(), 'circle-opacity': 0.18 } })
        m.addLayer({ id: 'hazards', type: 'circle', source: 'hazards', paint: { 'circle-radius': 6, 'circle-color': SEV_COLOUR(), 'circle-stroke-width': 1.5, 'circle-stroke-color': colours().surface } })
        m.on('click', 'hazards', (e) => {
          const id = e.features?.[0]?.properties?.id
          if (id) setSel(String(id))
        })
        m.on('click', 'hospitals', (e) => {
          const p = e.features?.[0]?.properties
          if (p) new maplibregl.Popup().setLngLat(e.lngLat).setHTML(`<b>${p.name}</b><br/>hospital · OSM`).addTo(m)
        })
        for (const l of ['hazards', 'hospitals']) {
          m.on('mouseenter', l, () => (m.getCanvas().style.cursor = 'pointer'))
          m.on('mouseleave', l, () => (m.getCanvas().style.cursor = ''))
        }
      })
    }
    // fall back to a blank canvas when the basemap is unreachable (edge kit / offline)
    fetch(STYLE(dark), { method: 'HEAD' })
      .then((r) => (r.ok ? start(STYLE(dark)) : Promise.reject()))
      .catch(() => {
        setOffline(true)
        start(OFFLINE)
      })
    return () => {
      cancelled = true
      map.current?.remove()
      map.current = null
    }
  }, [dark])

  useEffect(() => {
    const m = map.current
    if (!m || !m.isStyleLoaded()) return
    m.setLayoutProperty('district-fill', 'visibility', layers.districts ? 'visible' : 'none')
    m.setLayoutProperty('district-line', 'visibility', layers.districts ? 'visible' : 'none')
    for (const l of ['hazards', 'hazard-halo']) m.setLayoutProperty(l, 'visibility', layers.hazards ? 'visible' : 'none')
    m.setLayoutProperty('hospitals', 'visibility', layers.hospitals ? 'visible' : 'none')
    if (layers.hospitals && hospitalCount === 0) {
      api.assets().then((fc) => {
        ;(m.getSource('hospitals') as GeoJSONSource).setData(fc)
        setHospitalCount(fc.features.length)
      })
    }
  }, [layers, hospitalCount])

  useEffect(() => {
    const m = map.current
    setImpact(null)
    if (!sel) return
    api.impact(sel).then((r) => {
      setImpact(r)
      if (!m || !m.getSource('districts')) return
      m.removeFeatureState({ source: 'districts' })
      for (const d of r.districts) m.setFeatureState({ source: 'districts', id: d.lgd_code }, { hit: true })
      const c = coords.current.get(sel)
      if (c) m.flyTo({ center: c, zoom: 6.2 })
    })
  }, [sel, shared.tick])

  const sorted = useMemo(() => {
    const rank: Record<string, number> = { Extreme: 0, Severe: 1, Moderate: 2, Minor: 3, Unknown: 4 }
    return [...hazards].sort((a, b) => (rank[a.severity] ?? 5) - (rank[b.severity] ?? 5))
  }, [hazards])

  const resolved = hazards.filter((h) => h.districts.length).length

  return (
    <div className="workspace">
      <aside className="panel">
        <div className="section">
          <h3>Layers</h3>
          <Checkbox checked={layers.districts} label="District boundaries (Maharashtra, LGD)" onChange={() => setLayers({ ...layers, districts: !layers.districts })} />
          <Checkbox checked={layers.hazards} label="SACHET CAP alerts" onChange={() => setLayers({ ...layers, hazards: !layers.hazards })} />
          <Checkbox checked={layers.hospitals} label={`Hospitals (OSM)${hospitalCount ? ` · ${hospitalCount}` : ''}`} onChange={() => setLayers({ ...layers, hospitals: !layers.hospitals })} />
          {offline && <div className="notice small">Basemap unreachable: showing Mosaic layers only (offline mode).</div>}
        </div>
        <div className="section">
          <h3>Alerts <span className="count">{hazards.length} · {resolved} mapped</span></h3>
        </div>
        <ul className="list">
          {sorted.map((h) => (
            <li key={h.id} className={sel === h.id ? 'sel' : ''}>
              <button className="row-button" aria-current={sel === h.id ? 'true' : undefined} onClick={() => setSel(h.id)}>
                <span className="t" style={{ display: 'block' }}><span className={`sev-dot sev-${h.severity}`} aria-label={h.severity} />{h.event} <span className="muted small">· {h.sender}</span></span>
                <span className="s" style={{ display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>{h.headline}</span>
                <span className="row small" style={{ marginTop: 6 }}>
                  <span className={`chip ${h.districts.length ? '' : 'muted'}`} title={`Located by ${h.geocode_method.replaceAll('_', ' ')}`}>{GEOCODE[h.geocode_method] ?? h.geocode_method.replaceAll('_', ' ')}</span>
                  {h.expired && <span className="chip muted">Expired</span>}
                  {h.river && <span className={`chip ${h.water_level_m! >= h.danger_level_m! ? 'ev-suggested' : 'ev-single'}`}>{h.river}: {h.water_level_m} of {h.danger_level_m} m</span>}
                </span>
              </button>
            </li>
          ))}
        </ul>
      </aside>

      <main className="canvas">
        <div ref={el} className="map" />
      </main>

      <aside className="panel right">
        {impact ? <ImpactPanel impact={impact} hazardId={sel!} shared={shared} /> : <div className="panel-empty"><h3>No alert selected</h3><p>Select an alert to see the districts and hospitals it affects.</p></div>}
      </aside>
    </div>
  )
}

function ImpactPanel({ impact, hazardId, shared }: { impact: Impact; hazardId: string; shared: Shared }) {
  const h = impact.hazard as Record<string, string | number | boolean | undefined>
  const [res, setRes] = useState('Relief kits')
  const [qty, setQty] = useState(100)
  const [unit, setUnit] = useState(impact.districts[0]?.lgd_code ?? '')
  const [msg, setMsg] = useState('')
  const canDispatch = shared.me?.roles.some((r) => r === 'operator' || r === 'collector')

  const dispatch = () =>
    api
      .action('dispatch_resource', { resource: res, quantity: qty, admin_unit: unit, hazard_id: hazardId })
      .then(() => {
        setMsg('Dispatch recorded.')
        shared.refresh()
      })
      .catch((e) => setMsg(e.message))

  return (
    <div>
      <div className="section">
        <div className={`small sev-${h.severity}`} style={{ fontWeight: 600 }}><span className="sev-dot" />{String(h.severity)} · {String(h.event)}</div>
        <h2 style={{ margin: '6px 0 8px', fontSize: 16 }}>{String(h.headline)}</h2>
        {h.headline_original && <p className="muted small" lang="und">Original ({String(h.original_language)}): {String(h.headline_original)}</p>}
        <dl className="kv">
          <dt>Sender</dt><dd>{String(h.sender)}</dd>
          <dt>Effective</dt><dd>{shortDate(String(h.effective ?? ''))}</dd>
          <dt>Expires</dt><dd>{shortDate(String(h.expires ?? ''))}</dd>
          <dt>Geocoded by</dt><dd>{String(h.geocode_method).replaceAll('_', ' ')}</dd>
          <dt>Area text</dt><dd>{String(h.area_desc)}</dd>
          {h.river && (<><dt>Gauge</dt><dd>{String(h.river)} at {String(h.gauge_station)}: {String(h.water_level_m)} m (warning {String(h.warning_level_m)}, danger {String(h.danger_level_m)})</dd></>)}
        </dl>
        <div className="row" style={{ marginTop: 6 }}><span className="chip src">NDMA-SACHET</span><span className="chip">CAP {String(h.cap_identifier)}</span></div>
      </div>
      <div className="section">
        <h3>Affected districts <span className="count">{impact.districts.length}</span></h3>
        {impact.districts.length === 0 && <div className="notice small">Area could not be mapped to LGD codes. Logged as a data-quality issue for the issuing agency.</div>}
        <div className="row">{impact.districts.map((d) => <span key={d.lgd_code} className="chip">{d.name}</span>)}</div>
      </div>
      <div className="section">
        <h3>Hospitals in the area <span className="count">{impact.hospitals_in_area}</span></h3>
        {impact.hospitals_in_area === 0 && <div className="muted small">Hospital layer covers Maharashtra in this pilot.</div>}
        <ul className="list" style={{ maxHeight: 180, overflow: 'auto' }}>
          {impact.hospitals.slice(0, 50).map((x) => <li key={x.id} className="static"><div className="s">{x.name}</div></li>)}
        </ul>
      </div>
      {canDispatch && impact.districts.length > 0 && (
        <div className="section stack">
          <h3>Dispatch resource</h3>
          <InputGroup small aria-label="Resource" value={res} onChange={(e) => setRes(e.target.value)} />
          <div className="row">
            <NumericInput small aria-label="Quantity" value={qty} min={1} onValueChange={(v) => setQty(v)} style={{ width: 90 }} />
            <HTMLSelect value={unit} onChange={(e) => setUnit(e.target.value)} aria-label="District">
              {impact.districts.map((d) => <option key={d.lgd_code} value={d.lgd_code}>{d.name}</option>)}
            </HTMLSelect>
            <Button small intent="primary" onClick={dispatch}>Dispatch</Button>
          </div>
          {msg && <div className="small">{msg}</div>}
        </div>
      )}
      {impact.dispatches.length > 0 && (
        <div className="section">
          <h3>Dispatch log</h3>
          {impact.dispatches.map((d) => <div key={d.id} className="small">{shortDate(d.dispatched_at)} · {d.quantity} × {d.resource} to LGD {d.admin_unit} <span className="muted">({d.dispatched_by})</span></div>)}
        </div>
      )}
    </div>
  )
}

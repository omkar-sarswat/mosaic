import { Icon } from '@blueprintjs/core'
import { Select, Slider, TextInput, Textarea } from '@mantine/core'
import type { Feature, FeatureCollection } from 'geojson'
import type { GeoJSONSource, Map as MapLibre } from 'maplibre-gl'
import { useEffect, useMemo, useRef, useState } from 'react'
import { area, monitor, type AreaItem, type AreaResult, type AreaSite } from '../api'
import { colours, typeColour } from '../lib/palette'
import type { Nav } from '../views/nav'
import { Button } from './Button'
import { diaryTime } from './Diary'
import { MarkingChip } from './Marking'
import { WatchDialog } from './WatchButton'

export type AreaPick = { group: 'vehicles' | 'phones' | 'travellers'; item: AreaItem } | null
type Centre = { lat: number; lon: number; label: string }

const GROUPS: { key: 'vehicles' | 'phones' | 'travellers'; title: string; how: string }[] = [
  { key: 'vehicles', title: 'Vehicles', how: 'Read at a toll plaza or ANPR camera inside the area' },
  { key: 'phones', title: 'Phones', how: 'Made a call through a tower inside the area' },
  { key: 'travellers', title: 'Travellers', how: 'Booked a journey from or to the area' },
]
const SITE_LABEL: Record<AreaSite['kind'], string> = { toll: 'Toll plaza', anpr: 'ANPR camera', tower: 'Phone tower' }
const isoDay = (d: Date) => d.toISOString().slice(0, 10)

/** A circle of `km` around a point, as a polygon the map can draw. */
function circle(lat: number, lon: number, km: number, steps = 72): Feature {
  const R = 6371
  const d = km / R
  const la = (lat * Math.PI) / 180
  const lo = (lon * Math.PI) / 180
  const ring: [number, number][] = []
  for (let i = 0; i <= steps; i++) {
    const b = (2 * Math.PI * i) / steps
    const la2 = Math.asin(Math.sin(la) * Math.cos(d) + Math.cos(la) * Math.sin(d) * Math.cos(b))
    const lo2 = lo + Math.atan2(Math.sin(b) * Math.sin(d) * Math.cos(la), Math.cos(d) - Math.sin(la) * Math.sin(la2))
    ring.push([(lo2 * 180) / Math.PI, (la2 * 180) / Math.PI])
  }
  return { type: 'Feature', properties: {}, geometry: { type: 'Polygon', coordinates: [ring] } }
}

const fc = (features: Feature[]): FeatureCollection => ({ type: 'FeatureCollection', features })

/** Who and what was inside a circle on the map during a window: the question, its reason, and the answer. */
export function AreaSearch({ map, ready, nav, picked, onPick, initial }: {
  map: MapLibre | null; ready: boolean; nav: Nav; picked: AreaPick; onPick: (p: AreaPick) => void; initial?: Centre & { radius: number }
}) {
  const [sites, setSites] = useState<AreaSite[]>([])
  const [maxRadius, setMaxRadius] = useState(10)
  const [centre, setCentre] = useState<Centre | null>(initial ? { lat: initial.lat, lon: initial.lon, label: initial.label } : null)
  const [radius, setRadius] = useState(initial?.radius ?? 2)
  const [start, setStart] = useState(() => isoDay(new Date(Date.now() - 90 * 864e5)))
  const [end, setEnd] = useState(() => isoDay(new Date()))
  const [reason, setReason] = useState('')
  const [picking, setPicking] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [result, setResult] = useState<AreaResult | null>(null)
  const [watching, setWatching] = useState(false)
  const pickingRef = useRef(false)
  pickingRef.current = picking

  useEffect(() => {
    area.sites().then((r) => { setSites(r.sites); setMaxRadius(r.max_radius_km) }).catch(() => setSites([]))
  }, [])

  // the map layers this panel owns: the circle, the centre, the reads inside it
  useEffect(() => {
    if (!map || !ready) return
    if (!map.getSource('area-circle')) {
      const c = colours()
      for (const id of ['area-circle', 'area-points', 'area-centre']) map.addSource(id, { type: 'geojson', data: fc([]) })
      map.addLayer({ id: 'area-fill', type: 'fill', source: 'area-circle', paint: { 'fill-color': c.ink, 'fill-opacity': 0.06 } })
      map.addLayer({ id: 'area-line', type: 'line', source: 'area-circle', paint: { 'line-color': c.ink, 'line-width': 1.5, 'line-dasharray': [3, 2] } })
      map.addLayer({ id: 'area-points', type: 'circle', source: 'area-points', paint: {
        'circle-radius': ['case', ['get', 'on'], 8, 5], 'circle-color': ['get', 'colour'], 'circle-stroke-color': c.surface, 'circle-stroke-width': 1.5 } })
      map.addLayer({ id: 'area-centre', type: 'circle', source: 'area-centre', paint: { 'circle-radius': 4, 'circle-color': c.tape, 'circle-stroke-color': c.surface, 'circle-stroke-width': 2 } })
    }
    const onClick = (e: { lngLat: { lat: number; lng: number } }) => {
      if (!pickingRef.current) return
      setCentre({ lat: +e.lngLat.lat.toFixed(5), lon: +e.lngLat.lng.toFixed(5), label: 'Point chosen on the map' })
      setPicking(false)
    }
    map.on('click', onClick)
    return () => { map.off('click', onClick) }
  }, [map, ready])

  useEffect(() => {
    if (!map || !ready) return
    map.getCanvas().style.cursor = picking ? 'crosshair' : ''
  }, [map, ready, picking])

  useEffect(() => {
    if (!map || !ready || !map.getSource('area-circle')) return
    ;(map.getSource('area-circle') as GeoJSONSource).setData(fc(centre ? [circle(centre.lat, centre.lon, radius)] : []))
    ;(map.getSource('area-centre') as GeoJSONSource).setData(fc(centre ? [{ type: 'Feature', properties: {}, geometry: { type: 'Point', coordinates: [centre.lon, centre.lat] } }] : []))
  }, [map, ready, centre, radius])

  useEffect(() => {
    if (!map || !ready || !map.getSource('area-points')) return
    const points: Feature[] = []
    for (const g of GROUPS) {
      for (const item of result?.[g.key] ?? []) {
        const on = picked?.item.record.id === item.record.id
        for (const r of item.reads) points.push({ type: 'Feature', properties: { id: item.record.id, group: g.key, on, colour: typeColour(item.record.type) },
          geometry: { type: 'Point', coordinates: [r.lon, r.lat] } })
      }
    }
    ;(map.getSource('area-points') as GeoJSONSource).setData(fc(points))
  }, [map, ready, result, picked])

  useEffect(() => {
    if (!map || !centre) return
    map.flyTo({ center: [centre.lon, centre.lat], zoom: Math.max(8, 13.2 - Math.log2(Math.max(0.5, radius))), duration: 900 })
  }, [map, centre, radius])

  const siteOptions = useMemo(() => (['toll', 'anpr', 'tower'] as const).map((k) => ({
    group: SITE_LABEL[k] + 's', items: sites.filter((s) => s.kind === k).map((s) => ({ value: `${s.lat},${s.lon},${s.label}`, label: s.city && !s.label.includes(s.city) ? `${s.label} · ${s.city}` : s.label })),
  })).filter((g) => g.items.length), [sites])

  const ok = !!centre && reason.trim().length >= 10 && !!start && !!end && start <= end
  const run = () => {
    if (!ok || !centre) return
    setBusy(true)
    setErr('')
    onPick(null)
    area.search({ lat: centre.lat, lon: centre.lon, radius_km: radius, start, end, reason: reason.trim(), label: centre.label })
      .then(setResult).catch((e) => setErr(e.message)).finally(() => setBusy(false))
  }
  const total = result ? result.vehicles.length + result.phones.length + result.travellers.length : 0

  return (
    <>
      <div className="section area-form">
        <h3>Search an area</h3>
        <p className="muted small">Who and what was inside a circle during a period, from toll and ANPR reads, call records and travel bookings. The search and its reason are recorded with the case.</p>
        <div className="area-centre">
          <span className="area-label">Centre</span>
          {centre ? <span>{centre.label}<small>{centre.lat.toFixed(4)}, {centre.lon.toFixed(4)}</small></span> : <span className="muted">Not chosen</span>}
        </div>
        <div className="row">
          <Button small icon="locate" active={picking} onClick={() => setPicking(!picking)}>{picking ? 'Click the map…' : 'Pick on map'}</Button>
        </div>
        <Select size="xs" placeholder="Or search a toll plaza, camera or tower" data={siteOptions} searchable clearable limit={60} nothingFoundMessage="No place by that name" aria-label="Choose a place"
          value={centre && centre.label !== 'Point chosen on the map' ? `${centre.lat},${centre.lon},${centre.label}` : null}
          onChange={(v) => { if (v) { const [la, lo, ...rest] = v.split(','); setCentre({ lat: +la, lon: +lo, label: rest.join(',') }) } }} />
        <div className="area-field">
          <span className="area-label">Radius<b>{radius} km</b></span>
          <Slider min={0.5} max={maxRadius} step={0.5} value={radius} onChange={setRadius} label={null} aria-label="Radius in kilometres" />
        </div>
        <div className="area-dates">
          <TextInput size="xs" type="date" label="From" value={start} max={end} onChange={(e) => setStart(e.target.value)} />
          <TextInput size="xs" type="date" label="To" value={end} min={start} onChange={(e) => setEnd(e.target.value)} />
        </div>
        <Textarea size="xs" label="Reason" description="At least 10 characters; kept in the audit trail." minRows={2} autosize value={reason} onChange={(e) => setReason(e.target.value)}
          placeholder="For example: robbery at the Hadapsar estate on 14 Aug; who was near" />
        {err && <p className="err" role="alert">{err}</p>}
        <Button intent="primary" icon="search" loading={busy} disabled={!ok} onClick={run} fill>Search this area</Button>
      </div>
      {result && (
        <div className="section area-results">
          <div className="area-summary">
            <div><h3>{total ? `${total} found` : 'Nothing found'}</h3><span className="area-window">{result.radius_km} km around {result.label}, {result.window[0]} to {result.window[1].slice(0, 10)}</span></div>
            <Button small icon="notifications" onClick={() => setWatching(true)}>Watch this area</Button>
          </div>
          {!!result.flagged && <p className="area-key"><b>{result.flagged}</b> {result.flagged === 1 ? 'is a person' : 'are people'} on record (a subject of this case or accused in an FIR), listed first in each group.</p>}
          {result.withheld.length > 0 && <p className="watch-withheld"><Icon icon="lock" size={12} />{result.withheld.map((w) => `${w.count} not shown: ${w.reason}`).join(' · ')}</p>}
          {result.unlisted_numbers > 0 && <p className="watch-withheld">{result.unlisted_numbers} number{result.unlisted_numbers === 1 ? '' : 's'} used here are not on record and are not listed.</p>}
          {GROUPS.map((g) => result[g.key].length > 0 && (
            <div key={g.key} className="area-group">
              <h4>{g.title}<span className="count">{result[g.key].length}</span></h4>
              <p className="muted small">{g.how}</p>
              <ul className="area-items">
                {result[g.key].map((item) => (
                  <li key={item.record.id}>
                    <button className={`${picked?.item.record.id === item.record.id ? 'on' : ''} ${item.flag ? 'flagged' : ''}`} aria-current={picked?.item.record.id === item.record.id ? 'true' : undefined}
                      onClick={() => onPick({ group: g.key, item })}>
                      <span className="area-item-title">{item.record.title}{item.flag && <span className="area-flag">{item.flag}</span>}{item.owner && <small>{item.owner.label}</small>}</span>
                      <span className="area-item-meta">{item.count} read{item.count === 1 ? '' : 's'} · {diaryTime(item.last).day}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ))}
          {result.residents.length > 0 && (
            <details className="area-group">
              <summary>Recorded addresses inside the area<span className="count">{result.residents.length}</span></summary>
              <p className="muted small">Where people were registered as living. This does not place them there in the period.</p>
              <ul className="area-items">
                {result.residents.slice(0, 40).map((r) => (
                  <li key={`${r.record.id}:${r.address}`}><button className={r.flag ? 'flagged' : ''} onClick={() => nav.openEntity(r.record.id)}>
                    <span className="area-item-title">{r.record.title}{r.flag && <span className="area-flag">{r.flag}</span>}<small>{r.address}</small></span><span className="area-item-meta">{r.km} km</span>
                  </button></li>
                ))}
              </ul>
            </details>
          )}
          {result.sites.length > 0 && (
            <details className="area-sites">
              <summary>Inside the area: {(['tower', 'anpr', 'toll'] as const).map((k) => [k, result.sites.filter((x) => x.kind === k).length] as const).filter(([, n]) => n)
                .map(([k, n]) => `${n} ${SITE_LABEL[k].toLowerCase()}${n === 1 ? '' : 's'}`).join(', ')}</summary>
              <ul>{result.sites.slice(0, 80).map((x) => <li key={`${x.kind}:${x.label}:${x.lat}:${x.lon}`}>{SITE_LABEL[x.kind]}: {x.label}{x.km !== undefined ? ` · ${x.km} km` : ''}</li>)}</ul>
            </details>
          )}
          {!total && !result.sites.length && <p className="muted small">No toll plaza, camera or phone tower on record lies inside this circle, so nobody can be placed there. Widen the radius or move the centre.</p>}
          <WatchDialog opened={watching} onClose={() => setWatching(false)} title={`Watch ${result.radius_km} km around ${result.label}`} initial={result.reason}
            onConfirm={(why, days) => monitor.watchArea({ lat: result.centre.lat, lon: result.centre.lon, radius_km: result.radius_km, label: result.label, reason: why, lookback_days: days })
              .then(() => nav.setError('Area watch started. New presence inside it will reach the work queue.'))} />
        </div>
      )}
    </>
  )
}

/** The reads that place one vehicle, phone or traveller inside the searched area. */
export function AreaItemPanel({ pick, nav }: { pick: NonNullable<AreaPick>; nav: Nav }) {
  const { item, group } = pick
  return (
    <div className="section area-item-panel">
      <div className="row" style={{ justifyContent: 'space-between' }}><span className="watch-kicker">{GROUPS.find((g) => g.key === group)?.title.replace(/s$/, '')}</span><MarkingChip level={item.record.sensitivity} /></div>
      <h2>{item.record.title}</h2>
      {item.flag && <p className="area-key"><b>{item.flag}</b></p>}
      {item.owner && <p className="small">Registered to <button className="elink" onClick={() => nav.openEntity(item.owner!.id)}>{item.owner.label}</button></p>}
      <p className="muted small">{item.count} read{item.count === 1 ? '' : 's'} between {diaryTime(item.first).day} and {diaryTime(item.last).day}{item.places?.length ? ` at ${item.places.join(', ')}` : ''}.</p>
      <div className="row" style={{ margin: '10px 0 14px' }}>
        <Button small icon="person" onClick={() => nav.openEntity(item.record.id)}>Dossier</Button>
        {item.owner && <Button small icon="graph" onClick={() => nav.openGraph(item.owner!.id)}>Network</Button>}
      </div>
      <ul className="area-reads">
        {item.reads.map((r) => {
          const t = diaryTime(r.at)
          return (
            <li key={r.record}>
              <time dateTime={r.at}>{t.day}<small>{t.time}</small></time>
              <span>{r.detail ?? r.place}<small>{r.kind === 'anpr' ? 'Camera read' : r.kind === 'toll' ? 'FASTag toll read' : r.kind === 'voice' || r.kind === 'sms' ? (r.kind === 'sms' ? 'Message' : 'Call') : r.kind} · {r.source_name}</small></span>
            </li>
          )
        })}
      </ul>
      {item.count > item.reads.length && <p className="muted small">Showing the latest {item.reads.length} of {item.count}.</p>}
    </div>
  )
}

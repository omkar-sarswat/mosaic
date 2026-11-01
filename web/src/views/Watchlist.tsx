import { Icon, NonIdealState, Spinner } from '@blueprintjs/core'
import { Table } from '@mantine/core'
import { useEffect, useMemo, useState } from 'react'
import { monitor, type Activity, type ActivityEvent, type SavedSearch, type Watch, type Withheld } from '../api'
import { Button } from '../components/Button'
import { diaryTime, Mark } from '../components/Diary'
import { MarkingChip } from '../components/Marking'
import { Emph, PRIORITY_LABEL, Why, type Priority } from '../components/Emph'
import { ReasonDialog } from '../components/ReasonDialog'
import { day, sentence } from '../lib/format'
import type { Nav } from './nav'

type Picked = { kind: 'watch' | 'search'; id: string } | null
type SearchDetail = Awaited<ReturnType<typeof monitor.search>>

const KIND_LABEL: Record<ActivityEvent['kind'], string> = {
  sighting: 'Sightings', call: 'Calls', money: 'Money', travel: 'Travel', alert: 'Alerts', fir: 'FIRs', record: 'New facts', lead: 'Leads',
}
const KIND_ICON: Record<ActivityEvent['kind'], 'drive-time' | 'phone' | 'bank-account' | 'airplane' | 'flag' | 'document' | 'database' | 'search-around'> = {
  sighting: 'drive-time', call: 'phone', money: 'bank-account', travel: 'airplane', alert: 'flag', fir: 'document', record: 'database', lead: 'search-around',
}

export default function Watchlist({ nav }: { nav: Nav }) {
  const [data, setData] = useState<Awaited<ReturnType<typeof monitor.list>> | null>(null)
  const [err, setErr] = useState('')
  const [picked, setPicked] = useState<Picked>(null)
  const [reload, setReload] = useState(0)

  useEffect(() => {
    if (!nav.caseId) return
    setErr('')
    monitor.list().then((d) => {
      setData(d)
      setPicked((p) => {
        if (nav.focus && !p) return { kind: nav.focus.startsWith('search:') ? 'search' : 'watch', id: nav.focus }
        if (p) return p
        const first = d.watches.find((w) => w.status === 'active') ?? d.watches[0]
        const firstSearch = d.searches.find((s) => s.status === 'active')
        return first ? { kind: 'watch', id: first.id } : firstSearch ? { kind: 'search', id: firstSearch.id } : null
      })
    }).catch((e) => setErr(e.message))
  }, [nav.caseId, nav.tick, nav.focus, reload])

  if (!nav.caseId) return <NonIdealState icon="folder-open" title="No case selected" description="Watches and saved searches belong to a case. Choose one in the case bar above." />
  if (err) return <NonIdealState icon="lock" title="Watchlist not available" description={err} />
  if (!data) return <div className="app-loading" role="status"><Spinner size={22} /><p>Loading the watchlist…</p></div>

  const records = data.watches.filter((w) => w.kind === 'object' && w.status === 'active')
  const areas = data.watches.filter((w) => w.kind === 'area' && w.status === 'active')
  const searches = data.searches.filter((s) => s.status === 'active')
  const ended = [...data.watches.filter((w) => w.status !== 'active'), ...data.searches.filter((s) => s.status !== 'active')]
  const empty = !data.watches.length && !data.searches.length
  const refresh = () => setReload((n) => n + 1)

  return (
    <div className="watch-layout">
      <aside className="panel watch-index" aria-label="Followed in this case">
        <WatchGroup title="People and records" items={records} picked={picked} onPick={(id) => setPicked({ kind: 'watch', id })}
          empty="Open a dossier and choose Watch to follow a person, phone, vehicle or account." />
        <WatchGroup title="Places" items={areas} picked={picked} onPick={(id) => setPicked({ kind: 'watch', id })}
          empty="On the map, search an area and choose Watch this area to be told of new presence there." />
        <section className="section">
          <h3>Saved searches<span className="count">{searches.length}</span></h3>
          {searches.length ? (
            <ul className="watch-items">
              {searches.map((s) => (
                <li key={s.id}>
                  <button className={picked?.id === s.id ? 'on' : ''} aria-current={picked?.id === s.id ? 'true' : undefined} onClick={() => setPicked({ kind: 'search', id: s.id })}>
                    <span className="watch-name"><Icon icon="search" size={13} />{s.title}</span>
                    <span className="watch-meta">{s.new ? <b>{s.new} new</b> : 'No new results'}<span>{s.total ?? 0} visible</span></span>
                  </button>
                </li>
              ))}
            </ul>
          ) : <p className="watch-empty">In Explorer, run a search and choose Save search to have it asked again for you.</p>}
        </section>
        {ended.length > 0 && (
          <details className="section watch-ended">
            <summary>Ended<span className="count">{ended.length}</span></summary>
            <ul className="watch-items">
              {ended.map((x) => (
                <li key={x.id}>
                  <button className={picked?.id === x.id ? 'on' : ''} onClick={() => setPicked({ kind: x.id.startsWith('search:') ? 'search' : 'watch', id: x.id })}>
                    <span className="watch-name">{'label' in x ? x.label : x.title}</span>
                    <span className="watch-meta">Ended{(x as Watch).ended_at ? ` ${day((x as Watch).ended_at!)}` : ''}</span>
                  </button>
                </li>
              ))}
            </ul>
          </details>
        )}
      </aside>
      <main className="watch-main">
        {empty && (
          <div className="panel-empty watch-start">
            <h3>Nothing is followed in this case yet</h3>
            <p>A watch tells the case team when a new record touches a person, number, vehicle, account or place. A saved search is asked again each time the work queue loads, and new results land there.</p>
            <div className="row"><Button icon="person" onClick={() => nav.go('dossier')}>Open a dossier</Button><Button icon="search-template" onClick={() => nav.go('explore')}>Search records</Button><Button icon="globe" onClick={() => nav.go('globe')}>Search an area</Button></div>
          </div>
        )}
        {picked?.kind === 'watch' && <WatchDetail key={picked.id} id={picked.id} nav={nav} onChanged={refresh} />}
        {picked?.kind === 'search' && <SearchView key={picked.id} id={picked.id} nav={nav} onChanged={refresh} />}
      </main>
    </div>
  )
}

function WatchGroup({ title, items, picked, onPick, empty }: { title: string; items: Watch[]; picked: Picked; onPick: (id: string) => void; empty: string }) {
  return (
    <section className="section">
      <h3>{title}<span className="count">{items.length}</span></h3>
      {items.length ? (
        <ul className="watch-items">
          {items.map((w) => (
            <li key={w.id}>
              <button className={picked?.id === w.id ? 'on' : ''} aria-current={picked?.id === w.id ? 'true' : undefined} onClick={() => onPick(w.id)}>
                <span className="watch-name"><Icon icon={w.kind === 'area' ? 'map-marker' : 'person'} size={13} />{w.label}</span>
                <span className="watch-meta">
                  {w.unavailable ? <span>Not readable in this case</span> : w.new ? <b>{w.new_key ? `${w.new_key} to read · ` : ''}{w.new} new</b> : <span>Reviewed</span>}
                  {w.latest && <span>Latest {diaryTime(w.latest).day}</span>}
                </span>
              </button>
            </li>
          ))}
        </ul>
      ) : <p className="watch-empty">{empty}</p>}
    </section>
  )
}

function WithheldNote({ withheld }: { withheld: Withheld[] }) {
  if (!withheld.length) return null
  return <p className="watch-withheld"><Icon icon="lock" size={12} />{withheld.map((w) => `${w.count} record${w.count === 1 ? '' : 's'} not shown: ${w.reason}`).join(' · ')}</p>
}

function WatchDetail({ id, nav, onChanged }: { id: string; nav: Nav; onChanged: () => void }) {
  const [d, setD] = useState<{ watch: Watch; activity: Activity } | null>(null)
  const [err, setErr] = useState('')
  const [kind, setKind] = useState<ActivityEvent['kind'] | 'all'>('all')
  const [level, setLevel] = useState<'key' | Priority | 'all' | null>(null)
  const [ending, setEnding] = useState(false)
  const [busy, setBusy] = useState(false)
  const load = () => monitor.detail(id).then(setD).catch((e) => setErr(e.message))
  useEffect(() => { load() }, [id]) // eslint-disable-line react-hooks/exhaustive-deps

  const kinds = useMemo(() => Object.entries(d?.activity.counts ?? {}) as [ActivityEvent['kind'], number][], [d])
  if (err) return <NonIdealState icon="lock" title="Watch not available" description={err} />
  if (!d) return <div className="app-loading" role="status"><Spinner size={20} /></div>
  const { watch: w, activity: a } = d
  const pr = a.priorities ?? { high: 0, medium: 0, low: 0 }
  const keyCount = pr.high + pr.medium
  const lvl = level ?? (keyCount ? 'key' : 'all')
  const byLevel = (e: ActivityEvent) => lvl === 'all' || (lvl === 'key' ? e.priority !== 'low' : e.priority === lvl)
  const shown = a.events.filter((e) => (kind === 'all' || e.kind === kind) && byLevel(e))
  const top = a.events.filter((e) => e.priority === 'high').slice(0, 4)
  const review = () => {
    setBusy(true)
    monitor.seen(w.id).then(() => { load(); onChanged() }).catch((e) => nav.setError(e.message)).finally(() => setBusy(false))
  }

  return (
    <article className="watch-sheet">
      <header className="watch-head">
        <div>
          <div className="watch-kicker">{w.kind === 'area' ? 'Place' : 'Record'} · watched since {day(w.created_at)} by {w.created_by_name}</div>
          <h2>{w.label}</h2>
          <p className="watch-reason">{w.reason}</p>
          <p className="watch-review">{w.status !== 'active'
            ? `Ended ${w.ended_at ? day(w.ended_at) : ''} by ${w.ended_by_name ?? 'an officer'}: ${w.end_reason ?? ''}`
            : w.seen_by_name ? `Last reviewed by ${w.seen_by_name}, ${diaryTime(w.seen_at).day} ${diaryTime(w.seen_at).time}` : `Activity from ${day(w.since)} onwards, not yet reviewed`}</p>
        </div>
        {w.status === 'active' && (
          <div className="watch-actions">
            <Button intent="primary" icon="tick" loading={busy} disabled={!a.new} onClick={review}>{a.new ? `Mark ${a.new} reviewed` : 'All reviewed'}</Button>
            {w.object_id && <Button icon="person" onClick={() => nav.openEntity(w.object_id!)}>Open dossier</Button>}
            {w.area && <Button icon="globe" onClick={() => nav.open('globe', `area:${w.area!.lat},${w.area!.lon},${w.area!.radius_km},${w.area!.label}`)}>Open on map</Button>}
            <Button minimal icon="eye-off" onClick={() => setEnding(true)}>Stop watching</Button>
          </div>
        )}
      </header>
      {a.unavailable && <div className="notice">This record cannot be read under the active case: {a.unavailable}.</div>}
      {a.total > 0 && (
        <section className="watch-brief" aria-label="What to read first">
          <div className="brief-counts" role="group" aria-label="Show by importance">
            <button className="bc-high" aria-pressed={lvl === 'high'} onClick={() => setLevel(lvl === 'high' ? 'key' : 'high')}><b>{pr.high}</b><span>{PRIORITY_LABEL.high}</span></button>
            <button className="bc-medium" aria-pressed={lvl === 'medium'} onClick={() => setLevel(lvl === 'medium' ? 'key' : 'medium')}><b>{pr.medium}</b><span>{PRIORITY_LABEL.medium}</span></button>
            <button className="bc-low" aria-pressed={lvl === 'low'} onClick={() => setLevel(lvl === 'low' ? 'key' : 'low')}><b>{pr.low}</b><span>{PRIORITY_LABEL.low}</span></button>
            <button className="bc-all" aria-pressed={lvl === 'all'} onClick={() => setLevel(lvl === 'all' ? 'key' : 'all')}><b>{a.total}</b><span>Everything</span></button>
          </div>
          {top.length > 0 && (
            <ul className="brief-top">
              {top.map((e, i) => (
                <li key={`${e.record}:${i}`}>
                  <time dateTime={e.at}>{diaryTime(e.at).day}</time>
                  <span><Why priority="high" why={e.why} /> <Emph text={e.title} terms={e.emph} /></span>
                </li>
              ))}
            </ul>
          )}
          {!keyCount && <p className="brief-none">Nothing out of the ordinary: {a.total} routine entr{a.total === 1 ? 'y' : 'ies'}.</p>}
        </section>
      )}
      {kinds.length > 0 && (
        <div className="register-filters" role="group" aria-label="Kinds of activity">
          <button aria-pressed={kind === 'all'} onClick={() => setKind('all')}>All<span>{a.total}</span></button>
          {kinds.map(([k, n]) => <button key={k} aria-pressed={kind === k} onClick={() => setKind(k)}>{KIND_LABEL[k] ?? sentence(k)}<span>{n}</span></button>)}
        </div>
      )}
      <WithheldNote withheld={a.withheld} />
      {a.cut && a.cut.length > 0 && <p className="watch-withheld">Only the latest {a.cut.join(' and ')} are listed; the full record is in the dossier.</p>}
      {shown.length ? (
        <Table.ScrollContainer minWidth={640}>
          <Table className="queue-table watch-table">
            <Table.Thead><Table.Tr><Table.Th>When</Table.Th><Table.Th>What happened</Table.Th><Table.Th>Through</Table.Th><Table.Th>Source</Table.Th></Table.Tr></Table.Thead>
            <Table.Tbody>
              {shown.map((e, i) => {
                const t = diaryTime(e.at)
                return (
                  <Table.Tr key={`${e.record}:${i}`} className={`${e.new ? 'is-new' : ''} prio-${e.priority}`}>
                    <Table.Td className="queue-time"><time dateTime={e.at}>{t.day}<small>{t.time}</small></time>{e.new && <Mark kind="new" />}</Table.Td>
                    <Table.Td>
                      <div className="watch-event"><Icon icon={KIND_ICON[e.kind] ?? 'dot'} size={13} /><span><Emph text={e.title} terms={e.emph} /></span></div>
                      {e.priority !== 'low' && <div className="watch-why"><Why priority={e.priority} why={e.why} /></div>}
                      {(e.detail || e.other) && <div className="queue-detail">{e.other && e.detail.endsWith(e.other.label) ? e.detail.slice(0, -e.other.label.length) : <>{e.detail}{e.detail && e.other ? ' · ' : ''}</>}{e.other && <button className="elink" onClick={() => nav.openEntity(e.other!.id)}>{e.other.label}</button>}</div>}
                    </Table.Td>
                    <Table.Td>{e.via ? <button className="elink" onClick={() => nav.openEntity(e.via!.id)}>{e.via.label}</button> : <span className="muted">-</span>}</Table.Td>
                    <Table.Td className="watch-source">{e.source_name ?? '-'}{e.record && <small>{e.record}</small>}</Table.Td>
                  </Table.Tr>
                )
              })}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      ) : !a.unavailable && a.total > 0 ? <div className="register-empty"><h3>Nothing in this view</h3><p>Choose another importance or kind above.</p></div>
        : !a.unavailable && <div className="register-empty"><h3>No activity yet</h3><p>Nothing has touched {w.kind === 'area' ? 'this place' : 'this record'} since {day(w.since)}. New records will appear here and in the work queue.</p></div>}
      <ReasonDialog opened={ending} onClose={() => setEnding(false)} title="Stop watching" label="Why the watch is no longer needed"
        confirm="Stop watching" intent="danger" onConfirm={(reason) => monitor.end(w.id, reason).then(() => { load(); onChanged() })} />
    </article>
  )
}

function SearchView({ id, nav, onChanged }: { id: string; nav: Nav; onChanged: () => void }) {
  const [d, setD] = useState<SearchDetail | null>(null)
  const [err, setErr] = useState('')
  const [ending, setEnding] = useState(false)
  const [busy, setBusy] = useState(false)
  const load = () => monitor.search(id).then(setD).catch((e) => setErr(e.message))
  useEffect(() => { load() }, [id]) // eslint-disable-line react-hooks/exhaustive-deps
  if (err) return <NonIdealState icon="lock" title="Saved search not available" description={err} />
  if (!d) return <div className="app-loading" role="status"><Spinner size={20} /></div>
  const s: SavedSearch = d.search
  const fresh = d.results.filter((r) => r.new).length
  return (
    <article className="watch-sheet">
      <header className="watch-head">
        <div>
          <div className="watch-kicker">Saved search · since {day(s.created_at)} by {s.created_by_name}</div>
          <h2>{s.title}</h2>
          <p className="watch-reason">Searches for “{s.query}”{s.types ? ` among ${s.types.split(',').join(', ')}` : ''}. {s.reason}</p>
          <p className="watch-review">{s.checked_by_name ? `Last reviewed by ${s.checked_by_name}, ${diaryTime(s.checked_at).day} ${diaryTime(s.checked_at).time}` : ''}</p>
        </div>
        {s.status === 'active' && (
          <div className="watch-actions">
            <Button intent="primary" icon="tick" loading={busy} disabled={!fresh}
              onClick={() => { setBusy(true); monitor.searchSeen(s.id).then(() => { load(); onChanged() }).catch((e) => nav.setError(e.message)).finally(() => setBusy(false)) }}>
              {fresh ? `Mark ${fresh} reviewed` : 'All reviewed'}
            </Button>
            <Button minimal icon="eye-off" onClick={() => setEnding(true)}>Stop searching</Button>
          </div>
        )}
      </header>
      <WithheldNote withheld={d.withheld} />
      {d.results.length ? (
        <ul className="watch-results">
          {d.results.map((r) => (
            <li key={r.id}>
              <button className="row-button" onClick={() => nav.openEntity(r.id)}>
                <span className="watch-result-title">{r.title}{r.new && <Mark kind="new" />}</span>
                <span className="watch-result-meta">{sentence(r.type)}{r.district_name ? ` · ${r.district_name}` : ''}{r.props.birth_year ? ` · born ${r.props.birth_year}` : ''}</span>
              </button>
              <MarkingChip level={r.sensitivity} hidePublic />
            </li>
          ))}
        </ul>
      ) : <div className="register-empty"><h3>No visible results</h3><p>Nothing visible to this case matches yet. New matches will reach the work queue.</p></div>}
      <ReasonDialog opened={ending} onClose={() => setEnding(false)} title="Stop this saved search" label="Why the search is no longer needed"
        confirm="Stop searching" intent="danger" onConfirm={(reason) => monitor.endSearch(s.id, reason).then(() => { load(); onChanged() })} />
    </article>
  )
}

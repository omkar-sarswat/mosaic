import { HTMLSelect, InputGroup, Spinner } from '@blueprintjs/core'
import { Button } from '../components/Button'
import { useEffect, useRef, useState } from 'react'
import { Modal, TextInput, Textarea } from '@mantine/core'
import { api, monitor, type ObjSummary } from '../api'
import { isDemo } from '../auth'
import { MarkingChip } from '../components/Marking'
import ObjectPanel from './ObjectPanel'
import { type Shared, TYPE_COLOURS } from './shared'

type Facets = Awaited<ReturnType<typeof api.explore>>
const TYPES = ['', 'Person', 'Incident', 'Phone', 'BankAccount', 'Vehicle', 'Organisation', 'Asset', 'Hazard', 'AdminUnit']

export default function Explore(shared: Shared) {
  const [q, setQ] = useState('')
  const [type, setType] = useState('')
  const [results, setResults] = useState<ObjSummary[]>([])
  const [withheld, setWithheld] = useState<{ reason: string; count: number }[]>([])
  const [busy, setBusy] = useState(false)
  const [filters, setFilters] = useState<Record<string, string | undefined>>({})
  const [facets, setFacets] = useState<Facets | null>(null)
  const [facetErr, setFacetErr] = useState('')
  const [asked, setAsked] = useState<{ q: string; type: string } | null>(null)
  const [saving, setSaving] = useState(false)
  const box = useRef<HTMLInputElement>(null)
  const canSave = !!shared.caseId && !!shared.me?.roles.some((r) => ['io', 'supervisor', 'analyst'].includes(r))

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        box.current?.focus()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  useEffect(() => {
    setFacetErr('')
    api.explore(filters).then(setFacets).catch((e) => {
      setFacets(null)
      setFacetErr(e.message)
    })
  }, [filters, shared.tick])

  const run = () => {
    if (q.trim().length < 2) return
    setBusy(true)
    api
      .search(q.trim(), type || undefined)
      .then((r) => {
        setResults(r.results)
        setWithheld(r.withheld)
        setAsked({ q: q.trim(), type })
      })
      .catch((e) => shared.setError(e.message))
      .finally(() => setBusy(false))
  }

  // re-run the last search when the user or case changes, so the purpose banner's effect is visible
  useEffect(() => {
    if (q.trim().length >= 2) run()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shared.tick])

  const toggle = (k: string, v: string) => setFilters((f) => ({ ...f, [k]: f[k] === v ? undefined : v }))
  const max = (xs: { count: number }[]) => Math.max(1, ...xs.map((x) => x.count))

  return (
    <div className="workspace wide-left">
      <aside className="panel">
        <div className="section">
          <h3>Search</h3>
          <form onSubmit={(e) => { e.preventDefault(); run() }} className="stack">
            <InputGroup inputRef={box} leftIcon="search" aria-label="Search records" placeholder="Name, phone, vehicle, FIR…" value={q} onChange={(e) => setQ(e.target.value)} />
            <div className="row">
              <HTMLSelect value={type} onChange={(e) => setType(e.target.value)} aria-label="Object type">
                {TYPES.map((t) => <option key={t} value={t}>{t || 'All types'}</option>)}
              </HTMLSelect>
              <Button type="submit" intent="primary" loading={busy}>Search</Button>
            </div>
            {isDemo() && <div className="muted small">Try {['रमेश पाटील', 'Shaikh', 'Pateel', 'Sai Auto'].map((t, i) => <span key={t}>{i ? ' · ' : ''}<button type="button" className="link" onClick={() => setQ(t)}>{t}</button></span>)}</div>}
          </form>
        </div>
        {withheld.length > 0 && (
          <div className="section">
            <div className="notice">
              {withheld.map((w) => (
                <div key={w.reason}><b>{w.count}</b> result{w.count > 1 ? 's' : ''} withheld: {w.reason}</div>
              ))}
            </div>
          </div>
        )}
        {asked && canSave && !busy && (
          <div className="section save-search">
            <span>{results.length} visible result{results.length === 1 ? '' : 's'} for “{asked.q}”</span>
            <Button small icon="notifications" onClick={() => setSaving(true)}>Save search</Button>
          </div>
        )}
        {busy ? <div className="empty"><Spinner size={20} /></div> : (
          <ul className="list">
            {results.map((r) => (
              <li key={r.id} className={shared.selected === r.id ? 'sel' : ''}>
                <button className="row-button" aria-current={shared.selected === r.id ? 'true' : undefined} onClick={() => shared.setSelected(r.id)}>
                  <span className="t" style={{ display: 'block' }}><span className="type-dot" style={{ background: TYPE_COLOURS[r.type] ?? 'var(--muted)' }} />{r.title}</span>
                  <span className="s" style={{ display: 'block' }}>
                    {r.type}
                    {r.props.name_native ? ` · ${r.props.name_native}` : ''}
                    {r.district_name ? ` · ${r.district_name}` : ''}
                    {r.props.birth_year ? ` · born ${r.props.birth_year}` : ''}
                    <MarkingChip level={r.sensitivity} className="inline" hidePublic />
                  </span>
                </button>
              </li>
            ))}
            {!results.length && q && !busy && <li className="static muted">No visible results.</li>}
          </ul>
        )}
      </aside>

      <main className="canvas scroll" style={{ background: 'var(--paper)' }}>
        <div className="section" style={{ background: 'var(--sheet)' }}>
          <h3>Incidents</h3>
          {facetErr && <p className="muted">Aggregate crime figures are available to police roles.</p>}
          {facets && (
            <>
              <div className="row" style={{ marginBottom: 8 }}>
                <b style={{ fontSize: 22, fontVariantNumeric: 'tabular-nums' }}>{facets.total.toLocaleString('en-IN')}</b> <span className="muted">incidents match</span>
                {Object.entries(filters).filter(([, v]) => v).map(([k, v]) => (
                  <Button key={k} small minimal rightIcon="cross" onClick={() => toggle(k, v!)}>{k}: {k === 'district' ? facets.by_district.find((d) => d.key === v)?.label ?? v : v}</Button>
                ))}
              </div>
              <p className="muted small" style={{ margin: 0 }}>{facets.note} Select any bar to filter.</p>
            </>
          )}
        </div>
        {!facets && !facetErr && <div className="empty">Loading incident figures…</div>}
        {facets && (
          <div className="grid-cards">
            <div className="card">
              <h4>By month</h4>
              <div className="months" role="group" aria-label="Incidents by month">
                {facets.by_month.map((m) => (
                  <button key={m.key} className={filters.month === m.key ? 'on' : ''} aria-pressed={filters.month === m.key} aria-label={`${m.key}: ${m.count} incidents`} title={`${m.key}: ${m.count}`} style={{ height: `${(m.count / max(facets.by_month)) * 100}%` }} onClick={() => toggle('month', m.key)} />
                ))}
              </div>
              <div className="row small muted" style={{ justifyContent: 'space-between' }}>
                <span>{facets.by_month[0]?.key}</span><span>{facets.by_month.at(-1)?.key}</span>
              </div>
            </div>
            <Bars title="By district" items={facets.by_district.slice(0, 14).map((d) => ({ key: d.key, label: d.label, count: d.count }))} on={filters.district} onPick={(k) => toggle('district', k)} />
            <Bars title="By section of law" items={facets.by_section.map((d) => ({ key: d.key, label: d.key, count: d.count }))} on={filters.section} onPick={(k) => toggle('section', k)} />
            <Bars title="By kind" items={facets.by_kind.map((d) => ({ key: d.key, label: d.key, count: d.count }))} on={filters.kind} onPick={(k) => toggle('kind', k)} />
          </div>
        )}
      </main>

      <aside className="panel right">
        <ObjectPanel id={shared.selected} shared={shared} onSelect={shared.setSelected} />
      </aside>
      {asked && <SaveSearchDialog opened={saving} onClose={() => setSaving(false)} query={asked.q} type={asked.type}
        onSaved={() => shared.setError('Search saved. New results will reach the work queue and the watchlist.')} />}
    </div>
  )
}

/** Keep asking a search inside the case: new visible results become work items. The reason is audited. */
function SaveSearchDialog({ opened, onClose, query, type, onSaved }: { opened: boolean; onClose: () => void; query: string; type: string; onSaved: () => void }) {
  const [title, setTitle] = useState(query)
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  useEffect(() => {
    if (opened) {
      setTitle(query)
      setReason('')
      setErr('')
    }
  }, [opened, query])
  const ok = reason.trim().length >= 10 && title.trim().length > 0
  const submit = () => {
    if (!ok || busy) return
    setBusy(true)
    monitor.saveSearch({ query, types: type, title: title.trim(), reason: reason.trim() })
      .then(() => { onSaved(); onClose() })
      .catch((e) => setErr(e.message))
      .finally(() => setBusy(false))
  }
  return (
    <Modal opened={opened} onClose={onClose} title="Save this search" centered classNames={{ content: 'case-modal', header: 'case-modal-header', body: 'case-modal-body reason-modal-body' }}>
      <form onSubmit={(e) => { e.preventDefault(); submit() }}>
        <p className="muted small">The search “{query}”{type ? ` among ${type} records` : ''} is asked again whenever the case's work queue loads. Results already seen today are not reported again.</p>
        <TextInput label="Name" value={title} onChange={(e) => setTitle(e.target.value)} />
        <Textarea label="Why it should keep running" description="Recorded in the audit trail. At least 10 characters." minRows={2} autosize value={reason} onChange={(e) => setReason(e.target.value)} data-autofocus />
        {err && <p className="err" role="alert">{err}</p>}
        <div className="case-modal-actions"><Button onClick={onClose}>Cancel</Button><Button type="submit" intent="primary" loading={busy} disabled={!ok}>Save search</Button></div>
      </form>
    </Modal>
  )
}

function Bars({ title, items, on, onPick }: { title: string; items: { key: string; label: string; count: number }[]; on?: string; onPick: (k: string) => void }) {
  const max = Math.max(1, ...items.map((i) => i.count))
  return (
    <div className="card">
      <h4>{title}</h4>
      <div className="bars">
        {items.map((i) => (
          <button key={i.key} className={`bar ${on === i.key ? 'on' : ''}`} aria-pressed={on === i.key} onClick={() => onPick(i.key)} title={`${i.label}: ${i.count}`}>
            <span className="lab">{i.label}</span>
            <span className="fill" style={{ width: `${(i.count / max) * 100}%` }} />
            <span className="n">{i.count}</span>
          </button>
        ))}
      </div>
    </div>
  )
}

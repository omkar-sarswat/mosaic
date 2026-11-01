import { Callout, HTMLSelect, InputGroup, NonIdealState, Spinner, Tab, Tabs, Tag, TextArea } from '@blueprintjs/core'
import { Button } from '../components/Button'
import { Fragment, useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { intake, patterns, type IntakePattern, type IntakePreview, type IntakeProposal, type IntakeRow, type IntakeSource, type RecipeStep, type TextTag } from '../api'
import MiniGraph from '../components/MiniGraph'
import PlacesMap from '../components/PlacesMap'
import { titleCase, when } from '../lib/format'
import { familyColour, type Family } from '../lib/graph-style'
import type { Nav } from './nav'
import { theme as currentTheme } from '../lib/palette'

// Data studio: a source extract goes through detect -> clean -> map -> match -> interpret, and leaves
// as a proposal that a second officer reviews before anything reaches the ontology.

const STATUS_LABEL: Record<string, string> = { existing: 'On record', probable: 'Probable', new: 'New' }
const OP_LABEL: Record<string, string> = {
  create: 'New records', fill: 'Gaps filled', alias: 'Name spellings learned', corroborate: 'Values corroborated', conflict: 'Conflicts for review', link: 'Links', candidate: 'Resolver candidates',
}
const TAG_FAMILY: Record<string, Family> = { phone: 'comms', vehicle_reg: 'asset', account_no: 'money', ifsc: 'money', amount: 'money', pan: 'actor', name: 'actor', place: 'asset', date: 'record' }
const RECORD_WORD: Record<string, string> = { BankAccount: 'accounts', Vehicle: 'vehicles', Event: 'stays', Document: 'free text' }
const show = (v: unknown) => (v === null || v === undefined || v === '' ? '—' : typeof v === 'object' ? JSON.stringify(v) : String(v))

export default function DataStudio({ nav }: { nav: Nav }) {
  const [sources, setSources] = useState<IntakeSource[] | null>(null)
  const [src, setSrc] = useState<string>('')
  const [pv, setPv] = useState<IntakePreview | null>(null)
  const [recipe, setRecipe] = useState<RecipeStep[] | null>(null)
  const [mapping, setMapping] = useState<Record<string, string[]> | null>(null)
  const [dirty, setDirty] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [tab, setTab] = useState('profile')
  const [props, setProps] = useState<IntakeProposal[]>([])
  const [selProp, setSelProp] = useState<string | null>(nav.focus?.startsWith('intake') ? nav.focus : null)
  const [rowFilter, setRowFilter] = useState<number[] | null>(null)
  const [marks, setMarks] = useState<Record<string, 'checked' | 'dismissed'>>({})

  const loadProposals = useCallback(() => intake.proposals().then((r) => setProps(r.proposals)).catch(() => setProps([])), [])
  useEffect(() => {
    intake.sources().then((r) => setSources(r.sources)).catch((e) => nav.setError(e.message))
    loadProposals()
  }, [nav.caseId, nav.tick, loadProposals, nav])

  const run = useCallback((source: string, r: RecipeStep[] | null, m: Record<string, string[]> | null) => {
    setBusy(true)
    setErr('')
    intake
      .preview({ source, recipe: r, mapping: m })
      .then((res) => {
        setPv(res)
        setRecipe(res.recipe)
        setMapping(res.mapping)
        setDirty(false)
      })
      .catch((e) => {
        setPv(null)
        setErr(e.message)
      })
      .finally(() => setBusy(false))
  }, [])

  const choose = (s: IntakeSource) => {
    setSrc(s.id)
    setSelProp(null)
    setRowFilter(null)
    setMarks({})
    setTab(s.kind === 'text' ? 'tagging' : 'profile')
    run(s.id, null, null)
  }

  if (!nav.caseId)
    return (
      <div className="studio-empty">
        <NonIdealState icon="lock" title="Open a case to use the data studio"
          description="An extract is lawful material for one case. Choose the case it was obtained for from the case selector; the studio then shows only the sources that the case purpose covers." />
      </div>
    )

  const current = sources?.find((s) => s.id === src)
  return (
    <div className="workspace studio" style={{ gridTemplateColumns: '248px minmax(0, 1fr) 340px' }}>
      <aside className="panel">
        <div className="section">
          <h3>Source extracts</h3>
          <p className="small muted">Produced under a notice or order for this case. Nothing here reaches the record until a second officer approves it.</p>
          {!sources && <Spinner size={18} />}
          {sources && !sources.length && <p className="small muted">No extracts are available to this case.</p>}
          {sources?.map((s) => (
            <button key={s.id} className={`rule-row studio-source ${src === s.id ? 'on' : ''} ${s.missing.length ? 'is-blocked' : ''}`}
              aria-pressed={src === s.id} aria-disabled={s.missing.length ? true : undefined}
              onClick={() => (s.missing.length ? nav.setError(`The case purpose does not cover: ${s.missing.join(', ')}`) : choose(s))}
              title={s.missing.length ? `Case purpose does not cover ${s.missing.join(', ')}` : s.description}>
              <span>
                <span style={{ display: 'block' }}>{s.title}</span>
                <span className="small muted" style={{ display: 'block', fontWeight: 400 }}>{s.holder}</span>
              </span>
              <span>{RECORD_WORD[s.record_type] ?? s.record_type}</span>
            </button>
          ))}
        </div>
        <div className="section">
          <h3>Proposals in my cases</h3>
          {props.length === 0 && <p className="small muted">None yet.</p>}
          {props.map((p) => (
            <button key={p.id} className={`rule-row ${selProp === p.id ? 'on' : ''}`} aria-pressed={selProp === p.id} onClick={() => setSelProp(p.id)}>
              <span>
                <span style={{ display: 'block' }}>{p.summary.title ?? p.source}</span>
                <span className="small muted" style={{ display: 'block', fontWeight: 400 }}>{p.requested_by} · {when(p.requested_at)}</span>
              </span>
              <span className={`status-word s-${p.status}`}>{p.status}</span>
            </button>
          ))}
        </div>
      </aside>

      <main className="canvas studio-main">
        {!src && (
          <NonIdealState icon="th-derived" title="Choose a source extract"
            description="Mosaic reads each column, suggests clean-up steps, maps the columns to record fields, matches rows to people and accounts already on record, and shows what it finds before anything is published." />
        )}
        {src && busy && !pv && <Spinner />}
        {err && <Callout intent="danger" title="Not available">{err}</Callout>}
        {pv && current && (
          <>
            <header className="studio-head">
              <div>
                <h2>{pv.title}</h2>
                <div className="small muted">{pv.holder} · {pv.legal} · fingerprint {pv.fingerprint}</div>
              </div>
              {busy && <Spinner size={16} />}
            </header>
            <ol className="lineage" aria-label="Lineage" style={{ gridTemplateColumns: `repeat(${pv.lineage.length}, minmax(0, 1fr))` }}>
              {pv.lineage.map((l) => (
                <li key={l.stage}>
                  <span className="lineage-stage">{l.stage}</span>
                  <b>{l.n.toLocaleString('en-IN')}</b>
                  <span className="small muted">{l.label}</span>
                </li>
              ))}
            </ol>
            <Tabs id="studio-tabs" selectedTabId={tab} onChange={(t) => setTab(String(t))}>
              <Tab id="profile" title="Columns" />
              <Tab id="recipe" title={`Clean-up${dirty ? ' (not applied)' : ''}`} />
              <Tab id="mapping" title={`Fields${pv.mapping_errors.length ? ' (needs fixing)' : ''}`} />
              {pv.kind === 'text' ? <Tab id="tagging" title="Tagging" /> : <Tab id="matching" title="Matching" />}
              <Tab id="lenses" title={`Checks (${pv.lenses.patterns.filter((p) => p.severity === 'review').length})`} />
              <Tab id="changes" title="Changes" />
            </Tabs>
            <div className="studio-body">
              {tab === 'profile' && <Profile pv={pv} />}
              {tab === 'recipe' && recipe && (
                <Recipe pv={pv} recipe={recipe} dirty={dirty} busy={busy}
                  onChange={(r) => { setRecipe(r); setDirty(true) }} onApply={() => run(src, recipe, mapping)} onReset={() => run(src, null, mapping)} />
              )}
              {tab === 'mapping' && mapping && (
                <Mapping pv={pv} mapping={mapping} dirty={dirty} busy={busy}
                  onChange={(m) => { setMapping(m); setDirty(true) }} onApply={() => run(src, recipe, mapping)} onReset={() => run(src, recipe, null)} />
              )}
              {tab === 'matching' && <Matching rows={pv.rows} filter={rowFilter} onClear={() => setRowFilter(null)} nav={nav} keyCol={keyColumn(pv)} nameCol={nameColumn(pv)} />}
              {tab === 'tagging' && <Tagging rows={pv.rows} filter={rowFilter} onClear={() => setRowFilter(null)} />}
              {tab === 'lenses' && (
                <Lenses pv={pv} marks={marks} nav={nav}
                  onMark={(id, m) => setMarks((x) => ({ ...x, [id]: m }))}
                  onRows={(rows) => { setRowFilter(rows); setTab(pv.kind === 'text' ? 'tagging' : 'matching') }} />
              )}
              {tab === 'changes' && <Changes pv={pv} />}
            </div>
          </>
        )}
      </main>

      <aside className="panel right">
        {selProp ? (
          <ProposalPanel id={selProp} nav={nav} onBack={() => setSelProp(null)} onChange={loadProposals} />
        ) : pv && current ? (
          <ProposeForm pv={pv} source={current} recipe={recipe} mapping={mapping} dirty={dirty} marks={marks} nav={nav}
            onDone={(id) => { loadProposals(); setSelProp(id) }} />
        ) : (
          <div className="panel-empty"><h3>Nothing selected</h3><p>Choose a source extract to prepare it, or a proposal to review it.</p></div>
        )}
      </aside>
    </div>
  )
}

function keyColumn(pv: IntakePreview) {
  const k = pv.record.key ? `${pv.record.type}.${pv.record.key}` : null
  return Object.entries(pv.mapping).find(([, ts]) => (k ? ts.includes(k) : ts.includes('Event.location')))?.[0] ?? pv.columns[0]
}
function nameColumn(pv: IntakePreview) {
  return Object.entries(pv.mapping).find(([, ts]) => ts.includes('Person.name'))?.[0] ?? pv.columns[1]
}

// ---------------------------------------------------------------------------- profile
function Profile({ pv }: { pv: IntakePreview }) {
  return (
    <>
      <p className="small muted">Each column is typed by voting over its values, not by its header. Formats are value shapes (letters as A, digits as 9); the counts say how much of the column the suggested steps would change or reject.</p>
      <table className="data studio-table">
        <thead>
          <tr><th>Column</th><th>Detected as</th><th>Filled</th><th>Distinct</th><th>Formats seen</th><th>Would change</th><th>Would reject</th></tr>
        </thead>
        <tbody>
          {pv.profile.map((c) => (
            <tr key={c.column}>
              <td className="mono">{c.column}</td>
              <td>
                {c.detected_label}
                {c.detected !== 'text' && c.detected !== 'category' && <span className="small muted"> · {Math.round(c.confidence * 100)}%</span>}
                {c.ambiguous > 0 && <div className="small warn-text">{c.ambiguous} dates read either way (dd/mm or mm/dd)</div>}
              </td>
              <td>
                <div className="meter" title={`${c.filled} of ${c.rows}`}><span style={{ width: `${c.completeness * 100}%` }} /></div>
                <span className="small muted">{Math.round(c.completeness * 100)}%{c.placeholders ? ` · ${c.placeholders} placeholders` : ''}</span>
              </td>
              <td>{c.distinct}</td>
              <td>
                {c.values.length > 0
                  ? c.values.map((v) => <span key={v.value} className="chip mono">{v.value} <i>{v.n}</i></span>)
                  : c.shapes.slice(0, 4).map((s) => <span key={s.shape} className="chip mono" title={`e.g. ${s.example}`}>{s.shape} <i>{s.n}</i></span>)}
                {c.formats > 4 && c.values.length === 0 && <span className="small muted"> +{c.formats - 4}</span>}
              </td>
              <td>{c.would_change || '—'}</td>
              <td>{c.would_reject ? <b>{c.would_reject}</b> : '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  )
}

// ---------------------------------------------------------------------------- recipe
function Recipe({ pv, recipe, dirty, busy, onChange, onApply, onReset }: { pv: IntakePreview; recipe: RecipeStep[]; dirty: boolean; busy: boolean; onChange: (r: RecipeStep[]) => void; onApply: () => void; onReset: () => void }) {
  const [col, setCol] = useState('')
  const [view, setView] = useState<'changes' | 'quarantine' | 'duplicates'>('changes')
  const changes = pv.changes.filter((c) => !col || c.column === col)
  return (
    <>
      <div className="studio-toolbar">
        <span className="small muted">Steps run in order per column. Applying never touches the source rows; every changed cell is listed.</span>
        <span style={{ flex: 1 }} />
        <Button small text="Suggested steps" onClick={onReset} disabled={busy} />
        <Button small intent="primary" text="Apply clean-up" onClick={onApply} disabled={!dirty || busy} />
      </div>
      <table className="data studio-table">
        <tbody>
          {pv.columns.map((c) => {
            const steps = recipe.filter((r) => r.column === c)
            return (
              <tr key={c}>
                <td className="mono" style={{ width: 150 }}>{c}</td>
                <td>
                  {steps.map((s, i) => (
                    <Tag key={i} minimal className="step-tag" onRemove={() => onChange(recipe.filter((r) => !(r.column === c && r.step === s.step)))} title={pv.steps[s.step]}>
                      {i + 1}. {titleCase(s.step)}
                    </Tag>
                  ))}
                </td>
                <td style={{ width: 210 }}>
                  <HTMLSelect minimal value="" onChange={(e) => e.target.value && onChange([...recipe, { column: c, step: e.target.value }])}>
                    <option value="">Add a step…</option>
                    {Object.entries(pv.steps).filter(([k]) => !steps.some((s) => s.step === k)).map(([k, label]) => <option key={k} value={k}>{label}</option>)}
                  </HTMLSelect>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
      <div className="studio-toolbar" style={{ marginTop: 14 }}>
        <div className="segmented">
          <button className={view === 'changes' ? 'on' : ''} onClick={() => setView('changes')}>Cells changed ({pv.summary.cells_changed})</button>
          <button className={view === 'quarantine' ? 'on' : ''} onClick={() => setView('quarantine')}>Quarantined ({pv.quarantine.length})</button>
          <button className={view === 'duplicates' ? 'on' : ''} onClick={() => setView('duplicates')}>Duplicates ({pv.duplicates.length})</button>
        </div>
        <span style={{ flex: 1 }} />
        {view === 'changes' && (
          <HTMLSelect minimal value={col} onChange={(e) => setCol(e.target.value)}>
            <option value="">All columns</option>
            {pv.columns.map((c) => <option key={c} value={c}>{c}</option>)}
          </HTMLSelect>
        )}
      </div>
      {view === 'changes' && (
        <table className="data studio-table">
          <thead><tr><th>Row</th><th>Column</th><th>Before</th><th>After</th><th>Why</th></tr></thead>
          <tbody>
            {changes.slice(0, 250).map((c, i) => (
              <tr key={i}>
                <td>{c.row + 1}</td><td className="mono">{c.column}</td>
                <td className="mono before">{show(c.before)}</td><td className="mono">{show(c.after)}</td><td className="small muted">{c.note}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {view === 'changes' && changes.length > 250 && <p className="small muted">Showing 250 of {changes.length}.</p>}
      {view === 'quarantine' && (
        <table className="data studio-table">
          <thead><tr><th>Row</th><th>Why it was held back</th><th>Values after cleaning</th></tr></thead>
          <tbody>
            {pv.quarantine.map((q) => (
              <tr key={q.row}>
                <td>{q.row + 1}</td>
                <td>{q.reasons.map((r) => <div key={r}>{r}</div>)}</td>
                <td className="small mono">{Object.entries(q.values).filter(([, v]) => v).map(([k, v]) => `${k}=${show(v)}`).join('  ') || 'all empty'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {view === 'duplicates' && (
        <table className="data studio-table">
          <thead><tr><th>Row</th><th>Same key as row</th></tr></thead>
          <tbody>{pv.duplicates.map((d) => <tr key={d.row}><td>{d.row + 1}</td><td>{d.duplicate_of + 1}</td></tr>)}</tbody>
        </table>
      )}
    </>
  )
}

// ---------------------------------------------------------------------------- mapping
function Mapping({ pv, mapping, dirty, busy, onChange, onApply, onReset }: { pv: IntakePreview; mapping: Record<string, string[]>; dirty: boolean; busy: boolean; onChange: (m: Record<string, string[]>) => void; onApply: () => void; onReset: () => void }) {
  const detected = Object.fromEntries(pv.profile.map((c) => [c.column, c.detected_label]))
  const set = (c: string, ts: string[]) => onChange({ ...mapping, [c]: ts })
  return (
    <>
      <div className="studio-toolbar">
        <span className="small muted">
          Dataset → object type, row → object, column → property, cell → value, join → link. Each row becomes one <b>{pv.record.type}</b>
          {pv.record.key ? <> keyed on <span className="mono">{pv.record.key}</span></> : null}, tied to its {pv.kind === 'text' ? 'mentions' : 'person'} by <span className="mono">{pv.record.link}</span>.
        </span>
        <span style={{ flex: 1 }} />
        <Button small text="Default mapping" onClick={onReset} disabled={busy} />
        <Button small intent="primary" text="Apply mapping" onClick={onApply} disabled={!dirty || busy} />
      </div>
      {pv.mapping_errors.length > 0 && <Callout intent="warning" title="This mapping cannot be proposed">{pv.mapping_errors.map((e) => <div key={e}>{e}</div>)}</Callout>}
      <table className="data studio-table">
        <thead><tr><th>Column</th><th>Detected as</th><th>Maps to</th><th /></tr></thead>
        <tbody>
          {pv.columns.map((c) => {
            const ts = mapping[c] ?? []
            const sw = pv.switch[c]
            return (
              <tr key={c}>
                <td className="mono">{c}</td>
                <td className="small muted">{detected[c]}</td>
                <td>
                  {ts.length === 0 && <span className="small muted">not used</span>}
                  {ts.map((t) => t === 'switch' && sw ? (
                    <span key={t} className="small">by <span className="mono">{sw.by}</span>: {Object.entries(sw.cases).map(([k, v]) => <span key={k} className="chip mono">{k} → {v === 'check.aadhaar_last4' ? 'compare last 4 only' : v}</span>)}</span>
                  ) : (
                    <Tag key={t} minimal className="map-tag" onRemove={() => set(c, ts.filter((x) => x !== t))}>{t}</Tag>
                  ))}
                </td>
                <td style={{ width: 200 }}>
                  <HTMLSelect minimal value="" onChange={(e) => e.target.value && set(c, [...ts, e.target.value])}>
                    <option value="">Map to…</option>
                    {pv.mapping_options.filter((o) => !ts.includes(o)).map((o) => <option key={o} value={o}>{o}</option>)}
                  </HTMLSelect>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
      <p className="small muted">Full Aadhaar numbers are never stored: an ID column is masked when cleaned and only its last four digits are compared with the record.</p>
    </>
  )
}

// ---------------------------------------------------------------------------- matching
function Matching({ rows, filter, onClear, nav, keyCol, nameCol }: { rows: IntakeRow[]; filter: number[] | null; onClear: () => void; nav: Nav; keyCol: string; nameCol: string }) {
  const [status, setStatus] = useState('')
  const counts = useMemo(() => rows.reduce<Record<string, number>>((m, r) => ({ ...m, [r.match.status]: (m[r.match.status] ?? 0) + 1 }), {}), [rows])
  const shown = rows.filter((r) => (!filter || filter.includes(r.row)) && (!status || r.match.status === status))
  return (
    <>
      <div className="studio-toolbar">
        <div className="segmented">
          <button className={status === '' ? 'on' : ''} onClick={() => setStatus('')}>All ({rows.length})</button>
          {['existing', 'probable', 'new'].map((s) => <button key={s} className={status === s ? 'on' : ''} onClick={() => setStatus(s)}>{STATUS_LABEL[s]} ({counts[s] ?? 0})</button>)}
        </div>
        {filter && <Button small minimal icon="filter-remove" text={`Showing ${filter.length} rows from a lens`} onClick={onClear} />}
        <span style={{ flex: 1 }} />
        <span className="small muted">Identifiers decide; a name and city resemblance is only probable and goes to Resolve.</span>
      </div>
      <table className="data studio-table">
        <thead><tr><th>Row</th><th>{nameCol}</th><th>{keyCol}</th><th>Status</th><th>Basis</th><th>Record</th></tr></thead>
        <tbody>
          {shown.slice(0, 300).map((r) => (
            <tr key={r.row}>
              <td>{r.row + 1}</td>
              <td>{show(r.values[nameCol])}</td>
              <td className="mono">{show(r.values[keyCol])}</td>
              <td><span className={`status-word s-${r.match.status}`}>{STATUS_LABEL[r.match.status]}</span></td>
              <td className="small">
                {r.match.basis}
                {r.match.clashes.map((c, i) => <div key={i} className="small warn-text">Also points to {c.name_on_record ?? 'a record'}: {c.basis.join(', ')}</div>)}
              </td>
              <td>
                {r.match.person ? <Button small minimal text="Open" onClick={() => nav.openEntity(r.match.person!)} />
                  : r.match.status !== 'new' ? <span className="small muted" title="The guard does not allow this record for this case">withheld</span> : <span className="small muted">—</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {shown.length > 300 && <p className="small muted">Showing 300 of {shown.length}.</p>}
    </>
  )
}

// ---------------------------------------------------------------------------- tagging (free text)
function Marked({ text, tags }: { text: string; tags: TextTag[] }) {
  const light = currentTheme() === 'light'
  const parts: ReactNode[] = []
  let at = 0
  for (const t of tags) {
    if (t.start < at) continue
    parts.push(text.slice(at, t.start))
    const col = familyColour(TAG_FAMILY[t.kind] ?? 'other', light ? 'light' : 'dark')
    parts.push(
      <mark key={t.start} className="tag-span" style={{ borderBottomColor: col, background: `color-mix(in srgb, ${col} 16%, transparent)` }}
        title={`${titleCase(t.kind)}: ${show(t.value)}${t.object ? ' · on record' : ''}`}>{text.slice(t.start, t.end)}</mark>,
    )
    at = t.end
  }
  parts.push(text.slice(at))
  return <p className="tagged-text">{parts}</p>
}

function Tagging({ rows, filter, onClear }: { rows: IntakeRow[]; filter: number[] | null; onClear: () => void }) {
  const shown = rows.filter((r) => !filter || filter.includes(r.row))
  return (
    <>
      <div className="studio-toolbar">
        <span className="small muted">Identifiers, amounts, dates and places are tagged with their spans. A written name is tied to a person only when an identifier on the same page is on record for someone of that name.</span>
        {filter && <Button small minimal icon="filter-remove" text={`Showing ${filter.length} pages from a lens`} onClick={onClear} />}
      </div>
      <div className="tag-legend small">
        {['phone', 'account_no', 'vehicle_reg', 'name', 'amount', 'place', 'date'].map((k) => {
          const col = familyColour(TAG_FAMILY[k] ?? 'other')
          return <span key={k}><i style={{ background: col }} />{titleCase(k)}</span>
        })}
      </div>
      {shown.map((r) => (
        <div key={r.row} className="note-page">
          <div className="small muted">Page {show(r.values.page)} · written {show(r.values.written_on)}</div>
          <Marked text={String(r.values.text ?? '')} tags={r.tags} />
          <table className="data studio-table compact">
            <tbody>
              {r.tags.filter((t) => t.kind !== 'date').map((t) => (
                <tr key={t.start}>
                  <td className="small muted" style={{ width: 110 }}>{titleCase(t.kind)}</td>
                  <td className="mono">{show(t.value)}</td>
                  <td className="small">
                    {t.kind === 'name' ? (t.object ? t.basis : 'not tied: no identifier on this page belongs to this name')
                      : ['phone', 'account_no', 'vehicle_reg', 'pan'].includes(t.kind) ? (t.object ? `on record${t.owners.length ? `, ${t.owners.length} holder(s)` : ''}` : t.kind === 'phone' ? 'not on record: a new phone record is proposed' : 'not on record')
                      : ''}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </>
  )
}

// ---------------------------------------------------------------------------- lenses
function PatternCard({ p, mark, onMark, onRows, nav }: { p: IntakePattern; mark?: 'checked' | 'dismissed'; onMark: (m: 'checked' | 'dismissed') => void; onRows: () => void; nav: Nav }) {
  return (
    <div className={`pattern-card ${p.severity} ${mark ?? ''}`}>
      <div className="pattern-head">
        <span className="status-word">{p.severity === 'review' ? 'For review' : 'Note'}</span>
        {mark && <span className="small muted">· {mark === 'checked' ? 'checked by you' : 'dismissed by you'}</span>}
      </div>
      <b>{p.title}</b>
      <p className="small">{p.detail}</p>
      {p.benign && <p className="small muted">Could also be: {p.benign}</p>}
      {p.parties.length > 0 && (
        <div className="pattern-parties">
          {p.parties.map((x) => x.person
            ? <Button key={x.key} small minimal text={x.label} rightIcon="share" onClick={() => nav.openEntity(x.person!)} />
            : <span key={x.key} className="chip">{x.label}{x.status === 'new' ? ' · new' : ''}</span>)}
        </div>
      )}
      <div className="pattern-actions">
        {p.rows.length > 0 && <Button small minimal text={`Show ${p.rows.length} rows`} onClick={onRows} />}
        {p.severity === 'review' && <>
          <Button small minimal icon="tick" text="Checked" active={mark === 'checked'} onClick={() => onMark('checked')} />
          <Button small minimal icon="cross" text="Dismiss" active={mark === 'dismissed'} onClick={() => onMark('dismissed')} />
        </>}
      </div>
    </div>
  )
}

function Lenses({ pv, marks, onMark, onRows, nav }: { pv: IntakePreview; marks: Record<string, 'checked' | 'dismissed'>; onMark: (id: string, m: 'checked' | 'dismissed') => void; onRows: (rows: number[]) => void; nav: Nav }) {
  const open = useCallback((p: string) => nav.openEntity(p), [nav])
  return (
    <div className="lenses">
      <section>
        <h3 className="lens-title">Patterns</h3>
        <p className="small muted">Leads for the reviewer, each with its evidence and an innocent explanation. Nothing here is a finding.</p>
        {pv.lenses.patterns.length === 0 && <p className="small muted">No patterns in this extract.</p>}
        {pv.lenses.patterns.map((p) => <PatternCard key={p.id} p={p} mark={marks[p.id]} onMark={(m) => onMark(p.id, m)} onRows={() => onRows(p.rows)} nav={nav} />)}
      </section>
      <section>
        <h3 className="lens-title">Links the extract would add</h3>
        <MiniGraph nodes={pv.lenses.graph.nodes} links={pv.lenses.graph.links} onOpen={open} />
        <h3 className="lens-title" style={{ marginTop: 18 }}>Where the rows sit</h3>
        <PlacesMap places={pv.lenses.places} />
      </section>
    </div>
  )
}

// ---------------------------------------------------------------------------- changes
function Changes({ pv }: { pv: IntakePreview }) {
  const items = pv.ops.items
  const of = (op: string) => items.filter((o) => o.op === op)
  return (
    <>
      <p className="small muted">What a publish would do. Existing values are never overwritten: an incoming value fills a gap, corroborates the value on record, or is recorded as a conflict for a person to settle.</p>
      <div className="op-tiles">
        {Object.entries(OP_LABEL).map(([k, label]) => (
          <div key={k} className="op-tile"><b>{(pv.ops.counts[k] ?? 0).toLocaleString('en-IN')}</b><span>{label}</span></div>
        ))}
      </div>
      {of('conflict').length > 0 && <>
        <h3 className="lens-title">Conflicts for review</h3>
        <table className="data studio-table">
          <thead><tr><th>Row</th><th>Record</th><th>Property</th><th>On record</th><th>Extract says</th></tr></thead>
          <tbody>{of('conflict').map((o, i) => <tr key={i}><td>{Number(o.record.split('#')[1]) + 1}</td><td className="small">{o.type}</td><td className="mono">{o.prop}</td><td className="mono">{show(o.old)}</td><td className="mono">{show(o.value)}</td></tr>)}</tbody>
        </table>
      </>}
      {of('fill').length > 0 && <>
        <h3 className="lens-title">Gaps filled</h3>
        <table className="data studio-table">
          <thead><tr><th>Row</th><th>Record</th><th>Property</th><th>Value</th></tr></thead>
          <tbody>{of('fill').slice(0, 120).map((o, i) => <tr key={i}><td>{Number(o.record.split('#')[1]) + 1}</td><td className="small">{o.type}</td><td className="mono">{o.prop}</td><td className="mono">{show(o.value)}</td></tr>)}</tbody>
        </table>
      </>}
      {of('alias').length > 0 && <>
        <h3 className="lens-title">Name spellings learned</h3>
        <div>{of('alias').map((o, i) => <span key={i} className="chip">{show(o.value)} <i>for {show(o.old)}</i></span>)}</div>
      </>}
      {of('create').length > 0 && <>
        <h3 className="lens-title">New records</h3>
        <table className="data studio-table">
          <thead><tr><th>Type</th><th>Values</th></tr></thead>
          <tbody>{of('create').slice(0, 120).map((o, i) => (
            <tr key={i}><td className="small">{o.type}</td><td className="small mono">{Object.entries(o.props ?? {}).filter(([k]) => !k.startsWith('_')).map(([k, v]) => `${k}=${show(v)}`).join('  ')}</td></tr>
          ))}</tbody>
        </table>
      </>}
    </>
  )
}

// ---------------------------------------------------------------------------- propose and review
function ProposeForm({ pv, source, recipe, mapping, dirty, marks, nav, onDone }: { pv: IntakePreview; source: IntakeSource; recipe: RecipeStep[] | null; mapping: Record<string, string[]> | null; dirty: boolean; marks: Record<string, string>; nav: Nav; onDone: (id: string) => void }) {
  const [order, setOrder] = useState('')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const can = !!nav.me?.roles.some((r) => ['io', 'analyst', 'supervisor'].includes(r))
  const s = pv.summary
  const review = pv.lenses.patterns.filter((p) => p.severity === 'review')
  const markNote = () => {
    const by = (m: string) => review.filter((p) => marks[p.id] === m).map((p) => p.title)
    const parts = [by('checked').length ? `Checked: ${by('checked').join('; ')}` : '', by('dismissed').length ? `Dismissed: ${by('dismissed').join('; ')}` : '']
    return [note.trim(), ...parts].filter(Boolean).join('\n')
  }
  return (
    <div className="section">
      <h3>Proposal</h3>
      <div className="kv-grid small">
        <span>Rows received</span><b>{s.rows}</b>
        <span>Clean</span><b>{s.clean}</b>
        <span>Quarantined</span><b>{s.quarantined}</b>
        <span>Duplicates</span><b>{s.duplicates}</b>
        {pv.kind === 'text' ? <>
          <span>Entities tagged</span><b>{pv.rows.reduce((n, r) => n + r.tags.length, 0)}</b>
          <span>Tied to records</span><b>{pv.rows.reduce((n, r) => n + r.tags.filter((t) => t.object).length, 0)}</b>
        </> : <>
          <span>On record</span><b>{s.existing}</b>
          <span>Probable</span><b>{s.probable}</b>
          <span>New</span><b>{s.new}</b>
          <span>Distinct people</span><b>{s.identities}</b>
        </>}
        <span>Leads to review</span><b>{review.length}</b>
      </div>
      <p className="small muted" style={{ marginTop: 10 }}>Record classes: {source.class_labels.join(', ')}.</p>
      <label className="small muted">Order or notice under which it was obtained</label>
      <InputGroup small value={order} placeholder={`e.g. ${source.legal} No. 44/2026`} onChange={(e) => setOrder(e.target.value)} />
      <label className="small muted" style={{ marginTop: 8, display: 'block' }}>Note for the reviewer</label>
      <TextArea small fill rows={3} value={note} onChange={(e) => setNote(e.target.value)} />
      {dirty && <Callout intent="warning" style={{ marginTop: 8 }}>Apply your clean-up or field changes first; the proposal keeps what was last applied.</Callout>}
      <Button style={{ marginTop: 10 }} intent="primary" fill loading={busy} icon="send-to"
        disabled={!can || dirty || order.trim().length < 8 || pv.mapping_errors.length > 0}
        title={!can ? 'Only investigators and analysts can propose an intake' : ''}
        text="Propose for review"
        onClick={() => {
          setBusy(true)
          intake.propose({ source: pv.source, recipe, mapping, legal_order: order, note: markNote() })
            .then((r) => onDone(r.proposal))
            .catch((e) => nav.setError(e.message))
            .finally(() => setBusy(false))
        }} />
      <p className="small muted" style={{ marginTop: 8 }}>A supervisor who is a member of this case, and not you, approves it. Approval publishes the frozen operations with this order attached; a later revert undoes them card by card.</p>
    </div>
  )
}

function ProposalPanel({ id, nav, onBack, onChange }: { id: string; nav: Nav; onBack: () => void; onChange: () => void }) {
  const [p, setP] = useState<Awaited<ReturnType<typeof intake.proposal>> | null>(null)
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<string>('')
  const load = useCallback(() => intake.proposal(id).then(setP).catch((e) => nav.setError(e.message)), [id, nav])
  useEffect(() => { setResult(''); setReason(''); load() }, [load])
  if (!p) return <Spinner />
  const sup = !!nav.me?.roles.includes('supervisor')
  const mine = p.requested_by === nav.me?.id
  const act = (a: 'approve' | 'reject' | 'revert') => {
    setBusy(true)
    intake.decide(id, a, reason)
      .then((r) => {
        setResult(a === 'approve' ? `Published: ${Object.entries(r.applied ?? {}).map(([k, v]) => `${v} ${OP_LABEL[k]?.toLowerCase() ?? k}`).join(', ')}.` : a === 'revert' ? `Reverted: ${r.objects_removed ?? 0} records removed.` : 'Rejected.')
        load()
        onChange()
        nav.refresh()
      })
      .catch((e) => nav.setError(e.message))
      .finally(() => setBusy(false))
  }
  return (
    <div className="section">
      <Button small minimal icon="arrow-left" text="Back" onClick={onBack} />
      <h3 style={{ marginTop: 8 }}>{p.summary.title ?? p.source}</h3>
      <div className="small"><span className={`status-word s-${p.status}`}>{p.status}</span> · proposed by {p.requested_by} · {when(p.requested_at)}</div>
      <div className="small muted" style={{ margin: '6px 0' }}>Under: {p.legal_order}</div>
      <div className="kv-grid small">
        {Object.entries(p.ops.counts).map(([k, v]) => <Fragment key={k}><span>{OP_LABEL[k] ?? k}</span><b>{v.toLocaleString('en-IN')}</b></Fragment>)}
      </div>
      {p.summary.leads.length > 0 && <>
        <h3 style={{ marginTop: 12 }}>Leads raised</h3>
        {p.summary.leads.map((l, i) => <div key={i} className="kv-row small">{l.title}</div>)}
      </>}
      {p.recipe.note && <><h3 style={{ marginTop: 12 }}>Proposer's note</h3><p className="small" style={{ whiteSpace: 'pre-wrap' }}>{p.recipe.note}</p></>}
      {p.decided_by && <p className="small muted">Decided by {p.decided_by} · {when(p.decided_at)}: {p.decision_reason}</p>}
      {result && <Callout intent="success" style={{ margin: '8px 0' }}>{result}</Callout>}
      {sup && (p.status === 'pending' || p.status === 'approved') && (
        <>
          <label className="small muted">Reason (recorded in the audit log)</label>
          <TextArea small fill rows={2} value={reason} onChange={(e) => setReason(e.target.value)} />
          {p.status === 'pending' ? (
            <div className="studio-toolbar" style={{ marginTop: 8 }}>
              <Button intent="primary" icon="endorsed" text="Approve and publish" loading={busy} disabled={mine || reason.trim().length < 4}
                title={mine ? 'Two-person rule: another supervisor must approve your own proposal' : ''} onClick={() => act('approve')} />
              <Button text="Reject" disabled={busy || reason.trim().length < 4} onClick={() => act('reject')} />
            </div>
          ) : (
            <Button style={{ marginTop: 8 }} icon="undo" text="Revert this publish" loading={busy} disabled={reason.trim().length < 4} onClick={() => act('revert')} />
          )}
        </>
      )}
      {!sup && p.status === 'pending' && <p className="small muted">Waiting for a supervisor of this case.</p>}
      {p.status === 'approved' && (
        <div className="studio-toolbar" style={{ marginTop: 10 }}>
          <Button small icon="globe" text="Case on map" onClick={() => nav.openGlobe(p.case_id)} />
          {nav.me?.roles.some((r) => r === 'supervisor' || r === 'analyst') && (
            <Button small icon="search-around" text="Re-run patterns"
              onClick={() => patterns.run().then((r) => nav.setError(`Pattern engine: ${r.leads} leads in ${r.seconds}s`)).catch((e) => nav.setError(e.message))} />
          )}
        </div>
      )}
    </div>
  )
}

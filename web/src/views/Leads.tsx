import { Callout, HTMLSelect, InputGroup, NonIdealState, Spinner, Tag, TextArea } from '@blueprintjs/core'
import { Button } from '../components/Button'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { patterns, type Lead, type LeadDetail } from '../api'
import { activate } from '../lib/a11y'
import { day, sentence, titleCase, when, rupees } from '../lib/format'
import type { Nav } from './nav'

type Catalog = Awaited<ReturnType<typeof patterns.catalog>>
type Summary = Awaited<ReturnType<typeof patterns.summary>>
type Requests = Awaited<ReturnType<typeof patterns.requests>>['requests']

const SEV: Record<string, 'danger' | 'warning' | 'none'> = { high: 'danger', medium: 'warning', low: 'none' }

export default function Leads({ nav }: { nav: Nav }) {
  const [cat, setCat] = useState<Catalog | null>(null)
  const [sum, setSum] = useState<Summary | null>(null)
  const [track, setTrack] = useState('')
  const [detector, setDetector] = useState('')
  const [status, setStatus] = useState('open')
  const [leads, setLeads] = useState<Lead[] | null>(null)
  const [sel, setSel] = useState<string | null>(nav.focus)
  const [reqs, setReqs] = useState<Requests>([])
  const [denied, setDenied] = useState('')
  const [filtersOpen, setFiltersOpen] = useState(false)

  const cards = useMemo(() => Object.fromEntries((cat?.detectors ?? []).map((d) => [d.id, d])), [cat])
  const supervisor = !!nav.me?.roles.includes('supervisor')

  const reload = useCallback(() => {
    patterns.summary().then(setSum).catch(() => setSum(null))
    patterns
      .leads({ track: track || undefined, detector: detector || undefined, status })
      .then((r) => {
        setLeads(r.leads)
        setDenied('')
        setSel((s) => (s && r.leads.some((l) => l.id === s) ? s : r.leads.find((l) => l.id === nav.focus)?.id ?? r.leads[0]?.id ?? null))
      })
      .catch((e) => {
        setLeads([])
        setDenied(e.message)
      })
    if (supervisor) patterns.requests().then((r) => setReqs(r.requests)).catch(() => setReqs([]))
  }, [track, detector, status, supervisor])

  useEffect(() => {
    patterns.catalog().then(setCat).catch((e) => nav.setError(e.message))
  }, [nav])
  useEffect(() => {
    reload()
  }, [reload, nav.tick])

  const detectorsInView = useMemo(() => {
    const m = new Map<string, number>()
    for (const l of leads ?? []) m.set(l.detector, (m.get(l.detector) ?? 0) + 1)
    return [...m.entries()].sort((a, b) => b[1] - a[1])
  }, [leads])

  return (
    <div className="workspace" style={{ gridTemplateColumns: '250px 1fr 430px' }}>
      <aside className={`panel filter-panel ${filtersOpen ? 'filters-open' : ''}`}>
        <button className="panel-toggle" aria-expanded={filtersOpen} onClick={() => setFiltersOpen(!filtersOpen)}>Mission tracks and filters<span>{filtersOpen ? 'Hide' : 'Show'}</span></button>
        <div className="section">
          <h3>Mission tracks</h3>
          <p className="small muted">Patterns forming in the data, with their evidence. Leads, not findings; nobody is scored.</p>
          <button className={`rule-row ${track === '' ? 'on' : ''}`} aria-pressed={track === ''} onClick={() => setTrack('')}>
            <span>All my tracks</span><span>{sum?.open ?? ''}</span>
          </button>
          {(cat?.my_tracks ?? []).map((t) => (
            <button key={t} className={`rule-row ${track === t ? 'on' : ''}`} aria-pressed={track === t} onClick={() => setTrack(t)}>
              <span>{cat?.tracks[t]?.label ?? t}</span><span>{sum?.by_track[t] ?? 0}</span>
            </button>
          ))}
          {cat && cat.my_tracks.length === 0 && <p className="small muted">Your role or agency has no mission tracks. Detector quality figures are under Robustness.</p>}
        </div>
        <div className="section">
          <h3>Status</h3>
          <HTMLSelect fill value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Lead status">
            <option value="open">Open</option>
            <option value="case_opened">Case opened</option>
            <option value="dismissed">Dismissed</option>
            <option value="all">All</option>
          </HTMLSelect>
        </div>
        {detectorsInView.length > 0 && (
          <div className="section">
            <h3>Patterns</h3>
            <button className={`rule-row ${detector === '' ? 'on' : ''}`} aria-pressed={detector === ''} onClick={() => setDetector('')}>
              <span>All patterns</span><span>{leads?.length ?? ''}</span>
            </button>
            {detectorsInView.map(([d, n]) => (
              <button key={d} className={`rule-row ${detector === d ? 'on' : ''}`} aria-pressed={detector === d} onClick={() => setDetector(d)}>
                <span>{cards[d]?.title ?? titleCase(d)}</span><span>{n}</span>
              </button>
            ))}
          </div>
        )}
        {supervisor && reqs.length > 0 && (
          <div className="section">
            <h3>Case requests <span className="count">{reqs.filter((r) => r.status === 'pending').length} pending</span></h3>
            {reqs.map((r) => (
              <div key={r.id} className="kv-row small">
                <b>{r.lead_title}</b>
                <div className="muted">
                  {titleCase(r.purpose)} · asked by {r.requested_by} · {when(r.requested_at)}
                </div>
                {r.status === 'pending' ? (
                  <Button
                    small
                    intent="primary"
                    icon="endorsed"
                    disabled={r.requested_by === nav.me?.id}
                    title={r.requested_by === nav.me?.id ? 'Two-person rule: another supervisor must approve your own request' : ''}
                    onClick={() =>
                      patterns
                        .approve(r.id)
                        .then((o) => {
                          nav.setError(`Case ${o.case_id} opened with ${o.subjects} subjects in scope`)
                          nav.refresh()
                        })
                        .catch((e) => nav.setError(e.message))
                    }
                  >
                    Approve and open case
                  </Button>
                ) : (
                  <Tag minimal>{r.status}{r.case_id ? ` · ${r.case_id}` : ''}</Tag>
                )}
              </div>
            ))}
          </div>
        )}
      </aside>
      <main className="canvas scroll" style={{ padding: '4px 20px 20px', background: 'var(--sheet)' }}>
        <div className="register-heading" style={{ minHeight: 52 }}><h2 style={{ fontSize: 15 }}>Leads<span>{leads?.length ?? ''}</span></h2></div>
        {(
          <>
            {!leads && <div className="empty"><Spinner size={20} /></div>}
            {denied && <NonIdealState icon="lock" title="No leads for this role" description={denied} />}
            {leads && !denied && leads.length === 0 && <NonIdealState icon="tick-circle" title="No leads" description="Nothing in these tracks and filters." />}
            {leads && leads.length > 0 && (
              <table className="data leads-table">
                <thead>
                  <tr>
                    <th>Severity</th>
                    <th>Lead</th>
                    <th>Pattern</th>
                    <th>Tracks</th>
                    <th>Last seen</th>
                  </tr>
                </thead>
                <tbody>
                  {leads.map((l) => (
                    <tr key={l.id} className={`clickable ${sel === l.id ? 'selrow' : ''}`} aria-current={sel === l.id ? 'true' : undefined} {...activate(() => setSel(l.id))}>
                      <td>
                        <Tag minimal intent={SEV[l.severity]}>{titleCase(l.severity)}</Tag>
                      </td>
                      <td>
                        <b>{l.title}</b>
                        <div className="small muted">{l.pseudonymous ? 'Pseudonymous' : 'Case opened: names shown to members'}</div>
                      </td>
                      <td className="small">{cards[l.detector]?.title ?? titleCase(l.detector)}</td>
                      <td className="small muted">{l.tracks.map((t) => t.replaceAll('_', ' ')).join(', ')}</td>
                      <td className="small muted nowrap">{day(l.window[1] || '')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </>
        )}
      </main>
      <aside className="panel right">{sel ? <LeadPanel id={sel} nav={nav} onChange={reload} /> : <div className="panel-empty"><h3>No lead selected</h3><p>Choose a lead in the list to see its evidence, parties and what to do next.</p></div>}</aside>
    </div>
  )
}

function LeadPanel({ id, nav, onChange }: { id: string; nav: Nav; onChange: () => void }) {
  const [d, setD] = useState<LeadDetail | null>(null)
  const [purpose, setPurpose] = useState('')
  const [basis, setBasis] = useState('')
  const [title, setTitle] = useState('')
  const [reason, setReason] = useState('')
  const [msg, setMsg] = useState('')
  useEffect(() => {
    setD(null)
    setMsg('')
    patterns
      .lead(id)
      .then((r) => {
        setD(r)
        setPurpose(r.purposes[0] ?? '')
      })
      .catch((e) => setMsg(e.message))
  }, [id, nav.tick, nav.caseId])
  if (!d) return msg ? <div className="panel-empty"><p className="err">{msg}</p></div> : <div className="panel-empty"><Spinner size={20} /></div>
  const card = d.detector_card
  const canRequest = !!nav.me && (nav.me.roles.includes('io') || nav.me.roles.includes('supervisor')) && d.status === 'open'
  return (
    <div className="section">
      <div className="row" style={{ gap: 6 }}>
        <Tag minimal intent={SEV[d.severity]}>{titleCase(d.severity)}</Tag>
        <Tag minimal>{card?.title ?? d.detector}</Tag>
        {d.status !== 'open' && <Tag intent={d.status === 'dismissed' ? 'none' : 'success'}>{titleCase(d.status)}</Tag>}
      </div>
      <h2>{d.title}</h2>
      {d.pseudonymous ? (
        <Callout intent="primary" icon="eye-off" compact>
          Pseudonymous. Parties are labelled per lead, so leads cannot be joined by their labels. Names and evidence appear only to members of a case opened on this lead.
        </Callout>
      ) : (
        <Callout intent="success" icon="endorsed" compact>
          Shown to you as a member of the case opened on this lead. Every view is audited.
        </Callout>
      )}
      <p style={{ margin: '12px 0 0' }}>{rupees(d.summary)}</p>
      <h4>Parties</h4>
      <div className="row" style={{ flexWrap: 'wrap', gap: 6 }}>
        {d.parties.map((p, i) =>
          p.revealed && p.id ? (
            <Button key={i} small icon="person" onClick={() => nav.openEntity(p.id!)}>
              {p.label}
            </Button>
          ) : (
            <Tag key={i} minimal>
              {p.label}
            </Tag>
          ),
        )}
      </div>
      <h4>Evidence behind it</h4>
      <dl className="measure-list">
        {Object.entries(d.evidence_counts).filter(([, v]) => v).map(([k, v]) => (
          <div key={k} style={{ display: 'contents' }}><dt>{sentence(k)}</dt><dd>{v}</dd></div>
        ))}
        {d.window[0] && <div style={{ display: 'contents' }}><dt>Period</dt><dd>{day(d.window[0])} to {day(d.window[1])}</dd></div>}
      </dl>
      {card && (
        <details style={{ marginTop: 12 }}>
          <summary className="small">How this pattern works</summary>
          <p className="small"><b>{card.question}</b></p>
          {card.benign.length > 0 && <><p className="small muted" style={{ marginBottom: 2 }}>It deliberately ignores</p><ul className="small" style={{ marginTop: 0 }}>{card.benign.map((x) => <li key={x}>{x}</li>)}</ul></>}
          {card.blind_spots.length > 0 && <><p className="small muted" style={{ marginBottom: 2 }}>It can miss</p><ul className="small" style={{ marginTop: 0 }}>{card.blind_spots.map((x) => <li key={x}>{x}</li>)}</ul></>}
          <p className="small muted">A lead is a pattern in the records, not a finding. Check the evidence before acting.</p>
        </details>
      )}
      {d.requests.length > 0 && (
        <>
          <h4>Case requests</h4>
          {d.requests.map((r) => (
            <div key={r.id} className="kv-row small">
              {titleCase(r.purpose)} · {r.requested_by} · <Tag minimal>{titleCase(r.status)}</Tag> {r.case_id && <button className="link" onClick={() => nav.openCase(r.case_id!)}>{r.case_id}</button>}
            </div>
          ))}
        </>
      )}
      {canRequest && (
        <>
          <h4>Ask for a case on this lead</h4>
          <p className="small muted">A supervisor of your agency who is not you must approve. Only then do the parties enter a case scope.</p>
          <HTMLSelect fill value={purpose} onChange={(e) => setPurpose(e.target.value)} aria-label="Purpose">
            {d.purposes.map((p) => (
              <option key={p} value={p}>
                {titleCase(p)}
              </option>
            ))}
          </HTMLSelect>
          <InputGroup style={{ marginTop: 8 }} aria-label="Case title" placeholder="Case title" value={title} onChange={(e) => setTitle(e.target.value)} />
          <TextArea style={{ marginTop: 8 }} fill rows={2} aria-label="Legal basis" placeholder="Legal basis: FIR or order, and the provisions relied on" value={basis} onChange={(e) => setBasis(e.target.value)} />
          <Button
            style={{ marginTop: 8 }}
            intent="primary"
            icon="send-message"
            disabled={basis.trim().length < 10 || !purpose}
            onClick={() =>
              patterns
                .requestCase(d.id, { purpose, legal_basis: basis, title })
                .then((r) => {
                  setMsg(`Request ${r.request_id} sent: ${r.next}`)
                  onChange()
                })
                .catch((e) => setMsg(e.message))
            }
          >
            Request case
          </Button>
        </>
      )}
      {d.status === 'open' && (
        <>
          <h4>Dismiss</h4>
          <div className="row" style={{ gap: 6 }}>
            <InputGroup fill aria-label="Reason for dismissing" placeholder="Reason, kept as the reviewer's disposition" value={reason} onChange={(e) => setReason(e.target.value)} />
            <Button
              icon="cross"
              disabled={reason.trim().length < 10}
              onClick={() =>
                patterns
                  .dismiss(d.id, reason)
                  .then(() => onChange())
                  .catch((e) => setMsg(e.message))
              }
            >
              Dismiss
            </Button>
          </div>
        </>
      )}
      {msg && <p className="small" role="status" style={{ marginTop: 8 }}>{msg}</p>}
    </div>
  )
}

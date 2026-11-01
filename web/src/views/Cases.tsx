import { Icon, NonIdealState, Spinner, Tag } from '@blueprintjs/core'
import { Button } from '../components/Button'
import { ReasonDialog } from '../components/ReasonDialog'
import { PersonAvatar } from '../components/PersonPhoto'
import { Tabs } from '@mantine/core'
import { useEffect, useRef, useState } from 'react'
import { api, intel, type CaseBoard } from '../api'
import GraphCanvas, { type GraphHandle } from '../components/GraphCanvas'
import Evidence from './Evidence'
import Reports from './Reports'
import { activate } from '../lib/a11y'
import { day, inr, num, titleCase, when, rupees } from '../lib/format'
import type { Nav } from './nav'

export default function Cases({ caseId, nav }: { caseId: string | null; nav: Nav }) {
  const [b, setB] = useState<CaseBoard | null>(null)
  const [err, setErr] = useState('')
  const [open, setOpen] = useState<string | null>(null)
  const [view, setView] = useState<'board' | 'network' | 'evidence' | 'reports'>('board')
  const [asking, setAsking] = useState<'hold' | 'close' | null>(null)
  const id = caseId || nav.caseId
  useEffect(() => {
    setB(null)
    setErr('')
    if (id) intel.board(id).then(setB).catch((e) => setErr(e.message))
  }, [id, nav.tick])
  if (!id) return <NonIdealState icon="folder-open" title="No case selected" description="Choose a case in the case bar above, or open a new one from the overview." />
  if (err) return <NonIdealState icon="lock" title="Case not available" description={err} />
  if (!b) return <div className="app-loading" role="status"><Spinner size={22} /><p>Loading the case board…</p></div>
  const st = b.stats
  const canClose = b.case.status === 'open' && !!(nav.me?.roles.includes('io') || nav.me?.roles.includes('supervisor'))
  const supervisor = !!nav.me?.roles.includes('supervisor')

  const addLead = (subject: string, name: string, role: string) =>
    api.action('create_lead', { subject_id: subject, title: `${role}: ${name}`, note: 'From suspect ranking' }).then(nav.refresh).catch((e) => nav.setError(e.message))
  const move = (lead: string, stage: string) => api.action('move_lead', { lead_id: lead, stage }).then(nav.refresh).catch((e) => nav.setError(e.message))
  const money: [string, number][] = [['onward', st.money_onward], ['abroad', st.sinks.foreign ?? 0], ['withdrawn in cash', st.sinks.cash ?? 0]]
  const records = b.seeds.filter((s) => s.type !== 'Person')
  const people = b.seeds.filter((s) => s.type === 'Person')

  return (
    <Tabs className="page" value={view} onChange={(value) => setView(value as typeof view)} keepMounted={false}>
      <header className="case-head">
        <div className="case-head-meta">
          <span>{b.case.agency}</span>
          <span className="mono">{b.case.id}</span>
          <span className={b.case.status === 'open' ? 'case-status' : 'muted'}>{b.case.status === 'open' && <span />}{titleCase(b.case.status)}</span>
          <span>{titleCase(b.case.purpose)}</span>
          {b.case.legal_hold ? <Tag intent="danger" minimal>Legal hold</Tag> : null}
          {b.case.retention_until ? <span>Retained until {day(b.case.retention_until)}</span> : null}
        </div>
        <h1>{b.case.title}</h1>
        <p className="case-basis">{b.case.legal_basis}</p>
        {records.length > 0 && <div className="case-refs"><b>Records</b>{records.map((s) => <Tag key={s.id} interactive minimal onClick={() => nav.openEntity(s.id)} onKeyDown={(e) => e.key === 'Enter' && nav.openEntity(s.id)} tabIndex={0}>{s.title}</Tag>)}</div>}
        {people.length > 0 && <div className="case-refs"><b>People</b>{people.map((s) => <Tag key={s.id} interactive minimal onClick={() => nav.openEntity(s.id)} onKeyDown={(e) => e.key === 'Enter' && nav.openEntity(s.id)} tabIndex={0}>{s.title}</Tag>)}</div>}
      </header>
      <div className="case-bar">
        <Tabs.List className="case-view-tabs" aria-label="Case views">
          <Tabs.Tab value="board" leftSection={<Icon icon="th-list" size={14} />}>Case board</Tabs.Tab>
          <Tabs.Tab value="network" leftSection={<Icon icon="graph" size={14} />}>Network</Tabs.Tab>
          <Tabs.Tab value="evidence" leftSection={<Icon icon="archive" size={14} />}>Evidence and exports</Tabs.Tab>
          <Tabs.Tab value="reports" leftSection={<Icon icon="manually-entered-data" size={14} />}>Reports</Tabs.Tab>
        </Tabs.List>
        <div className="case-secondary-actions">
          <Button small icon="globe" onClick={() => nav.openGlobe(id)}>View map</Button>
          {supervisor && <Button small icon={b.case.legal_hold ? 'unlock' : 'lock'} onClick={() => setAsking('hold')}>{b.case.legal_hold ? 'Lift legal hold' : 'Legal hold'}</Button>}
          {canClose && <Button small icon="disable" intent="danger" onClick={() => setAsking('close')}>Close case</Button>}
        </div>
      </div>
      <div className="facts" aria-label="Case figures">
        <span><b>{num(st.network_objects)}</b>records in the network</span>
        <span><b>{num(st.persons)}</b>people</span>
        <span><b>{num(st.accounts)}</b>accounts</span>
        <span><b>{num(st.alerts)}</b>alerts</span>
        <span><b>{num(st.suspects_50)}</b>strong leads</span>
        {money.filter(([, v]) => v > 0).map(([k, v]) => <span key={k}><b>{inr(v)}</b>{k}</span>)}
      </div>
      <Tabs.Panel value="evidence"><Evidence caseId={id} nav={nav} /></Tabs.Panel>
      <Tabs.Panel value="reports"><Reports caseId={id} nav={nav} /></Tabs.Panel>
      <Tabs.Panel value="network"><CaseNetwork id={id} nav={nav} /></Tabs.Panel>
      <Tabs.Panel value="board">
        <div className="grid3">
          <section className="card span-2">
            <h4>Suspects ranked by evidence</h4>
            <p className="card-note">Built by tracing money from the case records, then adding account holders, signatories, directors, call contacts, shared handsets, co-location and family. Each rank is explained; it is a lead for the investigating officer, not a finding.</p>
            {!b.suspects.length && <p className="muted">No one is ranked yet. Add records to the case to build its network.</p>}
            {b.suspects.map((s, i) => (
              <div key={s.id} className={`sus-row ${open === s.id ? 'open' : ''}`}>
                <button className="sus-summary" aria-expanded={open === s.id} onClick={() => setOpen(open === s.id ? null : s.id)}>
                  <span className="rank">{i + 1}</span>
                  <span className="score" title="Evidence weight in this case's network (explained below); not a finding">{Math.round(s.score)}</span>
                  <PersonAvatar id={s.id} name={s.name} size={40} />
                  <span className="who">
                    <b>{s.name}</b> <span>{[s.occupation, s.city].filter(Boolean).join(', ')}</span>
                    <div>{s.evidence[0]}</div>
                  </span>
                  <Tag minimal>{s.role}</Tag>
                </button>
                {open === s.id && (
                  <div className="sus-detail">
                    <ul className="evidence">{s.evidence.map((e, j) => <li key={j}>{e}</li>)}</ul>
                    <p className="small muted" style={{ margin: '0 0 4px' }}>Linked to the case through: {s.why_in_network}{s.hops ? ` · ${s.hops} step${s.hops > 1 ? 's' : ''} from the case records` : ''}.</p>
                    <div className="row" style={{ marginTop: 8 }}>
                      <Button small icon="person" onClick={() => nav.openEntity(s.id)}>Dossier</Button>
                      <Button small icon="bank-account" onClick={() => nav.openTrace(s.id)}>Follow the money</Button>
                      <Button small icon="graph" onClick={() => nav.openGraph(s.id)}>Network</Button>
                      <Button small icon="add" intent="primary" onClick={() => addLead(s.id, s.name, s.role)}>Create lead</Button>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </section>
          <section className="card">
            <h4>Where the money went</h4>
            {b.beneficiaries.length ? b.beneficiaries.map((x) => (
              <button key={x.id} className="kv-row" onClick={() => nav.openEntity(x.id)}><span className="grow">{x.name}</span><span className="amount">{inr(x.amount)}</span></button>
            )) : <p className="muted small">No onward transfers traced from the case records.</p>}
            <h4 style={{ marginTop: 18 }}>Where it came from</h4>
            {b.sources.length ? b.sources.map((x) => (
              <button key={x.id} className="kv-row" onClick={() => nav.openEntity(x.id)}><span className="grow">{x.name}</span><span className="amount">{inr(x.amount)}</span></button>
            )) : <p className="muted small">No incoming transfers traced to the case records.</p>}
            {b.cross_case.length > 0 && (
              <>
                <h4 style={{ marginTop: 18 }}>Shared with other cases</h4>
                {b.cross_case.map((x) => (
                  <div key={x.case_id} className="notice small" style={{ marginBottom: 6 }}>
                    <button className="text-link" onClick={() => nav.openCase(x.case_id)}><b>{x.agency} · {x.title}</b></button>
                    <div>Shares {x.shared.map((s) => s.name).join(', ')}</div>
                  </div>
                ))}
              </>
            )}
          </section>
          <section className="card span-3">
            <h4>Leads board</h4>
            <p className="card-note">Drag cards between columns. Only a supervisor can move a lead to “Action authorised”.</p>
            <div className="kanban">
              {b.stages.map((stg) => {
                const inStage = b.leads.filter((l) => l.stage === stg)
                return (
                  <div key={stg} className="kcol" onDragOver={(e) => e.preventDefault()} onDrop={(e) => { const lid = e.dataTransfer.getData('text/lead'); if (lid) move(lid, stg) }}>
                    <div className="khead">{stg} <span className="muted">{inStage.length}</span></div>
                    {!inStage.length && <div className="kcol-empty">None</div>}
                    {inStage.map((l) => (
                      <div key={l.id} className="kcard" draggable onDragStart={(e) => e.dataTransfer.setData('text/lead', l.id)}>
                        {l.subject_id ? <button className="elink" onClick={() => nav.openEntity(l.subject_id!)}>{l.title}</button> : <b>{l.title}</b>}
                        <div className="small muted">{l.assignee} · {day(l.updated_at)}</div>
                        {l.notes.at(-1)?.text && <div className="small">{l.notes.at(-1)?.text}</div>}
                      </div>
                    ))}
                  </div>
                )
              })}
            </div>
          </section>
          <section className="card span-2">
            <h4>Alerts in the case network <span className="muted">{b.alerts.length}</span></h4>
            {!b.alerts.length && <p className="muted small">No typology alerts on accounts in this network.</p>}
            {b.alerts.length > 0 && <div className="table-scroll"><table className="data">
              <thead><tr><th>Typology</th><th>Finding</th><th>Subject</th><th className="numeric">Amount</th></tr></thead>
              <tbody>
                {b.alerts.slice(0, 30).map((a) => (
                  <tr key={a.id} className="clickable" {...activate(() => nav.openEntity(a.holder_id || a.subject_id))}>
                    <td><Tag minimal intent={a.severity === 'high' ? 'danger' : 'warning'}>{titleCase(a.rule)}</Tag></td>
                    <td className="small">{rupees(a.summary)}</td>
                    <td className="small">{a.holder || a.subject}</td>
                    <td className="numeric">{inr(a.amount)}</td>
                  </tr>
                ))}
              </tbody>
            </table></div>}
          </section>
          <section className="card">
            <h4>Case timeline</h4>
            <div className="timeline compact">
              {!b.timeline.length && <p className="muted small">Nothing recorded yet.</p>}
              {b.timeline.slice(0, 40).map((e, i) => {
                const body = <><span className="small muted">{when(e.at)}</span><b>{e.title}</b>{e.detail && <span className="small muted">{e.detail.slice(0, 120)}</span>}</>
                return e.id
                  ? <button key={i} className={`tl-item dated tl-${e.kind}`} onClick={() => nav.openEntity(e.id!)}>{body}</button>
                  : <div key={i} className={`tl-item dated tl-${e.kind}`}>{body}</div>
              })}
            </div>
          </section>
        </div>
      </Tabs.Panel>
      <ReasonDialog opened={asking === 'hold'} onClose={() => setAsking(null)}
        title={b.case.legal_hold ? 'Lift the legal hold' : 'Place a legal hold'}
        label={b.case.legal_hold ? 'Reason for lifting the hold' : 'Reason for the hold'}
        placeholder={b.case.legal_hold ? 'e.g. appeal period over; order of the Special Court dated…' : 'e.g. trial pending before the Special Court'}
        confirm={b.case.legal_hold ? 'Lift hold' : 'Place hold'}
        onConfirm={(reason) => api.action('set_legal_hold', { case_id: id, hold: !b.case.legal_hold, reason }).then(nav.refresh)} />
      <ReasonDialog opened={asking === 'close'} onClose={() => setAsking(null)} title="Close this case" intent="danger"
        label="Outcome" description="For example, chargesheet filed or closure report. Case-bound data is then kept only until its retention date."
        placeholder="Chargesheet filed before…" confirm="Close case"
        onConfirm={(outcome) => api.action<{ retention_until: string }>('close_case', { case_id: id, outcome }).then((r) => { nav.setError(`Case closed. Case-bound data is retained until ${day(r.retention_until)}.`); nav.refresh() })} />
    </Tabs>
  )
}

function CaseNetwork({ id, nav }: { id: string; nav: Nav }) {
  const g = useRef<GraphHandle>(null)
  useEffect(() => {
    intel
      .network(id)
      .then((r) => g.current?.add(r.nodes, r.edges.map((e) => ({ ...e, amount: e.amount ?? null, count: e.count ?? null }))))
      .catch((e) => nav.setError(e.message))
  }, [id, nav])
  return (
    <div className="card flush" style={{ height: 'calc(100vh - 300px)', minHeight: 480 }}>
      <GraphCanvas ref={g} onOpen={nav.openEntity} />
    </div>
  )
}

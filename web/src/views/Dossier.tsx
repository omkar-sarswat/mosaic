import { HTMLTable, Icon, InputGroup, NonIdealState, Spinner, Tab, Tabs, Tag, type IconName } from '@blueprintjs/core'
import { activate } from '../lib/a11y'
import { Button } from '../components/Button'
import { CaseStart } from '../components/CaseStart'
import { ReasonDialog } from '../components/ReasonDialog'
import { MarkingChip } from '../components/Marking'
import { WatchButton } from '../components/WatchButton'
import { PersonAvatar, Portrait } from '../components/PersonPhoto'
import { IdentityDocuments, highlights, personFacts, recordFacts } from '../components/IdentitySheet'
import { useEffect, useMemo, useRef, useState } from 'react'
import { api, intel, type Dossier as D, type TxRow } from '../api'
import EChart from '../components/EChart'
import GraphCanvas, { type GraphHandle } from '../components/GraphCanvas'
import { day, inr, num, titleCase, when, rupees } from '../lib/format'
import { TYPE_COLOURS, iconUri } from '../lib/icons'
import type { Nav } from './nav'
import DossierRecord from './DossierRecord'
import { colours, moneyColours } from '../lib/palette'

export default function Dossier({ id, nav }: { id: string | null; nav: Nav }) {
  const [d, setD] = useState<D | null>(null)
  const [err, setErr] = useState('')
  const [tab, setTab] = useState('overview')
  const [clear, setClear] = useState<Record<string, string>>({})
  const [unmasking, setUnmasking] = useState<string | null>(null)

  useEffect(() => {
    setD(null)
    setErr('')
    setClear({})
    if (!id) return
    intel.dossier(id).then(setD).catch((e) => setErr(e.message))
  }, [id, nav.tick])

  if (!id) return (
    <div className="canvas-message">
      <div>
        <NonIdealState icon="search" title="Open a dossier" description="Search above (Ctrl+K) for a name in any script, PAN, phone number, account number, vehicle, company or case number." />
        <CaseStart nav={nav} title="People in the active case" action="Open dossier" onPick={nav.openEntity} />
      </div>
    </div>
  )
  if (err) return <NonIdealState icon="lock" title="Access refused" description={`${err}. The refusal is in the audit log.`} />
  if (!d) return <div className="app-loading" role="status"><Spinner size={22} /><p>Loading the dossier…</p></div>

  const o = d.object
  const lead = d.lead
  const investigates = !!nav.me?.roles.some((r) => ['io', 'supervisor', 'analyst'].includes(r))
  const unmask = (key: string, reason: string) =>
    api.action<{ value: string }>('unmask', { object_id: o.id, property: key, reason }).then((r) => setClear((c) => ({ ...c, [key]: String(r.value) })))
  const createLead = () =>
    api
      .action('create_lead', { title: `Examine ${o.title}`, subject_id: o.id, note: lead ? `Ranked #${lead.rank} (${lead.role})` : 'From dossier' })
      .then(() => nav.setError('Lead added to the case board.'))
      .catch((e) => nav.setError(e.message))

  const kpis: [string, string][] = [
    ['Accounts', num(d.accounts.length + d.crypto.length)],
    ['Money in', inr(d.money.in_total)],
    ['Money out', inr(d.money.out_total)],
    ['Phones', num(d.phones.length)],
    ['Associates', num(d.associates.length)],
    ['Cases', num(d.incidents.length)],
    ['Alerts', num(d.alerts.length)],
    ['Trips', num(d.travel.length)],
  ]

  return (
    <div className="dossier">
      <header className={`dossier-head ${o.type === 'Person' ? 'person' : ''}`}>
        {o.type === 'Person'
          ? <Portrait photos={d.photos ?? []} name={o.title} />
          : <div className="avatar"><img src={iconUri(o.type, TYPE_COLOURS[o.type])} alt="" /></div>}
        <div className="dh-main">
          <div className="dh-kind">
            <span>{o.type === 'BankAccount' ? 'Bank account' : o.type}</span>
            <MarkingChip level={o.sensitivity} />
            {o.synthetic && <span className="synthetic-note" title="Every record in this demonstration is synthetic">Synthetic record</span>}
            <CopyReference id={o.id} />
          </div>
          <h1>{o.title}</h1>
          {o.props.name_native ? <div className="dh-native" lang="und">{String(o.props.name_native)}</div> : null}
          <dl className="dh-facts">
            {(o.type === 'Person' ? personFacts(o) : recordFacts(o)).map(([k, v]) => (
              <div key={k}><dt>{k}</dt><dd>{v}</dd></div>
            ))}
          </dl>
          {highlights(d).length > 0 && (
            <ul className="highlights" aria-label="What stands out">
              {highlights(d).map((h) => <li key={h.text} className={`hl ${h.tone}`} title={h.title ?? h.text}><Icon icon={h.icon} size={12} /><span>{h.text}</span></li>)}
            </ul>
          )}
        </div>
        <div className="dh-actions">
          {lead && (
            <div className="rank-block" title="Position among the people in this case's network, by the evidence listed under Lead assessment. Not a finding and not stored on the person.">
              <span>Rank in case</span>
              <b>{lead.rank}<small> of {lead.of}</small></b>
            </div>
          )}
          <div className="stack">
            <Button icon="graph" onClick={() => nav.openGraph(o.id)}>
              Network
            </Button>
            <Button icon="bank-account" onClick={() => nav.openTrace(o.id)} disabled={!d.accounts.length && o.type !== 'BankAccount'}>
              Follow the money
            </Button>
            <Button icon="link" onClick={() => nav.openConnect(o.id)}>
              Connections
            </Button>
            <Button icon="globe" onClick={() => nav.openGlobe(nav.caseId)}>
              Show on map
            </Button>
            {nav.caseId && investigates && <WatchButton objectId={o.id} label={o.title} nav={nav} />}
            {nav.caseId && (
              <Button icon="add-to-artifact" intent="primary" onClick={createLead} style={investigates ? undefined : { gridColumn: '1 / -1' }}>
                Add as lead
              </Button>
            )}
          </div>
        </div>
      </header>
      <IdentityDocuments d={d} clear={clear} onUnmask={setUnmasking} onOpen={nav.openEntity} />
      <div className="kpis">
        {kpis.map(([k, v]) => (
          <div key={k} className="kpi">
            <span>{k}</span>
            <b>{v}</b>
          </div>
        ))}
      </div>
      <ReasonDialog opened={!!unmasking} onClose={() => setUnmasking(null)} title="Unmask a protected value"
        label="Reason for unmasking" initial="Verification against KYC records for the case" confirm="Unmask"
        onConfirm={(reason) => unmasking ? unmask(unmasking, reason) : undefined} />
      <Tabs id="dossier-tabs" selectedTabId={tab} onChange={(t) => setTab(String(t))} renderActiveTabPanelOnly large={false} className="dossier-tabs">
        <Tab id="overview" title="Overview" panel={<Overview d={d} nav={nav} />} />
        <Tab
          id="record"
          title={`Record & patterns${d.findings?.length ? ` (${d.findings.length})` : ''}`}
          panel={<DossierRecord d={d} nav={nav} />}
        />
        <Tab id="money" title={`Financials (${d.accounts.length})`} panel={<Financials d={d} nav={nav} />} />
        <Tab id="network" title="Network" panel={<NetworkTab id={o.id} nav={nav} />} />
        <Tab id="comms" title={`Communications (${d.phones.length})`} panel={<Comms id={o.id} nav={nav} />} />
        <Tab id="assets" title="Travel & assets" panel={<Assets d={d} nav={nav} />} />
        <Tab id="timeline" title={`Timeline (${d.timeline.length})`} panel={<Timeline d={d} nav={nav} />} />
        <Tab id="sources" title="Sources" panel={<Sources d={d} nav={nav} />} />
      </Tabs>
    </div>
  )
}

/** Copies the record's reference for a report or an audit request; the reference itself is not screen content. */
function CopyReference({ id }: { id: string }) {
  const [done, setDone] = useState(false)
  return (
    <button className="text-link small" onClick={() => {
      navigator.clipboard?.writeText(id).then(() => { setDone(true); setTimeout(() => setDone(false), 1600) }).catch(() => undefined)
    }}>{done ? 'Reference copied' : 'Copy reference'}</button>
  )
}

function Card({ title, children, right, span }: { title: string; children: React.ReactNode; right?: React.ReactNode; span?: number }) {
  return (
    <section className="card" style={span ? { gridColumn: `span ${span}` } : undefined}>
      <h4 className="row" style={{ justifyContent: 'space-between' }}>
        <span>{title}</span>
        {right}
      </h4>
      {children}
    </section>
  )
}

function EntityLink({ id, label, nav, type }: { id?: string | null; label: string; nav: Nav; type?: string }) {
  if (!id) return <span>{label}</span>
  return (
    <button className="elink" onClick={() => nav.openEntity(id)}>
      {type && <span className="type-dot" style={{ background: TYPE_COLOURS[type] ?? 'var(--muted)' }} />}
      {label}
    </button>
  )
}

function Overview({ d, nav }: { d: D; nav: Nav }) {
  const lead = d.lead
  const monthly = d.money.monthly
  return (
    <div className="grid3">
      {lead && (
        <Card title={`Why ranked ${lead.rank} of ${lead.of} in this case`} span={2}>
          <p className="card-note">Assessed as <b>{lead.role.toLowerCase()}</b>, from the evidence in the case records:</p>
          <ul className="evidence">
            {lead.evidence.map((e, i) => (
              <li key={i}>{e}</li>
            ))}
          </ul>
          <div className="muted small">Linked to the case through: {lead.why_in_network}. The ranking orders leads by evidence for the investigating officer; it is not a finding.</div>
        </Card>
      )}
      <Card title={`Alerts (${d.alerts.length})`}>
        {d.alerts.length === 0 && <div className="muted small">No typology alerts on this entity or its accounts.</div>}
        {d.alerts.slice(0, 8).map((a) => (
          <div key={a.id} className={`alert-row sev-${a.severity}`}>
            <b>{titleCase(a.rule)}</b>
            <div className="small">{rupees(a.summary)}</div>
          </div>
        ))}
      </Card>
      <Card title={`Money flow · ${inr(d.money.in_total)} in / ${inr(d.money.out_total)} out`} span={lead ? 1 : 2}>
        {monthly.length ? (
          <EChart
            height={190}
            option={{
              grid: { left: 50, right: 10, top: 20, bottom: 24 },
              tooltip: { trigger: 'axis', valueFormatter: (v) => inr(Number(v)) },
              legend: { top: 0, right: 0, textStyle: { fontSize: 10 } },
              xAxis: { type: 'category', data: monthly.map((m) => m.month.slice(2)), axisLabel: { fontSize: 9 } },
              yAxis: { type: 'value', axisLabel: { formatter: (v: number) => inr(v), fontSize: 9 } },
              series: [
                { name: 'In', type: 'bar', data: monthly.map((m) => m.in), itemStyle: { color: moneyColours().in, borderRadius: [1, 1, 0, 0] } },
                { name: 'Out', type: 'bar', data: monthly.map((m) => -m.out), itemStyle: { color: moneyColours().out, borderRadius: [0, 0, 1, 1] } },
              ],
            }}
          />
        ) : (
          <div className="muted small">No transactions.</div>
        )}
      </Card>
      {d.flags && d.flags.length > 0 && (
        <Card title={`Behaviour flags (${d.flags.length})`} span={d.lead ? 1 : 2}>
          <div className="small muted" style={{ marginBottom: 6 }}>Conduct indicators to look into, not findings. No religion, caste, gender, age or political data is used.</div>
          {d.flags.map((f) => (
            <div key={f.id} className={`alert-row sev-${f.severity === 'info' ? 'low' : f.severity}`}>
              <b>{f.title}</b>
              <div className="small">{rupees(f.summary)}</div>
            </div>
          ))}
        </Card>
      )}
      <Card title={`Associates (${d.associates.length})`} right={<Button minimal small icon="link" title="Explain a connection" onClick={() => nav.openConnect(d.object.id)} />}>
        <div className="assoc">
          {d.associates.slice(0, 16).map((a) => (
            <button key={a.id} className="assoc-row" onClick={() => nav.openEntity(a.id)}>
              {a.type === 'Person' ? <PersonAvatar id={a.id} name={a.title} size={34} /> : <span className="avatar sm"><img src={iconUri(a.type)} alt="" /></span>}
              <span className="grow">
                <b>{a.title} {a.inferred && <span className="tag-inferred" title="inferred from shared behaviour">inferred</span>} {a.in_case && <span className="tag-in-case">in case</span>}</b>
                <span className="small muted" style={{ display: 'block' }}>{a.why.slice(0, 3).join(' · ')}</span>
              </span>
              <i className="strength" style={{ width: Math.min(60, a.strength * 8) }} />
            </button>
          ))}
        </div>
      </Card>
      <Card title={`Bank accounts (${d.accounts.length})`} span={2}>
        <HTMLTable compact className="data" style={{ width: '100%' }}>
          <thead>
            <tr>
              <th>Account</th>
              <th>Bank / branch</th>
              <th>Type</th>
              <th>Opened</th>
              <th style={{ textAlign: 'right' }}>In</th>
              <th style={{ textAlign: 'right' }}>Out</th>
              <th>Flags</th>
            </tr>
          </thead>
          <tbody>
            {d.accounts.map((a) => (
              <tr key={a.id} className="clickable" {...activate(() => nav.openEntity(a.id))}>
                <td className="mono">{a.title}</td>
                <td>
                  {String(a.props.bank ?? '').replace(' (synthetic)', '')}
                  <div className="small muted">{String(a.props.branch ?? '')}</div>
                </td>
                <td>
                  {String(a.props.account_type ?? '')} {a.relations.includes('signatory_of') && <Tag minimal>signatory</Tag>}
                </td>
                <td>{String(a.props.opened_on ?? '')}</td>
                <td style={{ textAlign: 'right' }}>{inr(a.summary.in_total)}</td>
                <td style={{ textAlign: 'right' }}>{inr(a.summary.out_total)}</td>
                <td>
                  {a.alerts.map((x) => (
                    <Tag key={x.id} minimal intent={x.severity === 'high' ? 'danger' : 'warning'} style={{ marginRight: 3 }}>
                      {titleCase(x.rule)}
                    </Tag>
                  ))}
                </td>
              </tr>
            ))}
          </tbody>
        </HTMLTable>
      </Card>
      <Card title="Contact & addresses">
        {d.phones.map((p) => (
          <div key={p.id} className="kv-row">
            <EntityLink id={p.id} label={p.title} nav={nav} type="Phone" />
            <span className="muted small">
              {String(p.props.operator ?? '')} · {String(p.props.subscriber_name ?? '')}
            </span>
          </div>
        ))}
        {d.object.props.email ? <div className="kv-row">{String(d.object.props.email)}</div> : null}
        {d.locations.map((l) => (
          <div key={l.id} className="kv-row small">
            📍 {String(l.props.address ?? l.title)}
          </div>
        ))}
        {d.devices.map((x) => (
          <div key={x.id} className="kv-row small">
            Handset <b>{String(x.props.model ?? '')}</b> · IMEI <span className="mono">{x.title}</span>
          </div>
        ))}
      </Card>
      <Card title={`Companies (${d.organisations.length})`}>
        {d.organisations.length === 0 && <div className="muted small">None.</div>}
        {d.organisations.map((x) => (
          <div key={x.id} className="kv-row">
            <EntityLink id={x.id} label={x.title} nav={nav} type="Organisation" />
            <span className="small muted">
              {x.relations.map(titleCase).join(', ')} · {String(x.props.kind ?? '')}
            </span>
            {x.alerts.slice(0, 2).map((a) => (
              <Tag key={a.id} minimal intent="danger">
                {titleCase(a.rule)}
              </Tag>
            ))}
          </div>
        ))}
        {d.people.length > 0 && d.object.type !== 'Person' && (
          <>
            <h5 className="muted">People</h5>
            {d.people.map((x) => (
              <div key={x.id} className="kv-row">
                <EntityLink id={x.id} label={x.title} nav={nav} type="Person" />
                <span className="small muted">{x.relations.map(titleCase).join(', ')}</span>
              </div>
            ))}
          </>
        )}
      </Card>
      <Card title={`Cases & records (${d.incidents.length})`}>
        {d.incidents.length === 0 && <div className="muted small">Not named in any case record.</div>}
        {d.incidents.map((x) => (
          <button key={x.id} className="kv-row" onClick={() => nav.openEntity(x.id)}>
            <Tag minimal>{String(x.props.agency ?? '')}</Tag>
            <span className="mono small">{x.title}</span>
            <span className="small muted" style={{ flexBasis: '100%' }}>
              {x.relations.map(titleCase).join(', ')} · {day(String(x.props.occurred_at ?? ''))} · {String((x.props.sections as string[] | undefined)?.join(', ') ?? '')}
            </span>
          </button>
        ))}
      </Card>
      <Card title="Assets">
        {(d.firearms ?? []).filter((x) => x.props.status === 'licensed').map((x) => (
          <div key={x.id} className="kv-row asset-key">
            <EntityLink id={x.id} label={`Licensed ${String(x.props.calibre ?? '')} ${String(x.props.kind ?? 'firearm')}`} nav={nav} type="Firearm" />
            <span className="small muted">Licence <b>{String(x.props.licence_no ?? '')}</b>{x.props.licence_valid_until ? ` · valid until ${day(String(x.props.licence_valid_until))}` : ''}</span>
          </div>
        ))}
        {[...d.vehicles, ...d.properties, ...d.crypto].map((x) => (
          <div key={x.id} className="kv-row">
            <EntityLink id={x.id} label={x.title} nav={nav} type={x.type} />
            <span className="small muted">
              {String(x.props.make ?? x.props.kind ?? x.props.exchange ?? '')} {x.props.value ? <>· <b>{inr(Number(x.props.value))}</b></> : ''}
            </span>
          </div>
        ))}
        {!d.vehicles.length && !d.properties.length && !d.crypto.length && !(d.firearms ?? []).length && <div className="muted small">No registered assets.</div>}
      </Card>
    </div>
  )
}

function Financials({ d, nav }: { d: D; nav: Nav }) {
  const [rows, setRows] = useState<TxRow[]>([])
  const [total, setTotal] = useState(0)
  const [acct, setAcct] = useState('')
  const [min, setMin] = useState('0')
  const [page, setPage] = useState(0)
  const id = d.object.id
  useEffect(() => {
    intel
      .transactions(id, { account: acct || undefined, min_amount: Number(min) || 0, limit: 100, offset: page * 100 })
      .then((r) => {
        setRows(r.rows)
        setTotal(r.total)
      })
      .catch((e) => nav.setError(e.message))
  }, [id, acct, min, page, nav])
  const monthly = d.object.type === 'BankAccount' && d.account_summary ? d.account_summary.monthly : d.money.monthly
  return (
    <div className="stack">
      <div className="row">
        <select value={acct} onChange={(e) => (setAcct(e.target.value), setPage(0))} aria-label="Account">
          <option value="">All accounts</option>
          {d.accounts.map((a) => (
            <option key={a.id} value={a.id}>
              {a.title} · {String(a.props.bank ?? '').replace(' (synthetic)', '')}
            </option>
          ))}
        </select>
        <span className="muted small">Min ₹</span>
        <InputGroup small value={min} onChange={(e) => (setMin(e.target.value), setPage(0))} style={{ width: 110 }} />
        <Button small icon="arrow-right" onClick={() => nav.openTrace(acct || id)}>
          Trace onward
        </Button>
        <span className="muted small grow" style={{ textAlign: 'right' }}>
          {num(total)} transactions
        </span>
      </div>
      <EChart
        height={170}
        option={{
          grid: { left: 56, right: 10, top: 14, bottom: 22 },
          tooltip: { trigger: 'axis', valueFormatter: (v) => inr(Math.abs(Number(v))) },
          xAxis: { type: 'category', data: monthly.map((m) => m.month) },
          yAxis: { type: 'value', axisLabel: { formatter: (v: number) => inr(v) } },
          series: [
            { name: 'In', type: 'bar', stack: 'a', data: monthly.map((m) => m.in), itemStyle: { color: moneyColours().in, borderRadius: [1, 1, 0, 0] } },
            { name: 'Out', type: 'bar', stack: 'a', data: monthly.map((m) => -m.out), itemStyle: { color: moneyColours().out, borderRadius: [0, 0, 1, 1] } },
          ],
        }}
      />
      <HTMLTable compact striped className="data" style={{ width: '100%' }}>
        <thead>
          <tr>
            <th>Date</th>
            <th></th>
            <th style={{ textAlign: 'right' }}>Amount</th>
            <th>Channel</th>
            <th>Narration</th>
            <th>Counterparty</th>
            <th>Ref</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id} className={r.flagged ? 'flagged' : ''}>
              <td className="mono">{when(r.ts)}</td>
              <td>{r.direction === 'in' ? <Tag minimal intent="success">IN</Tag> : <Tag minimal intent="danger">OUT</Tag>}</td>
              <td style={{ textAlign: 'right' }} className="mono">
                {inr(r.amount, false)}
              </td>
              <td>
                {r.channel}
                {r.country && r.country !== 'IN' ? <Tag minimal intent="warning">{r.country}</Tag> : null}
              </td>
              <td className="small">{r.narration}</td>
              <td>
                {r.counterparty_holder ? <EntityLink id={r.counterparty_holder} label={r.counterparty} nav={nav} /> : r.counterparty}
                {r.flagged && <Tag minimal intent="danger" style={{ marginLeft: 4 }}>flagged</Tag>}
              </td>
              <td className="mono small muted">{r.ref}</td>
            </tr>
          ))}
        </tbody>
      </HTMLTable>
      <div className="row">
        <Button small disabled={page === 0} onClick={() => setPage(page - 1)}>
          Newer
        </Button>
        <Button small disabled={(page + 1) * 100 >= total} onClick={() => setPage(page + 1)}>
          Older
        </Button>
      </div>
    </div>
  )
}

function NetworkTab({ id, nav }: { id: string; nav: Nav }) {
  const g = useRef<GraphHandle>(null)
  useEffect(() => {
    api
      .graph(id, 1)
      .then((r) =>
        g.current?.add(
          r.nodes.map((n) => ({ id: n.id, type: n.type, label: n.label, group: n.group, count: n.count ?? undefined, seed: n.id === id })),
          r.edges.map((e) => ({ id: e.id, source: e.source, target: e.target, type: e.type, amount: (e.props?.total as number) ?? null, count: (e.props?.count as number) ?? null, status: e.status })),
        ),
      )
      .catch((e) => nav.setError(e.message))
  }, [id, nav])
  return (
    <div style={{ height: 'calc(100vh - 330px)', minHeight: 420 }} className="card flush">
      <GraphCanvas ref={g} onOpen={nav.openEntity} />
    </div>
  )
}

function Comms({ id, nav }: { id: string; nav: Nav }) {
  const [c, setC] = useState<Awaited<ReturnType<typeof intel.calls>> | null>(null)
  useEffect(() => {
    intel.calls(id).then(setC).catch((e) => nav.setError(e.message))
  }, [id, nav])
  if (!c) return <Spinner />
  if (!c.total) return <div className="muted">No call records held for this entity.</div>
  return (
    <div className="grid3">
      <Card title={`Top contacts · ${num(c.total)} calls on ${c.numbers.join(', ')}`} span={2}>
        <HTMLTable compact className="data" style={{ width: '100%' }}>
          <thead>
            <tr>
              <th>Number</th>
              <th>Subscriber / owner</th>
              <th style={{ textAlign: 'right' }}>Calls</th>
              <th style={{ textAlign: 'right' }}>Minutes</th>
              <th>First</th>
              <th>Last</th>
            </tr>
          </thead>
          <tbody>
            {c.contacts.map((x) => (
              <tr key={x.number}>
                <td className="mono">{x.number}</td>
                <td>{x.owner_id ? <EntityLink id={x.owner_id} label={x.owner ?? ''} nav={nav} type="Person" /> : <span className={x.number.startsWith('+') ? 'err' : 'muted'}>{x.owner ?? 'unknown'}</span>}</td>
                <td style={{ textAlign: 'right' }}>{x.calls}</td>
                <td style={{ textAlign: 'right' }}>{Math.round(x.seconds / 60)}</td>
                <td>{day(x.first)}</td>
                <td>{day(x.last)}</td>
              </tr>
            ))}
          </tbody>
        </HTMLTable>
      </Card>
      <Card title="Calls by hour of day">
        <EChart
          height={200}
          option={{
            grid: { left: 30, right: 6, top: 10, bottom: 22 },
            xAxis: { type: 'category', data: c.hourly.map((_, i) => String(i)) },
            yAxis: { type: 'value' },
            series: [{ type: 'bar', data: c.hourly, itemStyle: { color: colours().slate, borderRadius: [1, 1, 0, 0] } }],
          }}
        />
        {c.towers.length > 0 && (
          <>
            <h5 className="muted">Cell towers</h5>
            {c.towers.map((t) => (
              <div key={t.id} className="small">
                <span className="mono">{t.id}</span> {t.label} · {t.hits} hits
              </div>
            ))}
          </>
        )}
      </Card>
    </div>
  )
}

function Assets({ d, nav }: { d: D; nav: Nav }) {
  return (
    <div className="grid3">
      <Card title={`Travel (${d.travel.length})`} span={2}>
        <HTMLTable compact className="data" style={{ width: '100%' }}>
          <thead>
            <tr>
              <th>Date</th>
              <th>From</th>
              <th>To</th>
              <th>PNR</th>
            </tr>
          </thead>
          <tbody>
            {d.travel.map((t) => (
              <tr key={t.id} className={t.to_country !== 'IN' || t.from_country !== 'IN' ? 'flagged' : ''}>
                <td>{when(t.ts)}</td>
                <td>
                  {t.from_city} <span className="muted small">{t.from_country}</span>
                </td>
                <td>
                  {t.to_city} <span className="muted small">{t.to_country}</span>
                </td>
                <td className="mono">{t.pnr}</td>
              </tr>
            ))}
          </tbody>
        </HTMLTable>
      </Card>
      <Card title="Vehicles, property, firearms, crypto">
        {(d.firearms ?? []).map((x) => (
          <div key={x.id} className="kv-row">
            <EntityLink id={x.id} label={`${String(x.props.make ?? 'Firearm')} ${String(x.props.calibre ?? '')} ${String(x.props.kind ?? '')}`} nav={nav} type="Firearm" />
            <div className="small muted">Serial {x.title} · licence {String(x.props.licence_no ?? '')} · {String(x.props.licensing_authority ?? '')}</div>
          </div>
        ))}
        {[...d.vehicles, ...d.properties, ...d.crypto].map((x) => (
          <div key={x.id} className="kv-row">
            <EntityLink id={x.id} label={x.title} nav={nav} type={x.type} />
            <div className="small muted">
              {String(x.props.make ?? x.props.kind ?? x.props.chain ?? '')} {x.props.value ? `· ${inr(Number(x.props.value))}` : ''} {x.props.registered_on ? `· ${x.props.registered_on}` : ''}
            </div>
          </div>
        ))}
      </Card>
    </div>
  )
}

const TL_ICON: Record<string, IconName> = { case: 'take-action', travel: 'airplane', asset: 'home', account: 'bank-account', money_in: 'arrow-down', money_out: 'arrow-up', alert: 'warning-sign' }

function Timeline({ d, nav }: { d: D; nav: Nav }) {
  const byMonth = useMemo(() => {
    const g: Record<string, typeof d.timeline> = {}
    for (const e of d.timeline) (g[e.at.slice(0, 7)] ??= []).push(e)
    return Object.entries(g)
  }, [d])
  return (
    <div className="timeline">
      {byMonth.map(([m, evs]) => (
        <div key={m}>
          <div className="tl-month">{new Date(`${m}-01T00:00:00`).toLocaleDateString('en-IN', { month: 'long', year: 'numeric' })}</div>
          {evs.map((e, i) => (
            <button key={i} className={`tl-item tl-${e.kind}`} disabled={!e.id} onClick={() => e.id && nav.openEntity(e.id)}>
              <span className="tl-icon"><Icon icon={TL_ICON[e.kind] ?? 'dot'} size={13} /></span>
              <span className="mono small muted">{when(e.at)}</span>
              <b>{rupees(e.title)}</b>
              <span className="small muted">{rupees(e.detail)}</span>
            </button>
          ))}
        </div>
      ))}
    </div>
  )
}

function Sources({ d, nav }: { d: D; nav: Nav }) {
  return (
    <div className="grid3">
      <Card title={`Property provenance (${d.provenance.length})`} span={2}>
        <HTMLTable compact className="data" style={{ width: '100%' }}>
          <thead>
            <tr>
              <th>Property</th>
              <th>Source system</th>
              <th>Record</th>
              <th>Ingested</th>
              <th>Confidence</th>
            </tr>
          </thead>
          <tbody>
            {d.provenance.map((p, i) => (
              <tr key={i}>
                <td>{titleCase(p.prop)}</td>
                <td>
                  <span className="chip src">{p.source}</span>
                </td>
                <td className="mono small">{p.record}</td>
                <td className="small">{when(p.ingested_at)}</td>
                <td>{p.confidence}</td>
              </tr>
            ))}
          </tbody>
        </HTMLTable>
      </Card>
      <Card title={`Fused source records (${d.fused_records.length})`}>
        <div className="muted small" style={{ marginBottom: 6 }}>
          Records from other systems that entity resolution linked to this person (never merged; each stays a separate record).
        </div>
        {d.fused_records.map((r) => (
          <button key={r.id} className="kv-row" onClick={() => nav.openEntity(r.id)}>
            <b>{r.title}</b> {r.props.name_native ? <span className="muted">{String(r.props.name_native)}</span> : null}
            <span className="small" style={{ flexBasis: '100%' }}>
              {r.sources.map((s) => (
                <span key={s} className="chip src">
                  {s}
                </span>
              ))}
            </span>
          </button>
        ))}
      </Card>
    </div>
  )
}

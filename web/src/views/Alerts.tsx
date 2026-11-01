import { HTMLSelect, NonIdealState, Spinner, Tag } from '@blueprintjs/core'
import { Button } from '../components/Button'
import { useEffect, useState } from 'react'
import { intel, type Alert } from '../api'
import { activate } from '../lib/a11y'
import { inr, titleCase, when, rupees } from '../lib/format'
import type { Nav } from './nav'

export default function Alerts({ nav }: { nav: Nav }) {
  const [rule, setRule] = useState('')
  const [sev, setSev] = useState('')
  const [data, setData] = useState<{ alerts: Alert[]; rules: { rule: string; n: number }[] } | null>(null)
  const [err, setErr] = useState('')
  const [sel, setSel] = useState<Alert | null>(null)
  useEffect(() => {
    setErr('')
    intel.alerts({ rule: rule || undefined, severity: sev || undefined }).then((d) => (setData(d), setSel(d.alerts[0] ?? null))).catch((e) => (setErr(e.message), setData({ alerts: [], rules: [] })))
  }, [rule, sev, nav])
  const total = data?.rules.reduce((a, r) => a + r.n, 0)
  return (
    <div className="workspace" style={{ gridTemplateColumns: '260px minmax(0, 1fr) 380px' }}>
      <aside className="panel">
        <div className="section">
          <h3>Typologies</h3>
          <button className={`rule-row ${rule === '' ? 'on' : ''}`} aria-pressed={rule === ''} onClick={() => setRule('')}>
            <span>All typologies</span><span>{total ?? ''}</span>
          </button>
          {data?.rules.map((r) => (
            <button key={r.rule} className={`rule-row ${rule === r.rule ? 'on' : ''}`} aria-pressed={rule === r.rule} onClick={() => setRule(r.rule)}>
              <span>{titleCase(r.rule)}</span><span>{r.n}</span>
            </button>
          ))}
        </div>
        <div className="section">
          <h3>Severity</h3>
          <HTMLSelect value={sev} onChange={(e) => setSev(e.target.value)} fill aria-label="Severity">
            <option value="">All severities</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
          </HTMLSelect>
        </div>
      </aside>
      <main className="canvas scroll" style={{ background: 'var(--sheet)' }}>
        {!data && <div className="empty"><Spinner size={20} /></div>}
        {err && <NonIdealState icon="lock" title="Alerts are not available" description={err} />}
        {data && !err && !data.alerts.length && <NonIdealState icon="tick-circle" title="No alerts" description="Nothing matches these filters in your case and jurisdiction." />}
        {data && data.alerts.length > 0 && (
          <table className="data">
            <thead>
              <tr>
                <th>Score</th>
                <th>Typology</th>
                <th>Subject</th>
                <th>Finding</th>
                <th className="numeric">Amount</th>
              </tr>
            </thead>
            <tbody>
              {data.alerts.map((a) => (
                <tr key={a.id} className={`clickable ${sel?.id === a.id ? 'selrow' : ''}`} aria-current={sel?.id === a.id ? 'true' : undefined} {...activate(() => setSel(a))}>
                  <td><Tag minimal intent={a.severity === 'high' ? 'danger' : 'warning'}>{Math.round(a.score)}</Tag></td>
                  <td>{titleCase(a.rule)}</td>
                  <td>
                    <b>{a.holder || a.subject}</b>
                    <div className="small muted">{a.subject_type}{a.holder ? ` · ${a.subject}` : ''}</div>
                  </td>
                  <td className="small">{rupees(a.summary)}</td>
                  <td className="numeric">{inr(a.amount)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </main>
      <aside className="panel right">
        {!sel && <div className="panel-empty"><h3>No alert selected</h3><p>Choose an alert to see the rule it met and where to go next.</p></div>}
        {sel && (
          <div className="section">
            <Tag minimal intent={sel.severity === 'high' ? 'danger' : 'warning'}>{titleCase(sel.severity)} · score {Math.round(sel.score)}</Tag>
            <h2>{titleCase(sel.rule)}</h2>
            {sel.details?.rule_text && <p className="muted small">{sel.details.rule_text}</p>}
            <p>{rupees(sel.summary)}</p>
            <dl className="kv">
              <dt>Subject</dt><dd><b>{sel.holder || sel.subject}</b> <span className="muted">{sel.subject_type}</span></dd>
              <dt>Amount</dt><dd>{inr(sel.amount)}</dd>
              {sel.window_start && <><dt>Window from</dt><dd>{when(sel.window_start)}</dd></>}
              <dt>Evidence</dt><dd>{sel.details?.evidence_txns.length ?? 0} transactions referenced</dd>
            </dl>
            <div className="row" style={{ marginTop: 16 }}>
              <Button icon="person" onClick={() => nav.openEntity(sel.holder_id || sel.subject_id)}>Open dossier</Button>
              <Button icon="bank-account" onClick={() => nav.openTrace(sel.subject_id)}>Trace funds</Button>
              <Button icon="graph" onClick={() => nav.openGraph(sel.holder_id || sel.subject_id)}>Network</Button>
            </div>
          </div>
        )}
      </aside>
    </div>
  )
}

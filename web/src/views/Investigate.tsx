import { Icon, NonIdealState, Spinner, Tag } from '@blueprintjs/core'
import { Button } from '../components/Button'
import { useEffect, useRef, useState } from 'react'
import { api, intel, type Dossier } from '../api'
import GraphCanvas, { type GraphHandle } from '../components/GraphCanvas'
import { PersonAvatar } from '../components/PersonPhoto'
import { inr, titleCase, rupees } from '../lib/format'
import type { Nav } from './nav'

// Gotham-style link-analysis workspace: canvas in the middle, selection helper on the right.
export default function Investigate({ root, nav }: { root: string | null; nav: Nav }) {
  const g = useRef<GraphHandle>(null)
  const [sel, setSel] = useState<string | null>(null)
  const [d, setD] = useState<Dossier | null>(null)
  const [loading, setLoading] = useState(false)
  const [graphError, setGraphError] = useState('')
  const [retry, setRetry] = useState(0)

  useEffect(() => {
    let current = true
    setGraphError('')
    g.current?.clear()
    if (root) {
      setLoading(true)
      api
        .graph(root, 1)
        .then((r) =>
          current && g.current?.add(
            r.nodes.map((n) => ({ id: n.id, type: n.type, label: n.label, group: n.group, count: n.count ?? undefined, seed: n.id === root })),
            r.edges.map((e) => ({ id: e.id, source: e.source, target: e.target, type: e.type, amount: (e.props?.total as number) ?? null, count: (e.props?.count as number) ?? null, status: e.status })),
          ),
        )
        .catch((e) => { if (current) setGraphError(e.message) })
        .finally(() => { if (current) setLoading(false) })
    } else if (nav.caseId) {
      setLoading(true)
      intel
        .network(nav.caseId)
        .then((r) => { if (current) g.current?.add(r.nodes, r.edges.map((e) => ({ ...e, amount: e.amount ?? null, count: e.count ?? null }))) })
        .catch((e) => { if (current) setGraphError(e.message) })
        .finally(() => { if (current) setLoading(false) })
    }
    return () => { current = false }
  }, [root, nav.caseId, nav.tick, retry])

  useEffect(() => {
    let current = true
    setD(null)
    if (sel && !sel.startsWith('group:')) intel.dossier(sel).then((result) => { if (current) setD(result) }).catch(() => { if (current) setD(null) })
    return () => { current = false }
  }, [sel])

  return (
    <div className="investigate-view">
      <div className="investigate-heading"><div><h1>Network analysis</h1><p>Explore relationships, inspect records and trace connections.</p></div><Button icon="refresh" onClick={() => setRetry((n) => n + 1)} loading={loading}>Reload</Button></div>
    <div className="workspace">
      <main className="canvas">
        <GraphCanvas ref={g} onSelect={(id) => setSel(id)} onOpen={nav.openEntity} />
        {loading && <div className="canvas-loading" role="status"><Spinner size={18} />Loading available connections…</div>}
        {graphError && <div className="canvas-empty" role="alert"><Icon icon="offline" size={26} /><h3>Network unavailable</h3><p>{graphError}</p><Button onClick={() => setRetry((n) => n + 1)}>Try again</Button></div>}
        {!root && !nav.caseId && <div className="canvas-empty"><NonIdealState icon="graph" title="Select a case to begin" description="Choose an active case above, or open the network from a record’s dossier." /></div>}
      </main>
      <aside className="panel right">
        <div className="inspector-heading"><Icon icon="properties" size={14} />Record inspector</div>
        {!d && <div className="inspector-empty"><Icon icon="select" size={28} /><h3>{sel ? 'Record selected' : 'Inspect a connection'}</h3><p>{sel ? 'Loading available details. Grouped or restricted records may not have a dossier.' : 'Select a record in the network to view its details, evidence and related records.'}</p><div className="inspector-shortcuts"><div><span>Select record</span><kbd>Click</kbd></div><div><span>Select multiple</span><kbd>Shift + click</kbd></div><div><span>Expand connections</span><kbd>Double-click</kbd></div><div><span>Open dossier</span><kbd>Right-click</kbd></div></div></div>}
        {d && (
          <div className="section">
            <div className="row">
              <Tag minimal>{d.object.type}</Tag>
              {d.lead && (
                <Tag minimal>
                  {Math.round(d.lead.score)} · {d.lead.role}
                </Tag>
              )}
            </div>
            <div className="inspector-person">
              {d.object.type === 'Person' && <PersonAvatar id={d.object.id} name={d.object.title} size={56} />}
              <h2>{d.object.title}</h2>
            </div>
            <div className="small muted">{[d.object.props.occupation, d.object.props.city, d.object.props.kind, d.object.props.bank].filter(Boolean).map(String).join(' · ')}</div>
            <div className="docs" style={{ margin: '8px 0' }}>
              {d.documents.slice(0, 4).map((x) => (
                <span key={x.key} className="doc">
                  <b>{x.label}</b> <span className="mono">{x.value}</span>
                </span>
              ))}
            </div>
            <dl className="measure-list">
              <dt>Money in</dt><dd>{inr(d.money.in_total)}</dd>
              <dt>Money out</dt><dd>{inr(d.money.out_total)}</dd>
            </dl>
            {d.lead && (
              <ul className="evidence small">
                {d.lead.evidence.slice(0, 6).map((e, i) => (
                  <li key={i}>{e}</li>
                ))}
              </ul>
            )}
            {d.alerts.slice(0, 4).map((a) => (
              <div key={a.id} className={`alert-row sev-${a.severity}`}>
                <b>{titleCase(a.rule)}</b>
                <div className="small">{rupees(a.summary)}</div>
              </div>
            ))}
            <div className="row" style={{ marginTop: 8 }}>
              <Button small icon="person" onClick={() => nav.openEntity(d.object.id)}>
                Full dossier
              </Button>
              <Button small icon="bank-account" onClick={() => nav.openTrace(d.object.id)}>
                Follow money
              </Button>
            </div>
            <h4>Top associates</h4>
            {d.associates.slice(0, 8).map((a) => (
              <button key={a.id} className="kv-row small" onClick={() => nav.openEntity(a.id)}>
                <b>{a.title}</b> <span className="muted">{a.why.slice(0, 2).join(' · ')}</span>
              </button>
            ))}
          </div>
        )}
      </aside>
    </div>
    </div>
  )
}

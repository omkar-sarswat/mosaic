import { HTMLSelect, InputGroup, Spinner } from '@blueprintjs/core'
import { Button } from '../components/Button'
import GraphCanvas, { type GraphHandle } from '../components/GraphCanvas'
import { useEffect, useRef, useState } from 'react'
import { api, type GEdge, type Graph } from '../api'
import ObjectPanel from './ObjectPanel'
import { type Shared, TYPE_COLOURS } from './shared'
import { evidenceColours } from '../lib/palette'

const EVIDENCE: Record<GEdge['evidence'], string> = evidenceColours()

export default function GraphView(shared: Shared & { root: string | null; setRoot: (id: string | null) => void }) {
  const canvas = useRef<GraphHandle>(null)
  const [graph, setGraph] = useState<Graph | null>(null)
  const [depth, setDepth] = useState(1)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const [pathA, setPathA] = useState<string | null>(null)
  const [pathMsg, setPathMsg] = useState('')
  const [reason, setReason] = useState('')
  const [reqMsg, setReqMsg] = useState('')
  const [pending, setPending] = useState<Awaited<ReturnType<typeof api.expansions>>>([])
  const { root, setSelected, selected } = shared

  useEffect(() => {
    if (!root) return
    setBusy(true)
    setErr('')
    api
      .graph(root, depth)
      .then(setGraph)
      .catch((e) => {
        setGraph(null)
        setErr(e.message)
      })
      .finally(() => setBusy(false))
  }, [root, depth, shared.tick])

  useEffect(() => {
    if (shared.me?.roles.includes('supervisor')) api.expansions().then(setPending).catch(() => setPending([]))
  }, [shared.me, shared.tick])

  useEffect(() => {
    canvas.current?.clear()
    if (!graph) return
    canvas.current?.add(
      graph.nodes.map((node) => ({ ...node, seed: node.id === graph.root, count: node.count ?? undefined })),
      graph.edges,
    )
  }, [graph])

  const findPath = () => {
    if (!pathA || !selected || pathA === selected) return
    setPathMsg('')
    api
      .path(pathA, selected)
      .then((p) => {
        canvas.current?.highlight(p.nodes.map((node) => node.id), p.edges.map((edge) => edge.id))
        const missing = p.nodes.filter((node) => !graph?.nodes.some((visible) => visible.id === node.id)).length
        setPathMsg(`${p.hops} hops: ${p.nodes.map((n) => n.label).join(' → ')}${missing ? ` (${missing} node(s) outside current view)` : ''}`)
      })
      .catch((e) => setPathMsg(e.message))
  }

  const requestExpansion = () =>
    api
      .action<{ request_id: string }>('request_expansion', { depth: depth + 1, reason })
      .then((r) => setReqMsg(`Requested (${r.request_id}). A different supervisor must approve.`))
      .catch((e) => setReqMsg(e.message))

  const approve = (id: string) => api.action('approve_expansion', { request_id: id }).then(shared.refresh).catch((e) => shared.setError(e.message))

  const typeCounts = graph ? Object.entries(graph.nodes.reduce<Record<string, number>>((a, n) => ({ ...a, [n.type]: (a[n.type] ?? 0) + (n.count ?? 1) }), {})) : []
  const brokers = graph ? [...graph.nodes].filter((n) => n.broker > 0.05 && !n.hub).sort((a, b) => b.broker - a.broker).slice(0, 5) : []

  return (
    <div className="workspace">
      <aside className="panel">
        <div className="section">
          <h3>Auto-graph</h3>
          {!root && <p className="muted">Open any object from Explore or Map with “Open graph”. Double-click a node to re-centre.</p>}
          {root && (
            <div className="row">
              <span className="small muted">Depth</span>
              <HTMLSelect value={depth} onChange={(e) => setDepth(Number(e.target.value))}>
                {[1, 2, 3].map((d) => <option key={d} value={d} disabled={d > (shared.activeCase?.max_depth ?? 1)}>{d}{d > (shared.activeCase?.max_depth ?? 1) ? ' (needs approval)' : ''}</option>)}
              </HTMLSelect>
              {busy && <Spinner size={16} />}
            </div>
          )}
          {err && <p className="err small">{err}</p>}
        </div>
        {graph && depth >= (shared.activeCase?.max_depth ?? 1) && depth < 3 && shared.caseId && (
          <div className="section stack">
            <h3>Wider network</h3>
            <p className="small muted">Going to depth {depth + 1} reaches second-degree contacts. It needs a supervisor’s approval (two-person rule).</p>
            <InputGroup small value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Why the wider network is necessary" />
            <Button small onClick={requestExpansion} disabled={reason.trim().length < 5}>Request depth {depth + 1}</Button>
            {reqMsg && <div className="small">{reqMsg}</div>}
          </div>
        )}
        {pending.length > 0 && (
          <div className="section">
            <h3>Pending approvals</h3>
            {pending.map((p) => (
              <div key={p.id} className="small stack" style={{ marginBottom: 8 }}>
                <div><b>{p.case_id}</b> depth {p.depth} · by {p.requested_by}</div>
                <div className="muted">{p.reason}</div>
                <Button small intent="success" onClick={() => approve(p.id)}>Approve</Button>
              </div>
            ))}
          </div>
        )}
        {graph && (
          <>
            <div className="section">
              <h3>In view</h3>
              {typeCounts.map(([t, n]) => <div key={t} className="small"><span className="type-dot" style={{ background: TYPE_COLOURS[t] ?? 'var(--muted)' }} />{t} · {n}</div>)}
            </div>
            {graph.hidden.length > 0 && (
              <div className="section">
                <h3>Not shown</h3>
                {graph.hidden.map((h) => <div key={h.type + h.reason} className="small"><b>{h.count}</b> {h.type}: <span className="muted">{h.reason}</span></div>)}
              </div>
            )}
            {brokers.length > 0 && (
              <div className="section">
                <h3>Brokers (betweenness)</h3>
                <p className="small muted">Objects that connect otherwise separate parts of this view. A lead, not a verdict.</p>
                {brokers.map((b) => <button key={b.id} className="rule-row small" onClick={() => setSelected(b.id)}><span><span className="type-dot" style={{ background: TYPE_COLOURS[b.type] }} />{b.label}</span><span>{b.broker.toFixed(2)}</span></button>)}
              </div>
            )}
            <div className="section stack">
              <h3>Path finder</h3>
              <div className="small">From: {pathA ? graph.nodes.find((n) => n.id === pathA)?.label ?? pathA : <span className="muted">select a node, then “Set start”</span>}</div>
              <div className="row">
                <Button small disabled={!selected} onClick={() => setPathA(selected)}>Set start</Button>
                <Button small intent="primary" disabled={!pathA || !selected || pathA === selected} onClick={findPath}>Path to selected</Button>
              </div>
              {pathMsg && <div className="small">{pathMsg}</div>}
            </div>
          </>
        )}
      </aside>

      <main className="canvas">
        <GraphCanvas ref={canvas} onSelect={(id) => setSelected(id)} onOpen={shared.openGraph} onExpand={shared.setRoot} />
        {graph && (
          <div className="legend">
            <div><span className="ln" style={{ background: EVIDENCE.corroborated }} />two independent sources or human-confirmed</div>
            <div><span className="ln" style={{ background: EVIDENCE.single }} />one source</div>
            <div><span className="ln" style={{ background: EVIDENCE.suggested, height: 0, borderTop: `3px dotted ${EVIDENCE.suggested}` }} />machine-suggested (entity resolution)</div>
            <div className="muted">Node size = broker score · ring = in case scope</div>
          </div>
        )}
        {!graph && !busy && <div className="empty" style={{ paddingTop: 120 }}>No graph yet.</div>}
      </main>

      <aside className="panel right">
        <ObjectPanel id={selected} shared={shared} onSelect={setSelected} />
      </aside>
    </div>
  )
}

import { Callout, NonIdealState, Spinner, Tag } from '@blueprintjs/core'
import { Button } from '../components/Button'
import { CaseStart } from '../components/CaseStart'
import { useEffect, useRef, useState } from 'react'
import { api, intel, type Associate, type ConnectPath, type Flag, type ObjSummary, type WhyLinked } from '../api'
import Omnibox from '../components/Omnibox'
import GraphCanvas, { type GraphHandle } from '../components/GraphCanvas'
import { titleCase, rupees } from '../lib/format'
import type { Nav } from './nav'

// Connections: who is associated with a person and why, and the chain of records between two entities.
export default function Connect({ nav, seed }: { nav: Nav; seed: string | null }) {
  const [a, setA] = useState<string | null>(seed)
  const [b, setB] = useState<string | null>(null)
  const [obj, setObj] = useState<ObjSummary | null>(null)
  const [assoc, setAssoc] = useState<{ associates: Associate[]; note: string } | null>(null)
  const [flags, setFlags] = useState<{ flags: Flag[]; note: string } | null>(null)
  const [path, setPath] = useState<ConnectPath | null>(null)
  const [why, setWhy] = useState<WhyLinked | null>(null)
  const [err, setErr] = useState('')
  const network = useRef<GraphHandle>(null)

  useEffect(() => {
    network.current?.clear()
    if (!obj || obj.id !== a) return
    if (path?.connected && path.nodes) {
      network.current?.add(path.nodes.map((node) => ({ id: node.id, type: node.type, label: node.title, seed: node.id === a || node.id === b })), (path.steps ?? []).map((step, index) => ({ id: `path:${index}:${step.from}:${step.to}`, source: step.from, target: step.to, type: step.type, evidence: 'record path' })))
    } else if (assoc) {
      network.current?.add([{ id: obj.id, type: obj.type, label: obj.title, seed: true }, ...assoc.associates.map((item) => ({ id: item.id, type: item.type, label: item.title }))], assoc.associates.map((item) => ({ id: `association:${obj.id}:${item.id}`, source: obj.id, target: item.id, type: 'associated_with', evidence: item.summary || item.why.join(', '), status: item.inferred ? 'candidate' : 'recorded' })))
    }
  }, [obj, assoc, path, a, b])

  useEffect(() => setA(seed), [seed])
  useEffect(() => {
    setAssoc(null)
    setFlags(null)
    setErr('')
    if (!a) return
    api.object(a).then(setObj).catch((e) => setErr(e.message))
    intel.associates(a).then(setAssoc).catch((e) => setErr(e.message))
    intel.flags(a).then(setFlags).catch(() => setFlags(null))
  }, [a, nav.tick, nav.caseId])
  useEffect(() => {
    setPath(null)
    setWhy(null)
    if (!a || !b) return
    intel.connect(a, b).then(setPath).catch((e) => setErr(e.message))
    intel.whyLinked(a, b).then(setWhy).catch(() => setWhy(null))
  }, [a, b, nav.tick])

  if (!nav.caseId) return <NonIdealState icon="lock" title="Select a case" description="Connections draw on personal records, so they need an open case you are a member of." />
  return (
    <div className="workspace" style={{ gridTemplateColumns: '340px 1fr 380px' }}>
      <aside className="panel">
        <div className="section">
          <h3>From</h3>
          <Omnibox onPick={(id) => setA(id)} shortcut={false} label="Search for the first person or record" />
          {obj && (
            <div className="kv-row" style={{ marginTop: 8 }}>
              <b>{obj.title}</b> <span className="muted small">{obj.type}</span>
              <Button small minimal icon="person" onClick={() => nav.openEntity(obj.id)} style={{ marginLeft: 'auto' }}>
                Dossier
              </Button>
            </div>
          )}
        </div>
        <div className="section">
          <h3>To <span className="count">optional</span></h3>
          <Omnibox onPick={(id) => setB(id)} shortcut={false} label="Search for the second person or record" />
          {b && <Button small minimal icon="cross" onClick={() => setB(null)} style={{ marginTop: 8 }}>Clear the second record</Button>}
        </div>
        {flags && flags.flags.length > 0 && (
          <div className="section">
            <h3>Conduct flags</h3>
            <p className="small muted">{flags.note}</p>
            {flags.flags.map((f) => (
              <div key={f.id} className="kv-row small">
                <Tag intent={f.severity === 'high' ? 'danger' : f.severity === 'medium' ? 'warning' : 'none'} minimal>
                  {f.severity}
                </Tag>{' '}
                <b>{f.title}</b>
                <div className="muted">{rupees(f.summary)}</div>
              </div>
            ))}
          </div>
        )}
      </aside>
      <main className="canvas scroll padded">
        {err && <p className="err">{err}</p>}
        {a && <section className="work-section" style={{ marginBottom: 16 }}><div className="section-heading"><div><h2>Connection network</h2><p>{path?.connected ? 'Records connecting the selected entities' : 'Available associations and their evidence'}</p></div></div><GraphCanvas ref={network} height={560} onSelect={(id) => { if (id && id !== a) setB(id) }} onOpen={nav.openEntity} caseBounded groupSimilar={false} /></section>}
        {!a && (
          <div className="canvas-message">
            <div>
              <NonIdealState icon="search" title="Choose who to start from" description="Search on the left for a person, account, phone or company, or open Connections from a dossier." />
              <CaseStart nav={nav} title="People in the active case" action="Show connections" onPick={setA} />
            </div>
          </div>
        )}
        {b && !path && <div className="empty"><Spinner size={20} /></div>}
        {path && (
          <section className="card" style={{ marginBottom: 16 }}>
            <h4>Chain of records</h4>
            {!path.connected && <p className="muted">{path.note}</p>}
            {path.connected && (
              <>
                <p className="small muted">{path.hops} step(s) through records in this case's reach.</p>
                {path.steps?.map((s, i) => (
                  <div key={i} className="kv-row small">
                    <b>{s.label}</b> <span className="muted">({titleCase(s.type)})</span>
                  </div>
                ))}
              </>
            )}
          </section>
        )}
        {why && why.bases.length > 0 && (
          <section className="card" style={{ marginBottom: 16 }}>
            <h4>Why they are associated <span className="muted">score {why.score.toFixed(2)}</span></h4>
            {why.bases.map((x, i) => (
              <div key={i} className="kv-row small">
                <Tag minimal>{why.labels[x.kind] ?? x.kind}</Tag> {x.detail} <span className="muted">weight {x.weight}</span>
              </div>
            ))}
          </section>
        )}
        {a && !assoc && !err && <div className="empty"><Spinner size={20} /></div>}
        {assoc && (
          <section className="card">
            <h4>Associates <span className="muted">{assoc.associates.length}</span></h4>
            <p className="small muted">{assoc.note}</p>
            {assoc.associates.map((x) => (
              <button key={x.id} className="assoc-row" onClick={() => setB(x.id)}>
                <b>{x.title}</b> {x.in_case && <Tag minimal intent="success">In case</Tag>}
                <span className="small muted" style={{ display: 'block' }}>{(x.summary || x.why?.join(', ') || '').slice(0, 160)}</span>
              </button>
            ))}
          </section>
        )}
      </main>
      <aside className="panel right">
        <div className="section">
          <Callout icon="info-sign" compact>
            Associations are inferred from what people did or share: handsets, SIMs, accounts, money, calls, addresses, journeys, convoys. Never from who they are. Each comes with its bases; treat them as leads.
          </Callout>
        </div>
      </aside>
    </div>
  )
}

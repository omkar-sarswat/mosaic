import { InputGroup, NonIdealState } from '@blueprintjs/core'
import { Button } from '../components/Button'
import { useEffect, useState } from 'react'
import { api, type ObjSummary } from '../api'
import type { Shared } from './shared'

type Item = Awaited<ReturnType<typeof api.review>>[number]

// The matcher explains itself in its own terms ("name=phonetic (+7.2)"). A reviewer needs the same facts in
// words: what agrees, what differs, and how much each counts.
const FIELD: Record<string, string> = {
  name: 'Name', father: "Father's or spouse's name", age: 'Age', dob: 'Date of birth', gender: 'Gender', district: 'District',
  address: 'Address', phone: 'Phone number', identity: 'ID numbers (PAN, Aadhaar)', email: 'Email',
}
const LEVEL: Record<string, string> = {
  exact: 'the same', match: 'the same', same: 'the same', phonetic: 'sounds the same', initials: 'initials and surname match',
  weak: 'only loosely similar', partial: 'partly the same', close: 'within a year or two', near: 'a few years apart', far: 'far apart', diff: 'different',
}
type Reason = { field: string; says: string; weight: number }
function reasons(features: string[]): Reason[] {
  return features.map((f) => {
    const m = /^(\w+)=(\w+)\s*\(([-+]?\d+(?:\.\d+)?)\)/.exec(f)
    if (!m) return { field: f, says: '', weight: 0 }
    return { field: FIELD[m[1]] ?? m[1], says: LEVEL[m[2]] ?? m[2].replaceAll('_', ' '), weight: Number(m[3]) }
  })
}
const strength = (w: number) => (Math.abs(w) >= 6 ? 'Strong' : Math.abs(w) >= 3 ? 'Moderate' : 'Weak')
const likely = (p: number) => `${Math.round(p * 100)}% likely the same person`

export default function Review(shared: Shared & { focus?: string | null }) {
  const [items, setItems] = useState<Item[]>([])
  const [err, setErr] = useState('')
  const [sel, setSel] = useState<Item | null>(null)
  const [reason, setReason] = useState('')

  useEffect(() => {
    setErr('')
    api.review().then((r) => { setItems(r); setSel(r.find((i) => i.id === shared.focus) ?? r[0] ?? null) }).catch((e) => { setItems([]); setErr(e.message) })
  }, [shared.tick])

  const decide = (action: 'confirm_match' | 'reject_match') => {
    if (!sel) return
    api.action(action, { review_id: sel.id, reason }).then(() => {
      const rest = items.filter((i) => i.id !== sel.id)
      setItems(rest)
      setSel(rest[0] ?? null)
      setReason('')
    }).catch((e) => setErr(e.message))
  }

  const why = sel ? reasons(sel.explanation.features) : []
  const agrees = why.filter((r) => r.weight > 0).sort((a, b) => b.weight - a.weight)
  const differs = why.filter((r) => r.weight < 0).sort((a, b) => a.weight - b.weight)

  return (
    <div className="workspace" style={{ gridTemplateColumns: '320px minmax(0, 1fr)' }}>
      <aside className="panel">
        <div className="section">
          <h3>Waiting for review <span className="count">{items.length}</span></h3>
          <p className="small muted" style={{ margin: 0 }}>Pairs of records the system thinks may be one person but is not sure of. Nothing is merged until a person decides, and every decision can be undone.</p>
          {err && <p className="err small">{err}</p>}
        </div>
        <ul className="list">
          {items.map((i) => (
            <li key={i.id} className={sel?.id === i.id ? 'sel' : ''}>
              <button className="row-button" aria-current={sel?.id === i.id ? 'true' : undefined} onClick={() => setSel(i)}>
                <span className="t" style={{ display: 'block' }}>{i.a.title} <span className="muted">and</span> {i.b.title}</span>
                <span className="s" style={{ display: 'block' }}>{likely(i.probability)}</span>
              </button>
            </li>
          ))}
        </ul>
      </aside>
      <main className="canvas scroll" style={{ background: 'var(--paper)' }}>
        {sel ? (
          <div className="section stack" style={{ borderBottom: 0, maxWidth: 980 }}>
            <h2 style={{ margin: 0 }}>Are these the same person?</h2>
            <p className="muted" style={{ margin: 0 }}>{likely(sel.probability)}, by the records below.</p>
            <div className="side-by-side">
              <Rec r={sel.a} />
              <Rec r={sel.b} />
            </div>
            <div className="card">
              <h4>Why they were paired</h4>
              {(sel.explanation.review_reasons ?? []).length > 0 && (
                <p className="small warn-text" style={{ marginTop: 0 }}>Held for a person to decide: {sel.explanation.review_reasons!.join('; ')}.</p>
              )}
              <div className="side-by-side">
                <div>
                  <h5 style={{ marginTop: 0 }}>What agrees</h5>
                  {!agrees.length && <p className="small muted">Nothing.</p>}
                  <dl className="measure-list">{agrees.map((r) => <div key={r.field} style={{ display: 'contents' }}><dt>{r.field}: {r.says}</dt><dd>{strength(r.weight)}</dd></div>)}</dl>
                </div>
                <div>
                  <h5 style={{ marginTop: 0 }}>What differs</h5>
                  {!differs.length && <p className="small muted">Nothing.</p>}
                  <dl className="measure-list">{differs.map((r) => <div key={r.field} style={{ display: 'contents' }}><dt>{r.field}: {r.says}</dt><dd>{strength(r.weight)}</dd></div>)}</dl>
                </div>
              </div>
              <p className="small muted" style={{ marginBottom: 0 }}>Common names count for less than rare ones. Check the source records before deciding.</p>
            </div>
            <InputGroup value={reason} onChange={(e) => setReason(e.target.value)} aria-label="Reason for your decision" placeholder="Reason for your decision (recorded)" />
            <div className="row">
              <Button intent="primary" icon="tick" disabled={reason.trim().length < 3} onClick={() => decide('confirm_match')}>Same person</Button>
              <Button icon="cross" disabled={reason.trim().length < 3} onClick={() => decide('reject_match')}>Different people</Button>
            </div>
          </div>
        ) : err ? <NonIdealState icon="lock" title="Review is for analysts and supervisors" description={err} />
          : <NonIdealState icon="tick-circle" title="No matches waiting" description="Pairs of records that may be one person appear here for someone to confirm or reject." />}
      </main>
    </div>
  )
}

function Rec({ r }: { r: ObjSummary }) {
  const p = r.props
  return (
    <div className="card">
      <h4>{String(p.name)}</h4>
      <dl className="kv">
        {p.name_native ? (<><dt>Original script</dt><dd>{String(p.name_native)}</dd></>) : null}
        <dt>Father / spouse</dt><dd>{String(p.father_name ?? '—')}</dd>
        <dt>Birth year</dt><dd>{String(p.birth_year ?? '—')}</dd>
        <dt>Gender</dt><dd>{p.gender === 'M' ? 'Male' : p.gender === 'F' ? 'Female' : String(p.gender ?? '—')}</dd>
        <dt>District</dt><dd>{r.district_name ?? '—'}</dd>
      </dl>
    </div>
  )
}

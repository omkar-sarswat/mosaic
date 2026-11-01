import { InputGroup, Spinner } from '@blueprintjs/core'
import { Button } from '../components/Button'
import { PersonAvatar } from '../components/PersonPhoto'
import { useEffect, useState } from 'react'
import { api, type ObjDetail } from '../api'
import { type Shared, TYPE_COLOURS, shortDate } from './shared'
import { MarkingChip } from '../components/Marking'

const HIDDEN_PROPS = new Set(['geom'])

export default function ObjectPanel({ id, shared, onSelect }: { id: string | null; shared: Shared; onSelect?: (id: string) => void }) {
  const [obj, setObj] = useState<ObjDetail | null>(null)
  const [err, setErr] = useState('')
  const [loading, setLoading] = useState(false)
  const [unmask, setUnmask] = useState<{ prop: string; reason: string } | null>(null)
  const [clear, setClear] = useState<Record<string, string>>({})
  const [reason, setReason] = useState('')
  const [msg, setMsg] = useState('')

  useEffect(() => {
    setObj(null)
    setErr('')
    setClear({})
    setMsg('')
    if (!id) return
    setLoading(true)
    api
      .object(id)
      .then(setObj)
      .catch((e) => setErr(e.message))
      .finally(() => setLoading(false))
  }, [id, shared.tick])

  if (!id) return <div className="panel-empty"><h3>Nothing selected</h3><p>Search on the left and choose a record to see its properties, sources and links.</p></div>
  if (loading) return <div className="empty"><Spinner size={20} /></div>
  if (err) return <div className="section"><p className="err">Access refused: {err}</p><p className="muted small">The refusal was recorded in the audit log.</p></div>
  if (!obj) return null

  const provFor = (p: string) => obj.provenance.filter((x) => x.prop === p)
  const props = Object.entries(obj.props).filter(([k, v]) => !HIDDEN_PROPS.has(k) && v !== null && v !== '' && typeof v !== 'object')
  const listProps = Object.entries(obj.props).filter(([, v]) => Array.isArray(v))

  const doUnmask = () => {
    if (!unmask) return
    api
      .action<{ value: string }>('unmask', { object_id: obj.id, property: unmask.prop, reason: unmask.reason })
      .then((r) => {
        setClear({ ...clear, [unmask.prop]: String(r.value) })
        setUnmask(null)
      })
      .catch((e) => setMsg(e.message))
  }

  const addToCase = () =>
    api
      .action('add_to_case', { object_id: obj.id, reason: reason || 'linked by evidence in the case graph' })
      .then(() => {
        setMsg('Added to case scope.')
        shared.refresh()
      })
      .catch((e) => setMsg(e.message))

  return (
    <div>
      <div className="section">
        <div className="row">
          <span className="type-dot" style={{ background: TYPE_COLOURS[obj.type] ?? 'var(--muted)' }} />
          <span className="muted small">{obj.type}</span>
          {obj.synthetic && <span className="chip syn">synthetic</span>}
          <MarkingChip level={obj.sensitivity} />
          {obj.in_case && <span className="chip src">in case</span>}
        </div>
        <div className="inspector-person">
          {obj.type === 'Person' && <PersonAvatar id={obj.id} name={obj.title} size={56} />}
          <h2 style={{ fontSize: 17 }}>{obj.title}</h2>
        </div>
        {obj.district_name && <div className="muted small">{obj.district_name} district (LGD {obj.district})</div>}
        <div className="row" style={{ marginTop: 8 }}>
          <Button small icon="graph" onClick={() => shared.openGraph(obj.id)}>
            Open graph
          </Button>
          {shared.caseId && obj.sensitivity > 0 && !obj.in_case && (
            <Button small icon="add-to-folder" onClick={addToCase} title="Bring into the case scope (audited)">
              Add to case
            </Button>
          )}
        </div>
        {shared.caseId && obj.sensitivity > 0 && !obj.in_case && (
          <InputGroup small placeholder="Reason for adding (recorded)" value={reason} onChange={(e) => setReason(e.target.value)} style={{ marginTop: 6 }} />
        )}
        {msg && <p className="small" style={{ marginTop: 6 }}>{msg}</p>}
      </div>

      <div className="section">
        <h3>Properties and sources</h3>
        <dl className="kv">
          {props.map(([k, v]) => (
            <Prop key={k} name={k} value={clear[k] ?? String(v)} masked={obj.masked.includes(k) && !clear[k]} prov={provFor(k)}
              onUnmask={() => setUnmask({ prop: k, reason: '' })} />
          ))}
          {listProps.map(([k, v]) => (
            <Prop key={k} name={k} value={(v as unknown[]).join(', ')} masked={false} prov={provFor(k)} />
          ))}
        </dl>
        {unmask && (
          <div className="notice" style={{ marginTop: 8 }}>
            <div className="small">Unmask <b>{unmask.prop}</b>: state why (logged, visible to the oversight officer).</div>
            <InputGroup small value={unmask.reason} onChange={(e) => setUnmask({ ...unmask, reason: e.target.value })} placeholder="e.g. CDR request under BNSS s.94" />
            <div className="row" style={{ marginTop: 6 }}>
              <Button small intent="warning" onClick={doUnmask} disabled={unmask.reason.trim().length < 10}>Unmask</Button>
              <Button small minimal onClick={() => setUnmask(null)}>Cancel</Button>
            </div>
          </div>
        )}
      </div>

      {obj.resolved_records && (
        <div className="section">
          <h3>Resolved entity <span className="count">{obj.resolved_records.length + 1} records</span></h3>
          {obj.resolved_records.length === 0 && <div className="muted small">No other records linked to this one.</div>}
          <ul className="list">
            {obj.resolved_records.map((r) => (
              <li key={r.id}>
                <button className="row-button" onClick={() => onSelect?.(r.id)}>
                  <span className="t" style={{ display: 'block' }}>{r.title}</span>
                  <span className="s" style={{ display: 'block' }}>
                    {String(r.props.name_native ?? '')} {r.district_name ? `· ${r.district_name}` : ''} {r.props.birth_year ? `· born ${r.props.birth_year}` : ''}
                  </span>
                </button>
              </li>
            ))}
          </ul>
          {obj.match_links && obj.match_links.length > 0 && (
            <div className="stack" style={{ marginTop: 8 }}>
              {obj.match_links.slice(0, 6).map((m) => (
                <div key={m.id} className="small">
                  <span className={`chip ${m.status === 'confirmed' ? 'ev-corroborated' : 'ev-suggested'}`}>
                    {m.status} · p={m.confidence.toFixed(3)}
                  </span>
                  <span className="muted">{m.explanation?.features.join(' · ')}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      <div className="section">
        <h3>Links</h3>
        <div className="row">
          {Object.entries(obj.link_counts).map(([k, n]) => (
            <span key={k} className="chip">{k.replaceAll('_', ' ')} · {n}</span>
          ))}
        </div>
      </div>
    </div>
  )
}

function Prop({ name, value, masked, prov, onUnmask }: { name: string; value: string; masked: boolean; prov: { source: string; record: string; ingested_at: string; confidence: number }[]; onUnmask?: () => void }) {
  return (
    <>
      <dt>{name.replaceAll('_', ' ')}</dt>
      <dd>
        <span className={masked ? 'mono' : ''}>{value}</span>{' '}
        {masked && (
          <button className="chip masked" style={{ cursor: 'pointer', background: 'none' }} onClick={onUnmask} title="Unmask with a recorded reason">
            masked
          </button>
        )}
        <div>
          {prov.map((p) => (
            <span key={p.source + p.record} className="chip src" title={`record ${p.record} · ingested ${shortDate(p.ingested_at)} · confidence ${p.confidence}`}>
              {p.source}
            </span>
          ))}
        </div>
      </dd>
    </>
  )
}

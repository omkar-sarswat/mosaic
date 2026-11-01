import { Icon, InputGroup } from '@blueprintjs/core'
import { Button } from '../components/Button'
import { useEffect, useState } from 'react'
import { api, casework } from '../api'
import { type Shared, shortDate } from './shared'
import { sentence } from '../lib/format'

type Row = Awaited<ReturnType<typeof api.audit>>[number]

export default function Oversight(shared: Shared) {
  const [rows, setRows] = useState<Row[]>([])
  const [verify, setVerify] = useState<Awaited<ReturnType<typeof api.verify>> | null>(null)
  const [alerts, setAlerts] = useState<Awaited<ReturnType<typeof api.alerts>>>([])
  const [trans, setTrans] = useState<Awaited<ReturnType<typeof api.transparency>> | null>(null)
  const [err, setErr] = useState('')
  const [user, setUser] = useState('')
  const [obj, setObj] = useState('')
  const [seal, setSeal] = useState('')
  const isAuditor = shared.me?.roles.includes('auditor')
  const canRetention = shared.me?.roles.some((r) => ['auditor', 'admin', 'supervisor'].includes(r))
  const [ret, setRet] = useState<Awaited<ReturnType<typeof casework.retention>> | null>(null)
  useEffect(() => {
    if (canRetention) casework.retention().then(setRet).catch(() => setRet(null))
  }, [canRetention, shared.tick])

  const load = () => {
    setErr('')
    api.transparency().then(setTrans).catch(() => setTrans(null))
    if (!isAuditor) return
    api.audit({ user: user || undefined, object_id: obj || undefined }).then(setRows).catch((e) => setErr(e.message))
    api.verify().then(setVerify).catch(() => setVerify(null))
    api.alerts().then(setAlerts).catch(() => setAlerts([]))
  }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(load, [shared.tick, isAuditor])

  const doSeal = () => api.seal().then((r) => setSeal(r.root_hash ? `Sealed ${r.day}: ${r.root_hash}` : 'Nothing to seal')).catch((e) => setSeal(e.message))

  return (
    <div className="workspace wide-left" style={isAuditor ? undefined : { gridTemplateColumns: '320px minmax(0, 1fr)' }}>
      <aside className="panel">
        <div className="section">
          <h3>Audit chain</h3>
          {!isAuditor && <p className="muted small">The audit log is readable only by the independent oversight officer. Every look-up you make is recorded in it.</p>}
          {verify && (
            <div className={verify.ok ? '' : 'err'}>
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, color: verify.ok ? 'var(--approve)' : 'var(--tape)', fontWeight: 600 }}>
                <Icon icon={verify.ok ? 'tick-circle' : 'error'} size={14} />{verify.ok ? `Intact · ${verify.checked.toLocaleString('en-IN')} entries` : `Broken at entry ${verify.first_bad_seq}`}
              </span>
              {verify.head && <div className="mono small muted" style={{ wordBreak: 'break-all', marginTop: 4 }}>Head {verify.head}</div>}
            </div>
          )}
          {isAuditor && (
            <div className="stack" style={{ marginTop: 8 }}>
              <Button small icon="lock" onClick={doSeal}>Seal today’s root hash</Button>
              {seal && <div className="mono small" style={{ wordBreak: 'break-all' }}>{seal}</div>}
              <p className="small muted">Publish the root outside Mosaic (e.g. to the oversight board) so any later rewrite is detectable.</p>
            </div>
          )}
        </div>
        {isAuditor && (
          <div className="section">
            <h3>Insider-threat alerts <span className="count">{alerts.length}</span></h3>
            {alerts.length === 0 && <p className="muted small">None.</p>}
            {alerts.map((a) => (
              <div key={a.seq + a.rule} className="small" style={{ marginBottom: 8 }}>
                <span className={`chip ${a.severity === 'critical' ? 'ev-suggested' : a.severity === 'high' ? 'ev-single' : ''}`}>{a.severity}</span>
                <b>{a.rule.replaceAll('_', ' ')}</b> · {a.user_id}
                <div className="muted">{a.detail} · #{a.seq} {shortDate(a.ts)}</div>
              </div>
            ))}
          </div>
        )}
        {ret && (
          <div className="section">
            <h3>Retention</h3>
            <div className="small">Due now: <b>{ret.due.length}</b> · scheduled: {ret.scheduled.length} · on legal hold: {ret.held.length}</div>
            {ret.scheduled.slice(0, 6).map((c) => <div key={c.id} className="small muted">{c.id} · purge after {c.retention_until}</div>)}
            {ret.held.map((c) => <div key={c.id} className="small"><Icon icon="lock" size={12} /> {c.id}: {c.hold_reason}</div>)}
            {shared.me?.roles.some((r) => r === 'admin' || r === 'supervisor') && (
              <Button small icon="trash" intent="danger" disabled={!ret.due.length} onClick={() => casework.runRetention().then(shared.refresh).catch((e) => shared.setError(e.message))}>
                Purge {ret.due.length} due case(s)
              </Button>
            )}
            {ret.purged.slice(0, 6).map((p) => (
              <div key={p.id} className="small" style={{ marginTop: 4 }}>
                <Icon icon="trash" size={12} /> {p.case_id ?? p.legal_order} · {p.purged_at.slice(0, 16)} · {Object.entries(p.counts).map(([k, v]) => `${v} ${k}`).join(', ')}
                <div className="mono muted">manifest {p.manifest_sha256.slice(0, 20)}…</div>
              </div>
            ))}
          </div>
        )}
      </aside>

      <main className="canvas scroll" style={{ background: 'var(--sheet)' }}>
        {isAuditor ? (
          <>
            <form className="section row" onSubmit={(e) => { e.preventDefault(); load() }}>
              <InputGroup small aria-label="Filter by user" placeholder="Filter by user id" value={user} onChange={(e) => setUser(e.target.value)} />
              <InputGroup small aria-label="Filter by record" placeholder="Filter by record id (who looked at this person?)" value={obj} onChange={(e) => setObj(e.target.value)} style={{ minWidth: 300 }} />
              <Button small type="submit">Apply filters</Button>
              {err && <span className="err small">{err}</span>}
            </form>
            <table className="data">
              <thead>
                <tr><th>#</th><th>Time (UTC)</th><th>User</th><th>Action</th><th>Case and purpose</th><th className="numeric">Records</th><th>Outcome</th><th>Detail</th></tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.seq} className={r.outcome === 'denied' ? 'denied' : ''}>
                    <td className="mono">{r.seq}</td>
                    <td className="mono">{shortDate(r.ts)}</td>
                    <td>{r.user_id}<div className="muted small">{r.role}</div></td>
                    <td>{r.action}</td>
                    <td className="small">{r.case_id ?? '—'}<div className="muted">{r.purpose?.replaceAll('_', ' ')}</div></td>
                    <td className="numeric">{r.object_ids.length}</td>
                    <td>{r.outcome}</td>
                    <td className="small muted" style={{ maxWidth: 320, wordBreak: 'break-word' }}>{JSON.stringify(r.detail).slice(0, 180)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        ) : (
          <div className="section" style={{ borderBottom: 0 }}>
            <h2 style={{ marginTop: 0 }}>Public transparency report</h2>
            <p className="muted small">The audit log itself is readable only by the independent oversight officer. These aggregate figures are published for anyone to read, as German and UK oversight bodies recommend.</p>
            {trans && <div className="grid-cards" style={{ padding: '8px 0 0' }}>
              <Stat title="Events by action" data={trans.audit_events_by_action} card />
              <Stat title="Outcomes" data={trans.audit_events_by_outcome} card />
              <Stat title="Cases by purpose" data={trans.cases_by_purpose} card />
              <Stat title="Records by source" data={trans.objects_by_source} card />
            </div>}
          </div>
        )}
      </main>

      {isAuditor && <aside className="panel right">
        <div className="section">
          <h3>Public transparency report</h3>
          <p className="small muted">Aggregate figures anyone can read, as German and UK oversight bodies recommend.</p>
        </div>
        {trans && (
          <>
            <Stat title="Events by action" data={trans.audit_events_by_action} />
            <Stat title="Outcomes" data={trans.audit_events_by_outcome} />
            <Stat title="Cases by purpose" data={trans.cases_by_purpose} />
            <Stat title="Records by source" data={trans.objects_by_source} />
          </>
        )}
      </aside>}
    </div>
  )
}

function Stat({ title, data, card = false }: { title: string; data: Record<string, number>; card?: boolean }) {
  const rows = Object.entries(data).sort((a, b) => b[1] - a[1])
  return (
    <div className={card ? 'card' : 'section'}>
      {card ? <h4>{title}</h4> : <h3>{title}</h3>}
      <dl className="measure-list">
        {rows.map(([k, v]) => (
          <div key={k} style={{ display: 'contents' }}><dt>{sentence((k || 'unspecified').replaceAll(':', ': '))}</dt><dd>{v.toLocaleString('en-IN')}</dd></div>
        ))}
      </dl>
    </div>
  )
}

import { Callout, Tag } from '@blueprintjs/core'
import { Button } from '../components/Button'
import type { Dossier } from '../api'
import { titleCase, when, rupees } from '../lib/format'
import type { Nav } from './nav'

const ROLE_INTENT: Record<string, 'danger' | 'warning' | 'primary' | 'none'> = { accused: 'danger', convicted: 'danger', victim: 'primary', complainant: 'primary', witness: 'none' }

// Criminal background with roles, pattern findings, movement, purchase registers, tenders and weapons.
// Sections outside the active case's purpose are listed as withheld, never silently empty.
export default function DossierRecord({ d, nav }: { d: Dossier; nav: Nav }) {
  const c = d.criminal
  return (
    <div className="grid3" style={{ gridTemplateColumns: '1.3fr 1fr', padding: 10 }}>
      {d.withheld_sections && d.withheld_sections.length > 0 && (
        <div style={{ gridColumn: 'span 2' }}>
          <Callout icon="lock" compact>
            Outside this case's purpose, so not shown: {d.withheld_sections.join(', ')}. A case opened for a purpose that covers them would show them.
          </Callout>
        </div>
      )}
      {d.findings && d.findings.length > 0 && (
        <section className="card" style={{ gridColumn: 'span 2' }}>
          <h4>Pattern findings ({d.findings.length})</h4>
          <p className="small muted">Patterns this entity is part of, with their evidence. Leads for an officer to examine, not conclusions.</p>
          {d.findings.map((f) => (
            <div key={f.id} className="kv-row">
              <Tag intent={f.severity === 'high' ? 'danger' : 'warning'}>{f.severity}</Tag> <b>{f.title}</b>{' '}
              {f.status !== 'open' && <Tag minimal>{titleCase(f.status)}</Tag>}
              <div className="small">{rupees(f.summary)}</div>
              <div className="small muted">{f.tracks.map((t) => t.replaceAll('_', ' ')).join(' · ')}</div>
            </div>
          ))}
          <Button small minimal icon="search-around" onClick={() => nav.go('leads')}>
            Open the leads queue
          </Button>
        </section>
      )}
      {d.deconfliction && d.deconfliction.other_track_leads > 0 && (
        <div style={{ gridColumn: 'span 2' }}>
          <Callout intent="warning" icon="people" compact>
            Deconfliction: {d.deconfliction.other_track_leads} lead(s) in other agencies' tracks also involve this entity (
            {Object.entries(d.deconfliction.tracks).map(([t, n]) => `${t.replaceAll('_', ' ')}: ${n}`).join(', ')}). Their content is not shown; coordinate
            through a case share.
          </Callout>
        </div>
      )}
      {c && (
        <section className="card">
          <h4>
            Criminal background ({c.records.length}) {c.history_sheet && <Tag intent="danger" minimal>History-sheet {c.history_sheet}</Tag>}
          </h4>
          <div className="small muted" style={{ marginBottom: 6 }}>
            {Object.entries(c.roles).map(([r, n]) => `${n} as ${r}`).join(' · ') || 'No FIR roles on record'}
          </div>
          {c.records.map((r) => (
            <button key={`${r.id}-${r.role}`} className="kv-row small" onClick={() => nav.openEntity(r.id)}>
              <Tag minimal intent={ROLE_INTENT[r.role] ?? 'none'}>{r.role}</Tag> <b>{r.title}</b> <span className="muted">{r.agency}</span>{' '}
              <Tag minimal>{titleCase(r.status || '')}</Tag>
              <span className="muted" style={{ flexBasis: '100%' }}>
                {when(r.occurred_at)} · {(r.sections || []).join(', ')}
                {r.chargesheeted_on && ` · charge-sheeted ${r.chargesheeted_on}`}
                {r.co_accused > 0 && ` · ${r.co_accused} co-accused`}
              </span>
              {r.summary && <span style={{ flexBasis: '100%' }}>{rupees(r.summary)}</span>}
            </button>
          ))}
        </section>
      )}
      {d.comms && (
        <section className="card">
          <h4>Communications ({d.comms.calls.toLocaleString('en-IN')} calls)</h4>
          <div className="small muted">
            {when(d.comms.first)} to {when(d.comms.last)}
          </div>
          <div className="small" style={{ marginTop: 6 }}>
            <b>Regular contacts</b>
          </div>
          {d.comms.top_contacts.map((t, i) => (
            <div key={i} className="kv-row small">
              {t.label} {t.foreign && <Tag minimal intent="warning">foreign</Tag>} <span className="muted">{t.calls} calls</span>
            </div>
          ))}
          {d.comms.towers.length > 0 && (
            <>
              <div className="small" style={{ marginTop: 6 }}>
                <b>Towers</b>
              </div>
              {d.comms.towers.map((t) => (
                <div key={t.tower} className="kv-row small">
                  {t.tower} <span className="muted">{t.calls}</span>
                </div>
              ))}
            </>
          )}
        </section>
      )}
      {d.movement && (
        <section className="card">
          <h4>Movement ({d.movement.total} toll / ANPR reads)</h4>
          {Object.entries(d.movement.places).map(([p, n]) => (
            <div key={p} className="kv-row small">
              {p} <span className="muted">{n}</span>
            </div>
          ))}
          <div className="small muted" style={{ marginTop: 6 }}>
            Latest: {d.movement.reads.slice(0, 5).map((r) => `${r.plaza} ${when(r.ts)}`).join(' · ')}
          </div>
        </section>
      )}
      {d.procurement && (
        <section className="card">
          <h4>Purchase registers ({d.procurement.orders} orders, {d.procurement.dealers} dealers)</h4>
          <div className="small">
            Licence on record: <b>{d.procurement.licence_on_record || 'none'}</b> {d.procurement.licensed_for.length > 0 && `for ${d.procurement.licensed_for.join(', ')}`}
          </div>
          <div className="small">Licences quoted on invoices: {d.procurement.licences_quoted.join(', ') || 'none'}</div>
          {d.procurement.monthly.slice(-12).map((m) => (
            <div key={`${m.month}-${m.substance}`} className="kv-row small">
              {m.month} · {m.substance.replaceAll('_', ' ')} <b>{m.kg} kg</b>
            </div>
          ))}
        </section>
      )}
      {d.tenders && d.tenders.length > 0 && (
        <section className="card">
          <h4>Tenders bid ({d.tenders.length})</h4>
          {d.tenders.map((t) => (
            <div key={t.tender} className="kv-row small">
              {t.won ? <Tag intent="success" minimal>won</Tag> : <Tag minimal>lost</Tag>} <b>{t.tender}</b> {t.title}
              <div className="muted">
                bid {(t.bid / 1e5).toFixed(1)} L vs estimate {(t.estimate / 1e5).toFixed(1)} L ({((100 * t.bid) / t.estimate).toFixed(1)}%)
              </div>
            </div>
          ))}
        </section>
      )}
      {d.firearms && d.firearms.length > 0 && (
        <section className="card">
          <h4>Weapons linked ({d.firearms.length})</h4>
          {d.firearms.map((f) => (
            <div key={f.id} className="kv-row small">
              <b>{f.title}</b> {String(f.props.kind ?? '')} {String(f.props.calibre ?? '')} <Tag minimal>{String(f.props.status ?? '')}</Tag>
              {f.props.ballistic_ref ? <div className="muted">Ballistic signature {String(f.props.ballistic_ref)}</div> : null}
            </div>
          ))}
        </section>
      )}
    </div>
  )
}

import { Callout, NonIdealState, Spinner, Tag } from '@blueprintjs/core'
import { Tabs } from '@mantine/core'
import { useEffect, useState } from 'react'
import { api, patterns, type DetectorCard, type Evaluation } from '../api'
import type { Nav } from './nav'

// Administration: how the detectors and the record matcher are built and how well they perform. This is
// for the people who maintain and oversee them (administrator, data steward, oversight officer); officers
// acting on leads see each lead's plain explanation instead.
export default function Admin({ nav }: { nav: Nav }) {
  const [tab, setTab] = useState<string | null>('library')
  const [cat, setCat] = useState<Awaited<ReturnType<typeof patterns.catalog>> | null>(null)
  useEffect(() => {
    patterns.catalog().then(setCat).catch((e) => nav.setError(e.message))
  }, [nav])
  return (
    <Tabs className="page" value={tab} onChange={setTab} keepMounted={false}>
      <div className="case-bar">
        <Tabs.List className="case-view-tabs" aria-label="Administration">
          <Tabs.Tab value="library">Pattern library</Tabs.Tab>
          <Tabs.Tab value="tests">Pattern tests</Tabs.Tab>
          <Tabs.Tab value="matching">Record matching</Tabs.Tab>
          <Tabs.Tab value="quality">Source data quality</Tabs.Tab>
        </Tabs.List>
      </div>
      <Tabs.Panel value="library">{cat ? <Catalogue cards={cat.detectors} tracks={cat.tracks} /> : <div className="empty"><Spinner size={20} /></div>}</Tabs.Panel>
      <Tabs.Panel value="tests"><Robustness nav={nav} /></Tabs.Panel>
      <Tabs.Panel value="matching"><Matching nav={nav} /></Tabs.Panel>
      <Tabs.Panel value="quality"><Quality nav={nav} /></Tabs.Panel>
    </Tabs>
  )
}

function Matching({ nav }: { nav: Nav }) {
  const [q, setQ] = useState<Awaited<ReturnType<typeof api.quality>> | null>(null)
  const [err, setErr] = useState('')
  useEffect(() => {
    api.quality().then(setQ).catch((e) => setErr(e.message))
  }, [nav.tick])
  if (err) return <NonIdealState icon="lock" title="Not available" description={err} />
  if (!q) return <div className="empty"><Spinner size={20} /></div>
  const m = (q.resolve ?? {}) as Record<string, unknown>
  const auto = m.benchmark_auto_only as Record<string, number> | undefined
  const reviewed = m.benchmark_if_all_reviews_confirmed as Record<string, number> | undefined
  return (
    <div style={{ display: 'grid', gap: 16, maxWidth: 760 }}>
      <Callout icon="lab-test" compact>Measured against synthetic ground truth. Real precision must be measured on an audited sample of real record pairs before a deployment relies on automatic links.</Callout>
      <section className="card">
        <h4>Record matching</h4>
        <dl className="measure-list">
          <dt>Source records</dt><dd>{String(m.records ?? '')}</dd>
          <dt>Resolved people</dt><dd>{String(m.resolved_entities ?? '')}</dd>
          <dt>Linked automatically</dt><dd>{String(m.auto_links ?? '')}</dd>
          <dt>Sent to a person for review</dt><dd>{String(m.sent_to_review ?? '')}</dd>
          <dt>Parameters</dt><dd>{String(m.parameters ?? '')}</dd>
        </dl>
      </section>
      {auto && <section className="card">
        <h4>Accuracy</h4>
        <div className="table-scroll"><table className="data">
          <thead><tr><th></th><th className="numeric">Precision</th><th className="numeric">Recall</th><th className="numeric">F1</th></tr></thead>
          <tbody>
            <tr><td>Automatic links only</td><td className="numeric">{auto.precision}</td><td className="numeric">{auto.recall}</td><td className="numeric">{auto.f1}</td></tr>
            {reviewed && <tr><td>If every proposed match is confirmed</td><td className="numeric">{reviewed.precision}</td><td className="numeric">{reviewed.recall}</td><td className="numeric">{reviewed.f1}</td></tr>}
          </tbody>
        </table></div>
      </section>}
    </div>
  )
}

function Quality({ nav }: { nav: Nav }) {
  const [q, setQ] = useState<Awaited<ReturnType<typeof api.quality>> | null>(null)
  const [err, setErr] = useState('')
  useEffect(() => {
    api.quality().then(setQ).catch((e) => setErr(e.message))
  }, [nav.tick])
  if (err) return <NonIdealState icon="lock" title="Not available" description={err} />
  if (!q) return <div className="empty"><Spinner size={20} /></div>
  return (
    <section className="card" style={{ maxWidth: 900 }}>
      <h4>Source data issues <span className="muted">{q.lgd.length}</span></h4>
      <p className="card-note">Problems found while loading source records, to report back to the agency that owns each source.</p>
      {!q.lgd.length && <p className="muted small">No issues recorded.</p>}
      {q.lgd.length > 0 && <div className="table-scroll"><table className="data">
        <thead><tr><th>Record</th><th>Issue</th><th>Source</th></tr></thead>
        <tbody>{q.lgd.slice(0, 200).map((x, i) => <tr key={i}><td>{x.object}</td><td className="small">{x.issue}</td><td className="small muted">{x.source}</td></tr>)}</tbody>
      </table></div>}
    </section>
  )
}

function Catalogue({ cards, tracks }: { cards: DetectorCard[]; tracks: Record<string, { label: string; lead: string }> }) {
  return (
    <div className="grid3" style={{ marginTop: 16 }}>
      {cards.map((c) => (
        <section className="card" key={c.id}>
          <h4>
            {c.title} <span className="muted">version {c.version} · {c.scope}</span>
          </h4>
          <div className="row" style={{ flexWrap: 'wrap', gap: 4, marginBottom: 6 }}>
            {c.tracks.map((t) => (
              <Tag key={t} minimal title={tracks[t]?.label}>
                {t.replaceAll('_', ' ')}
              </Tag>
            ))}
          </div>
          <p className="small"><b>{c.question}</b></p>
          <p className="small">{c.algorithm}</p>
          <details>
            <summary className="small">Evasion it defeats ({c.evasion.length}), look-alikes it ignores ({c.benign.length}), blind spots ({c.blind_spots.length})</summary>
            <p className="small"><b>Defeats</b></p>
            <ul className="small">{c.evasion.map((e) => <li key={e}>{e}</li>)}</ul>
            <p className="small"><b>Ignores</b></p>
            <ul className="small">{c.benign.map((e) => <li key={e}>{e}</li>)}</ul>
            <p className="small"><b>Cannot see</b></p>
            <ul className="small">{c.blind_spots.map((e) => <li key={e}>{e}</li>)}</ul>
            <p className="small muted">{c.references.join(' · ')}</p>
            <p className="small muted">Complexity: {c.complexity}</p>
          </details>
        </section>
      ))}
    </div>
  )
}

function Robustness({ nav }: { nav: Nav }) {
  const [ev, setEv] = useState<Evaluation | null>(null)
  const [err, setErr] = useState('')
  useEffect(() => {
    patterns.evaluation().then(setEv).catch((e) => setErr(e.message))
  }, [nav.tick])
  if (err) return <NonIdealState icon="lab-test" title="No evaluation" description={err} />
  if (!ev) return <div className="empty"><Spinner size={20} /></div>
  const s = ev.summary
  return (
    <div style={{ marginTop: 16 }}>
      <Callout intent="warning" icon="lab-test" compact>
        {ev.caveat} Benign look-alikes are planted to tempt each detector (a family sharing a phone, a call centre, an old business group, a commuter).
      </Callout>
      <div className="tiles" style={{ marginTop: 16 }}>
        <div className="tile"><span>Planted networks found</span><b>{s.found}/{s.planted_networks}</b><small>recall {s.recall}</small></div>
        <div className="tile"><span>Precision</span><b>{s.precision}</b><small>over {s.hits} leads</small></div>
        <div className="tile"><span>Look-alikes fired</span><b>{s.benign_fired}</b><small>designed false positives</small></div>
        <div className="tile"><span>Background false leads</span><b>{s.background_false_leads}</b><small>unplanned</small></div>
        {ev.redteam && (
          <div className="tile"><span>Evasion tactics defeated</span><b>{ev.redteam.closed}</b><small>{ev.redteam.known_limits_confirmed} known limits confirmed</small></div>
        )}
      </div>
      <h3 style={{ margin: '20px 0 10px', fontSize: 15 }}>Per detector</h3>
      <table className="data">
        <thead>
          <tr>
            <th>Detector</th>
            <th>Scope</th>
            <th>Found</th>
            <th>Leads: planted / other planted / look-alike / background</th>
            <th>False leads per 1,000</th>
            <th>Time</th>
          </tr>
        </thead>
        <tbody>
          {ev.detectors.map((r) => (
            <tr key={r.detector}>
              <td>{r.title}</td>
              <td className="small">{r.scope}</td>
              <td>{r.found}/{r.planted}</td>
              <td className="small">{r.hit} / {r.cross} / {r.benign} / {r.background}</td>
              <td className="small">{r.false_leads_per_1000 ?? '—'} <span className="muted">of {r.eligible.toLocaleString('en-IN')} {r.eligible_label}</span></td>
              <td className="small muted">{r.seconds ?? '—'} s</td>
            </tr>
          ))}
        </tbody>
      </table>
      {ev.redteam && (
        <>
          <h3 style={{ margin: '20px 0 6px', fontSize: 15 }}>Adversary simulation</h3>
          <p className="small muted">Each tactic rewrites the planted networks the way an adversary who read the detector's description would, then re-runs every detector.</p>
          <table className="data">
            <thead>
              <tr>
                <th>Tactic</th>
                <th>What it attacks</th>
                <th>Found before → after</th>
                <th>Outcome</th>
              </tr>
            </thead>
            <tbody>
              {ev.redteam.tactics.map((t) => (
                <tr key={t.id}>
                  <td>
                    <b>{t.label}</b>
                    <div className="small muted">{t.change}</div>
                  </td>
                  <td className="small">{t.loophole}</td>
                  <td>{t.before} → {t.after}</td>
                  <td>
                    <Tag intent={t.outcome === 'caught' ? 'success' : 'warning'}>{t.outcome === 'caught' ? 'still caught' : 'evades (known limit)'}</Tag>
                    {!t.as_designed && <Tag intent="danger">unexpected</Tag>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  )
}

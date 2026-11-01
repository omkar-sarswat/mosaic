import { ButtonGroup, HTMLSelect, NonIdealState, Slider, Spinner, Tag } from '@blueprintjs/core'
import { Button } from '../components/Button'
import { CaseStart } from '../components/CaseStart'
import { useEffect, useState } from 'react'
import { intel, type Trace } from '../api'
import FlowDiagram from '../components/FlowDiagram'
import { inr, titleCase } from '../lib/format'
import type { Nav } from './nav'
import { moneyColours } from '../lib/palette'

// Money is blue throughout the app; where it leaves the banking trail is shown in neutrals or orange (abroad).
// Accounts carrying typology alerts take the status colour and are also named as flagged in their label.
const KIND_COLOUR: Record<string, string> = new Proxy({} as Record<string, string>, { get: (_, k) => (moneyColours() as Record<string, string>)[String(k)] })

export default function Money({ root, nav }: { root: string | null; nav: Nav }) {
  const [dir, setDir] = useState<'out' | 'in'>('out')
  const [hops, setHops] = useState(5)
  const [min, setMin] = useState(100000)
  const [t, setT] = useState<Trace | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [byParty, setByParty] = useState(true)

  useEffect(() => {
    if (!root) return
    setBusy(true)
    setErr('')
    intel
      .trace(root, { direction: dir, hops, min_amount: min, window_days: 120 })
      .then(setT)
      .catch((e) => (setErr(e.message), setT(null)))
      .finally(() => setBusy(false))
  }, [root, dir, hops, min])

  if (!root) return (
    <div className="canvas-message">
      <div>
        <NonIdealState icon="bank-account" title="Follow the money" description="Start from a person, company or account: choose “Follow the money” on a dossier or case board, or pick someone below." />
        <CaseStart nav={nav} title="People in the active case" action="Follow the money" onPick={nav.openTrace} />
      </div>
    </div>
  )

  return (
    <div className="page">
      <div className="money-controls">
        <ButtonGroup>
          <Button icon="arrow-right" active={dir === 'out'} onClick={() => setDir('out')}>
            Where it went
          </Button>
          <Button icon="arrow-left" active={dir === 'in'} onClick={() => setDir('in')}>
            Where it came from
          </Button>
        </ButtonGroup>
        <label>Hops
          <Slider min={1} max={8} value={hops} onChange={setHops} labelStepSize={1} />
        </label>
        <label>Ignore transfers below
          <HTMLSelect value={min} onChange={(e) => setMin(Number(e.target.value))}>
            {[10000, 50000, 100000, 500000, 1000000].map((v) => (
              <option key={v} value={v}>
                {inr(v)}
              </option>
            ))}
          </HTMLSelect>
        </label>
        {busy && <Spinner size={16} />}
        <Button minimal icon="person" onClick={() => nav.openEntity(root)} style={{ marginLeft: 'auto' }}>
          Back to dossier
        </Button>
      </div>
      {err && <div className="notice">{err}</div>}
      {t && (
        <div className="grid3">
          <section className="card span-2">
            <h4>
              Funds traced {dir === 'out' ? 'onward' : 'to their sources'} <span className="muted">{t.accounts_reached} accounts · {inr(t.traced_total)} from the start</span>
            </h4>
            <div className="row" style={{ gap: 6, margin: '4px 0 8px' }}>
              <ButtonGroup>
                <Button small active={byParty} onClick={() => setByParty(true)}>By party</Button>
                <Button small active={!byParty} onClick={() => setByParty(false)}>By account</Button>
              </ButtonGroup>
              <span className="muted small">{byParty ? 'Each bar is a person or company; their accounts are combined.' : 'Each bar is one account.'} Hover a bar to isolate its flows.</span>
            </div>
            <FlowDiagram trace={t} byParty={byParty} onOpen={(h) => nav.openEntity(h)} />
            <div className="muted small">
              Value is apportioned hop by hop in time order (only transfers made after the money arrived, within 120 days). Bars outlined in red carry typology alerts (also written “flagged”). Each transfer has its own slot on a bar, so lines never merge. Click a bar to open its holder.
            </div>
          </section>
          <section className="card">
            <h4>End points</h4>
            {!Object.keys(t.sinks).length && <p className="muted small">No end points reached within these limits.</p>}
            {Object.entries(t.sinks).map(([k, v]) => (
              <div key={k} className="kv-row">
                <span><i className="ln" style={{ background: KIND_COLOUR[k] }} />{titleCase(k)}</span><span className="amount">{inr(v)}</span>
              </div>
            ))}
            <h4 style={{ marginTop: 18 }}>{dir === 'out' ? 'Recipients' : 'Originators'} by traced value</h4>
            {!t.beneficiaries.length && <p className="muted small">None within these limits.</p>}
            {t.beneficiaries.map((b) => (
              <button key={b.id} className="kv-row" onClick={() => nav.openEntity(b.id)}>
                <span className="grow">
                  {b.name} <span className="muted small">{b.type}</span>
                </span>
                <span className="amount">{inr(b.amount)}</span>
              </button>
            ))}
            <h4 style={{ marginTop: 18 }}>Flagged accounts on the trail</h4>
            {!t.nodes.some((n) => n.alerts.length) && <p className="muted small">No account on this trail carries a typology alert.</p>}
            {t.nodes
              .filter((n) => n.alerts.length)
              .map((n) => (
                <button key={n.id} className="kv-row small" disabled={!n.holder} onClick={() => n.holder && nav.openEntity(n.holder)}>
                  <b>{n.holder_name}</b> {n.alerts.map((a) => (
                    <Tag key={a} minimal intent="danger" style={{ marginRight: 3 }}>
                      {titleCase(a)}
                    </Tag>
                  ))}
                </button>
              ))}
          </section>
        </div>
      )}
    </div>
  )
}

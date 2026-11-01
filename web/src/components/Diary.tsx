// Shared case pieces: the active-case control, human decisions, evidence marks, Indian-time dates.
import { HTMLSelect, Icon } from '@blueprintjs/core'
import { Button } from './Button'
import { Popover } from '@mantine/core'
import type { CaseRow } from '../api'

const IST = 'Asia/Kolkata'

/** "16 Oct 12:50" in Indian time; the year only when it is not this year. */
export function diaryTime(iso: string | null | undefined): { day: string; time: string } {
  if (!iso) return { day: '', time: '' }
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return { day: iso.slice(0, 10), time: '' }
  const sameYear = d.getFullYear() === new Date().getFullYear()
  const day = d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', ...(sameYear ? {} : { year: 'numeric' }), timeZone: IST })
  const time = d.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: false, timeZone: IST })
  return { day, time }
}

/** dd.mm.yyyy, as dates are written in a case diary */
export function docketDate(iso: string | null | undefined): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso.slice(0, 10)
  return d.toLocaleDateString('en-GB', { timeZone: IST }).replaceAll('/', '.')
}

const DECISION_LABEL: Record<string, string> = {
  approved: 'Approved', rejected: 'Rejected', dismissed: 'Dismissed', reverted: 'Reverted', pending: 'Awaiting approval', proposed: 'Proposed',
}

/** A human decision, drawn as a dated rubber stamp naming the officer. */
export function Stamp({ decision, by, at, inline = false }: { decision: string; by?: string | null; at?: string | null; inline?: boolean }) {
  const label = DECISION_LABEL[decision] ?? decision
  const when = at ? docketDate(at) : ''
  return (
    <span className={`stamp ${decision} ${inline ? 'inline' : ''}`} role="img" aria-label={`${label}${by ? ` by ${by}` : ''}${when ? ` on ${when}` : ''}`}>
      {label}
      {!inline && (by || when) && <small>{[by, when].filter(Boolean).join(' · ')}</small>}
    </span>
  )
}

const MARK_LABEL: Record<string, string> = {
  corroborated: 'Corroborated', single: 'Single source', proposed: 'Machine proposal', suggested: 'Machine proposal',
  pending: 'Waiting for a second officer', critical: 'Alarm', flagged: 'Flagged', approved: 'Approved', rejected: 'Refused', dismissed: 'Dismissed', new: 'New',
}

/** How sure a fact is, or where a request stands: a short rule in the evidence style plus words. */
export function Mark({ kind, label }: { kind: string; label?: string }) {
  return <span className={`mark ${kind}`}>{label ?? MARK_LABEL[kind] ?? kind}</span>
}

type CaseFull = CaseRow & { title?: string; agency?: string; opened_at?: string }

/** The active case, beside the tools: every look-up is recorded against it. Switching here re-scopes the
 * whole workspace; with no case chosen, personal records stay hidden. */
export function CaseContext({ cases, caseId, onChoose, onNewCase }: {
  cases: CaseFull[]; caseId: string; onChoose: (id: string) => void; onNewCase?: () => void
}) {
  const open = cases.filter((c) => c.status === 'open')
  const active = open.find((c) => c.id === caseId)
  if (!open.length && !onNewCase) return null
  return (
    <section className={`case-context ${active ? '' : 'no-case'}`} aria-label="Active case">
      <label className="case-context-label" htmlFor="active-case">Case</label>
      <HTMLSelect id="active-case" value={caseId} onChange={(e) => onChoose(e.target.value)} title={active?.title ?? 'Choose a case'}>
        <option value="">{open.length ? 'Choose a case' : 'No open cases'}</option>
        {open.map((c) => <option key={c.id} value={c.id}>{c.title || c.purpose.replaceAll('_', ' ')}</option>)}
      </HTMLSelect>
      {active ? <span className="case-context-id">{active.id}</span> : <span className="case-status"><span />Personal records hidden</span>}
      {active && <Popover position="bottom-end" withinPortal trapFocus returnFocus>
        <Popover.Target><button className="icon-button" aria-label="Case details" title="Case details"><Icon icon="info-sign" size={15} /></button></Popover.Target>
        <Popover.Dropdown className="workspace-popover case-popover">
          <h2>{active.title || active.purpose.replaceAll('_', ' ')}</h2>
          <p className="mono">{active.id}</p>
          <dl><dt>Purpose</dt><dd>{active.purpose.replaceAll('_', ' ')}</dd><dt>Legal basis</dt><dd>{active.legal_basis}</dd>{active.opened_at && <><dt>Opened</dt><dd>{docketDate(active.opened_at)}</dd></>}</dl>
        </Popover.Dropdown>
      </Popover>}
      {onNewCase && <Button className="new-case-button" small icon="plus" aria-label="New case" onClick={onNewCase}><span className="button-text">New case</span></Button>}
    </section>
  )
}

/** The Weirwood mark: light tiles and the red tile, for the dark application bar. */
export function Logo() {
  return <img className="brand-mark" src="/brand/weirwood-mark-light.png" alt="" aria-hidden width="30" height="30" />
}

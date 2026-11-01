import { Icon, Spinner } from '@blueprintjs/core'
import { Table, TextInput } from '@mantine/core'
import { useMediaQuery } from '@mantine/hooks'
import { Button } from '../components/Button'
import { useEffect, useMemo, useState } from 'react'
import { api, type Today as TodayData, type TodayEntry } from '../api'
import { diaryTime, Mark, Stamp } from '../components/Diary'
import { PersonAvatar } from '../components/PersonPhoto'
import { sentence } from '../lib/format'
import { Emph } from '../components/Emph'
import type { Nav, ViewId } from './nav'

// What each role reads first, and how its diary is titled.
const HEADINGS: Record<string, { title: string; empty: string }> = {
  io: { title: 'Needs attention', empty: 'No pending work. New leads, requests, and decisions will appear here.' },
  supervisor: { title: 'Needs your decision', empty: 'No request is waiting for you. When an officer asks to widen a case, open one from a lead or publish an extract, it lands here.' },
  analyst: { title: 'Lead queue', empty: 'No open leads in your agency’s mission tracks. New patterns appear here after each run of the pattern engine.' },
  steward: { title: 'Matches to review', empty: 'No record matches are waiting. Proposed matches between sources appear here for a person to confirm or reject.' },
  auditor: { title: 'Oversight trail', empty: 'No alarms. Reads of canary records, bursts of refused requests and bulk personal look-ups appear here.' },
}
const FILTERS: { kind: TodayEntry['kind'] | 'all'; label: string }[] = [
  { kind: 'all', label: 'All' }, { kind: 'approval', label: 'Approvals' }, { kind: 'request', label: 'My requests' }, { kind: 'lead', label: 'Leads' },
  { kind: 'watch', label: 'Watchlist' }, { kind: 'search', label: 'Saved searches' },
  { kind: 'match', label: 'Matches' }, { kind: 'alarm', label: 'Alarms' }, { kind: 'denied', label: 'Refusals' },
]
const ACTION: Record<TodayEntry['kind'], string> = { approval: 'Decide', request: 'View', lead: 'Evaluate', match: 'Review', alarm: 'Inspect', denied: 'Inspect', watch: 'Review', search: 'Review' }


export default function Today({ nav, onNewCase }: { nav: Nav; onNewCase?: () => void }) {
  const [data, setData] = useState<TodayData | null>(null)
  const [error, setError] = useState('')
  const [filter, setFilter] = useState<TodayEntry['kind'] | 'all'>('all')
  const [reload, setReload] = useState(0)
  const [query, setQuery] = useState('')
  const narrow = useMediaQuery('(max-width: 760px)')
  const [today] = useState(() => new Intl.DateTimeFormat('en-IN', { weekday: 'long', day: 'numeric', month: 'long', timeZone: 'Asia/Kolkata' }).format(new Date()))

  useEffect(() => {
    let current = true
    setError('')
    api.today().then((d) => { if (current) setData(d) }).catch((e) => { if (current) setError(e.message) })
    return () => { current = false }
  }, [nav.tick, nav.caseId, reload])

  const counts = useMemo(() => {
    const c: Record<string, number> = {}
    for (const e of data?.entries ?? []) c[e.kind] = (c[e.kind] ?? 0) + 1
    return c
  }, [data])

  if (!data) {
    return (
      <div className="app-loading" role="status">
        {error ? <><Icon icon="offline" size={26} /><h2>Your day could not be loaded</h2><p>{error}</p><Button onClick={() => setReload((n) => n + 1)}>Try again</Button></>
          : <><Spinner size={22} /><h2>Loading overview</h2><p>Retrieving pending work and case records.</p></>}
      </div>
    )
  }

  const heading = HEADINGS[data.role] ?? { title: 'Today', empty: 'Nothing is waiting.' }
  const shown = data.entries.filter((entry) => (filter === 'all' || entry.kind === filter) && `${entry.title} ${entry.ref} ${entry.detail}`.toLowerCase().includes(query.toLowerCase()))
  const go = (e: TodayEntry) => {
    if (e.kind === 'alarm' || e.kind === 'denied') nav.go('oversight')
    else if (e.view === 'cases' && e.target) nav.openCase(e.target)
    else nav.open(e.view as ViewId, e.target)
  }
  const c = data.counts
  const roles = nav.me?.roles ?? []
  const investigates = roles.some((r) => ['io', 'supervisor', 'analyst'].includes(r))
  const reviews = roles.some((r) => ['analyst', 'supervisor', 'steward'].includes(r))
  // the case summary is for people who work cases; oversight, operators and analysts outside a case read the queue full width
  const showBrief = !!data.case || !!onNewCase

  return (
    <div className="workbench-home">
      <header className="day-heading">
        <div><h1>Work queue</h1><p>{today} · {data.person.name}</p></div>
        <div className="day-actions"><Button minimal icon="refresh" aria-label="Refresh work queue" onClick={() => setReload((value) => value + 1)}><span className="button-text">Refresh</span></Button></div>
      </header>
      {error && <div className="notice" role="alert">The queue could not be refreshed. {error}<Button small minimal onClick={() => setReload((value) => value + 1)}>Retry</Button></div>}
      <div className={`workbench-columns ${showBrief ? '' : 'single'}`}>
        <div className="register-column">
          <section className="work-register" aria-labelledby="queue-title">
            <div className="register-heading"><h2 id="queue-title">{heading.title}<span>{data.entries.length}</span></h2><TextInput className="queue-search" aria-label="Filter work queue" placeholder="Find in queue" value={query} onChange={(event) => setQuery(event.target.value)} leftSection={<Icon icon="search" size={13} />} /></div>
            <div className="register-filters" role="group" aria-label="Work categories">{FILTERS.filter((item) => item.kind === 'all' || counts[item.kind]).map((item) => <button key={item.kind} aria-pressed={filter === item.kind} onClick={() => setFilter(item.kind)}>{item.label}<span>{item.kind === 'all' ? data.entries.length : counts[item.kind]}</span></button>)}</div>
            <Table.ScrollContainer minWidth={narrow ? 0 : 640} className="queue-scroll">
              <Table className="queue-table" highlightOnHover>
                <Table.Thead><Table.Tr><Table.Th>Reference</Table.Th><Table.Th>Item</Table.Th><Table.Th>Status</Table.Th><Table.Th>Received</Table.Th><Table.Th><span className="sr-only">Action</span></Table.Th></Table.Tr></Table.Thead>
                <Table.Tbody>{shown.map((entry) => {
                  const time = diaryTime(entry.at)
                  return <Table.Tr key={`${entry.kind}:${entry.id}`}><Table.Td className="queue-ref">{entry.ref}</Table.Td><Table.Td><button className="queue-subject" onClick={() => go(entry)}>{entry.title}</button><div className="queue-detail"><Emph text={entry.detail.replaceAll('_', ' ')} terms={[/^\d+ to read first/.exec(entry.detail)?.[0]]} /></div></Table.Td><Table.Td><Mark kind={entry.mark} /></Table.Td><Table.Td className="queue-time">{entry.at ? <time dateTime={entry.at}>{time.day}<small>{time.time}</small></time> : <span>Undated</span>}</Table.Td><Table.Td><Button small minimal rightIcon="arrow-right" aria-label={`${ACTION[entry.kind]}: ${entry.title}`} onClick={() => go(entry)}>{ACTION[entry.kind]}</Button></Table.Td></Table.Tr>
                })}</Table.Tbody>
              </Table>
            </Table.ScrollContainer>
            {!shown.length && <div className="register-empty"><h3>{query || filter !== 'all' ? 'No matching items' : 'Nothing pending'}</h3><p>{query ? 'Try a different name or reference.' : heading.empty}</p>{(filter !== 'all' || query) && <Button small onClick={() => { setFilter('all'); setQuery('') }}>Clear filters</Button>}</div>}
            <div className="register-footer"><span>{shown.length} of {data.entries.length} items</span><span>Times in IST</span></div>
          </section>
          <div className="work-totals" aria-label="Elsewhere in your workspace">
            {investigates && <button onClick={() => nav.go('leads')}><b>{c.leads_open}</b><span>open leads</span><Icon icon="arrow-right" size={12} /></button>}
            {reviews && <button onClick={() => nav.go('review')}><b>{c.review_pending}</b><span>record matches to review</span><Icon icon="arrow-right" size={12} /></button>}
            {c.alarms > 0 && <button onClick={() => nav.go('oversight')}><b>{c.alarms}</b><span>critical oversight alarms</span><Icon icon="arrow-right" size={12} /></button>}
          </div>
          <section className="decision-register" aria-labelledby="decisions-title"><div className="register-heading"><h2 id="decisions-title">Recent decisions<span>{data.stamps.length}</span></h2></div>{!data.stamps.length && <p className="register-note">No decisions recorded yet. Approvals and refusals by a second officer appear here.</p>}{data.stamps.map((decision) => <div className="decision-line" key={`${decision.ref}:${decision.at}`}><Stamp decision={decision.decision} by={decision.by_name} at={decision.at} /><div><p>{decision.what}</p><small>{decision.requested_by ? `Requested by ${decision.requested_by}` : decision.ref}</small></div></div>)}</section>
        </div>
        {showBrief && <aside className="case-brief" aria-label="Active case">
          {data.case ? <>
            <h2>{data.case.title}</h2>
            <div className="brief-meta"><span className="case-status"><span />Open</span><span className="mono">{data.case.id}</span><span>{sentence(data.case.purpose)}</span></div>
            <p className="brief-purpose">{data.case.opened_by_name ? `Opened by ${data.case.opened_by_name}` : ''}{data.case.opened_by_name && data.case.members.length > 1 ? ` · ${data.case.members.length} members` : ''}</p>
            <Button className="brief-open" intent="primary" rightIcon="arrow-right" onClick={() => nav.openCase(data.case!.id)}>Open case board</Button>
            <div className="brief-tools"><button onClick={() => nav.go('graph')}>Network</button><button onClick={() => nav.go('money')}>Money trail</button><button onClick={() => nav.go('globe')}>Map</button></div>
            <section className="brief-section"><h3>People<span>{data.case.people}</span></h3>{data.case.subjects.length ? data.case.subjects.map((subject) => <button className="brief-person" key={subject.id} onClick={() => nav.openEntity(subject.id)}><PersonAvatar id={subject.id} name={subject.name} size={36} /><span><b>{subject.name}</b><small>{subject.accused_in ? `Accused in ${subject.accused_in} FIR${subject.accused_in > 1 ? 's' : ''}` : 'Subject'}</small></span><Icon icon="chevron-right" size={12} /></button>) : <p>No people added yet.</p>}</section>
            <section className="brief-section"><h3>Evidence<span>{data.case.evidence_count}</span></h3>{data.case.evidence.length ? data.case.evidence.map((item) => <button className="brief-evidence" key={item.id} onClick={() => nav.openCase(data.case!.id)}><Icon icon="document" size={14} /><span>{item.filename}<small>{item.source_type || 'Exhibit'} · {item.status}</small></span></button>) : <p>No exhibits recorded.</p>}<Button small minimal icon="plus" onClick={() => nav.openCase(data.case!.id)}>Add evidence</Button></section>
            <details className="brief-basis"><summary>Legal basis</summary><p>{data.case.legal_basis}</p></details>
          </> : <>
            <h2>No case selected</h2>
            <p className="brief-purpose">Personal records stay hidden until you work inside a case. Choose one in the case bar above{onNewCase ? ', or open a new one' : ''}.</p>
            {onNewCase && <Button intent="primary" icon="plus" onClick={onNewCase}>Open a case</Button>}
          </>}
        </aside>}
      </div>
    </div>
  )
}

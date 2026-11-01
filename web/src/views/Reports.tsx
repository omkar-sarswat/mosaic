import { Checkbox, Icon, NonIdealState, Spinner } from '@blueprintjs/core'
import { Modal, Select, Table, TextInput, Textarea } from '@mantine/core'
import { useCallback, useEffect, useRef, useState } from 'react'
import { reports, saveResponse, type BlockView, type Cite, type ReportBlock, type ReportMeta, type ReportSources, type ReportTemplate } from '../api'
import { Button } from '../components/Button'
import { diaryTime } from '../components/Diary'
import { MarkingChip } from '../components/Marking'
import { MARKINGS, noteMarking } from '../lib/marking'
import { day, sentence } from '../lib/format'
import type { Nav } from './nav'

const newId = () => 'b' + Math.random().toString(16).slice(2, 10)
const BLOCK_LABEL: Record<ReportBlock['type'], string> = {
  heading: 'Section heading', text: 'Text', record: 'Record', exhibit: 'Exhibit', lead: 'Pattern lead', area: 'Area search', relations: 'Links between records',
}
const SHOW: { key: 'identity' | 'links' | 'history'; label: string }[] = [
  { key: 'identity', label: 'Particulars' }, { key: 'links', label: 'Phones, accounts, addresses' }, { key: 'history', label: 'Criminal history' },
]

/** Reports of a case: case diary entries, chargesheet annexures and intelligence summaries. */
export default function Reports({ caseId, nav }: { caseId: string; nav: Nav }) {
  const [list, setList] = useState<{ reports: ReportMeta[]; templates: ReportTemplate[] } | null>(null)
  const [err, setErr] = useState('')
  const [open, setOpen] = useState<string | null>(null)
  const [creating, setCreating] = useState<string | null>(null)
  const load = useCallback(() => {
    setErr('')
    reports.list(caseId).then(setList).catch((e) => setErr(e.message))
  }, [caseId])
  useEffect(() => { load() }, [load, nav.tick])

  if (caseId !== nav.caseId) return <NonIdealState icon="swap-horizontal" title="Switch to this case to write its reports" description="Reports read records under the case's purpose, so they are written inside the case. Choose it in the case bar above." />
  if (err) return <NonIdealState icon="lock" title="Reports not available" description={err} />
  if (!list) return <div className="app-loading" role="status"><Spinner size={20} /></div>
  if (open) return <ReportEditor id={open} caseId={caseId} nav={nav} onClose={() => { setOpen(null); load() }} />

  const create = (template: string) => {
    setCreating(template)
    reports.create(caseId, template).then((r) => setOpen(r.id)).catch((e) => nav.setError(e.message)).finally(() => setCreating(null))
  }
  return (
    <div className="reports">
      <section className="report-templates" aria-label="Start a report">
        {list.templates.map((t) => (
          <article key={t.id} className="report-template">
            <h3>{t.title}</h3>
            <p className="report-basis">{t.basis}</p>
            <p>{t.description}</p>
            <Button small icon="add" loading={creating === t.id} onClick={() => create(t.id)}>Start {t.title.split(':')[0].toLowerCase()}</Button>
          </article>
        ))}
      </section>
      <section className="work-section">
        <div className="section-heading"><div><h2>Reports in this case</h2><p>Drafts update from the records each time they are opened; an exported copy is fixed, hashed and logged.</p></div></div>
        {list.reports.length ? (
          <Table className="queue-table" highlightOnHover>
            <Table.Thead><Table.Tr><Table.Th>Report</Table.Th><Table.Th>Kind</Table.Th><Table.Th>Last edited</Table.Th><Table.Th>Exported</Table.Th></Table.Tr></Table.Thead>
            <Table.Tbody>
              {list.reports.map((r) => (
                <Table.Tr key={r.id}>
                  <Table.Td><button className="queue-subject" onClick={() => setOpen(r.id)}>{r.title}</button><div className="queue-detail">{r.blocks} parts · started by {r.created_by_name}</div></Table.Td>
                  <Table.Td>{r.template_title}</Table.Td>
                  <Table.Td className="queue-time"><time dateTime={r.updated_at}>{diaryTime(r.updated_at).day}<small>{r.updated_by_name}</small></time></Table.Td>
                  <Table.Td>{r.exports ? `${r.exports.count} cop${r.exports.count === 1 ? 'y' : 'ies'}, last ${day(r.exports.last)}` : <span className="muted">Draft</span>}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        ) : <div className="register-empty"><h3>No reports yet</h3><p>Start one above. Each starts with the case's people and the sections the document needs.</p></div>}
      </section>
    </div>
  )
}

function ReportEditor({ id, caseId, nav, onClose }: { id: string; caseId: string; nav: Nav; onClose: () => void }) {
  const [meta, setMeta] = useState<ReportMeta | null>(null)
  const [title, setTitle] = useState('')
  const [blocks, setBlocks] = useState<ReportBlock[]>([])
  const [marking, setMarking] = useState(1)
  const [template, setTemplate] = useState<ReportTemplate | null>(null)
  const [sources, setSources] = useState<ReportSources | null>(null)
  const [dirty, setDirty] = useState(false)
  const [resolve, setResolve] = useState(false)
  const [saving, setSaving] = useState(false)
  const [savedAt, setSavedAt] = useState<string | null>(null)
  const [conflict, setConflict] = useState('')
  const [err, setErr] = useState('')
  const [exporting, setExporting] = useState(false)
  const [cursor, setCursor] = useState<string | null>(null)
  const version = useRef(0)
  const latest = useRef({ title, blocks })
  latest.current = { title, blocks }

  const load = useCallback(() => reports.get(id).then((r) => {
    setMeta(r.report)
    setTitle(r.report.title)
    setBlocks(r.blocks)
    setMarking(r.marking)
    noteMarking(r.marking)
    setTemplate(r.template)
    version.current = r.report.version
    setDirty(false)
    setConflict('')
  }).catch((e) => setErr(e.message)), [id])
  useEffect(() => { load() }, [load])
  useEffect(() => { reports.sources(caseId).then(setSources).catch(() => setSources(null)) }, [caseId])

  const save = useCallback(async (andResolve: boolean) => {
    setSaving(true)
    try {
      const m = await reports.save(id, { title: latest.current.title, blocks: latest.current.blocks, version: version.current })
      version.current = m.version
      setMeta(m)
      setSavedAt(m.updated_at)
      setDirty(false)
      if (andResolve) {
        const fresh = await reports.get(id)
        version.current = fresh.report.version
        setMarking(fresh.marking)
        noteMarking(fresh.marking)
        setBlocks((cur) => cur.map((b) => ({ ...b, view: fresh.blocks.find((f) => f.id === b.id)?.view ?? b.view })))
      }
    } catch (e) {
      const msg = (e as Error).message
      if ((e as { status?: number }).status === 409) setConflict(msg)
      else nav.setError(msg)
    } finally {
      setSaving(false)
      setResolve(false)
    }
  }, [id, nav])

  // drafts save themselves a moment after the last change; inserting a reference also reads it afresh
  useEffect(() => {
    if (!dirty || conflict) return
    const t = setTimeout(() => save(resolve), resolve ? 150 : 1200)
    return () => clearTimeout(t)
  }, [dirty, resolve, blocks, title, conflict, save])

  if (err) return <NonIdealState icon="lock" title="Report not available" description={err} action={<Button onClick={onClose}>All reports</Button>} />
  if (!meta) return <div className="app-loading" role="status"><Spinner size={20} /></div>

  const change = (next: ReportBlock[], needsResolve = false) => {
    setBlocks(next)
    setDirty(true)
    if (needsResolve) setResolve(true)
  }
  const update = (bid: string, patch: Partial<ReportBlock>, needsResolve = false) => change(blocks.map((b) => (b.id === bid ? { ...b, ...patch } : b)), needsResolve)
  const insert = (b: Omit<ReportBlock, 'id'>) => {
    const block = { ...b, id: newId() } as ReportBlock
    const at = cursor ? blocks.findIndex((x) => x.id === cursor) + 1 : blocks.length
    const next = [...blocks.slice(0, at), block, ...blocks.slice(at)]
    setCursor(block.id)
    change(next, !['text', 'heading'].includes(block.type))
  }
  const move = (bid: string, by: number) => {
    const i = blocks.findIndex((b) => b.id === bid)
    const j = i + by
    if (j < 0 || j >= blocks.length) return
    const next = [...blocks]
    ;[next[i], next[j]] = [next[j], next[i]]
    change(next)
  }
  const remove = (bid: string) => change(blocks.filter((b) => b.id !== bid), true)
  const inReport = new Set(blocks.flatMap((b) => [b.object_id, b.evidence_id, b.lead_id, b.search_id].filter(Boolean) as string[]))

  return (
    <div className="report-editor">
      <header className="report-bar">
        <Button minimal small icon="arrow-left" onClick={() => (dirty ? save(false).then(onClose) : onClose())}>All reports</Button>
        <div className="report-status">
          <MarkingChip level={marking} />
          <span>{saving ? 'Saving…' : dirty ? 'Unsaved changes' : savedAt ? `Saved ${diaryTime(savedAt).time}` : `Version ${meta.version}`}</span>
        </div>
        <div className="report-actions">
          <Button small icon="floppy-disk" disabled={!dirty || saving} onClick={() => save(true)}>Save</Button>
          <Button small intent="primary" icon="document-share" onClick={() => (dirty ? save(true).then(() => setExporting(true)) : setExporting(true))}>Export PDF</Button>
          {meta.created_by === nav.me?.id && <Button small minimal icon="trash" onClick={() => reports.discard(id).then(onClose).catch((e) => nav.setError(e.message))}>Discard draft</Button>}
        </div>
      </header>
      {conflict && <div className="notice report-conflict" role="alert">{conflict}<Button small onClick={() => load()}>Reload</Button></div>}
      <div className="report-columns">
        <article className="report-sheet" aria-label="Report">
          <div className="report-kicker">{template?.title}{template?.basis ? ` · ${template.basis}` : ''}</div>
          <input className="report-title" aria-label="Report title" value={title} onChange={(e) => { setTitle(e.target.value); setDirty(true) }} />
          <p className="report-byline">Started by {meta.created_by_name} on {day(meta.created_at)} · last edited by {meta.updated_by_name}</p>
          {blocks.map((b, i) => (
            <section key={b.id} className={`report-block rb-${b.type} ${cursor === b.id ? 'is-cursor' : ''}`} onFocusCapture={() => setCursor(b.id)} onClick={() => setCursor(b.id)}>
              <div className="rb-tools">
                <span>{BLOCK_LABEL[b.type]}</span>
                <button aria-label="Move up" disabled={i === 0} onClick={() => move(b.id, -1)}><Icon icon="arrow-up" size={12} /></button>
                <button aria-label="Move down" disabled={i === blocks.length - 1} onClick={() => move(b.id, 1)}><Icon icon="arrow-down" size={12} /></button>
                <button aria-label={`Remove ${BLOCK_LABEL[b.type].toLowerCase()}`} onClick={() => remove(b.id)}><Icon icon="cross" size={12} /></button>
              </div>
              <BlockBody b={b} nav={nav} onChange={(patch, r) => update(b.id, patch, r)} />
            </section>
          ))}
          {!blocks.length && <p className="muted">Empty report. Add text, records and exhibits from the panel.</p>}
        </article>
        <aside className="report-insert" aria-label="Insert into the report">
          <h3>Insert{cursor ? ' after the selected part' : ' at the end'}</h3>
          <div className="insert-basic">
            <Button small icon="header" onClick={() => insert({ type: 'heading', text: 'New section' })}>Heading</Button>
            <Button small icon="paragraph" onClick={() => insert({ type: 'text', text: '' })}>Text</Button>
            <Button small icon="graph" onClick={() => insert({ type: 'relations' })}>Links between records</Button>
          </div>
          {!sources && <Spinner size={16} />}
          {sources && <>
            <InsertList title="Records in the case" empty="No records in the case scope yet." items={sources.records.map((r) => ({ id: r.id, label: r.title, meta: sentence(r.type), level: r.sensitivity }))}
              used={inReport} onInsert={(oid) => insert({ type: 'record', object_id: oid, show: ['identity', 'links', 'history'], note: '' })} />
            <InsertList title="Exhibits" empty="No exhibits in the evidence register." items={sources.exhibits.map((e) => ({ id: e.id, label: e.filename, meta: e.source_type ?? 'Exhibit' }))}
              used={inReport} onInsert={(eid) => insert({ type: 'exhibit', evidence_id: eid, note: '' })} />
            <InsertList title="Pattern leads" empty="No pattern lead is tied to this case." items={sources.leads.map((l) => ({ id: l.id, label: l.title, meta: `${sentence(l.severity)} severity` }))}
              used={inReport} onInsert={(lid) => insert({ type: 'lead', lead_id: lid, note: '' })} />
            <InsertList title="Area searches" empty="Searches made on the map appear here." items={sources.areas.map((a) => ({ id: a.id, label: `${a.radius_km} km around ${a.label}`, meta: `${a.start_ts} to ${a.end_ts}` }))}
              used={inReport} onInsert={(sid) => insert({ type: 'area', search_id: sid, note: '' })} />
          </>}
        </aside>
      </div>
      <ExportDialog opened={exporting} onClose={() => setExporting(false)} reportId={id} nav={nav} marking={marking} />
    </div>
  )
}

function InsertList({ title, items, used, empty, onInsert }: { title: string; items: { id: string; label: string; meta: string; level?: number }[]; used: Set<string>; empty: string; onInsert: (id: string) => void }) {
  return (
    <section className="insert-group">
      <h4>{title}<span className="count">{items.length}</span></h4>
      {items.length ? (
        <ul>
          {items.map((x) => (
            <li key={x.id}>
              <button onClick={() => onInsert(x.id)} disabled={used.has(x.id)} title={used.has(x.id) ? 'Already in the report' : `Insert ${x.label}`}>
                <span>{x.label}<small>{x.meta}</small></span>
                {used.has(x.id) ? <Icon icon="tick" size={12} /> : <Icon icon="plus" size={12} />}
              </button>
            </li>
          ))}
        </ul>
      ) : <p className="muted small">{empty}</p>}
    </section>
  )
}

function Sources({ cites }: { cites: Cite[] }) {
  const names = [...new Set(cites.map((c) => c.source_name))]
  if (!names.length) return <span className="muted">No source</span>
  return <span className="rb-sources" title={cites.map((c) => `${c.source_name}: ${c.record ?? ''}`).join('\n')}>{names.join('; ')}</span>
}

function Unavailable({ v, kind }: { v: BlockView; kind: string }) {
  return <p className="rb-withheld"><Icon icon="lock" size={12} />This {kind} will not print: {v.withheld ?? v.missing}.</p>
}

function BlockBody({ b, nav, onChange }: { b: ReportBlock; nav: Nav; onChange: (patch: Partial<ReportBlock>, resolve?: boolean) => void }) {
  const v = b.view
  const note = (
    <Textarea className="rb-note" size="xs" autosize minRows={1} placeholder="Officer's note on this item (prints below it)" aria-label="Note"
      value={b.note ?? ''} onChange={(e) => onChange({ note: e.target.value })} />
  )
  if (b.type === 'heading') return <TextInput className="rb-heading" aria-label="Section heading" value={b.text ?? ''} onChange={(e) => onChange({ text: e.target.value })} />
  if (b.type === 'text') return <Textarea className="rb-text" aria-label="Text" autosize minRows={2} placeholder={b.hint || 'Write here'} value={b.text ?? ''} onChange={(e) => onChange({ text: e.target.value })} />
  if (!v) return <p className="muted small"><Spinner size={12} /> Reading the record…</p>
  if (v.withheld || v.missing) return <Unavailable v={v} kind={BLOCK_LABEL[b.type].toLowerCase()} />
  if (b.type === 'record' && v.record) {
    const show = b.show ?? ['identity', 'links', 'history']
    return (
      <>
        <div className="rb-record-head">
          <button className="elink" onClick={() => nav.openEntity(v.record!.id)}>{v.record.title}</button>
          <span className="muted small">{sentence(v.record.type)}</span>
          <MarkingChip level={v.record.sensitivity} />
        </div>
        <div className="rb-show" role="group" aria-label="What to print">
          {SHOW.map((s) => <Checkbox key={s.key} inline label={s.label} checked={show.includes(s.key)}
            onChange={() => onChange({ show: show.includes(s.key) ? show.filter((x) => x !== s.key) : [...show, s.key] }, true)} />)}
        </div>
        {show.includes('identity') && v.facts && v.facts.length > 0 && (
          <table className="rb-facts">
            <tbody>{v.facts.map((f) => <tr key={f.label}><th>{f.label}</th><td>{f.value}{f.masked && <span className="muted"> (masked)</span>}</td><td><Sources cites={f.cites} /></td></tr>)}</tbody>
          </table>
        )}
        {show.includes('links') && v.groups?.map((g) => (
          <p key={g.label} className="rb-group"><b>{g.label}</b>{g.items.map((it, i) => <span key={it.id}>{i ? '; ' : ''}<button className="elink" onClick={() => nav.openEntity(it.id)}>{it.label}</button>{it.detail ? ` (${it.detail})` : ''}</span>)}</p>
        ))}
        {show.includes('history') && v.history && v.history.length > 0 && (
          <table className="rb-facts rb-history">
            <thead><tr><th>FIR</th><th>Role</th><th>Date</th><th>Particulars</th></tr></thead>
            <tbody>{v.history.map((h) => <tr key={h.id + h.role}><td><button className="elink" onClick={() => nav.openEntity(h.id)}>{h.label}</button></td><td>{h.role}</td><td>{h.at}</td><td>{h.detail}</td></tr>)}</tbody>
          </table>
        )}
        {note}
      </>
    )
  }
  if (b.type === 'exhibit' && v.exhibit) {
    const e = v.exhibit
    return (
      <>
        <div className="rb-record-head"><b>{e.filename}</b><span className="muted small">{e.source_type ?? 'Exhibit'}</span></div>
        <dl className="rb-kv">
          <div><dt>Description</dt><dd>{e.description || '-'}</dd></div>
          <div><dt>SHA-256</dt><dd className="mono">{e.sha256}</dd></div>
          <div><dt>Seized from</dt><dd>{e.seized_from || '-'}</dd></div>
          <div><dt>Order</dt><dd>{e.legal_order || '-'}</dd></div>
          <div><dt>Custody</dt><dd>{e.custody_events} recorded event{e.custody_events === 1 ? '' : 's'} · {e.status}</dd></div>
        </dl>
        {note}
      </>
    )
  }
  if (b.type === 'lead' && v.lead) {
    return (
      <>
        <div className="rb-record-head"><b>{v.lead.title}</b><span className={`small sev-${v.lead.severity}`}>{sentence(v.lead.severity)} severity</span></div>
        <p className="small">{v.lead.summary}</p>
        <p className="muted small">Prints as an investigative pointer, not a finding.</p>
        {note}
      </>
    )
  }
  if (b.type === 'area' && v.area) {
    const a = v.area
    const rows = [...a.vehicles, ...a.phones, ...a.travellers]
    return (
      <>
        <div className="rb-record-head"><b>{a.radius_km} km around {a.label}</b><span className="muted small">{a.start} to {a.end.slice(0, 10)}</span></div>
        <p className="muted small">Asked on {day(a.searched_at)}: {a.reason}</p>
        {rows.length ? (
          <table className="rb-facts">
            <thead><tr><th>Record</th><th>Reads</th><th>First and last</th><th>Where</th></tr></thead>
            <tbody>{rows.map((x) => <tr key={x.id}><td><button className="elink" onClick={() => nav.openEntity(x.id)}>{x.label}</button>{x.owner && <small className="muted"> · {x.owner}</small>}</td><td>{x.count}</td><td>{diaryTime(x.first).day} to {diaryTime(x.last).day}</td><td>{x.places.join(', ')}</td></tr>)}</tbody>
          </table>
        ) : <p className="muted small">Nothing visible was inside the area in that window.</p>}
        {note}
      </>
    )
  }
  if (b.type === 'relations') {
    return v.pairs && v.pairs.length ? (
      <table className="rb-facts">
        <thead><tr><th>Between</th><th>And</th><th>How</th><th>Source</th></tr></thead>
        <tbody>{v.pairs.map((p, i) => <tr key={i}><td>{p.a}</td><td>{p.b}</td><td>{p.how}</td><td><Sources cites={p.cites} /></td></tr>)}</tbody>
      </table>
    ) : <p className="muted small">{v.note ?? 'No recorded link between the records in this report.'}</p>
  }
  return null
}

function ExportDialog({ opened, onClose, reportId, nav, marking }: { opened: boolean; onClose: () => void; reportId: string; nav: Nav; marking: number }) {
  const mine = nav.me?.clearance ?? 1
  const [recipient, setRecipient] = useState('')
  const [level, setLevel] = useState(String(mine))
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState<{ name: string; sha256: string; marking: string } | null>(null)
  const [err, setErr] = useState('')
  useEffect(() => {
    if (opened) {
      setDone(null)
      setErr('')
      setLevel(String(mine))
    }
  }, [opened, mine])
  const run = () => {
    setBusy(true)
    setErr('')
    reports.export(reportId, { recipient: recipient.trim(), recipient_clearance: Number(level) })
      .then(async (res) => ({ ...(await saveResponse(res, 'report.pdf')), marking: res.headers.get('X-Marking') ?? '' }))
      .then(setDone).catch((e) => setErr(e.message)).finally(() => setBusy(false))
  }
  return (
    <Modal opened={opened} onClose={onClose} title="Export the report" centered classNames={{ content: 'case-modal', header: 'case-modal-header', body: 'case-modal-body reason-modal-body' }}>
      {done ? (
        <div className="export-done">
          <p><b>{done.name}</b> was saved, marked {done.marking}.</p>
          <p className="muted small">SHA-256 <span className="mono">{done.sha256}</span>. The copy, its recipient and its hash are in the case's export register and the audit trail.</p>
          <div className="case-modal-actions"><Button intent="primary" onClick={onClose}>Done</Button></div>
        </div>
      ) : (
        <form onSubmit={(e) => { e.preventDefault(); run() }}>
          <p className="muted small">Facts print as held in the source registers today, each with its source. The draft is marked {MARKINGS[marking]} for you; a copy for a reader with a lower clearance leaves out what they may not see and says so on its cover.</p>
          <TextInput label="Copy for" placeholder="For example: Court of the JMFC, Pune" value={recipient} onChange={(e) => setRecipient(e.target.value)} data-autofocus />
          <Select label="Reader's clearance" value={level} onChange={(v) => setLevel(v ?? String(mine))} allowDeselect={false}
            data={MARKINGS.slice(0, mine + 1).map((m, i) => ({ value: String(i), label: sentence(m.toLowerCase()) }))} />
          {err && <p className="err" role="alert">{err}</p>}
          <div className="case-modal-actions"><Button onClick={onClose}>Cancel</Button><Button type="submit" intent="primary" icon="document-share" loading={busy}>Export PDF</Button></div>
        </form>
      )}
    </Modal>
  )
}

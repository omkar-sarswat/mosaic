import { FormGroup, HTMLSelect, HTMLTable, InputGroup, Tag } from '@blueprintjs/core'
import { Button } from '../components/Button'
import { FileDrop } from '../components/FileDrop'
import { useEffect, useState } from 'react'
import { casework, saveResponse, type CustodyRow, type Exhibit, type ExportRow } from '../api'
import { when } from '../lib/format'
import type { Nav } from './nav'

const MARK = ['UNCLASSIFIED', 'RESTRICTED', 'CONFIDENTIAL', 'SECRET']

export default function Evidence({ caseId, nav }: { caseId: string; nav: Nav }) {
  const [items, setItems] = useState<Exhibit[]>([])
  const [exports, setExports] = useState<ExportRow[]>([])
  const [types, setTypes] = useState<string[]>([])
  const [file, setFile] = useState<File | null>(null)
  const [meta, setMeta] = useState({ description: '', source_type: '', device_make: '', device_model: '', device_serial: '', device_id: '', seized_from: '', legal_order: '' })
  const [busy, setBusy] = useState('')
  const [custody, setCustody] = useState<{ id: string; rows: CustodyRow[] } | null>(null)
  const [verify, setVerify] = useState<Record<string, string>>({})
  const [recipient, setRecipient] = useState('')
  const [clr, setClr] = useState(nav.me?.clearance ?? 2)

  const load = () => {
    casework.list(caseId).then(setItems).catch((e) => nav.setError(e.message))
    casework.exports(caseId).then(setExports).catch(() => setExports([]))
  }
  useEffect(load, [caseId, nav.tick]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    casework.sourceTypes().then(setTypes).catch(() => setTypes([]))
  }, [])

  const upload = async () => {
    if (!file) return
    setBusy('upload')
    const f = new FormData()
    f.append('file', file)
    Object.entries(meta).forEach(([k, v]) => f.append(k, v))
    try {
      const ev = await casework.upload(caseId, f)
      nav.setError(`Exhibit sealed · SHA-256 ${ev.sha256.slice(0, 16)}…`)
      setFile(null)
      load()
    } catch (e) {
      nav.setError((e as Error).message)
    } finally {
      setBusy('')
    }
  }

  const doExport = async (kind: string) => {
    setBusy(kind)
    try {
      const res = await casework.exportCase(caseId, { kind, recipient, recipient_clearance: clr })
      const r = await saveResponse(res, `${caseId}_${kind}`)
      nav.setError(`Exported ${r.name} · SHA-256 ${r.sha256.slice(0, 16)}…`)
      load()
    } catch (e) {
      nav.setError((e as Error).message)
    } finally {
      setBusy('')
    }
  }

  return (
    <div className="grid3">
      <section className="card">
        <h4>Seal a new exhibit</h4>
        <FileDrop file={file} onFile={setFile} label="Exhibit file" hint="any format; hashed before it is stored" />
        <FormGroup label="Description">
          <InputGroup value={meta.description} onChange={(e) => setMeta({ ...meta, description: e.target.value })} placeholder="Bank statement of A/c ··8033 (reply to s.94 notice)" />
        </FormGroup>
        <FormGroup label="Device / source">
          <HTMLSelect fill value={meta.source_type} onChange={(e) => setMeta({ ...meta, source_type: e.target.value })}>
            <option value="">—</option>
            {types.map((t) => (
              <option key={t}>{t}</option>
            ))}
          </HTMLSelect>
        </FormGroup>
        <div className="row">
          <InputGroup placeholder="Make" value={meta.device_make} onChange={(e) => setMeta({ ...meta, device_make: e.target.value })} />
          <InputGroup placeholder="Model" value={meta.device_model} onChange={(e) => setMeta({ ...meta, device_model: e.target.value })} />
        </div>
        <div className="row" style={{ marginTop: 6 }}>
          <InputGroup placeholder="Serial no." value={meta.device_serial} onChange={(e) => setMeta({ ...meta, device_serial: e.target.value })} />
          <InputGroup placeholder="IMEI / MAC / UID" value={meta.device_id} onChange={(e) => setMeta({ ...meta, device_id: e.target.value })} />
        </div>
        <FormGroup label="Seized from / produced by" style={{ marginTop: 8 }}>
          <InputGroup value={meta.seized_from} onChange={(e) => setMeta({ ...meta, seized_from: e.target.value })} />
        </FormGroup>
        <FormGroup label="Legal order (s.94 BNSS notice, warrant, PMLA s.17 search…)">
          <InputGroup value={meta.legal_order} onChange={(e) => setMeta({ ...meta, legal_order: e.target.value })} />
        </FormGroup>
        <Button intent="primary" icon="lock" loading={busy === 'upload'} disabled={!file} onClick={upload}>
          Hash and seal
        </Button>
        <p className="small muted">The file is stored write-once by its SHA-256. Every later touch is added to its custody chain.</p>
      </section>
      <section className="card" style={{ gridColumn: 'span 2' }}>
        <h4>Evidence locker ({items.length})</h4>
        <HTMLTable compact className="data" style={{ width: '100%' }}>
          <thead>
            <tr>
              <th>Exhibit</th>
              <th>Device / order</th>
              <th>SHA-256 / MD5</th>
              <th>Custody</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {items.map((x) => (
              <tr key={x.id}>
                <td>
                  <b>{x.filename}</b>
                  <div className="small muted">
                    {x.description} · {(x.size / 1024).toFixed(1)} KB · {when(x.uploaded_at)} by {x.uploaded_by}
                  </div>
                  {x.status !== 'held' && <Tag intent="danger">{x.status}</Tag>}
                </td>
                <td className="small">
                  {[x.source_type, x.device_make, x.device_model, x.device_serial].filter(Boolean).join(' · ')}
                  <div className="muted">{x.legal_order}</div>
                </td>
                <td className="mono small" style={{ wordBreak: 'break-all', maxWidth: 260 }}>
                  {x.sha256}
                  <div className="muted">{x.md5}</div>
                </td>
                <td>
                  <button className="link" onClick={() => casework.custody(x.id).then((rows) => setCustody({ id: x.id, rows }))}>
                    {x.custody_events} events
                  </button>
                  {verify[x.id] && <div className="small">{verify[x.id]}</div>}
                </td>
                <td>
                  <div className="row">
                    <Button small icon="tick-circle" onClick={() => casework.verify(x.id).then((r) => (setVerify({ ...verify, [x.id]: r.file_intact && r.custody_intact ? 'Intact' : 'Altered' }), load()))}>
                      Verify
                    </Button>
                    <Button small icon="download" aria-label={`Download ${x.filename}`} title="Download" disabled={x.status !== 'held'} onClick={() => casework.download(x.id).then((r) => saveResponse(r, x.filename)).then(load)} />
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </HTMLTable>
        {custody && (
          <div className="notice" style={{ marginTop: 8 }}>
            <div className="row" style={{ justifyContent: 'space-between' }}>
              <b>Chain of custody · {custody.id}</b>
              <Button small minimal icon="cross" aria-label="Close chain of custody" onClick={() => setCustody(null)} />
            </div>
            {custody.rows.map((r) => (
              <div key={r.seq} className="small mono">
                {when(r.ts)} · {r.actor} · <b>{r.action}</b> · {JSON.stringify(r.detail).slice(0, 110)} · #{r.hash.slice(0, 10)}
              </div>
            ))}
          </div>
        )}
      </section>
      <section className="card" style={{ gridColumn: 'span 3' }}>
        <h4>Exports for prosecution and dissemination</h4>
        <div className="row">
          <InputGroup placeholder="Recipient (e.g. Special Court PMLA, Mumbai / CBI BS&FC)" value={recipient} onChange={(e) => setRecipient(e.target.value)} style={{ minWidth: 340 }} />
          <span className="small muted">Release at</span>
          <HTMLSelect value={clr} onChange={(e) => setClr(Number(e.target.value))}>
            {MARK.map((m, i) => (
              <option key={m} value={i} disabled={i > (nav.me?.clearance ?? 0)}>
                {m}
              </option>
            ))}
          </HTMLSelect>
          <Button icon="document" loading={busy === 'report_pdf'} onClick={() => doExport('report_pdf')}>
            Case report (PDF)
          </Button>
          <Button icon="code" loading={busy === 'report_html'} onClick={() => doExport('report_html')}>
            Report (HTML)
          </Button>
          <Button icon="archive" intent="primary" loading={busy === 'evidence_pack'} onClick={() => doExport('evidence_pack')}>
            Court evidence pack (ZIP + s.63 certificate)
          </Button>
        </div>
        <p className="small muted">
          Release copies drop anything above the recipient's clearance and mask identifiers accordingly. Every page carries the marking and a watermark naming you, the time and the recipient.
          The pack holds the report, a draft BSA s.63(4) certificate with each exhibit's hash values, the custody chains, the exhibits and a SHA-256 manifest.
        </p>
        <HTMLTable compact className="data" style={{ width: '100%' }}>
          <thead>
            <tr>
              <th>Export</th>
              <th>Kind</th>
              <th>Recipient</th>
              <th>By / when</th>
              <th>SHA-256</th>
            </tr>
          </thead>
          <tbody>
            {exports.map((x) => (
              <tr key={x.id}>
                <td className="mono">{x.id}</td>
                <td>{x.kind}</td>
                <td>
                  {x.recipient || 'internal'} <Tag minimal>{MARK[Number(x.marking)] ?? x.marking}</Tag>
                </td>
                <td className="small">
                  {x.exported_by} · {when(x.exported_at)}
                </td>
                <td className="mono small">{x.sha256.slice(0, 24)}…</td>
              </tr>
            ))}
          </tbody>
        </HTMLTable>
      </section>
    </div>
  )
}

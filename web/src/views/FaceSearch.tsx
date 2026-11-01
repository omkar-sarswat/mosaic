import { Callout, InputGroup, NonIdealState, Tag } from '@blueprintjs/core'
import { Button } from '../components/Button'
import { FileDrop } from '../components/FileDrop'
import { useEffect, useState } from 'react'
import { faces, type Candidate, type FaceMatch, type FaceStatus, type ProbeResult } from '../api'
import { when } from '../lib/format'
import type { Nav } from './nav'

type Result = { candidates: Candidate[]; note: string; gallery_searched: number; withheld: number }

// Face search on a still lawfully held as case evidence: one face per search, a stated reason,
// candidates only, and a second officer's confirmation before a match counts. The screen walks the
// officer through those three steps in order.
export default function FaceSearch({ nav }: { nav: Nav }) {
  const [st, setSt] = useState<FaceStatus | null>(null)
  const [file, setFile] = useState<File | null>(null)
  const [local, setLocal] = useState('')
  const [order, setOrder] = useState('')
  const [probe, setProbe] = useState<ProbeResult | null>(null)
  const [img, setImg] = useState('')
  const [face, setFace] = useState<string | null>(null)
  const [reason, setReason] = useState('')
  const [res, setRes] = useState<Result | null>(null)
  const [matches, setMatches] = useState<FaceMatch[]>([])
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState<'' | 'upload' | 'search'>('')
  const [why, setWhy] = useState('')

  useEffect(() => {
    faces.status().then(setSt).catch(() => setSt(null))
    if (nav.caseId) faces.matches().then(setMatches).catch(() => setMatches([]))
  }, [nav.caseId, nav.tick])

  // a preview of the chosen still before it is sent anywhere
  useEffect(() => {
    if (!file) { setLocal(''); return }
    const url = URL.createObjectURL(file)
    setLocal(url)
    return () => URL.revokeObjectURL(url)
  }, [file])

  if (!nav.caseId) return <NonIdealState icon="lock" title="Select a case" description="Face search runs only on evidence held in an open case, with a reason for each search." />

  const choose = (f: File | null) => {
    setFile(f)
    setProbe(null)
    setImg('')
    setRes(null)
    setFace(null)
    setMsg('')
  }
  const upload = () => {
    if (!file) return
    const f = new FormData()
    f.append('file', file)
    f.append('legal_order', order)
    f.append('description', 'Face search still')
    setBusy('upload')
    setMsg('')
    faces
      .probe(f)
      .then(async (p) => {
        setProbe(p)
        setRes(null)
        setFace(p.faces.length === 1 ? p.faces[0].face_id : null)
        setImg(await faces.media(p.media_id, { thumb: 640 }))
      })
      .catch((e) => setMsg(e.message))
      .finally(() => setBusy(''))
  }
  const search = () => {
    if (!face) return
    setBusy('search')
    setMsg('')
    faces
      .search(face, reason)
      .then((r) => {
        setRes(r)
        faces.matches().then(setMatches)
      })
      .catch((e) => setMsg(e.message))
      .finally(() => setBusy(''))
  }
  const decide = (id: string, d: 'confirm' | 'reject') =>
    faces
      .decide(id, d, why)
      .then(() => faces.matches().then(setMatches))
      .catch((e) => setMsg(e.message))

  const step1 = !!probe
  const step2 = !!res
  const chosen = probe?.faces.find((f) => f.face_id === face)
  const pending = matches.filter((m) => m.status === 'candidate')

  return (
    <div className="workspace" style={{ gridTemplateColumns: '360px minmax(0, 1fr) 360px' }}>
      <aside className="panel">
        {st && !st.available && <div className="section"><Callout intent="warning" icon="warning-sign" compact>Face models are not installed on this server, so stills cannot be searched.</Callout></div>}
        <ol className="probe-steps">
          <li className={step1 ? 'done' : ''}>
            <h3>Add the still to the case</h3>
            <p>It is sealed as case evidence under the order you name, before any face is read from it.</p>
            <FileDrop file={file} onFile={choose} accept="image/jpeg,image/png,image/webp" label="Probe image" hint="JPEG, PNG or WebP" preview disabled={busy !== ''} />
            <InputGroup aria-label="Legal order or seizure memo" placeholder="Legal order or seizure memo for this still" value={order} onChange={(e) => setOrder(e.target.value)} disabled={step1} />
            <Button style={{ marginTop: 10 }} icon="upload" intent={step1 ? 'none' : 'primary'} loading={busy === 'upload'} disabled={!file || !!busy || step1 || st?.available === false} onClick={upload}>
              {step1 ? 'Added as evidence' : 'Add as evidence and find faces'}
            </Button>
          </li>
          <li className={step2 ? 'done' : step1 ? '' : 'waiting'}>
            <h3>Choose one face and say why</h3>
            {!probe && <p>Faces found in the still appear here.</p>}
            {probe && !probe.faces.length && <p>No face was found in this still. Try a clearer or closer image.</p>}
            {probe && probe.faces.length > 0 && (
              <>
                <p>One face per search. The reason is kept with the search in the audit log.</p>
                {probe.faces.map((f) => (
                  <label key={f.face_id} className="face-row">
                    <input type="radio" name="probe-face" checked={face === f.face_id} onChange={() => setFace(f.face_id)} />
                    <span>Face {f.index + 1}</span>
                  </label>
                ))}
                <InputGroup style={{ marginTop: 10 }} aria-label="Reason for this search" placeholder="Why this face is being searched (at least 10 characters)" value={reason} onChange={(e) => setReason(e.target.value)} />
                <Button style={{ marginTop: 10 }} icon="search" intent="primary" loading={busy === 'search'} disabled={!face || reason.trim().length < 10 || !!busy} onClick={search}>
                  {chosen ? `Search face ${chosen.index + 1}` : 'Search the chosen face'}
                </Button>
              </>
            )}
          </li>
          <li className={step2 ? '' : 'waiting'}>
            <h3>A second officer confirms</h3>
            <p>Results are candidates, not identifications. A match counts only after another officer of the case confirms it with a reason.</p>
          </li>
        </ol>
        {msg && <div className="section"><p className="err small" role="alert" style={{ margin: 0 }}>{msg}</p></div>}
        {st?.available && <div className="section"><p className="small muted" style={{ margin: 0 }}>{st.gallery_faces.toLocaleString('en-IN')} faces on record. {st.policy}</p></div>}
      </aside>
      <main className="canvas scroll padded">
        {!local && !img && (
          <div className="canvas-message">
            <NonIdealState icon="mugshot" title="No still yet" description="Add a still on the left. You will see it here before it is sent, and the faces found in it after it is added as evidence." />
          </div>
        )}
        {(img || local) && (
          <figure className="probe-preview" style={{ margin: 0 }}>
            <div style={{ position: 'relative', display: 'inline-block', maxWidth: '100%' }}>
              <img className="probe-image" src={img || local} alt={probe ? 'Probe still, added as case evidence' : 'Chosen still, not yet sent'} />
              {probe && probe.faces.map((f) => {
                const [x, y, w, h] = f.box
                const on = f.face_id === face
                return (
                  <button key={f.face_id} type="button" aria-label={`Choose face ${f.index + 1}`} aria-pressed={on} onClick={() => setFace(f.face_id)}
                    style={{ position: 'absolute', left: `${(x / probe.width) * 100}%`, top: `${(y / probe.height) * 100}%`, width: `${(w / probe.width) * 100}%`, height: `${(h / probe.height) * 100}%`,
                      border: `2px solid ${on ? 'var(--accent)' : 'rgb(255 255 255 / 85%)'}`, borderRadius: 4, background: 'transparent', boxShadow: '0 0 0 1px rgb(0 0 0 / 35%)', cursor: 'pointer', padding: 0 }}>
                    <span style={{ position: 'absolute', left: -2, top: -24, padding: '1px 7px', borderRadius: 3, background: on ? 'var(--accent)' : 'rgb(20 22 26 / 80%)', color: '#fff', font: '600 12px/20px var(--sans)' }}>{f.index + 1}</span>
                  </button>
                )
              })}
            </div>
            <figcaption>{probe ? `Case evidence · ${probe.faces.length === 1 ? 'one face found' : `${probe.faces.length} faces found`} · select a face on the image or in the list` : 'Not sent yet. The still becomes case evidence when you add it.'}</figcaption>
          </figure>
        )}
        {res && (
          <section className="card" style={{ marginTop: 20 }}>
            <h4>Candidates <span className="muted">{res.candidates.length}</span></h4>
            <p className="card-note">{res.note} Searched {res.gallery_searched.toLocaleString('en-IN')} photographs on record; {res.withheld} withheld by access rules.</p>
            {!res.candidates.length && <p className="muted small">No photograph on record is similar enough to propose.</p>}
            {res.candidates.map((c, i) => (
              <div key={i} className="kv-row">
                <b>{c.object.title}</b> <Tag minimal>{c.band}</Tag> <span className="small muted">similarity {c.similarity.toFixed(3)} · photo from {c.photo_source}</span>
                <Button small minimal icon="person" style={{ marginLeft: 'auto' }} onClick={() => nav.openEntity(c.object.id)}>Dossier</Button>
              </div>
            ))}
          </section>
        )}
      </main>
      <aside className="panel right">
        <div className="section">
          <h3>Awaiting a second officer <span className="count">{pending.length}</span></h3>
          {matches.length === 0 && <p className="small muted" style={{ margin: 0 }}>No face searches in this case yet.</p>}
          {pending.length > 0 && (
            <InputGroup aria-label="Reason for your decision" placeholder="Reason for your decision (at least 10 characters)" value={why} onChange={(e) => setWhy(e.target.value)} />
          )}
          {matches.map((m) => (
            <div key={m.id} className="kv-row small">
              <b>{m.candidate?.title ?? 'Withheld'}</b> <Tag minimal intent={m.status === 'confirmed' ? 'success' : m.status === 'rejected' ? 'none' : 'warning'}>{m.status}</Tag>
              <span className="muted" style={{ flexBasis: '100%' }}>Similarity {m.similarity.toFixed(3)} · searched by {m.searched_by} · {when(m.created_at)}</span>
              <span className="muted" style={{ flexBasis: '100%' }}>Reason: {m.reason}</span>
              {m.status === 'candidate' && m.searched_by !== nav.me?.id && (
                <span className="row" style={{ gap: 6 }}>
                  <Button small intent="success" disabled={why.trim().length < 10} onClick={() => decide(m.id, 'confirm')}>Confirm</Button>
                  <Button small disabled={why.trim().length < 10} onClick={() => decide(m.id, 'reject')}>Reject</Button>
                </span>
              )}
              {m.status === 'candidate' && m.searched_by === nav.me?.id && <span className="muted" style={{ flexBasis: '100%' }}>Your own search: another officer must decide.</span>}
            </div>
          ))}
        </div>
      </aside>
    </div>
  )
}

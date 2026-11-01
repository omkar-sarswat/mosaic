import { Icon } from '@blueprintjs/core'
import { Modal } from '@mantine/core'
import { useEffect, useState } from 'react'
import { faces, identityKey, type Dossier } from '../api'
import { day, initials } from '../lib/format'

// Photographs are fetched with the caller's identity (they are personal data, checked per viewer), so
// every cache is keyed by who is asking.
const blobs = new Map<string, Promise<string>>()
function photoUrl(mediaId: string, opts: { thumb?: number; face?: number }): Promise<string> {
  const key = `${identityKey()}|${mediaId}|${opts.thumb ?? ''}|${opts.face ?? ''}`
  if (!blobs.has(key)) blobs.set(key, faces.media(mediaId, opts).catch((e) => { blobs.delete(key); throw e }))
  return blobs.get(key)!
}

// People on screen are looked up in one request per render pass, not one per face.
const ids = new Map<string, Promise<string | null>>()
let queue: { id: string; resolve: (v: string | null) => void }[] = []
let timer: ReturnType<typeof setTimeout> | null = null
function portraitOf(id: string): Promise<string | null> {
  const key = `${identityKey()}|${id}`
  if (!ids.has(key)) {
    ids.set(key, new Promise((resolve) => {
      queue.push({ id, resolve })
      timer ??= setTimeout(() => {
        const batch = queue
        queue = []
        timer = null
        for (let i = 0; i < batch.length; i += 60) {
          const part = batch.slice(i, i + 60)
          faces.portraits(part.map((x) => x.id)).then((m) => part.forEach((x) => x.resolve(m[x.id] ?? null))).catch(() => part.forEach((x) => x.resolve(null)))
        }
      }, 0)
    }))
  }
  return ids.get(key)!
}

/** A small face for lists: the photograph on record, cropped to the face, or the person's initials. */
export function PersonAvatar({ id, name, size = 32 }: { id: string; name: string; size?: number }) {
  const [url, setUrl] = useState('')
  useEffect(() => {
    let live = true
    setUrl('')
    if (id.startsWith('person:')) portraitOf(id).then((m) => (m ? photoUrl(m, { face: 0 }) : '')).then((u) => { if (live) setUrl(u) }).catch(() => undefined)
    return () => { live = false }
  }, [id])
  return (
    <span className="person-avatar" style={{ width: size, height: size, fontSize: Math.round(size * 0.36) }} aria-hidden>
      {url ? <img src={url} alt="" /> : initials(name)}
    </span>
  )
}

type Photo = NonNullable<Dossier['photos']>[number]

/** The dossier portrait: the photograph on record with where it came from and why it is held, or a plain
 * statement that there is none. Opens larger with its full provenance. */
export function Portrait({ photos, name }: { photos: Photo[]; name: string }) {
  const [i, setI] = useState(0)
  const [url, setUrl] = useState('')
  const [large, setLarge] = useState('')
  const [open, setOpen] = useState(false)
  const p = photos[i]
  useEffect(() => {
    let live = true
    setUrl('')
    if (p) photoUrl(p.id, { thumb: 480 }).then((u) => { if (live) setUrl(u) }).catch(() => undefined)
    return () => { live = false }
  }, [p])
  useEffect(() => {
    let live = true
    if (open && p) photoUrl(p.id, {}).then((u) => { if (live) setLarge(u) }).catch(() => undefined)
    return () => { live = false }
  }, [open, p])
  if (!p) {
    return (
      <figure className="portrait empty">
        <div className="portrait-frame"><Icon icon="person" size={44} /></div>
        <figcaption>No photograph on record</figcaption>
      </figure>
    )
  }
  return (
    <figure className="portrait">
      <button className="portrait-frame" onClick={() => setOpen(true)} aria-label={`Open the photograph of ${name}`}>
        {url ? <img src={url} alt={`Photograph on record of ${name}`} /> : <Icon icon="person" size={44} />}
        {photos.length > 1 && <span className="portrait-count">{i + 1} of {photos.length}</span>}
      </button>
      <figcaption>
        <span>{p.source}</span>
        {p.synthetic && <span className="portrait-synthetic">Synthetic portrait</span>}
        {photos.length > 1 && (
          <span className="portrait-nav">
            <button className="icon-button" aria-label="Previous photograph" onClick={() => setI((i + photos.length - 1) % photos.length)}><Icon icon="chevron-left" size={14} /></button>
            <button className="icon-button" aria-label="Next photograph" onClick={() => setI((i + 1) % photos.length)}><Icon icon="chevron-right" size={14} /></button>
          </span>
        )}
      </figcaption>
      <Modal opened={open} onClose={() => setOpen(false)} title={`Photograph on record · ${name}`} centered size="lg"
        classNames={{ content: 'case-modal', header: 'case-modal-header', body: 'case-modal-body' }}>
        <div className="portrait-large">
          {large ? <img src={large} alt={`Photograph on record of ${name}`} /> : <div className="app-loading" style={{ minHeight: 280 }}>Loading the photograph…</div>}
          <dl className="kv">
            <dt>Source</dt><dd>{p.source}</dd>
            <dt>Legal basis</dt><dd>{p.legal_basis || 'Not recorded'}</dd>
            {p.case_id && <><dt>Held in case</dt><dd className="mono">{p.case_id}</dd></>}
            <dt>Added</dt><dd>{day(p.added_at)}</dd>
            <dt>Size</dt><dd>{p.width} × {p.height} px</dd>
            {p.synthetic && <><dt>Note</dt><dd>A synthetic face of a person who does not exist (StyleGAN2), standing in for a photograph on record in this demonstration.</dd></>}
          </dl>
        </div>
      </Modal>
    </figure>
  )
}

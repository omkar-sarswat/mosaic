import { Icon } from '@blueprintjs/core'
import { useEffect, useId, useRef, useState, type DragEvent } from 'react'
import { Button } from './Button'

const size = (n: number) => (n >= 1 << 20 ? `${(n / (1 << 20)).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`)

/** A file picker that also takes a dropped file, and shows what was chosen before anything is sent.
 * The real <input type="file"> stays in the tab order (visually hidden), so the keyboard path is the
 * browser's own: focus it, press Enter or Space. */
export function FileDrop({ file, onFile, accept, label, hint, disabled = false, preview = false }: {
  file: File | null; onFile: (f: File | null) => void; accept?: string; label: string; hint?: string; disabled?: boolean
  /** show a thumbnail when the file is an image */
  preview?: boolean
}) {
  const id = useId()
  const input = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)
  const [thumb, setThumb] = useState('')
  useEffect(() => {
    if (!preview || !file || !file.type.startsWith('image/')) { setThumb(''); return }
    const url = URL.createObjectURL(file)
    setThumb(url)
    return () => URL.revokeObjectURL(url)
  }, [file, preview])
  const accepts = (f: File) => !accept || accept.split(',').some((a) => {
    const t = a.trim()
    return t.endsWith('/*') ? f.type.startsWith(t.slice(0, -1)) : t.startsWith('.') ? f.name.toLowerCase().endsWith(t) : f.type === t
  })
  const onDrop = (e: DragEvent) => {
    e.preventDefault()
    setDragging(false)
    const f = e.dataTransfer.files?.[0]
    if (f && !disabled && accepts(f)) onFile(f)
  }
  return (
    <div className={`file-drop ${dragging ? 'dragging' : ''} ${file ? 'filled' : ''} ${disabled ? 'disabled' : ''}`}
      onDragOver={(e) => { e.preventDefault(); if (!disabled) setDragging(true) }} onDragLeave={() => setDragging(false)} onDrop={onDrop}>
      <input ref={input} id={id} type="file" className="sr-only" accept={accept} disabled={disabled}
        onChange={(e) => { onFile(e.target.files?.[0] ?? null); e.target.value = '' }} />
      {!file ? (
        <label htmlFor={id} className="file-drop-zone">
          <Icon icon="cloud-upload" size={20} />
          <span><b>{label}</b><small>Drop it here, or <u>choose a file</u>{hint ? ` · ${hint}` : ''}</small></span>
        </label>
      ) : (
        <div className="file-drop-chosen">
          {thumb ? <img src={thumb} alt="" /> : <span className="file-drop-icon"><Icon icon="document" size={18} /></span>}
          <span className="file-drop-name"><b title={file.name}>{file.name}</b><small>{size(file.size)}</small></span>
          <Button small minimal onClick={() => input.current?.click()} disabled={disabled}>Replace</Button>
          <Button small minimal icon="cross" aria-label={`Remove ${file.name}`} onClick={() => onFile(null)} disabled={disabled} />
        </div>
      )}
    </div>
  )
}

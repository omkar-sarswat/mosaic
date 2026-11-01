import { Icon, Spinner } from '@blueprintjs/core'
import { useEffect, useId, useMemo, useRef, useState } from 'react'
import { api, type ObjSummary } from '../api'
import { TYPE_COLOURS } from '../lib/icons'
import { PersonAvatar } from './PersonPhoto'

const ORDER = ['Person', 'Organisation', 'BankAccount', 'Phone', 'Vehicle', 'Incident', 'Property', 'CryptoWallet', 'Location', 'Asset', 'AdminUnit', 'Hazard']

function sub(o: ObjSummary): string {
  const p = o.props
  const bits = [
    p.name_native as string,
    p.pan ? `PAN ${p.pan}` : '',
    p.bank as string,
    p.holder_name as string,
    p.kind as string,
    p.agency as string,
    p.make as string,
    (p.city as string) || o.district_name || '',
  ].filter(Boolean)
  return bits.slice(0, 3).join(' · ')
}

export default function Omnibox({ onPick, className = '', autoFocus = false, onDismiss, shortcut = true, label = 'Search records' }: {
  onPick: (id: string) => void; className?: string; autoFocus?: boolean; onDismiss?: () => void
  /** only the application bar's search answers Ctrl+K */
  shortcut?: boolean; label?: string
}) {
  const [q, setQ] = useState('')
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [res, setRes] = useState<ObjSummary[]>([])
  const [withheld, setWithheld] = useState(0)
  const [cursor, setCursor] = useState(0)
  const [error, setError] = useState('')
  const box = useRef<HTMLInputElement>(null)
  const listId = useId()

  useEffect(() => {
    if (!shortcut) return
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        box.current?.focus()
        setOpen(true)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [shortcut])

  useEffect(() => {
    let current = true
    setError('')
    setRes([])
    setWithheld(0)
    if (q.trim().length < 2) {
      setBusy(false)
      return
    }
    setBusy(true)
    const t = setTimeout(() => {
      api
        .search(q.trim())
        .then((r) => {
          if (!current) return
          setRes(r.results)
          setWithheld(r.withheld.reduce((a, w) => a + w.count, 0))
          setCursor(0)
        })
        .catch(() => { if (current) setError('Search is unavailable. Change your search to try again.') })
        .finally(() => { if (current) setBusy(false) })
    }, 220)
    return () => { current = false; clearTimeout(t) }
  }, [q])

  const grouped = useMemo(() => {
    const g: Record<string, ObjSummary[]> = {}
    for (const r of res) (g[r.type] ??= []).push(r)
    return ORDER.filter((t) => g[t]).map((t) => [t, g[t].slice(0, 6)] as const)
  }, [res])
  const flat = grouped.flatMap(([, xs]) => xs)
  const expanded = open && q.trim().length >= 2

  useEffect(() => {
    if (expanded) document.getElementById(`${listId}-${cursor}`)?.scrollIntoView({ block: 'nearest' })
  }, [cursor, expanded, listId])

  useEffect(() => {
    if (autoFocus) box.current?.focus()
  }, [autoFocus])

  const pick = (id: string) => {
    setOpen(false)
    setQ('')
    onDismiss?.()
    onPick(id)
  }

  return (
    <div className={`omni ${className}`} role="search">
      <Icon icon="search" className="omni-icon" />
      <input
        ref={box}
        value={q}
        placeholder="Search records, people, accounts…"
        aria-label={label}
        role="combobox"
        aria-autocomplete="list"
        aria-expanded={expanded}
        aria-controls={expanded ? listId : undefined}
        aria-activedescendant={expanded && flat[cursor] ? `${listId}-${cursor}` : undefined}
        autoComplete="off"
        onChange={(e) => {
          setQ(e.target.value)
          setOpen(true)
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => { setOpen(false); onDismiss?.() }, 180)}
        onKeyDown={(e) => {
          if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
            e.preventDefault()
            setOpen(true)
            setCursor((c) => e.key === 'ArrowDown' ? Math.min(c + 1, Math.max(0, flat.length - 1)) : Math.max(c - 1, 0))
          }
          if (e.key === 'Enter' && expanded && flat[cursor]) pick(flat[cursor].id)
          if (e.key === 'Escape') { setOpen(false); onDismiss?.() }
        }}
      />
      {!busy && shortcut && <kbd className="omni-shortcut">Ctrl K</kbd>}
      {busy && <Spinner size={14} className="omni-spin" />}
      {expanded && (
        <div className="omni-drop">
          <div role="status" className="omni-status">{busy ? 'Searching…' : error || (flat.length ? `${flat.length} results` : `No visible results${withheld ? ` · ${withheld} withheld by policy` : ''}`)}</div>
          <div role="listbox" id={listId} aria-label="Search results" aria-busy={busy}>
          {grouped.map(([type, xs]) => (
            <div key={type} role="group" aria-label={type.replace(/([a-z])([A-Z])/g, '$1 $2')}>
              <div className="omni-head">{type.replace(/([a-z])([A-Z])/g, '$1 $2')}</div>
              {xs.map((r) => {
                const i = flat.indexOf(r)
                return (
                  <div key={r.id} id={`${listId}-${i}`} role="option" aria-selected={i === cursor} className={`omni-row ${i === cursor ? 'on' : ''}`} onMouseDown={(event) => event.preventDefault()} onClick={() => pick(r.id)} onMouseEnter={() => setCursor(i)}>
                    {type === 'Person' ? <PersonAvatar id={r.id} name={r.title} size={26} /> : <span className="type-dot" style={{ background: TYPE_COLOURS[type] ?? 'var(--muted)' }} />}
                    <span className="omni-title">{r.title}</span>
                    <span className="omni-sub">{sub(r)}</span>
                  </div>
                )
              })}
            </div>
          ))}
          </div>
          {withheld > 0 && grouped.length > 0 && <div className="omni-empty">{withheld} more withheld by policy (purpose / jurisdiction)</div>}
        </div>
      )}
    </div>
  )
}

import { Modal, Textarea } from '@mantine/core'
import { useEffect, useState } from 'react'
import { Button } from './Button'

/** Asks for the recorded reason behind a consequential action (legal hold, closing a case, unmasking).
 * The reason is kept in the audit log, so it must say something: at least `min` characters. */
export function ReasonDialog({ opened, title, label, description, placeholder, initial = '', confirm, intent = 'primary', min = 10, onClose, onConfirm }: {
  opened: boolean; title: string; label: string; description?: string; placeholder?: string; initial?: string
  confirm: string; intent?: 'primary' | 'danger'; min?: number
  onClose: () => void; onConfirm: (reason: string) => Promise<unknown> | void
}) {
  const [reason, setReason] = useState(initial)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  useEffect(() => {
    if (opened) {
      setReason(initial)
      setErr('')
    }
  }, [opened, initial])
  const ok = reason.trim().length >= min
  const submit = () => {
    if (!ok || busy) return
    setBusy(true)
    setErr('')
    Promise.resolve(onConfirm(reason.trim()))
      .then(() => onClose())
      .catch((e) => setErr(e?.message ?? String(e)))
      .finally(() => setBusy(false))
  }
  return (
    <Modal opened={opened} onClose={onClose} title={title} centered classNames={{ content: 'case-modal', header: 'case-modal-header', body: 'case-modal-body reason-modal-body' }}>
      <form onSubmit={(e) => { e.preventDefault(); submit() }}>
        <Textarea label={label} description={description ?? `Recorded in the audit log. At least ${min} characters.`} placeholder={placeholder}
          minRows={3} autosize value={reason} onChange={(e) => setReason(e.target.value)} data-autofocus />
        {err && <p className="err" role="alert">{err}</p>}
        <div className="case-modal-actions">
          <Button onClick={onClose}>Cancel</Button>
          <Button type="submit" intent={intent} loading={busy} disabled={!ok}>{confirm}</Button>
        </div>
      </form>
    </Modal>
  )
}

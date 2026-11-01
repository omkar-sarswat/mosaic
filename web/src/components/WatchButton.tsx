import { Modal, SegmentedControl, Textarea } from '@mantine/core'
import { useEffect, useState } from 'react'
import { monitor, type Watch } from '../api'
import type { Nav } from '../views/nav'
import { Button } from './Button'

const LOOKBACK = [{ value: '0', label: 'From now' }, { value: '30', label: 'Last 30 days' }, { value: '90', label: 'Last 90 days' }]

/** Follow a record inside the active case: new calls, sightings, money, travel, FIRs and facts reach the work queue. */
export function WatchButton({ objectId, label, nav }: { objectId: string; label: string; nav: Nav }) {
  const [watch, setWatch] = useState<Watch | null | undefined>(undefined)
  const [open, setOpen] = useState(false)
  useEffect(() => {
    setWatch(undefined)
    monitor.of(objectId).then((r) => setWatch(r.watch)).catch(() => setWatch(null))
  }, [objectId, nav.caseId])
  if (watch === undefined) return <Button icon="notifications" disabled>Watch</Button>
  if (watch) return <Button icon="notifications" active onClick={() => nav.open('watch', watch.id)} title={`Watched since ${watch.created_at.slice(0, 10)}: ${watch.reason}`}>Watching</Button>
  return (
    <>
      <Button icon="notifications" onClick={() => setOpen(true)}>Watch</Button>
      <WatchDialog opened={open} onClose={() => setOpen(false)} title={`Watch ${label}`}
        onConfirm={(reason, days) => monitor.watch(objectId, reason, days).then((w) => { setWatch(w); nav.setError('Watch started. New activity will reach the work queue.') })} />
    </>
  )
}

/** The reason and look-back for a watch on a record or an area. The reason is kept in the audit trail. */
export function WatchDialog({ opened, title, onClose, onConfirm, initial = '' }: {
  opened: boolean; title: string; initial?: string; onClose: () => void; onConfirm: (reason: string, lookbackDays: number) => Promise<unknown>
}) {
  const [reason, setReason] = useState(initial)
  const [days, setDays] = useState('30')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  useEffect(() => {
    if (opened) {
      setReason(initial)
      setErr('')
    }
  }, [opened, initial])
  const ok = reason.trim().length >= 10
  const submit = () => {
    if (!ok || busy) return
    setBusy(true)
    setErr('')
    onConfirm(reason.trim(), Number(days)).then(onClose).catch((e) => setErr(e?.message ?? String(e))).finally(() => setBusy(false))
  }
  return (
    <Modal opened={opened} onClose={onClose} title={title} centered classNames={{ content: 'case-modal', header: 'case-modal-header', body: 'case-modal-body reason-modal-body' }}>
      <form onSubmit={(e) => { e.preventDefault(); submit() }}>
        <Textarea label="Why this needs watching" description="Recorded in the audit trail and shown to the case team. At least 10 characters." minRows={3} autosize
          value={reason} onChange={(e) => setReason(e.target.value)} data-autofocus placeholder="For example: principal accused; follow movement and new contacts" />
        <div className="watch-lookback">
          <span>Include activity</span>
          <SegmentedControl size="xs" value={days} onChange={setDays} data={LOOKBACK} aria-label="Include earlier activity" />
        </div>
        {err && <p className="err" role="alert">{err}</p>}
        <div className="case-modal-actions">
          <Button onClick={onClose}>Cancel</Button>
          <Button type="submit" intent="primary" loading={busy} disabled={!ok}>Start watching</Button>
        </div>
      </form>
    </Modal>
  )
}

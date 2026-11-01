import { Icon } from '@blueprintjs/core'
import { useEffect, useState } from 'react'
import { api, type TodaySubject } from '../api'
import type { Nav } from '../views/nav'
import { PersonAvatar } from './PersonPhoto'

/** Starting points for a screen that needs someone to start from: the people already in the active case.
 * Shown under an empty state so the officer is one click from work, not a blank page. */
export function CaseStart({ nav, title, action, onPick }: { nav: Nav; title: string; action: string; onPick: (id: string) => void }) {
  const [people, setPeople] = useState<TodaySubject[] | null>(null)
  useEffect(() => {
    let current = true
    setPeople(null)
    if (nav.caseId) api.today().then((d) => { if (current) setPeople(d.case?.subjects ?? []) }).catch(() => { if (current) setPeople([]) })
    return () => { current = false }
  }, [nav.caseId])
  if (!people?.length) return null
  return (
    <div className="start-list">
      <h3>{title}</h3>
      {people.slice(0, 6).map((p) => (
        <button key={p.id} onClick={() => onPick(p.id)}>
          <PersonAvatar id={p.id} name={p.name} size={36} />
          <span style={{ flex: 1 }}>{p.name}<br /><small>{p.accused_in ? `Accused in ${p.accused_in} FIR${p.accused_in > 1 ? 's' : ''}` : 'In this case'}</small></span>
          <small>{action} <Icon icon="arrow-right" size={12} /></small>
        </button>
      ))}
    </div>
  )
}

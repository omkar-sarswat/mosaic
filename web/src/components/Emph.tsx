import type { ReactNode } from 'react'

/** A line with its key words in bold (a number, an amount, a place), so the eye lands on what carries the point. */
export function Emph({ text, terms }: { text: string; terms?: (string | null | undefined)[] }) {
  const list = [...new Set((terms ?? []).filter((t): t is string => !!t && text.includes(t)))].sort((a, b) => b.length - a.length)
  if (!list.length) return <>{text}</>
  const parts: ReactNode[] = []
  let rest = text
  let key = 0
  while (rest) {
    let at = -1
    let term = ''
    for (const t of list) {
      const i = rest.indexOf(t)
      if (i >= 0 && (at < 0 || i < at)) {
        at = i
        term = t
      }
    }
    if (at < 0) {
      parts.push(rest)
      break
    }
    if (at > 0) parts.push(rest.slice(0, at))
    parts.push(<b key={key++}>{term}</b>)
    rest = rest.slice(at + term.length)
  }
  return <>{parts}</>
}

export type Priority = 'high' | 'medium' | 'low'
export const PRIORITY_LABEL: Record<Priority, string> = { high: 'Read first', medium: 'Worth a look', low: 'Routine' }

/** Why an entry matters, in a few words, in the weight of its priority. Text only, never a tinted badge. */
export function Why({ priority, why }: { priority: Priority; why?: string | null }) {
  if (priority === 'low' && !why) return null
  return <span className={`why why-${priority}`}>{why ?? PRIORITY_LABEL[priority]}</span>
}

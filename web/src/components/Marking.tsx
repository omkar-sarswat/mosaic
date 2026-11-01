import { markingOf, useHighestMarking } from '../lib/marking'

/** A record's handling marking, as printed on its file: text, never a coloured badge. */
export function MarkingChip({ level, className = '', hidePublic = false }: { level: number | null | undefined; className?: string; hidePublic?: boolean }) {
  const value = Math.max(0, Math.min(3, Number(level) || 0))
  if (hidePublic && value === 0) return null
  return <span className={`marking-chip m${value} ${className}`} title={`Handling marking: ${markingOf(value)}`}>{markingOf(value)}</span>
}

/** The highest marking shown since this officer opened this case; the workspace never reads below RESTRICTED. */
export function SessionMarking() {
  const highest = Math.max(1, useHighestMarking())
  return <b className={`session-marking m${highest}`} aria-label={`Highest handling marking on screen: ${markingOf(highest)}`}>{markingOf(highest)}</b>
}

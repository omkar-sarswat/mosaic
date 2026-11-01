import { useSyncExternalStore } from 'react'

// Handling markings (Manual of Departmental Security Instructions). Every record carries a sensitivity from
// 0 to 3; the workspace footer shows the highest marking of anything shown since the session (officer and
// case) began, so a screenshot or a print-out always carries the marking of its most sensitive content.
export const MARKINGS = ['UNCLASSIFIED', 'RESTRICTED', 'CONFIDENTIAL', 'SECRET'] as const
export type Marking = (typeof MARKINGS)[number]

const clamp = (level: unknown) => Math.max(0, Math.min(3, Math.trunc(Number(level) || 0)))
export const markingOf = (level: unknown): Marking => MARKINGS[clamp(level)]

let highest = 0
const listeners = new Set<() => void>()
const emit = () => listeners.forEach((listener) => listener())

/** Something of this sensitivity reached the screen. */
export function noteMarking(level: unknown) {
  const value = clamp(level)
  if (value > highest) {
    highest = value
    emit()
  }
}

/** A new officer or case starts a new session. */
export function resetMarking() {
  if (highest) {
    highest = 0
    emit()
  }
}

/** Walks an API answer for record sensitivities. Bounded, so a large graph costs little. */
export function scanMarking(body: unknown, budget = 20000) {
  let top = 0
  const stack: unknown[] = [body]
  while (stack.length && budget-- > 0 && top < 3) {
    const item = stack.pop()
    if (Array.isArray(item)) {
      for (const value of item) if (value && typeof value === 'object') stack.push(value)
    } else if (item && typeof item === 'object') {
      for (const [key, value] of Object.entries(item as Record<string, unknown>)) {
        if (key === 'sensitivity' && typeof value === 'number') top = Math.max(top, value)
        else if (value && typeof value === 'object') stack.push(value)
      }
    }
  }
  if (top) noteMarking(top)
}

const subscribe = (listener: () => void) => {
  listeners.add(listener)
  return () => { listeners.delete(listener) }
}
export const useHighestMarking = () => useSyncExternalStore(subscribe, () => highest)

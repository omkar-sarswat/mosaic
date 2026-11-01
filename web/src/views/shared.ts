import type { CaseRow, User } from '../api'

export type Shared = {
  me: User | null
  caseId: string
  activeCase: CaseRow | undefined
  selected: string | null
  setSelected: (id: string | null) => void
  openGraph: (id: string) => void
  tick: number
  setError: (e: string) => void
  refresh: () => void
}

// One colour per object type, shared by Graph, lists and legends (Case Diary palette, current theme).
export { TYPE_COLOURS } from '../lib/icons'

export const shortDate = (s: string) => (s ? s.replace('T', ' ').slice(0, 16) : '')

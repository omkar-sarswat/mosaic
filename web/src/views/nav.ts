import type { CaseRow, User } from '../api'

export type ViewId = 'home' | 'leads' | 'studio' | 'dossier' | 'graph' | 'money' | 'globe' | 'cases' | 'alerts' | 'explore' | 'connect' | 'faces' | 'cop' | 'review' | 'oversight' | 'admin' | 'watch'

export type Nav = {
  me: User | null
  caseId: string
  activeCase: CaseRow | undefined
  tick: number
  /** the item a screen should open on arrival (a lead, a match, a proposal), set by open() */
  focus: string | null
  setError: (e: string) => void
  refresh: () => void
  openEntity: (id: string) => void
  openTrace: (id: string) => void
  openGraph: (id: string) => void
  openCase: (id: string) => void
  openGlobe: (caseId?: string) => void
  openConnect: (id?: string) => void
  go: (v: ViewId) => void
  open: (v: ViewId, id?: string | null) => void
}

import { call, type ObjSummary, type Provenance, type User } from './api'
import type { GEdgeIn, GNodeIn } from './components/GraphCanvas'

export type RecordItem = ObjSummary & { domain: string; sources?: string[]; match?: string; relations?: string[] }
export type EventItem = { id: string; at: string; kind: string; title: string; domain: string; object_ids: string[]; location: string | null; lat: number | null; lon: number | null; accuracy_m: number | null; source: string }
export type Finding = { id: string; rule: string; version: string; title: string; object_ids: string[]; detail: string; limitation: string; measurements: Record<string, unknown>; status: string }
export type Note = { id: string; case_id: string; object_id: string | null; body: string; author: string; created_at: string }
export type Board = { id: string; title: string; object_ids: string[]; created_by: string; created_at: string }
export type Overview = { case: { id: string; max_depth: number; purpose: string }; counts: Record<string, number>; domains: Record<string, number>; types: Record<string, number>; recent_events: EventItem[]; findings: Finding[]; cases: { id: string; title: string; agency: string; purpose: string; status: string }[]; scope: string; generated_at: string }
export type ObjectDetail = { object: RecordItem; related: RecordItem[]; edges: GEdgeIn[]; provenance: Provenance[]; timeline: EventItem[]; findings: Finding[]; notes: Note[]; coverage: Record<string, number>; documents: RecordItem[] }
export type Source = { source: string; records: number; types: string[]; latest: string; synthetic: boolean; assertions: number; connection: string; live: boolean }
export type ShareRequest = { id: string; recipient: string; reason: string; requested_by: string; requested_at: string; status: string; decided_by: string | null }
export type Collaboration = { members: User[]; requests: ShareRequest[]; recipients: User[]; can_approve: boolean; note: string }
export type Metrics = { precision: number; recall: number; f1: number; average_precision: number; roc_auc: number; brier: number; true_positive: number; false_positive: number; true_negative: number; false_negative: number; pairs: number; threshold: number }
export type ModelReport = { name: string; family: string; version: string; status: string; trained_at: string; seed: number; runtime: string; training_records: number; features: number; split_policy: string; splits: Record<string, { records: number; identities: number; pairs: number; positive_pairs: number; blocking_recall: number }>; identity_overlap: number; test: Metrics; validation: Metrics; baselines: Record<string, Metrics>; f1_pair_bootstrap_95: number[]; model_sha256: string; limitations: string[] }
export type Comparison = { version: string; match_score: number; threshold: number; recommendation: string; identity_conflict: boolean; contributions: { feature: string; value: number; log_odds: number }[]; limitation: string }

const query = (params: Record<string, string | number>) => new URLSearchParams(Object.entries(params).map(([k, v]) => [k, String(v)])).toString()
const get = <T>(path: string, params: Record<string, string | number> = {}, signal?: AbortSignal) => call<T>(`/api/investigation/${path}?${query(params)}`, { signal })
const post = <T>(path: string, body: unknown) => call<T>(`/api/investigation/${path}`, { method: 'POST', body: JSON.stringify(body) })

export const investigation = {
  overview: () => get<Overview>('overview'),
  search: (q = '', type = '', domain = '', source = '', offset = 0, signal?: AbortSignal) => get<{ items: RecordItem[]; total: number; facets: Record<string, number>; offset: number; limit: number }>('search', { q, type, domain, source, offset, limit: 40 }, signal),
  object: (id: string) => get<ObjectDetail>('object', { id }),
  graph: () => get<{ nodes: GNodeIn[]; edges: GEdgeIn[]; max_depth: number }>('graph'),
  path: (a: string, b: string) => get<{ nodes: RecordItem[]; edges: GEdgeIn[]; hops: number | null; reason: string }>('path', { a, b }),
  timeline: (domain = '', after = '', before = '') => get<{ events: EventItem[]; timezone: string; note: string }>('timeline', { domain, after, before }),
  sources: () => get<{ sources: Source[]; note: string }>('sources'),
  findings: () => get<{ findings: Finding[]; note: string; version: string }>('findings'),
  notes: () => get<Note[]>('notes'),
  addNote: (body: string, object_id?: string) => post<Note>('notes', { body, object_id }),
  boards: () => get<Board[]>('boards'),
  saveBoard: (title: string, object_ids: string[]) => post<Board>('boards', { title, object_ids }),
  collaboration: () => get<Collaboration>('collaboration'),
  requestShare: (recipient: string, reason: string) => post('collaboration', { recipient, reason }),
  decideShare: (id: string, approve: boolean) => post(`collaboration/${encodeURIComponent(id)}`, { approve }),
  models: () => get<{ record_linkage: ModelReport | null; checks: string[]; scope: string }>('models'),
  compare: (a: string, b: string) => get<Comparison>('compare', { a, b }),
  export: () => get<unknown>('export'),
}

export const domainLabels: Record<string, string> = { identity: 'People & identity', organisations: 'Organisations', communications: 'Communications & devices', movement: 'Events & movement', documents: 'Documents', cyber: 'Digital evidence', incidents: 'Incidents', assets: 'Places & assets', finance: 'Financial records', other: 'Other' }
export function formatTime(value: string) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat('en-IN', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Kolkata' }).format(date)
}

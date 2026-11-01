import { bearer, reauthenticate } from './auth'
import { scanMarking } from './lib/marking'
import type { FeatureCollection } from 'geojson'

// Thin client for the DRISHTI API. Every call carries the acting user and the active case,
// because the server refuses personal data without a stated purpose.

export type User = {
  id: string
  name: string
  role: string
  roles: string[]
  clearance: number
  districts: string[]
  agency: string
}

export type CaseRow = {
  id: string
  purpose: string
  legal_basis: string
  fir_no: string | null
  status: string
  max_depth: number
  opened_by: string
  opened_at: string
}

export type ObjSummary = {
  id: string
  type: string
  title: string
  district: string | null
  district_name: string | null
  sensitivity: number
  synthetic: boolean
  masked: string[]
  props: Record<string, unknown>
  lat?: number | null
  lon?: number | null
}

export type Provenance = { prop: string; source: string; record: string; ingested_at: string; confidence: number }

export type ObjDetail = ObjSummary & {
  provenance: Provenance[]
  resolved_records?: ObjSummary[]
  match_links?: { id: string; other: string; status: string; confidence: number; explanation?: { features: string[]; probability: number } }[]
  link_counts: Record<string, number>
  in_case: boolean
  geom?: unknown
}

export type GNode = {
  id: string
  type: string
  label: string
  district: string | null
  district_name?: string | null
  hop: number
  broker: number
  group: boolean
  count?: number
  hub: boolean
  in_case: boolean
  synthetic: boolean
}

export type GEdge = {
  id: string
  source: string
  target: string
  type: string
  evidence: 'corroborated' | 'single' | 'suggested'
  status: string
  confidence: number
  sources: { source: string; record: string }[]
  props: Record<string, unknown>
}

export type Graph = { root: string; nodes: GNode[]; edges: GEdge[]; hidden: { type: string; reason: string; count: number }[]; depth: number; max_depth: number }

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

let currentUser = ''
let currentCase = ''

export function setIdentity(user: string, caseId: string) {
  currentUser = user
  currentCase = caseId
}

/** Who is asking, as a cache key: anything cached per viewer (photographs) is kept per user and case. */
export const identityKey = () => `${currentUser}|${currentCase}`

function identityHeaders(): Record<string, string> {
  const headers: Record<string, string> = {}
  const token = bearer()
  if (token) headers.Authorization = `Bearer ${token}`
  else if (currentUser) headers['X-DRISHTI-User'] = currentUser
  if (currentCase) headers['X-DRISHTI-Case'] = currentCase
  return headers
}

export async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json', ...identityHeaders() }
  const res = await fetch(path, { ...init, headers: { ...headers, ...(init.headers as Record<string, string>) } })
  if (res.status === 401) reauthenticate()
  if (!res.ok) {
    let msg = res.statusText
    try {
      const body = await res.json()
      msg = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    } catch {
      /* not json */
    }
    throw new ApiError(res.status, msg)
  }
  const body = (await res.json()) as T
  scanMarking(body)
  return body
}

const q = (params: Record<string, string | number | undefined | null>) => {
  const u = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== '') u.set(k, String(v))
  const s = u.toString()
  return s ? `?${s}` : ''
}

export type TodayEntry = {
  at: string | null; kind: 'approval' | 'request' | 'lead' | 'match' | 'alarm' | 'denied' | 'watch' | 'search'; ref: string; id: string; title: string; detail: string
  mark: 'proposed' | 'pending' | 'approved' | 'rejected' | 'dismissed' | 'critical' | 'flagged' | 'new'; view: string; target: string | null; by: string | null; by_name: string | null
}
export type TodayStamp = { at: string | null; decision: string; by: string; by_name: string | null; what: string; ref: string; requested_by: string | null }
export type TodaySubject = { id: string; name: string; accused_in: number; basis: string }
export type TodayCase = {
  id: string; title: string; purpose: string; legal_basis: string; agency: string | null; opened_at: string | null; opened_by: string | null; opened_by_name: string | null
  depth: number; members: string[]; people: number; subjects: TodaySubject[]; evidence_count: number
  evidence: { id: string; filename: string; source_type: string | null; uploaded_by: string; uploaded_at: string; status: string }[]; approver: string | null
}
export type Today = {
  role: string; person: User; case: TodayCase | null; entries: TodayEntry[]; stamps: TodayStamp[]
  counts: { leads_open: number; review_pending: number; approvals_waiting: number; requests_waiting: number; alarms: number; watching?: number }
}

export const api = {
  today: () => call<Today>('/api/today'),
  devUsers: () => call<User[]>('/api/dev/users'),
  me: () => call<{ user: User; cases: CaseRow[]; active_case: unknown }>('/api/me'),
  search: (text: string, types?: string) =>
    call<{ results: ObjSummary[]; withheld: { reason: string; count: number }[] }>(`/api/search${q({ q: text, types })}`),
  object: (id: string) => call<ObjDetail>(`/api/objects/${encodeURIComponent(id)}`),
  graph: (id: string, depth = 1) => call<Graph>(`/api/objects/${encodeURIComponent(id)}/graph${q({ depth })}`),
  timeline: (id: string) => call<{ events: { at: string; object: ObjSummary; via: string }[] }>(`/api/objects/${encodeURIComponent(id)}/timeline`),
  path: (a: string, b: string) => call<{ nodes: GNode[]; edges: GEdge[]; hops: number }>(`/api/path${q({ a, b })}`),
  explore: (f: Record<string, string | undefined>) =>
    call<{
      total: number
      by_district: { key: string; label: string; count: number }[]
      by_section: { key: string; count: number }[]
      by_month: { key: string; count: number }[]
      by_kind: { key: string; count: number }[]
      note: string
    }>(`/api/explore/incidents${q(f)}`),
  districts: () => call<FeatureCollection>('/api/map/districts'),
  hazards: () => call<FeatureCollection>('/api/map/hazards'),
  assets: () => call<FeatureCollection>('/api/map/assets'),
  impact: (id: string) =>
    call<{
      hazard: Record<string, unknown>
      districts: { lgd_code: string; name: string }[]
      hospitals_in_area: number
      hospitals: { id: string; name: string; district: string }[]
      dispatches: { id: number; resource: string; quantity: number; admin_unit: string; dispatched_by: string; dispatched_at: string }[]
    }>(`/api/hazards/${encodeURIComponent(id)}/impact`),
  action: <T = Record<string, unknown>>(name: string, body: Record<string, unknown>) =>
    call<T>(`/api/actions/${name}`, { method: 'POST', body: JSON.stringify(body) }),
  review: () =>
    call<{ id: string; probability: number; explanation: { features: string[]; review_reasons?: string[]; probability: number }; a: ObjSummary; b: ObjSummary }[]>('/api/review'),
  expansions: () => call<{ id: string; case_id: string; depth: number; reason: string; requested_by: string; requested_at: string }[]>('/api/expansions'),
  audit: (f: Record<string, string | undefined> = {}) =>
    call<
      {
        seq: number
        ts: string
        user_id: string
        role: string
        case_id: string | null
        purpose: string | null
        action: string
        outcome: string
        object_ids: string[]
        detail: Record<string, unknown>
        hash: string
      }[]
    >(`/api/audit${q(f)}`),
  verify: () => call<{ ok: boolean; checked: number; head?: string; first_bad_seq?: number }>('/api/audit/verify'),
  alerts: () => call<{ severity: string; rule: string; user_id: string; seq: number; ts: string; detail: string }[]>('/api/audit/alerts'),
  seal: () => call<{ day: string; sealed: boolean; root_hash?: string }>('/api/audit/seal', { method: 'POST' }),
  transparency: () =>
    call<{
      audit_events_by_action: Record<string, number>
      audit_events_by_outcome: Record<string, number>
      cases_by_purpose: Record<string, number>
      objects_by_source: Record<string, number>
    }>('/api/transparency'),
  quality: () => call<{ resolve: Record<string, unknown> | null; lgd: { object: string; issue: string; source: string }[]; sachet: unknown }>('/api/quality'),
  ontology: () => call<{ purposes: string[] }>('/api/ontology'),
}

// ---------------------------------------------------------------------------- intelligence API
export type Alert = {
  id: string
  rule: string
  severity: 'high' | 'medium' | 'low'
  subject_id: string
  subject_type: string
  subject?: string
  holder?: string
  holder_id?: string | null
  score: number
  amount: number | null
  summary: string
  window_start?: string | null
  details?: { rule_text: string; evidence_txns: string[] }
}

export type Suspect = {
  id: string
  name: string
  score: number
  role: string
  hops: number
  factors: Record<string, number>
  evidence: string[]
  why_in_network: string
  city?: string
  occupation?: string
  declared_income?: number
}

export type Linked = ObjSummary & { relations: string[]; alerts: Alert[] }
export type AccountCard = Linked & {
  summary: { in_total: number; out_total: number; in_count: number; out_count: number; cash_in: number; cash_out: number; first: string | null; last: string | null }
  monthly: { month: string; in: number; out: number }[]
  top_senders: { account: string | null; label: string; holder: string | null; amount: number }[]
  top_receivers: { account: string | null; label: string; holder: string | null; amount: number }[]
}
export type TimelineEvent = { at: string; kind: string; title: string; detail?: string; id?: string | null }

export type Dossier = {
  object: ObjSummary & { geom?: unknown }
  provenance: Provenance[]
  documents: { key: string; label: string; value: string; masked: boolean; source: string }[]
  photos?: { id: string; object_id: string; case_id: string | null; source: string; legal_basis: string | null; added_by: string; added_at: string; width: number; height: number; synthetic: boolean }[]
  fused_records: (ObjSummary & { sources: string[] })[]
  sources: string[]
  accounts: AccountCard[]
  account_summary?: { monthly: { month: string; in: number; out: number }[]; in_total: number; out_total: number }
  crypto: Linked[]
  phones: Linked[]
  vehicles: Linked[]
  properties: Linked[]
  devices: Linked[]
  organisations: Linked[]
  locations: Linked[]
  incidents: Linked[]
  people: Linked[]
  associates: Associate[]
  flags?: Flag[]
  money: { in_total: number; out_total: number; accounts: number; monthly: { month: string; in: number; out: number }[] }
  travel: { id: string; ts: string; from_city: string; to_city: string; from_country: string; to_country: string; from_lat: number; from_lon: number; to_lat: number; to_lon: number; pnr: string }[]
  alerts: Alert[]
  timeline: TimelineEvent[]
  lead?: Suspect & { rank: number; of: number; case: string }
  criminal?: { records: CrimRecord[]; history_sheet: string | null; roles: Record<string, number> }
  movement?: { reads: { id: string; vehicle_id: string; ts: string; plaza: string; lat: number; lon: number; kind: string | null }[]; total: number; places: Record<string, number> }
  comms?: { calls: number; monthly: { month: string; calls: number }[]; top_contacts: { label: string; calls: number; foreign: boolean }[]; towers: { tower: string; calls: number }[]; first: string | null; last: string | null }
  procurement?: { orders: number; dealers: number; monthly: { month: string; substance: string; kg: number }[]; licence_on_record: string | null; licensed_for: string[]; licences_quoted: string[] }
  tenders?: { tender: string; title: string; estimate: number; bid: number; at: string; won: boolean }[]
  firearms?: ObjSummary[]
  findings?: Lead[]
  deconfliction?: { other_track_leads: number; tracks: Record<string, number> }
  withheld_sections?: string[]
}

export type CrimRecord = { id: string; title: string; role: string; agency: string; kind: string; sections: string[]; status: string; occurred_at: string; chargesheeted_on: string | null; summary: string; co_accused: number }

export type TxRow = {
  id: string
  ts: string
  direction: 'in' | 'out'
  amount: number
  channel: string
  narration: string
  ref: string
  country: string
  account: string
  counterparty_account: string | null
  counterparty: string
  counterparty_holder: string | null
  flagged: boolean
}

export type Trace = {
  direction: string
  nodes: { id: string; label: string; holder: string | null; holder_name: string; holder_type: string; kind: string; hop: number; alerts: string[] }[]
  links: { source: string; target: string; value: number; count: number }[]
  sinks: Record<string, number>
  beneficiaries: { id: string; name: string; type: string; amount: number }[]
  traced_total: number
  accounts_reached: number
}

export type CaseBoard = {
  case: CaseRow & { title: string; agency: string; legal_hold?: number; retention_until?: string | null; purged_at?: string | null }
  seeds: ObjSummary[]
  stats: { network_objects: number; persons: number; organisations: number; accounts: number; phones: number; alerts: number; money_onward: number; money_sources: number; sinks: Record<string, number>; suspects_50: number }
  suspects: Suspect[]
  alerts: Alert[]
  beneficiaries: { id: string; name: string; type: string; amount: number }[]
  sources: { id: string; name: string; type: string; amount: number }[]
  cross_case: { case_id: string; title: string; agency: string; shared: { id: string; name: string; role: string }[] }[]
  leads: { id: string; title: string; stage: string; subject_id: string | null; assignee: string; notes: { by: string; at: string; text: string }[]; updated_at: string }[]
  stages: string[]
  timeline: TimelineEvent[]
}

export type NetNode = { id: string; type: string; label: string; score: number | null; role: string | null; alerts: number; seed: boolean; kind?: string }
export type NetEdge = { id: string; source: string; target: string; type: string; evidence: string; amount?: number; count?: number; status: string }

export type Home = {
  counts: Record<string, number>
  alerts_by_rule: { rule: string; n: number; amount: number }[]
  alerts_by_severity: Record<string, number>
  top_alerts: Alert[]
  cases: { id: string; title: string; agency: string; purpose: string; status: string; suspects?: number; network?: number; top?: { id: string; name: string; score: number; role: string }[] }[]
  incidents_by_agency: Record<string, number>
  recent_cases: { id: string; title: string; agency: string; kind: string; summary: string; occurred_at: string; amount?: number }[]
  monthly_volume: { month: string; amount: number; n: number }[]
}

export type GlobeData = {
  arcs: { from: string; to: string; from_id?: string; to_id?: string; from_coord: [number, number]; to_coord: [number, number]; amount: number; count: number; international: boolean }[]
  trips: { person: string; from: string; to: string; from_coord: [number, number]; to_coord: [number, number]; ts: string }[]
  entities: { id: string; type: string; label: string; lon: number; lat: number; score: number | null; role: string | null; city: string; kind?: string; place?: string }[]
  incidents: { id: string; label: string; agency: string; kind: string; lon: number; lat: number; summary: string }[]
  agency_colours: Record<string, string>
  bounds?: [number, number, number, number] | null
  ties?: { a: string; b: string; a_label: string; b_label: string; a_coord: [number, number]; b_coord: [number, number]; kinds: string[]; inferred: boolean }[]
}

export type Basis = { kind: string; weight: number; detail: string; refs: string[] }
export type Flag = { id: string; subject_id: string; code: string; severity: 'high' | 'medium' | 'low' | 'info'; weight: number; title: string; summary: string; evidence: Record<string, unknown>; inputs: string[] }
export type Associate = ObjSummary & { why: string[]; strength: number; score?: number; summary?: string; kinds?: string[]; bases?: Basis[]; inferred?: boolean; in_case?: boolean }
export type ConnectPath = {
  from: ObjSummary; to: ObjSummary; connected: boolean; hops?: number
  nodes?: ObjSummary[]; steps?: { from: string; to: string; type: string; label: string; via: Record<string, string> }[]; note?: string
}
export type WhyLinked = { from: ObjSummary; to: ObjSummary; a: string; b: string; score: number; bases: Basis[]; labels: Record<string, string> }
export type FlagRow = ObjSummary & { score: number; flags: number; high: number; codes: string[] }

const enc = encodeURIComponent
export const intel = {
  home: () => call<Home>('/api/intel/home'),
  flags: (id: string) => call<{ object: ObjSummary; flags: Flag[]; note: string }>(`/api/intel/flags/${enc(id)}`),
  associates: (id: string) => call<{ object: ObjSummary; associates: Associate[]; labels: Record<string, string>; note: string }>(`/api/intel/associates/${enc(id)}`),
  connect: (a: string, b: string) => call<ConnectPath>(`/api/intel/connect${q({ a, b })}`),
  whyLinked: (a: string, b: string) => call<WhyLinked>(`/api/intel/why-linked${q({ a, b })}`),
  flagboard: () => call<{ people: FlagRow[]; note: string }>('/api/intel/flagboard'),
  dossier: (id: string) => call<Dossier>(`/api/intel/entity/${enc(id)}`),
  transactions: (id: string, p: { account?: string; limit?: number; offset?: number; min_amount?: number } = {}) =>
    call<{ rows: TxRow[]; total: number }>(`/api/intel/tx/${enc(id)}${q(p)}`),
  calls: (id: string) =>
    call<{ numbers: string[]; total: number; contacts: { number: string; calls: number; seconds: number; first: string; last: string; owner: string | null; owner_id: string | null }[]; hourly: number[]; towers: { id: string; label: string; lat: number; lon: number; hits: number }[] }>(
      `/api/intel/calls/${enc(id)}`,
    ),
  trace: (id: string, p: { direction?: string; hops?: number; min_amount?: number; window_days?: number } = {}) => call<Trace>(`/api/intel/trace${q({ id, ...p })}`),
  board: (caseId: string) => call<CaseBoard>(`/api/intel/cases/${enc(caseId)}/board`),
  network: (caseId: string) => call<{ nodes: NetNode[]; edges: NetEdge[] }>(`/api/intel/cases/${enc(caseId)}/network`),
  alerts: (p: { rule?: string; severity?: string } = {}) => call<{ alerts: Alert[]; rules: { rule: string; n: number }[] }>(`/api/intel/alerts${q(p)}`),
  globe: (caseId?: string) => call<GlobeData>(`/api/intel/globe${q({ case: caseId })}`),
}


// ---------------------------------------------------------------------------- casework
export type Exhibit = {
  id: string
  case_id: string
  filename: string
  mime: string | null
  size: number
  sha256: string
  md5: string
  description: string | null
  source_type: string | null
  device_make: string | null
  device_model: string | null
  device_serial: string | null
  device_id: string | null
  seized_from: string | null
  legal_order: string | null
  collected_at: string | null
  uploaded_by: string
  uploaded_at: string
  status: string
  custody_events: number
}
export type ExportRow = { id: string; kind: string; filename: string; sha256: string; size: number; exported_by: string; exported_at: string; recipient: string; marking: string }
export type CustodyRow = { seq: number; ts: string; actor: string; action: string; detail: Record<string, unknown>; hash: string }

async function raw(path: string, init: RequestInit): Promise<Response> {
  const res = await fetch(path, { ...init, headers: { ...identityHeaders(), ...(init.headers as Record<string, string>) } })
  if (res.status === 401) reauthenticate()
  if (!res.ok) {
    let msg = res.statusText
    try {
      msg = (await res.json()).detail
    } catch {
      /* not json */
    }
    throw new ApiError(res.status, msg)
  }
  return res
}

export const casework = {
  sourceTypes: () => call<string[]>('/api/evidence/source-types'),
  list: (caseId: string) => call<Exhibit[]>(`/api/cases/${encodeURIComponent(caseId)}/evidence`),
  upload: (caseId: string, form: FormData) => raw(`/api/cases/${encodeURIComponent(caseId)}/evidence`, { method: 'POST', body: form }).then((r) => r.json() as Promise<Exhibit>),
  verify: (id: string) => call<{ file_intact: boolean | null; custody_intact: boolean; custody_events: number; sha256: string }>(`/api/evidence/${encodeURIComponent(id)}/verify`, { method: 'POST' }),
  custody: (id: string) => call<CustodyRow[]>(`/api/evidence/${encodeURIComponent(id)}/custody`),
  download: (id: string) => raw(`/api/evidence/${encodeURIComponent(id)}/download`, { method: 'GET' }),
  exportCase: (caseId: string, body: { kind: string; recipient?: string; recipient_clearance?: number }) =>
    raw(`/api/cases/${encodeURIComponent(caseId)}/export`, { method: 'POST', body: JSON.stringify(body), headers: { 'Content-Type': 'application/json' } }),
  exports: (caseId: string) => call<ExportRow[]>(`/api/cases/${encodeURIComponent(caseId)}/exports`),
  retention: () =>
    call<{ due: CaseRow[]; held: { id: string; title: string; hold_reason: string; retention_until: string }[]; scheduled: { id: string; title: string; retention_until: string }[]; purged: { id: number; case_id: string | null; legal_order: string | null; purged_at: string; purged_by: string; reason: string; counts: Record<string, number>; manifest_sha256: string }[] }>(
      '/api/retention',
    ),
  runRetention: () => call<{ purged: unknown[] }>('/api/retention/run', { method: 'POST' }),
}

// ---------------------------------------------------------------------------- faces
export type FaceBox = { box: number[]; score: number; landmarks: number[][] }
export type ProbeResult = { media_id: string; evidence_id: string; sha256: string; width: number; height: number; faces: (FaceBox & { face_id: string; index: number })[] }
export type Candidate = { match_id: string | null; object: ObjSummary; similarity: number; band: string; gallery_media: string; photo_source: string; photo_legal_basis: string }
export type FaceStatus = { available: boolean; gallery_faces: number; match_threshold: number; strong_threshold: number; models: string[]; policy: string }
export type FaceMatch = { id: string; status: string; similarity: number; reason: string; searched_by: string; decided_by: string | null; decision_reason: string | null; created_at: string; candidate: ObjSummary | null }

export const faces = {
  status: () => call<FaceStatus>('/api/faces/status'),
  /** the first photograph on record of each visible person (resolved entity), as media ids */
  portraits: (ids: string[]) => call<Record<string, string>>(`/api/faces/portraits${q({ ids: ids.join(',') })}`),
  photosOf: (oid: string) => call<{ id: string; source: string; legal_basis: string; added_by: string; added_at: string; face_id: string; score: number }[]>(`/api/faces/object/${encodeURIComponent(oid)}`),
  enrol: (form: FormData) => raw('/api/faces/enrol', { method: 'POST', body: form }).then((r) => r.json()),
  probe: (form: FormData) => raw('/api/faces/probe', { method: 'POST', body: form }).then((r) => r.json() as Promise<ProbeResult>),
  search: (probe_face_id: string, reason: string) => call<{ probe_face: string; threshold: number; gallery_searched: number; withheld: number; candidates: Candidate[]; note: string }>('/api/faces/search', { method: 'POST', body: JSON.stringify({ probe_face_id, reason }) }),
  decide: (matchId: string, decision: 'confirm' | 'reject', reason: string) => call<{ match_id: string; status: string }>(`/api/faces/matches/${encodeURIComponent(matchId)}/decide`, { method: 'POST', body: JSON.stringify({ decision, reason }) }),
  matches: () => call<FaceMatch[]>('/api/faces/matches'),
  async media(mid: string, p: { thumb?: number; face?: number } = {}): Promise<string> {
    const r = await raw(`/api/faces/media/${encodeURIComponent(mid)}${q(p as Record<string, string | number | undefined>)}`, { method: 'GET' })
    return URL.createObjectURL(await r.blob())
  },
}

export async function saveResponse(res: Response, fallback: string) {
  const blob = await res.blob()
  const cd = res.headers.get('Content-Disposition') || ''
  const name = /filename="([^"]+)"/.exec(cd)?.[1] || fallback
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = name
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 2000)
  return { name, sha256: res.headers.get('X-SHA256') || '' }
}


// ---------------------------------------------------------------------------- mission-track pattern leads
export type Party = { id: string | null; label: string; type: string | null; revealed: boolean; summary: ObjSummary | null }
export type Lead = {
  id: string
  detector: string
  version: string
  tracks: string[]
  severity: 'high' | 'medium' | 'low'
  title: string
  summary: string
  parties: Party[]
  measurements: Record<string, unknown>
  thresholds: Record<string, unknown>
  evidence_counts: Record<string, number>
  evidence: Record<string, unknown> | null
  window: [string | null, string | null]
  district: string | null
  status: string
  case_id: string | null
  disposition: string | null
  pseudonymous: boolean
}
export type DetectorCard = {
  id: string; version: string; title: string; tracks: string[]; scope: string; question: string; inputs: string[]; algorithm: string
  evasion: string[]; benign: string[]; blind_spots: string[]; references: string[]; complexity: string; depends: string[]
}
export type LeadDetail = Lead & {
  detector_card: DetectorCard | null
  requests: { id: string; purpose: string; title: string; requested_by: string; requested_at: string; status: string; decided_by: string | null; case_id: string | null }[]
  purposes: string[]
}
export type EvalRow = {
  detector: string; title: string; tracks: string[]; scope: string; hits: number; hit: number; cross: number; benign: number; background: number
  planted: number; found: number; recall: number | null; precision: number | null; benign_lookalikes: number; eligible: number; eligible_label: string
  false_leads_per_1000: number | null; seconds: number | null
}
export type RedTeamRow = { id: string; label: string; loophole: string; change: string; expected: string; outcome: string; as_designed: boolean; before: string; after: string; new_background_false_leads: number }
export type Evaluation = {
  generated_at: string
  detectors: EvalRow[]
  summary: { detectors: number; planted_networks: number; found: number; hits: number; benign_fired: number; background_false_leads: number; recall: number; precision: number }
  caveat: string
  redteam?: { tactics: RedTeamRow[]; closed: number; known_limits_confirmed: number; surprises: string[] }
}

export const patterns = {
  catalog: () =>
    call<{ detectors: DetectorCard[]; tracks: Record<string, { label: string; lead: string }>; agencies: Record<string, { purposes: string[]; tracks: string[] }>; my_tracks: string[]; record_classes: Record<string, string>; purpose_classes: Record<string, string[]> }>(
      '/api/patterns/catalog',
    ),
  summary: () => call<{ visible: number; open: number; by_track: Record<string, number>; by_detector: Record<string, number>; by_severity: Record<string, number>; by_status: Record<string, number>; all_leads: number; last_run: { started_at: string; data_fingerprint: string; counts: Record<string, number>; timings: Record<string, number> } | null }>('/api/patterns/summary'),
  leads: (p: { track?: string; detector?: string; status?: string } = {}) => call<{ leads: Lead[]; tracks: string[] }>(`/api/patterns/leads${q(p)}`),
  lead: (id: string) => call<LeadDetail>(`/api/patterns/leads/${encodeURIComponent(id)}`),
  requestCase: (id: string, body: { purpose: string; legal_basis: string; title?: string }) =>
    call<{ request_id: string; status: string; next: string }>(`/api/patterns/leads/${encodeURIComponent(id)}/request-case`, { method: 'POST', body: JSON.stringify(body) }),
  requests: () => call<{ requests: { id: string; hit_id: string; purpose: string; title: string; requested_by: string; requested_at: string; status: string; case_id: string | null; lead_title: string; severity: string; detector: string }[] }>('/api/patterns/requests'),
  approve: (rid: string) => call<{ case_id: string; lead: string; subjects: number }>(`/api/patterns/requests/${encodeURIComponent(rid)}/approve`, { method: 'POST' }),
  dismiss: (id: string, reason: string) => call<{ ok: boolean }>(`/api/patterns/leads/${encodeURIComponent(id)}/dismiss`, { method: 'POST', body: JSON.stringify({ reason }) }),
  evaluation: () => call<Evaluation>('/api/patterns/evaluation'),
  run: () => call<{ leads: number; seconds: number }>('/api/patterns/run', { method: 'POST' }),
}

// ---------------------------------------------------------------------------- data studio (intake)
export type IntakeSource = { id: string; title: string; holder: string; legal: string; description: string; kind: 'table' | 'text'; classes: string[]; class_labels: string[]; record_type: string; missing: string[] }
export type ProfileCol = {
  column: string; rows: number; filled: number; completeness: number; distinct: number; detected: string; detected_label: string; confidence: number
  shapes: { shape: string; n: number; example: string }[]; formats: number; placeholders: number; would_change: number; would_reject: number; suggested: string[]; ambiguous: number; values: { value: string; n: number }[]
}
export type RecipeStep = { column: string; step: string }
export type IntakeMatch = { status: 'existing' | 'probable' | 'new'; basis: string; person: string | null; record: string | null; visible?: boolean; clashes: { person: string | null; basis: string[]; name_on_record: string | null }[] }
export type TextTag = { kind: string; start: number; end: number; text: string; value: unknown; object: string | null; owners: string[]; basis?: string }
export type IntakeRow = { row: number; values: Record<string, unknown>; match: IntakeMatch; identity: string; tags: TextTag[] }
export type IntakeOp = { op: string; type?: string; id?: string; prop?: string; value?: unknown; old?: unknown; record: string; props?: Record<string, unknown>; src?: string; dst?: string; a?: string; b?: string; basis?: string }
export type IntakeParty = { key: string; label: string; status: string; person: string | null }
export type IntakePattern = { id: string; kind: string; severity: 'review' | 'info'; title: string; detail: string; benign: string; rows: number[]; parties: IntakeParty[] }
export type IntakeSummary = { rows: number; clean: number; quarantined: number; duplicates: number; cells_changed: number; existing: number; probable: number; new: number; identities: number; ops: Record<string, number>; creates: Record<string, number> }
export type IntakePreview = {
  source: string; title: string; holder: string; legal: string; description: string; kind: 'table' | 'text'; columns: string[]; classes: string[]
  profile: ProfileCol[]; recipe: RecipeStep[]; steps: Record<string, string>; mapping: Record<string, string[]>; mapping_options: string[]; mapping_errors: string[]
  record: { type: string; key: string | null; link: string }; switch: Record<string, { by: string; cases: Record<string, string> }>
  sample: Record<string, unknown>[]; changes: { row: number; column: string; before: unknown; after: unknown; note: string }[]
  quarantine: { row: number; values: Record<string, unknown>; reasons: string[] }[]; duplicates: { row: number; duplicate_of: number }[]
  rows: IntakeRow[]; ops: { counts: Record<string, number>; items: IntakeOp[] }; summary: IntakeSummary
  lenses: { patterns: IntakePattern[]; graph: { nodes: { id: string; label: string; kind: string; status: string; person?: string | null }[]; links: { source: string; target: string; label: string }[] }; places: { city: string; lat: number | null; lon: number | null; rows: number; existing?: number; probable?: number; new?: number }[] }
  lineage: { stage: string; label: string; n: number }[]; fingerprint: string
}
export type IntakeProposal = {
  id: string; case_id: string; source: string; recipe: { recipe: RecipeStep[]; mapping: Record<string, string[]>; note: string }; legal_order: string
  summary: IntakeSummary & { leads: { title: string; kind: string }[]; title: string }; fingerprint: string; requested_by: string; requested_at: string
  status: 'pending' | 'approved' | 'rejected' | 'reverted'; decided_by: string | null; decided_at: string | null; decision_reason: string | null; applied: { applied: Record<string, number>; skipped: number } | null
}
export type RevisionCard = { id: number; object_id: string; prop: string | null; op: string; old_value: unknown; new_value: unknown; source: string; record: string; proposal_id: string; actor: string; at: string; legal_order: string | null; case_id: string | null }

export const intake = {
  sources: () => call<{ sources: IntakeSource[]; case: { id: string; purpose: string } | null; steps: Record<string, string> }>('/api/intake/sources'),
  preview: (body: { source: string; recipe?: RecipeStep[] | null; mapping?: Record<string, string[]> | null }) =>
    call<IntakePreview>('/api/intake/preview', { method: 'POST', body: JSON.stringify(body) }),
  propose: (body: { source: string; recipe?: RecipeStep[] | null; mapping?: Record<string, string[]> | null; legal_order: string; note?: string }) =>
    call<{ proposal: string; summary: IntakeSummary; leads: { title: string; kind: string }[] }>('/api/intake/proposals', { method: 'POST', body: JSON.stringify(body) }),
  proposals: () => call<{ proposals: IntakeProposal[] }>('/api/intake/proposals'),
  proposal: (id: string) => call<IntakeProposal & { ops: { counts: Record<string, number>; items: IntakeOp[] } }>(`/api/intake/proposals/${encodeURIComponent(id)}`),
  decide: (id: string, action: 'approve' | 'reject' | 'revert', reason: string) =>
    call<{ status: string; case: string; applied?: Record<string, number>; touches_case_subjects?: string[]; objects_removed?: number }>(
      `/api/intake/proposals/${encodeURIComponent(id)}/${action}`, { method: 'POST', body: JSON.stringify({ reason }) }),
  history: (objectId: string) => call<{ object_id: string; cards: RevisionCard[] }>(`/api/intake/history/${encodeURIComponent(objectId)}`),
}

// ---------------------------------------------------------------------------- watchlists, saved searches, area search
export type Ref = { id: string; label: string; type: string }
export type ActivityEvent = {
  at: string; kind: 'sighting' | 'call' | 'money' | 'travel' | 'alert' | 'fir' | 'record' | 'lead'; title: string; detail: string
  source: string | null; source_name: string | null; record: string | null; via: Ref | null; other: Ref | null
  lat: number | null; lon: number | null; place: string | null; new?: boolean
  priority: 'high' | 'medium' | 'low'; why: string | null; emph: string[]
}
export type Withheld = { reason: string; count: number }
export type Watch = {
  id: string; case_id: string; kind: 'object' | 'area'; object_id: string | null; label: string; reason: string
  created_by: string; created_by_name: string | null; created_at: string; since: string; seen_at: string; seen_by: string | null; seen_by_name: string | null
  status: 'active' | 'ended'; ended_by_name: string | null; ended_at: string | null; end_reason: string | null
  area: { lat: number; lon: number; radius_km: number; label: string } | null
  new?: number; new_key?: number; total?: number; latest?: string | null; unavailable?: string | null
}
export type Activity = {
  events: ActivityEvent[]; total: number; counts: Record<string, number>; new: number; new_key?: number; withheld: Withheld[]; cut?: string[]; unavailable?: string
  unlisted_numbers?: number; priorities?: { high: number; medium: number; low: number }
}
export type SavedSearch = {
  id: string; case_id: string; title: string; query: string; types: string; reason: string; created_by: string; created_by_name: string | null; created_at: string
  checked_at: string; checked_by_name: string | null; status: 'active' | 'ended'; new?: number; total?: number
}
export type AreaRead = { at: string; place: string; kind: string; detail?: string; lat: number; lon: number; source: string; source_name: string; record: string }
export type AreaItem = { record: ObjSummary; owner?: Ref | null; count: number; first: string; last: string; places?: string[]; reads: AreaRead[]; flag?: string | null }
export type AreaSite = { kind: 'toll' | 'anpr' | 'tower'; label: string; lat: number; lon: number; reads: number | null; km?: number; city?: string | null; road?: string | null; operator?: string | null; technology?: string | null }
export type AreaResult = {
  id: string; label: string; reason: string; centre: { lat: number; lon: number }; radius_km: number; window: [string, string]
  vehicles: AreaItem[]; phones: AreaItem[]; travellers: AreaItem[]
  residents: { record: ObjSummary; address: string; km: number; lat: number; lon: number; flag?: string | null }[]
  incidents: { record: ObjSummary; at: string; lat: number; lon: number }[]
  sites: AreaSite[]; unlisted_numbers: number; withheld: Withheld[]; cut: string[]; counts: Record<string, number>; flagged?: number
}

export const monitor = {
  list: () => call<{ case: string; watches: Watch[]; searches: SavedSearch[]; lookback_max: number; max_radius_km: number }>('/api/watches'),
  watch: (object_id: string, reason: string, lookback_days = 30) => call<Watch>('/api/watches', { method: 'POST', body: JSON.stringify({ object_id, reason, lookback_days }) }),
  watchArea: (body: { lat: number; lon: number; radius_km: number; label: string; reason: string; lookback_days?: number }) =>
    call<Watch>('/api/watches/area', { method: 'POST', body: JSON.stringify(body) }),
  of: (objectId: string) => call<{ watch: Watch | null }>(`/api/watches/of/${encodeURIComponent(objectId)}`),
  detail: (id: string) => call<{ watch: Watch; activity: Activity }>(`/api/watches/${encodeURIComponent(id)}`),
  seen: (id: string) => call<{ id: string; seen_at: string }>(`/api/watches/${encodeURIComponent(id)}/seen`, { method: 'POST' }),
  end: (id: string, reason: string) => call<{ id: string }>(`/api/watches/${encodeURIComponent(id)}/end`, { method: 'POST', body: JSON.stringify({ reason }) }),
  saveSearch: (body: { query: string; types?: string; title?: string; reason: string }) => call<SavedSearch>('/api/searches', { method: 'POST', body: JSON.stringify(body) }),
  search: (id: string) => call<{ search: SavedSearch; results: (ObjSummary & { new: boolean })[]; withheld: Withheld[] }>(`/api/searches/${encodeURIComponent(id)}`),
  searchSeen: (id: string) => call<{ id: string }>(`/api/searches/${encodeURIComponent(id)}/seen`, { method: 'POST' }),
  endSearch: (id: string, reason: string) => call<{ id: string }>(`/api/searches/${encodeURIComponent(id)}/end`, { method: 'POST', body: JSON.stringify({ reason }) }),
}

export const area = {
  sites: () => call<{ sites: AreaSite[]; max_radius_km: number; max_days: number }>('/api/area/sites'),
  search: (body: { lat: number; lon: number; radius_km: number; start: string; end: string; reason: string; label?: string }) =>
    call<AreaResult>('/api/area/search', { method: 'POST', body: JSON.stringify(body) }),
}

// ---------------------------------------------------------------------------- report builder
export type Cite = { source: string; source_name: string; record: string | null }
export type RecordView = {
  record: { id: string; type: string; title: string; sensitivity: number; masked: string[]; props: Record<string, unknown> }
  facts: { label: string; value: string; masked: boolean; cites: Cite[] }[]
  groups: { label: string; items: { id: string; label: string; detail: string; cites: Cite[] }[] }[]
  history: { id: string; label: string; role: string; at: string; detail: string; cites: Cite[] }[]
}
export type AreaBrief = { id: string; label: string; type: string; count: number | null; first: string | null; last: string | null; places: string[]; owner: string | null; cites: Cite[] }
export type BlockView = {
  withheld?: string; missing?: string; note?: string
  record?: RecordView['record']; facts?: RecordView['facts']; groups?: RecordView['groups']; history?: RecordView['history']
  exhibit?: { id: string; filename: string; description: string | null; source_type: string | null; sha256: string; seized_from: string | null; legal_order: string | null; collected_at: string | null; status: string; custody_events: number }
  lead?: { id: string; title: string; summary: string; severity: string; status: string; window: [string | null, string | null]; evidence_counts: Record<string, number> }
  area?: {
    id: string; label: string; lat: number; lon: number; radius_km: number; start: string; end: string; reason: string; searched_by: string; searched_at: string
    counts_then: Record<string, number>; counts_now: Record<string, number>; vehicles: AreaBrief[]; phones: AreaBrief[]; travellers: AreaBrief[]
  }
  pairs?: { a: string; b: string; how: string; cites: Cite[] }[]
}
export type ReportBlock = {
  id: string; type: 'heading' | 'text' | 'record' | 'exhibit' | 'lead' | 'area' | 'relations'
  text?: string; hint?: string; object_id?: string; show?: ('identity' | 'links' | 'history')[]; evidence_id?: string; lead_id?: string; search_id?: string; note?: string
  view?: BlockView
}
export type ReportMeta = {
  id: string; case_id: string; template: string; template_title: string; title: string; created_by: string; created_by_name: string | null; created_at: string
  updated_by: string; updated_by_name: string | null; updated_at: string; version: number; blocks?: number; exports?: { count: number; last: string } | null
}
export type ReportTemplate = { id: string; title: string; basis: string; description: string }
export type ReportSources = {
  records: { id: string; type: string; title: string; sensitivity: number }[]
  exhibits: { id: string; filename: string; description: string | null; source_type: string | null; uploaded_at: string }[]
  leads: { id: string; title: string; severity: string }[]
  areas: { id: string; label: string; radius_km: number; start_ts: string; end_ts: string; counts: Record<string, number>; searched_at: string }[]
}

const stripView = (blocks: ReportBlock[]) => blocks.map((b) => {
  const copy = { ...b }
  delete copy.view
  return copy
})

export const reports = {
  list: (caseId: string) => call<{ reports: ReportMeta[]; templates: ReportTemplate[] }>(`/api/cases/${encodeURIComponent(caseId)}/reports`),
  create: (caseId: string, template: string, title?: string) =>
    call<ReportMeta>(`/api/cases/${encodeURIComponent(caseId)}/reports`, { method: 'POST', body: JSON.stringify({ template, title }) }),
  get: (id: string) => call<{ report: ReportMeta; blocks: ReportBlock[]; marking: number; marking_label: string; template: ReportTemplate | null }>(`/api/reports/${encodeURIComponent(id)}`),
  save: (id: string, body: { title: string; blocks: ReportBlock[]; version: number }) =>
    call<ReportMeta>(`/api/reports/${encodeURIComponent(id)}`, { method: 'PUT', body: JSON.stringify({ ...body, blocks: stripView(body.blocks) }) }),
  discard: (id: string) => call<{ deleted: boolean }>(`/api/reports/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  sources: (caseId: string) => call<ReportSources>(`/api/cases/${encodeURIComponent(caseId)}/report-sources`),
  export: (id: string, body: { recipient?: string; recipient_clearance?: number }) =>
    raw(`/api/reports/${encodeURIComponent(id)}/export`, { method: 'POST', body: JSON.stringify(body), headers: { 'Content-Type': 'application/json' } }),
}

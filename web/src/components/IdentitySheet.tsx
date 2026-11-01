import { Icon, type IconName } from '@blueprintjs/core'
import type { Dossier } from '../api'
import { day, inr, rupees, sentence } from '../lib/format'
import { Button } from './Button'

// The person at a glance: who they are on paper (facts), what stands out (highlights), and the identity
// documents on record with where each came from and whether it reads as a valid number.

const YEAR = 2026
const ageOf = (p: Record<string, unknown>) => {
  if (p.dob) {
    const [y, m, d] = String(p.dob).split('-').map(Number)
    const now = new Date()
    return now.getFullYear() - y - (now.getMonth() + 1 < m || (now.getMonth() + 1 === m && now.getDate() < d) ? 1 : 0)
  }
  return p.birth_year ? YEAR - Number(p.birth_year) : p.age ? Number(p.age) : null
}

export function personFacts(o: Dossier['object']): [string, string][] {
  const p = o.props as Record<string, unknown>
  const age = ageOf(p)
  const rows: [string, string | null | undefined][] = [
    ['Date of birth', p.dob ? `${day(String(p.dob))}${age != null ? ` · ${age} years` : ''}` : p.birth_year ? `${p.birth_year}${age != null ? ` · about ${age} years` : ''}` : null],
    ['Gender', p.gender === 'M' ? 'Male' : p.gender === 'F' ? 'Female' : (p.gender as string)],
    ['Father', p.father_name as string],
    ['Nationality', p.nationality as string],
    ['Occupation', p.occupation as string],
    ['Declared income', p.declared_income != null ? `${inr(Number(p.declared_income))} a year` : null],
    ['Address', p.address as string],
    ['District', o.district_name ?? (p.city as string)],
    ['Also known as', Array.isArray(p.aliases) ? (p.aliases as string[]).join(', ') : (p.aliases as string)],
  ]
  return rows.filter((r): r is [string, string] => !!r[1])
}

// recorded property names, in the words an officer uses
const LABELS: Record<string, string> = {
  account_no: 'Account number', ifsc: 'IFSC', kyc: 'KYC', holder_name: 'Holder', opened_on: 'Opened', account_type: 'Account type',
  reg_no: 'Registration', chassis_no: 'Chassis number', engine_no: 'Engine number', make: 'Make', model: 'Model', colour: 'Colour',
  cin: 'CIN', gstin: 'GSTIN', incorporated_on: 'Incorporated', registered_office: 'Registered office', imei: 'IMEI', msisdn: 'Number',
  fir_no: 'Case number', max_punishment_years: 'Maximum sentence (years)', chargesheeted_on: 'Charge-sheeted',
}
// record kinds as agencies name them
const KIND_NAMES: Record<string, string> = {
  fir: 'FIR', complaint: 'Complaint', ecir: 'ECIR (ED)', cbi_rc: 'CBI regular case (RC)', nia_case: 'NIA case', seizure: 'Seizure report',
  str: 'Suspicious transaction report', ib_assessment: 'IB assessment', lookout_circular: 'Look-out circular', cri_mac_alert: 'CRI-MAC alert',
}
const HIDDEN = new Set(['name', 'name_native', 'title', 'lat', 'lon', 'district_lgd', 'aadhaar', 'pan', 'passport_no', 'dl_no', 'voter_id', 'email', 'cin', 'gstin'])
/** For records that are not people: their recorded properties, in plain words. */
export function recordFacts(o: Dossier['object']): [string, string][] {
  return Object.entries(o.props as Record<string, unknown>)
    .filter(([k, v]) => !k.startsWith('_') && !HIDDEN.has(k) && v != null && v !== '' && typeof v !== 'object')
    .slice(0, 9)
    .map(([k, v]) => [LABELS[k] ?? sentence(k),
      typeof v === 'number' && /amount|income|balance|value|estimate/.test(k) ? inr(v)
        : typeof v === 'string' && /^\d{4}-\d{2}-\d{2}/.test(v) ? day(v)
          : k === 'kind' && typeof v === 'string' && KIND_NAMES[v] ? KIND_NAMES[v]
            : typeof v === 'string' && /^[a-z_]+$/.test(v) ? sentence(v) : typeof v === 'string' ? rupees(v) : String(v)])
}

type Tone = 'danger' | 'warn' | 'proposal' | 'neutral' | 'ok'
export function highlights(d: Dossier): { tone: Tone; icon: IconName; text: string; title?: string }[] {
  const out: { tone: Tone; icon: IconName; text: string; title?: string }[] = []
  const p = d.object.props as Record<string, unknown>
  const accused = d.criminal?.records.filter((r) => r.role === 'accused') ?? []
  if (accused.length) out.push({ tone: 'danger', icon: 'take-action', text: `Accused in ${accused.length} case record${accused.length > 1 ? 's' : ''}`, title: accused.map((r) => r.title).join(', ') })
  const sheet = d.criminal?.history_sheet || (p.history_sheet_no as string | undefined)
  if (sheet) out.push({ tone: 'danger', icon: 'document', text: `History sheet ${sheet}` })
  if (p.watchlist) out.push({ tone: 'danger', icon: 'eye-open', text: String(p.watchlist) })
  if (d.lead) out.push({ tone: 'proposal', icon: 'search-around', text: `${d.lead.role} · rank ${d.lead.rank} of ${d.lead.of} in this case`, title: 'Inferred from the evidence in the case network; a lead, not a finding' })
  if (d.alerts.length) out.push({ tone: 'warn', icon: 'flag', text: `${d.alerts.length} typology alert${d.alerts.length > 1 ? 's' : ''}` })
  if (d.flags?.length) out.push({ tone: 'warn', icon: 'warning-sign', text: `${d.flags.length} conduct flag${d.flags.length > 1 ? 's' : ''}` })
  if (d.deconfliction?.other_track_leads) out.push({ tone: 'neutral', icon: 'git-merge', text: `In ${d.deconfliction.other_track_leads} lead${d.deconfliction.other_track_leads > 1 ? 's' : ''} on other tracks` })
  const guns = (d.firearms ?? []).filter((g) => g.props.status === 'licensed')
  if (guns.length) out.push({ tone: 'warn', icon: 'shield', text: `Holds ${guns.length === 1 ? 'a licensed firearm' : `${guns.length} licensed firearms`}`,
    title: guns.map((g) => `${String(g.props.calibre ?? '')} ${String(g.props.kind ?? '')} · licence ${String(g.props.licence_no ?? '')}`).join('; ') })
  const firms = d.organisations.filter((o) => o.relations.some((r) => r.startsWith('director_of') || r.startsWith('controls')))
  if (firms.length) out.push({ tone: 'neutral', icon: 'office', text: `Runs ${firms.length} business${firms.length > 1 ? 'es' : ''}`, title: firms.map((f) => f.title).join(', ') })
  if (d.travel.some((t) => t.to_country && t.to_country !== 'IN' && t.to_country !== 'India')) out.push({ tone: 'neutral', icon: 'airplane', text: 'Travelled abroad' })
  if (d.fused_records.length) out.push({ tone: 'neutral', icon: 'merge-columns', text: `Resolved from ${d.fused_records.length + 1} records in ${d.sources.length} sources` })
  if (d.withheld_sections?.length) out.push({ tone: 'neutral', icon: 'lock', text: 'Some sections withheld by policy', title: d.withheld_sections.join(', ') })
  return out
}

type Doc = { key: string; label: string; value: string; masked: boolean; source: string; icon: IconName; issuer: string; checks: { ok: boolean; text: string }[]; foot?: string }

const META: Record<string, { icon: IconName; issuer: string; pattern?: RegExp; format?: (v: string) => string }> = {
  aadhaar: { icon: 'id-number', issuer: 'UIDAI', format: (v) => v.replaceAll('-', ' ') },
  pan: { icon: 'credit-card', issuer: 'Income Tax Department', pattern: /^[A-Z]{5}\d{4}[A-Z]$/ },
  passport_no: { icon: 'airplane', issuer: 'Passport Seva, MEA', pattern: /^[A-Z]\d{7}$/ },
  dl_no: { icon: 'drive-time', issuer: 'Transport department', pattern: /^[A-Z]{2}[- ]?\d{2}/ },
  voter_id: { icon: 'endorsed', issuer: 'Election Commission', pattern: /^[A-Z]{3}\d{7}$/ },
  email: { icon: 'envelope', issuer: 'Telecom / service provider' },
  cin: { icon: 'office', issuer: 'Ministry of Corporate Affairs', pattern: /^[LU]\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6}$/ },
  gstin: { icon: 'shop', issuer: 'GST Network', pattern: /^\d{2}[A-Z]{5}\d{4}[A-Z]\d[A-Z\d]{2}$/ },
}
const PAN_HOLDER: Record<string, string> = { P: 'individual', C: 'company', H: 'Hindu undivided family', F: 'firm', T: 'trust', A: 'association of persons', B: 'body of individuals', G: 'government', L: 'local authority', J: 'artificial juridical person' }

export function identityDocs(d: Dossier): Doc[] {
  const name = String(d.object.props.name ?? d.object.title)
  const surname = name.trim().split(/\s+/).at(-1) ?? ''
  const docs: Doc[] = d.documents.map((x) => {
    const m = META[x.key] ?? { icon: 'document' as IconName, issuer: '' }
    const checks: { ok: boolean; text: string }[] = []
    if (!x.masked && m.pattern) checks.push(m.pattern.test(x.value) ? { ok: true, text: 'Valid format' } : { ok: false, text: 'Unusual format' })
    if (x.key === 'pan' && !x.masked && /^[A-Z]{5}/.test(x.value)) {
      const holder = PAN_HOLDER[x.value[3]]
      if (holder) checks.push({ ok: true, text: `Holder: ${holder}` })
      if (x.value[3] === 'P' && surname) checks.push(x.value[4] === surname[0].toUpperCase() ? { ok: true, text: 'Surname initial matches' } : { ok: false, text: `Surname initial is ${x.value[4]}, not ${surname[0].toUpperCase()}` })
    }
    return { ...x, icon: m.icon, issuer: m.issuer, value: m.format ? m.format(x.value) : x.value, checks }
  })
  for (const ph of d.phones) {
    const p = ph.props as Record<string, unknown>
    const own = !p.subscriber_name || String(p.subscriber_name) === name
    docs.push({ key: ph.id, label: 'Mobile number', value: String(p.number ?? ph.title), masked: false, source: '', icon: 'mobile-phone', issuer: [p.operator, p.circle].filter(Boolean).join(' · '),
      checks: own ? [{ ok: true, text: 'Subscribed in this name' }] : [{ ok: false, text: `Subscribed by ${p.subscriber_name}` }] })
  }
  return docs
}

export function IdentityDocuments({ d, clear, onUnmask, onOpen }: { d: Dossier; clear: Record<string, string>; onUnmask: (key: string) => void; onOpen: (id: string) => void }) {
  const docs = identityDocs(d)
  if (!docs.length) return null
  return (
    <section className="id-docs" aria-labelledby="id-docs-title">
      <h2 id="id-docs-title">Identity documents <span className="count">{docs.length}</span></h2>
      <div className="id-grid">
        {docs.map((x) => {
          const shown = clear[x.key] ?? x.value
          const isPhone = x.key.startsWith('phone:')
          return (
            <article key={x.key} className={`id-card ${x.masked && !clear[x.key] ? 'masked' : ''}`}>
              <header>
                <Icon icon={x.icon} size={14} />
                <span>{x.label}</span>
                {x.source && <span className="chip src" title="Source system">{x.source}</span>}
              </header>
              <div className={`id-value ${shown.length > 18 ? 'long' : ''}`}>{isPhone ? <button className="text-link" onClick={() => onOpen(x.key)}>{shown}</button> : shown}</div>
              <div className="id-issuer">{x.issuer}</div>
              <ul className="id-checks">
                {x.masked && !clear[x.key] && <li className="masked"><Icon icon="eye-off" size={12} />Masked by policy<Button small minimal onClick={() => onUnmask(x.key)} aria-label={`Unmask ${x.label}`}>Unmask</Button></li>}
                {clear[x.key] && <li className="ok"><Icon icon="unlock" size={12} />Unmasked for you; recorded in the audit log</li>}
                {x.checks.map((c) => <li key={c.text} className={c.ok ? 'ok' : 'warn'}><Icon icon={c.ok ? 'tick-circle' : 'warning-sign'} size={12} />{c.text}</li>)}
              </ul>
            </article>
          )
        })}
      </div>
    </section>
  )
}

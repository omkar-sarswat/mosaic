// Indian number formatting: lakh (1e5) and crore (1e7).
export function inr(v: number | null | undefined, compact = true): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '—'
  const a = Math.abs(v)
  if (compact) {
    if (a >= 1e7) return `₹${(v / 1e7).toFixed(a >= 1e9 ? 0 : 2)} Cr`
    if (a >= 1e5) return `₹${(v / 1e5).toFixed(2)} L`
  }
  return '₹' + Math.round(v).toLocaleString('en-IN')
}

export const num = (v: number | null | undefined) => (v === null || v === undefined ? '—' : v.toLocaleString('en-IN'))

// Dates read the same everywhere: "05 Aug 2026", "05 Aug 2026, 12:50" in Indian time. A bare date
// ("2026-08-05") is a calendar day, not an instant, so it is formatted without a time-zone shift.
const IST = 'Asia/Kolkata'
function parse(s: string): { d: Date; dateOnly: boolean } | null {
  const dateOnly = /^\d{4}-\d{2}-\d{2}$/.test(s)
  const d = new Date(dateOnly ? `${s}T00:00:00Z` : s)
  return Number.isNaN(d.getTime()) ? null : { d, dateOnly }
}
export const day = (s?: string | null) => {
  if (!s) return ''
  const p = parse(s)
  if (!p) return s.slice(0, 10)
  return p.d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric', timeZone: p.dateOnly ? 'UTC' : IST })
}
export const when = (s?: string | null) => {
  if (!s) return ''
  const p = parse(s)
  if (!p) return s.replace('T', ' ').slice(0, 16)
  if (p.dateOnly) return day(s)
  const time = p.d.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: false, timeZone: IST })
  return `${day(s)}, ${time}`
}

/** "organised_crime_investigation" -> "Organised crime investigation" */
export const sentence = (s: string) => { const t = s.replaceAll('_', ' ').trim(); return t.charAt(0).toUpperCase() + t.slice(1) }
export const titleCase = (s: string) => s.replaceAll('_', ' ').toLowerCase().replace(/(^|\s)\S/g, (t) => t.toUpperCase())

export const initials = (name: string) =>
  name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0])
    .join('')
    .toUpperCase()

// Evidence rank inside a case is a lead for an officer, not a risk score: it is shown in neutral ink,
// never in alarm colours. (Kept as a function so callers stay simple; every rank gets the same ink.)
export function scoreColour(_score?: number | null): string {
  return 'var(--muted)'
}

/** Amounts written into stored texts ("Rs 1,800,000,000") in the Indian form an officer reads at a glance ("₹180 Cr"). */
export function rupees(text: string | null | undefined): string {
  if (!text) return ''
  return text.replace(/(?:Rs\.?|INR)\s?(\d[\d,]*(?:\.\d+)?)/g, (_, n: string) => inr(Number(n.replaceAll(',', ''))))
}

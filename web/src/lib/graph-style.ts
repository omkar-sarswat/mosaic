import { familyColours, theme as currentTheme } from './palette.ts'
// Visual encoding for the network: what a record IS is shown by colour family + glyph + size,
// never by colour alone. Colours were checked with the data-viz palette validator against the
// graph surface: only three hues stay distinguishable for colour-blind readers when every pair
// is on screen at once, so the remaining families are neutrals that differ in lightness and size.
// Colour never encodes risk, rank or suspicion.

export type Family = 'actor' | 'money' | 'asset' | 'record' | 'comms' | 'other'

export const FAMILY_OF: Record<string, Family> = {
  Person: 'actor', Organisation: 'actor',
  BankAccount: 'money', CryptoWallet: 'money',
  Property: 'asset', Vehicle: 'asset', Location: 'asset',
  Incident: 'record', Firearm: 'record', CourtCase: 'record', Document: 'record', Case: 'record', Event: 'record', Shipment: 'record',
  Phone: 'comms', Device: 'comms', DigitalArtifact: 'comms',
}
export const familyOf = (type: string): Family => FAMILY_OF[type] ?? 'other'

export const FAMILY_LABEL: Record<Family, string> = {
  actor: 'People and organisations', money: 'Money', asset: 'Property, vehicles, places', record: 'Case records', comms: 'Phones and devices', other: 'Other records',
}
// Sector order around a person: money first, then holdings, then records, then devices.
export const FAMILY_ORDER: Family[] = ['money', 'asset', 'record', 'comms', 'other']

// Case Diary palette (lib/palette.ts): ink for people, ink-blue for money, green for holdings, red tape for case
// records, buff for devices, quiet for the rest; families also differ in lightness and glyph, never colour alone.
export const familyColour = (f: Family, t: 'dark' | 'light' = currentTheme()) => familyColours(t)[f]
export const typeColour = (type: string, t: 'dark' | 'light' = currentTheme()) => familyColour(familyOf(type), t)

// Sizes are in graph units (Sigma itemSizesReference = "positions"), so the layout's
// no-overlap guarantee holds at every zoom level.
export const SIZE: Record<Family, number> = { actor: 13, money: 9, asset: 9, record: 9, comms: 7, other: 7 }

// Relationship families, used for edge colour and for the relationship-layer filter.
export type RelFamily = 'money' | 'ownership' | 'comms' | 'records' | 'identity' | 'association'
export const REL_FAMILY: Record<string, RelFamily> = {
  transferred_to: 'money',
  holds_account: 'ownership', signatory_of: 'ownership', owns: 'ownership', director_of: 'ownership', controls: 'ownership',
  registered_at: 'ownership', resides_at: 'ownership', licensed_to: 'ownership', employee_of: 'ownership', beneficiary_of: 'ownership',
  called: 'comms', uses_phone: 'comms', sim_in_device: 'comms', holds_handle: 'comms',
  accused_in: 'records', victim_in: 'records', complainant_in: 'records', witness_in: 'records', mentions: 'records', convicted_in: 'records',
  used_in: 'records', recovered_in: 'records', stolen_in: 'records', part_of: 'records', documented_in: 'records', reported_at: 'records',
  same_as: 'identity',
  inferred_association: 'association', relative_of: 'association', associate_of: 'association',
}
export const relFamily = (type: string): RelFamily => REL_FAMILY[type] ?? 'association'

export function edgeColour(type: string, theme: 'dark' | 'light' = currentTheme()): string {
  const f = relFamily(type)
  const p = familyColours(theme)
  // Relationships must remain legible at overview and in exported figures.
  // Use opaque colours: low alpha erased thin ownership/association links on
  // the light surface. Interaction dimming is handled separately by the renderer.
  if (f === 'money') return p.money
  if (f === 'records') return p.record
  if (f === 'identity') return p.actor
  if (f === 'comms') return p.comms
  if (f === 'association') return theme === 'light' ? '#737D86' : '#A7B3C2'
  return theme === 'light' ? '#62747D' : '#AAB8C2'
}

// Labels on the canvas are short; the full label is in the tooltip, list and inspector.
export function shortLabel(type: string, label: string): string {
  const s = String(label ?? '').trim()
  const tail = (n: number) => s.replace(/\s+/g, '').slice(-n)
  if (type === 'BankAccount') {
    if (/^\d[\d ]{5,}$/.test(s)) return `A/c ··${tail(4)}`
    const m = /^(.*?)\s*·\s*(\d{3,})$/.exec(s)  // "Holder name ·1234" from the case network
    if (m) return `${m[1].length > 16 ? m[1].slice(0, 15) + '…' : m[1]} ··${m[2].slice(-4)}`
    return s.length > 22 ? s.slice(0, 21) + '…' : s
  }
  if (type === 'Phone') return /^\+?\d[\d ]{6,}$/.test(s) ? (s.startsWith('+') && !s.startsWith('+91') ? `${s.slice(0, 4)} ··${tail(4)}` : `··${tail(4)}`) : s
  if (type === 'Device') return /\d{8,}/.test(s) ? `IMEI ··${tail(4)}` : s.length > 20 ? s.slice(0, 19) + '…' : s
  if (type === 'CryptoWallet') return s.length > 14 ? `${s.slice(0, 6)}…${s.slice(-4)}` : s
  return s.length > 26 ? s.slice(0, 25) + '…' : s
}

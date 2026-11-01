// Data colours. Charts, map layers and graph families read them here so every visual speaks
// the same palette as the stylesheet, in both the day (light) and night-duty (dark) themes.
// Meanings are fixed across the product: ink = what is known, buff = the active file and selection,
// red = critical and cross-border, slate = machine proposals, green = approved. No violet, no candy tints.

export type Theme = 'light' | 'dark'

export function theme(): Theme {
  return typeof document !== 'undefined' && document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light'
}

const DAY = {
  ink: '#343B43', inkSoft: '#46758B', buff: '#A27726', tape: '#A8392C', stamp: '#58657A', approve: '#4E6E59', caution: '#956019',
  slate: '#747C89', quiet: '#A6ABB2', text: '#242529', muted: '#686B70', surface: '#F8F8F5', dim: '#DDDEDA',
}
const NIGHT = {
  ink: '#D7DDE6', inkSoft: '#8BBBD4', buff: '#DFBD78', tape: '#E98A7C', stamp: '#A7B3C2', approve: '#8CC3A2', caution: '#DFBD78',
  slate: '#A1ADBD', quiet: '#6E7B8B', text: '#E9EAEC', muted: '#ACB2BB', surface: '#1B1E22', dim: '#383E45',
}

export function colours(t: Theme = theme()) {
  return t === 'dark' ? NIGHT : DAY
}

/** Money: domestic flows in ink, cross-border in red tape, cash in slate, crypto in stamp violet. */
export function moneyColours(t: Theme = theme()) {
  const c = colours(t)
  return { account: c.inkSoft, party: c.inkSoft, domestic: c.inkSoft, foreign: c.tape, cash: c.slate, crypto: c.stamp, retail: c.quiet, in: c.inkSoft, out: c.buff, flagged: c.tape }
}

/** Evidence on a link: corroborated (ink, solid), single source (caution, dashed), machine-proposed (stamp violet, dotted). */
export function evidenceColours(t: Theme = theme()) {
  const c = colours(t)
  return { corroborated: c.ink, single: c.caution, suggested: c.stamp }
}

/** Entity families in graphs. Six slots, distinguishable in both themes and for common colour-vision deficiencies
 * by lightness as well as hue (actor darkest, other lightest). */
export function familyColours(t: Theme = theme()) {
  const c = colours(t)
  return { actor: c.ink, money: c.inkSoft, asset: c.approve, record: c.tape, comms: c.buff, other: c.quiet }
}

/** Entity types (type dots, map markers), grouped onto the family colours so the product shows six, not fifteen. */
export function typeColour(type: string, t: Theme = theme()): string {
  const f = familyColours(t)
  const map: Record<string, string> = {
    Person: f.actor, Organisation: f.actor,
    BankAccount: f.money, Transaction: f.money, CryptoWallet: f.money, Scheme: f.money,
    Vehicle: f.asset, Property: f.asset, Asset: f.asset, Firearm: f.asset,
    Incident: f.record, Document: f.record, Tender: f.record, Hazard: f.record,
    Phone: f.comms, Device: f.comms,
    Location: f.other, AdminUnit: f.other,
  }
  return map[type] ?? f.other
}

/** Hazard severity on the disaster map: red tape for the worst, then caution, then ink. */
export function severityColours(t: Theme = theme()) {
  const c = colours(t)
  return { Extreme: c.tape, Severe: '#B05A26', Moderate: c.caution, other: c.slate }
}

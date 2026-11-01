import { typeColour } from './graph-style.ts'
// Entity glyphs (24x24, white on the node colour) used in the graph and lists.
const PATHS: Record<string, string> = {
  Person: '<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4.4 3.6-7 8-7s8 2.6 8 7z"/>',
  Organisation: '<path d="M4 21V5l8-3 8 3v16h-6v-5h-4v5z"/><path fill="#141517" d="M8 7h2v2H8zm6 0h2v2h-2zM8 11h2v2H8zm6 0h2v2h-2z"/>',
  BankAccount: '<path d="M12 2 2 7v2h20V7z"/><path d="M4 10h2v8H4zm5 0h2v8H9zm4 0h2v8h-2zm5 0h2v8h-2zM2 19h20v3H2z"/>',
  Phone: '<path d="M7 2h10a2 2 0 0 1 2 2v16a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z"/><circle cx="12" cy="18.5" r="1.3" fill="#141517"/>',
  Device: '<rect x="5" y="2" width="14" height="20" rx="2"/><rect x="7" y="4" width="10" height="13" fill="#141517"/>',
  Vehicle: '<path d="M5 11 7 5h10l2 6h1a2 2 0 0 1 2 2v4h-2a2 2 0 0 1-4 0H8a2 2 0 0 1-4 0H2v-4a2 2 0 0 1 2-2z"/>',
  Property: '<path d="M12 3 2 11h3v10h5v-6h4v6h5V11h3z"/>',
  Incident: '<path d="M6 2h9l5 5v15H6z"/><path fill="#141517" d="M9 11h8v1.6H9zm0 4h8v1.6H9z"/>',
  CryptoWallet: '<circle cx="12" cy="12" r="10"/><text x="12" y="16.5" font-size="12" text-anchor="middle" fill="#141517" font-family="Arial" font-weight="bold">₿</text>',
  Location: '<path d="M12 2a7 7 0 0 0-7 7c0 5 7 13 7 13s7-8 7-13a7 7 0 0 0-7-7z"/><circle cx="12" cy="9" r="2.6" fill="#141517"/>',
  Case: '<path d="M3 6h7l2 2h9v12H3z"/>',
  AdminUnit: '<path d="M3 4l6-2 6 2 6-2v18l-6 2-6-2-6 2z"/>',
  Scheme: '<rect x="4" y="4" width="16" height="16" rx="3"/>',
  Asset: '<path d="M12 2l9 5v10l-9 5-9-5V7z"/>',
  Firearm: '<path d="M3 8h16l2 2v3h-7l-1 2h-2l-1 4H6l1.6-6H4z"/>',
  Tender: '<path d="M6 3h12v18H6z"/><path fill="#141517" d="M9 7h6v1.6H9zm0 4h6v1.6H9zm0 4h4v1.6H9z"/>',
  Document: '<path d="M6 2h9l5 5v15H6z"/><path fill="#141517" d="M9 11h8v1.6H9zm0 4h8v1.6H9z"/>',
  CourtCase: '<path d="M12 3 3 8h18zM5 10h2v7H5zm6 0h2v7h-2zm6 0h2v7h-2zM3 19h18v2H3z"/>',
  DigitalArtifact: '<rect x="3" y="4" width="18" height="13" rx="1.5"/><path d="M8 20h8v1.6H8z"/>',
  Hazard: '<path d="M12 2 1 21h22z"/><path fill="#141517" d="M11 9h2v6h-2zm0 7.5h2v2h-2z"/>',
}

// Colour by record family (validated palette, see graph-style.ts); the glyph tells types apart within a family.
// A live view: each read takes the current theme, so a theme switch recolours lists and dots on the next render.
export const TYPE_COLOURS: Record<string, string> = new Proxy({} as Record<string, string>, { get: (_, type) => typeColour(String(type)) })

const cache = new Map<string, string>()
export function iconUri(type: string, fill = '#ffffff'): string {
  const key = type + fill
  if (!cache.has(key)) {
    const body = PATHS[type] ?? '<circle cx="12" cy="12" r="8"/>'
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 24 24" fill="${fill}">${body}</svg>`
    cache.set(key, 'data:image/svg+xml;utf8,' + encodeURIComponent(svg))
  }
  return cache.get(key)!
}

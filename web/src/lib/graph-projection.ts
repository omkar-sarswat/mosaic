// The presentation graph: what is drawn, built from the data graph each time the view changes.
//
// At overview, the individual records between two people's "orbits" (their accounts, phones, property)
// are replaced by one aggregated link per pair and kind: "14 transfers · ₹3.20 Cr" between two people
// instead of fourteen lines crossing the canvas. The member records stay in the presentation graph,
// hidden, and are revealed when either orbit is selected (drill-down). The data graph is never changed:
// analysis, paths and evidence always use the real records.

import { MultiDirectedGraph } from 'graphology'
import { edgeColour, familyOf, relFamily, type RelFamily } from './graph-style.ts'

/** Orbit of each visible record: a person or organisation is its own orbit; a record linked to exactly
 *  one visible person or organisation belongs to that orbit; anything else is its own orbit. */
export function orbits(graph: MultiDirectedGraph, visible: Set<string>): Map<string, string> {
  const isActor = (id: string) => familyOf(String(graph.getNodeAttribute(id, 'entityType'))) === 'actor'
  const out = new Map<string, string>()
  for (const id of visible) {
    if (!graph.hasNode(id)) continue
    if (isActor(id)) { out.set(id, id); continue }
    const owners = new Set<string>()
    graph.forEachNeighbor(id, (n) => { if (visible.has(n) && isActor(n)) owners.add(n) })
    out.set(id, owners.size === 1 ? [...owners][0] : id)
  }
  return out
}

const NOUN: Record<RelFamily, [string, string]> = {
  money: ['transfer', 'transfers'], comms: ['call link', 'call links'], records: ['case link', 'case links'],
  ownership: ['holding', 'holdings'], identity: ['identity link', 'identity links'], association: ['association', 'associations'],
}
function inrShort(v: number): string {
  if (v >= 1e7) return `₹${(v / 1e7).toFixed(2)} Cr`
  if (v >= 1e5) return `₹${(v / 1e5).toFixed(1)} L`
  return `₹${Math.round(v).toLocaleString('en-IN')}`
}

export type ViewStats = { nodes: number; edges: number; aggregated: number; members: number }

export function buildView(view: MultiDirectedGraph, graph: MultiDirectedGraph, visible: Set<string>,
  options: { aggregate: boolean; straight: boolean; theme: 'dark' | 'light'; orbit?: Map<string, string> }): ViewStats {
  view.clear()
  for (const id of visible) if (graph.hasNode(id)) view.addNode(id, { ...graph.getNodeAttributes(id) })
  const orbit = options.orbit ?? orbits(graph, visible)
  // one combined link per pair of orbits, whatever the kinds of record behind it
  type Meta = { source: string; target: string; members: string[]; amount: number; byFam: Map<RelFamily, number>; flow: number }
  const meta = new Map<string, Meta>()
  let members = 0
  graph.forEachEdge((id, attrs, s, t) => {
    if (!view.hasNode(s) || !view.hasNode(t)) return
    const os = orbit.get(s) ?? s, ot = orbit.get(t) ?? t
    const crossing = options.aggregate && os !== ot && !(os === s && ot === t)
    view.addDirectedEdgeWithKey(id, s, t, { ...attrs, crossOrbit: crossing, orbitA: os, orbitB: ot, type: options.straight ? 'arrow' : 'curved' })
    if (!crossing) return
    members++
    const fam = relFamily(attrs.relationType)
    const [a, b] = os < ot ? [os, ot] : [ot, os]
    const key = `meta:${a}>${b}`
    const m: Meta = meta.get(key) ?? { source: a, target: b, members: [], amount: 0, byFam: new Map(), flow: 0 }
    m.members.push(id)
    const n = fam === 'money' || fam === 'comms' ? Number(attrs.count) || 1 : 1
    m.byFam.set(fam, (m.byFam.get(fam) ?? 0) + n)
    if (fam === 'money') {
      const amt = Number(attrs.amount) || 0
      m.amount += amt
      m.flow += os === a ? amt || 1 : -(amt || 1)  // net direction of money between the two orbits
    }
    meta.set(key, m)
  })
  const ORDER: RelFamily[] = ['money', 'comms', 'records', 'ownership', 'identity', 'association']
  for (const [key, m] of meta) {
    const parts = ORDER.filter((f) => m.byFam.has(f)).map((f) => {
      const n = m.byFam.get(f)!
      const [one, many] = NOUN[f]
      return `${n} ${n === 1 ? one : many}${f === 'money' && m.amount ? ` · ${inrShort(m.amount)}` : ''}`
    })
    const money = m.byFam.has('money')
    const [source, target] = money && m.flow < 0 ? [m.target, m.source] : [m.source, m.target]
    const lead: RelFamily = money ? 'money' : ORDER.find((f) => m.byFam.has(f))!
    const size = money && m.amount ? Math.min(4, 0.9 + 0.9 * Math.log10(m.amount / 1e5 + 1)) : Math.min(1.8, 0.45 + 0.3 * Math.log2(m.members.length + 1))
    view.addDirectedEdgeWithKey(key, source, target, {
      meta: true, relationType: 'meta', relFamily: lead, families: [...m.byFam.keys()], members: m.members, amount: m.amount || null,
      count: m.members.length, label: parts.join(' · '),
      color: edgeColour(lead === 'money' ? 'transferred_to' : lead === 'records' ? 'accused_in' : lead === 'comms' ? 'called' : 'owns', options.theme),
      size, type: money ? 'curved' : 'curved', curvature: 0.05, orbitA: m.source, orbitB: m.target,
    })
  }
  return { nodes: view.order, edges: view.size, aggregated: meta.size, members }
}

/** People and organisations whose links go to (nearly) the same other orbits are structurally
 *  equivalent (Lorrain & White 1971): drawing them one by one only repeats the same lines. Groups of
 *  three or more with an IDF-free Jaccard similarity of their counterpart sets >= `threshold` are
 *  returned so the view can draw each group as one node. Seeds, selected and pinned records never group. */
export function equivalentGroups(view: MultiDirectedGraph, orbit: Map<string, string>, keep: Set<string>, threshold = 0.6, minSize = 3): string[][] {
  const isActor = (id: string) => familyOf(String(view.getNodeAttribute(id, 'entityType'))) === 'actor'
  const sig = new Map<string, Set<string>>()
  view.forEachEdge((_e, a, s, t) => {
    if (a.relationType === 'inferred_association') return
    const os = orbit.get(s) ?? s, ot = orbit.get(t) ?? t
    if (os === ot) return
    for (const [x, y] of [[os, ot], [ot, os]]) {
      if (!view.hasNode(x) || !isActor(x)) continue
      if (!sig.has(x)) sig.set(x, new Set())
      sig.get(x)!.add(y)
    }
  })
  const actors = [...sig.keys()].filter((a) => !keep.has(a) && !view.getNodeAttribute(a, 'seed')).sort()
  const parent = new Map(actors.map((a) => [a, a]))
  const find = (x: string): string => { while (parent.get(x) !== x) { parent.set(x, parent.get(parent.get(x)!)!); x = parent.get(x)! } return x }
  for (let i = 0; i < actors.length; i++) for (let j = i + 1; j < actors.length; j++) {
    const A = sig.get(actors[i])!, B = sig.get(actors[j])!
    if (A.has(actors[j]) || B.has(actors[i])) continue  // directly linked people stay visible as a pair
    let inter = 0
    for (const x of A) if (B.has(x)) inter++
    if (inter / (A.size + B.size - inter) >= threshold) parent.set(find(actors[i]), find(actors[j]))
  }
  const groups = new Map<string, string[]>()
  for (const a of actors) { const r = find(a); groups.set(r, [...(groups.get(r) ?? []), a]) }
  return [...groups.values()].filter((g) => g.length >= minSize).map((g) => g.sort())
}

/** Replace each group by one node at its members' centroid; the members' own records fold into it and
 *  every link of a member is redrawn once per counterpart orbit, from the group. */
export function collapseGroups(view: MultiDirectedGraph, orbit: Map<string, string>, groups: string[][], theme: 'dark' | 'light'): Map<string, string[]> {
  const index = new Map<string, string[]>()
  for (const members of groups) {
    const id = `group:${members[0]}+${members.length}`
    const inGroup = new Set(members)
    const folded = view.filterNodes((n) => inGroup.has(orbit.get(n) ?? n))
    const pts = members.map((m) => view.getNodeAttributes(m))
    let x = pts.reduce((s, p) => s + p.x, 0) / pts.length, y = pts.reduce((s, p) => s + p.y, 0) / pts.length
    const base = view.getNodeAttributes(members[0])
    // members orbiting one record have their centre on that record: stack the group there and the picture
    // collapses to a point (and the camera zooms without limit), so take the first member's place instead
    const clash = view.someNode((n, a) => !inGroup.has(orbit.get(n) ?? n) && Math.hypot(a.x - x, a.y - y) < (Number(base.size) || 8) * 2.5)
    if (clash) ({ x, y } = pts[0] as { x: number; y: number })
    const holdings = folded.length - members.length
    view.addNode(id, { ...base, x, y, size: base.size * 1.35, group: true, members, folded,
      label: `${members.length} with the same links`, fullLabel: `${members.length} people / organisations with the same links${holdings ? ` (${holdings} records folded in)` : ''}`, seed: false })
    const links = new Map<string, { other: string; out: boolean; members: string[]; amount: number; fam: Set<string> }>()
    for (const n of folded) view.forEachEdge(n, (e, a, s, t) => {
      if (a.crossOrbit) return  // represented by the combined link that carries it
      const other = s === n ? t : s
      if (folded.includes(other)) return
      const ids = a.meta ? (a.members as string[]) : [e]
      const key = `${other}|${s === n}`
      const l = links.get(key) ?? { other, out: s === n, members: [], amount: 0, fam: new Set<string>() }
      l.members.push(...ids)
      l.amount += Number(a.amount) || 0
      l.fam.add(String(a.relFamily ?? relFamily(a.relationType)))
      links.set(key, l)
    })
    for (const n of folded) view.dropNode(n)
    for (const [key, l] of links) {
      if (!view.hasNode(l.other)) continue
      const money = l.fam.has('money')
      view.addDirectedEdgeWithKey(`meta:${id}:${key}`, l.out ? id : l.other, l.out ? l.other : id, {
        meta: true, relationType: 'meta', relFamily: money ? 'money' : [...l.fam][0], families: [...l.fam], members: [...new Set(l.members)],
        amount: l.amount || null, count: l.members.length, label: `${l.members.length} record(s)${money && l.amount ? ` · ${inrShort(l.amount)}` : ''}`,
        color: edgeColour(money ? 'transferred_to' : 'owns', theme), size: money ? Math.min(4, 0.9 + 0.9 * Math.log10(l.amount / 1e5 + 1)) : 0.8,
        type: 'curved', curvature: 0.05, orbitA: id, orbitB: l.other,
      })
    }
    index.set(id, members)
  }
  return index
}

/** Money between parties: every visible account is replaced by its holder (person or organisation) where
 *  one is on record, and transfers are summed per ordered pair of parties. Accounts with no visible holder
 *  stay as accounts. Transfers between a holder's own accounts are dropped (they are not money moving
 *  between parties). Returns a graph ready for moneyLayout, with each link's member transfers kept. */
export function moneyParties(graph: MultiDirectedGraph, accounts: Set<string>): MultiDirectedGraph {
  const party = new Map<string, string>()
  for (const a of accounts) {
    if (!graph.hasNode(a)) continue
    // the account holder is the party; a signatory (e.g. a CA operating a company's account) is not
    const via = (rel: string) => [...new Set(graph.inEdges(a).filter((e) => graph.getEdgeAttribute(e, 'relationType') === rel).map((e) => graph.source(e))
      .filter((n) => familyOf(String(graph.getNodeAttribute(n, 'entityType'))) === 'actor'))]
    const holders = via('holds_account')
    const signers = via('signatory_of')
    party.set(a, holders.length === 1 ? holders[0] : !holders.length && signers.length === 1 ? signers[0] : a)
  }
  const out = new MultiDirectedGraph()
  const held = new Map<string, number>()
  for (const [a, p] of party) {
    held.set(p, (held.get(p) ?? 0) + (p !== a ? 1 : 0))
    if (!out.hasNode(p)) out.addNode(p, { ...graph.getNodeAttributes(p) })
  }
  for (const [p, n] of held) if (n) out.mergeNodeAttributes(p, { accounts: n })
  for (const [a, p] of party) out.mergeNodeAttributes(p, { accountIds: [...((out.getNodeAttribute(p, 'accountIds') as string[] | undefined) ?? []), a] })
  const sums = new Map<string, { s: string; t: string; amount: number; count: number; members: string[] }>()
  graph.forEachEdge((id, attrs, s, t) => {
    if (attrs.relationType !== 'transferred_to' || !party.has(s) || !party.has(t)) return
    const ps = party.get(s)!, pt = party.get(t)!
    if (ps === pt) return
    const key = `${ps}>${pt}`
    const m = sums.get(key) ?? { s: ps, t: pt, amount: 0, count: 0, members: [] }
    m.amount += Number(attrs.amount) || 0
    m.count += Number(attrs.count) || 1
    m.members.push(id)
    sums.set(key, m)
  })
  for (const [key, m] of sums) {
    out.addDirectedEdgeWithKey(`money:${key}`, m.s, m.t, {
      relationType: 'transferred_to', meta: true, relFamily: 'money', families: ['money'], members: m.members, amount: m.amount || null, count: m.count,
      label: `${m.count} transfer${m.count === 1 ? '' : 's'}${m.amount ? ` · ${inrShort(m.amount)}` : ''}`,
      color: edgeColour('transferred_to'), size: m.amount ? Math.min(5, 0.8 + 1.1 * Math.log10(m.amount / 1e5 + 1)) : 0.8, type: 'arrow',
    })
  }
  return out
}

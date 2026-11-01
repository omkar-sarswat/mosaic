// Readable, deterministic layouts for investigation networks. All coordinates are in graph units, the
// same units as node sizes (Sigma itemSizesReference = "positions"), so the final overlap-removal pass
// guarantees separated nodes at every zoom level.
//
//  structureLayout  People and organisations are laid out by their relationships (ForceAtlas2 on the
//                   actor graph only). Each actor's own records orbit it in rings, grouped into angular
//                   sectors by family (money, property, records, devices) and turned toward free space.
//                   Records shared by several actors sit between them. Records owned by no visible actor
//                   orbit the record they are linked to. A final Noverlap pass removes any overlap.
//  moneyLayout      Accounts in layers from left to right along the direction money moved (Sugiyama:
//                   Eades-Lin-Smyth greedy cycle breaking, longest-path layering, barycentre crossing
//                   reduction), so a laundering chain reads as a chain.
//  forceLayout      ForceAtlas2 on everything visible (LinLog), then Noverlap.
//
// Layouts never change data, never read scores, and are seeded from sorted ids, so the same records
// always produce the same picture.

import type { MultiDirectedGraph } from 'graphology'
import { UndirectedGraph } from 'graphology'
import forceAtlas2 from 'graphology-layout-forceatlas2'
import noverlap from 'graphology-layout-noverlap'
import { FAMILY_ORDER, familyOf, relFamily, SIZE } from './graph-style.ts'

export type Pos = { x: number; y: number }
const ACTORS = new Set(['Person', 'Organisation'])
const GOLDEN = 2.399963229728653

function unitHash(s: string): number {
  let h = 2166136261
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i)
    h = Math.imul(h, 16777619)
  }
  return (h >>> 0) / 4294967295
}
const sizeOf = (graph: MultiDirectedGraph, id: string) => SIZE[familyOf(String(graph.getNodeAttribute(id, 'entityType')))]

function resolveOverlaps(positions: Map<string, Pos>, size: (id: string) => number, margin: number) {
  if (positions.size < 2) return
  const g = new UndirectedGraph()
  for (const [id, p] of positions) g.addNode(id, { x: p.x, y: p.y, size: size(id) })
  noverlap.assign(g, { maxIterations: 400, settings: { margin, ratio: 1, expansion: 1.05, gridSize: 24, speed: 3 } })
  g.forEachNode((id, a) => positions.set(id, { x: a.x, y: a.y }))
}

function spiralSeed(ids: string[], scale: number) {
  return new Map(ids.map((id, i) => [id, { x: Math.cos(i * GOLDEN) * scale * Math.sqrt(i + 1), y: Math.sin(i * GOLDEN) * scale * Math.sqrt(i + 1) }]))
}

// ---------------------------------------------------------------------------- structure
export function structureLayout(graph: MultiDirectedGraph, visible: Set<string>, spacing = 1, angles?: Map<string, number>): Map<string, Pos> {
  const ids = [...visible].filter((id) => graph.hasNode(id)).sort()
  const typeOf = (id: string) => String(graph.getNodeAttribute(id, 'entityType'))
  let actors = ids.filter((id) => ACTORS.has(typeOf(id)))
  if (!actors.length) actors = [...ids].sort((a, b) => graph.degree(b) - graph.degree(a) || a.localeCompare(b)).slice(0, Math.max(1, Math.ceil(ids.length / 6)))
  const actorSet = new Set(actors)

  // who each record belongs to (any relationship to a visible actor)
  const owners = new Map<string, string[]>()
  for (const id of ids) {
    if (actorSet.has(id)) continue
    const os = new Set<string>()
    graph.forEachNeighbor(id, (n) => { if (actorSet.has(n)) os.add(n) })
    owners.set(id, [...os].sort())
  }

  // actor graph: direct relations, shared records and money between their accounts
  const H = new UndirectedGraph()
  for (const [id, p] of spiralSeed(actors, 10)) H.addNode(id, { ...p, size: 1 })
  const bump = (a: string, b: string, w: number) => {
    if (a === b) return
    if (H.hasEdge(a, b)) H.updateEdgeAttribute(a, b, 'weight', (x: number) => x + w)
    else H.addEdge(a, b, { weight: w })
  }
  graph.forEachEdge((_e, attrs, s, t) => {
    if (!visible.has(s) || !visible.has(t)) return
    if (actorSet.has(s) && actorSet.has(t)) bump(s, t, relFamily(attrs.relationType) === 'association' ? 1 : 2)
    if (attrs.relationType === 'transferred_to') {
      const os = actorSet.has(s) ? [s] : owners.get(s) ?? []
      const ot = actorSet.has(t) ? [t] : owners.get(t) ?? []
      for (const a of os) for (const b of ot) bump(a, b, 1 + Math.log10(1 + (Number(attrs.amount) || 0) / 1e5))
    }
  })
  for (const os of owners.values()) for (let i = 0; i < Math.min(os.length, 8); i++) for (let j = i + 1; j < Math.min(os.length, 8); j++) bump(os[i], os[j], 1.5)

  // satellites owned by exactly one actor, in family sectors
  const own = new Map<string, string[]>(actors.map((a) => [a, []]))
  for (const [id, os] of owners) if (os.length === 1) own.get(os[0])!.push(id)
  const famRank = (id: string) => FAMILY_ORDER.indexOf(familyOf(typeOf(id)))
  for (const list of own.values()) list.sort((a, b) => famRank(a) - famRank(b) || String(graph.getNodeAttribute(a, 'label')).localeCompare(String(graph.getNodeAttribute(b, 'label'))) || a.localeCompare(b))
  const step = 34 * spacing
  const ringsOf = (n: number) => {
    const rings: { r: number; n: number }[] = []
    let r = 54 * spacing, left = n
    while (left > 0) {
      const cap = Math.max(6, Math.floor((2 * Math.PI * r) / step))
      rings.push({ r, n: Math.min(cap, left) })
      left -= cap
      r += 40 * spacing
    }
    return rings
  }
  const reach = new Map(actors.map((a) => {
    const rings = ringsOf(own.get(a)!.length)
    return [a, (rings.length ? rings[rings.length - 1].r : 0) + SIZE.actor + 10 * spacing]
  }))

  // lay out actors, then spread them so their orbits do not touch
  if (H.order > 1) {
    // plain ForceAtlas2 with strong gravity keeps separate networks visibly apart (LinLog was tried: it tangled them)
    const settings = { ...forceAtlas2.inferSettings(H), gravity: 1, strongGravityMode: true, scalingRatio: 6, edgeWeightInfluence: 1, barnesHutOptimize: H.order > 300 }
    forceAtlas2.assign(H, { iterations: H.order > 250 ? 150 : 400, settings, getEdgeWeight: 'weight' })
    let nn = 0
    H.forEachNode((a, p) => {
      let best = Infinity
      H.forEachNode((b, q) => { if (a !== b) best = Math.min(best, Math.hypot(p.x - q.x, p.y - q.y)) })
      nn += best
    })
    nn /= H.order
    const radii = actors.map((a) => reach.get(a)!).sort((x, y) => x - y)
    const target = 2.2 * radii[Math.floor(radii.length / 2)] + 30 * spacing
    const scale = nn > 0 ? target / nn : 1
    H.forEachNode((a, p) => H.mergeNodeAttributes(a, { x: p.x * scale, y: p.y * scale, size: reach.get(a)! }))
    noverlap.assign(H, { maxIterations: 600, settings: { margin: 22 * spacing, ratio: 1, expansion: 1.05, gridSize: 20, speed: 3 } })
  }
  const pos = new Map<string, Pos>()
  H.forEachNode((a, p) => pos.set(a, { x: p.x, y: p.y }))
  if (H.order === 1) pos.set(actors[0], { x: 0, y: 0 })

  // place orbits, turned toward the side away from the actor's related actors
  const cx = actors.reduce((s, a) => s + pos.get(a)!.x, 0) / actors.length
  const cy = actors.reduce((s, a) => s + pos.get(a)!.y, 0) / actors.length
  for (const a of actors) {
    const p = pos.get(a)!
    let vx = 0, vy = 0
    H.forEachNeighbor(a, (b) => { const q = pos.get(b)!; const d = Math.hypot(q.x - p.x, q.y - p.y) || 1; vx += (q.x - p.x) / d; vy += (q.y - p.y) / d })
    if (!vx && !vy) { vx = cx - p.x; vy = cy - p.y }
    const free = vx || vy ? Math.atan2(-vy, -vx) : -Math.PI / 2
    const list = own.get(a)!
    let k = 0
    for (const ring of ringsOf(list.length)) {
      const cap = Math.max(6, Math.floor((2 * Math.PI * ring.r) / step))
      const da = ring.n >= cap ? (2 * Math.PI) / ring.n : step / ring.r
      const start = free - (da * (ring.n - 1)) / 2
      for (let i = 0; i < ring.n; i++, k++) {
        pos.set(list[k], { x: p.x + Math.cos(start + i * da) * ring.r, y: p.y + Math.sin(start + i * da) * ring.r })
        angles?.set(list[k], start + i * da)
      }
    }
  }
  // records shared by several actors sit between them
  for (const [id, os] of owners) {
    if (os.length < 2) continue
    const xs = os.map((o) => pos.get(o)!)
    const mx = xs.reduce((s, q) => s + q.x, 0) / xs.length, my = xs.reduce((s, q) => s + q.y, 0) / xs.length
    const ang = unitHash(id) * 2 * Math.PI
    pos.set(id, { x: mx + Math.cos(ang) * 14 * spacing, y: my + Math.sin(ang) * 14 * spacing })
  }
  // records linked only to other records orbit the record they are linked to
  for (let pass = 0; pass < 4; pass++) {
    let placed = 0
    for (const [id, os] of owners) {
      if (os.length || pos.has(id)) continue
      const anchor = graph.neighbors(id).filter((n) => pos.has(n)).sort()[0]
      if (!anchor) continue
      const q = pos.get(anchor)!
      const ang = unitHash(id) * 2 * Math.PI
      pos.set(id, { x: q.x + Math.cos(ang) * 34 * spacing, y: q.y + Math.sin(ang) * 34 * spacing })
      placed++
    }
    if (!placed) break
  }
  // anything still unplaced goes in a row under the picture, grouped by family
  const rest = ids.filter((id) => !pos.has(id)).sort((a, b) => famRank(a) - famRank(b) || a.localeCompare(b))
  if (rest.length) {
    const ys = [...pos.values()].map((p) => p.y)
    const xs = [...pos.values()].map((p) => p.x)
    const y0 = (ys.length ? Math.min(...ys) : 0) - 90 * spacing
    const x0 = xs.length ? Math.min(...xs) : 0
    rest.forEach((id, i) => pos.set(id, { x: x0 + (i % 20) * 30 * spacing, y: y0 - Math.floor(i / 20) * 34 * spacing }))
  }
  resolveOverlaps(pos, (id) => sizeOf(graph, id), 5 * spacing)
  return pos
}

// ---------------------------------------------------------------------------- money (layered)
/** Eades, Lin & Smyth (1993) greedy heuristic for a small feedback arc set: an order of the nodes in
 *  which few edges point backwards. Backward edges are the ones a cycle-free layering reverses. */
export function greedyOrder(nodes: string[], edges: [string, string][]): string[] {
  const out = new Map(nodes.map((n) => [n, new Set<string>()])), inc = new Map(nodes.map((n) => [n, new Set<string>()]))
  for (const [a, b] of edges) if (a !== b && out.has(a) && out.has(b)) { out.get(a)!.add(b); inc.get(b)!.add(a) }
  const alive = new Set(nodes), s1: string[] = [], s2: string[] = []
  const drop = (n: string) => { alive.delete(n); for (const m of out.get(n)!) inc.get(m)!.delete(n); for (const m of inc.get(n)!) out.get(m)!.delete(n) }
  while (alive.size) {
    let changed = true
    while (changed) {
      changed = false
      for (const n of [...alive].sort()) {
        if (!alive.has(n)) continue
        if (!out.get(n)!.size) { s2.unshift(n); drop(n); changed = true } else if (!inc.get(n)!.size) { s1.push(n); drop(n); changed = true }
      }
    }
    if (!alive.size) break
    const pick = [...alive].sort((a, b) => (out.get(b)!.size - inc.get(b)!.size) - (out.get(a)!.size - inc.get(a)!.size) || a.localeCompare(b))[0]
    s1.push(pick)
    drop(pick)
  }
  return [...s1, ...s2]
}

export function moneyLayout(graph: MultiDirectedGraph, visible: Set<string>, spacing = 1): { positions: Map<string, Pos>; layers: number; reversed: number } {
  const ids = [...visible].filter((id) => graph.hasNode(id)).sort()
  const flows: [string, string][] = []
  graph.forEachEdge((_e, attrs, s, t) => { if (attrs.relationType === 'transferred_to' && visible.has(s) && visible.has(t) && s !== t) flows.push([s, t]) })
  const order = greedyOrder(ids, flows)
  const rank = new Map(order.map((n, i) => [n, i]))
  const dag = new Map(ids.map((n) => [n, new Set<string>()]))
  let reversed = 0
  for (const [a, b] of flows) {
    if (rank.get(a)! < rank.get(b)!) dag.get(a)!.add(b)
    else { dag.get(b)!.add(a); reversed++ }
  }
  // longest-path layering in topological (greedy) order
  const layer = new Map(ids.map((n) => [n, 0]))
  for (const n of order) for (const m of dag.get(n)!) layer.set(m, Math.max(layer.get(m)!, layer.get(n)! + 1))
  // records with no transfer in view go to a final column
  const flowing = new Set(flows.flat())
  const maxLayer = Math.max(0, ...[...layer.entries()].filter(([n]) => flowing.has(n)).map(([, l]) => l))
  for (const n of ids) if (!flowing.has(n)) layer.set(n, maxLayer + 1)
  const byLayer: string[][] = []
  for (const n of order) (byLayer[layer.get(n)!] ??= []).push(n)
  for (let i = 0; i < byLayer.length; i++) byLayer[i] ??= []
  // barycentre crossing reduction: alternate downward and upward sweeps
  const nbrs = (n: string, dir: 'up' | 'down') => {
    const out: string[] = []
    for (const [a, b] of flows) { if (dir === 'up' && b === n) out.push(a); if (dir === 'down' && a === n) out.push(b) }
    return out
  }
  const index = new Map<string, number>()
  const reindex = () => byLayer.forEach((l) => l.forEach((n, i) => index.set(n, i)))
  reindex()
  for (let sweep = 0; sweep < 8; sweep++) {
    const down = sweep % 2 === 0
    const range = down ? [...byLayer.keys()].slice(1) : [...byLayer.keys()].reverse().slice(1)
    for (const li of range) {
      const bary = (n: string) => { const ns = nbrs(n, down ? 'up' : 'down').filter((m) => index.has(m)); return ns.length ? ns.reduce((s, m) => s + index.get(m)!, 0) / ns.length : index.get(n)! }
      byLayer[li].sort((a, b) => bary(a) - bary(b) || a.localeCompare(b))
      reindex()
    }
  }
  // every layer is spread over the same height, so a small layer of collectors is not stacked in the middle
  // where all incoming lines would meet; its records sit at the barycentre-ordered fractions of the height
  const positions = new Map<string, Pos>()
  const gapX = 260 * spacing, gapY = 58 * spacing
  const tallest = Math.max(1, ...byLayer.map((l) => l.length))
  const height = (tallest - 1) * gapY
  byLayer.forEach((l, li) => l.forEach((n, i) => positions.set(n, { x: li * gapX, y: l.length === 1 ? 0 : height / 2 - (i * height) / (l.length - 1) })))
  return { positions, layers: byLayer.filter((l) => l.length).length, reversed }
}

// ---------------------------------------------------------------------------- force
export function forceLayout(graph: MultiDirectedGraph, visible: Set<string>, spacing = 1): Map<string, Pos> {
  const ids = [...visible].filter((id) => graph.hasNode(id)).sort()
  const g = new UndirectedGraph()
  for (const [id, p] of spiralSeed(ids, 12)) g.addNode(id, { ...p, size: sizeOf(graph, id) })
  graph.forEachEdge((_e, _a, s, t) => { if (visible.has(s) && visible.has(t) && s !== t && !g.hasEdge(s, t)) g.addEdge(s, t, { weight: 1 }) })
  if (g.order > 1) {
    const settings = { ...forceAtlas2.inferSettings(g), linLogMode: true, gravity: 0.6, scalingRatio: 18 * spacing, adjustSizes: false, barnesHutOptimize: g.order > 300 }
    forceAtlas2.assign(g, { iterations: g.order > 400 ? 150 : 350, settings })
  }
  // normalise so the median edge is long enough for labels, then remove overlaps
  const lengths: number[] = []
  g.forEachEdge((_e, _a, s, t) => { const p = g.getNodeAttributes(s), q = g.getNodeAttributes(t); lengths.push(Math.hypot(p.x - q.x, p.y - q.y)) })
  lengths.sort((a, b) => a - b)
  const med = lengths[Math.floor(lengths.length / 2)] || 1
  const scale = (70 * spacing) / med
  const positions = new Map<string, Pos>()
  g.forEachNode((id, p) => positions.set(id, { x: p.x * scale, y: p.y * scale }))
  resolveOverlaps(positions, (id) => sizeOf(graph, id), 8 * spacing)
  return positions
}

/** Smallest distance between the borders of any two placed nodes (negative = overlap). For tests. */
export function minGap(positions: Map<string, Pos>, size: (id: string) => number): number {
  const ids = [...positions.keys()]
  let best = Infinity
  for (let i = 0; i < ids.length; i++) for (let j = i + 1; j < ids.length; j++) {
    const p = positions.get(ids[i])!, q = positions.get(ids[j])!
    best = Math.min(best, Math.hypot(p.x - q.x, p.y - q.y) - size(ids[i]) - size(ids[j]))
  }
  return best
}

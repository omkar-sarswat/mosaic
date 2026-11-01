import { MultiDirectedGraph } from 'graphology'
import { iconUri } from './icons.ts'
import { edgeColour, familyOf, relFamily, shortLabel, SIZE, typeColour } from './graph-style.ts'
import { colours } from './palette.ts'

export type GNodeIn = { id: string; type: string; label: string; score?: number | null; role?: string | null; alerts?: number; seed?: boolean; group?: boolean; count?: number }
export type GEdgeIn = { id: string; source: string; target: string; type: string; amount?: number | null; count?: number | null; evidence?: string; status?: string }
// Colour family + glyph + size encode what a record is; colour never encodes risk (see graph-style.ts).
export const NODE_COLORS: Record<string, string> = Object.fromEntries(
  ['Person', 'Organisation', 'BankAccount', 'CryptoWallet', 'Phone', 'Device', 'Vehicle', 'Property', 'Location', 'Incident', 'Firearm', 'Case'].map((t) => [t, typeColour(t)]),
)
export function createNetwork() { return new MultiDirectedGraph() }
export function mergeNetwork(graph: MultiDirectedGraph, nodes: GNodeIn[], edges: GEdgeIn[], focus?: string) {
  const origin = focus && graph.hasNode(focus) ? graph.getNodeAttributes(focus) : { x: 0, y: 0 }
  nodes.forEach((node, index) => {
    const angle = (graph.order + index) * 2.399963229728653
    const radius = 20 + Math.sqrt(graph.order + index + 1) * 12
    const fam = familyOf(node.type)
    const full = node.group ? `${node.count ?? 0} × ${node.type}` : node.label
    const attributes = { ...node, entityType: node.type, family: fam, type: 'image', image: iconUri(node.type, colours().surface), fullLabel: full,
      label: node.group ? full : shortLabel(node.type, node.label), color: typeColour(node.type), size: SIZE[fam], forceLabel: false }
    if (graph.hasNode(node.id)) graph.mergeNodeAttributes(node.id, attributes)
    else graph.addNode(node.id, { ...attributes, x: origin.x + Math.cos(angle) * radius, y: origin.y + Math.sin(angle) * radius })
  })
  let omitted = 0
  edges.forEach((edge) => {
    if (!graph.hasNode(edge.source) || !graph.hasNode(edge.target)) { omitted++; return }
    const qualifier = edge.status === 'candidate' || edge.evidence === 'suggested' ? ' · suggested' : ''
    const money = edge.type === 'transferred_to'
    const attributes = { ...edge, relationType: edge.type, relFamily: relFamily(edge.type), type: 'arrow', color: edgeColour(edge.type),
      label: edge.type.replaceAll('_', ' ') + (money && edge.amount ? ` · ${inrShort(edge.amount)}` : '') + qualifier,
      size: money && edge.amount ? Math.min(3.2, 0.6 + 0.9 * Math.log10(edge.amount / 1e5 + 1)) : 0.55, weight: 1 }
    // Stable edge IDs must never silently attach evidence to different endpoints.
    if (graph.hasEdge(edge.id)) {
      if (graph.source(edge.id) === edge.source && graph.target(edge.id) === edge.target) graph.mergeEdgeAttributes(edge.id, attributes)
      else omitted++
    } else graph.addDirectedEdgeWithKey(edge.id, edge.source, edge.target, attributes)
  })
  return omitted
}
function inrShort(v: number): string {
  if (v >= 1e7) return `₹${(v / 1e7).toFixed(2)} Cr`
  if (v >= 1e5) return `₹${(v / 1e5).toFixed(1)} L`
  return `₹${Math.round(v).toLocaleString('en-IN')}`
}
// Traverse connections in either direction while retaining the records' directed edges.
export function visiblePath(graph: MultiDirectedGraph, source: string, target: string, options: { directed?: boolean; relations?: Set<string> } = {}): { nodes: string[]; edges: string[] } | null {
  if (!graph.hasNode(source) || !graph.hasNode(target)) return null
  const queue = [source]
  const parents = new Map<string, { node: string; edge: string } | null>([[source, null]])
  for (let i = 0; i < queue.length; i++) {
    const node = queue[i]
    if (node === target) {
      const nodes = [node], edges: string[] = []
      let current = node
      while (parents.get(current)) { const parent = parents.get(current)!; edges.unshift(parent.edge); nodes.unshift(parent.node); current = parent.node }
      return { nodes, edges }
    }
    graph.forEachEdge(node, (edge, attrs, a, b) => {
      if (options.directed && a !== node) return
      if (options.relations && !options.relations.has(attrs.relationType)) return
      const neighbor = a === node ? b : a
      if (!parents.has(neighbor)) { parents.set(neighbor, { node, edge }); queue.push(neighbor) }
    })
  }
  return null
}

/** Edmonds-Karp maximum flow over transfers: the most money that could have moved from `source` to
 *  `sink` through the loaded accounts, given what each pair of accounts actually exchanged (capacity =
 *  total transferred). Returns the flow value, the transfers carrying it and the bottleneck cut. */
export function maxMoneyFlow(graph: MultiDirectedGraph, source: string, sink: string) {
  if (!graph.hasNode(source) || !graph.hasNode(sink) || source === sink) return null
  const cap = new Map<string, Map<string, number>>()
  const edgesOf = new Map<string, string[]>()
  const add = (a: string, b: string, c: number) => {
    if (!cap.has(a)) cap.set(a, new Map())
    if (!cap.has(b)) cap.set(b, new Map())
    cap.get(a)!.set(b, (cap.get(a)!.get(b) ?? 0) + c)
    if (!cap.get(b)!.has(a)) cap.get(b)!.set(a, 0)
  }
  graph.forEachEdge((id, attrs, a, b) => {
    if (attrs.relationType !== 'transferred_to' || a === b) return
    const amount = Number(attrs.amount) || 0
    if (amount <= 0) return
    add(a, b, amount)
    const key = `${a}\u0000${b}`
    edgesOf.set(key, [...(edgesOf.get(key) ?? []), id])
  })
  if (!cap.has(source) || !cap.has(sink)) return { value: 0, edges: [] as string[], cut: [] as string[], paths: 0 }
  const flow = new Map<string, number>()
  const f = (a: string, b: string) => flow.get(`${a}\u0000${b}`) ?? 0
  let value = 0, paths = 0
  for (;;) {
    const parent = new Map<string, string>([[source, source]])
    const queue = [source]
    for (let i = 0; i < queue.length && !parent.has(sink); i++) {
      const u = queue[i]
      for (const [v, c] of cap.get(u)!) if (!parent.has(v) && c - f(u, v) > 1e-6) { parent.set(v, u); queue.push(v) }
    }
    if (!parent.has(sink)) break
    let push = Infinity
    for (let v = sink; v !== source; v = parent.get(v)!) { const u = parent.get(v)!; push = Math.min(push, cap.get(u)!.get(v)! - f(u, v)) }
    for (let v = sink; v !== source; v = parent.get(v)!) {
      const u = parent.get(v)!
      flow.set(`${u}\u0000${v}`, f(u, v) + push)
      flow.set(`${v}\u0000${u}`, f(v, u) - push)
    }
    value += push
    paths++
  }
  // residual reachability gives the minimum cut (the transfers that bound the flow)
  const seen = new Set([source])
  const queue = [source]
  for (let i = 0; i < queue.length; i++) for (const [v, c] of cap.get(queue[i])!) if (!seen.has(v) && c - f(queue[i], v) > 1e-6) { seen.add(v); queue.push(v) }
  const carrying: string[] = [], cut: string[] = []
  for (const [key, ids] of edgesOf) {
    const [a, b] = key.split('\u0000')
    if (f(a, b) > 1e-6) carrying.push(...ids)
    if (seen.has(a) && !seen.has(b)) cut.push(...ids)
  }
  return { value, edges: carrying, cut, paths }
}

/** Yen's k shortest loopless paths (1971) on unit-weight relationships, either direction. Shows the
 *  alternative routes between two records, not just the first one found. */
export function kShortestPaths(graph: MultiDirectedGraph, source: string, target: string, k = 3, options: { relations?: Set<string> } = {}) {
  type Path = { nodes: string[]; edges: string[] }
  const bfs = (from: string, to: string, banNodes: Set<string>, banEdges: Set<string>): Path | null => {
    const parents = new Map<string, { node: string; edge: string } | null>([[from, null]])
    const queue = [from]
    for (let i = 0; i < queue.length; i++) {
      const node = queue[i]
      if (node === to) {
        const nodes = [to], edges: string[] = []
        for (let cur = to; parents.get(cur); cur = parents.get(cur)!.node) { edges.unshift(parents.get(cur)!.edge); nodes.unshift(parents.get(cur)!.node) }
        return { nodes, edges }
      }
      const options2: [string, string][] = []
      graph.forEachEdge(node, (edge, attrs, a, b) => {
        if (options.relations && !options.relations.has(attrs.relationType)) return
        if (banEdges.has(edge)) return
        const next = a === node ? b : a
        if (!banNodes.has(next) && !parents.has(next)) options2.push([next, edge])
      })
      options2.sort((x, y) => x[0].localeCompare(y[0]) || x[1].localeCompare(y[1]))
      for (const [next, edge] of options2) if (!parents.has(next)) { parents.set(next, { node, edge }); queue.push(next) }
    }
    return null
  }
  if (!graph.hasNode(source) || !graph.hasNode(target)) return []
  const first = bfs(source, target, new Set(), new Set())
  if (!first) return []
  const A: Path[] = [first]
  const B: Path[] = []
  const key = (p: Path) => p.edges.join('|')
  for (let kk = 1; kk < k; kk++) {
    const last = A[kk - 1]
    for (let i = 0; i < last.nodes.length - 1; i++) {
      const spur = last.nodes[i]
      const rootNodes = last.nodes.slice(0, i + 1), rootEdges = last.edges.slice(0, i)
      const banEdges = new Set<string>()
      for (const p of A) if (p.nodes.slice(0, i + 1).join('|') === rootNodes.join('|') && p.edges[i]) {
        // ban every parallel edge between the same two records so the detour is a genuinely different route
        const [a, b] = [p.nodes[i], p.nodes[i + 1]]
        graph.forEachEdge(a, b, (e) => { banEdges.add(e) })
        graph.forEachEdge(b, a, (e) => { banEdges.add(e) })
      }
      const banNodes = new Set(rootNodes.slice(0, -1))
      const tail = bfs(spur, target, banNodes, banEdges)
      if (!tail) continue
      const cand = { nodes: [...rootNodes.slice(0, -1), ...tail.nodes], edges: [...rootEdges, ...tail.edges] }
      if (![...A, ...B].some((p) => key(p) === key(cand))) B.push(cand)
    }
    if (!B.length) break
    B.sort((x, y) => x.edges.length - y.edges.length || key(x).localeCompare(key(y)))
    A.push(B.shift()!)
  }
  return A
}

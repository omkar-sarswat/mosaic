import { MultiDirectedGraph, UndirectedGraph } from 'graphology'
import louvain from 'graphology-communities-louvain'
import { connectedComponents, stronglyConnectedComponents } from 'graphology-components'

// Structure of the loaded network. Every measure describes the shape of the records an officer is
// allowed to see; none of them is a judgement about a person, and none is stored.
export type NetworkReport = {
  records: number; relationships: number; uniquePairs: number; density: number
  components: string[][]; cycles: string[][]; communities: Record<string, number>
  communityCount: number; modularity: number | null; resolution: number
  bridges: { source: string; target: string; edges: string[] }[]
  articulation: string[]
  core: { number: Record<string, number>; max: number; members: string[] }
  brokers: { id: string; betweenness: number }[]
  elapsedMs: number
}

function simpleProjection(graph: MultiDirectedGraph) {
  const simple = new UndirectedGraph()
  graph.nodes().sort().forEach((id) => simple.addNode(id))
  graph.forEachEdge((edge, _attrs, a, b) => {
    if (a === b) return
    if (simple.hasEdge(a, b)) simple.getEdgeAttribute(a, b, 'records').push(edge)
    else simple.addEdge(a, b, { weight: 1, records: [edge] })
  })
  return simple
}

/** Bridges and articulation points in one iterative depth-first pass (Tarjan 1974). */
function bridgesAndCuts(simple: UndirectedGraph) {
  const bridges: NetworkReport['bridges'] = []
  const cuts = new Set<string>()
  const disc = new Map<string, number>(), low = new Map<string, number>()
  let clock = 0
  for (const root of simple.nodes()) {
    if (disc.has(root)) continue
    disc.set(root, ++clock); low.set(root, clock)
    let rootChildren = 0
    const stack: { node: string; parent: string | null; neighbors: string[]; index: number }[] = [{ node: root, parent: null, neighbors: simple.neighbors(root), index: 0 }]
    while (stack.length) {
      const frame = stack[stack.length - 1]
      if (frame.index < frame.neighbors.length) {
        const next = frame.neighbors[frame.index++]
        if (next === frame.parent) continue
        if (!disc.has(next)) {
          if (frame.node === root) rootChildren++
          disc.set(next, ++clock); low.set(next, clock)
          stack.push({ node: next, parent: frame.node, neighbors: simple.neighbors(next), index: 0 })
        } else low.set(frame.node, Math.min(low.get(frame.node)!, disc.get(next)!))
      } else {
        stack.pop()
        if (frame.parent !== null) {
          low.set(frame.parent, Math.min(low.get(frame.parent)!, low.get(frame.node)!))
          if (low.get(frame.node)! > disc.get(frame.parent)!) bridges.push({ source: frame.parent, target: frame.node, edges: simple.getEdgeAttribute(frame.parent, frame.node, 'records') })
          if (frame.parent !== root && low.get(frame.node)! >= disc.get(frame.parent)!) cuts.add(frame.parent)
        }
      }
    }
    if (rootChildren > 1) cuts.add(root)
  }
  return { bridges, articulation: [...cuts].sort() }
}

/** k-core decomposition (Batagelj & Zaversnik 2003), O(E). */
export function coreNumbers(simple: UndirectedGraph): Record<string, number> {
  const deg = new Map(simple.nodes().map((n) => [n, simple.degree(n)]))
  const maxDeg = Math.max(0, ...deg.values())
  const bins: Set<string>[] = Array.from({ length: maxDeg + 1 }, () => new Set())
  for (const [n, d] of deg) bins[d].add(n)
  const core: Record<string, number> = {}
  for (let d = 0; d <= maxDeg; d++) {
    while (bins[d].size) {
      const n = bins[d].values().next().value as string
      bins[d].delete(n)
      core[n] = d
      simple.forEachNeighbor(n, (m) => {
        if (m in core) return
        const dm = deg.get(m)!
        if (dm > d) { bins[dm].delete(m); deg.set(m, dm - 1); bins[dm - 1].add(m) }
      })
    }
  }
  return core
}

/** Brandes (2001) betweenness on the unweighted, undirected projection, normalised to [0, 1]. */
export function betweenness(simple: UndirectedGraph): Record<string, number> {
  const nodes = simple.nodes()
  const cb: Record<string, number> = Object.fromEntries(nodes.map((n) => [n, 0]))
  for (const s of nodes) {
    const stack: string[] = [], pred = new Map<string, string[]>(), sigma = new Map<string, number>(), dist = new Map<string, number>()
    for (const n of nodes) { pred.set(n, []); sigma.set(n, 0); dist.set(n, -1) }
    sigma.set(s, 1); dist.set(s, 0)
    const queue = [s]
    for (let qi = 0; qi < queue.length; qi++) {
      const v = queue[qi]
      stack.push(v)
      simple.forEachNeighbor(v, (w) => {
        if (dist.get(w)! < 0) { dist.set(w, dist.get(v)! + 1); queue.push(w) }
        if (dist.get(w) === dist.get(v)! + 1) { sigma.set(w, sigma.get(w)! + sigma.get(v)!); pred.get(w)!.push(v) }
      })
    }
    const delta = new Map(nodes.map((n) => [n, 0]))
    while (stack.length) {
      const w = stack.pop()!
      for (const v of pred.get(w)!) delta.set(v, delta.get(v)! + (sigma.get(v)! / sigma.get(w)!) * (1 + delta.get(w)!))
      if (w !== s) cb[w] += delta.get(w)!
    }
  }
  const n = nodes.length
  const norm = n > 2 ? (n - 1) * (n - 2) : 1  // undirected: each pair counted twice above
  for (const k of nodes) cb[k] = cb[k] / norm
  return cb
}

export function analyzeNetwork(graph: MultiDirectedGraph, resolution = 1): NetworkReport {
  const started = performance.now()
  const simple = simpleProjection(graph)
  const communities = simple.size ? louvain.detailed(simple, { resolution, randomWalk: false, getEdgeWeight: null }) : null
  const { bridges, articulation } = bridgesAndCuts(simple)
  const coreNum = coreNumbers(simple)
  const maxCore = Math.max(0, ...Object.values(coreNum))
  const bc = simple.order <= 1500 ? betweenness(simple) : {}
  const brokers = Object.entries(bc).filter(([, v]) => v > 0).sort((a, b) => b[1] - a[1]).slice(0, 12).map(([id, v]) => ({ id, betweenness: Math.round(v * 1000) / 1000 }))
  const cycles = stronglyConnectedComponents(graph).filter((nodes) => nodes.length > 1 || graph.hasEdge(nodes[0], nodes[0])).sort((a, b) => b.length - a.length)
  return {
    records: graph.order, relationships: graph.size, uniquePairs: simple.size,
    density: simple.order > 1 ? 2 * simple.size / (simple.order * (simple.order - 1)) : 0,
    components: connectedComponents(graph).sort((a, b) => b.length - a.length), cycles,
    communities: communities?.communities ?? Object.fromEntries(simple.nodes().map((id, index) => [id, index])),
    communityCount: communities?.count ?? simple.order,
    modularity: communities && Number.isFinite(communities.modularity) ? communities.modularity : null,
    resolution, bridges, articulation,
    core: { number: coreNum, max: maxCore, members: Object.entries(coreNum).filter(([, k]) => k === maxCore && maxCore > 1).map(([id]) => id).sort() },
    brokers, elapsedMs: performance.now() - started,
  }
}

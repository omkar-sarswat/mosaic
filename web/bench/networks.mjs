// External benchmark: run the product's own network analysis (src/lib/network-analysis.ts) on real
// criminal networks (Montagna, Caviar) and write the full rankings for scoring by bench/criminal_networks.py.
//   node --experimental-strip-types bench/networks.mjs <edges.json> <out.json>
// edges.json: { "<network name>": [[source, target, weight], ...], ... }
import { readFileSync, writeFileSync } from 'node:fs'
import { MultiDirectedGraph, UndirectedGraph } from 'graphology'
import { analyzeNetwork, betweenness, coreNumbers } from '../src/lib/network-analysis.ts'

const [, , input, output] = process.argv
const networks = JSON.parse(readFileSync(input, 'utf8'))
const out = {}
for (const [name, edges] of Object.entries(networks)) {
  const g = new MultiDirectedGraph()
  const simple = new UndirectedGraph()
  for (const [s, t, w] of edges) {
    for (const id of [s, t]) {
      if (!g.hasNode(id)) g.addNode(id, { type: 'Person', label: id })
      if (!simple.hasNode(id)) simple.addNode(id)
    }
    if (s === t) continue
    g.addEdge(s, t, { type: 'called', weight: w })
    if (!simple.hasEdge(s, t)) simple.addEdge(s, t)
  }
  const report = analyzeNetwork(g)
  const degree = Object.fromEntries(simple.nodes().map((id) => [id, simple.degree(id)]))
  out[name] = {
    nodes: simple.order, edges: simple.size, communities: report.communities, communityCount: report.communityCount,
    modularity: report.modularity, articulation: report.articulation, core: coreNumbers(simple), coreMax: report.core.max,
    coreMembers: report.core.members, betweenness: betweenness(simple), degree, brokers: report.brokers, elapsedMs: report.elapsedMs,
  }
}
writeFileSync(output, JSON.stringify(out))
console.log(Object.entries(out).map(([k, v]) => `${k}: ${v.nodes} people, ${v.edges} ties, ${v.communityCount} communities, max core ${v.coreMax}`).join('\n'))

import { MultiDirectedGraph } from 'graphology'
import { analyzeNetwork } from './network-analysis'

self.onmessage = (event) => {
  try {
    const graph = new MultiDirectedGraph()
    graph.import(event.data.graph)
    self.postMessage({ report: analyzeNetwork(graph, event.data.resolution) })
  } catch (error) { self.postMessage({ error: error instanceof Error ? error.message : String(error) }) }
}

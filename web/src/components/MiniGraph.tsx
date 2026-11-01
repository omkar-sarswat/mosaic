import { useEffect, useRef } from 'react'
import Sigma from 'sigma'
import { MultiDirectedGraph } from 'graphology'
import { forceLayout } from '../lib/graph-layouts'
import { familyColour, SIZE, type Family } from '../lib/graph-style'
import { colours, theme as currentTheme } from '../lib/palette'

// A small, read-only link chart for one extract: only the parts that form a pattern are drawn, so it
// stays legible. Kind follows the shared encoding (colour family + size); status is written in the label.
type GNode = { id: string; label: string; kind: string; status: string; person?: string | null }
type GLink = { source: string; target: string; label: string }

const FAMILIES: Family[] = ['actor', 'money', 'asset', 'record', 'comms']
const STATUS: Record<string, string> = { new: 'new', probable: 'probable match' }

export default function MiniGraph({ nodes, links, height = 340, onOpen }: { nodes: GNode[]; links: GLink[]; height?: number; onOpen?: (person: string) => void }) {
  const el = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!el.current || !nodes.length) return
    const light = currentTheme() === 'light'
    const g = new MultiDirectedGraph()
    for (const n of nodes) {
      const fam = (FAMILIES.includes(n.kind as Family) ? n.kind : 'other') as Family
      const suffix = n.kind === 'actor' && STATUS[n.status] ? ` · ${STATUS[n.status]}` : ''
      g.addNode(n.id, { label: n.label + suffix, forceLabel: true, size: SIZE[fam] * 0.6, color: familyColour(fam, light ? 'light' : 'dark'), person: n.person ?? null })
    }
    for (const l of links) if (g.hasNode(l.source) && g.hasNode(l.target)) g.addEdge(l.source, l.target, { label: l.label, size: 1.5, color: colours().muted })
    const pos = forceLayout(g, new Set(g.nodes()), 1.6)
    for (const [id, p] of pos) g.mergeNodeAttributes(id, p)
    const css = getComputedStyle(document.documentElement)
    const sigma = new Sigma(g, el.current, {
      allowInvalidContainer: true, itemSizesReference: 'positions', zoomToSizeRatioFunction: (r) => r,
      labelFont: 'Source Sans 3 Variable', labelSize: 11, labelWeight: '400', labelColor: { color: css.getPropertyValue('--text').trim() || colours().text },
      edgeLabelFont: 'Source Sans 3 Variable', edgeLabelSize: 10, edgeLabelColor: { color: css.getPropertyValue('--muted').trim() || colours().muted },
      renderEdgeLabels: true, labelRenderedSizeThreshold: 2, stagePadding: 70, minCameraRatio: 0.1, maxCameraRatio: 3, minEdgeThickness: 1.25,
    })
    sigma.on('clickNode', ({ node }) => {
      const p = g.getNodeAttribute(node, 'person')
      if (p && onOpen) onOpen(p)
    })
    return () => sigma.kill()
  }, [nodes, links, onOpen])
  if (!nodes.length) return <p className="muted small">Nothing in this extract forms a pattern, so there is nothing to chart.</p>
  return <div ref={el} className="mini-graph" style={{ height }} role="img" aria-label="Links the extract would add" />
}

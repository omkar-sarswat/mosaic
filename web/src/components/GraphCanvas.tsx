import { ButtonGroup, Icon } from '@blueprintjs/core'
import { Button } from './Button'
import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from 'react'
import Sigma from 'sigma'
import { EdgeArrowProgram } from 'sigma/rendering'
import { createNodeImageProgram } from '@sigma/node-image'
import { createEdgeCurveProgram, indexParallelEdgesIndex } from '@sigma/edge-curve'
import { api, type Trace } from '../api'
import FlowDiagram from './FlowDiagram'
import { createNetwork, kShortestPaths, maxMoneyFlow, mergeNetwork, visiblePath, type GEdgeIn, type GNodeIn } from '../lib/network'
import { inr } from '../lib/format'
import { arrangeGroups, chooseFocus, matchesLayer, TYPE_LABELS, type GroupBox, type LayoutMode, type RelationshipLayer } from '../lib/network-layout'
import { forceLayout, moneyLayout, structureLayout, type Pos } from '../lib/graph-layouts'
import { buildView, collapseGroups, equivalentGroups, moneyParties, orbits, type ViewStats } from '../lib/graph-projection'
import { edgeColour, FAMILY_LABEL, FAMILY_ORDER, familyColour, familyOf, typeColour, type Family } from '../lib/graph-style'
import type { NetworkReport } from '../lib/network-analysis'
import NetworkAnalysis from './NetworkAnalysis'
import { iconUri } from '../lib/icons'

const ImageNode = createNodeImageProgram({ padding: 0.2, size: { mode: 'force', value: 64 } })
// Keep direction readable at overview scale and in exported screen captures.
const ReadableCurvedArrow = createEdgeCurveProgram({
  arrowHead: { extremity: 'target', lengthToThicknessRatio: 5, widenessToThicknessRatio: 3.5 },
})
const LEGEND: Family[] = ['actor', ...FAMILY_ORDER]
const LAYOUTS: { id: LayoutMode; label: string; hint: string }[] = [
  { id: 'structure', label: 'Structure', hint: 'People and organisations by their relationships; each one’s accounts, phones, property and records around it' },
  { id: 'money', label: 'Money flow', hint: 'Accounts in layers from left to right, in the direction money moved' },
  { id: 'types', label: 'By record type', hint: 'Records grouped into boxes by type' },
  { id: 'communities', label: 'By community', hint: 'Records grouped by Louvain community' },
  { id: 'neighborhood', label: 'Neighbourhood', hint: 'Only the records around the selected record' },
  { id: 'force', label: 'Force-directed', hint: 'ForceAtlas2 over everything visible' },
]
const PATHS = [
  { id: 'connection', label: 'Shortest connection, either direction' },
  { id: 'alternatives', label: 'Three alternative routes (Yen)' },
  { id: 'directed', label: 'Shortest path following arrows' },
  { id: 'money', label: 'Money path, transfers only' },
  { id: 'maxflow', label: 'Most money that could have moved (max flow)' },
]

export type { GNodeIn, GEdgeIn } from '../lib/network'
export type GraphHandle = {
  add: (nodes: GNodeIn[], edges: GEdgeIn[], focus?: string) => void
  fit: () => void
  clear: () => void
  highlight: (nodes: string[], edges: string[]) => void
}
type Props = {
  onSelect?: (id: string | null, data?: Record<string, unknown>) => void
  onOpen?: (id: string) => void
  onExpand?: (id: string) => void
  height?: string | number
  caseBounded?: boolean
  compact?: boolean
  /** draw people with identical links as one group node (off where the list of associates is the point) */
  groupSimilar?: boolean
}
type Theme = 'dark' | 'light'
const themeNow = (): Theme => (document.documentElement.dataset.theme === 'light' ? 'light' : 'dark')

const GraphCanvas = forwardRef<GraphHandle, Props>(function GraphCanvas({ onSelect, onOpen, onExpand, height = '100%', caseBounded = false, compact = false, groupSimilar = true }, ref) {
  const el = useRef<HTMLDivElement>(null)
  const groupCanvas = useRef<HTMLCanvasElement>(null)
  const groups = useRef<GroupBox[]>([])
  const analyzer = useRef<Worker | null>(null)
  const [graph] = useState(createNetwork)  // the records
  const [view] = useState(createNetwork)   // what is drawn (see graph-projection.ts)
  const renderer = useRef<Sigma | null>(null)
  const epoch = useRef(0)
  const callbacks = useRef({ onSelect, onOpen, onExpand, caseBounded })
  callbacks.current = { onSelect, onOpen, onExpand, caseBounded }
  const state = useRef({
    selected: [] as string[], hovered: null as string | null, pathNodes: new Set<string>(), pathEdges: new Set<string>(),
    filter: '', visible: new Set<string>(), layer: 'all' as RelationshipLayer, allEdges: true, mode: 'structure' as LayoutMode,
    limit: compact ? 60 : 90, spacing: 1, depth: 1, root: '', subset: undefined as Set<string> | undefined,
    communities: {} as Record<string, number>, hidden: new Set<Family>(), inferred: false,
    angles: new Map<string, number>(), altLabels: new Map<string, string>(),
    orbit: new Map<string, string>(), focus: null as Set<string> | null, stats: null as ViewStats | null, note: '',
    grouping: groupSimilar, expanded: new Set<string>(), groups: new Map<string, string[]>(), partyOf: new Map<string, string>(),
    text: '#e4e4e0', muted: '#a1a3a8', dim: '#2b2d31', surface: '#141517', theme: 'dark' as Theme,
  })
  const [selected, setSelected] = useState<string[]>([])
  const [revision, setRevision] = useState(0)
  const [busy, setBusy] = useState(false)
  const [labels, setLabels] = useState(true)
  const [msg, setMsg] = useState('')
  const [failure, setFailure] = useState('')
  const [listOpen, setListOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState('')
  const [mode, setMode] = useState<LayoutMode>('structure')
  const [layer, setLayer] = useState<RelationshipLayer>('all')
  const [allEdges, setAllEdges] = useState(true)
  const [inferred, setInferred] = useState(false)
  const [grouping, setGrouping] = useState(groupSimilar)
  const [flow, setFlow] = useState<Trace | null>(null)
  const [limit, setLimit] = useState(compact ? 60 : 90)
  const [spacing, setSpacing] = useState(1)
  const [depth, setDepth] = useState(1)
  const [pathMode, setPathMode] = useState('connection')
  const [eligible, setEligible] = useState(0)
  const [hidden, setHidden] = useState<Set<Family>>(new Set())
  const [analysisOpen, setAnalysisOpen] = useState(false)
  const [analyzing, setAnalyzing] = useState(false)
  const [analysisError, setAnalysisError] = useState('')
  const [report, setReport] = useState<NetworkReport | null>(null)
  const [resolution, setResolution] = useState(1)

  const fit = () => renderer.current?.getCamera().animatedReset({ duration: 250 })
  const nodeLabel = (id: string) => (graph.hasNode(id) ? String(graph.getNodeAttribute(id, 'fullLabel') ?? graph.getNodeAttribute(id, 'label')) : id)

  // ------------------------------------------------------------------ layout
  const layout = () => {
    if (!graph.order) return
    const s = state.current
    const neighborhoodRoot = s.mode === 'neighborhood' ? s.root : undefined
    const { visible, eligible: count } = chooseFocus(graph, {
      limit: s.limit, type: s.filter, layer: s.layer, root: neighborhoodRoot, depth: s.depth, subset: s.subset, hidden: s.hidden,
      pinned: new Set([...s.selected, ...s.pathNodes]), money: s.mode === 'money',
    })
    s.visible = visible
    setEligible(count)
    groups.current = []
    s.angles = new Map()
    s.altLabels = new Map()
    s.note = ''
    let positions: Map<string, Pos> | null = null
    if (s.mode === 'types' || s.mode === 'communities') {
      const aspect = el.current ? el.current.clientWidth / Math.max(el.current.clientHeight, 1) : 1.6
      groups.current = arrangeGroups(graph, visible, s.mode, s.communities, aspect, s.spacing)
    } else if (s.mode === 'money') {
      // money moves between parties: each account is shown as its holder, transfers summed per pair
      const parties = moneyParties(graph, visible)
      const r = moneyLayout(parties, new Set(parties.nodes()), s.spacing)
      s.note = r.reversed ? `${r.reversed} flow(s) loop back to an earlier party` : ''
      s.partyOf = new Map()
      for (const [id, a] of parties.mapNodes((n, at) => [n, at] as const)) for (const acc of (a.accountIds as string[] | undefined) ?? []) s.partyOf.set(acc, id)
      view.clear()
      parties.forEachNode((id, a) => {
        const p = r.positions.get(id) ?? { x: 0, y: 0 }
        view.addNode(id, { ...a, ...p })
        if (a.accounts) {
          const name = String(a.fullLabel ?? a.label)
          s.altLabels.set(id, `${name.length > 22 ? name.slice(0, 21) + '…' : name} · ${a.accounts} a/c`)
        }
      })
      parties.forEachEdge((id, a, from, to) => view.addDirectedEdgeWithKey(id, from, to, { ...a }))
      for (const id of r.positions.keys()) s.angles.set(id, 0)  // labels to the right: columns never collide
      s.stats = { nodes: view.order, edges: view.size, aggregated: view.size, members: parties.reduceEdges((n, _e, a) => n + (a.members?.length ?? 0), 0) }
      // money is read as a flow diagram (Sankey with one lane per transfer), not as a node-link canvas
      setFlow({
        direction: 'out', sinks: {}, beneficiaries: [], traced_total: 0, accounts_reached: 0,
        nodes: parties.mapNodes((id, a) => {
          const name = String(a.fullLabel ?? a.label)
          return { id, label: name, holder: id, holder_name: a.accounts > 1 ? `${name} · ${a.accounts} a/c` : name, holder_type: String(a.entityType),
            kind: 'account', hop: 0, alerts: Number(a.alerts) > 0 ? ['flagged'] : [] }
        }),
        links: parties.mapEdges((_e, a, from, to) => ({ source: from, target: to, value: Number(a.amount) || Number(a.count) || 1, count: Number(a.count) || 1 })),
      })
      s.orbit = new Map()
      s.groups = new Map()
      s.focus = null
      renderer.current?.setSetting('labelRenderedSizeThreshold', 3)
      renderer.current?.setSetting('stagePadding', 90)
      renderer.current?.setCustomBBox(null)
      setRevision((n) => n + 1)
      renderer.current?.refresh()
      fit()
      return
    } else if (s.mode === 'force') positions = forceLayout(graph, visible, s.spacing)
    else positions = structureLayout(graph, visible, s.spacing, s.angles)
    if (positions) for (const [id, p] of positions) graph.mergeNodeAttributes(id, p)
    renderer.current?.setSetting('labelRenderedSizeThreshold', compact ? 7 : 6)
    renderer.current?.setSetting('stagePadding', compact ? 36 : 56)
    // the presentation graph: in the structure views, links between two orbits are drawn once, aggregated
    const aggregate = s.mode === 'structure' || s.mode === 'neighborhood'
    s.orbit = aggregate ? orbits(graph, visible) : new Map()
    s.stats = buildView(view, graph, visible, { aggregate, straight: false, theme: s.theme, orbit: s.orbit })
    s.groups = new Map()
    if (aggregate && s.grouping) {
      // people with the same links are drawn once (structural equivalence); double-click a group to open it
      const keep = new Set([...s.selected, ...s.pathNodes, ...s.expanded])
      s.groups = collapseGroups(view, s.orbit, equivalentGroups(view, s.orbit, keep), s.theme)
    }
    indexParallelEdgesIndex(view)
    view.forEachEdge((id, a) => { if (!a.meta) view.mergeEdgeAttributes(id, { curvature: a.parallelMaxIndex ? 0.14 + (a.parallelIndex || 0) * 0.16 : 0.06 }) })
    s.focus = null
    if (groups.current.length) {
      const boxes = groups.current
      renderer.current?.setCustomBBox({ x: [0, Math.max(...boxes.map((b) => b.x + b.width))], y: [Math.min(...boxes.map((b) => b.y - b.height)), 0] })
    } else renderer.current?.setCustomBBox(null)
    setRevision((n) => n + 1)
    renderer.current?.refresh()
    fit()
  }

  const recolour = () => {
    const t = state.current.theme
    for (const g of [graph, view]) {
      g.forEachNode((id, a) => g.mergeNodeAttributes(id, { color: typeColour(a.entityType, t), image: iconUri(a.entityType, state.current.surface) }))
      g.forEachEdge((id, a) => { if (!a.meta) g.mergeEdgeAttributes(id, { color: edgeColour(a.relationType, t) }) })
    }
  }
  // the records in focus around the active record: its orbit and everything linked to that orbit
  const refocus = () => {
    const s = state.current
    const active = s.hovered || s.selected.at(-1)
    if (!active || !view.hasNode(active)) { s.focus = null; return }
    const home = s.orbit.get(active) ?? active
    const inOrbit = view.filterNodes((id) => (s.orbit.get(id) ?? id) === home)
    const focus = new Set<string>(inOrbit)
    for (const id of inOrbit) view.forEachNeighbor(id, (n) => { focus.add(n) })
    s.focus = focus
  }

  // ------------------------------------------------------------------ selection
  const choose = (id: string | null, multiple = false) => {
    const previous = state.current.selected
    const next = id ? (multiple ? (previous.includes(id) ? previous.filter((n) => n !== id) : [...previous, id]) : [id]) : []
    state.current.selected = next
    setSelected(next)
    if (id && !id.startsWith('group:') && !state.current.visible.has(id)) layout()
    refocus()
    const last = next.at(-1)
    const data = last && graph.hasNode(last) ? graph.getNodeAttributes(last) : undefined
    callbacks.current.onSelect?.(last ?? null, data ? { ...data, type: data.entityType } : undefined)
    renderer.current?.refresh()
  }
  const add = (nodes: GNodeIn[], edges: GEdgeIn[], focus?: string) => {
    const omitted = mergeNetwork(graph, nodes, edges, focus)
    graph.forEachEdge((id) => graph.mergeEdgeAttributes(id, { type: 'curved' }))
    recolour()
    analyzer.current?.terminate()
    analyzer.current = null
    setAnalyzing(false)
    setReport(null)
    if (omitted) setMsg(`${omitted} connection(s) left out because their records are unavailable or inconsistent.`)
    layout()
  }
  const highlight = (nodes: string[], edges: string[]) => {
    if (state.current.mode === 'money') nodes = nodes.map((n) => state.current.partyOf.get(n) ?? n)
    state.current.pathNodes = new Set(nodes)
    state.current.pathEdges = new Set(edges)
    if (nodes.some((n) => !state.current.visible.has(n))) layout()
    renderer.current?.refresh()
  }
  const resetView = () => {
    const s = state.current
    setFlow(null)
    s.subset = undefined; s.mode = 'structure'; s.filter = ''; s.layer = 'all'; s.pathNodes.clear(); s.pathEdges.clear(); s.hidden = new Set()
    setMode('structure'); setFilter(''); setLayer('all'); setHidden(new Set()); setMsg('')
    layout()
  }
  const clear = () => {
    epoch.current++
    analyzer.current?.terminate()
    analyzer.current = null
    setReport(null)
    setAnalyzing(false)
    graph.clear()
    view.clear()
    groups.current = []
    state.current.visible.clear()
    choose(null)
    highlight([], [])
    setMsg('')
    setBusy(false)
    setRevision((n) => n + 1)
  }
  const expand = async (id: string) => {
    if (id.startsWith('group:')) {
      for (const m of state.current.groups.get(id) ?? []) state.current.expanded.add(m)
      state.current.selected = []
      setSelected([])
      layout()
      return
    }
    if (callbacks.current.onExpand) { callbacks.current.onExpand(id); return }
    if (callbacks.current.caseBounded) { callbacks.current.onOpen?.(id); return }
    if (!graph.hasNode(id) || graph.getNodeAttribute(id, 'group')) return
    const version = epoch.current
    setBusy(true)
    setMsg('')
    try {
      const result = await api.graph(id, 1)
      if (version !== epoch.current) return
      add(result.nodes.map((n) => ({ ...n, count: n.count ?? undefined })), result.edges.map((e) => ({ ...e, amount: Number(e.props?.total) || null, count: Number(e.props?.count) || null })), id)
      if (result.hidden.length) setMsg(result.hidden.map((h) => `${h.count} ${h.type} withheld (${h.reason})`).join(' · '))
    } catch (e) {
      if (version === epoch.current) setMsg((e as Error).message)
    } finally {
      if (version === epoch.current) setBusy(false)
    }
  }
  const actions = useRef({ expand, choose })
  actions.current = { expand, choose }

  // ------------------------------------------------------------------ analysis worker
  const runAnalysis = (toCommunities = false) => {
    analyzer.current?.terminate()
    setAnalyzing(true)
    setAnalysisError('')
    const task = new Worker(new URL('../lib/network-analysis.worker.ts', import.meta.url), { type: 'module' })
    analyzer.current = task
    task.onmessage = (event: MessageEvent<{ report?: NetworkReport; error?: string }>) => {
      if (analyzer.current !== task) return
      setAnalyzing(false)
      if (event.data.report) {
        setReport(event.data.report)
        state.current.communities = event.data.report.communities
        if (toCommunities || state.current.mode === 'communities') { state.current.mode = 'communities'; setMode('communities'); layout() }
      } else setAnalysisError(event.data.error || 'Analysis could not complete.')
      task.terminate()
      analyzer.current = null
    }
    task.onerror = () => {
      if (analyzer.current !== task) return
      setAnalyzing(false)
      setAnalysisError('The analysis worker could not start. Try again.')
      task.terminate()
      analyzer.current = null
    }
    task.postMessage({ graph: graph.export(), resolution })
  }

  // ------------------------------------------------------------------ renderer
  useEffect(() => {
    if (!el.current) return
    const readTheme = () => {
      const css = getComputedStyle(document.documentElement)
      const s = state.current
      s.theme = themeNow()
      s.text = css.getPropertyValue('--text').trim() || '#e4e4e0'
      s.muted = css.getPropertyValue('--muted').trim() || '#a1a3a8'
      s.surface = css.getPropertyValue('--graph-bg').trim() || '#141517'
      s.dim = css.getPropertyValue('--graph-dim').trim() || '#2b2d31'
    }
    readTheme()
    let sigma: Sigma
    try {
      sigma = new Sigma(view, el.current, {
        allowInvalidContainer: true, defaultEdgeType: 'curved', enableEdgeEvents: true,
        nodeProgramClasses: { image: ImageNode }, edgeProgramClasses: { curved: ReadableCurvedArrow, arrow: EdgeArrowProgram },
        // sizes in graph units: the layouts' no-overlap guarantee holds at every zoom level
        itemSizesReference: 'positions', zoomToSizeRatioFunction: (r) => r,
        labelFont: 'Public Sans Variable, sans-serif', labelSize: 11, labelWeight: '400', labelColor: { color: state.current.text },
        edgeLabelFont: 'IBM Plex Sans', edgeLabelSize: 10, edgeLabelColor: { color: state.current.muted },
        stagePadding: compact ? 36 : 56, labelDensity: 0.8, labelGridCellSize: 110,
        // semantic zoom: people's labels appear first, holdings' labels as you zoom in
        labelRenderedSizeThreshold: compact ? 7 : 6, renderEdgeLabels: true,
        minCameraRatio: 0.04, maxCameraRatio: 4, zIndex: true, minEdgeThickness: 1.6,
        nodeReducer: (id, data) => {
          const s = state.current
          const active = s.hovered || s.selected.at(-1)
          const hiddenNode = false  // the presentation graph holds only what is on the canvas (records and groups)
          const marked = s.selected.includes(id) || s.pathNodes.has(id)
          const near = !!active && (active === id || (s.focus ? s.focus.has(id) : view.hasNode(active) && view.areNeighbors(active, id)))
          const dim = (!!active && !near && !marked) || (s.pathNodes.size > 0 && !marked && !near)
          return {
            ...data, hidden: hiddenNode, color: dim ? s.dim : data.color, label: dim ? '' : s.altLabels.get(id) ?? data.label, labelAngle: s.angles.get(id),
            highlighted: marked, forceLabel: marked || (!!active && near), zIndex: marked ? 3 : near ? 2 : 0,
            // the money flow is a diagram of few, spaced records: draw them larger so labels fit at overview
            size: data.size * (marked ? 1.25 : 1) * (s.mode === 'money' ? 1.2 : 1),
          }
        },
        edgeReducer: (id, data) => {
          const s = state.current
          const a = view.source(id), b = view.target(id)
          const active = s.hovered || s.selected.at(-1)
          const home = active ? s.orbit.get(active) ?? active : null
          const inPath = s.pathEdges.has(id) || (data.meta && (data.members as string[]).some((m) => s.pathEdges.has(m)))
          const orbitTouched = !!home && (data.orbitA === home || data.orbitB === home)
          const touches = !!active && (a === active || b === active || orbitTouched)
          // machine-inferred associations outnumber recorded relationships; they appear on selection unless asked for
          const machine = data.relationType === 'inferred_association'
          const famRel: Record<string, string> = { money: 'transferred_to', comms: 'called', records: 'accused_in', identity: 'same_as', association: 'relative_of', ownership: 'owns' }
          const layerOk = data.meta ? (data.families as string[]).some((f) => matchesLayer(famRel[f] ?? 'owns', s.layer)) : matchesLayer(data.relationType, s.layer)
          // aggregated links give way to their member records when one of their orbits is in focus
          const show = s.mode === 'money'
            ? inPath || touches || s.allEdges
            : data.meta
            ? layerOk && s.allEdges && !orbitTouched && !inPath
            : data.crossOrbit
              ? layerOk && (s.pathEdges.has(id) || orbitTouched)
              : layerOk && (inPath || touches || (s.allEdges && (!machine || s.inferred)))
          void a
          const dim = (!!active && !touches && !inPath) || (s.pathEdges.size > 0 && !inPath)
          return {
            ...data, hidden: !show, color: inPath ? s.text : dim ? (s.theme === 'light' ? '#A0A8AF' : '#68737D') : data.color, size: inPath ? Math.max(2, data.size * 1.6) : data.size,
            label: inPath || touches ? data.label : '', forceLabel: inPath || touches, zIndex: inPath ? 2 : touches ? 1 : 0,
          }
        },
        defaultDrawNodeLabel: (ctx, node, settings) => {
          if (!node.label) return
          const text = String(node.label)
          ctx.font = `${settings.labelWeight} ${settings.labelSize}px ${settings.labelFont}`
          const w = ctx.measureText(text).width
          const h = settings.labelSize + 6
          const angle = (node as unknown as { labelAngle?: number }).labelAngle
          let x: number, y: number
          if (angle === undefined || angle === null) {
            x = node.x - w / 2
            y = node.y + node.size + 4
          } else {
            // records on an orbit are labelled outward along the ray from their owner, so neighbours fan apart
            const sx = Math.cos(angle), sy = -Math.sin(angle)  // graph y points up, screen y points down
            const ax = node.x + sx * (node.size + 5), ay = node.y + sy * (node.size + 5)
            x = Math.abs(sx) < 0.3 ? ax - w / 2 : sx >= 0 ? ax : ax - w
            y = ay - h / 2 + sy * (h / 2)
          }
          ctx.globalAlpha = 0.86
          ctx.fillStyle = state.current.surface
          ctx.fillRect(x - 4, y, w + 8, h)
          ctx.globalAlpha = 1
          ctx.fillStyle = state.current.text
          ctx.fillText(text, x, y + settings.labelSize + 1)
        },
        defaultDrawNodeHover: (ctx, node, settings) => {
          const id = (node as unknown as { key?: string }).key
          const full = id && graph.hasNode(id) ? String(graph.getNodeAttribute(id, 'fullLabel') ?? node.label ?? '') : String(node.label ?? '')
          const kind = id && graph.hasNode(id) ? TYPE_LABELS[graph.getNodeAttribute(id, 'entityType')] ?? graph.getNodeAttribute(id, 'entityType') : ''
          ctx.font = `500 ${settings.labelSize + 1}px ${settings.labelFont}`
          const w1 = ctx.measureText(full).width
          ctx.font = `400 ${settings.labelSize - 1}px ${settings.labelFont}`
          const w2 = ctx.measureText(String(kind)).width
          const w = Math.max(w1, w2) + 16
          const x = node.x + node.size + 6, y = node.y - 20
          ctx.fillStyle = state.current.surface
          ctx.strokeStyle = state.current.muted
          ctx.lineWidth = 1
          ctx.fillRect(x, y, w, 40)
          ctx.strokeRect(x + 0.5, y + 0.5, w - 1, 39)
          ctx.fillStyle = state.current.text
          ctx.font = `500 ${settings.labelSize + 1}px ${settings.labelFont}`
          ctx.fillText(full, x + 8, y + 17)
          ctx.fillStyle = state.current.muted
          ctx.font = `400 ${settings.labelSize - 1}px ${settings.labelFont}`
          ctx.fillText(String(kind), x + 8, y + 32)
          ctx.strokeStyle = state.current.text
          ctx.lineWidth = 1.5
          ctx.beginPath()
          ctx.arc(node.x, node.y, node.size + 3, 0, Math.PI * 2)
          ctx.stroke()
        },
      })
    } catch {
      setFailure('Graph rendering needs WebGL. Enable it in your browser, or use the record list.')
      setListOpen(true)
      return
    }
    renderer.current = sigma
    const drawGroups = () => {
      const canvas = groupCanvas.current, container = el.current
      if (!canvas || !container) return
      const width = container.clientWidth, h = container.clientHeight, ratio = window.devicePixelRatio || 1
      if (canvas.width !== Math.round(width * ratio) || canvas.height !== Math.round(h * ratio)) { canvas.width = Math.round(width * ratio); canvas.height = Math.round(h * ratio) }
      const ctx = canvas.getContext('2d')
      if (!ctx) return
      ctx.setTransform(ratio, 0, 0, ratio, 0, 0)
      ctx.clearRect(0, 0, width, h)
      const css = getComputedStyle(document.documentElement)
      for (const group of groups.current) {
        const start = sigma.graphToViewport({ x: group.x, y: group.y })
        const end = sigma.graphToViewport({ x: group.x + group.width, y: group.y - group.height })
        ctx.fillStyle = css.getPropertyValue('--panel').trim()
        ctx.globalAlpha = 0.55
        ctx.fillRect(start.x, start.y, end.x - start.x, end.y - start.y)
        ctx.globalAlpha = 1
        ctx.strokeStyle = css.getPropertyValue('--line').trim()
        ctx.lineWidth = 1
        ctx.strokeRect(start.x + 0.5, start.y + 0.5, end.x - start.x, end.y - start.y)
        ctx.font = `500 ${compact ? 9 : 11}px Public Sans Variable, sans-serif`
        ctx.fillStyle = css.getPropertyValue('--muted').trim()
        ctx.fillText(`${group.label}  ·  ${group.count}`, start.x + 10, start.y + 18)
      }
    }
    sigma.on('afterRender', drawGroups)
    sigma.on('clickNode', ({ node, event }) => actions.current.choose(node, 'shiftKey' in event.original && (event.original.shiftKey || event.original.ctrlKey || event.original.metaKey)))
    sigma.on('clickStage', () => actions.current.choose(null))
    sigma.on('doubleClickNode', ({ node, preventSigmaDefault }) => { preventSigmaDefault(); void actions.current.expand(node) })
    sigma.on('rightClickNode', ({ node, event }) => { event.original.preventDefault(); callbacks.current.onOpen?.(node) })
    sigma.on('clickEdge', ({ edge }) => {
      const d = view.getEdgeAttributes(edge)
      if (d.meta) {
        const ids = d.members as string[]
        setMsg(`${nodeLabel(view.source(edge))} → ${nodeLabel(view.target(edge))} · ${d.label}. Drawn as one link; select either side to see the ${ids.length} record(s) behind it.`)
        state.current.pathEdges = new Set(ids)
        state.current.pathNodes = new Set(ids.flatMap((m) => (view.hasEdge(m) ? [view.source(m), view.target(m)] : [])))
      } else {
        setMsg(`${nodeLabel(view.source(edge))} → ${nodeLabel(view.target(edge))} · ${String(d.relationType).replaceAll('_', ' ')}${d.amount ? ` · ${inr(d.amount)}` : ''}${d.count ? ` · ${d.count} records` : ''}${d.evidence ? ` · evidence: ${d.evidence}` : ''}${d.status ? ` · ${d.status}` : ''}`)
        state.current.pathEdges = new Set([edge])
        state.current.pathNodes = new Set()
      }
      sigma.refresh()
    })
    sigma.on('enterNode', ({ node }) => { state.current.hovered = node; refocus(); if (el.current) el.current.style.cursor = 'pointer'; sigma.refresh() })
    sigma.on('leaveNode', () => { state.current.hovered = null; refocus(); if (el.current) el.current.style.cursor = 'grab'; sigma.refresh() })
    let dragged: string | null = null
    sigma.on('downNode', ({ node }) => { dragged = node; if (!sigma.getCustomBBox()) sigma.setCustomBBox(sigma.getBBox()) })
    sigma.getMouseCaptor().on('mousemovebody', (event) => {
      if (!dragged) return
      const p = sigma.viewportToGraph(event)
      view.mergeNodeAttributes(dragged, p)
      if (graph.hasNode(dragged)) graph.mergeNodeAttributes(dragged, p)
      event.preventSigmaDefault()
      event.original.preventDefault()
      event.original.stopPropagation()
    })
    sigma.getMouseCaptor().on('mouseup', () => { dragged = null })
    const observer = new MutationObserver(() => {
      readTheme()
      recolour()
      sigma.setSettings({ labelColor: { color: state.current.text }, edgeLabelColor: { color: state.current.muted } })
      sigma.refresh()
    })
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
    const resize = new ResizeObserver(() => sigma.resize())
    resize.observe(el.current)
    return () => {
      epoch.current++
      analyzer.current?.terminate()
      analyzer.current = null
      observer.disconnect()
      resize.disconnect()
      sigma.kill()
      renderer.current = null
    }
    // Event callbacks read current props through refs without rebuilding the renderer.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graph, view, compact])

  useImperativeHandle(ref, () => ({ add, fit, clear, highlight }))

  // ------------------------------------------------------------------ paths
  const findPath = async () => {
    const [a, b] = selected.slice(-2)
    if (!a || !b) return
    const version = epoch.current
    highlight([], [])
    setBusy(true)
    const names = (ids: string[]) => ids.map(nodeLabel).join(' → ')
    try {
      if (caseBounded) {
        const { investigation } = await import('../investigation')
        const result = await investigation.path(a, b)
        if (version !== epoch.current) return
        highlight(result.nodes.map((n) => n.id), result.edges.map((e) => e.id))
        setMsg(result.nodes.length ? result.nodes.map((n) => n.title).join(' → ') : result.reason)
      } else if (pathMode === 'maxflow') {
        const r = maxMoneyFlow(graph, a, b)
        if (!r || !r.value) setMsg('No money can be traced from the first selected account to the second through the loaded transfers. Select the source first.')
        else {
          const nodes = new Set<string>([a, b])
          r.edges.forEach((e) => { nodes.add(graph.source(e)); nodes.add(graph.target(e)) })
          highlight([...nodes], r.edges)
          setMsg(`Up to ${inr(r.value)} could have moved from ${nodeLabel(a)} to ${nodeLabel(b)} along ${r.paths} augmenting path(s) (Edmonds–Karp). The bottleneck is ${r.cut.length} transfer record(s). Capacity is what each pair of accounts actually exchanged; this bounds the flow, it does not prove it.`)
        }
      } else if (pathMode === 'alternatives') {
        const routes = kShortestPaths(graph, a, b, 3)
        if (!routes.length) setMsg('No route between these records in the loaded network.')
        else {
          highlight([...new Set(routes.flatMap((r) => r.nodes))], [...new Set(routes.flatMap((r) => r.edges))])
          setMsg(routes.map((r, i) => `Route ${i + 1} (${r.edges.length} steps): ${names(r.nodes)}`).join('  ·  '))
        }
      } else {
        const local = visiblePath(graph, a, b, { directed: pathMode !== 'connection', relations: pathMode === 'money' ? new Set(['transferred_to']) : undefined })
        if (local) {
          highlight(local.nodes, local.edges)
          setMsg(`${local.edges.length} step(s): ${names(local.nodes)}`)
        } else if (pathMode !== 'connection') setMsg(`No ${pathMode === 'money' ? 'transfer' : 'directed'} path from the first selected record to the second in the loaded network.`)
        else {
          const result = await api.path(a, b)
          if (version !== epoch.current) return
          add(result.nodes.map((n) => ({ ...n, count: n.count ?? undefined })), result.edges)
          highlight(result.nodes.map((n) => n.id), result.edges.map((e) => e.id))
          setMsg(result.nodes.length ? `${result.hops} step(s): ${result.nodes.map((n) => n.label).join(' → ')}` : 'No connection found in the available records.')
        }
      }
    } catch (e) {
      if (version === epoch.current) setMsg((e as Error).message)
    } finally {
      if (version === epoch.current) setBusy(false)
    }
  }

  // ------------------------------------------------------------------ derived view data
  void revision
  const counts = new Map<Family, { total: number; shown: number }>()
  graph.forEachNode((id, a) => {
    const f = familyOf(a.entityType)
    const c = counts.get(f) ?? { total: 0, shown: 0 }
    c.total++
    if (state.current.visible.has(id)) c.shown++
    counts.set(f, c)
  })
  const types = [...new Set(graph.mapNodes((_id, a) => a.entityType as string))].sort((x, y) => (TYPE_LABELS[x] || x).localeCompare(TYPE_LABELS[y] || y))
  const records = graph.mapNodes((id, a) => ({ id, label: String(a.fullLabel ?? a.label), type: String(a.entityType) }))
    .filter((n) => (!filter || n.type === filter) && n.label.toLowerCase().includes(query.toLowerCase()))
    .sort((x, y) => x.label.localeCompare(y.label))
    .slice(0, 400)
  const setModeTo = (next: LayoutMode) => {
    setMsg('')
    if (next !== 'money') setFlow(null)
    if (next === 'communities' && !report) { runAnalysis(true); setAnalysisOpen(true); return }
    state.current.mode = next
    state.current.root = selected.at(-1) || graph.findNode((_id, a) => a.seed) || graph.nodes()[0] || ''
    setMode(next)
    layout()
  }
  const toggleFamily = (f: Family) => {
    const next = new Set(hidden)
    if (next.has(f)) next.delete(f)
    else next.add(f)
    state.current.hidden = next
    setHidden(next)
    layout()
  }
  const remaining = Math.max(0, eligible - state.current.visible.size)
  const modeHint = LAYOUTS.find((l) => l.id === mode)?.hint ?? ''
  const filtered = !!state.current.subset || mode === 'neighborhood' || !!filter || layer !== 'all' || hidden.size > 0

  return (
    <div className={`network-canvas ${compact ? 'compact' : ''}`} style={{ height }} aria-label="Connection graph">
      <canvas ref={groupCanvas} className="network-group-layer" aria-hidden="true" />
      <div ref={el} className="sigma-container" aria-label="Interactive network; use the record list for keyboard selection" />
      <div className="network-toolbar">
        <div className="network-count">
          <Icon icon="graph" size={14} />
          <span>{state.current.visible.size} of {graph.order} records</span>
          <span className="muted">· {graph.size} links{state.current.stats?.aggregated ? ` · ${state.current.stats.members} drawn as ${state.current.stats.aggregated} combined` : ''}</span>
          {!compact && <span className="muted network-mode-hint" title={modeHint}>· {state.current.note ? `${state.current.note} · ` : ''}{modeHint}</span>}
        </div>
        <div className="network-actions">
          {!compact && (
            <>
              <select aria-label="Network layout" value={mode} onChange={(e) => setModeTo(e.target.value as LayoutMode)}>
                {LAYOUTS.map((l) => <option key={l.id} value={l.id}>{l.label}</option>)}
              </select>
              <Button small minimal icon="layout-hierarchy" active={analysisOpen} onClick={() => { setAnalysisOpen(!analysisOpen); if (!report && !analyzing) runAnalysis() }}>Analyze</Button>
            </>
          )}
          <Button small minimal icon="list" active={listOpen} aria-label="Toggle record list" title="Record list and search" onClick={() => setListOpen(!listOpen)} />
          <Button small minimal icon="layout-auto" aria-label="Rearrange network" title="Rearrange" onClick={layout} disabled={!graph.order} />
          <Button small minimal icon="zoom-to-fit" aria-label="Fit network" title="Fit to view" onClick={fit} />
        </div>
      </div>
      {!compact && (
        <div className="network-filterbar">
          <select aria-label="Relationship layer" value={layer} onChange={(e) => { const next = e.target.value as RelationshipLayer; state.current.layer = next; setLayer(next); layout() }}>
            <option value="all">All relationships</option>
            <option value="money">Money and accounts</option>
            <option value="communications">Calls and devices</option>
            <option value="assets">Property, vehicles, companies</option>
            <option value="records">Case and identity records</option>
          </select>
          <select aria-label="Filter graph by record type" value={filter} onChange={(e) => { setFilter(e.target.value); state.current.filter = e.target.value; layout() }}>
            <option value="">All record types</option>
            {types.map((t) => <option key={t} value={t}>{TYPE_LABELS[t] || t}</option>)}
          </select>
          <Button small minimal icon={allEdges ? 'eye-open' : 'select'} active={!allEdges} onClick={() => { state.current.allEdges = !allEdges; setAllEdges(!allEdges); renderer.current?.refresh() }}>
            {allEdges ? 'Recorded links shown' : 'Links on selection'}
          </Button>
          <details className="graph-view-options">
            <summary>View options<Icon icon="chevron-down" size={10} /></summary>
            <div>
              <div className="display-toggles">
                <Button small minimal icon="group-objects" active={grouping} onClick={() => { state.current.grouping = !grouping; state.current.expanded = new Set(); setGrouping(!grouping); layout() }}>Group similar records</Button>
                <Button small minimal icon="link" active={inferred} onClick={() => { state.current.inferred = !inferred; setInferred(!inferred); renderer.current?.refresh() }}>Show inferred links</Button>
              </div>
              <label>Records on canvas
                <select aria-label="Records on canvas" value={limit} onChange={(e) => { const next = Number(e.target.value); state.current.limit = next; setLimit(next); layout() }}>
                  <option value={40}>40 · focused</option><option value={90}>90 · balanced</option><option value={160}>160 · wide</option><option value={1000000}>All loaded records</option>
                </select>
              </label>
              <label>Spacing
                <select aria-label="Graph spacing" value={spacing} onChange={(e) => { const next = Number(e.target.value); state.current.spacing = next; setSpacing(next); layout() }}>
                  <option value={1}>Comfortable</option><option value={1.4}>Wide</option><option value={1.9}>Extra wide</option>
                </select>
              </label>
              <label>Neighbourhood depth
                <select aria-label="Neighborhood depth" value={depth} onChange={(e) => { const next = Number(e.target.value); state.current.depth = next; setDepth(next); if (state.current.mode === 'neighborhood') layout() }}>
                  <option value={1}>1 step</option><option value={2}>2 steps</option><option value={3}>3 steps</option>
                </select>
              </label>
              <label>Path method
                <select aria-label="Path method" value={pathMode} onChange={(e) => setPathMode(e.target.value)}>
                  {PATHS.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
                </select>
              </label>
              <p>Depth and paths explore records already loaded. They never widen your case permissions.</p>
              <p>{modeHint}</p>
            </div>
          </details>
        </div>
      )}
      {analysisOpen && (
        <NetworkAnalysis
          report={report} busy={analyzing} error={analysisError} resolution={resolution} onResolution={setResolution}
          onRun={() => runAnalysis()} onClose={() => setAnalysisOpen(false)} label={nodeLabel}
          onShow={(nodes, edges = []) => {
            const s = state.current
            s.subset = new Set(nodes); s.filter = ''; s.layer = 'all'; s.pathNodes = new Set(); s.pathEdges = new Set(edges); s.selected = []
            setSelected([]); setFilter(''); setLayer('all'); setAnalysisOpen(false)
            layout()
            setMsg(`Showing ${nodes.length} record(s) from the analysis. Reset view returns to the whole network.`)
          }}
        />
      )}
      {!compact && filtered && <button className="network-reset" onClick={resetView}><Icon icon="reset" size={11} />Reset view</button>}
      {mode === 'money' && flow && (
        <div className="flow-overlay">
          <FlowDiagram trace={flow} byParty={false} onOpen={(id) => callbacks.current.onOpen?.(id)} />
          <p className="muted small">Each bar is a person, company or account; each transfer between two of them has its own lane, so flows never merge. Bar height and lane width are proportional to the amount. Hover a bar to isolate its flows; click it for the dossier.</p>
        </div>
      )}
      {failure && <div className="graph-msg" role="alert">{failure}</div>}
      {msg && <div className="graph-msg" role="status"><span>{msg}</span><Button minimal small icon="cross" aria-label="Dismiss graph message" onClick={() => { setMsg(''); state.current.pathEdges = new Set(); state.current.pathNodes = new Set(); renderer.current?.refresh() }} /></div>}
      {listOpen && (
        <div className="network-records">
          <input aria-label="Find a record in this graph" placeholder="Find a record…" value={query} onChange={(e) => setQuery(e.target.value)} />
          <div className="record-list" aria-label="Graph records">
            {records.map((r) => (
              <button key={r.id} aria-pressed={selected.includes(r.id)} onClick={() => choose(r.id, true)}>
                <img alt="" src={iconUri(r.type, typeColour(r.type, state.current.theme))} />
                <span>{r.label}<small>{TYPE_LABELS[r.type] || r.type}{!state.current.visible.has(r.id) ? ' · not on canvas' : ''}</small></span>
                {selected.includes(r.id) && <Icon icon="tick" size={12} />}
              </button>
            ))}
            {!records.length && <p className="muted">No matching records.</p>}
          </div>
        </div>
      )}
      {!!selected.length && (
        <div className="network-selection">
          <strong>{selected.length} selected</strong>
          {selected.at(-1)?.startsWith('group:')
            ? <Button small minimal icon="ungroup-objects" onClick={() => void expand(selected.at(-1)!)}>Open group</Button>
            : <Button small minimal icon="document-open" onClick={() => onOpen?.(selected.at(-1)!)} disabled={!onOpen}>Inspect</Button>}
          {!compact && (
            <>
              <Button small minimal icon="search-around" loading={busy} onClick={() => void expand(selected.at(-1)!)}>{caseBounded ? 'Open record' : 'Expand'}</Button>
              <Button small minimal icon="flows" disabled={selected.length < 2 || busy} onClick={findPath} title={PATHS.find((p) => p.id === pathMode)?.label}>Find path</Button>
              <Button small minimal icon="eye-off" title="Remove from this view only" onClick={() => {
                epoch.current++
                selected.forEach((id) => { if (graph.hasNode(id)) graph.dropNode(id) })
                choose(null); highlight([], []); setRevision((n) => n + 1); setBusy(false); layout()
              }}>Hide</Button>
            </>
          )}
          <Button small minimal icon="cross" aria-label="Clear graph selection" onClick={() => choose(null)} />
        </div>
      )}
      <div className="network-zoom">
        <ButtonGroup vertical>
          <Button small minimal icon="plus" aria-label="Zoom in" onClick={() => renderer.current?.getCamera().animatedZoom({ duration: 180 })} />
          <Button small minimal icon="minus" aria-label="Zoom out" onClick={() => renderer.current?.getCamera().animatedUnzoom({ duration: 180 })} />
          <Button small minimal icon="label" active={labels} aria-label="Toggle graph labels" onClick={() => { renderer.current?.setSetting('renderLabels', !labels); setLabels(!labels) }} />
        </ButtonGroup>
      </div>
      <div className="network-footer">
        <div className="network-key" role="group" aria-label="Record families; select to hide or show">
          {LEGEND.filter((f) => counts.get(f)?.total).map((f) => (
            <button key={f} className={hidden.has(f) ? 'off' : ''} aria-pressed={!hidden.has(f)} onClick={() => toggleFamily(f)} title={hidden.has(f) ? `Show ${FAMILY_LABEL[f]}` : `Hide ${FAMILY_LABEL[f]}`}>
              <i style={{ background: familyColour(f, state.current.theme) }} />
              {FAMILY_LABEL[f]}
              <span className="muted">{counts.get(f)!.shown}/{counts.get(f)!.total}</span>
            </button>
          ))}
        </div>
        <span className="network-hint">
          {remaining ? `${remaining} more record(s) available: raise “Records on canvas” or select one from the list. ` : ''}
          {compact ? 'Select a record to focus its connections.' : 'Hover or select to focus · Shift-click to select a pair · Double-click to expand · Right-click for the dossier'}
        </span>
      </div>
    </div>
  )
})
export default GraphCanvas

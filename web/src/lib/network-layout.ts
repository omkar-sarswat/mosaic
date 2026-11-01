import type { MultiDirectedGraph } from 'graphology'
import { familyOf, relFamily, type Family, type RelFamily } from './graph-style.ts'

export type LayoutMode = 'structure' | 'money' | 'types' | 'communities' | 'neighborhood' | 'force'
export type RelationshipLayer = 'all' | 'money' | 'communications' | 'assets' | 'records'
export type GroupBox = { label: string; count: number; x: number; y: number; width: number; height: number }
export const TYPE_LABELS: Record<string, string> = { Person: 'People', Organisation: 'Organisations', BankAccount: 'Bank accounts', CryptoWallet: 'Crypto wallets', Phone: 'Phones', Device: 'Devices', Property: 'Properties', Vehicle: 'Vehicles', Incident: 'Case records', Location: 'Locations', Case: 'Cases', Firearm: 'Firearms', Tender: 'Tenders', Document: 'Documents', CourtCase: 'Court cases' }
const TYPE_ORDER = ['Person', 'Organisation', 'BankAccount', 'CryptoWallet', 'Property', 'Vehicle', 'Phone', 'Device', 'Incident', 'Firearm', 'Case', 'Location']
const LAYER_FAMILIES: Record<Exclude<RelationshipLayer, 'all'>, Set<RelFamily>> = {
  money: new Set(['money', 'ownership']),
  communications: new Set(['comms']),
  assets: new Set(['ownership']),
  records: new Set(['records', 'identity']),
}
const ACCOUNT_LINKS = new Set(['holds_account', 'signatory_of'])
export function matchesLayer(type: string, layer: RelationshipLayer) {
  if (layer === 'all') return true
  if (layer === 'money' && relFamily(type) === 'ownership') return ACCOUNT_LINKS.has(type)
  if (layer === 'assets' && ACCOUNT_LINKS.has(type)) return false
  return LAYER_FAMILIES[layer].has(relFamily(type))
}

export function neighborhood(graph: MultiDirectedGraph, root: string, depth: number, layer: RelationshipLayer = 'all') {
  const found = new Set<string>()
  if (!graph.hasNode(root)) return found
  found.add(root)
  let frontier = [root]
  for (let hop = 0; hop < depth; hop++) {
    const next: string[] = []
    frontier.forEach((node) => graph.forEachEdge(node, (_edge, attrs, a, b) => {
      if (!matchesLayer(attrs.relationType, layer)) return
      const other = a === node ? b : a
      if (!found.has(other)) { found.add(other); next.push(other) }
    }))
    frontier = next
  }
  return found
}

export function chooseVisible(graph: MultiDirectedGraph, options: { limit: number; type: string; layer: RelationshipLayer; root?: string; depth?: number; pinned?: Set<string>; subset?: Set<string> }) {
  let candidates = graph.nodes()
  if (options.subset) candidates = candidates.filter((id) => options.subset!.has(id))
  if (options.layer !== 'all') {
    const endpoints = new Set<string>()
    graph.forEachEdge((_id, attrs, a, b) => { if (matchesLayer(attrs.relationType, options.layer)) { endpoints.add(a); endpoints.add(b) } })
    candidates = candidates.filter((id) => endpoints.has(id))
  }
  if (options.type) candidates = candidates.filter((id) => graph.getNodeAttribute(id, 'entityType') === options.type)
  if (options.root) { const neighbors = neighborhood(graph, options.root, options.depth ?? 1, options.layer); candidates = candidates.filter((id) => neighbors.has(id)) }
  const groups = new Map<string, string[]>()
  candidates.forEach((id) => { const type = graph.getNodeAttribute(id, 'entityType'); if (!groups.has(type)) groups.set(type, []); groups.get(type)!.push(id) })
  groups.forEach((nodes) => nodes.sort((a, b) => Number(!!graph.getNodeAttribute(b, 'seed')) - Number(!!graph.getNodeAttribute(a, 'seed')) || graph.degree(b) - graph.degree(a) || a.localeCompare(b)))
  const visible = new Set<string>(candidates.filter((id) => options.pinned?.has(id)))
  const lists = [...groups.values()]
  // Round-robin retains every available entity type before allocating more detail to larger types.
  for (let index = 0; visible.size < options.limit && index < candidates.length; index++) {
    for (const list of lists) { if (visible.size >= options.limit) break; if (list[index]) visible.add(list[index]) }
  }
  return { visible, eligible: candidates.length }
}

export function arrangeGroups(graph: MultiDirectedGraph, visible: Set<string>, mode: LayoutMode, communities: Record<string, number> = {}, aspect = 1.6, spacing = 1): GroupBox[] {
  const grouped = new Map<string, string[]>()
  visible.forEach((id) => {
    const type = graph.getNodeAttribute(id, 'entityType') as string
    const key = mode === 'communities' ? `Community ${(communities[id] ?? 0) + 1}` : TYPE_LABELS[type] || type
    if (!grouped.has(key)) grouped.set(key, [])
    grouped.get(key)!.push(id)
  })
  const items = [...grouped].sort(([a], [b]) => {
    if (mode === 'communities') return a.localeCompare(b, undefined, { numeric: true })
    const labels = TYPE_ORDER.map((type) => TYPE_LABELS[type] || type)
    const ai = labels.indexOf(a), bi = labels.indexOf(b)
    return (ai < 0 ? 100 : ai) - (bi < 0 ? 100 : bi) || a.localeCompare(b)
  }).map(([label, ids]) => {
    ids.sort((a, b) => String(graph.getNodeAttribute(a, 'label')).localeCompare(String(graph.getNodeAttribute(b, 'label'))))
    const columns = Math.min(5, Math.max(2, Math.ceil(Math.sqrt(ids.length * 1.4))))
    return { label, ids, columns, width: columns * 155 * spacing + 36, height: Math.ceil(ids.length / columns) * 110 * spacing + 85 }
  })
  const totalArea = items.reduce((sum, group) => sum + (group.width + 32) * (group.height + 32), 0)
  const target = Math.max(...items.map((item) => item.width), Math.sqrt(totalArea * Math.max(0.7, aspect)))
  const boxes: GroupBox[] = []
  let x = 0, y = 0, rowHeight = 0
  items.forEach((item) => {
    if (x && x + item.width > target) { x = 0; y += rowHeight + 32; rowHeight = 0 }
    boxes.push({ label: item.label, count: item.ids.length, x, y: -y, width: item.width, height: item.height })
    item.ids.forEach((id, index) => graph.mergeNodeAttributes(id, { x: x + 18 + (index % item.columns + 0.5) * 155 * spacing, y: -(y + 85 + Math.floor(index / item.columns) * 110 * spacing) }))
    x += item.width + 32; rowHeight = Math.max(rowHeight, item.height)
  })
  // Hidden records must not expand Sigma's viewport extent.
  graph.forEachNode((id) => { if (!visible.has(id)) graph.mergeNodeAttributes(id, { x: 0, y: 0 }) })
  return boxes
}

/** People-first budget for the structure and money views: seeds and pinned records first, then the
 *  best-connected people and organisations, each bringing its own records along, so what is on the
 *  canvas is a set of complete small pictures rather than a scatter of unrelated records. */
export function chooseFocus(graph: MultiDirectedGraph, options: { limit: number; type: string; layer: RelationshipLayer; root?: string; depth?: number;
  pinned?: Set<string>; subset?: Set<string>; hidden?: Set<Family>; money?: boolean }) {
  let candidates = graph.nodes()
  if (options.subset) candidates = candidates.filter((id) => options.subset!.has(id))
  if (options.layer !== 'all' || options.money) {
    const endpoints = new Set<string>()
    graph.forEachEdge((_id, attrs, a, b) => {
      const ok = options.money ? attrs.relationType === 'transferred_to' : matchesLayer(attrs.relationType, options.layer)
      if (ok) { endpoints.add(a); endpoints.add(b) }
    })
    candidates = candidates.filter((id) => endpoints.has(id))
  }
  if (options.type) candidates = candidates.filter((id) => graph.getNodeAttribute(id, 'entityType') === options.type)
  if (options.hidden?.size) candidates = candidates.filter((id) => !options.hidden!.has(familyOf(String(graph.getNodeAttribute(id, 'entityType')))))
  if (options.root) { const near = neighborhood(graph, options.root, options.depth ?? 1, options.layer); candidates = candidates.filter((id) => near.has(id)) }
  const pool = new Set(candidates)
  const isActor = (id: string) => familyOf(String(graph.getNodeAttribute(id, 'entityType'))) === 'actor'
  const weight = (id: string) => options.money
    ? graph.reduceEdges(id, (sum, _e, attrs) => sum + (attrs.relationType === 'transferred_to' ? Number(attrs.amount) || 1 : 0), 0)
    : graph.degree(id)
  const order = [...candidates].sort((a, b) =>
    Number(!!graph.getNodeAttribute(b, 'seed')) - Number(!!graph.getNodeAttribute(a, 'seed'))
    || (options.money ? 0 : Number(isActor(b)) - Number(isActor(a)))
    || weight(b) - weight(a) || a.localeCompare(b))
  const visible = new Set<string>([...(options.pinned ?? [])].filter((id) => pool.has(id)))
  for (const id of order) {
    if (visible.size >= options.limit) break
    visible.add(id)
    if (!options.money && isActor(id)) {
      const own = graph.neighbors(id).filter((n) => pool.has(n) && !isActor(n) && !visible.has(n)).sort((a, b) => graph.degree(b) - graph.degree(a) || a.localeCompare(b))
      for (const n of own.slice(0, 12)) { if (visible.size >= options.limit) break; visible.add(n) }
    }
  }
  return { visible, eligible: candidates.length }
}

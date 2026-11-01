import { useMemo, useState } from 'react'
import type { Trace } from '../api'
import { inr } from '../lib/format'
import { greedyOrder } from '../lib/graph-layouts'
import { moneyColours } from '../lib/palette'

// A deterministic Sankey for traced money. Columns are hops in the direction money moved; inside a
// column, bars are ordered by the barycentre of the bars they exchange money with (four sweeps), which
// keeps crossings low. Every link has its own slot on each bar it touches (Sankey port stacking), so
// lines never meet at a point; widths are proportional to value. Each bar's slot is at least one label
// high, so labels never overlap. Money that returns to an earlier column is drawn as a dashed arc.

type N = { id: string; name: string; kind: string; flagged: boolean; holder: string | null; accounts: number; layer: number; value: number; y: number; h: number; slot: number }
type L = { source: string; target: string; value: number; count: number; back: boolean; sy: number; ty: number; w: number }

const KIND: Record<string, string> = new Proxy({} as Record<string, string>, { get: (_, k) => (moneyColours() as Record<string, string>)[String(k)] })
const COL_W = 12, LABEL_W = 210, MIN_SLOT = 30, GAP = 10, TOP = 34, COL_STEP = 190

export default function FlowDiagram({ trace, byParty, width = 980, onOpen }: { trace: Trace; byParty: boolean; width?: number; onOpen?: (holder: string) => void }) {
  const [hover, setHover] = useState<string | null>(null)
  const model = useMemo(() => build(trace, byParty, width), [trace, byParty, width])
  if (!model.nodes.length) return <p className="muted">No transfers above the threshold in this direction.</p>
  const { nodes, links, columns, height, colX, ky, fullWidth } = model
  const chars = Math.floor((COL_STEP - COL_W - 14) / 6.3)
  const byId = new Map(nodes.map((n) => [n.id, n]))
  const active = hover ? new Set([hover, ...links.filter((l) => l.source === hover || l.target === hover).flatMap((l) => [l.source, l.target])]) : null
  return (
    <div className="flow-scroll">
    <svg className="flow-diagram" viewBox={`0 0 ${fullWidth} ${height}`} width={fullWidth} height={height} role="img" aria-label="Traced money, by hop">
      {columns.map((c, i) => (
        <text key={i} x={colX(i)} y={16} textAnchor="start" className="flow-col">{c}</text>
      ))}
      <g fill="none">
        {links.map((l, i) => {
          const s = byId.get(l.source)!, t = byId.get(l.target)!
          const dim = active && !(active.has(l.source) && active.has(l.target))
          if (l.back) {
            const x0 = colX(s.layer) + COL_W / 2, x1 = colX(t.layer) + COL_W / 2, y0 = s.y + s.h, y1 = t.y + t.h
            const dip = Math.max(y0, y1) + 40
            return <path key={i} d={`M${x0},${y0} C${x0},${dip} ${x1},${dip} ${x1},${y1}`} stroke={moneyColours().foreign} strokeOpacity={dim ? 0.15 : 0.85} strokeWidth={2} strokeDasharray="4 3">
              <title>{`${s.name} → ${t.name} (returns upstream): ${inr(l.value)}, ${l.count} transfer(s)`}</title>
            </path>
          }
          const x0 = colX(s.layer) + COL_W, x1 = colX(t.layer), xm = (x0 + x1) / 2
          const y0 = s.y + l.sy + l.w / 2, y1 = t.y + l.ty + l.w / 2
          return <path key={i} d={`M${x0},${y0} C${xm},${y0} ${xm},${y1} ${x1},${y1}`} stroke={t.kind === 'foreign' ? KIND.foreign : t.kind === 'cash' ? KIND.cash : KIND.account}
            strokeOpacity={dim ? 0.12 : hover ? 0.8 : 0.65} strokeWidth={Math.max(1.5, l.w)}>
            <title>{`${s.name} → ${t.name}: ${inr(l.value)} in ${l.count} transfer(s)`}</title>
          </path>
        })}
      </g>
      {nodes.map((n) => {
        const dim = active && !active.has(n.id)
        const right = true  // labels always to the right; the right margin is reserved for the last column
        const lx = right ? colX(n.layer) + COL_W + 6 : colX(n.layer) - 6
        const cy = n.y + n.h / 2
        return (
          <g key={n.id} opacity={dim ? 0.25 : 1} style={{ cursor: n.holder ? 'pointer' : 'default' }}
            onMouseEnter={() => setHover(n.id)} onMouseLeave={() => setHover(null)} onClick={() => n.holder && onOpen?.(n.holder)}>
            <rect x={colX(n.layer)} y={n.y} width={COL_W} height={Math.max(2, n.h)} rx={2} fill={KIND[n.kind] ?? KIND.account}
              stroke={n.flagged ? moneyColours().flagged : 'none'} strokeWidth={n.flagged ? 2 : 0} />
            <text x={lx} y={cy - 2} textAnchor={right ? 'start' : 'end'} className="flow-label">
              {trim(n.name + (n.accounts > 1 ? ` · ${n.accounts} a/c` : ''), n.layer === columns.length - 1 ? 32 : chars)}
            </text>
            <text x={lx} y={cy + 11} textAnchor={right ? 'start' : 'end'} className="flow-sub">
              {inr(n.value)}{n.flagged ? ' · flagged' : ''}
            </text>
          </g>
        )
      })}
      <text x={fullWidth - 4} y={height - 4} textAnchor="end" className="flow-sub">Bar height ∝ value · 1 px ≈ {inr(1 / Math.max(ky, 1e-12))}</text>
    </svg>
    </div>
  )
}

const trim = (s: string, n: number) => (s.length > n ? s.slice(0, n - 1) + '…' : s)

function build(trace: Trace, byParty: boolean, width: number) {
  // 1. nodes: accounts, or their holders (parties)
  const partyOf = new Map<string, string>()
  const nodes = new Map<string, N>()
  for (const n of trace.nodes) {
    const pid = byParty && n.holder && n.id !== 'CASH' && n.kind === 'account' ? `party:${n.holder}` : n.id
    partyOf.set(n.id, pid)
    const name = n.id === 'CASH' ? 'Cash withdrawn' : `${n.holder_name || n.label}${n.kind === 'foreign' ? ' (abroad)' : ''}`
    const prev = nodes.get(pid)
    if (prev) {
      prev.accounts += 1
      prev.flagged ||= n.alerts.length > 0
      prev.layer = Math.min(prev.layer, n.hop)
    } else nodes.set(pid, { id: pid, name, kind: pid.startsWith('party:') ? 'party' : n.kind, flagged: n.alerts.length > 0, holder: n.holder, accounts: 1, layer: n.hop, value: 0, y: 0, h: 0, slot: 0 })
  }
  // 2. links summed per pair of parties
  const sums = new Map<string, L>()
  for (const l of trace.links) {
    const s = partyOf.get(l.source) ?? l.source, t = partyOf.get(l.target) ?? l.target
    if (s === t || !nodes.has(s) || !nodes.has(t)) continue
    const key = `${s}>${t}`
    const m = sums.get(key) ?? { source: s, target: t, value: 0, count: 0, back: false, sy: 0, ty: 0, w: 0 }
    m.value += l.value
    m.count += l.count
    sums.set(key, m)
  }
  const links = [...sums.values()]
  // columns from the flows themselves (links run in the direction money moved, for both trace directions):
  // Eades-Lin-Smyth order breaks cycles, then longest-path layering; records with no link are left out
  const linked = new Set(links.flatMap((l) => [l.source, l.target]))
  for (const id of [...nodes.keys()]) if (!linked.has(id)) nodes.delete(id)
  const order = greedyOrder([...nodes.keys()].sort(), links.map((l) => [l.source, l.target] as [string, string]))
  const rank = new Map(order.map((n, i) => [n, i]))
  for (const n of nodes.values()) n.layer = 0
  for (const l of links) l.back = rank.get(l.source)! > rank.get(l.target)!
  for (const id of order) for (const l of links) if (!l.back && l.source === id) {
    const t = nodes.get(l.target)!
    t.layer = Math.max(t.layer, nodes.get(id)!.layer + 1)
  }
  // compact empty columns
  const used = [...new Set([...nodes.values()].map((n) => n.layer))].sort((a, b) => a - b)
  for (const n of nodes.values()) n.layer = used.indexOf(n.layer)
  // 3. value of each bar
  const inV = new Map<string, number>(), outV = new Map<string, number>()
  for (const l of links) if (!l.back) { outV.set(l.source, (outV.get(l.source) ?? 0) + l.value); inV.set(l.target, (inV.get(l.target) ?? 0) + l.value) }
  for (const n of nodes.values()) n.value = Math.max(inV.get(n.id) ?? 0, outV.get(n.id) ?? 0)
  const cols: N[][] = used.map((_, i) => [...nodes.values()].filter((n) => n.layer === i).sort((a, b) => b.value - a.value || a.id.localeCompare(b.id)))
  // 4. vertical scale: the busiest column fills ~460 px of bars
  const ky = Math.min(...cols.map((c) => (460 - (c.length - 1) * GAP) / Math.max(1, c.reduce((s, n) => s + n.value, 0))).filter((x) => x > 0), 1e9)
  for (const n of nodes.values()) { n.h = Math.max(3, n.value * ky); n.slot = Math.max(n.h, MIN_SLOT) }
  // 5. barycentre ordering, 4 sweeps
  const pos = () => { for (const c of cols) { let y = 0; for (const n of c) { n.y = y + (n.slot - n.h) / 2; y += n.slot + GAP } } }
  pos()
  const centre = (n: N) => n.y + n.h / 2
  for (let sweep = 0; sweep < 4; sweep++) {
    const forward = sweep % 2 === 0
    const order = forward ? cols.slice(1) : cols.slice(0, -1).reverse()
    for (const c of order) {
      const bary = (n: N) => {
        const ls = links.filter((l) => !l.back && (forward ? l.target === n.id : l.source === n.id))
        const tot = ls.reduce((s, l) => s + l.value, 0)
        return tot ? ls.reduce((s, l) => s + centre(nodes.get(forward ? l.source : l.target)!) * l.value, 0) / tot : centre(n)
      }
      const keys = new Map(c.map((n) => [n.id, bary(n)]))
      c.sort((a, b) => keys.get(a.id)! - keys.get(b.id)! || a.id.localeCompare(b.id))
      pos()
    }
  }
  // centre columns vertically
  const colH = cols.map((c) => c.reduce((s, n) => s + n.slot, 0) + Math.max(0, c.length - 1) * GAP)
  const H = Math.max(...colH)
  cols.forEach((c, i) => { const off = TOP + (H - colH[i]) / 2; for (const n of c) n.y += off })
  // 6. port stacking: outgoing slots ordered by target position, incoming by source position
  for (const n of nodes.values()) {
    let o = 0
    for (const l of links.filter((l) => !l.back && l.source === n.id).sort((a, b) => centre(nodes.get(a.target)!) - centre(nodes.get(b.target)!))) { l.w = l.value * ky; l.sy = o; o += l.w }
    let i = 0
    for (const l of links.filter((l) => !l.back && l.target === n.id).sort((a, b) => centre(nodes.get(a.source)!) - centre(nodes.get(b.source)!))) { l.ty = i; i += l.value * ky }
  }
  // a fixed step per column (labels need ~190 px); wide traces scroll sideways instead of overlapping
  const nCols = cols.length
  const step = Math.max(COL_STEP, nCols > 1 ? (width - LABEL_W - COL_W - 8) / (nCols - 1) : COL_STEP)
  const colX = (i: number) => 8 + i * step
  const fullWidth = Math.max(width, 8 + (nCols - 1) * step + COL_W + LABEL_W)
  const names = cols.map((_, i) => (i === 0 ? (trace.direction === 'in' ? 'Origins' : 'Start') : i === nCols - 1 ? 'End points' : `Hop ${i}`))
  const backDip = links.some((l) => l.back) ? 60 : 0
  return { nodes: [...nodes.values()], links, columns: names, height: TOP + H + 24 + backDip, colX, ky, fullWidth, omitted: trace.nodes.length - nodes.size }
}

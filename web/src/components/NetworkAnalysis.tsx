import { Icon, Spinner } from '@blueprintjs/core'
import { Button } from './Button'
import type { NetworkReport } from '../lib/network-analysis'

type Props = {
  report: NetworkReport | null; busy: boolean; error: string; resolution: number
  onResolution: (value: number) => void; onRun: () => void; onClose: () => void
  onShow: (nodes: string[], edges?: string[]) => void; label: (id: string) => string
}

// Structure of the loaded network. Every section says what the measure is and what it is not:
// shape of the records, never a judgement about a person.
export default function NetworkAnalysis({ report, busy, error, resolution, onResolution, onRun, onClose, onShow, label }: Props) {
  const communities = report
    ? Object.entries(Object.entries(report.communities).reduce<Record<string, string[]>>((groups, [id, c]) => { (groups[c] ??= []).push(id); return groups }, {}))
      .sort((a, b) => b[1].length - a[1].length)
    : []
  return (
    <aside className="network-analysis" aria-label="Network structure analysis">
      <div className="analysis-heading">
        <div><h3>Network structure</h3><p>All loaded records, not only those on the canvas</p></div>
        <Button small minimal icon="cross" aria-label="Close network analysis" onClick={onClose} />
      </div>
      <div className="analysis-controls">
        <label>Group size
          <select value={resolution} onChange={(e) => onResolution(Number(e.target.value))}>
            <option value={0.5}>Broader groups</option><option value={1}>Standard</option><option value={1.5}>Finer groups</option><option value={2}>Finest groups</option>
          </select>
        </label>
        <Button small icon="refresh" loading={busy} onClick={onRun}>Run analysis</Button>
      </div>
      {busy && <div className="analysis-status" role="status"><Spinner size={16} />Calculating network structure…</div>}
      {error && <p className="err" role="alert">{error}</p>}
      {report && !busy && (
        <>
          <div className="analysis-metrics">
            <div><b>{report.records}</b><span>Records</span></div>
            <div><b>{report.relationships}</b><span>Links</span></div>
            <div><b>{report.components.length}</b><span>Separate parts</span></div>
            <div><b>{report.communityCount}</b><span>Groups</span></div>
          </div>
          <details open>
            <summary>Groups <span>{report.communityCount}</span></summary>
            <p>Records more connected to each other than to the rest of the network. A starting point for questions, not a finding: groups change with what is loaded.</p>
            {communities.slice(0, 14).map(([c, nodes]) => (
              <button className="analysis-result" key={c} onClick={() => onShow(nodes)}><span>Group {Number(c) + 1}<small>{nodes.slice(0, 2).map(label).join(', ')}{nodes.length > 2 ? '…' : ''}</small></span><span>{nodes.length}<Icon icon="arrow-right" size={11} /></span></button>
            ))}
          </details>
          <details>
            <summary>Go-betweens <span>{report.brokers.length}</span></summary>
            <p>Records that sit on the routes between otherwise separate people, such as an intermediary or a shared account. Strongest first. A position in this picture, not a measure of involvement.</p>
            {report.brokers.map((b) => (
              <button className="analysis-result" key={b.id} onClick={() => onShow([b.id])}><span>{label(b.id)}</span><span><Icon icon="arrow-right" size={11} /></span></button>
            ))}
            {!report.brokers.length && <p>No record sits between others.</p>}
          </details>
          <details>
            <summary>Records holding it together <span>{report.articulation.length}</span></summary>
            <p>Remove one of these and the network splits apart. Often a shared account, handset or intermediary.</p>
            {report.articulation.slice(0, 20).map((id) => (
              <button className="analysis-result" key={id} onClick={() => onShow([id])}><span>{label(id)}</span><Icon icon="arrow-right" size={11} /></button>
            ))}
            {!report.articulation.length && <p>No single record holds the network together.</p>}
          </details>
          <details>
            <summary>Tightest group <span>{report.core.members.length}</span></summary>
            <p>The largest set of records in which each is linked to at least {report.core.max} others in the set.</p>
            {report.core.members.length > 0
              ? <button className="analysis-result" onClick={() => onShow(report.core.members)}><span>Show the tightest group<small>{report.core.members.slice(0, 3).map(label).join(', ')}{report.core.members.length > 3 ? '…' : ''}</small></span><span>{report.core.members.length}<Icon icon="arrow-right" size={11} /></span></button>
              : <p>No group is tighter than a simple chain.</p>}
          </details>
          <details>
            <summary>Separate parts <span>{report.components.length}</span></summary>
            <p>Parts of the network with no link between them in the loaded records.</p>
            {report.components.slice(0, 20).map((nodes, i) => (
              <button className="analysis-result" key={i} onClick={() => onShow(nodes)}><span>Part {i + 1}</span><span>{nodes.length}<Icon icon="arrow-right" size={11} /></span></button>
            ))}
          </details>
          <details>
            <summary>Loops <span>{report.cycles.length}</span></summary>
            <p>Records that link back to each other in a circle, following the direction of the links. A loop of mixed links is not proof that money went round; the round-tripping pattern checks the dates.</p>
            {report.cycles.map((nodes, i) => (
              <button className="analysis-result" key={i} onClick={() => onShow(nodes)}><span>Loop {i + 1}</span><span>{nodes.length}<Icon icon="arrow-right" size={11} /></span></button>
            ))}
            {!report.cycles.length && <p>No loops.</p>}
          </details>
          <details>
            <summary>Only links between parts <span>{report.bridges.length}</span></summary>
            <p>Pairs whose link is the only route between two parts of the network.</p>
            {report.bridges.slice(0, 30).map((b, i) => (
              <button className="analysis-result bridge-result" key={i} onClick={() => onShow([b.source, b.target], b.edges)}><span>{label(b.source)}<small>↔ {label(b.target)}</small></span><span>{b.edges.length}</span></button>
            ))}
            {!report.bridges.length && <p>None.</p>}
          </details>
          <details>
            <summary>Method</summary>
            <p>Missing records can change every result. None of these measures infers intent, guilt or risk, and none is stored.</p>
            <p>For specialists: groups by Louvain modularity split into connected parts ({report.modularity === null ? 'modularity n/a' : `modularity ${report.modularity.toFixed(3)}`}); go-betweens by betweenness; holding records are articulation points; the tightest group is the {report.core.max}-core. Density {(report.density * 100).toFixed(2)}%.</p>
          </details>
        </>
      )}
    </aside>
  )
}

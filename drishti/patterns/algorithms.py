"""Graph, temporal and statistical algorithms used by the pattern detectors.

Each one is a published, well-understood method, implemented small and dependency-free so a
reviewer can read it end to end:

  * union-find with path halving                     (Tarjan 1975)
  * strongly connected components, iterative         (Tarjan 1972)
  * time-respecting cycle enumeration                (Kumar & Calders, "2SCENT", VLDB 2018 - bounded DFS form)
  * Louvain modularity communities + connectivity    (Blondel et al. 2008; refinement step after
    refinement as in Leiden                            Traag, Waltman & van Eck 2019)
  * camouflage-resistant dense block (Fraudar)       (Hooi et al., KDD 2016)
  * robust z-score (median / MAD)                    (Iglewicz & Hoaglin 1993)
  * one-sided CUSUM change detection                 (Page 1954)
  * IDF-weighted Jaccard similarity                  (Sparck Jones 1972 weighting)
  * great-circle distance                            (haversine)
"""

from __future__ import annotations

import heapq
import math
import random
from collections import defaultdict
from collections.abc import Hashable, Iterable
from datetime import datetime, timedelta
from statistics import median
from typing import Any


# ---------------------------------------------------------------------------- union-find
class UnionFind:
    def __init__(self, items: Iterable[Hashable] = ()) -> None:
        self.parent: dict[Hashable, Hashable] = {}
        for x in items:
            self.parent[x] = x

    def find(self, x: Hashable) -> Hashable:
        p = self.parent.setdefault(x, x)
        while p != x:
            gp = self.parent.get(p, p)
            self.parent[x] = gp
            x, p = p, gp
        return x

    def union(self, a: Hashable, b: Hashable) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            if str(ra) < str(rb):
                ra, rb = rb, ra
            self.parent[ra] = rb

    def groups(self) -> list[set]:
        out: dict[Hashable, set] = defaultdict(set)
        for x in list(self.parent):
            out[self.find(x)].add(x)
        return list(out.values())


# ---------------------------------------------------------------------------- SCC
def strongly_connected(adj: dict[Hashable, Iterable[Hashable]]) -> list[list[Hashable]]:
    """Tarjan's algorithm without recursion. Returns components with more than one node or a self-loop."""
    index: dict[Hashable, int] = {}
    low: dict[Hashable, int] = {}
    on: set[Hashable] = set()
    stack: list[Hashable] = []
    out: list[list[Hashable]] = []
    counter = 0
    nodes = set(adj) | {v for vs in adj.values() for v in vs}
    for root in sorted(nodes, key=str):
        if root in index:
            continue
        work = [(root, iter(sorted(adj.get(root, ()), key=str)))]
        index[root] = low[root] = counter
        counter += 1
        stack.append(root)
        on.add(root)
        while work:
            node, it = work[-1]
            advanced = False
            for nxt in it:
                if nxt not in index:
                    index[nxt] = low[nxt] = counter
                    counter += 1
                    stack.append(nxt)
                    on.add(nxt)
                    work.append((nxt, iter(sorted(adj.get(nxt, ()), key=str))))
                    advanced = True
                    break
                if nxt in on:
                    low[node] = min(low[node], index[nxt])
            if advanced:
                continue
            work.pop()
            if work:
                low[work[-1][0]] = min(low[work[-1][0]], low[node])
            if low[node] == index[node]:
                comp = []
                while True:
                    w = stack.pop()
                    on.discard(w)
                    comp.append(w)
                    if w == node:
                        break
                if len(comp) > 1 or node in set(adj.get(node, ())):
                    out.append(comp)
    return out


# ---------------------------------------------------------------------------- temporal cycles
def temporal_cycles(edges: Iterable[tuple[str, str, str, float, str]], *, max_len: int = 5, window: timedelta = timedelta(days=60),
                    min_amount: float = 0.0, retain: float = 0.5, limit: int = 500) -> list[list[tuple[str, str, str, float, str]]]:
    """Cycles whose edges happen in strictly increasing time, within `window`, where each hop carries at
    least `retain` of the previous hop's amount. A static cycle (A pays B in May, B paid A in January) is
    not a round trip; a time-respecting one is. Edges are (src, dst, ts_iso, amount, txn_id)."""
    out_e: dict[str, list[tuple[str, str, str, float, str]]] = defaultdict(list)
    for e in edges:
        if e[3] >= min_amount and e[0] != e[1]:
            out_e[e[0]].append(e)
    for v in out_e.values():
        v.sort(key=lambda e: e[2])
    found: list[list[tuple]] = []
    seen: set[tuple] = set()
    for start in sorted(out_e):
        for first in out_e[start]:
            t0 = datetime.fromisoformat(first[2])
            stack = [(first[1], [first])]
            while stack and len(found) < limit:
                node, path = stack.pop()
                last = path[-1]
                for e in out_e.get(node, ()):
                    if e[2] <= last[2] or e[3] < retain * last[3]:
                        continue
                    if datetime.fromisoformat(e[2]) - t0 > window:
                        break
                    if e[1] == start:
                        key = tuple(sorted({x[0] for x in path + [e]}))
                        if key not in seen:
                            seen.add(key)
                            found.append(path + [e])
                        continue
                    if len(path) < max_len - 1 and e[1] not in {x[0] for x in path} and e[1] > start:
                        stack.append((e[1], path + [e]))
    return found


# ---------------------------------------------------------------------------- Louvain (+ connectivity refinement)
def louvain(nodes: Iterable[Hashable], edges: Iterable[tuple[Hashable, Hashable, float]], *, resolution: float = 1.0,
            seed: int = 7, max_levels: int = 10) -> dict[Hashable, int]:
    """Modularity communities. After each run every community is split into its connected parts,
    the guarantee Leiden adds over plain Louvain (no badly connected communities)."""
    rng = random.Random(seed)
    w: dict[Hashable, dict[Hashable, float]] = defaultdict(lambda: defaultdict(float))
    for a, b, x in edges:
        if a == b:
            w[a][a] += x
        else:
            w[a][b] += x
            w[b][a] += x
    node_list = list(dict.fromkeys(list(nodes) + list(w)))
    member = {n: n for n in node_list}  # original node -> current super-node
    graph = {n: dict(w[n]) for n in node_list}
    for _ in range(max_levels):
        comm = {n: n for n in graph}
        k = {n: sum(graph[n].values()) + graph[n].get(n, 0.0) for n in graph}
        m2 = sum(k.values()) or 1.0
        tot = defaultdict(float)
        for n in graph:
            tot[comm[n]] += k[n]
        improved, moved = True, False
        while improved:
            improved = False
            order = list(graph)
            rng.shuffle(order)
            for n in order:
                c0 = comm[n]
                links = defaultdict(float)
                for nb, x in graph[n].items():
                    if nb != n:
                        links[comm[nb]] += x
                tot[c0] -= k[n]
                best, gain = c0, links.get(c0, 0.0) - resolution * tot[c0] * k[n] / m2
                for c, x in links.items():
                    g = x - resolution * tot[c] * k[n] / m2
                    if g > gain + 1e-12:
                        best, gain = c, g
                comm[n] = best
                tot[best] += k[n]
                if best != c0:
                    improved = moved = True
        if not moved:
            break
        new_graph: dict[Hashable, dict[Hashable, float]] = defaultdict(lambda: defaultdict(float))
        for n, nbs in graph.items():
            for nb, x in nbs.items():
                new_graph[comm[n]][comm[nb]] += x
        for orig, sup in member.items():
            member[orig] = comm[sup]
        graph = {n: dict(v) for n, v in new_graph.items()}
    # Leiden-style guarantee: a community must be connected in the original graph
    labels: dict[Hashable, int] = {}
    groups: dict[Hashable, list] = defaultdict(list)
    for n, c in member.items():
        groups[c].append(n)
    nxt = 0
    for members in groups.values():
        ms = set(members)
        uf = UnionFind(ms)
        for a in ms:
            for b in w.get(a, {}):
                if b in ms:
                    uf.union(a, b)
        for part in uf.groups():
            for n in part:
                labels[n] = nxt
            nxt += 1
    return labels


# ---------------------------------------------------------------------------- Fraudar
def fraudar(edges: Iterable[tuple[Hashable, Hashable, float]], *, min_rows: int = 2, min_cols: int = 2) -> dict[str, Any]:
    """Densest bipartite block under column weights 1/log(degree + 5) (Hooi et al. 2016).

    Greedy peeling removes, one at a time, the node whose edges carry least weight inside the current
    block, and returns the block with the best average weight per node. Down-weighting popular columns
    makes the score resistant to camouflage: adding edges to ordinary, high-degree accounts does not
    hide a dense block of edges among rarely-used ones."""
    rows: dict[Hashable, dict[Hashable, float]] = defaultdict(dict)
    cols: dict[Hashable, dict[Hashable, float]] = defaultdict(dict)
    for u, v, x in edges:
        rows[("r", u)][("c", v)] = x
        cols[("c", v)][("r", u)] = x
    if not rows:
        return {"rows": [], "cols": [], "score": 0.0}
    cw = {c: 1.0 / math.log(len(nb) + 5) for c, nb in cols.items()}
    adj: dict[Hashable, dict[Hashable, float]] = {}
    for r, nb in rows.items():
        adj[r] = {c: cw[c] for c in nb}
    for c, nb in cols.items():
        adj[c] = {r: cw[c] for r in nb}
    prio = {n: sum(nb.values()) for n, nb in adj.items()}
    total = sum(prio[r] for r in rows)
    alive = set(adj)
    heap = [(p, str(n), n) for n, p in prio.items()]
    heapq.heapify(heap)
    best_score, best_removed = total / len(alive), 0
    removed: list[Hashable] = []
    while len(alive) > 2:
        p, _, n = heapq.heappop(heap)
        if n not in alive or abs(p - prio[n]) > 1e-12:
            continue
        alive.discard(n)
        removed.append(n)
        total -= prio[n]
        for nb, x in adj[n].items():
            if nb in alive:
                prio[nb] -= x
                heapq.heappush(heap, (prio[nb], str(nb), nb))
        score = total / len(alive)
        if score > best_score:
            best_score, best_removed = score, len(removed)
    gone = set(removed[:best_removed])
    block = set(adj) - gone
    r = [n[1] for n in block if n[0] == "r"]
    c = [n[1] for n in block if n[0] == "c"]
    if len(r) < min_rows or len(c) < min_cols:
        return {"rows": [], "cols": [], "score": 0.0}
    return {"rows": sorted(r, key=str), "cols": sorted(c, key=str), "score": round(best_score, 4)}


# ---------------------------------------------------------------------------- statistics
def robust_z(x: float, history: list[float]) -> tuple[float, float, float]:
    """(median, MAD, z) with the 1.4826 consistency constant; a floor of 10% of the median stops a
    perfectly steady history from turning any change into an infinite z."""
    if not history:
        return 0.0, 0.0, 0.0
    med = median(history)
    mad = median([abs(h - med) for h in history])
    scale = max(1.4826 * mad, 0.10 * abs(med), 1e-9)
    return med, mad, (x - med) / scale


def page_cusum(values: list[float], *, target: float, k: float, h: float) -> tuple[int | None, list[float]]:
    """One-sided upper CUSUM: S_t = max(0, S_{t-1} + x_t - target - k); alarm when S_t > h."""
    s, path, alarm = 0.0, [], None
    for i, x in enumerate(values):
        s = max(0.0, s + x - target - k)
        path.append(round(s, 3))
        if alarm is None and s > h:
            alarm = i
    return alarm, path


def idf_weights(degree: dict[Hashable, int]) -> dict[Hashable, float]:
    return {n: 1.0 / math.log(2 + d) for n, d in degree.items()}


def weighted_jaccard(a: set, b: set, weight: dict[Hashable, float]) -> float:
    inter = sum(weight.get(x, 1.0) for x in a & b)
    union = sum(weight.get(x, 1.0) for x in a | b)
    return inter / union if union else 0.0


def circular_std_hours(hours: list[float]) -> float:
    if not hours:
        return 0.0
    angles = [h / 24 * 2 * math.pi for h in hours]
    c = sum(math.cos(a) for a in angles) / len(angles)
    s = sum(math.sin(a) for a in angles) / len(angles)
    r = min(1.0, math.hypot(c, s))
    return math.sqrt(-2 * math.log(max(r, 1e-12))) * 24 / (2 * math.pi)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(a))

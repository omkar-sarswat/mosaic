"""Policy-aware graph building: auto-graph, shortest path, broker (betweenness) scores.

Design doc 16.5C ("the graph builds itself") with the 5.2 safeguards applied at every hop:

* nodes the user may not see are never returned; they are counted per type and reason;
* people reached only through non-evidentiary links (relatives, neighbours, co-residents)
  and not already in the case scope are shown as counts, not identities (BVerfG 2023);
* depth is capped by the case (1 by default; 2-3 only after supervisor approval);
* hub objects (districts, schemes, police stations) are shown but never expanded;
* resolver links that are still candidates are drawn (red) but not traversed.
"""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Any, Callable

from .guard.policy import CaseCtx, Decision
from .ontology import Ontology
from .store import Store

HUB_TYPES = {"AdminUnit", "Scheme"}
HUB_ORG_KINDS = {"police_station", "bank", "department"}
GROUP_THRESHOLD = 25
TRAVERSE = ("active", "auto", "confirmed")
DRAW = TRAVERSE + ("candidate",)


def is_hub(obj: dict[str, Any]) -> bool:
    return obj["type"] in HUB_TYPES or (obj["type"] == "Organisation" and obj["props"].get("kind") in HUB_ORG_KINDS)


class GraphBuilder:
    def __init__(self, store: Store, decide: Callable[[dict[str, Any]], Decision], case: CaseCtx | None):
        self.store = store
        self.ontology: Ontology = store.ontology
        self.decide = decide
        self.case = case
        self._decisions: dict[str, Decision] = {}

    def _allowed(self, obj: dict[str, Any]) -> Decision:
        if obj["id"] not in self._decisions:
            self._decisions[obj["id"]] = self.decide(obj)
        return self._decisions[obj["id"]]

    def neighbourhood(self, root_id: str, depth: int) -> dict[str, Any]:
        root = self.store.get_object(root_id)
        if root is None:
            raise KeyError(root_id)
        nodes: dict[str, dict[str, Any]] = {root_id: root}
        edges: dict[str, dict[str, Any]] = {}
        hidden: dict[tuple[str, str], int] = defaultdict(int)
        hops = {root_id: 0}
        frontier = [root_id]
        scope = self.case.scope if self.case else frozenset()
        for level in range(1, depth + 1):
            links = self.store.links_for(frontier, statuses=DRAW)
            by_parent_type: dict[tuple[str, str], list[tuple[dict, str]]] = defaultdict(list)
            other_ids = {l["dst"] if l["src"] in frontier else l["src"] for l in links}
            objs = self.store.get_objects(other_ids)
            for l in links:
                parent = l["src"] if l["src"] in frontier else l["dst"]
                other = l["dst"] if parent == l["src"] else l["src"]
                if other in nodes:
                    if other != parent:
                        edges[l["id"]] = l
                    continue
                obj = objs.get(other)
                if obj is None:
                    continue
                d = self._allowed(obj)
                if not d.allow:
                    hidden[(obj["type"], d.reason)] += 1
                    continue
                lt = self.ontology.links.get(l["type"])
                ot = self.ontology.objects[obj["type"]]
                # people reached only through non-evidentiary links (family, co-residence) are shown
                # as context but never expanded further unless they are in the case scope
                context_only = bool(ot.personal and lt and not lt.evidentiary and other not in scope)
                by_parent_type[(parent, obj["type"])].append((obj, "context" if context_only else l["status"]))
            new_frontier = []
            for (parent, typ), items in by_parent_type.items():
                if len(items) > GROUP_THRESHOLD and level > 1 or len(items) > GROUP_THRESHOLD * 2:
                    gid = f"group:{parent}:{typ}"
                    nodes[gid] = {"id": gid, "type": typ, "title": f"{len(items)} {typ} objects", "group": True,
                                  "count": len(items), "members": [o["id"] for o, _ in items][:500], "props": {}}
                    edges[f"{gid}:edge"] = {"id": f"{gid}:edge", "type": "grouped", "src": parent, "dst": gid,
                                            "evidence": "single", "status": "active", "sources": [], "confidence": 1.0}
                    continue
                for obj, status in items:
                    if obj["id"] in nodes:
                        continue
                    nodes[obj["id"]] = obj
                    hops[obj["id"]] = level
                    # candidate resolver links are drawn but not followed; hubs are never expanded
                    if status in TRAVERSE and not is_hub(obj):
                        new_frontier.append(obj["id"])
            for l in links:
                if l["src"] in nodes and l["dst"] in nodes:
                    edges[l["id"]] = l
            frontier = new_frontier
            if not frontier:
                break
        # edges among returned nodes that were not yet included
        ids = [n for n in nodes if not str(n).startswith("group:")]
        for l in self.store.links_for(ids, statuses=DRAW):
            if l["src"] in nodes and l["dst"] in nodes:
                edges[l["id"]] = l
        traversable = [e for e in edges.values() if e["status"] in TRAVERSE]
        scores = betweenness([n for n in nodes], [(e["src"], e["dst"]) for e in traversable])
        return {
            "root": root_id,
            "nodes": [self._node(n, hops.get(n["id"], 1), scores.get(n["id"], 0.0)) for n in nodes.values()],
            "edges": [self._edge(e) for e in edges.values()],
            "hidden": [{"type": t, "reason": r, "count": c} for (t, r), c in sorted(hidden.items())],
        }

    def _node(self, obj: dict[str, Any], hop: int, broker: float) -> dict[str, Any]:
        return {
            "id": obj["id"], "type": obj["type"], "label": obj.get("title"), "district": obj.get("district_lgd"),
            "hop": hop, "broker": round(broker, 4), "group": obj.get("group", False), "count": obj.get("count"),
            "members": obj.get("members"), "synthetic": obj.get("synthetic", False), "hub": is_hub(obj) if not obj.get("group") else False,
            "in_case": bool(self.case and obj["id"] in self.case.scope),
        }

    @staticmethod
    def _edge(e: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": e["id"], "source": e["src"], "target": e["dst"], "type": e["type"], "evidence": e["evidence"],
            "status": e["status"], "confidence": e["confidence"], "sources": e["sources"], "props": e.get("props", {}),
        }

    def shortest_path(self, a: str, b: str, max_hops: int = 6, max_nodes: int = 20000) -> dict[str, Any] | None:
        prev: dict[str, tuple[str, dict]] = {}
        seen = {a}
        q = deque([(a, 0)])
        while q and len(seen) < max_nodes:
            node, d = q.popleft()
            if node == b:
                break
            if d >= max_hops:
                continue
            links = self.store.links_for([node], statuses=TRAVERSE)
            objs = self.store.get_objects({l["dst"] if l["src"] == node else l["src"] for l in links})
            for l in links:
                other = l["dst"] if l["src"] == node else l["src"]
                if other in seen or other not in objs:
                    continue
                obj = objs[other]
                if not self._allowed(obj).allow:
                    continue
                seen.add(other)
                prev[other] = (node, l)
                if not is_hub(obj) or other == b:
                    q.append((other, d + 1))
        if b not in prev and a != b:
            return None
        path_nodes, path_edges = [b], []
        cur = b
        while cur != a:
            p, l = prev[cur]
            path_edges.append(l)
            path_nodes.append(p)
            cur = p
        path_nodes.reverse()
        path_edges.reverse()
        objs = self.store.get_objects(path_nodes)
        return {
            "nodes": [self._node(objs[n], i, 0.0) for i, n in enumerate(path_nodes)],
            "edges": [self._edge(e) for e in path_edges],
            "hops": len(path_edges),
        }


def betweenness(nodes: list[str], edges: list[tuple[str, str]]) -> dict[str, float]:
    """Brandes' algorithm, unweighted, undirected, normalised to [0, 1]."""
    adj: dict[str, set[str]] = {n: set() for n in nodes}
    for u, v in edges:
        if u in adj and v in adj and u != v:
            adj[u].add(v)
            adj[v].add(u)
    cb = dict.fromkeys(nodes, 0.0)
    for s in nodes:
        stack, pred = [], {w: [] for w in nodes}
        sigma = dict.fromkeys(nodes, 0.0)
        sigma[s] = 1.0
        dist = dict.fromkeys(nodes, -1)
        dist[s] = 0
        q = deque([s])
        while q:
            v = q.popleft()
            stack.append(v)
            for w in adj[v]:
                if dist[w] < 0:
                    dist[w] = dist[v] + 1
                    q.append(w)
                if dist[w] == dist[v] + 1:
                    sigma[w] += sigma[v]
                    pred[w].append(v)
        delta = dict.fromkeys(nodes, 0.0)
        while stack:
            w = stack.pop()
            for v in pred[w]:
                delta[v] += sigma[v] / sigma[w] * (1 + delta[w])
            if w != s:
                cb[w] += delta[w]
    n = len(nodes)
    scale = 1 / ((n - 1) * (n - 2)) if n > 2 else 1.0
    return {k: v * scale for k, v in cb.items()}

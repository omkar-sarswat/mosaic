"""Run entity resolution over the store and persist candidate links + review queue.

Routing (design doc 12.2 step 7):
  p >= 0.95         -> same_as link, status "auto"      (shown red: machine-suggested)
  r <= p < 0.95     -> review queue + link "candidate"  (not traversed until confirmed)
  p < r             -> dropped
where r is 0.70 with the hand-set parameters; adopted trained parameters carry their own r, chosen on
their training world so that sharper probabilities do not drop borderline true pairs unseen.
Merges are never destructive: records stay separate objects joined by same_as links,
so un-merging is a status change with full history.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from typing import Any

from ..config import settings
from ..store import Store, utcnow
from .matcher import Matcher, PersonRecord, clusters, pairwise_metrics


def _records(store: Store) -> list[PersonRecord]:
    persons = store.objects_of_type("Person")
    phones: dict[str, set[str]] = defaultdict(set)
    sources: dict[str, str] = {}
    for row in store.query("SELECT l.src, o.props FROM links l JOIN objects o ON o.id=l.dst WHERE l.type='uses_phone' "
                           "AND l.status IN ('active','auto','confirmed')"):
        phones[row["src"]].add(json.loads(row["props"])["number"])
    for row in store.query("SELECT object_id, source FROM provenance WHERE prop='name'"):
        sources.setdefault(row["object_id"], row["source"])
    canaries = {r["object_id"] for r in store.query("SELECT object_id FROM canaries")}
    return [
        PersonRecord.from_props(p["id"], p["props"], phones.get(p["id"], ()), sources.get(p["id"], ""))
        for p in persons
        if p["id"] not in canaries  # canaries must never be linked to real records
    ]


class _IdentityComponents:
    """Incremental cannot-link checks before accepting a machine-proposed union.

    Human-confirmed components are retained. A proposed union must not introduce a
    conflicting identifier of the same kind or reconnect a human-rejected pair.
    Identifier values stay internal; explanations disclose only the conflicting kinds.
    """

    def __init__(self, records: list[PersonRecord], rejected: set[tuple[str, str]]):
        self.parent: dict[str, str] = {}
        self.members: dict[str, set[str]] = {}
        self.identifiers: dict[str, dict[str, set[str]]] = {}
        self.forbidden: dict[str, set[str]] = defaultdict(set)
        for record in records:
            self.find(record.id)
            for value in record.ids:
                kind, _, identifier = value.partition(":")
                self.identifiers[record.id].setdefault(kind, set()).add(identifier)
        for a, b in rejected:
            self.find(a)
            self.find(b)
            self.forbidden[a].add(b)
            self.forbidden[b].add(a)

    def find(self, node: str) -> str:
        if node not in self.parent:
            self.parent[node] = node
            self.members[node] = {node}
            self.identifiers[node] = {}
        root = node
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[node] != node:
            previous = self.parent[node]
            self.parent[node] = root
            node = previous
        return root

    def conflicts(self, a: str, b: str) -> list[str]:
        ra, rb = self.find(a), self.find(b)
        ai, bi = self.identifiers[ra], self.identifiers[rb]
        kinds = sorted(k for k in ai.keys() | bi.keys() if len(ai.get(k, set()) | bi.get(k, set())) > 1)
        reasons = ["conflicting identity identifiers: " + ", ".join(kinds)] if kinds else []
        if self.forbidden[ra] & self.members[rb] or self.forbidden[rb] & self.members[ra]:
            reasons.append("human-rejected identity pair would share a component")
        return reasons

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if (len(self.members[ra]), ra) < (len(self.members[rb]), rb):
            ra, rb = rb, ra
        self.parent[rb] = ra
        self.members[ra].update(self.members.pop(rb))
        self.forbidden[ra].update(self.forbidden.pop(rb, set()))
        for kind, values in self.identifiers.pop(rb).items():
            self.identifiers[ra].setdefault(kind, set()).update(values)


def _machine_owned(row: Any) -> bool:
    """Only this resolver's suggestions may be withdrawn by its next complete run."""
    sources = json.loads(row["sources"])
    return row["origin"] == "resolver" and bool(sources) and all(s.get("source") == "RESOLVE" for s in sources)


def _reconcile(store: Store, records: list[PersonRecord], scores: list[Any], now: str) -> dict[str, int]:
    counts = {"auto_links": 0, "sent_to_review": 0, "withdrawn_links": 0, "blocked_auto_links": 0}
    # Read decisions and update links and their review items under the same lock and
    # transaction. A failure must not leave a half-reconciled identity graph.
    with store.tx() as conn:
        existing: dict[tuple[str, str], list[Any]] = defaultdict(list)
        for row in conn.execute("SELECT * FROM links WHERE type='same_as' ORDER BY id"):
            existing[tuple(sorted((row["src"], row["dst"])))].append(row)
        decided = {
            tuple(sorted((r["a"], r["b"]))): r["status"]
            for r in conn.execute("SELECT a,b,status FROM review_queue WHERE status IN ('confirmed','rejected')")
        }
        rejected = {pair for pair, status in decided.items() if status == "rejected"}
        rejected.update(pair for pair, rows in existing.items() if any(r["status"] == "rejected" for r in rows))
        components = _IdentityComponents(records, rejected)
        for pair, rows in existing.items():
            # A saved human decision is authoritative even if an older interrupted
            # review left the associated machine link in its previous state.
            if pair in decided:
                for row in rows:
                    if _machine_owned(row) and row["status"] not in ("confirmed", "rejected"):
                        conn.execute("UPDATE links SET status=?,updated_at=? WHERE id=?", (decided[pair], now, row["id"]))
                if decided[pair] == "confirmed":
                    components.union(*pair)
                continue
            if any(r["status"] == "confirmed" or (r["status"] == "auto" and not _machine_owned(r)) for r in rows):
                components.union(*pair)

        current = {(s.a, s.b) if s.a < s.b else (s.b, s.a): s for s in scores}
        for pair, rows in existing.items():
            if pair in current or pair in decided:
                continue
            for row in rows:
                if _machine_owned(row) and row["status"] in ("auto", "candidate"):
                    props = json.loads(row["props"])
                    props["resolution_state"] = {"status": "withdrawn", "at": now,
                                                 "reason": "no longer meets the current proposal criteria"}
                    conn.execute("UPDATE links SET status='withdrawn',props=?,updated_at=? WHERE id=?",
                                 (json.dumps(props), now, row["id"]))
                    conn.execute("UPDATE review_queue SET status='withdrawn' WHERE a=? AND b=? AND status IN ('pending','auto')", pair)
                    counts["withdrawn_links"] += 1

        for pair, score in sorted(current.items(), key=lambda item: (-item[1].probability, item[0])):
            rows = existing.get(pair, [])
            if pair in decided or any(r["status"] in ("confirmed", "rejected") or not _machine_owned(r) for r in rows):
                continue  # Neither human decisions nor another source's assertions are overwritten.
            reasons = components.conflicts(*pair)
            if getattr(score, "identity_conflicts", ()):
                direct = "conflicting identity identifiers: " + ", ".join(score.identity_conflicts)
                if direct not in reasons:
                    reasons.append(direct)
            if getattr(score, "name_conflict", False):
                reasons.append("given names conflict: twins and relatives share a father, birth date and address")
            wants_auto = score.probability >= settings.auto_link_threshold
            status = "auto" if wants_auto and not reasons else "candidate"
            explanation = {"probability": round(score.probability, 4), "match_weight": round(score.match_weight, 2),
                           "features": score.explain(), "review_reasons": reasons}
            props = {"explanation": explanation, "resolution_state": {"status": status, "at": now}}
            if not rows:
                link_id = store.upsert_link("same_as", *pair, source="RESOLVE", record="splink-compatible-fs", origin="resolver",
                                            confidence=score.probability, status=status, props=props)
            else:
                link_id = rows[0]["id"]
                for row in rows:
                    merged = json.loads(row["props"]) | props
                    # Generic ingestion retains maximum confidence; recomputation must
                    # instead replace it with the current model's evidence and routing.
                    conn.execute("UPDATE links SET status=?,confidence=?,props=?,updated_at=? WHERE id=?",
                                 (status, score.probability, json.dumps(merged), now, row["id"]))
            if status == "auto":
                components.union(*pair)
                counts["auto_links"] += 1
                conn.execute("UPDATE review_queue SET status='auto',probability=?,explanation=? "
                             "WHERE a=? AND b=? AND status IN ('pending','auto','withdrawn')",
                             (score.probability, json.dumps(explanation | {"link_id": link_id}), *pair))
            else:
                counts["sent_to_review"] += 1
                counts["blocked_auto_links"] += int(wants_auto)
                rid = "review:" + hashlib.sha1(f"{pair[0]}|{pair[1]}".encode()).hexdigest()[:16]
                conn.execute(
                    "INSERT INTO review_queue(id,a,b,probability,explanation) VALUES(?,?,?,?,?) "
                    "ON CONFLICT(id) DO UPDATE SET probability=excluded.probability,explanation=excluded.explanation,status='pending' "
                    "WHERE review_queue.status IN ('pending','auto','withdrawn')",
                    (rid, *pair, score.probability, json.dumps(explanation | {"link_id": link_id})),
                )
    return counts


def run_resolution(store: Store) -> dict[str, Any]:
    from . import train

    trained = train.load(settings.matcher_params)
    records = _records(store)
    matcher = Matcher(records, params=trained)
    review_at = (train.review_threshold(settings.matcher_params) or settings.review_threshold) if trained else settings.review_threshold
    scores, prior = matcher.score_with_prior(min_probability=review_at)
    now = utcnow()
    routing = _reconcile(store, records, scores, now)

    accepted = [
        (r["src"], r["dst"])
        for r in store.query("SELECT src, dst FROM links WHERE type='same_as' AND status IN ('auto','confirmed')")
    ]
    ids = [r.id for r in records]
    cluster_of = clusters(ids, accepted)
    result: dict[str, Any] = {
        "records": len(records),
        "pairs_scored": len(scores),
        "estimated_prior": round(prior, 7),
        **routing,
        "resolved_entities": len(set(cluster_of.values())),
        "computed_at": now,
    }
    # Data-quality feedback to source owners: several records of one person inside one source.
    # Normal for FIR parties (one record per FIR); for registries that must hold one record
    # per person (ration cards, pensions) these are suspected duplicate beneficiaries.
    by_id = {r.id: r for r in records}
    dup = Counter()
    for a, b in accepted:
        if a in by_id and b in by_id and by_id[a].source and by_id[a].source == by_id[b].source:
            dup[by_id[a].source] += 1
    result["within_source_links"] = dict(dup)
    if any(r.truth_id for r in records):
        result["benchmark_auto_only"] = pairwise_metrics(records, cluster_of)
        candidates = accepted + [(r["src"], r["dst"]) for r in store.query("SELECT src, dst FROM links WHERE type='same_as' AND status='candidate'")]
        result["benchmark_if_all_reviews_confirmed"] = pairwise_metrics(records, clusters(ids, candidates))
    result["parameters"] = "trained" if trained else "hand-set"
    result["review_threshold"] = review_at
    store.set_meta("resolve_metrics", result)
    return result


def entity_cluster(store: Store, person_id: str) -> list[str]:
    """All records linked to this one by accepted same_as links (the resolved entity)."""
    seen, frontier = {person_id}, [person_id]
    while frontier:
        nxt = []
        for l in store.links_for(frontier, statuses=("auto", "confirmed")):
            if l["type"] != "same_as":
                continue
            for x in (l["src"], l["dst"]):
                if x not in seen:
                    seen.add(x)
                    nxt.append(x)
        frontier = nxt
    return sorted(seen)

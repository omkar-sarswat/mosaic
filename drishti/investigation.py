"""Case-bounded exploration. Only admitted, readable records enter analysis.

These algorithms report record relationships and quality findings, never guilt.
Every result can be reproduced from the returned source records and parameters.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict, deque
from datetime import datetime
from typing import Any

from .store import Store

DOMAINS = {
    "identity": {"Person"},
    "organisations": {"Organisation"},
    "communications": {"Phone", "Device"},
    "movement": {"Location", "Vehicle", "Shipment", "Event"},
    "documents": {"Document", "CourtCase"},
    "cyber": {"DigitalArtifact"},
    "incidents": {"Incident", "Case"},
    "assets": {"Property", "Asset", "Resource", "Hazard", "AdminUnit", "Scheme"},
    "finance": {"BankAccount", "CryptoWallet"},
}


def domain_of(type_name: str) -> str:
    return next((k for k, values in DOMAINS.items() if type_name in values), "other")


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        from datetime import timezone
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
    except ValueError:
        return None


def graph_links(store: Store, objects: dict[str, dict]) -> list[dict]:
    """Rejected/candidate/automatic identity matches cannot become factual paths."""
    return sorted((l for l in store.links_for(objects, statuses=("active", "confirmed"))
                   if l["src"] in objects and l["dst"] in objects), key=lambda l: l["id"])


def shortest_evidence_path(objects: dict[str, dict], links: list[dict], start: str,
                           end: str, max_hops: int) -> dict:
    """Stable breadth-first traversal of explicit, undirected evidence links."""
    if start not in objects or end not in objects:
        return {"nodes": [], "edges": [], "hops": None, "reason": "Record unavailable in this case"}
    adjacency: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    for edge in links:
        adjacency[edge["src"]].append((edge["dst"], edge))
        adjacency[edge["dst"]].append((edge["src"], edge))
    queue = deque([(start, 0)])
    parent: dict[str, tuple[str, dict] | None] = {start: None}
    while queue:
        current, depth = queue.popleft()
        if current == end:
            nodes, edges = [current], []
            while parent[current] is not None:
                previous, edge = parent[current]
                edges.append(edge)
                nodes.append(previous)
                current = previous
            return {"nodes": list(reversed(nodes)), "edges": list(reversed(edges)), "hops": depth,
                    "reason": "An association path is not proof of wrongdoing"}
        if depth >= max_hops:
            continue
        for other, edge in sorted(adjacency[current], key=lambda x: (x[0], x[1]["id"])):
            if other not in parent:
                parent[other] = (current, edge)
                queue.append((other, depth + 1))
    return {"nodes": [], "edges": [], "hops": None, "reason": "No recorded path within the approved depth"}


def timeline(store: Store, objects: dict[str, dict], links: list[dict]) -> list[dict]:
    """Recorded event time is separate from ingestion time; never invent dates."""
    out = []
    participants: dict[str, list[str]] = defaultdict(list)
    for edge in links:
        if edge["type"] in ("participated_in", "documented_in", "accused_in", "witness_in", "complainant_in", "victim_in"):
            participants[edge["dst"]].append(edge["src"])
    for oid, obj in objects.items():
        props = obj["props"]
        at = next((props.get(k) for k in ("occurred_at", "authored_at", "registered_on", "incorporated_on", "first_seen", "effective") if props.get(k)), None)
        if at:
            out.append({"id": oid, "at": at, "kind": props.get("kind", obj["type"]), "title": obj["title"],
                        "domain": domain_of(obj["type"]), "object_ids": [oid, *sorted(set(participants[oid]))],
                        "location": props.get("location", props.get("city")), "lat": obj.get("lat"), "lon": obj.get("lon"),
                        "accuracy_m": props.get("accuracy_m"), "source": ", ".join(sorted({p["source"] for p in store.provenance(oid)}))})
    # Import event-table rows only for subjects explicitly admitted to the case.
    people = [oid for oid, obj in objects.items() if obj["type"] == "Person"]
    vehicles = [oid for oid, obj in objects.items() if obj["type"] == "Vehicle"]
    for ids, table, field in ((people, "travel", "person_id"), (vehicles, "tollhits", "vehicle_id")):
        for offset in range(0, len(ids), 300):
            chunk = ids[offset:offset + 300]
            for raw in store.query(f"SELECT * FROM {table} WHERE {field} IN ({','.join('?' for _ in chunk)})", chunk):
                row = dict(raw)
                title = f"{row.get('from_city')} → {row.get('to_city')}" if table == "travel" else row["plaza"]
                out.append({"id": row["id"], "at": row["ts"], "kind": "travel" if table == "travel" else "toll record",
                            "title": title, "domain": "movement", "object_ids": [row[field]], "source": row["source"],
                            "location": row.get("to_city", row.get("plaza")), "lat": row.get("to_lat", row.get("lat")),
                            "lon": row.get("to_lon", row.get("lon")), "accuracy_m": None})
    return sorted(out, key=lambda e: (e["at"], e["id"]), reverse=True)


def findings(store: Store, objects: dict[str, dict], links: list[dict]) -> list[dict]:
    """Versioned evidence-quality checks; no behavioural/person risk scores."""
    out: list[dict] = []

    def add(rule: str, title: str, ids: list[str], detail: str, limitation: str, measurements: dict):
        ids = sorted(set(ids))
        fingerprint = hashlib.sha256(json.dumps([rule, ids, measurements], sort_keys=True).encode()).hexdigest()[:20]
        out.append({"id": fingerprint, "rule": rule, "version": "1.0", "title": title,
                    "object_ids": ids, "detail": detail, "limitation": limitation, "measurements": measurements,
                    "kind": "evidence_quality", "status": "needs_review"})

    groups: dict[tuple[str, str], list[str]] = defaultdict(list)
    for oid, obj in objects.items():
        props = obj["props"]
        for field in ("email", "registered_address", "registration_no", "reference"):
            value = props.get(field)
            if isinstance(value, str) and value.strip():
                groups[(field, " ".join(value.casefold().split()))].append(oid)
        start, end = parse_time(props.get("occurred_at")), parse_time(props.get("ended_at"))
        if start and end and end < start:
            add("REVERSED_INTERVAL", "Event ends before it starts", [oid],
                "The recorded event interval is inconsistent.", "Verify source timezone and transcription before correcting the record.",
                {"start": props["occurred_at"], "end": props["ended_at"]})
        if obj["type"] == "Document" and props.get("sha256"):
            digest = hashlib.sha256(props.get("content", "").encode()).hexdigest()
            if digest != props["sha256"]:
                add("DOCUMENT_HASH_MISMATCH", "Document content differs from its recorded hash", [oid],
                    "SHA-256 of the stored text does not equal the recorded digest.",
                    "Text normalization can change a digest. Verify the original exhibit and acquisition method.",
                    {"algorithm": "SHA-256", "actual": digest, "recorded": props["sha256"]})
        if not store.provenance(oid):
            add("MISSING_PROVENANCE", "Record has no property provenance", [oid],
                "No source assertions are recorded for this object.", "A missing source is a coverage gap, not evidence of deception.", {})
    for (field, _), ids in sorted(groups.items()):
        if len(ids) > 1:
            add("SHARED_REFERENCE", f"{len(ids)} records share {field.replace('_', ' ')}", ids,
                "Exact normalized field agreement links these records for review.",
                "Shared addresses and contact details can be legitimate. This does not establish common control or identity.",
                {"field": field, "records": len(ids), "normalization": "casefold + whitespace"})
    # Return only contradictions explicitly present in separate source assertions.
    by_pair: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for edge in links:
        if edge["type"] == "same_as" and edge["status"] == "confirmed":
            a, b = objects[edge["src"]], objects[edge["dst"]]
            for field in ("dob", "birth_year", "registration_no", "incorporated_on"):
                x, y = a["props"].get(field), b["props"].get(field)
                if x and y and x != y:
                    add("CONFLICTING_ASSERTIONS", f"Linked records disagree on {field.replace('_', ' ')}", [a["id"], b["id"]],
                        "A confirmed identity link contains conflicting source values.",
                        "Do not overwrite either assertion until a reviewer resolves the discrepancy.", {"field": field, "values": [x, y]})
        if edge["type"] == "participated_in":
            by_pair[(edge["src"], "events")].append(edge)
    for (subject, _), edges in by_pair.items():
        events = [objects[e["dst"]] for e in edges if objects[e["dst"]]["type"] == "Event"]
        for i, event in enumerate(events):
            for other in events[i + 1:]:
                a, b = parse_time(event["props"].get("occurred_at")), parse_time(other["props"].get("occurred_at"))
                la, lb = event["props"].get("location"), other["props"].get("location")
                if a and b and a == b and la and lb and la != lb:
                    add("SIMULTANEOUS_LOCATIONS", "Source records disagree on event location", [subject, event["id"], other["id"]],
                        "The same admitted subject is associated with two differently named places at the same recorded time.",
                        "Names may be aliases, timestamps may be rounded, and participation does not prove physical presence.",
                        {"at": a.isoformat(), "locations": sorted([la, lb])})
    return sorted(out, key=lambda f: (f["rule"], f["id"]))


def coverage(objects: dict[str, dict]) -> dict[str, int]:
    counts = Counter(domain_of(o["type"]) for o in objects.values())
    return {domain: counts.get(domain, 0) for domain in DOMAINS}

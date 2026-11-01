"""Retention: purge case-bound data when its retention period ends, and destroy data obtained
under an order that is set aside (Telecommunications interception rules, 2024).

What a purge removes for a case past `retention_until` (and not under legal hold):
  * objects obtained for the case (`objects.origin_case`), their links, provenance and index rows;
  * exhibits in the evidence locker (file overwritten, then unlinked; custody records "destroyed");
  * the case scope, leads and export files.
What survives: the case row (closed, purged_at set), the audit chain, the custody chains, and a
tombstone in `purge_log` holding counts and the SHA-256 of the manifest of what was destroyed,
so the destruction itself can be proven without keeping the data.
Source-system records (CCTNS, bank, telecom originals) are not the platform's to delete.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .evidence import destroy_evidence_file
from .guard.audit import AuditLog
from .store import Store, utcnow


def due_cases(store: Store, now: str | None = None) -> list[dict[str, Any]]:
    now = now or datetime.now(timezone.utc).date().isoformat()
    return [dict(r) for r in store.query(
        "SELECT * FROM cases WHERE status='closed' AND purged_at IS NULL AND legal_hold=0 AND retention_until IS NOT NULL AND retention_until<=?", (now,))]


def status(store: Store) -> dict[str, Any]:
    return {
        "due": due_cases(store),
        "held": [dict(r) for r in store.query("SELECT id, title, hold_reason, retention_until FROM cases WHERE legal_hold=1")],
        "scheduled": [dict(r) for r in store.query("SELECT id, title, retention_until FROM cases WHERE status='closed' AND purged_at IS NULL AND legal_hold=0 ORDER BY retention_until")],
        "purged": [dict(r) | {"counts": json.loads(r["counts"])} for r in store.query("SELECT * FROM purge_log ORDER BY id DESC LIMIT 50")],
    }


def _delete_media(store: Store, where: str, params: tuple) -> int:
    """Photographs and probe images: the face rows, their embeddings and the stored file."""
    rows = [dict(r) for r in store.query(f"SELECT id, kind, path FROM media WHERE {where}", params)]
    with store.tx() as conn:
        for m in rows:
            conn.execute("DELETE FROM faces WHERE media_id=?", (m["id"],))
            conn.execute("DELETE FROM media WHERE id=?", (m["id"],))
    for m in rows:  # probe files are exhibits and go through destroy_evidence_file
        if m["kind"] == "photo" and m["path"] and Path(m["path"]).exists() and not store.query("SELECT 1 FROM media WHERE path=?", (m["path"],)):
            os.remove(m["path"])
    return len(rows)


def _delete_objects(store: Store, ids: list[str]) -> int:
    n = 0
    for i in range(0, len(ids), 300):
        chunk = ids[i:i + 300]
        _delete_media(store, f"object_id IN ({','.join('?' * len(chunk))})", tuple(chunk))
    for i in range(0, len(ids), 300):
        chunk = ids[i:i + 300]
        q = ",".join("?" * len(chunk))
        with store.tx() as conn:
            conn.execute(f"DELETE FROM links WHERE src IN ({q}) OR dst IN ({q})", (*chunk, *chunk))
            conn.execute(f"DELETE FROM provenance WHERE object_id IN ({q})", chunk)
            conn.execute(f"DELETE FROM identifiers WHERE object_id IN ({q})", chunk)
            store.drop_search_rows(chunk)
            conn.execute(f"DELETE FROM case_objects WHERE object_id IN ({q})", chunk)
            n += conn.execute(f"DELETE FROM objects WHERE id IN ({q})", chunk).rowcount
    return n


def _manifest(store: Store, objects: list[str], evidence: list[dict]) -> str:
    rows = []
    for oid in sorted(objects):
        r = store.query("SELECT props FROM objects WHERE id=?", (oid,))
        rows.append(f"object {oid} {hashlib.sha256((r[0]['props'] if r else '').encode()).hexdigest()}")
    rows += [f"exhibit {e['id']} {e['sha256']}" for e in evidence]
    return hashlib.sha256("\n".join(rows).encode()).hexdigest()


def purge_case(store: Store, case_id: str, actor: str, reason: str) -> dict[str, Any]:
    case = store.query("SELECT * FROM cases WHERE id=?", (case_id,))
    if not case:
        raise ValueError("no such case")
    c = case[0]
    if c["legal_hold"]:
        raise PermissionError(f"case is under legal hold: {c['hold_reason']}")
    if c["status"] != "closed":
        raise PermissionError("only closed cases can be purged")
    objs = [r["id"] for r in store.query("SELECT id FROM objects WHERE origin_case=?", (case_id,))]
    ev = [dict(r) for r in store.query("SELECT id, sha256 FROM evidence WHERE case_id=? AND status='held'", (case_id,))]
    manifest = _manifest(store, objs, ev)
    for e in ev:
        destroy_evidence_file(store, e["id"], actor, f"retention: {reason}")
    exports = [dict(r) for r in store.query("SELECT id, path FROM exports WHERE case_id=?", (case_id,))]
    for x in exports:
        if x["path"] and Path(x["path"]).exists():
            os.remove(x["path"])
    counts = {"objects": _delete_objects(store, objs), "exhibits": len(ev), "exports": len(exports),
              "images": _delete_media(store, "case_id=?", (case_id,))}
    with store.tx() as conn:
        counts["face_searches"] = conn.execute("DELETE FROM face_matches WHERE case_id=?", (case_id,)).rowcount
        counts["scope"] = conn.execute("DELETE FROM case_objects WHERE case_id=?", (case_id,)).rowcount
        counts["leads"] = conn.execute("DELETE FROM leads WHERE case_id=?", (case_id,)).rowcount
        counts["watches"] = conn.execute("DELETE FROM watches WHERE case_id=?", (case_id,)).rowcount
        counts["saved_searches"] = conn.execute("DELETE FROM saved_searches WHERE case_id=?", (case_id,)).rowcount
        counts["area_searches"] = conn.execute("DELETE FROM area_searches WHERE case_id=?", (case_id,)).rowcount
        counts["reports"] = conn.execute("DELETE FROM reports WHERE case_id=?", (case_id,)).rowcount
        conn.execute("UPDATE exports SET path=NULL WHERE case_id=?", (case_id,))
        conn.execute("UPDATE cases SET purged_at=? WHERE id=?", (utcnow(), case_id))
        conn.execute("INSERT INTO purge_log(case_id,legal_order,purged_at,purged_by,reason,counts,manifest_sha256) VALUES(?,?,?,?,?,?,?)",
                     (case_id, None, utcnow(), actor, reason, json.dumps(counts), manifest))
    AuditLog(store).append(user_id=actor, role="system" if actor.startswith("system") else None, action="retention:purge_case",
                           case_id=case_id, detail={"reason": reason, "counts": counts, "manifest_sha256": manifest})
    return {"case_id": case_id, "counts": counts, "manifest_sha256": manifest}


def destroy_order_data(store: Store, legal_order: str, actor: str, reason: str) -> dict[str, Any]:
    """An interception / production order was set aside: destroy everything obtained under it."""
    objs = [r["id"] for r in store.query("SELECT id FROM objects WHERE legal_order=?", (legal_order,))]
    ev = [dict(r) for r in store.query("SELECT id, sha256 FROM evidence WHERE legal_order=? AND status='held'", (legal_order,))]
    calls = store.query("SELECT COUNT(*) n FROM cdrs WHERE legal_order=?", (legal_order,))[0]["n"]
    manifest = _manifest(store, objs, ev)
    for e in ev:
        destroy_evidence_file(store, e["id"], actor, f"order set aside: {reason}")
    counts = {"objects": _delete_objects(store, objs), "exhibits": len(ev)}
    with store.tx() as conn:
        counts["call_records"] = conn.execute("DELETE FROM cdrs WHERE legal_order=?", (legal_order,)).rowcount if calls else 0
        conn.execute("INSERT INTO purge_log(case_id,legal_order,purged_at,purged_by,reason,counts,manifest_sha256) VALUES(?,?,?,?,?,?,?)",
                     (None, legal_order, utcnow(), actor, reason, json.dumps(counts), manifest))
    AuditLog(store).append(user_id=actor, role=None, action="retention:destroy_order_data", detail={"legal_order": legal_order, "reason": reason,
                                                                                                    "counts": counts, "manifest_sha256": manifest})
    return {"legal_order": legal_order, "counts": counts, "manifest_sha256": manifest}


def run_due(store: Store, actor: str = "system:retention") -> list[dict[str, Any]]:
    return [purge_case(store, c["id"], actor, f"retention period ended {c['retention_until']}") for c in due_cases(store)]


def start_scheduler(store: Store, interval_hours: float) -> threading.Thread:
    """Daily (or configured) background purge inside the API process."""
    def loop() -> None:
        while True:
            try:
                run_due(store)
            except Exception:  # noqa: BLE001 - never kill the API; next run retries
                pass
            time.sleep(interval_hours * 3600)

    t = threading.Thread(target=loop, name="drishti-retention", daemon=True)
    t.start()
    return t

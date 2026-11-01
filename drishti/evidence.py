"""Evidence locker and chain of custody (design doc module M8).

* Exhibits are stored content-addressed and write-once: var/evidence/<sha256[:2]>/<sha256>.
  The same bytes uploaded twice are one file; a changed byte is a different exhibit.
* Every exhibit records SHA-256 and MD5 (BSA 2023 s.63(4) Schedule Part A asks for the hash
  value and the algorithm), the device it came from, the legal order and who collected it.
* Every touch (acquire, view, download, verify, export, destroy) is appended to a per-exhibit
  hash chain in `custody` (database-enforced append-only) and to the main audit chain.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
from pathlib import Path
from typing import Any

from .config import settings
from .store import Store, utcnow

GENESIS = "0" * 64
SOURCE_TYPES = ["Computer / storage media", "DVR", "Mobile phone", "Flash drive", "CD / DVD", "Server", "Cloud", "Bank / institution reply", "Other"]


def evidence_root() -> Path:
    root = Path(os.environ.get("DRISHTI_EVIDENCE_DIR", settings.db_path.parent / "evidence"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def _chain_hash(prev: str, row: dict[str, Any]) -> str:
    canonical = json.dumps({k: row[k] for k in ("evidence_id", "ts", "actor", "action", "detail")}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256((prev + canonical).encode()).hexdigest()


def custody_append(store: Store, evidence_id: str, actor: str, action: str, detail: dict[str, Any] | None = None) -> dict[str, Any]:
    with store.tx() as conn:
        last = conn.execute("SELECT hash FROM custody WHERE evidence_id=? ORDER BY seq DESC LIMIT 1", (evidence_id,)).fetchone()
        row = {"evidence_id": evidence_id, "ts": utcnow(), "actor": actor, "action": action, "detail": json.dumps(detail or {}, sort_keys=True)}
        prev = last["hash"] if last else GENESIS
        row["prev_hash"], row["hash"] = prev, _chain_hash(prev, row)
        conn.execute("INSERT INTO custody(evidence_id,ts,actor,action,detail,prev_hash,hash) VALUES(?,?,?,?,?,?,?)",
                     (row["evidence_id"], row["ts"], actor, action, row["detail"], prev, row["hash"]))
    return row


def custody_log(store: Store, evidence_id: str) -> list[dict[str, Any]]:
    return [dict(r) | {"detail": json.loads(r["detail"])} for r in store.query("SELECT * FROM custody WHERE evidence_id=? ORDER BY seq", (evidence_id,))]


def content_disposition(filename: str) -> str:
    """An attachment header that cannot be broken by quotes or control characters in a stored filename (RFC 6266)."""
    from urllib.parse import quote

    ascii_name = "".join(c if 32 <= ord(c) < 127 and c not in '"\\;' else "_" for c in filename)[:150] or "download"
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename[:150], safe='')}"


def store_evidence(store: Store, case_id: str, actor: str, filename: str, data: bytes, meta: dict[str, Any]) -> dict[str, Any]:
    sha256 = hashlib.sha256(data).hexdigest()
    md5 = hashlib.md5(data, usedforsecurity=False).hexdigest()
    path = evidence_root() / sha256[:2] / sha256
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        tmp = path.with_suffix(".part")
        tmp.write_bytes(data)
        tmp.replace(path)
        try:
            os.chmod(path, 0o444)  # write-once
        except OSError:
            pass
    eid = "evidence:" + secrets.token_hex(8)
    now = utcnow()
    row = {
        "id": eid, "case_id": case_id, "filename": Path(filename).name[:200], "mime": meta.get("mime"), "size": len(data),
        "sha256": sha256, "md5": md5, "storage_path": str(path), "description": meta.get("description"),
        "source_type": meta.get("source_type"), "device_make": meta.get("device_make"), "device_model": meta.get("device_model"),
        "device_serial": meta.get("device_serial"), "device_id": meta.get("device_id"), "seized_from": meta.get("seized_from"),
        "legal_order": meta.get("legal_order"), "collected_at": meta.get("collected_at"), "collected_by": meta.get("collected_by") or actor,
        "linked_objects": json.dumps(meta.get("linked_objects") or []), "uploaded_by": actor, "uploaded_at": now, "status": "held",
    }
    with store.tx() as conn:
        conn.execute(f"INSERT INTO evidence({','.join(row)}) VALUES({','.join('?' * len(row))})", list(row.values()))
    custody_append(store, eid, actor, "acquired", {"sha256": sha256, "md5": md5, "size": len(data), "filename": row["filename"],
                                                   "legal_order": row["legal_order"], "seized_from": row["seized_from"]})
    return get_evidence(store, eid)


def get_evidence(store: Store, eid: str) -> dict[str, Any] | None:
    rows = store.query("SELECT * FROM evidence WHERE id=?", (eid,))
    if not rows:
        return None
    r = dict(rows[0])
    r["linked_objects"] = json.loads(r["linked_objects"])
    r.pop("storage_path", None)
    return r


def list_evidence(store: Store, case_id: str) -> list[dict[str, Any]]:
    out = []
    for r in store.query("SELECT id FROM evidence WHERE case_id=? ORDER BY uploaded_at", (case_id,)):
        e = get_evidence(store, r["id"])
        e["custody_events"] = store.query("SELECT COUNT(*) n FROM custody WHERE evidence_id=?", (r["id"],))[0]["n"]
        out.append(e)
    return out


def read_evidence(store: Store, eid: str, actor: str, purpose: str = "downloaded") -> tuple[dict[str, Any], bytes]:
    rows = store.query("SELECT * FROM evidence WHERE id=?", (eid,))
    if not rows or rows[0]["status"] != "held":
        raise FileNotFoundError("exhibit not held")
    data = Path(rows[0]["storage_path"]).read_bytes()
    custody_append(store, eid, actor, purpose, {"sha256_at_access": hashlib.sha256(data).hexdigest()})
    return get_evidence(store, eid), data


def verify_evidence(store: Store, eid: str, actor: str) -> dict[str, Any]:
    rows = store.query("SELECT * FROM evidence WHERE id=?", (eid,))
    if not rows:
        raise FileNotFoundError(eid)
    r = rows[0]
    file_ok = None
    if r["status"] == "held":
        data = Path(r["storage_path"]).read_bytes()
        file_ok = hashlib.sha256(data).hexdigest() == r["sha256"] and hashlib.md5(data, usedforsecurity=False).hexdigest() == r["md5"]
    prev, chain_ok, n = GENESIS, True, 0
    for c in store.query("SELECT * FROM custody WHERE evidence_id=? ORDER BY seq", (eid,)):
        row = dict(c)
        if row["prev_hash"] != prev or _chain_hash(prev, row) != row["hash"]:
            chain_ok = False
            break
        prev = row["hash"]
        n += 1
    result = {"evidence_id": eid, "file_intact": file_ok, "custody_intact": chain_ok, "custody_events": n, "sha256": r["sha256"], "status": r["status"]}
    custody_append(store, eid, actor, "verified", {"file_intact": file_ok, "custody_intact": chain_ok})
    return result


def destroy_evidence_file(store: Store, eid: str, actor: str, reason: str) -> None:
    rows = store.query("SELECT * FROM evidence WHERE id=?", (eid,))
    if not rows or rows[0]["status"] != "held":
        return
    path = Path(rows[0]["storage_path"])
    still_used = store.query("SELECT COUNT(*) n FROM evidence WHERE sha256=? AND status='held' AND id<>?", (rows[0]["sha256"], eid))[0]["n"]
    if path.exists() and not still_used:
        try:
            os.chmod(path, 0o644)
        except OSError:
            pass
        with path.open("r+b") as fh:  # overwrite before unlinking
            fh.write(b"\0" * path.stat().st_size)
        path.unlink()
    with store.tx() as conn:
        conn.execute("UPDATE evidence SET status='destroyed', description=NULL, linked_objects='[]' WHERE id=?", (eid,))
    custody_append(store, eid, actor, "destroyed", {"reason": reason, "sha256": rows[0]["sha256"]})

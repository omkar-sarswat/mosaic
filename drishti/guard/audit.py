"""Hash-chained, append-only audit log and insider-threat analytics (design doc 11.2, 11.5)."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from ..config import settings
from ..store import Store, utcnow

GENESIS = "0" * 64
IST = timezone(timedelta(hours=5, minutes=30))
# Workflows that show many records by design and whose contents the user does not choose.
# They are still fully audited; they just do not trip the volume and after-hours rules.
SANCTIONED_BULK = {"review_queue"}
_FIELDS = ("ts", "user_id", "role", "case_id", "purpose", "action", "detail", "object_ids", "outcome", "client")


def _row_hash(prev_hash: str, row: dict[str, Any]) -> str:
    canonical = json.dumps({k: row.get(k) for k in _FIELDS}, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256((prev_hash + canonical).encode("utf-8")).hexdigest()


class AuditLog:
    def __init__(self, store: Store):
        self.store = store

    def append(
        self,
        *,
        user_id: str,
        role: str | None,
        action: str,
        outcome: str = "ok",
        case_id: str | None = None,
        purpose: str | None = None,
        detail: dict[str, Any] | None = None,
        object_ids: list[str] | None = None,
        client: str | None = None,
    ) -> dict[str, Any]:
        row = {
            "ts": utcnow(),
            "user_id": user_id,
            "role": role,
            "case_id": case_id,
            "purpose": purpose,
            "action": action,
            "detail": json.dumps(detail or {}, sort_keys=True, ensure_ascii=False),
            "object_ids": json.dumps(sorted(set(object_ids or []))),
            "outcome": outcome,
            "client": client,
        }
        with self.store.tx() as conn:  # serialised: the chain must be linear
            last = conn.execute("SELECT hash FROM audit ORDER BY seq DESC LIMIT 1").fetchone()
            prev = last["hash"] if last else GENESIS
            row["prev_hash"] = prev
            row["hash"] = _row_hash(prev, row)
            cur = conn.execute(
                f"INSERT INTO audit({','.join(_FIELDS)},prev_hash,hash) VALUES({','.join('?' * (len(_FIELDS) + 2))}) RETURNING seq",
                [row[k] for k in _FIELDS] + [row["prev_hash"], row["hash"]],
            )
            row["seq"] = cur.fetchone()[0]
        return row

    def verify(self) -> dict[str, Any]:
        prev = GENESIS
        checked = 0
        for r in self.store.query("SELECT * FROM audit ORDER BY seq"):
            row = dict(r)
            if row["prev_hash"] != prev or _row_hash(prev, row) != row["hash"]:
                return {"ok": False, "checked": checked, "first_bad_seq": row["seq"]}
            prev = row["hash"]
            checked += 1
        return {"ok": True, "checked": checked, "head": prev}

    def seal_day(self, day: str | None = None) -> dict[str, Any]:
        """Record the chain head for a day. Publish root_hash outside DRISHTI (e.g. to the
        oversight body by email or a public transparency page) so tampering is detectable."""
        day = day or datetime.now(timezone.utc).date().isoformat()
        rows = self.store.query("SELECT seq, hash FROM audit WHERE ts < ? ORDER BY seq DESC LIMIT 1", (f"{day}T23:59:59.999",))
        if not rows:
            return {"day": day, "sealed": False}
        with self.store.tx() as conn:
            conn.execute(
                "INSERT INTO audit_roots(day,last_seq,root_hash,created_at) VALUES(?,?,?,?) "
                "ON CONFLICT(day) DO UPDATE SET last_seq=excluded.last_seq, root_hash=excluded.root_hash, created_at=excluded.created_at",
                (day, rows[0]["seq"], rows[0]["hash"], utcnow()),
            )
        return {"day": day, "sealed": True, "last_seq": rows[0]["seq"], "root_hash": rows[0]["hash"]}

    def rows(self, *, user_id: str | None = None, object_id: str | None = None, case_id: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
        sql, params = "SELECT * FROM audit WHERE 1=1", []
        if user_id:
            sql += " AND user_id=?"
            params.append(user_id)
        if case_id:
            sql += " AND case_id=?"
            params.append(case_id)
        if object_id:
            sql += " AND object_ids LIKE ?"
            params.append(f'%"{object_id}"%')
        sql += " ORDER BY seq DESC LIMIT ?"
        params.append(limit)
        out = []
        for r in self.store.query(sql, params):
            d = dict(r)
            d["detail"] = json.loads(d["detail"])
            d["object_ids"] = json.loads(d["object_ids"])
            out.append(d)
        return out

    # ------------------------------------------------------------ insider-threat analytics
    def alerts(self, *, volume_per_hour: int = 40, denied_burst: int = 5, after_hours_min: int = 10) -> list[dict[str, Any]]:
        canaries = {r["object_id"] for r in self.store.query("SELECT object_id FROM canaries")}
        personal_types = {n for n, t in self.store.ontology.objects.items() if t.personal}
        rows = self.store.query("SELECT seq, ts, user_id, action, object_ids, outcome FROM audit ORDER BY seq")
        alerts: list[dict[str, Any]] = []
        per_hour: dict[tuple[str, str], set[str]] = defaultdict(set)
        denied: dict[str, list[datetime]] = defaultdict(list)
        after: dict[tuple[str, str], set[str]] = defaultdict(set)
        type_cache: dict[str, str] = {}

        def is_personal(oid: str) -> bool:
            if oid not in type_cache:
                hit = self.store.query("SELECT type FROM objects WHERE id=?", (oid,))
                type_cache[oid] = hit[0]["type"] if hit else ""
            return type_cache[oid] in personal_types

        for r in rows:
            ids = json.loads(r["object_ids"])
            ts = datetime.fromisoformat(r["ts"])
            if canaries.intersection(ids):
                alerts.append({
                    "severity": "critical", "rule": "canary_record_accessed", "user_id": r["user_id"], "seq": r["seq"], "ts": r["ts"],
                    "detail": "A planted canary record was returned to this user. Treat as possible compromise or misuse.",
                })
            if r["outcome"] == "denied":
                window = [t for t in denied[r["user_id"]] if ts - t <= timedelta(minutes=10)] + [ts]
                denied[r["user_id"]] = window
                if len(window) == denied_burst:
                    alerts.append({"severity": "medium", "rule": "denied_access_burst", "user_id": r["user_id"], "seq": r["seq"], "ts": r["ts"],
                                   "detail": f"{denied_burst} denied requests within 10 minutes"})
                continue
            personal = [i for i in ids if is_personal(i)]
            if not personal or r["action"] in SANCTIONED_BULK:
                continue
            hour = ts.strftime("%Y-%m-%dT%H")
            bucket = per_hour[(r["user_id"], hour)]
            before = len(bucket)
            bucket.update(personal)
            if before < volume_per_hour <= len(bucket):
                alerts.append({"severity": "high", "rule": "bulk_personal_lookup", "user_id": r["user_id"], "seq": r["seq"], "ts": r["ts"],
                               "detail": f"{len(bucket)}+ distinct personal records in one hour"})
            local = ts.astimezone(IST)
            start, end = settings.after_hours
            if local.hour >= start or local.hour < end:
                ab = after[(r["user_id"], local.date().isoformat())]
                before = len(ab)
                ab.update(personal)
                if before < after_hours_min <= len(ab):
                    alerts.append({"severity": "medium", "rule": "after_hours_lookup", "user_id": r["user_id"], "seq": r["seq"], "ts": r["ts"],
                                   "detail": f"{len(ab)} personal records viewed between {start}:00 and {end}:00 IST"})
        order = {"critical": 0, "high": 1, "medium": 2}
        return sorted(alerts, key=lambda a: (order[a["severity"]], -a["seq"]))

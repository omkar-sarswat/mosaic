"""Ontology store: objects, links, provenance, cases, review queue and audit tables.

Two engines run the same schema and SQL:

* SQLite, a single file: the laptop, tests and the offline edge kit (module M12), no servers
* PostgreSQL 18, given a URL (DRISHTI_DB_URL=postgresql://user:pass@host:port/db, optionally
  ?schema=name for a separate namespace): a state or agency deployment

The schema is written once for SQLite and translated for PostgreSQL by _pg_schema (double precision
for amounts, identity columns, plpgsql triggers that keep the audit and custody logs append-only, and a
tsvector search table in place of FTS5). SQL that differs between engines goes through Store.dialect
helpers; drishti/pgcompat.py gives the PostgreSQL connection the sqlite3 interface the code uses.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

from .ontology import Ontology, get_ontology
from .pgcompat import Connection as PgConnection, split_target
from .resolve.names import name_search_terms, normalize_name, to_latin

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);

CREATE TABLE IF NOT EXISTS objects(
  id TEXT PRIMARY KEY,
  type TEXT NOT NULL,
  title TEXT,
  props TEXT NOT NULL,
  sensitivity INTEGER NOT NULL,
  district_lgd TEXT,
  lat REAL, lon REAL,
  geom TEXT,
  synthetic INTEGER NOT NULL DEFAULT 0,
  origin_case TEXT,          -- set when the object was obtained for a case (bank reply, CDR, NATGRID response)
  legal_order TEXT,          -- the order under which it was obtained; destroyed if the order is set aside
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS objects_type ON objects(type);
CREATE INDEX IF NOT EXISTS objects_origin ON objects(origin_case);
CREATE INDEX IF NOT EXISTS objects_district ON objects(district_lgd);

-- Provenance on every property: which source said what, when, with what confidence.
CREATE TABLE IF NOT EXISTS provenance(
  object_id TEXT NOT NULL REFERENCES objects(id) ON DELETE CASCADE,
  prop TEXT NOT NULL,
  source TEXT NOT NULL,
  record TEXT NOT NULL,
  ingested_at TEXT NOT NULL,
  confidence REAL NOT NULL DEFAULT 1.0,
  PRIMARY KEY(object_id, prop, source, record)
);

-- Links carry their evidence: the list of independent source records asserting them.
-- status: active (ingested fact) | auto / candidate / confirmed / rejected (resolver output)
CREATE TABLE IF NOT EXISTS links(
  id TEXT PRIMARY KEY,
  type TEXT NOT NULL,
  src TEXT NOT NULL REFERENCES objects(id) ON DELETE CASCADE,
  dst TEXT NOT NULL REFERENCES objects(id) ON DELETE CASCADE,
  props TEXT NOT NULL DEFAULT '{}',
  sources TEXT NOT NULL DEFAULT '[]',
  origin TEXT NOT NULL DEFAULT 'ingest',
  confidence REAL NOT NULL DEFAULT 1.0,
  status TEXT NOT NULL DEFAULT 'active',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS links_src ON links(src);
CREATE INDEX IF NOT EXISTS links_dst ON links(dst);
CREATE INDEX IF NOT EXISTS links_type ON links(type, status);

CREATE TABLE IF NOT EXISTS identifiers(
  kind TEXT NOT NULL, value TEXT NOT NULL, object_id TEXT NOT NULL REFERENCES objects(id) ON DELETE CASCADE,
  PRIMARY KEY(kind, value, object_id)
);
CREATE INDEX IF NOT EXISTS identifiers_value ON identifiers(value);
CREATE INDEX IF NOT EXISTS identifiers_object ON identifiers(object_id);

CREATE VIRTUAL TABLE IF NOT EXISTS objects_fts USING fts5(id UNINDEXED, type UNINDEXED, body, tokenize='unicode61');

CREATE TABLE IF NOT EXISTS cases(
  id TEXT PRIMARY KEY,
  purpose TEXT NOT NULL,
  legal_basis TEXT NOT NULL,
  fir_no TEXT,
  title TEXT,
  agency TEXT,
  opened_by TEXT NOT NULL,
  opened_at TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'open',
  max_depth INTEGER NOT NULL DEFAULT 1,
  closed_at TEXT, outcome TEXT, retention_until TEXT,
  legal_hold INTEGER NOT NULL DEFAULT 0, hold_reason TEXT, purged_at TEXT
);
CREATE TABLE IF NOT EXISTS case_members(case_id TEXT NOT NULL REFERENCES cases(id), user_id TEXT NOT NULL, PRIMARY KEY(case_id, user_id));
CREATE TABLE IF NOT EXISTS case_objects(
  case_id TEXT NOT NULL REFERENCES cases(id), object_id TEXT NOT NULL REFERENCES objects(id),
  added_by TEXT NOT NULL, reason TEXT NOT NULL, added_at TEXT NOT NULL,
  PRIMARY KEY(case_id, object_id)
);
CREATE TABLE IF NOT EXISTS expansion_requests(
  id TEXT PRIMARY KEY, case_id TEXT NOT NULL REFERENCES cases(id), depth INTEGER NOT NULL, reason TEXT NOT NULL,
  requested_by TEXT NOT NULL, requested_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
  decided_by TEXT, decided_at TEXT
);

CREATE TABLE IF NOT EXISTS review_queue(
  id TEXT PRIMARY KEY, a TEXT NOT NULL, b TEXT NOT NULL, probability REAL NOT NULL, explanation TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending', decided_by TEXT, decided_at TEXT, reason TEXT
);

CREATE TABLE IF NOT EXISTS dispatches(
  id INTEGER PRIMARY KEY AUTOINCREMENT, hazard_id TEXT, admin_unit TEXT NOT NULL, resource TEXT NOT NULL,
  quantity INTEGER NOT NULL, dispatched_by TEXT NOT NULL, dispatched_at TEXT NOT NULL
);

-- Append-only, hash-chained audit log (design doc 11.2). Triggers refuse UPDATE/DELETE;
-- the hash chain plus published daily roots detect anyone who bypasses the triggers.
CREATE TABLE IF NOT EXISTS audit(
  seq INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL, user_id TEXT NOT NULL, role TEXT, case_id TEXT, purpose TEXT,
  action TEXT NOT NULL, detail TEXT NOT NULL, object_ids TEXT NOT NULL, outcome TEXT NOT NULL,
  client TEXT, prev_hash TEXT NOT NULL, hash TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit BEGIN SELECT RAISE(ABORT, 'audit log is append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit BEGIN SELECT RAISE(ABORT, 'audit log is append-only'); END;
CREATE TABLE IF NOT EXISTS audit_roots(day TEXT PRIMARY KEY, last_seq INTEGER NOT NULL, root_hash TEXT NOT NULL, created_at TEXT NOT NULL);

-- Canary records: planted fake entries that raise an alarm whenever they are read.
CREATE TABLE IF NOT EXISTS canaries(object_id TEXT PRIMARY KEY);

-- ---------------------------------------------------------------- event tables
-- High-volume events stay out of the object graph; they surface as aggregated links.
CREATE TABLE IF NOT EXISTS txns(
  id TEXT PRIMARY KEY, ts TEXT NOT NULL,
  from_acct TEXT, to_acct TEXT,            -- NULL from_acct = cash deposit, NULL to_acct = cash withdrawal
  amount REAL NOT NULL, channel TEXT NOT NULL, narration TEXT, ref TEXT,
  country TEXT, source TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS txns_from ON txns(from_acct, ts);
CREATE INDEX IF NOT EXISTS txns_to ON txns(to_acct, ts);

CREATE TABLE IF NOT EXISTS towers(id TEXT PRIMARY KEY, label TEXT, lat REAL, lon REAL, district_lgd TEXT,
  operator TEXT, technology TEXT, cgi TEXT, site_type TEXT, city TEXT);
-- fixed places that read number plates: ANPR junction cameras and highway toll plazas (FASTag)
CREATE TABLE IF NOT EXISTS checkpoints(
  id TEXT PRIMARY KEY, kind TEXT NOT NULL, label TEXT NOT NULL, lat REAL NOT NULL, lon REAL NOT NULL, district_lgd TEXT,
  city TEXT, road TEXT, operator TEXT
);
CREATE TABLE IF NOT EXISTS cdrs(
  id TEXT PRIMARY KEY, ts TEXT NOT NULL, a_number TEXT NOT NULL, b_number TEXT NOT NULL,
  duration_s INTEGER, call_type TEXT, tower_id TEXT, legal_order TEXT, source TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS cdrs_a ON cdrs(a_number, ts);
CREATE INDEX IF NOT EXISTS cdrs_b ON cdrs(b_number, ts);
CREATE INDEX IF NOT EXISTS cdrs_tower ON cdrs(tower_id, ts);

CREATE TABLE IF NOT EXISTS travel(
  id TEXT PRIMARY KEY, person_id TEXT NOT NULL, ts TEXT NOT NULL, mode TEXT, pnr TEXT,
  from_city TEXT, from_country TEXT, from_lat REAL, from_lon REAL,
  to_city TEXT, to_country TEXT, to_lat REAL, to_lon REAL, source TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS travel_person ON travel(person_id, ts);

-- FASTag toll reads and ANPR camera reads (kind: toll | anpr). A read records the plate seen;
-- a cloned plate shows up as one registration in two places no vehicle could connect in time.
CREATE TABLE IF NOT EXISTS tollhits(
  id TEXT PRIMARY KEY, vehicle_id TEXT NOT NULL, ts TEXT NOT NULL, plaza TEXT, lat REAL, lon REAL, source TEXT NOT NULL,
  kind TEXT
);
CREATE INDEX IF NOT EXISTS toll_vehicle ON tollhits(vehicle_id, ts);
CREATE INDEX IF NOT EXISTS toll_plaza ON tollhits(plaza, ts);

-- Purchase registers kept by licensed dealers: NDPS controlled substances (precursors) and
-- explosives precursors (Ammonium Nitrate Rules). One row per sale.
CREATE TABLE IF NOT EXISTS procurements(
  id TEXT PRIMARY KEY, ts TEXT NOT NULL, buyer_id TEXT NOT NULL, seller_id TEXT NOT NULL,
  substance TEXT NOT NULL, regime TEXT NOT NULL, quantity_kg REAL NOT NULL,
  invoice TEXT, buyer_licence TEXT, source TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS procurements_buyer ON procurements(buyer_id, ts);

-- Public-procurement bids (e-procurement portal exports).
CREATE TABLE IF NOT EXISTS bids(
  id TEXT PRIMARY KEY, tender_id TEXT NOT NULL, bidder_id TEXT NOT NULL, amount REAL NOT NULL,
  submitted_at TEXT NOT NULL, submit_ip TEXT, source TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS bids_tender ON bids(tender_id);

-- ---------------------------------------------------------------- evidence locker (module M8)
CREATE TABLE IF NOT EXISTS evidence(
  id TEXT PRIMARY KEY, case_id TEXT NOT NULL, filename TEXT NOT NULL, mime TEXT, size INTEGER NOT NULL,
  sha256 TEXT NOT NULL, md5 TEXT NOT NULL, storage_path TEXT NOT NULL, description TEXT,
  source_type TEXT, device_make TEXT, device_model TEXT, device_serial TEXT, device_id TEXT,
  seized_from TEXT, legal_order TEXT, collected_at TEXT, collected_by TEXT,
  linked_objects TEXT NOT NULL DEFAULT '[]', uploaded_by TEXT NOT NULL, uploaded_at TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'held'
);
CREATE INDEX IF NOT EXISTS evidence_case ON evidence(case_id);
-- chain of custody: one hash chain per exhibit, append-only like the audit log
CREATE TABLE IF NOT EXISTS custody(
  seq INTEGER PRIMARY KEY AUTOINCREMENT, evidence_id TEXT NOT NULL, ts TEXT NOT NULL, actor TEXT NOT NULL,
  action TEXT NOT NULL, detail TEXT NOT NULL, prev_hash TEXT NOT NULL, hash TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS custody_ev ON custody(evidence_id, seq);
CREATE TRIGGER IF NOT EXISTS custody_no_update BEFORE UPDATE ON custody BEGIN SELECT RAISE(ABORT, 'custody log is append-only'); END;
CREATE TRIGGER IF NOT EXISTS custody_no_delete BEFORE DELETE ON custody BEGIN SELECT RAISE(ABORT, 'custody log is append-only'); END;
CREATE TABLE IF NOT EXISTS exports(
  id TEXT PRIMARY KEY, case_id TEXT NOT NULL, kind TEXT NOT NULL, filename TEXT NOT NULL, sha256 TEXT NOT NULL,
  size INTEGER NOT NULL, exported_by TEXT NOT NULL, exported_at TEXT NOT NULL, recipient TEXT, marking TEXT, path TEXT
);
-- retention: a tombstone survives every purge so the deletion itself is accountable
CREATE TABLE IF NOT EXISTS purge_log(
  id INTEGER PRIMARY KEY AUTOINCREMENT, case_id TEXT, legal_order TEXT, purged_at TEXT NOT NULL, purged_by TEXT NOT NULL,
  reason TEXT NOT NULL, counts TEXT NOT NULL, manifest_sha256 TEXT NOT NULL
);

-- ---------------------------------------------------------------- behaviour flags (conduct only)
CREATE TABLE IF NOT EXISTS behaviour_flags(
  id TEXT PRIMARY KEY, subject_id TEXT NOT NULL, code TEXT NOT NULL, severity TEXT NOT NULL, weight REAL NOT NULL,
  title TEXT NOT NULL, summary TEXT NOT NULL, evidence TEXT NOT NULL, inputs TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS flags_subject ON behaviour_flags(subject_id);
CREATE INDEX IF NOT EXISTS flags_code ON behaviour_flags(code);

-- ---------------------------------------------------------------- photographs and faces
CREATE TABLE IF NOT EXISTS media(
  id TEXT PRIMARY KEY, object_id TEXT, case_id TEXT, kind TEXT NOT NULL, sha256 TEXT NOT NULL, path TEXT NOT NULL,
  mime TEXT, width INTEGER, height INTEGER, source TEXT NOT NULL, legal_basis TEXT, evidence_id TEXT,
  added_by TEXT NOT NULL, added_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS media_object ON media(object_id);
CREATE TABLE IF NOT EXISTS faces(
  id TEXT PRIMARY KEY, media_id TEXT NOT NULL, object_id TEXT, idx INTEGER NOT NULL, box TEXT NOT NULL,
  score REAL NOT NULL, embedding BLOB NOT NULL, role TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS faces_role ON faces(role);
CREATE TABLE IF NOT EXISTS face_matches(
  id TEXT PRIMARY KEY, case_id TEXT NOT NULL, probe_face TEXT NOT NULL, candidate_object TEXT NOT NULL, gallery_face TEXT NOT NULL,
  similarity REAL NOT NULL, status TEXT NOT NULL DEFAULT 'candidate', searched_by TEXT NOT NULL, reason TEXT NOT NULL,
  decided_by TEXT, decision_reason TEXT, decided_at TEXT, created_at TEXT NOT NULL
);

-- ---------------------------------------------------------------- analytics output
CREATE TABLE IF NOT EXISTS alerts(
  id TEXT PRIMARY KEY, rule TEXT NOT NULL, severity TEXT NOT NULL, subject_id TEXT NOT NULL,
  subject_type TEXT NOT NULL, score REAL NOT NULL, amount REAL, window_start TEXT, window_end TEXT,
  summary TEXT NOT NULL, details TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS alerts_subject ON alerts(subject_id);
CREATE INDEX IF NOT EXISTS alerts_rule ON alerts(rule);

CREATE TABLE IF NOT EXISTS leads(
  id TEXT PRIMARY KEY, case_id TEXT NOT NULL, subject_id TEXT, title TEXT NOT NULL,
  stage TEXT NOT NULL, assignee TEXT, notes TEXT NOT NULL DEFAULT '[]',
  created_by TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS investigation_notes(
  id TEXT PRIMARY KEY, case_id TEXT NOT NULL REFERENCES cases(id), object_id TEXT REFERENCES objects(id),
  body TEXT NOT NULL, author TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS case_shares(
  id TEXT PRIMARY KEY, case_id TEXT NOT NULL REFERENCES cases(id), recipient TEXT NOT NULL,
  reason TEXT NOT NULL, requested_by TEXT NOT NULL, requested_at TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending', decided_by TEXT, decided_at TEXT
);
-- ---------------------------------------------------------------- pattern engine (leads, not findings)
-- A run records which detector versions saw which data (fingerprint), so every lead is reproducible.
CREATE TABLE IF NOT EXISTS pattern_runs(
  id TEXT PRIMARY KEY, started_at TEXT NOT NULL, finished_at TEXT, run_by TEXT NOT NULL,
  data_fingerprint TEXT NOT NULL, detectors TEXT NOT NULL, counts TEXT NOT NULL, timings TEXT NOT NULL
);
-- A hit is a pattern seen in the data, with its evidence. Its id is stable across runs so a
-- reviewer's disposition (dismissed, case opened) survives recomputation.
CREATE TABLE IF NOT EXISTS pattern_hits(
  id TEXT PRIMARY KEY, run_id TEXT NOT NULL, detector TEXT NOT NULL, version TEXT NOT NULL, tracks TEXT NOT NULL,
  severity TEXT NOT NULL, title TEXT NOT NULL, summary TEXT NOT NULL, subjects TEXT NOT NULL, evidence TEXT NOT NULL,
  measurements TEXT NOT NULL, thresholds TEXT NOT NULL, window_start TEXT, window_end TEXT, district_lgd TEXT,
  status TEXT NOT NULL DEFAULT 'open', case_id TEXT, disposition TEXT, decided_by TEXT, decided_at TEXT,
  first_seen TEXT NOT NULL, last_seen TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS hits_detector ON pattern_hits(detector, status);
CREATE TABLE IF NOT EXISTS lead_requests(
  id TEXT PRIMARY KEY, hit_id TEXT NOT NULL, purpose TEXT NOT NULL, legal_basis TEXT NOT NULL, title TEXT,
  requested_by TEXT NOT NULL, agency TEXT NOT NULL, requested_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
  decided_by TEXT, decided_at TEXT, case_id TEXT
);

-- revision cards: one row per governed change to a property or link (who, when, which source row, which proposal)
CREATE TABLE IF NOT EXISTS revisions(
  id INTEGER PRIMARY KEY AUTOINCREMENT, object_id TEXT NOT NULL, prop TEXT, op TEXT NOT NULL, old_value TEXT, new_value TEXT,
  source TEXT NOT NULL, record TEXT, proposal_id TEXT, actor TEXT NOT NULL, at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS revisions_object ON revisions(object_id);
CREATE INDEX IF NOT EXISTS revisions_proposal ON revisions(proposal_id);

-- intake proposals: a cleaned extract waiting for a second officer's approval before it touches the ontology
CREATE TABLE IF NOT EXISTS intake_proposals(
  id TEXT PRIMARY KEY, case_id TEXT NOT NULL, source TEXT NOT NULL, recipe TEXT NOT NULL, legal_order TEXT NOT NULL,
  summary TEXT NOT NULL, changes TEXT NOT NULL, fingerprint TEXT NOT NULL, requested_by TEXT NOT NULL, requested_at TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending', decided_by TEXT, decided_at TEXT, decision_reason TEXT, applied TEXT
);

CREATE TABLE IF NOT EXISTS investigation_boards(
  id TEXT PRIMARY KEY, case_id TEXT NOT NULL REFERENCES cases(id), title TEXT NOT NULL,
  object_ids TEXT NOT NULL, created_by TEXT NOT NULL, created_at TEXT NOT NULL
);

-- ---------------------------------------------------------------- monitoring (watchlists, saved searches)
-- A watch follows one record (kind 'object') or one area (kind 'area', JSON in `area`) inside a case. New
-- activity after `seen_at` becomes a work item; `since` is where the watch's history starts.
CREATE TABLE IF NOT EXISTS watches(
  id TEXT PRIMARY KEY, case_id TEXT NOT NULL REFERENCES cases(id), kind TEXT NOT NULL, object_id TEXT, area TEXT,
  label TEXT NOT NULL, reason TEXT NOT NULL, created_by TEXT NOT NULL, created_at TEXT NOT NULL, since TEXT NOT NULL,
  seen_at TEXT NOT NULL, seen_by TEXT, status TEXT NOT NULL DEFAULT 'active', ended_by TEXT, ended_at TEXT, end_reason TEXT
);
CREATE INDEX IF NOT EXISTS watches_case ON watches(case_id, status);
-- A saved search re-runs under the same case; `known` holds the record ids the officer has already seen.
CREATE TABLE IF NOT EXISTS saved_searches(
  id TEXT PRIMARY KEY, case_id TEXT NOT NULL REFERENCES cases(id), title TEXT NOT NULL, query TEXT NOT NULL, types TEXT NOT NULL,
  reason TEXT NOT NULL, created_by TEXT NOT NULL, created_at TEXT NOT NULL, known TEXT NOT NULL, checked_at TEXT NOT NULL, checked_by TEXT,
  status TEXT NOT NULL DEFAULT 'active', ended_by TEXT, ended_at TEXT, end_reason TEXT
);
CREATE INDEX IF NOT EXISTS searches_case ON saved_searches(case_id, status);

-- ---------------------------------------------------------------- reports (case diary, chargesheet annexures)
-- Blocks are JSON: text written by the officer, and references (records, exhibits, leads, area searches) that
-- are read afresh, through the access rules, whenever the report is opened or exported.
CREATE TABLE IF NOT EXISTS reports(
  id TEXT PRIMARY KEY, case_id TEXT NOT NULL REFERENCES cases(id), template TEXT NOT NULL, title TEXT NOT NULL,
  blocks TEXT NOT NULL, created_by TEXT NOT NULL, created_at TEXT NOT NULL, updated_by TEXT NOT NULL, updated_at TEXT NOT NULL,
  version INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS reports_case ON reports(case_id);
-- area searches kept for a report or a geofence: the question asked and the answer at the time
CREATE TABLE IF NOT EXISTS area_searches(
  id TEXT PRIMARY KEY, case_id TEXT NOT NULL REFERENCES cases(id), lat REAL NOT NULL, lon REAL NOT NULL, radius_km REAL NOT NULL,
  start_ts TEXT NOT NULL, end_ts TEXT NOT NULL, label TEXT, reason TEXT NOT NULL, counts TEXT NOT NULL,
  searched_by TEXT NOT NULL, searched_at TEXT NOT NULL
);
"""


PG_SEARCH = """
CREATE TABLE IF NOT EXISTS object_search(
  id TEXT PRIMARY KEY, type TEXT NOT NULL, body TEXT NOT NULL,
  tsv tsvector GENERATED ALWAYS AS (to_tsvector('simple', body)) STORED
);
CREATE INDEX IF NOT EXISTS object_search_tsv ON object_search USING GIN(tsv);
CREATE OR REPLACE FUNCTION append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION '% log is append-only', TG_TABLE_NAME; END $$;
CREATE OR REPLACE TRIGGER audit_no_update BEFORE UPDATE ON audit FOR EACH ROW EXECUTE FUNCTION append_only();
CREATE OR REPLACE TRIGGER audit_no_delete BEFORE DELETE ON audit FOR EACH ROW EXECUTE FUNCTION append_only();
CREATE OR REPLACE TRIGGER custody_no_update BEFORE UPDATE ON custody FOR EACH ROW EXECUTE FUNCTION append_only();
CREATE OR REPLACE TRIGGER custody_no_delete BEFORE DELETE ON custody FOR EACH ROW EXECUTE FUNCTION append_only();
"""


def _pg_schema(sql: str) -> str:
    """The SQLite schema in PostgreSQL's dialect."""
    out = []
    for line in sql.split("\n"):
        stripped = line.strip()
        if stripped.startswith(("PRAGMA", "CREATE TRIGGER", "CREATE VIRTUAL TABLE")):
            continue
        out.append(line)
    text = "\n".join(out)
    text = re.sub(r"\bINTEGER PRIMARY KEY AUTOINCREMENT\b", "BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY", text)
    text = re.sub(r"\bINTEGER\b", "BIGINT", text)
    text = re.sub(r"\bREAL\b", "DOUBLE PRECISION", text)
    text = re.sub(r"\bBLOB\b", "BYTEA", text)
    return text + PG_SEARCH


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def make_id(type_name: str, source: str, record: str) -> str:
    return f"{type_name.lower()}:{hashlib.sha1(f'{source}|{record}'.encode()).hexdigest()[:16]}"


def normalize_identifier(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value).upper())


def is_postgres(target: Path | str) -> bool:
    return str(target).startswith(("postgresql://", "postgres://"))


class Store:
    def __init__(self, path: Path | str, ontology: Ontology | None = None):
        self.ontology = ontology or get_ontology()
        self._lock = threading.RLock()
        self._depth = 0
        self.target = str(path)
        if is_postgres(path):
            from .config import settings

            self.dialect = "postgres"
            url, schema = split_target(str(path))
            self.schema = schema
            self.path = Path(settings.db_path)  # files next to the database (evidence, media, exports) stay under var/
            self.conn = PgConnection(url, schema)
        else:
            self.dialect = "sqlite"
            self.schema = None
            self.path = Path(path)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.conn = sqlite3.connect(str(self.path), check_same_thread=False, isolation_level=None)
            self.conn.row_factory = sqlite3.Row
        # Additive upgrades must run before indexes reference new columns.
        with self.tx():
            for table, additions in {
                "objects": {"origin_case": "TEXT", "legal_order": "TEXT"},
                "cases": {"legal_hold": "INTEGER NOT NULL DEFAULT 0", "hold_reason": "TEXT", "purged_at": "TEXT"},
                "tollhits": {"kind": "TEXT"},
                "towers": {"operator": "TEXT", "technology": "TEXT", "cgi": "TEXT", "site_type": "TEXT", "city": "TEXT"},
            }.items():
                columns = self._columns(table)
                if columns:
                    for name, definition in additions.items():
                        if name not in columns:
                            if self.dialect == "postgres":
                                definition = definition.replace("INTEGER", "BIGINT")
                            self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")
        self.conn.executescript(SCHEMA if self.dialect == "sqlite" else _pg_schema(SCHEMA))
        if self.query("SELECT value FROM meta WHERE key='fts_layout'") == []:
            self._rebuild_fts()

    def _columns(self, table: str) -> set[str]:
        if self.dialect == "sqlite":
            return {r[1] for r in self.conn.execute(f"PRAGMA table_info({table})")}
        return {r[0] for r in self.conn.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_schema=current_schema() AND table_name=?", (table,))}

    # ------------------------------------------------------------------ dialect helpers
    def greatest(self, a: str, b: str) -> str:
        return f"MAX({a}, {b})" if self.dialect == "sqlite" else f"GREATEST({a}, {b})"

    def group_concat(self, expr: str) -> str:
        return f"GROUP_CONCAT({expr})" if self.dialect == "sqlite" else f"STRING_AGG({expr}::text, ',')"

    def json_text(self, column: str, key: str) -> str:
        """A top-level JSON property as text (keys are internal identifiers, never user input)."""
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            raise ValueError(f"invalid JSON key {key!r}")
        return f"json_extract({column}, '$.{key}')" if self.dialect == "sqlite" else f"({column}::jsonb ->> '{key}')"

    def drop_search_rows(self, ids: list[str]) -> None:
        """Remove objects from the search index (retention purge)."""
        for i in range(0, len(ids), 400):
            chunk = ids[i : i + 400]
            q = ",".join("?" * len(chunk))
            if self.dialect == "sqlite":
                self.conn.execute(f"DELETE FROM objects_fts WHERE rowid IN (SELECT rowid FROM objects WHERE id IN ({q}))", chunk)
            else:
                self.conn.execute(f"DELETE FROM object_search WHERE id IN ({q})", chunk)

    def copy_to(self, target: Path | str) -> "Store":
        """A full, independent copy of this store (tests and adversary simulation work on copies)."""
        if self.dialect == "sqlite":
            dst = sqlite3.connect(str(target))
            with self._lock:
                self.conn.backup(dst)
            dst.close()
            return Store(target, self.ontology)
        other = Store(target, self.ontology)
        if not other.schema or not self.schema:
            raise ValueError("PostgreSQL copies need ?schema= on both targets")
        tables = [r[0] for r in self.conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema=? AND table_type='BASE TABLE'", (self.schema,))]
        with other._lock:
            other.conn.execute("SET session_replication_role = replica")  # no FK checks or triggers while copying
            try:
                for t in tables:
                    cols = [r[0] for r in other.conn.execute(
                        "SELECT column_name FROM information_schema.columns WHERE table_schema=? AND table_name=? AND is_generated='NEVER' "
                        "ORDER BY ordinal_position", (self.schema, t))]
                    collist = ",".join(cols)
                    other.conn.execute(f"DELETE FROM {other.schema}.{t}")
                    other.conn.execute(f"INSERT INTO {other.schema}.{t}({collist}) SELECT {collist} FROM {self.schema}.{t}")
                    for r in other.conn.execute(
                            "SELECT column_name FROM information_schema.columns WHERE table_schema=? AND table_name=? AND is_identity='YES'",
                            (other.schema, t)):
                        other.conn.execute(f"SELECT setval(pg_get_serial_sequence('{other.schema}.{t}', '{r[0]}'), "
                                           f"COALESCE((SELECT MAX({r[0]}) FROM {other.schema}.{t}), 0) + 1, false)")
            finally:
                other.conn.execute("SET session_replication_role = DEFAULT")
        return other

    # ------------------------------------------------------------------ plumbing
    @contextmanager
    def tx(self) -> Iterator[Any]:
        """Transaction; re-entrant, so a bulk ingest wrapped in tx() commits once at the end."""
        with self._lock:
            outer = self._depth == 0
            if outer:
                self.conn.execute("BEGIN")
            self._depth += 1
            try:
                yield self.conn
            except BaseException:
                self._depth -= 1
                if outer:
                    self.conn.execute("ROLLBACK")
                raise
            self._depth -= 1
            if outer:
                self.conn.execute("COMMIT")

    def execute(self, sql: str, params: Iterable[Any] = ()) -> Any:
        with self._lock:
            return self.conn.execute(sql, tuple(params))

    def executemany(self, sql: str, rows: Iterable[Iterable[Any]]) -> None:
        with self._lock:
            self.conn.executemany(sql, [tuple(r) for r in rows])

    def query(self, sql: str, params: Iterable[Any] = ()) -> list[Any]:
        with self._lock:
            return self.conn.execute(sql, tuple(params)).fetchall()

    def close(self) -> None:
        self.conn.close()

    # ------------------------------------------------------------------ objects
    def upsert_object(
        self,
        type_name: str,
        props: dict[str, Any],
        *,
        source: str,
        record: str,
        obj_id: str | None = None,
        confidence: float = 1.0,
        sensitivity: int | None = None,
        district_lgd: str | None = None,
        lat: float | None = None,
        lon: float | None = None,
        geom: dict | None = None,
        synthetic: bool = False,
        origin_case: str | None = None,
        legal_order: str | None = None,
    ) -> str:
        ot = self.ontology.object_type(type_name)
        self.ontology.validate_object(type_name, props)
        obj_id = obj_id or make_id(type_name, source, record)
        now = utcnow()
        clean = {k: v for k, v in props.items() if v not in (None, "")}
        with self._lock:
            existing = self.conn.execute("SELECT props FROM objects WHERE id=?", (obj_id,)).fetchone()
            merged = {**json.loads(existing["props"]), **clean} if existing else clean
            title = str(merged.get(ot.title, obj_id))
            district = district_lgd or merged.get("district_lgd")
            self.conn.execute(
                """INSERT INTO objects(id,type,title,props,sensitivity,district_lgd,lat,lon,geom,synthetic,origin_case,legal_order,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET title=excluded.title, props=excluded.props,
                     district_lgd=COALESCE(excluded.district_lgd, objects.district_lgd),
                     lat=COALESCE(excluded.lat, objects.lat), lon=COALESCE(excluded.lon, objects.lon),
                     geom=COALESCE(excluded.geom, objects.geom), updated_at=excluded.updated_at""",
                (
                    obj_id, type_name, title, json.dumps(merged, ensure_ascii=False),
                    ot.sensitivity if sensitivity is None else sensitivity, district, lat, lon,
                    json.dumps(geom) if geom else None, int(synthetic), origin_case, legal_order, now, now,
                ),
            )
            self.conn.executemany(
                "INSERT INTO provenance(object_id,prop,source,record,ingested_at,confidence) VALUES(?,?,?,?,?,?) "
                "ON CONFLICT(object_id,prop,source,record) DO UPDATE SET ingested_at=excluded.ingested_at, confidence=excluded.confidence",
                [(obj_id, k, source, record, now, confidence) for k in clean if not k.startswith("_")],
            )
            self._index(obj_id, type_name, merged)
        return obj_id

    def _index(self, obj_id: str, type_name: str, props: dict[str, Any]) -> None:
        """Search terms and identifiers for one object. The full-text row shares the object's rowid, so
        replacing it is a keyed lookup (an FTS5 UNINDEXED column cannot be searched without a full scan)."""
        body, idents = self._terms(type_name, props)
        if self.dialect == "sqlite":
            rowid = self.conn.execute("SELECT rowid FROM objects WHERE id=?", (obj_id,)).fetchone()[0]
            self.conn.execute("DELETE FROM objects_fts WHERE rowid=?", (rowid,))
            self.conn.execute("INSERT INTO objects_fts(rowid,id,type,body) VALUES(?,?,?,?)", (rowid, obj_id, type_name, body))
        else:
            self.conn.execute("INSERT INTO object_search(id,type,body) VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET type=excluded.type, body=excluded.body",
                              (obj_id, type_name, body))
        self.conn.execute("DELETE FROM identifiers WHERE object_id=?", (obj_id,))
        self.conn.executemany("INSERT INTO identifiers(kind,value,object_id) VALUES(?,?,?) ON CONFLICT DO NOTHING", [(k, v, obj_id) for k, v in idents])

    def _terms(self, type_name: str, props: dict[str, Any]) -> tuple[str, list[tuple[str, str]]]:
        ot = self.ontology.object_type(type_name)
        terms: list[str] = []
        idents: list[tuple[str, str]] = []
        for pname, pdef in ot.properties.items():
            value = props.get(pname)
            if value in (None, "") or not pdef.search:
                continue
            values = value if isinstance(value, list) else [value]
            for v in values:
                if pdef.search == "name":
                    terms += name_search_terms(str(v))
                elif pdef.search == "id":
                    norm = normalize_identifier(v)
                    terms.append(norm.lower())
                    idents.append((pname, norm))
                else:
                    terms.append(to_latin(str(v)))
        return " ".join(terms), idents

    def _rebuild_fts(self) -> int:
        """One-time migration: re-key the full-text index on object rowids."""
        n = 0
        sqlite = self.dialect == "sqlite"
        with self.tx() as conn:
            conn.execute("DELETE FROM objects_fts" if sqlite else "DELETE FROM object_search")
            batch = []
            for r in conn.execute(f"SELECT {'rowid' if sqlite else 'NULL AS rowid'}, id, type, props FROM objects").fetchall():
                body, _ = self._terms(r["type"], json.loads(r["props"]))
                batch.append((r["rowid"], r["id"], r["type"], body) if sqlite else (r["id"], r["type"], body))
                n += 1
            if sqlite:
                conn.executemany("INSERT INTO objects_fts(rowid,id,type,body) VALUES(?,?,?,?)", batch)
            else:
                conn.executemany("INSERT INTO object_search(id,type,body) VALUES(?,?,?)", batch)
            conn.execute("INSERT INTO meta(key,value) VALUES('fts_layout', '\"rowid\"') ON CONFLICT(key) DO UPDATE SET value=excluded.value")
        return n

    @staticmethod
    def _row_to_obj(row: Any) -> dict[str, Any]:
        return {
            "id": row["id"],
            "type": row["type"],
            "title": row["title"],
            "props": json.loads(row["props"]),
            "sensitivity": row["sensitivity"],
            "district_lgd": row["district_lgd"],
            "lat": row["lat"],
            "lon": row["lon"],
            "synthetic": bool(row["synthetic"]),
        }

    def get_object(self, obj_id: str, *, with_geom: bool = False) -> dict[str, Any] | None:
        rows = self.query("SELECT * FROM objects WHERE id=?", (obj_id,))
        if not rows:
            return None
        obj = self._row_to_obj(rows[0])
        if with_geom and rows[0]["geom"]:
            obj["geom"] = json.loads(rows[0]["geom"])
        return obj

    def get_objects(self, ids: Iterable[str]) -> dict[str, dict[str, Any]]:
        ids = list(dict.fromkeys(ids))
        out: dict[str, dict[str, Any]] = {}
        for i in range(0, len(ids), 500):
            chunk = ids[i : i + 500]
            for row in self.query(f"SELECT * FROM objects WHERE id IN ({','.join('?' * len(chunk))})", chunk):
                out[row["id"]] = self._row_to_obj(row)
        return out

    def objects_of_type(self, type_name: str, *, with_geom: bool = False) -> list[dict[str, Any]]:
        rows = self.query("SELECT * FROM objects WHERE type=?", (type_name,))
        out = []
        for r in rows:
            o = self._row_to_obj(r)
            if with_geom and r["geom"]:
                o["geom"] = json.loads(r["geom"])
            out.append(o)
        return out

    def provenance(self, obj_id: str) -> list[dict[str, Any]]:
        return [dict(r) for r in self.query("SELECT prop,source,record,ingested_at,confidence FROM provenance WHERE object_id=? ORDER BY prop", (obj_id,))]

    def count(self, type_name: str | None = None) -> int:
        if type_name:
            return self.query("SELECT COUNT(*) c FROM objects WHERE type=?", (type_name,))[0]["c"]
        return self.query("SELECT COUNT(*) c FROM objects")[0]["c"]

    # ------------------------------------------------------------------ links
    def upsert_link(
        self,
        link_type: str,
        src: str,
        dst: str,
        *,
        source: str,
        record: str,
        origin: str = "ingest",
        confidence: float = 1.0,
        status: str = "active",
        props: dict[str, Any] | None = None,
        validate: bool = True,
    ) -> str:
        with self._lock:
            if validate:
                types = {r["id"]: r["type"] for r in self.conn.execute("SELECT id,type FROM objects WHERE id IN (?,?)", (src, dst))}
                self.ontology.validate_link(link_type, types[src], types[dst])
            link_id = "link:" + hashlib.sha1(f"{link_type}|{src}|{dst}".encode()).hexdigest()[:16]
            now = utcnow()
            row = self.conn.execute("SELECT sources, props FROM links WHERE id=?", (link_id,)).fetchone()
            sources = json.loads(row["sources"]) if row else []
            ev = {"source": source, "record": record}
            if ev not in sources:
                sources.append(ev)
            merged = {**(json.loads(row["props"]) if row else {}), **(props or {})}
            self.conn.execute(
                """INSERT INTO links(id,type,src,dst,props,sources,origin,confidence,status,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET sources=excluded.sources, props=excluded.props,
                     confidence=""" + self.greatest("links.confidence", "excluded.confidence") + """, updated_at=excluded.updated_at""",
                (link_id, link_type, src, dst, json.dumps(merged, ensure_ascii=False), json.dumps(sources), origin, confidence, status, now, now),
            )
        return link_id

    def set_link_status(self, link_id: str, status: str) -> None:
        with self._lock:
            self.conn.execute("UPDATE links SET status=?, updated_at=? WHERE id=?", (status, utcnow(), link_id))

    def links_for(self, ids: Iterable[str], statuses: tuple[str, ...] = ("active", "auto", "confirmed")) -> list[dict[str, Any]]:
        ids = list(dict.fromkeys(ids))
        out: dict[str, dict[str, Any]] = {}
        st = ",".join("?" * len(statuses))
        for i in range(0, len(ids), 400):
            chunk = ids[i : i + 400]
            q = ",".join("?" * len(chunk))
            rows = self.query(
                f"SELECT * FROM links WHERE status IN ({st}) AND (src IN ({q}) OR dst IN ({q}))",
                (*statuses, *chunk, *chunk),
            )
            for r in rows:
                out[r["id"]] = self._row_to_link(r)
        return list(out.values())

    def get_link(self, link_id: str) -> dict[str, Any] | None:
        rows = self.query("SELECT * FROM links WHERE id=?", (link_id,))
        return self._row_to_link(rows[0]) if rows else None

    @staticmethod
    def _row_to_link(r: Any) -> dict[str, Any]:
        sources = json.loads(r["sources"])
        distinct = {s["source"] for s in sources}
        if r["origin"] in ("resolver", "ai") and r["status"] != "confirmed":
            evidence = "suggested"  # red: machine-proposed, not yet confirmed by a human
        elif len(distinct) >= 2 or r["status"] == "confirmed":
            evidence = "corroborated"  # green: two independent sources or human-confirmed
        else:
            evidence = "single"  # amber: one source
        return {
            "id": r["id"], "type": r["type"], "src": r["src"], "dst": r["dst"],
            "props": json.loads(r["props"]), "sources": sources, "origin": r["origin"],
            "confidence": r["confidence"], "status": r["status"], "evidence": evidence,
        }

    # ------------------------------------------------------------------ search
    def find_identifier(self, text: str) -> list[str]:
        norm = normalize_identifier(text)
        if len(norm) < 4:
            return []
        return [r["object_id"] for r in self.query("SELECT DISTINCT object_id FROM identifiers WHERE value=? LIMIT 50", (norm,))]

    def search(self, text: str, types: Iterable[str] | None = None, limit: int = 50) -> list[str]:
        """Return object ids matching a free-text query (names in any script, ids, text)."""
        hits = self.find_identifier(text)
        parsed = normalize_name(text)
        groups = []
        for tok, key in zip(parsed.tokens, parsed.keys):
            tok = re.sub(r"[^a-z0-9]", "", tok)
            if not tok:
                continue
            # prefix on the transliterated token OR the Indic phonetic key (Pateel finds Patil)
            alts = [f'"{tok}"*'] + ([f'"ph{key}"'] if key and len(key) >= 2 else [])
            groups.append("(" + " OR ".join(alts) + ")")
        type_list = list(types or [])
        type_sql = f" AND type IN ({','.join('?' * len(type_list))})" if type_list else ""
        if self.dialect == "postgres":  # tsquery: prefix terms "tok:*", alternatives with |, groups with & or |
            groups = ["(" + " | ".join(a.replace('"', "").replace("*", ":*") for a in g[1:-1].split(" OR ")) + ")" for g in groups]
        for joiner in ((" AND ", " OR ") if self.dialect == "sqlite" else (" & ", " | ")):
            if not groups or len(hits) >= limit:
                break
            if self.dialect == "sqlite":
                rows = self.query(
                    f"SELECT id FROM objects_fts WHERE objects_fts MATCH ?{type_sql} ORDER BY bm25(objects_fts) LIMIT ?",
                    (joiner.join(groups), *type_list, limit),
                )
            else:
                q = joiner.join(groups)
                rows = self.query(
                    f"SELECT id FROM object_search WHERE tsv @@ to_tsquery('simple', ?){type_sql} "
                    "ORDER BY ts_rank(tsv, to_tsquery('simple', ?)) DESC, id LIMIT ?",
                    (q, *type_list, q, limit),
                )
            hits += [r["id"] for r in rows if r["id"] not in hits]
            if hits:
                break
        if type_list and hits:
            objs = self.get_objects(hits)
            hits = [h for h in hits if h in objs and objs[h]["type"] in type_list]
        return hits[:limit]

    # ------------------------------------------------------------------ meta
    def set_meta(self, key: str, value: Any) -> None:
        with self._lock:
            self.conn.execute("INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, json.dumps(value)))

    def get_meta(self, key: str, default: Any = None) -> Any:
        rows = self.query("SELECT value FROM meta WHERE key=?", (key,))
        return json.loads(rows[0]["value"]) if rows else default

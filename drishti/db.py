"""Database connections: SQLite (laptop / offline edge kit) or PostgreSQL 18 + PostGIS + AGE (state).

All DRISHTI SQL is written once in the portable subset both engines accept
(`?` placeholders, `ON CONFLICT`, `RETURNING`). The PostgreSQL adapter rewrites `?` to `%s`
for psycopg. Engine-specific SQL (full-text search, triggers, geometry, the graph) lives
behind `Database.dialect` checks in store.py and graphdb.py.
"""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Iterator


class Database:
    dialect = "base"

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._depth = 0

    # subclasses implement _raw_execute / _raw_executemany / _begin / _commit / _rollback
    def execute(self, sql: str, params: Iterable[Any] = ()) -> Any:
        with self._lock:
            return self._raw_execute(sql, tuple(params))

    def executemany(self, sql: str, seq: Iterable[Iterable[Any]]) -> None:
        rows = [tuple(p) for p in seq]
        if rows:
            with self._lock:
                self._raw_executemany(sql, rows)

    def query(self, sql: str, params: Iterable[Any] = ()) -> list[Any]:
        with self._lock:
            return self._raw_execute(sql, tuple(params)).fetchall()

    @contextmanager
    def tx(self) -> Iterator["Database"]:
        """Re-entrant transaction: only the outermost block commits."""
        with self._lock:
            outer = self._depth == 0
            if outer:
                self._begin()
            self._depth += 1
            try:
                yield self
            except BaseException:
                self._depth -= 1
                if outer:
                    self._rollback()
                raise
            self._depth -= 1
            if outer:
                self._commit()

    def greatest(self, a: str, b: str) -> str:
        raise NotImplementedError


class SQLiteDB(Database):
    dialect = "sqlite"

    def __init__(self, path: Path):
        super().__init__()
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path), check_same_thread=False, isolation_level=None)
        self.conn.row_factory = sqlite3.Row

    def executescript(self, sql: str) -> None:
        with self._lock:
            self.conn.executescript(sql)

    def _raw_execute(self, sql: str, params: tuple) -> Any:
        return self.conn.execute(sql, params)

    def _raw_executemany(self, sql: str, rows: list[tuple]) -> None:
        self.conn.executemany(sql, rows)

    def _begin(self) -> None:
        self.conn.execute("BEGIN")

    def _commit(self) -> None:
        self.conn.execute("COMMIT")

    def _rollback(self) -> None:
        self.conn.execute("ROLLBACK")

    def greatest(self, a: str, b: str) -> str:
        return f"MAX({a}, {b})"

    def close(self) -> None:
        self.conn.close()

    def describe(self) -> str:
        return f"sqlite:{self.path}"


def _to_psycopg(sql: str) -> str:
    """Rewrite `?` placeholders to `%s` and escape literal `%`, outside quoted strings."""
    out, quote = [], None
    for ch in sql:
        if quote:
            out.append("%%" if ch == "%" else ch)
            if ch == quote:
                quote = None
        elif ch in ("'", '"'):
            quote = ch
            out.append(ch)
        elif ch == "?":
            out.append("%s")
        elif ch == "%":
            out.append("%%")
        else:
            out.append(ch)
    return "".join(out)


class PostgresDB(Database):
    dialect = "postgres"

    def __init__(self, url: str):
        super().__init__()
        import psycopg
        from psycopg.rows import dict_row

        self.url = url
        self.conn = psycopg.connect(url, autocommit=True, row_factory=dict_row)
        self._tx_ctx = None
        self.age = self._load_age()

    def _load_age(self) -> bool:
        try:
            self.conn.execute("CREATE EXTENSION IF NOT EXISTS age")
            self.conn.execute("LOAD 'age'")
            self.conn.execute('SET search_path = public, ag_catalog, "$user"')
            return True
        except Exception:  # noqa: BLE001 - AGE is optional; graph queries are disabled without it
            self.conn.execute('SET search_path = public, "$user"')
            return False

    def _raw_execute(self, sql: str, params: tuple) -> Any:
        return self.conn.execute(_to_psycopg(sql) if params else sql, params or None)

    def _raw_executemany(self, sql: str, rows: list[tuple]) -> None:
        with self.conn.cursor() as cur:
            cur.executemany(_to_psycopg(sql), rows)

    def _begin(self) -> None:
        self._tx_ctx = self.conn.transaction()
        self._tx_ctx.__enter__()

    def _commit(self) -> None:
        ctx, self._tx_ctx = self._tx_ctx, None
        ctx.__exit__(None, None, None)

    def _rollback(self) -> None:
        ctx, self._tx_ctx = self._tx_ctx, None
        ctx.__exit__(RuntimeError, RuntimeError("rollback"), None)

    def executescript(self, sql: str) -> None:
        with self._lock:
            self.conn.execute(sql)

    def greatest(self, a: str, b: str) -> str:
        return f"GREATEST({a}, {b})"

    def close(self) -> None:
        self.conn.close()

    def describe(self) -> str:
        info = self.conn.info
        return f"postgresql://{info.host}:{info.port}/{info.dbname}"


def connect(target: str | Path) -> Database:
    t = str(target)
    if t.startswith(("postgresql://", "postgres://")):
        return PostgresDB(t)
    return SQLiteDB(Path(t))

"""PostgreSQL behind the sqlite3 interface the rest of DRISHTI already uses.

The store and every module call `conn.execute(sql, params)` with `?` placeholders, iterate cursors, read
rows by column name or position, and catch sqlite3 errors. This module gives a psycopg connection that
interface, so one body of SQL serves both the laptop (SQLite) and a state deployment (PostgreSQL 18):

* `?` placeholders become `%s` (outside quoted strings; literal `%` is escaped)
* rows support row["col"], row[0], keys() and dict(row), like sqlite3.Row
* Decimal results (SUM/AVG of integers) come back as int or float, as SQLite returns them
* bool parameters are sent as 0/1, since DRISHTI's flag columns are integers
* psycopg errors are re-raised as the matching sqlite3 exception classes
* the few SQLite-only statement forms the tests use (DROP TRIGGER without ON) are rewritten

SQL that differs between the engines is chosen by `Store.dialect` in store.py, not translated here.
"""

from __future__ import annotations

import re
import sqlite3
from decimal import Decimal
from typing import Any, Iterable, Iterator

# triggers created by the schema, for "DROP TRIGGER name" (SQLite) -> "DROP TRIGGER name ON table"
TRIGGER_TABLES = {"audit_no_update": "audit", "audit_no_delete": "audit", "custody_no_update": "custody", "custody_no_delete": "custody"}


def to_psycopg(sql: str) -> str:
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


def _rewrite(sql: str) -> str:
    m = re.fullmatch(r"\s*DROP TRIGGER (?:IF EXISTS )?(\w+)\s*;?\s*", sql, re.I)
    if m and m.group(1) in TRIGGER_TABLES:
        return f"DROP TRIGGER IF EXISTS {m.group(1)} ON {TRIGGER_TABLES[m.group(1)]}"
    return sql


class Row(tuple):
    """A result row readable by position and by column name (like sqlite3.Row)."""

    __slots__ = ()
    _index: dict[str, int]

    def __new__(cls, values: Iterable[Any], index: dict[str, int]):
        row = super().__new__(cls, values)
        return row

    def __getitem__(self, key):  # type: ignore[override]
        if isinstance(key, str):
            return tuple.__getitem__(self, self._index[key])
        return tuple.__getitem__(self, key)

    def keys(self) -> list[str]:
        return list(self._index)


def _row_class(names: list[str]) -> type[Row]:
    return type("Row", (Row,), {"__slots__": (), "_index": {n: i for i, n in enumerate(names)}})


def _plain(v: Any) -> Any:
    if isinstance(v, Decimal):
        return int(v) if v == v.to_integral_value() else float(v)
    if isinstance(v, memoryview):
        return bytes(v)
    return v


def _row_factory(cursor):
    if cursor.description is None:
        return lambda values: values
    cls = _row_class([c.name for c in cursor.description])
    return lambda values: cls(tuple(_plain(v) for v in values), cls._index)


def _params(params: Iterable[Any] | None) -> tuple | None:
    if params is None:
        return None
    return tuple(int(p) if isinstance(p, bool) else p for p in params)


def _translate_error(exc: Exception) -> Exception:
    import psycopg

    msg = str(exc).strip()
    if isinstance(exc, psycopg.errors.IntegrityError):
        return sqlite3.IntegrityError(msg)
    if isinstance(exc, psycopg.errors.RaiseException):  # an append-only trigger refused the change
        return sqlite3.IntegrityError(msg)
    if isinstance(exc, psycopg.errors.OperationalError):
        return sqlite3.OperationalError(msg)
    if isinstance(exc, psycopg.errors.ProgrammingError):
        return sqlite3.OperationalError(msg)
    return sqlite3.DatabaseError(msg)


class Cursor:
    def __init__(self, cur):
        self._cur = cur

    def fetchone(self):
        return self._cur.fetchone() if self._cur.description else None

    def fetchall(self) -> list:
        return self._cur.fetchall() if self._cur.description else []

    def __iter__(self) -> Iterator:
        return iter(self.fetchall())

    @property
    def rowcount(self) -> int:
        return self._cur.rowcount

    @property
    def description(self):
        return self._cur.description


class Connection:
    """A psycopg connection with the sqlite3.Connection surface DRISHTI uses."""

    def __init__(self, url: str, schema: str | None = None):
        import psycopg

        self._pg = psycopg.connect(url, autocommit=True, row_factory=_row_factory)
        self.schema = schema
        if schema:
            if not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", schema):
                raise ValueError(f"invalid schema name {schema!r}")
            self._pg.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
            self._pg.execute(f"SET search_path TO {schema}, public")

    def execute(self, sql: str, params: Iterable[Any] = ()) -> Cursor:
        import psycopg

        sql = _rewrite(sql)
        p = _params(params)
        try:
            cur = self._pg.execute(to_psycopg(sql) if p else sql, p or None)
        except psycopg.Error as exc:
            raise _translate_error(exc) from exc
        return Cursor(cur)

    def executemany(self, sql: str, seq: Iterable[Iterable[Any]]) -> None:
        import psycopg

        rows = [_params(r) for r in seq]
        if not rows:
            return
        try:
            with self._pg.cursor() as cur:
                cur.executemany(to_psycopg(sql), rows)
        except psycopg.Error as exc:
            raise _translate_error(exc) from exc

    def executescript(self, sql: str) -> None:
        import psycopg

        try:
            self._pg.execute(sql)
        except psycopg.Error as exc:
            raise _translate_error(exc) from exc

    def close(self) -> None:
        self._pg.close()


def split_target(target: str) -> tuple[str, str | None]:
    """'postgresql://u:p@h:5544/db?schema=x' -> ('postgresql://u:p@h:5544/db', 'x')."""
    m = re.search(r"([?&])schema=([^&]+)", target)
    if not m:
        return target, None
    url = target[: m.start()] + (target[m.end():].replace("&", "?", 1) if m.group(1) == "?" else target[m.end():])
    return url.rstrip("?"), m.group(2)

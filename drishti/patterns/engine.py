"""Pattern engine: registered detectors over one shared, read-only feature plane.

Design (see docs/research/08):

  * A detector is a pure function Context -> list[Hit], registered with a declaration of what it
    asks of the data, which record features it reads, the algorithm, the evasion it is built to
    defeat, the look-alikes it must ignore, its known blind spots and its references.
  * The Context computes each shared index once per run (resolved identities, accounts by
    identity, SIM-handset graph, families, accused, CDR aggregates...). Detectors never query
    another detector's private state; compound detectors declare `depends` and read earlier hits.
  * Detectors may read person attributes only through `Context.person_attr`, which allows
    declared income and history-sheet number and refuses name, gender, age, religion, caste,
    community, nationality and place of origin. Tests also re-run the engine on a copy of the data
    with those attributes scrambled and require identical hits.
  * A hit is a lead: the pattern, its evidence, measurements and thresholds. Its id is stable
    across runs, so a reviewer's disposition survives recomputation. No score is stored on a
    person, and nothing predicts future conduct.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from functools import cached_property
from typing import Any

from ..analytics.inference import Resolver
from ..analytics.money import Ledger
from ..store import Store, utcnow

LIVE = ("active", "auto", "confirmed")
# Regulated institutions whose accounts end a money trace. A business label such as "merchant" is
# self-declared, so it exempts nothing: merchant-like accounts are recognised by behaviour instead.
REGULATED_KINDS = {"bank", "department", "crypto_exchange", "police_station"}
SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}

ALLOWED_PERSON_ATTRS = {"declared_income", "history_sheet_no"}
PROTECTED_ATTRS = {"name", "name_native", "father_name", "aliases", "gender", "dob", "age", "birth_year", "nationality",
                   "religion", "caste", "community", "address", "city", "district_lgd", "email", "occupation"}


class ProtectedAttributeError(PermissionError):
    pass


@dataclass
class Hit:
    detector: str
    key: str
    severity: str
    title: str
    summary: str  # may contain [[object_id]] tokens; the API renders them as names or pseudonyms
    subjects: list[str]
    evidence: dict[str, list[str]] = field(default_factory=dict)
    measurements: dict[str, Any] = field(default_factory=dict)
    thresholds: dict[str, Any] = field(default_factory=dict)
    window: tuple[str | None, str | None] = (None, None)
    district: str | None = None


@dataclass(frozen=True)
class DetectorSpec:
    id: str
    version: str
    title: str
    tracks: tuple[str, ...]
    scope: str  # population | seeded | compound
    question: str
    inputs: tuple[str, ...]
    algorithm: str
    evasion: tuple[str, ...]
    benign: tuple[str, ...]
    blind_spots: tuple[str, ...]
    references: tuple[str, ...]
    complexity: str
    depends: tuple[str, ...]
    fn: Callable[[Context], list[Hit]]

    def card(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("fn")
        return d


REGISTRY: dict[str, DetectorSpec] = {}


def detector(*, id: str, version: str, title: str, tracks: list[str], scope: str, question: str, inputs: list[str], algorithm: str,
             evasion: list[str], benign: list[str], blind_spots: list[str], references: list[str], complexity: str,
             depends: list[str] | None = None) -> Callable:
    def wrap(fn: Callable[[Context], list[Hit]]) -> Callable[[Context], list[Hit]]:
        bad = {i.split(".", 1)[1] for i in inputs if i.startswith("Person.")} - ALLOWED_PERSON_ATTRS
        if bad:
            raise ProtectedAttributeError(f"detector {id} declares protected person attributes {bad}")
        REGISTRY[id] = DetectorSpec(id, version, title, tuple(tracks), scope, question, tuple(inputs), algorithm, tuple(evasion),
                                    tuple(benign), tuple(blind_spots), tuple(references), complexity, tuple(depends or ()), fn)
        return fn
    return wrap


def ref(oid: str | None) -> str:
    return f"[[{oid}]]" if oid else "an unknown party"


def dt(ts: str) -> datetime:
    """Parse an ISO timestamp as naive UTC (sources mix offset and offset-less stamps)."""
    t = datetime.fromisoformat(ts)
    return t.astimezone(timezone.utc).replace(tzinfo=None) if t.tzinfo else t


def money(x: float) -> str:
    if x >= 1_00_00_000:
        return f"Rs {x / 1_00_00_000:.2f} crore"
    if x >= 1_00_000:
        return f"Rs {x / 1_00_000:.1f} lakh"
    return f"Rs {x:,.0f}"


class Context:
    """Read-only indexes shared by every detector in one run."""

    def __init__(self, store: Store, ledger: Ledger | None = None):
        self.s = store
        self.ontology = store.ontology
        self.L = ledger or Ledger(store)
        self.R = Resolver(store)
        self.hits: dict[str, list[Hit]] = {}
        stamps = [r["m"] for r in store.query(
            "SELECT MAX(ts) m FROM txns UNION ALL SELECT MAX(ts) FROM cdrs UNION ALL SELECT MAX(ts) FROM tollhits "
            "UNION ALL SELECT MAX(ts) FROM procurements") if r["m"]]
        self.today = max((dt(x) for x in stamps), default=datetime.now(timezone.utc).replace(tzinfo=None))

    # ------------------------------------------------------------------ guarded attribute access
    def person_attr(self, pid: str, attr: str) -> Any:
        if attr not in ALLOWED_PERSON_ATTRS:
            raise ProtectedAttributeError(f"detectors may not read Person.{attr}")
        people = self._props("Person")
        for rec in [pid, *self.cluster.get(self.R(pid), ())]:
            v = people.get(rec, {}).get(attr)
            if v not in (None, ""):
                return v
        return None

    @cached_property
    def cluster(self) -> dict[str, list[str]]:
        """Resolved identity -> every source record merged into it."""
        out: dict[str, list[str]] = defaultdict(list)
        for rec, rep in self.R.rep.items():
            out[rep].append(rec)
        return out

    def props(self, type_name: str) -> dict[str, dict[str, Any]]:
        if type_name == "Person":
            raise ProtectedAttributeError("person attributes are read only through Context.person_attr")
        return self._props(type_name)

    def _props(self, type_name: str) -> dict[str, dict[str, Any]]:
        cache = self.__dict__.setdefault("_props_cache", {})
        if type_name not in cache:
            rows = self.s.query("SELECT id, props FROM objects WHERE type=?", (type_name,))
            cache[type_name] = {r["id"]: json.loads(r["props"]) for r in rows}
        return cache[type_name]

    def org_attr(self, oid: str, attr: str) -> Any:
        return self.props("Organisation").get(oid, {}).get(attr)

    # ------------------------------------------------------------------ links
    @cached_property
    def links(self) -> dict[str, list[tuple[str, str, dict]]]:
        out: dict[str, list[tuple[str, str, dict]]] = defaultdict(list)
        for r in self.s.query("SELECT type, src, dst, props FROM links WHERE status IN ('active','auto','confirmed') AND type NOT IN "
                              "('transferred_to','called','inferred_association','located_in')"):
            out[r["type"]].append((r["src"], r["dst"], json.loads(r["props"] or "{}")))
        return out

    @cached_property
    def org_kind(self) -> dict[str, str]:
        return {k: v.get("kind", "") for k, v in self.props("Organisation").items()}

    @cached_property
    def hub_accounts(self) -> set[str]:
        """Accounts a trace does not follow: regulated institutions, and accounts that behave like a shop
        (50+ distinct payers, and less than 30% of inflow leaves within 72 hours)."""
        from .detectors.finance import _pass_through

        hubs = {a for a, h in self.L.holder.items() if self.org_kind.get(h) in REGULATED_KINDS}
        for a, ins in self.L.inc.items():
            payers = {t[2] for t in ins if t[2]}
            if len(payers) >= 50 and a not in hubs and _pass_through([t for t in ins if t[2]], self.L.out.get(a, [])) < 0.3:
                hubs.add(a)
        return hubs

    def identity(self, oid: str | None) -> str | None:
        """Resolved identity of a person record, or the object itself."""
        return self.R(oid) if oid else None

    def acct_identity(self, acct: str | None) -> str | None:
        h = self.L.holder.get(acct or "")
        return self.R(h) if h else None

    @cached_property
    def accounts_of(self) -> dict[str, set[str]]:
        out: dict[str, set[str]] = defaultdict(set)
        for t in ("holds_account", "signatory_of"):
            for a, b, _ in self.links.get(t, ()):
                out[self.R(a)].add(b)
        return out

    # ------------------------------------------------------------------ people and families
    @cached_property
    def family(self) -> dict[str, set[str]]:
        """Relatives on record plus people registered at the same small address (a household)."""
        fam: dict[str, set[str]] = defaultdict(set)
        for a, b, _ in self.links.get("relative_of", ()):
            fam[self.R(a)].add(self.R(b))
            fam[self.R(b)].add(self.R(a))
        at: dict[str, set[str]] = defaultdict(set)
        for p, loc, _ in self.links.get("resides_at", ()):
            at[loc].add(self.R(p))
        for ps in at.values():
            if 1 < len(ps) <= 8:
                for a in ps:
                    fam[a] |= ps - {a}
        return fam

    def related(self, a: str, b: str) -> bool:
        return b in self.family.get(a, set())

    @cached_property
    def accused(self) -> dict[str, set[str]]:
        out: dict[str, set[str]] = defaultdict(set)
        for p, inc, _ in self.links.get("accused_in", ()):
            if p.startswith("person:"):
                out[self.R(p)].add(inc)
        return out

    @cached_property
    def incident_accused(self) -> dict[str, set[str]]:
        out: dict[str, set[str]] = defaultdict(set)
        for p, incs in self.accused.items():
            for i in incs:
                out[i].add(p)
        return out

    @cached_property
    def victims(self) -> dict[str, set[str]]:
        out: dict[str, set[str]] = defaultdict(set)
        for t in ("complainant_in", "victim_in"):
            for p, inc, _ in self.links.get(t, ()):
                if p.startswith("person:"):
                    out[self.R(p)].add(inc)
        return out

    # ------------------------------------------------------------------ phones and handsets
    @cached_property
    def phone_number(self) -> dict[str, str]:
        return {k: v.get("number", "") for k, v in self.props("Phone").items()}

    @cached_property
    def number_phone(self) -> dict[str, str]:
        return {v: k for k, v in self.phone_number.items()}

    @cached_property
    def phone_users(self) -> dict[str, set[str]]:
        out: dict[str, set[str]] = defaultdict(set)
        for who, ph, _ in self.links.get("uses_phone", ()):
            if who.startswith("person:"):
                out[ph].add(self.R(who))
        return out

    @cached_property
    def person_phones(self) -> dict[str, set[str]]:
        out: dict[str, set[str]] = defaultdict(set)
        for ph, users in self.phone_users.items():
            for u in users:
                out[u].add(ph)
        return out

    def owner_of_number(self, number: str) -> str | None:
        users = self.phone_users.get(self.number_phone.get(number, ""), set())
        return next(iter(users)) if len(users) == 1 else None

    @cached_property
    def cdrs(self) -> list[tuple[str, str, str, str, int, str | None]]:
        return [(r["id"], r["ts"], r["a_number"], r["b_number"], r["duration_s"] or 0, r["tower_id"])
                for r in self.s.query("SELECT id, ts, a_number, b_number, duration_s, tower_id FROM cdrs ORDER BY ts")]

    @cached_property
    def towers(self) -> dict[str, dict[str, Any]]:
        return {r["id"]: dict(r) for r in self.s.query("SELECT * FROM towers")}

    # ------------------------------------------------------------------ movement
    @cached_property
    def reads(self) -> list[dict[str, Any]]:
        return [dict(r) for r in self.s.query("SELECT id, vehicle_id, ts, plaza, lat, lon, kind FROM tollhits ORDER BY ts")]

    @cached_property
    def vehicle_owner(self) -> dict[str, str]:
        return {v: self.R(o) for o, v, _ in self.links.get("owns", ()) if v.startswith("vehicle:")}

    # ------------------------------------------------------------------ incidents
    @cached_property
    def incidents(self) -> dict[str, dict[str, Any]]:
        return self.props("Incident")

    def incident_time(self, inc: str) -> datetime | None:
        t = self.incidents.get(inc, {}).get("occurred_at")
        return dt(t) if t else None

    # ------------------------------------------------------------------ cross-detector context
    def subjects_of(self, *detectors: str) -> set[str]:
        return {s for d in detectors for h in self.hits.get(d, []) for s in h.subjects}


# ---------------------------------------------------------------------------- running
def _order() -> list[DetectorSpec]:
    done: list[DetectorSpec] = []
    pending = dict(REGISTRY)
    while pending:
        ready = [d for d in pending.values() if all(x in {y.id for y in done} or x not in REGISTRY for x in d.depends)]
        if not ready:
            raise RuntimeError(f"detector dependency cycle among {sorted(pending)}")
        for d in sorted(ready, key=lambda d: d.id):
            done.append(d)
            pending.pop(d.id)
    return done


def hit_id(h: Hit) -> str:
    return "lead:" + hashlib.sha256(f"{h.detector}|{h.key}".encode()).hexdigest()[:20]


def data_fingerprint(store: Store) -> str:
    parts = []
    for t in ("objects", "links", "txns", "cdrs", "tollhits", "travel", "procurements", "bids"):
        r = store.query(f"SELECT COUNT(*) n FROM {t}")[0]
        parts.append(f"{t}:{r['n']}")
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:24]


def detect(store: Store, ledger: Ledger | None = None, only: list[str] | None = None) -> tuple[Context, dict[str, float]]:
    """Run detectors without persisting (used by tests and evaluation)."""
    from . import detectors  # noqa: F401  (registers every detector)

    ctx = Context(store, ledger)
    timings: dict[str, float] = {}
    for spec in _order():
        if only and spec.id not in only and spec.id not in {d for o in only for d in REGISTRY[o].depends}:
            continue
        t0 = time.perf_counter()
        hits = spec.fn(ctx)
        for h in hits:
            h.detector = spec.id
        ctx.hits[spec.id] = sorted(hits, key=lambda h: (SEVERITY_ORDER.get(h.severity, 9), h.key))
        timings[spec.id] = round(time.perf_counter() - t0, 3)
    return ctx, timings


def run_patterns(store: Store, ledger: Ledger | None = None, run_by: str = "system") -> dict[str, Any]:
    """Run every detector, persist hits as leads (keeping reviewers' dispositions), record the run."""
    started = utcnow()
    ctx, timings = detect(store, ledger)
    run_id = "run:" + hashlib.sha256(f"{started}|{run_by}".encode()).hexdigest()[:16]
    now = utcnow()
    rows, ids = [], set()
    for spec_id, hits in ctx.hits.items():
        spec = REGISTRY[spec_id]
        for h in hits:
            hid = hit_id(h)
            if hid in ids:
                continue
            ids.add(hid)
            rows.append((hid, run_id, spec_id, spec.version, json.dumps(spec.tracks), h.severity, h.title, h.summary,
                         json.dumps(sorted(dict.fromkeys(h.subjects), key=h.subjects.index)), json.dumps(h.evidence, default=str),
                         json.dumps(h.measurements, default=str), json.dumps(h.thresholds, default=str), h.window[0], h.window[1],
                         h.district, now, now))
    with store.tx() as conn:
        conn.execute("DELETE FROM pattern_hits WHERE status='open'")
        conn.executemany(
            """INSERT INTO pattern_hits(id,run_id,detector,version,tracks,severity,title,summary,subjects,evidence,measurements,thresholds,
                 window_start,window_end,district_lgd,first_seen,last_seen) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET run_id=excluded.run_id, version=excluded.version, severity=excluded.severity,
                 title=excluded.title, summary=excluded.summary, subjects=excluded.subjects, evidence=excluded.evidence,
                 measurements=excluded.measurements, thresholds=excluded.thresholds, window_start=excluded.window_start,
                 window_end=excluded.window_end, last_seen=excluded.last_seen""", rows)
        counts = {k: len(v) for k, v in ctx.hits.items()}
        conn.execute("INSERT INTO pattern_runs(id,started_at,finished_at,run_by,data_fingerprint,detectors,counts,timings) VALUES(?,?,?,?,?,?,?,?)",
                     (run_id, started, utcnow(), run_by, data_fingerprint(store), json.dumps({k: v.version for k, v in REGISTRY.items()}),
                      json.dumps(counts), json.dumps(timings)))
    return {"run": run_id, "leads": len(rows), "by_detector": {k: v for k, v in counts.items() if v}, "seconds": round(sum(timings.values()), 2)}


def catalog() -> list[dict[str, Any]]:
    from . import detectors  # noqa: F401

    return [REGISTRY[d.id].card() for d in _order()]


def within(ts: str, start: datetime, days: float) -> bool:
    t = dt(ts)
    return start <= t <= start + timedelta(days=days)

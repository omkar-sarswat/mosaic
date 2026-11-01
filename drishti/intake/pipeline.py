"""Intake: extract -> detect -> clean -> map -> match -> lenses -> proposal -> second-officer review -> publish.

The design follows the ontology-mapping principle (dataset -> object type, row -> object, column ->
property, cell -> property value, join -> link type) with three guarantees on top:

* Nothing an intake produces touches the ontology until a second officer approves the proposal; the
  proposal freezes the exact recipe, mapping and operations, so what is reviewed is what is published.
* Existing values are never overwritten. An incoming value fills a gap, corroborates the value on record,
  or is recorded as a conflict for a human to settle. Every change is written as a revision card (who,
  when, which source row, which order), so the publish can be reverted card by card.
* Identity is decided by shared identifiers, and conflicting identifiers are surfaced, not resolved
  silently. A name-and-city resemblance is only "probable": it becomes a new record plus a resolver
  candidate for the Resolve queue.

Interpretation lenses run over the cleaned, matched extract before anything is published: patterns
(shared identifiers, many records per person, document mismatches, repeat co-stays, recurring numbers
in seized notes), geography and the link graph the extract would add. Lenses are leads for the
reviewer, never findings.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
from collections import Counter, defaultdict
from typing import Any

from ..guard import PolicyError, User
from ..resolve.matcher import compare_names
from ..resolve.names import normalize_name
from ..store import Store, make_id, normalize_identifier, utcnow
from . import clean
from .sources import SOURCES, generate

# ---------------------------------------------------------------------------- mapping specs
# targets are "Type.property" in the ontology; "geo.city" places the record on the map; "context" is kept
# in lineage only. "switch" maps one column by the value of another (an ID column typed by an ID-type column).
SPECS: dict[str, dict[str, Any]] = {
    "kyc": {"types": ["Person", "Phone", "BankAccount"], "record": {"type": "BankAccount", "key": "account_no", "link": "holds_account"},
            "required": ["account_number", "customer_name"], "dedupe": ["account_number"], "classes": ["identity", "financial", "communications"],
            "mapping": {"account_number": ["BankAccount.account_no"], "ifsc_code": ["BankAccount.ifsc"], "customer_name": ["Person.name", "BankAccount.holder_name"],
                        "pan": ["Person.pan"], "mobile": ["Phone.number"], "date_of_birth": ["Person.dob"], "city": ["Person.city", "geo.city"],
                        "account_type": ["BankAccount.account_type"]},
            "recipe": {"account_type": ["null_placeholders", "account_type"]}},
    "rto": {"types": ["Person", "Phone", "Vehicle"], "record": {"type": "Vehicle", "key": "registration_no", "link": "owns"},
            "required": ["reg_no", "owner_name"], "dedupe": ["reg_no"], "classes": ["identity", "property_assets", "communications"],
            "mapping": {"reg_no": ["Vehicle.registration_no"], "owner_name": ["Person.name"], "owner_mobile": ["Phone.number"], "chassis_no": ["Vehicle.chassis_no"],
                        "engine_no": ["Vehicle.engine_no"], "maker_model": ["Vehicle.make"], "colour": ["Vehicle.colour"], "reg_date": ["context"],
                        "rto_city": ["Person.city", "geo.city"]},
            "recipe": {"colour": ["null_placeholders", "colour"], "maker_model": ["null_placeholders", "title_case"], "chassis_no": ["null_placeholders", "upper"],
                       "engine_no": ["null_placeholders", "upper"]}},
    "hotel": {"types": ["Person", "Phone", "Event"], "record": {"type": "Event", "key": None, "link": "participated_in"},
              "required": ["guest_name", "check_in"], "dedupe": ["guest_name", "check_in", "hotel"], "classes": ["identity", "documents", "communications"],
              "mapping": {"hotel": ["Event.location"], "hotel_city": ["geo.city"], "guest_name": ["Person.name"], "guest_mobile": ["Phone.number"], "id_type": ["context"],
                          "id_number": ["switch"], "check_in": ["Event.occurred_at"], "check_out": ["Event.ended_at"], "coming_from": ["Person.city"]},
              "switch": {"id_number": {"by": "id_type", "cases": {"PAN": "Person.pan", "Driving licence": "Person.dl_no", "Aadhaar": "check.aadhaar_last4"}}},
              "fixed": {"Event.kind": "hotel_stay"},
              "recipe": {"id_type": ["null_placeholders", "trim"], "id_number": ["null_placeholders", "id_document"], "hotel": ["null_placeholders", "trim"]}},
    "notes": {"types": ["Document", "Phone", "Vehicle", "BankAccount", "Person"], "record": {"type": "Document", "key": None, "link": "mentions"},
              "required": ["text"], "dedupe": ["text"], "classes": ["identity", "documents", "communications", "financial", "property_assets"],
              "mapping": {"page": ["Document.reference"], "written_on": ["Document.authored_at"], "text": ["Document.content"]},
              "recipe": {"text": ["null_placeholders", "trim"], "page": ["trim"]}},
}
COMPATIBLE = {"exact", "phonetic", "initials", "subset"}
ID_PROPS = {"pan", "dl_no", "account_no", "registration_no", "chassis_no", "engine_no", "number", "ifsc"}
NAME_PROPS = {"holder_name", "subscriber_name", "father_name"}


def suggested_recipe(profile: list[dict[str, Any]], source: str) -> list[dict[str, str]]:
    over = SPECS[source].get("recipe", {})
    out = []
    for col in profile:
        for st in over.get(col["column"], col["suggested"]):
            out.append({"column": col["column"], "step": st})
    return out


def mapping_options(store: Store, source: str) -> list[str]:
    ont = store.ontology
    opts = [f"{t}.{p}" for t in SPECS[source]["types"] for p in ont.object_type(t).properties if p not in ("aadhaar",)]
    return opts + ["geo.city", "context"]


def validate_mapping(store: Store, source: str, mapping: dict[str, list[str]]) -> list[str]:
    spec = SPECS[source]
    opts = set(mapping_options(store, source)) | {"switch"}
    errs = [f"{c}: {t} is not a property of {', '.join(spec['types'])}" for c, ts in mapping.items() for t in ts if t not in opts]
    rec = spec["record"]
    if rec["key"] and not any(f"{rec['type']}.{rec['key']}" in ts for ts in mapping.values()):
        errs.append(f"one column must map to {rec['type']}.{rec['key']} (the record key)")
    if source != "notes" and not any("Person.name" in ts for ts in mapping.values()):
        errs.append("one column must map to Person.name")
    if any("Person.aadhaar" in ts for ts in mapping.values()):
        errs.append("full Aadhaar numbers are never stored; only the last four digits are compared")
    return errs


# ---------------------------------------------------------------------------- lookups
class Lookup:
    """Read-only views of the store used for matching; built once per run."""

    def __init__(self, store: Store):
        self.s = store
        self.city_xy: dict[str, tuple[float, float]] = {}
        acc: dict[str, list[tuple[float, float]]] = defaultdict(list)
        for r in store.query("SELECT props, lat, lon FROM objects WHERE type='Location' AND lat IS NOT NULL"):
            c = json.loads(r["props"]).get("city")
            if c:
                acc[c].append((r["lat"], r["lon"]))
        for c, pts in acc.items():
            self.city_xy[c] = (round(sum(p[0] for p in pts) / len(pts), 4), round(sum(p[1] for p in pts) / len(pts), 4))
        self._props: dict[str, dict[str, Any]] = {}

    def props(self, oid: str) -> dict[str, Any]:
        if oid not in self._props:
            o = self.s.get_object(oid)
            self._props[oid] = o["props"] if o else {}
        return self._props[oid]

    def by_ident(self, kind: str, value: Any, prefix: str = "") -> list[str]:
        rows = self.s.query("SELECT object_id FROM identifiers WHERE kind=? AND value=?", (kind, normalize_identifier(value)))
        return sorted(r["object_id"] for r in rows if r["object_id"].startswith(prefix))

    def holders(self, oid: str, link: str) -> list[str]:
        return sorted(r["src"] for r in self.s.query("SELECT src FROM links WHERE type=? AND dst=? AND src LIKE 'person:%'", (link, oid)))

    def phone_users(self, number: str) -> tuple[str | None, list[str]]:
        ph = self.by_ident("number", number, "phone:")
        return (ph[0], self.holders(ph[0], "uses_phone")) if ph else (None, [])


def name_level(a: str, b: str) -> str:
    return compare_names(normalize_name(str(a)), normalize_name(str(b)))


def _raw_tokens(n: str) -> list[str]:
    return [t for t in re.split(r"[^a-z]+", str(n).lower()) if t]


def names_compatible(a: str, b: str) -> bool:
    """compare_names, plus initials read against the spelling as written: the canonical form of
    Dnyaneshwar is Gyaneshwar, but on a KYC form he is still D. A. Sawant."""
    if name_level(a, b) in COMPATIBLE:
        return True
    ta, tb = _raw_tokens(a), _raw_tokens(b)
    for short, full in ((ta, tb), (tb, ta)):
        inits = [t for t in short if len(t) == 1]
        words = [t for t in short if len(t) > 1]
        rest = [t for t in full if t not in words]
        if inits and words and all(w in full for w in words) and len(rest) == len(inits) and sorted(t[0] for t in rest) == sorted(inits):
            return True
    return False


def _norm(prop: str, v: Any) -> str:
    if v is None:
        return ""
    if prop in ID_PROPS:
        return normalize_identifier(v)
    if prop in ("dob", "occurred_at", "ended_at", "authored_at"):
        return str(v)[:10]
    return re.sub(r"\s+", " ", str(v)).strip().lower()


# ---------------------------------------------------------------------------- per-row typing
def row_props(source: str, mapping: dict[str, list[str]], v: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], str | None, dict[str, Any]]:
    spec = SPECS[source]
    out: dict[str, dict[str, Any]] = defaultdict(dict)
    geo, checks = None, {}
    for col, targets in mapping.items():
        val = v.get(col)
        if val in (None, ""):
            continue
        for t in targets:
            if t == "geo.city":
                geo = str(val)
            elif t == "switch":
                sw = spec["switch"][col]
                tgt = sw["cases"].get(str(v.get(sw["by"]) or ""))
                if tgt == "check.aadhaar_last4":
                    checks["aadhaar_last4"] = clean.digits(val)[-4:]
                elif tgt == "Person.pan" and not re.fullmatch(r"[A-Z]{3}[PCHFATBLJG][A-Z][0-9]{4}[A-Z]", str(val)):
                    continue
                elif tgt:
                    typ, prop = tgt.split(".")
                    out[typ][prop] = val
            elif t != "context":
                typ, prop = t.split(".")
                out[typ][prop] = val
    for t, val in spec.get("fixed", {}).items():
        typ, prop = t.split(".")
        out[typ][prop] = val
    if source == "hotel":
        ev = out["Event"]
        ev["title"] = f"Hotel stay: {ev.get('location', 'hotel')}"
        if ev.get("occurred_at"):
            ev["occurred_at"] = f"{ev['occurred_at']}T08:30:00+00:00"  # 14:00 IST check-in
        if ev.get("ended_at"):
            ev["ended_at"] = f"{ev['ended_at']}T05:30:00+00:00"  # 11:00 IST check-out
        if v.get("id_type"):
            shown = clean.apply_step("id_document", v.get("id_number"))[0] if v.get("id_number") else None
            ev["summary"] = f"Guest register entry; {v['id_type']} shown{': ' + str(shown) if shown else ''}"
    if "Phone" in out and not re.fullmatch(r"^[6-9][0-9]{9}$|^\+[1-9][0-9]{7,14}$", str(out["Phone"].get("number", ""))):
        out.pop("Phone")
    return out, geo, checks


# ---------------------------------------------------------------------------- matching
def match_row(lk: Lookup, source: str, typed: dict[str, dict[str, Any]], checks: dict[str, Any]) -> dict[str, Any]:
    """Gather every identifier hit; agreeing identifiers decide, disagreeing ones are reported."""
    spec = SPECS[source]
    rec = spec["record"]
    person = typed.get("Person", {})
    name = person.get("name", "")
    hits: dict[str, list[str]] = defaultdict(list)
    clashes: list[dict[str, Any]] = []
    record_id = None
    if rec["key"] and typed.get(rec["type"], {}).get(rec["key"]):
        found = lk.by_ident(rec["key"], typed[rec["type"]][rec["key"]], rec["type"].lower() + ":")
        record_id = found[0] if found else None
        for pid in lk.holders(record_id, rec["link"]) if record_id else []:
            hits[pid].append(f"{rec['type']} {rec['key'].replace('_', ' ')} on record")
    if person.get("pan"):
        for pid in lk.by_ident("pan", person["pan"], "person:"):
            hits[pid].append("PAN on record")
    if person.get("dl_no"):
        for pid in lk.by_ident("dl_no", person["dl_no"], "person:"):
            hits[pid].append("driving licence on record")
    phone_id, users = lk.phone_users(typed["Phone"]["number"]) if typed.get("Phone") else (None, [])
    for pid in users:
        hits[pid].append("mobile number on record")
    if not hits:
        if name:
            for cand in lk.s.search(str(name), types=["Person"], limit=8):
                p = lk.props(cand)
                lvl = name_level(name, p.get("name", ""))
                if lvl in COMPATIBLE and person.get("city") and _norm("city", p.get("city")) == _norm("city", person.get("city")):
                    return {"status": "probable", "basis": f"name ({lvl}) and city match; no shared identifier", "person": cand, "record": record_id, "phone": phone_id, "clashes": []}
        return {"status": "new", "basis": "no shared identifier on record", "person": None, "record": record_id, "phone": phone_id, "clashes": []}
    ok = {pid: b for pid, b in hits.items() if names_compatible(name, lk.props(pid).get("name", ""))}
    if not ok and len(hits) == 1 and len(set(next(iter(hits.values())))) >= 2:
        ok = dict(hits)  # two independent identifiers agree on one person; the name is just written differently
    pick = max(ok, key=lambda p: (len(ok[p]), p)) if ok else None
    suspect: set[str] = set()
    for pid, b in hits.items():
        if pid != pick:
            clashes.append({"person": pid, "basis": b, "name_on_record": lk.props(pid).get("name")})
            suspect |= {"pan" for x in b if x.startswith("PAN")} | {"dl_no" for x in b if x.startswith("driving")}
    if checks.get("aadhaar_last4") and pick:
        rec_a = str(lk.props(pick).get("aadhaar") or "")
        if rec_a and rec_a[-4:] != checks["aadhaar_last4"]:
            clashes.append({"person": pick, "basis": ["Aadhaar shown ends differently from the record"], "name_on_record": lk.props(pick).get("name")})
    if pick is None:
        return {"status": "new", "basis": "identifiers on record belong to differently named people", "person": None, "record": record_id, "phone": phone_id,
                "clashes": clashes, "suspect": sorted(suspect)}
    return {"status": "existing", "basis": "; ".join(sorted(set(ok[pick]))), "person": pick, "record": record_id, "phone": phone_id, "clashes": clashes, "suspect": sorted(suspect)}


class _UF:
    def __init__(self) -> None:
        self.p: dict[Any, Any] = {}

    def find(self, x: Any) -> Any:
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a: Any, b: Any) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[max(ra, rb)] = min(ra, rb)


def resolve_new(rows: list[dict[str, Any]]) -> dict[int, int]:
    """Entity resolution inside the extract for rows not on record: same PAN, or same mobile with a
    compatible name, or the same full name and date of birth. Returns row -> cluster root row."""
    uf = _UF()
    fresh = [r for r in rows if r["match"]["status"] != "existing" and r["typed"].get("Person", {}).get("name")]
    by_key: dict[tuple, list[dict]] = defaultdict(list)
    for r in fresh:
        p = r["typed"]["Person"]
        uf.find(r["row"])
        if p.get("pan"):
            by_key[("pan", normalize_identifier(p["pan"]))].append(r)
        if r["typed"].get("Phone"):
            by_key[("phone", r["typed"]["Phone"]["number"])].append(r)
        if p.get("dob"):
            by_key[("name_dob", " ".join(sorted(normalize_name(p["name"]).tokens)), p["dob"])].append(r)
    for key, grp in by_key.items():
        for a in grp[1:]:
            if key[0] != "phone" or names_compatible(a["typed"]["Person"]["name"], grp[0]["typed"]["Person"]["name"]):
                uf.union(grp[0]["row"], a["row"])
    return {r["row"]: uf.find(r["row"]) for r in fresh}


# ---------------------------------------------------------------------------- notes: tagging
TAG_KINDS = {"phone": ("number", "phone:", "uses_phone"), "vehicle_reg": ("registration_no", "vehicle:", "owns"), "account_no": ("account_no", "bankaccount:", "holds_account")}


def tag_notes(lk: Lookup, rows: list[dict[str, Any]]) -> None:
    """Tag identifiers and names in free text, resolve identifiers against the record, and accept a
    written name only when an identifier on the same page belongs to a person with that name."""
    for r in rows:
        tags = clean.extract_entities(str(r["values"].get("text") or ""))
        people_here: dict[str, list[str]] = defaultdict(list)
        for t in tags:
            t["object"], t["owners"] = None, []
            if t["kind"] in TAG_KINDS:
                ident, prefix, link = TAG_KINDS[t["kind"]]
                found = lk.by_ident(ident, t["value"], prefix)
                if found:
                    t["object"] = found[0]
                    t["owners"] = lk.holders(found[0], link)
                    for pid in t["owners"]:
                        people_here[pid].append(t["text"])
            elif t["kind"] == "pan":
                found = lk.by_ident("pan", t["value"], "person:")
                if found:
                    t["object"] = found[0]
                    people_here[found[0]].append(t["text"])
        for t in tags:
            if t["kind"] != "name":
                continue
            keys = set(normalize_name(t["text"]).keys)
            for pid in people_here:
                if keys and keys <= set(normalize_name(lk.props(pid).get("name", "")).keys):
                    t["object"], t["basis"] = pid, f"written next to {', '.join(people_here[pid][:2])}, which is on record for this person"
                    break
        r["tags"] = tags


# ---------------------------------------------------------------------------- run (read-only)
def run(store: Store, source: str, recipe: list[dict[str, str]] | None = None, mapping: dict[str, list[str]] | None = None) -> dict[str, Any]:
    """Detect, clean, dedupe, map, match and interpret one extract. Writes nothing."""
    spec = SPECS[source]
    ext = generate(store, source)
    prof = clean.profile(ext["columns"], ext["rows"])
    recipe = recipe or suggested_recipe(prof, source)
    mapping = mapping or spec["mapping"]
    errors = validate_mapping(store, source, mapping)
    res = clean.apply_recipe(ext["rows"], recipe, spec["required"])
    kept, dups = clean.dedupe(res["clean"], spec["dedupe"])
    lk = Lookup(store)
    rows = []
    for r in kept:
        typed, geo, checks = row_props(source, mapping, r["values"])
        rows.append({"row": r["row"], "values": r["values"], "typed": typed, "geo": geo, "checks": checks})
    clusters: dict[int, int] = {}
    if source == "notes":
        tag_notes(lk, rows)
        for r in rows:
            r["match"] = {"status": "new", "basis": "a new document", "person": None, "record": None, "phone": None, "clashes": []}
    else:
        for r in rows:
            r["match"] = match_row(lk, source, r["typed"], r["checks"])
        clusters = resolve_new(rows)
    for r in rows:
        r["identity"] = r["match"]["person"] if r["match"]["status"] == "existing" else f"new:{clusters.get(r['row'], r['row'])}"
    ops = plan(lk, source, rows, clusters) if not errors else []
    sensitive = {c["column"] for c in prof if c["detected"] in clean.SENSITIVE_KINDS}
    mk = lambda col, v: clean.mask_raw(v) if col in sensitive or col == "text" else v  # noqa: E731
    summary = {"rows": len(ext["rows"]), "clean": len(kept), "quarantined": len(res["quarantine"]), "duplicates": len(dups), "cells_changed": len(res["changes"]),
               "existing": sum(r["match"]["status"] == "existing" for r in rows), "probable": sum(r["match"]["status"] == "probable" for r in rows),
               "new": sum(r["match"]["status"] == "new" for r in rows), "identities": len({r["identity"] for r in rows}),
               "ops": dict(Counter(o["op"] for o in ops)), "creates": dict(Counter(o["type"] for o in ops if o["op"] == "create"))}
    lenses = interpret(lk, source, rows, ops)
    return {
        "source": source, **{k: ext[k] for k in ("title", "holder", "legal", "description", "kind", "columns")},
        "classes": spec["classes"], "profile": prof, "recipe": recipe, "steps": {k: v["label"] for k, v in clean.STEPS.items()},
        "mapping": mapping, "mapping_options": mapping_options(store, source), "mapping_errors": errors, "record": spec["record"], "switch": spec.get("switch", {}),
        "sample": [{c: mk(c, v) for c, v in x.items()} for x in ext["rows"][:60]],
        "changes": [ch | {"before": mk(ch["column"], ch["before"]), "after": mk(ch["column"], ch["after"])} for ch in res["changes"][:600]],
        "quarantine": [q | {"values": {c: mk(c, v) for c, v in q["values"].items()}} for q in res["quarantine"]], "duplicates": dups,
        "rows": [{"row": r["row"], "values": {c: mk(c, v) for c, v in r["values"].items()}, "match": r["match"], "identity": r["identity"], "tags": r.get("tags", [])} for r in rows],
        "ops": ops, "summary": summary, "lenses": lenses,
        "lineage": [
            {"stage": "Extract", "label": "Rows received", "n": len(ext["rows"])},
            {"stage": "Detect", "label": "Columns typed", "n": sum(1 for c in prof if c["detected"] != "text")},
            {"stage": "Transform", "label": "Cells cleaned", "n": len(res["changes"])},
            {"stage": "Quarantine", "label": "Rows held back", "n": len(res["quarantine"])},
            {"stage": "Dedupe", "label": "Duplicates dropped", "n": len(dups)},
            *([{"stage": "Parse", "label": "Entities tagged", "n": sum(len(r.get("tags", [])) for r in rows)}] if source == "notes" else []),
            {"stage": "Match", "label": "Rows tied to records", "n": summary["existing"]},
            {"stage": "Ontology", "label": "Changes proposed", "n": sum(1 for o in ops if o["op"] in ("create", "fill", "alias", "link", "candidate"))},
        ],
        "fingerprint": hashlib.sha256(json.dumps([ext["rows"], recipe, mapping], sort_keys=True, default=str).encode()).hexdigest()[:16],
    }


# ---------------------------------------------------------------------------- plan
def _diff(lk: Lookup, typ: str, oid: str, incoming: dict[str, Any], record: str) -> list[dict[str, Any]]:
    cur = lk.props(oid)
    ops = []
    for prop, val in incoming.items():
        if val in (None, "") or prop.startswith("_"):
            continue
        old = cur.get(prop)
        if typ == "Person" and prop == "name":
            if name_level(val, old or "") != "exact" and val not in (cur.get("aliases") or []):
                ops.append({"op": "alias", "type": typ, "id": oid, "prop": "aliases", "value": val, "old": old, "record": record})
            continue
        if prop in NAME_PROPS and old not in (None, "") and names_compatible(val, old):
            ops.append({"op": "corroborate", "type": typ, "id": oid, "prop": prop, "value": val, "old": old, "record": record})
            continue
        if old in (None, ""):
            ops.append({"op": "fill", "type": typ, "id": oid, "prop": prop, "value": val, "old": None, "record": record})
        elif _norm(prop, old) == _norm(prop, val):
            ops.append({"op": "corroborate", "type": typ, "id": oid, "prop": prop, "value": val, "old": old, "record": record})
        else:
            ops.append({"op": "conflict", "type": typ, "id": oid, "prop": prop, "value": val, "old": old, "record": record})
    return ops


def plan(lk: Lookup, source: str, rows: list[dict[str, Any]], clusters: dict[int, int]) -> list[dict[str, Any]]:
    """The exact operations a publish will apply, in order."""
    rec = SPECS[source]["record"]
    ops: list[dict[str, Any]] = []
    made_people: dict[int, str] = {}
    made_phones: dict[str, str] = {}
    planned: dict[tuple[str, str], Any] = {}  # (object, property) -> value already proposed by an earlier row
    said: set[tuple] = set()

    def add_diff(o: dict[str, Any]) -> None:
        """Several rows about one record yield one operation each; a later row that disagrees with an
        earlier row's proposed fill becomes a conflict instead of a second fill."""
        k = (o["id"], o["prop"])
        if o["op"] == "fill":
            if k in planned:
                if _norm(o["prop"], planned[k]) == _norm(o["prop"], o["value"]):
                    return
                o = o | {"op": "conflict", "old": planned[k]}
            else:
                planned[k] = o["value"]
        sig = (o["op"], o["id"], o["prop"], _norm(o["prop"] or "", o["value"]))
        if sig in said:
            return
        said.add(sig)
        ops.append(o)

    def phone_of(num: str, record: str) -> str:
        existing, _ = lk.phone_users(num)
        if existing:
            return existing
        if num not in made_phones:
            made_phones[num] = make_id("Phone", "INTAKE", num)
            ops.append({"op": "create", "type": "Phone", "id": made_phones[num], "props": {"number": num}, "record": record})
        return made_phones[num]

    def link(typ: str, src: str, dst: str, record: str) -> None:
        ops.append({"op": "link", "type": typ, "src": src, "dst": dst, "record": record})

    if source == "notes":
        for r in rows:
            key = f"notes#{r['row']}"
            v = r["values"]
            doc = make_id("Document", f"INTAKE/{source}", f"{key}|{hashlib.sha1(str(v.get('text')).encode()).hexdigest()[:8]}")
            props = {"title": f"Seized diary, page {v.get('page')}", "content": clean.mask_raw(v.get("text")), "category": "seized_diary",
                     "reference": f"page {v.get('page')}", **({"authored_at": f"{v['written_on']}T00:00:00+00:00"} if v.get("written_on") else {})}
            ops.append({"op": "create", "type": "Document", "id": doc, "props": props, "record": key})
            seen: set[str] = set()
            for t in r["tags"]:
                target = t.get("object")
                if not target and t["kind"] == "phone" and re.fullmatch(r"[6-9][0-9]{9}", t["value"]):
                    target = phone_of(t["value"], key)
                if target and target not in seen:
                    seen.add(target)
                    link("mentions", doc, target, key)
        return ops

    for r in rows:
        key = f"{source}#{r['row']}"
        t, mt = r["typed"], r["match"]
        person_props = t.get("Person", {})
        person_props = {k: v for k, v in person_props.items() if k not in mt.get("suspect", [])}
        if mt["status"] == "existing":
            person = mt["person"]
            for o in _diff(lk, "Person", person, person_props, key):
                add_diff(o)
        else:
            root = clusters.get(r["row"], r["row"])
            if root not in made_people:
                made_people[root] = make_id("Person", f"INTAKE/{source}", f"{source}#{root}")
                merged: dict[str, Any] = {}
                for other in rows:
                    if clusters.get(other["row"]) == root:
                        for k2, v2 in other["typed"].get("Person", {}).items():
                            merged.setdefault(k2, v2)
                ops.append({"op": "create", "type": "Person", "id": made_people[root], "props": merged, "record": key})
                if mt["status"] == "probable":
                    ops.append({"op": "candidate", "a": made_people[root], "b": mt["person"], "basis": mt["basis"], "record": key})
            person = made_people[root]
        rprops = dict(t.get(rec["type"], {}))
        if rec["type"] == "Event" and r["geo"] in lk.city_xy:
            rprops |= {"_lat": lk.city_xy[r["geo"]][0], "_lon": lk.city_xy[r["geo"]][1]}
        if mt.get("record"):
            rid = mt["record"]
            for o in _diff(lk, rec["type"], rid, rprops, key):
                add_diff(o)
        else:
            rid = make_id(rec["type"], f"INTAKE/{source}", key)
            ops.append({"op": "create", "type": rec["type"], "id": rid, "props": rprops, "record": key})
        link(rec["link"], person, rid, key)
        if t.get("Phone"):
            link("uses_phone", person, phone_of(t["Phone"]["number"], key), key)
    return ops


# ---------------------------------------------------------------------------- lenses
def interpret(lk: Lookup, source: str, rows: list[dict[str, Any]], ops: list[dict[str, Any]]) -> dict[str, Any]:
    pats: list[dict[str, Any]] = []
    label = {r["identity"]: (r["typed"].get("Person", {}).get("name") or "?") for r in rows}
    status = {r["identity"]: r["match"]["status"] for r in rows}

    def party(i: str) -> dict[str, Any]:
        return {"key": i, "label": label.get(i, "?"), "status": status.get(i, "new"), "person": None if str(i).startswith("new:") else i}

    gnodes: dict[str, dict[str, Any]] = {}
    glinks: list[dict[str, Any]] = []

    def gnode(nid: str, lbl: str, kind: str, st: str = "", from_record: bool = False) -> str:
        gnodes.setdefault(nid, {"id": nid, "label": lbl, "kind": kind, "status": st, "from_record": from_record})
        return nid

    def actor(i: str) -> str:
        return gnode(str(i), label.get(i, "?"), "actor", status.get(i, ""))

    if source != "notes":
        # 1. one identifier, several identities (mule accounts, shared SIMs, cloned chassis)
        for kind, getter, title in (
            ("mobile", lambda r: (r["typed"].get("Phone") or {}).get("number"), "One mobile number, {n} different people"),
            ("PAN", lambda r: (r["typed"].get("Person") or {}).get("pan"), "One PAN, {n} different people"),
            ("chassis", lambda r: (r["typed"].get("Vehicle") or {}).get("chassis_no"), "One chassis number on {n} registrations"),
            ("engine", lambda r: (r["typed"].get("Vehicle") or {}).get("engine_no"), "One engine number on {n} registrations"),
        ):
            groups: dict[str, list[dict]] = defaultdict(list)
            for r in rows:
                v = getter(r)
                if v:
                    groups[normalize_identifier(v)].append(r)
            for val, grp in groups.items():
                person_level = kind in ("mobile", "PAN")
                ids = sorted({r["identity"] for r in grp}) if person_level else sorted({(r["typed"].get("Vehicle") or {}).get("registration_no") for r in grp})
                if len(ids) < 2:
                    continue
                masked = val[:2] + "…" + val[-4:]
                pats.append({"id": f"shared_{kind}_{val[-6:]}", "kind": "shared_identifier", "severity": "review", "title": title.format(n=len(ids)),
                             "detail": f"{kind[0].upper() + kind[1:]} {masked} appears on {len(grp)} rows under {len(ids)} different {'names' if person_level else 'registrations'}.",
                             "benign": "A family or office line, or a dealer's number entered for customers." if kind == "mobile" else "A data-entry error at the source.",
                             "rows": [r["row"] for r in grp], "parties": [party(i) for i in ids] if person_level else [{"key": i, "label": i, "status": "", "person": None} for i in ids]})
                hub = gnode(f"{kind}:{val}", f"{kind} {masked}", "comms" if kind == "mobile" else "asset")
                for r in grp:
                    if person_level:
                        glinks.append({"source": actor(r["identity"]), "target": hub, "label": kind})
                    else:
                        reg = str((r["typed"].get("Vehicle") or {}).get("registration_no"))
                        glinks.append({"source": gnode(f"rec:{reg}", reg, "asset"), "target": hub, "label": kind})
                        glinks.append({"source": actor(r["identity"]), "target": f"rec:{reg}", "label": "owns"})
        # 2. many records for one identity
        if SPECS[source]["record"]["type"] in ("BankAccount", "Vehicle"):
            per: dict[str, list[dict]] = defaultdict(list)
            for r in rows:
                per[r["identity"]].append(r)
            for ident, grp in per.items():
                if len(grp) < 3:
                    continue
                what = "accounts" if source == "kyc" else "vehicles"
                branches = sorted({str(r["values"].get("ifsc_code") or "") for r in grp} - {""})
                pats.append({"id": f"many_{str(ident)[-8:]}", "kind": "many_records", "severity": "review", "title": f"One person, {len(grp)} {what} in this extract",
                             "detail": f"{label.get(ident)} appears on {len(grp)} rows" + (f" across {len(branches)} branches." if source == "kyc" else "."),
                             "benign": "Business owners and families often hold several accounts or vehicles.", "rows": [r["row"] for r in grp], "parties": [party(ident)]})
                for r in grp:
                    k = str((r["typed"].get("BankAccount") or {}).get("account_no") or (r["typed"].get("Vehicle") or {}).get("registration_no"))
                    glinks.append({"source": actor(ident), "target": gnode(f"rec:{k}", ("A/c ··" + k[-4:]) if source == "kyc" else k, "money" if source == "kyc" else "asset"),
                                   "label": "holds" if source == "kyc" else "owns"})
        # 3. identifiers that point at someone else on record
        for r in rows:
            for c in r["match"].get("clashes", []):
                aadhaar = "Aadhaar" in " ".join(c["basis"])
                pats.append({"id": f"clash_{r['row']}_{c['person'][-6:]}", "kind": "document_mismatch", "severity": "review",
                             "title": "Aadhaar digits differ from the record" if aadhaar else "Identifier on record for a different person",
                             "detail": f"Row {r['row'] + 1} ({label.get(r['identity'])}): {', '.join(c['basis'])}" + ("." if aadhaar else ", recorded for the person named below."),
                             "benign": "A typing error at the counter, or a relative's document used for convenience.", "rows": [r["row"]],
                             "parties": [party(r["identity"])] + ([] if aadhaar else [{"key": c["person"], "label": c.get("name_on_record") or "?", "status": "existing", "person": c["person"], "from_record": True}])})
                if not aadhaar:
                    glinks.append({"source": actor(r["identity"]), "target": gnode(c["person"], c.get("name_on_record") or "?", "actor", "existing", True), "label": "used document of"})
        # 4. values that disagree with the record
        conflicts = [o for o in ops if o["op"] == "conflict"]
        if conflicts:
            by_prop = Counter(o["prop"] for o in conflicts)
            pats.append({"id": "conflicts", "kind": "record_conflict", "severity": "review", "title": f"{len(conflicts)} values disagree with the record",
                         "detail": "; ".join(f"{p.replace('_', ' ')}: {n}" for p, n in by_prop.most_common()) + ". Nothing on record is overwritten; the reviewer settles each one.",
                         "benign": "Address changes, transliteration, or an error in either source.", "rows": sorted({int(o["record"].split("#")[1]) for o in conflicts}), "parties": []})
        # 5. repeat co-stays at the same hotel
        if source == "hotel":
            stays = [(str(r["identity"]), r["values"].get("hotel"), r["values"].get("check_in"), r["values"].get("check_out") or r["values"].get("check_in"), r["row"])
                     for r in rows if r["values"].get("check_in")]
            together: dict[tuple, list] = defaultdict(list)
            for i, a in enumerate(stays):
                for b in stays[i + 1:]:
                    if a[0] != b[0] and a[1] == b[1] and a[2] <= b[3] and b[2] <= a[3]:
                        together[tuple(sorted((a[0], b[0])))].append((a[1], max(a[2], b[2]), a[4], b[4]))
            singles = 0
            for (x, y), occ in sorted(together.items()):
                occasions = sorted({(h, d) for h, d, *_ in occ}, key=lambda z: z[1])
                if len(occasions) < 2:
                    singles += 1
                    continue
                linked = not x.startswith("new:") and not y.startswith("new:") and bool(lk.s.query(
                    "SELECT 1 FROM links WHERE ((src=? AND dst=?) OR (src=? AND dst=?)) AND status IN ('active','confirmed') LIMIT 1", (x, y, y, x)))
                pats.append({"id": f"costay_{x[-6:]}_{y[-6:]}", "kind": "repeat_co_stay", "severity": "info" if linked else "review",
                             "title": f"At the same hotel at the same time, {len(occasions)} times",
                             "detail": f"{label.get(x)} and {label.get(y)}: " + "; ".join(f"{h}, {d}" for h, d in occasions) + "."
                             + (" They are already linked on record." if linked else " No link between them on record."),
                             "benign": "Colleagues on work travel, or a family.", "rows": sorted({rr for *_, ra, rb in occ for rr in (ra, rb)}), "parties": [party(x), party(y)]})
                glinks.append({"source": actor(x), "target": actor(y), "label": f"co-stay ×{len(occasions)}"})
            if singles:
                pats.append({"id": "costay_single", "kind": "co_stay_background", "severity": "info", "title": f"{singles} pairs overlapped once",
                             "detail": "A single overlap at a busy hotel is common and is not raised as a lead.", "benign": "", "rows": [], "parties": []})
        # 6. what the extract teaches the record
        aliases = [o for o in ops if o["op"] == "alias"]
        if aliases:
            pats.append({"id": "aliases", "kind": "aliases", "severity": "info", "title": f"{len(aliases)} new spellings of names on record",
                         "detail": "Added as aliases on publish, so later searches find these people under either spelling.", "benign": "",
                         "rows": sorted({int(o["record"].split("#")[1]) for o in aliases}), "parties": []})
        foreign = [r for r in rows if str((r["typed"].get("Phone") or {}).get("number", "")).startswith("+")]
        if foreign:
            pats.append({"id": "foreign", "kind": "foreign_number", "severity": "info", "title": f"{len(foreign)} foreign mobile numbers",
                         "detail": "Kept with their country code.", "benign": "NRIs and foreign nationals.", "rows": [r["row"] for r in foreign], "parties": []})
    else:
        # seized notes: identifiers that recur across pages, people named on the same page
        where: dict[tuple, set] = defaultdict(set)
        page_people: dict[int, set] = defaultdict(set)
        for r in rows:
            for t in r["tags"]:
                if t["kind"] in TAG_KINDS:
                    where[(t["kind"], t["value"])].add(r["row"])
                if t.get("object") and str(t["object"]).startswith("person:"):
                    page_people[r["row"]].add(t["object"])
                for o in t.get("owners", []):
                    page_people[r["row"]].add(o)
        page_no = {r["row"]: str(r["values"].get("page") or r["row"] + 1) for r in rows}
        for (kind, val), pages in sorted(where.items()):
            if len(pages) < 2:
                continue
            owners = sorted({o for r in rows if r["row"] in pages for t in r["tags"] if t["value"] == val for o in t.get("owners", [])})
            nm = {"phone": "number", "vehicle_reg": "vehicle", "account_no": "account"}[kind]
            pats.append({"id": f"recur_{val[-6:]}", "kind": "recurring_identifier", "severity": "review",
                         "title": f"The same {nm} on {len(pages)} pages" + ("" if owners else ", not on record"),
                         "detail": f"{nm[0].upper() + nm[1:]} ··{val[-4:]} is written on pages {', '.join(page_no[p] for p in sorted(pages))}.",
                         "benign": "A shop, a driver or a common contact.", "rows": sorted(pages), "parties": []})
            hub = gnode(f"{kind}:{val}", f"{nm} ··{val[-4:]}", "comms" if kind == "phone" else "money" if kind == "account_no" else "asset")
            for p in sorted(pages):
                glinks.append({"source": gnode(f"page:{p}", f"Page {page_no[p]}", "record"), "target": hub, "label": "written on"})
        for r in rows:
            for pid in sorted(page_people[r["row"]]):
                glinks.append({"source": gnode(f"page:{r['row']}", f"Page {page_no[r['row']]}", "record"), "target": gnode(pid, lk.props(pid).get("name", "?"), "actor", "existing", True), "label": "names"})
        named = sum(1 for r in rows for t in r["tags"] if t["kind"] == "name" and t.get("object"))
        total = sum(1 for r in rows for t in r["tags"] if t["kind"] == "name")
        pats.append({"id": "names", "kind": "names_resolved", "severity": "info", "title": f"{named} of {total} written names tied to a person on record",
                     "detail": "A name is tied only when an identifier on the same page is on record for a person with that name; other names stay as text.",
                     "benign": "", "rows": [], "parties": []})
    geo: dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        if r["geo"]:
            geo[r["geo"]][r["match"]["status"]] += 1
    places = [{"city": c, "lat": lk.city_xy.get(c, (None, None))[0], "lon": lk.city_xy.get(c, (None, None))[1], "rows": sum(n.values()), **dict(n)} for c, n in geo.items()]
    places.sort(key=lambda p: (-p["rows"], p["city"]))
    order = {"review": 0, "info": 1}
    pats.sort(key=lambda p: (order.get(p["severity"], 2), p["kind"], p["id"]))
    return {"patterns": pats, "graph": {"nodes": list(gnodes.values()), "links": glinks}, "places": places}


# ---------------------------------------------------------------------------- proposals
def _case_classes(store: Store, case_id: str) -> tuple[str, ...]:
    rows = store.query("SELECT purpose FROM cases WHERE id=?", (case_id,))
    return store.ontology.purpose_classes(rows[0]["purpose"]) if rows else ()


def check_case(store: Store, user: User, case_id: str | None, source: str) -> None:
    if not case_id:
        raise PolicyError("intake is case-bound: open a case first")
    rows = store.query("SELECT c.status, m.user_id FROM cases c LEFT JOIN case_members m ON m.case_id=c.id AND m.user_id=? WHERE c.id=?", (user.id, case_id))
    if not rows or rows[0]["status"] != "open":
        raise PolicyError("the case is not open")
    if rows[0]["user_id"] is None:
        raise PolicyError("you are not a member of this case")
    missing = [c for c in SPECS[source]["classes"] if c not in _case_classes(store, case_id)]
    if missing:
        raise PolicyError(f"the case purpose does not cover: {', '.join(missing)}")


def propose(store: Store, user: User, case_id: str, source: str, recipe: list[dict[str, str]] | None, mapping: dict[str, list[str]] | None,
            legal_order: str, note: str = "") -> dict[str, Any]:
    if not user.has("io", "analyst", "supervisor"):
        raise PolicyError("only investigators and analysts can propose an intake")
    check_case(store, user, case_id, source)
    if len(legal_order.strip()) < 8:
        raise PolicyError("cite the order or notice under which this extract was obtained")
    res = run(store, source, recipe, mapping)
    if res["mapping_errors"]:
        raise PolicyError("; ".join(res["mapping_errors"]))
    pid = make_id("intakeproposal", source, f"{case_id}|{user.id}|{utcnow()}|{secrets.token_hex(3)}")
    leads = [{"title": p["title"], "kind": p["kind"]} for p in res["lenses"]["patterns"] if p["severity"] == "review"]
    with store.tx() as conn:
        conn.execute("INSERT INTO intake_proposals(id,case_id,source,recipe,legal_order,summary,changes,fingerprint,requested_by,requested_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                     (pid, case_id, source, json.dumps({"recipe": res["recipe"], "mapping": res["mapping"], "note": note}), legal_order.strip(),
                      json.dumps(res["summary"] | {"leads": leads, "title": res["title"]}), json.dumps(res["ops"], default=str), res["fingerprint"], user.id, utcnow()))
    return {"proposal": pid, "summary": res["summary"], "leads": leads}


def _card(conn: Any, oid: str, prop: str | None, op: str, old: Any, new: Any, source: str, record: str, proposal: str, actor: str, now: str) -> None:
    conn.execute("INSERT INTO revisions(object_id,prop,op,old_value,new_value,source,record,proposal_id,actor,at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                 (oid, prop, op, json.dumps(old, default=str) if old is not None else None, json.dumps(new, default=str) if new is not None else None,
                  source, record, proposal, actor, now))


def _set_prop(store: Store, oid: str, prop: str, value: Any, source: str, record: str) -> None:
    row = store.query("SELECT type, props FROM objects WHERE id=?", (oid,))[0]
    props = json.loads(row["props"])
    if value is None:
        props.pop(prop, None)
    else:
        props[prop] = value
    store.ontology.validate_object(row["type"], props)
    title = str(props.get(store.ontology.object_type(row["type"]).title, oid))
    store.conn.execute("UPDATE objects SET props=?, title=?, updated_at=? WHERE id=?", (json.dumps(props, ensure_ascii=False), title, utcnow(), oid))
    if value is not None:
        store.conn.execute("INSERT INTO provenance(object_id,prop,source,record,ingested_at,confidence) VALUES(?,?,?,?,?,?) ON CONFLICT(object_id,prop,source,record) DO UPDATE SET ingested_at=excluded.ingested_at, confidence=excluded.confidence", (oid, prop, source, record, utcnow(), 1.0))
    else:
        store.conn.execute("DELETE FROM provenance WHERE object_id=? AND prop=? AND source=?", (oid, prop, source))
    store._index(oid, row["type"], props)


def decide(store: Store, user: User, proposal_id: str, approve: bool, reason: str = "") -> dict[str, Any]:
    rows = store.query("SELECT * FROM intake_proposals WHERE id=?", (proposal_id,))
    if not rows or rows[0]["status"] != "pending":
        raise PolicyError("no pending proposal with that id")
    p = dict(rows[0])
    if not user.has("supervisor"):
        raise PolicyError("only a supervisor can approve or reject an intake")
    if user.id == p["requested_by"]:
        raise PolicyError("two-person rule: the proposer cannot approve their own intake")
    if not store.query("SELECT 1 FROM case_members WHERE case_id=? AND user_id=?", (p["case_id"], user.id)):
        raise PolicyError("the approver must be a member of the case")
    if len(reason.strip()) < 4:
        raise PolicyError("record a reason for the decision")
    now = utcnow()
    if not approve:
        with store.tx() as conn:
            conn.execute("UPDATE intake_proposals SET status='rejected', decided_by=?, decided_at=?, decision_reason=? WHERE id=?", (user.id, now, reason, proposal_id))
        return {"status": "rejected", "case": p["case_id"]}
    source = f"INTAKE/{p['source']}"
    applied: Counter = Counter()
    skipped: list[dict[str, Any]] = []
    touched: set[str] = set()
    with store.tx() as conn:
        for op in json.loads(p["changes"]):
            kind = op["op"]
            if kind == "create":
                props = {k: v for k, v in op["props"].items() if not k.startswith("_")}
                if store.query("SELECT 1 FROM objects WHERE id=?", (op["id"],)):
                    skipped.append({"op": op, "why": "already exists"})
                    continue
                store.upsert_object(op["type"], props, source=source, record=op["record"], obj_id=op["id"], synthetic=True, origin_case=p["case_id"],
                                    legal_order=p["legal_order"], lat=op["props"].get("_lat"), lon=op["props"].get("_lon"))
                _card(conn, op["id"], None, "create", None, props, source, op["record"], proposal_id, user.id, now)
                touched.add(op["id"])
            elif kind in ("fill", "alias"):
                cur = (store.get_object(op["id"]) or {}).get("props", {})
                if kind == "fill":
                    if cur.get(op["prop"]) not in (None, ""):
                        skipped.append({"op": op, "why": "filled since the proposal was made"})
                        continue
                    _set_prop(store, op["id"], op["prop"], op["value"], source, op["record"])
                    _card(conn, op["id"], op["prop"], "fill", None, op["value"], source, op["record"], proposal_id, user.id, now)
                else:
                    al = list(cur.get("aliases") or [])
                    if op["value"] in al:
                        continue
                    _set_prop(store, op["id"], "aliases", al + [op["value"]], source, op["record"])
                    _card(conn, op["id"], "aliases", "alias", None, op["value"], source, op["record"], proposal_id, user.id, now)
                touched.add(op["id"])
            elif kind == "corroborate":
                conn.execute("INSERT INTO provenance(object_id,prop,source,record,ingested_at,confidence) VALUES(?,?,?,?,?,?) ON CONFLICT(object_id,prop,source,record) DO UPDATE SET ingested_at=excluded.ingested_at, confidence=excluded.confidence", (op["id"], op["prop"], source, op["record"], now, 1.0))
                _card(conn, op["id"], op["prop"], "corroborate", op["old"], op["value"], source, op["record"], proposal_id, user.id, now)
            elif kind == "conflict":
                _card(conn, op["id"], op["prop"], "conflict", op["old"], op["value"], source, op["record"], proposal_id, user.id, now)
                touched.add(op["id"])
            elif kind == "link":
                existed = bool(store.query("SELECT 1 FROM links WHERE type=? AND src=? AND dst=?", (op["type"], op["src"], op["dst"])))
                lid = store.upsert_link(op["type"], op["src"], op["dst"], source=source, record=op["record"])
                _card(conn, lid, None, "link_evidence" if existed else "link", None, {"type": op["type"], "src": op["src"], "dst": op["dst"]}, source, op["record"], proposal_id, user.id, now)
                touched.update((op["src"], op["dst"]))
            elif kind == "candidate":
                a, b = sorted((op["a"], op["b"]))
                lid = store.upsert_link("same_as", a, b, source=source, record=op["record"], origin="resolver", confidence=0.7, status="candidate",
                                        props={"explanation": {"probability": 0.7, "features": [op["basis"], f"from intake {p['source']}"]}})
                rid = "review:" + hashlib.sha1(f"{a}|{b}".encode()).hexdigest()[:16]
                conn.execute("INSERT INTO review_queue(id,a,b,probability,explanation) VALUES(?,?,?,?,?) ON CONFLICT DO NOTHING",
                             (rid, a, b, 0.7, json.dumps({"probability": 0.7, "match_weight": 0.0, "features": [op["basis"], f"intake {p['source']}"], "link_id": lid})))
                _card(conn, lid, None, "candidate", None, {"a": a, "b": b, "review": rid}, source, op["record"], proposal_id, user.id, now)
            applied[kind] += 1
        for oid in sorted(touched):
            if oid.split(":")[0] in ("person", "phone", "vehicle", "bankaccount", "event", "document"):
                conn.execute("INSERT INTO case_objects(case_id,object_id,added_by,reason,added_at) VALUES(?,?,?,?,?) ON CONFLICT DO NOTHING",
                             (p["case_id"], oid, user.id, f"intake {p['source']} under {p['legal_order']}", now))
        conn.execute("UPDATE intake_proposals SET status='approved', decided_by=?, decided_at=?, decision_reason=?, applied=? WHERE id=?",
                     (user.id, now, reason, json.dumps({"applied": dict(applied), "skipped": len(skipped)}), proposal_id))
    subjects = {r["object_id"] for r in store.query("SELECT object_id FROM case_objects WHERE case_id=? AND reason NOT LIKE 'intake %'", (p["case_id"],))}
    return {"status": "approved", "case": p["case_id"], "applied": dict(applied), "skipped": skipped[:20], "touches_case_subjects": sorted(subjects & touched)[:50]}


def revert(store: Store, user: User, proposal_id: str, reason: str) -> dict[str, Any]:
    """Undo a published intake card by card: created objects are removed, filled values are cleared only
    if nobody has changed them since, evidence entries are taken off links, pending candidates withdrawn."""
    rows = store.query("SELECT * FROM intake_proposals WHERE id=?", (proposal_id,))
    if not rows or rows[0]["status"] != "approved":
        raise PolicyError("only a published intake can be reverted")
    if not user.has("supervisor"):
        raise PolicyError("only a supervisor can revert an intake")
    if len(reason.strip()) < 4:
        raise PolicyError("record a reason for the revert")
    p = dict(rows[0])
    source = f"INTAKE/{p['source']}"
    cards = [dict(r) for r in store.query("SELECT * FROM revisions WHERE proposal_id=? ORDER BY id DESC", (proposal_id,))]
    out: Counter = Counter()
    created = {c["object_id"] for c in cards if c["op"] == "create"}
    now = utcnow()
    with store.tx() as conn:
        for c in cards:
            new = json.loads(c["new_value"]) if c["new_value"] else None
            if c["op"] in ("fill", "alias") and c["object_id"] not in created:
                cur = (store.get_object(c["object_id"]) or {}).get("props", {})
                if c["op"] == "fill" and cur.get(c["prop"]) == new:
                    _set_prop(store, c["object_id"], c["prop"], None, source, c["record"])
                    out["values_cleared"] += 1
                elif c["op"] == "alias" and new in (cur.get("aliases") or []):
                    rest = [a for a in cur["aliases"] if a != new]
                    _set_prop(store, c["object_id"], "aliases", rest or None, source, c["record"])
                    out["aliases_removed"] += 1
            elif c["op"] == "corroborate":
                conn.execute("DELETE FROM provenance WHERE object_id=? AND prop=? AND source=? AND record=?", (c["object_id"], c["prop"], source, c["record"]))
            elif c["op"] in ("link", "link_evidence"):
                lr = store.query("SELECT sources FROM links WHERE id=?", (c["object_id"],))
                if lr:
                    srcs = [s for s in json.loads(lr[0]["sources"]) if s.get("source") != source]
                    if srcs:
                        conn.execute("UPDATE links SET sources=?, updated_at=? WHERE id=?", (json.dumps(srcs), now, c["object_id"]))
                    else:
                        conn.execute("DELETE FROM links WHERE id=?", (c["object_id"],))
                        out["links_removed"] += 1
            elif c["op"] == "candidate":
                conn.execute("DELETE FROM review_queue WHERE id=? AND status='pending'", (new["review"],))
                conn.execute("DELETE FROM links WHERE id=? AND status='candidate'", (c["object_id"],))
            if not c["op"].startswith("revert_"):
                _card(conn, c["object_id"], c["prop"], f"revert_{c['op']}", new, None, source, c["record"], proposal_id, user.id, now)
        conn.execute("UPDATE intake_proposals SET status='reverted', decision_reason=COALESCE(decision_reason,'') || ? WHERE id=?",
                     (f" | reverted by {user.id}: {reason}", proposal_id))
    from ..retention import _delete_objects

    out["objects_removed"] = _delete_objects(store, sorted(created))
    return {"status": "reverted", "case": p["case_id"], **dict(out)}


def history(store: Store, object_id: str) -> list[dict[str, Any]]:
    """Revision cards for one object: the stack of changes with who, when, source row and order."""
    rows = store.query("SELECT r.*, p.legal_order, p.case_id FROM revisions r LEFT JOIN intake_proposals p ON p.id=r.proposal_id WHERE r.object_id=? ORDER BY r.id", (object_id,))
    return [{**dict(r), "old_value": json.loads(r["old_value"]) if r["old_value"] else None, "new_value": json.loads(r["new_value"]) if r["new_value"] else None} for r in rows]


def sources_catalog() -> list[dict[str, Any]]:
    return [{"id": k, **v, "classes": SPECS[k]["classes"], "record_type": SPECS[k]["record"]["type"]} for k, v in SOURCES.items()]

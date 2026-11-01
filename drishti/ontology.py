"""Load the ontology YAML and validate objects and links against it."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from .config import settings


class OntologyError(ValueError):
    pass


@dataclass(frozen=True)
class PropertyDef:
    name: str
    type: str
    required: bool = False
    search: str | None = None
    mask: str | None = None
    mask_below: int | None = None  # mask only for users below this clearance
    pattern: str | None = None
    values: tuple[str, ...] | None = None


@dataclass(frozen=True)
class ObjectType:
    name: str
    sensitivity: int
    personal: bool
    title: str
    retention: str | None
    properties: dict[str, PropertyDef]
    requires_when: tuple[dict, ...] = ()


@dataclass(frozen=True)
class LinkType:
    name: str
    from_types: tuple[str, ...]
    to_types: tuple[str, ...]
    evidentiary: bool
    resolver: bool = False


@dataclass
class Ontology:
    version: str
    levels: dict[str, int]
    objects: dict[str, ObjectType]
    links: dict[str, LinkType]
    actions: dict[str, dict]
    purposes: list[str] = field(default_factory=list)
    record_classes: dict[str, dict] = field(default_factory=dict)
    purpose_class_map: dict[str, tuple[str, ...]] = field(default_factory=dict)
    mission_tracks: dict[str, dict] = field(default_factory=dict)
    agencies: dict[str, dict] = field(default_factory=dict)

    def record_class_of(self, type_name: str) -> str:
        """The record class an object type belongs to (ontology `record_classes`)."""
        for name, spec in self.record_classes.items():
            if type_name in (spec.get("objects") or ()):
                return name
        return "documents"

    def purpose_classes(self, purpose: str) -> tuple[str, ...]:
        return self.purpose_class_map.get(purpose, ("identity", "geography"))

    def agency_purposes(self, agency: str) -> tuple[str, ...]:
        return tuple((self.agencies.get(agency) or {}).get("purposes") or ())

    def agency_tracks(self, agency: str) -> tuple[str, ...]:
        return tuple((self.agencies.get(agency) or {}).get("tracks") or ())

    def object_type(self, name: str) -> ObjectType:
        try:
            return self.objects[name]
        except KeyError:
            raise OntologyError(f"unknown object type {name!r}") from None

    def link_type(self, name: str) -> LinkType:
        try:
            return self.links[name]
        except KeyError:
            raise OntologyError(f"unknown link type {name!r}") from None

    def validate_object(self, type_name: str, props: dict[str, Any]) -> None:
        ot = self.object_type(type_name)
        for pname, pdef in ot.properties.items():
            if pdef.required and props.get(pname) in (None, ""):
                raise OntologyError(f"{type_name}.{pname} is required")
        for rule in ot.requires_when:
            if all(props.get(k) in v for k, v in rule["when"].items()):
                missing = [k for k in rule["require"] if props.get(k) in (None, "")]
                if missing:
                    raise OntologyError(f"{type_name} with {rule['when']} requires {', '.join(missing)}")
        for pname, value in props.items():
            pdef = ot.properties.get(pname)
            if pdef is None or value in (None, ""):
                continue  # extra properties are allowed and kept; the schema governs known ones
            if pdef.pattern and not re.fullmatch(pdef.pattern, str(value)):
                raise OntologyError(f"{type_name}.{pname}={value!r} does not match {pdef.pattern}")
            if pdef.values and str(value) not in pdef.values:
                raise OntologyError(f"{type_name}.{pname}={value!r} not in {list(pdef.values)}")
            if pdef.type == "integer" and not isinstance(value, int):
                raise OntologyError(f"{type_name}.{pname} must be an integer")
            if pdef.type == "number" and not isinstance(value, (int, float)):
                raise OntologyError(f"{type_name}.{pname} must be a number")

    def validate_link(self, link_type: str, src_type: str, dst_type: str) -> None:
        lt = self.link_type(link_type)
        if src_type not in lt.from_types or dst_type not in lt.to_types:
            raise OntologyError(f"{link_type} cannot connect {src_type} -> {dst_type}")

    def to_public_dict(self) -> dict:
        """Schema summary for clients (no policy internals)."""
        return {
            "version": self.version,
            "objects": {
                n: {
                    "sensitivity": t.sensitivity,
                    "personal": t.personal,
                    "title": t.title,
                    "properties": {p: {"type": d.type, "masked": bool(d.mask)} for p, d in t.properties.items()},
                }
                for n, t in self.objects.items()
            },
            "links": {n: {"from": l.from_types, "to": l.to_types, "evidentiary": l.evidentiary} for n, l in self.links.items()},
            "actions": sorted(self.actions),
            "purposes": self.purposes,
            "record_classes": {k: v.get("label", k) for k, v in self.record_classes.items()},
            "purpose_classes": {k: list(v) for k, v in self.purpose_class_map.items()},
            "mission_tracks": self.mission_tracks,
            "agencies": self.agencies,
        }


def _as_tuple(v: Any) -> tuple[str, ...]:
    return tuple(v) if isinstance(v, (list, tuple)) else (v,)


def load_ontology(path: Path | None = None) -> Ontology:
    raw = yaml.safe_load(Path(path or settings.ontology_path).read_text(encoding="utf-8"))
    levels = raw["sensitivity_levels"]
    objects = {}
    for name, spec in raw["object_types"].items():
        props = {
            p: PropertyDef(
                name=p,
                type=d.get("type", "string"),
                required=d.get("required", False),
                search=d.get("search"),
                mask=d.get("mask"),
                mask_below=d.get("mask_below"),
                pattern=d.get("pattern"),
                values=tuple(d["values"]) if "values" in d else None,
            )
            for p, d in (spec.get("properties") or {}).items()
        }
        objects[name] = ObjectType(
            name=name,
            sensitivity=levels[spec.get("sensitivity", "PUBLIC")],
            personal=spec.get("personal", False),
            title=spec.get("title", next(iter(props), "id")),
            retention=spec.get("retention"),
            properties=props,
            requires_when=tuple(spec.get("requires_when") or ()),
        )
    links = {}
    for name, spec in raw["link_types"].items():
        lt = LinkType(name, _as_tuple(spec["from"]), _as_tuple(spec["to"]), spec.get("evidentiary", True), spec.get("resolver", False))
        for t in lt.from_types + lt.to_types:
            if t not in objects:
                raise OntologyError(f"link {name} references unknown type {t}")
        links[name] = lt
    purposes = raw.get("purposes", [])
    pclasses = {k: tuple(v) for k, v in (raw.get("purpose_classes") or {}).items()}
    classes = raw.get("record_classes") or {}
    for k, v in pclasses.items():
        if k not in purposes:
            raise OntologyError(f"purpose_classes names unknown purpose {k}")
        if set(v) - set(classes):
            raise OntologyError(f"purpose {k} names unknown record classes {set(v) - set(classes)}")
    tracks = raw.get("mission_tracks") or {}
    agencies = raw.get("agencies") or {}
    for a, spec in agencies.items():
        for pu in spec.get("purposes") or ():
            if pu not in purposes:
                raise OntologyError(f"agency {a} mandates unknown purpose {pu}")
        for t in spec.get("tracks") or ():
            if t not in tracks:
                raise OntologyError(f"agency {a} names unknown track {t}")
    return Ontology(raw["version"], levels, objects, links, raw.get("actions", {}), purposes, classes, pclasses, tracks, agencies)


@lru_cache(maxsize=1)
def get_ontology() -> Ontology:
    return load_ontology()

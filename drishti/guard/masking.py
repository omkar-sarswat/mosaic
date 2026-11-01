"""Field masking. Aadhaar is always masked until an audited unmask (UIDAI rule); other
identifiers are masked only for users whose clearance is below the field's `mask_below`."""

from __future__ import annotations

import re
from typing import Any

from ..ontology import Ontology


def mask_value(kind: str, value: Any) -> str:
    s = re.sub(r"\s", "", str(value))
    if kind == "aadhaar":
        return "XXXX-XXXX-" + s[-4:]
    if kind == "pan":
        return s[:3] + "XX" + "XXXX" + s[-1:] if len(s) == 10 else "X" * len(s)
    if kind in ("phone", "account"):
        return "X" * max(len(s) - 4, 2) + s[-4:]
    return "•" * len(s)


def mask_object(ontology: Ontology, obj: dict[str, Any], clearance: int = 0) -> dict[str, Any]:
    ot = ontology.object_type(obj["type"])
    props = dict(obj["props"])
    masked = []
    for pname, pdef in ot.properties.items():
        if not pdef.mask or props.get(pname) in (None, ""):
            continue
        if pdef.mask_below is not None and clearance >= pdef.mask_below:
            continue
        props[pname] = mask_value(pdef.mask, props[pname])
        masked.append(pname)
    out = {**obj, "props": props, "masked": masked}
    if ot.title in masked:
        out["title"] = props[ot.title]
    # internal fields never leave the server
    out["props"] = {k: v for k, v in out["props"].items() if not k.startswith("_")}
    return out

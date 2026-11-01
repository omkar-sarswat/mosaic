"""Profiling and cleaning of source extracts before they enter the ontology.

Every step is a pure function value -> (cleaned value, note). A recipe is an ordered list of
(column, step) pairs; applying it never touches the source rows, records every changed cell, and
quarantines rows that still fail validation (with the reason), so nothing is silently dropped.

Detectors infer what a column holds (phone, PAN, IFSC, Aadhaar, account number, vehicle registration,
date, email, city, person name, amount) by voting over its values, and propose the default cleaning
steps for that type.
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import date, datetime
from typing import Any, Callable

from ..resolve.matcher import _jaro_winkler

PLACEHOLDERS = {"", "na", "n/a", "nil", "null", "none", "-", "--", "0", "unknown", "not available", "xx", "xxx", "."}

# Historic and colloquial city names -> the name used in LGD / the ontology.
CITY_ALIASES = {
    "bombay": "Mumbai", "mumbai": "Mumbai", "mum": "Mumbai", "poona": "Pune", "pune": "Pune", "calcutta": "Kolkata", "madras": "Chennai",
    "bangalore": "Bengaluru", "banglore": "Bengaluru", "bengaluru": "Bengaluru", "baroda": "Vadodara", "trivandrum": "Thiruvananthapuram",
    "gurgaon": "Gurugram", "new bombay": "Navi Mumbai", "navi mumbai": "Navi Mumbai", "thana": "Thane", "thane": "Thane",
    "nasik": "Nashik", "nashik": "Nashik", "kolhapur": "Kolhapur", "sholapur": "Solapur", "solapur": "Solapur", "delhi": "New Delhi",
    "new delhi": "New Delhi", "hyderabad": "Hyderabad", "secunderabad": "Hyderabad", "aurangabad": "Aurangabad", "nagpur": "Nagpur",
    "surat": "Surat", "ahmedabad": "Ahmedabad", "amdavad": "Ahmedabad", "panaji": "Panaji", "panjim": "Panaji", "goa": "Panaji",
    "andheri": "Andheri", "bhiwandi": "Bhiwandi", "panvel": "Panvel", "jaipur": "Jaipur", "lucknow": "Lucknow", "indore": "Indore",
    "kochi": "Kochi", "cochin": "Kochi", "chennai": "Chennai", "kolkata": "Kolkata",
}

TYPE_LABEL = {
    "phone": "Mobile number", "pan": "PAN", "ifsc": "IFSC", "aadhaar": "Aadhaar (masked)", "account_no": "Bank account number",
    "vehicle_reg": "Vehicle registration", "date": "Date", "email": "Email", "city": "City", "person_name": "Person name",
    "amount": "Amount", "category": "Category (coded values)", "id_document": "Identity document number", "code": "Code / identifier", "text": "Free text",
}

SENSITIVE_KINDS = ("aadhaar", "id_document")
AADHAAR_RAW = re.compile(r"(?<![\d+])([2-9]\d{3})([\s-]?)(\d{4})([\s-]?)(\d{4})(?!\d)")


def mask_raw(v: Any) -> Any:
    """Mask full Aadhaar numbers wherever they appear, before any value is shown or stored (UIDAI rule).
    The mask keeps the text's length and separators, so tag spans computed on the original still line up.
    A number written with a leading + is a phone number with its country code, not an Aadhaar."""
    if not isinstance(v, str):
        return v
    return AADHAAR_RAW.sub(lambda m: f"XXXX{m.group(2)}XXXX{m.group(4)}{m.group(5)}", v)


def shape(v: Any) -> str:
    """Format signature: letters -> A, digits -> 9, runs collapsed above 3 (e.g. '+99 99999 99999')."""
    s = re.sub(r"[A-Za-z]", "A", str(v))
    s = re.sub(r"\d", "9", s)
    return re.sub(r"(A{4,}|9{4,})", lambda m: m.group(0)[0] * 4 + "…", s)[:24]


def is_blank(v: Any) -> bool:
    return v is None or str(v).strip().lower() in PLACEHOLDERS


def digits(v: Any) -> str:
    return re.sub(r"\D", "", str(v))


# ---------------------------------------------------------------------------- type detectors
DETECT: list[tuple[str, Callable[[str], bool]]] = [
    ("email", lambda s: bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[A-Za-z]{2,}", s.strip()))),
    ("ifsc", lambda s: bool(re.fullmatch(r"[A-Za-z]{4}0[A-Za-z0-9]{6}", s.strip()))),
    ("pan", lambda s: bool(re.fullmatch(r"[A-Za-z]{5}\s?\d{4}\s?[A-Za-z]", s.strip()))),
    ("vehicle_reg", lambda s: bool(re.fullmatch(r"[A-Za-z]{2}[\s.-]?\d{1,2}[\s.-]?[A-Za-z]{0,3}[\s.-]?\d{4}|\d{2}\s?BH\s?\d{4}\s?[A-Za-z]{1,2}", s.strip(), re.I))),
    ("aadhaar", lambda s: bool(re.fullmatch(r"(X{4}[\s-]?){2}\d{4}|\d{4}[\s-]?\d{4}[\s-]?\d{4}", s.strip(), re.I))),
    ("id_document", lambda s: bool(re.fullmatch(r"(X{4}[\s-]?){2}\d{4}|\d{4}[\s-]?\d{4}[\s-]?\d{4}|[A-Za-z]{5}\s?\d{4}\s?[A-Za-z]|[A-Za-z]{2}\d{2}\s?\d{11}", s.strip(), re.I))),
    ("phone", lambda s: bool(re.fullmatch(r"\+?[\d\s()-]{10,17}", s.strip())) and 10 <= len(digits(s)) <= 13),
    ("account_no", lambda s: bool(re.fullmatch(r"[\d\s-]{9,22}", s.strip())) and 9 <= len(digits(s)) <= 18),
    ("date", lambda s: parse_date(s) is not None),
    ("amount", lambda s: bool(re.fullmatch(r"(Rs\.?|₹|INR)?\s?[\d,]+(\.\d+)?(\s?(L|lakh|Cr|crore))?", s.strip(), re.I))),
    ("city", lambda s: canonical_city(s) is not None),
    ("person_name", lambda s: bool(re.fullmatch(r"[A-Za-z][A-Za-z.' ]{2,60}", s.strip())) and 1 <= len(s.split()) <= 5),
]


def detect_type(values: list[Any]) -> tuple[str, float]:
    vals = [str(v) for v in values if not is_blank(v)][:400]
    if not vals:
        return "text", 0.0
    # a column of a few repeated codes (SB / Savings / CA, WHT / Black) is a category, not names
    distinct = {v.strip().lower() for v in vals}
    if len(vals) >= 20 and len(distinct) <= 12 and len(distinct) / len(vals) <= 0.2 and not any(t(v) for v in list(distinct)[:3] for n, t in DETECT if n == "city"):
        return "category", 1.0
    best, share = "text", 0.0
    for name, test in DETECT:
        hit = sum(1 for v in vals if test(v)) / len(vals)
        if hit > share + 1e-9 and hit >= 0.6:
            best, share = name, hit
            if hit >= 0.97:
                break
    return best, round(share, 3)


# ---------------------------------------------------------------------------- cleaning steps
def parse_date(s: Any) -> str | None:
    t = str(s).strip()
    if not t:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%y", "%d-%b-%Y", "%d %b %Y", "%d %B %Y", "%b %d, %Y", "%Y/%m/%d", "%d-%m-%y"):
        try:
            d = datetime.strptime(t, fmt).date()
        except ValueError:
            continue
        if date(1900, 1, 1) <= d <= date(2100, 1, 1):
            return d.isoformat()
    try:
        return datetime.fromisoformat(t).date().isoformat()
    except ValueError:
        return None


def canonical_city(s: Any) -> str | None:
    t = re.sub(r"[^a-z ]", "", str(s).strip().lower())
    t = re.sub(r"\s+", " ", t).strip()
    if not t:
        return None
    if t in CITY_ALIASES:
        return CITY_ALIASES[t]
    best = max(CITY_ALIASES, key=lambda k: _jaro_winkler(t, k))
    return CITY_ALIASES[best] if _jaro_winkler(t, best) >= 0.93 else None


def _phone(v: str) -> tuple[str | None, str]:
    d = digits(v)
    if str(v).strip().startswith("+") and not d.startswith("91"):
        return ("+" + d, "international, kept with country code") if 8 <= len(d) <= 15 else (None, "not a valid international number")
    if len(d) == 12 and d.startswith("91"):
        d = d[2:]
    elif len(d) == 11 and d.startswith("0"):
        d = d[1:]
    if len(d) == 10 and d[0] in "6789":
        return d, "normalised to 10-digit mobile"
    return None, "not a valid Indian mobile number"


def _vehicle(v: str) -> tuple[str | None, str]:
    s = re.sub(r"[\s.-]", "", str(v)).upper()
    if re.fullmatch(r"[A-Z]{2}[0-9]{1,2}[A-Z]{0,3}[0-9]{4}|[0-9]{2}BH[0-9]{4}[A-HJ-NP-Z]{1,2}", s):
        return s, "canonical registration (no spaces or dashes, upper case)"
    return None, "not a valid Indian registration"


def _pan(v: str) -> tuple[str | None, str]:
    s = re.sub(r"\s", "", str(v)).upper()
    return (s, "upper case") if re.fullmatch(r"[A-Z]{3}[PCHFATBLJG][A-Z][0-9]{4}[A-Z]", s) else (None, "not a valid PAN")


def _aadhaar(v: str) -> tuple[str | None, str]:
    d = digits(v)
    if len(d) == 12:
        return f"XXXX-XXXX-{d[-4:]}", "masked to the last four digits (UIDAI storage rule)"
    if re.fullmatch(r"(X{4}[\s-]?){2}\d{4}", str(v).strip(), re.I):
        return f"XXXX-XXXX-{d[-4:]}", "already masked"
    return None, "not an Aadhaar number"


def _name(v: str) -> tuple[str | None, str]:
    s = re.sub(r"\s+", " ", str(v)).strip(" .,")
    if not s:
        return None, "empty"
    s = re.sub(r"^(Mr|Mrs|Ms|Shri|Smt|Dr|Kum)\.?\s+", "", s, flags=re.I)
    out = s.title() if (s.isupper() or s.islower()) else s
    return out, "spacing, case and honorifics normalised"


def _id_document(v: str) -> tuple[str | None, str]:
    """A column of mixed identity documents: mask Aadhaar, validate PAN, keep others upper case."""
    s = str(v).strip()
    if re.fullmatch(r"(X{4}[\s-]?){2}\d{4}|\d{4}[\s-]?\d{4}[\s-]?\d{4}", s, re.I):
        return _aadhaar(s)
    if re.fullmatch(r"[A-Za-z]{5}\s?\d{4}\s?[A-Za-z]", s):
        return _pan(s)
    t = re.sub(r"\s+", "", s).upper()
    return (t, "upper case, spaces removed") if len(t) >= 6 else (None, "not an identity document number")


COLOUR_CODES = {"wht": "White", "white": "White", "blk": "Black", "black": "Black", "slv": "Silver", "silver": "Silver", "silver grey": "Silver",
                "red": "Red", "gry": "Grey", "grey": "Grey", "gray": "Grey", "blu": "Blue", "blue": "Blue"}
ACCOUNT_TYPES = {"sb": "savings", "savings": "savings", "saving": "savings", "ca": "current", "current": "current", "nre": "nre", "od": "loan", "loan": "loan"}


def _parse_mdy(v: Any) -> str | None:
    t = str(v).strip()
    for fmt in ("%m/%d/%Y", "%m-%d-%Y", "%m.%d.%Y"):
        try:
            return datetime.strptime(t, fmt).date().isoformat()
        except ValueError:
            continue
    return parse_date(t)


def ambiguous_date(v: Any) -> bool:
    """dd/mm vs mm/dd: both readings are valid dates and they differ."""
    m = re.fullmatch(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})", str(v).strip())
    return bool(m) and int(m.group(1)) <= 12 and int(m.group(2)) <= 12 and m.group(1) != m.group(2)


def _amount(v: str) -> tuple[float | None, str]:
    s = str(v).strip().lower().replace(",", "").replace("₹", "").replace("rs.", "").replace("rs", "").replace("inr", "").strip()
    mult = 1.0
    for suffix, m in (("crore", 1e7), ("cr", 1e7), ("lakh", 1e5), ("l", 1e5)):
        if s.endswith(suffix):
            s, mult = s[: -len(suffix)].strip(), m
            break
    try:
        return round(float(s) * mult, 2), "parsed to rupees"
    except ValueError:
        return None, "not a number"


STEPS: dict[str, dict[str, Any]] = {
    "null_placeholders": {"label": "Treat placeholders (NA, -, 0, unknown) as empty", "fn": lambda v: (None, "placeholder removed") if is_blank(v) else (v, "")},
    "trim": {"label": "Trim and collapse spaces", "fn": lambda v: (re.sub(r"\s+", " ", str(v)).strip(), "spacing")},
    "upper": {"label": "Upper case", "fn": lambda v: (str(v).strip().upper(), "upper case")},
    "lower": {"label": "Lower case", "fn": lambda v: (str(v).strip().lower(), "lower case")},
    "person_name": {"label": "Person name: spacing, case, honorifics", "fn": _name},
    "phone": {"label": "Mobile number to 10 digits (or +country code)", "fn": _phone},
    "vehicle_reg": {"label": "Vehicle registration to canonical form", "fn": _vehicle},
    "pan": {"label": "PAN: upper case, validate", "fn": _pan},
    "ifsc": {"label": "IFSC: upper case, validate", "fn": lambda v: ((s := re.sub(r"\s", "", str(v)).upper()), "upper case") if re.fullmatch(r"[A-Z]{4}0[A-Z0-9]{6}", re.sub(r"\s", "", str(v)).upper()) else (None, "not a valid IFSC")},
    "account_no": {"label": "Account number: digits only", "fn": lambda v: (d, "digits only") if 9 <= len(d := digits(v)) <= 18 else (None, "not an account number")},
    "aadhaar_mask": {"label": "Aadhaar: keep only the last four digits", "fn": _aadhaar},
    "date_iso": {"label": "Date to ISO (from dd/mm/yyyy, 16-Jun-1991, ...)", "fn": lambda v: (d, "ISO date") if (d := parse_date(v)) else (None, "unreadable date")},
    "city": {"label": "City to its LGD name (Bombay -> Mumbai, Poona -> Pune)", "fn": lambda v: (c, "canonical city") if (c := canonical_city(v)) else (str(v).strip().title(), "unknown city kept as written")},
    "email": {"label": "Email: lower case, validate", "fn": lambda v: (s, "lower case") if re.fullmatch(r"[^@\s]+@[^@\s]+\.[a-z]{2,}", s := str(v).strip().lower()) else (None, "not an email")},
    "amount": {"label": "Amount to rupees (1.5 L, Rs 2,00,000, 3 Cr)", "fn": _amount},
    "date_iso_mdy": {"label": "Date to ISO, reading 03/04 as March 4 (foreign systems)", "fn": lambda v: (d, "ISO date, month first") if (d := _parse_mdy(v)) else (None, "unreadable date")},
    "title_case": {"label": "Title case", "fn": lambda v: (str(v).strip().title() if (str(v).isupper() or str(v).islower()) else str(v).strip(), "title case")},
    "colour": {"label": "Vehicle colour codes to names (WHT -> White)", "fn": lambda v: (COLOUR_CODES.get(re.sub(r"\s+", " ", str(v)).strip().lower(), str(v).strip().title()), "colour name")},
    "account_type": {"label": "Account type codes to the ontology (SB -> savings, CA -> current)", "fn": lambda v: (ACCOUNT_TYPES[k], "account type") if (k := str(v).strip().lower()) in ACCOUNT_TYPES else (None, "unknown account type")},
    "id_document": {"label": "Identity document: mask Aadhaar, validate PAN", "fn": _id_document},
}
DEFAULT_STEPS = {
    "phone": ["null_placeholders", "phone"], "pan": ["null_placeholders", "pan"], "ifsc": ["null_placeholders", "ifsc"],
    "aadhaar": ["null_placeholders", "aadhaar_mask"], "account_no": ["null_placeholders", "account_no"],
    "vehicle_reg": ["null_placeholders", "vehicle_reg"], "date": ["null_placeholders", "date_iso"], "email": ["null_placeholders", "email"],
    "city": ["null_placeholders", "city"], "person_name": ["null_placeholders", "person_name"], "amount": ["null_placeholders", "amount"],
    "code": ["null_placeholders", "trim"], "text": ["null_placeholders", "trim"], "category": ["null_placeholders", "trim"],
    "id_document": ["null_placeholders", "id_document"],
}


def apply_step(step: str, value: Any) -> tuple[Any, str]:
    if value is None:
        return None, ""
    return STEPS[step]["fn"](value)


# ---------------------------------------------------------------------------- tagging free text
# Spans are found in priority order and never overlap: a cue-word account number wins over the phone
# pattern that would also match its digits, a registration wins over a capitalised word.
TAG_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("account_no", re.compile(r"(?:A/c|a/c|account|acct)\.?\s*(?:no\.?\s*)?([0-9][0-9 -]{7,24}[0-9])", re.I)),
    ("vehicle_reg", re.compile(r"\b([A-Z]{2}[\s-]?[0-9]{1,2}[\s-]?[A-Z]{1,3}[\s-]?[0-9]{4})\b")),
    ("pan", re.compile(r"\b([A-Z]{3}[PCHFATBLJG][A-Z][0-9]{4}[A-Z])\b")),
    ("ifsc", re.compile(r"\b([A-Z]{4}0[A-Z0-9]{6})\b")),
    ("phone", re.compile(r"(?<![0-9])((?:\+91[\s-]?)?[6-9][0-9]{2}[\s-]?[0-9]{2,3}[\s-]?[0-9]{3,5})(?![0-9])")),
    ("amount", re.compile(r"((?:Rs\.?|INR|₹)\s?[0-9][0-9,]*(?:\.[0-9]+)?(?:\s?(?:L|lakh|lakhs|Cr|crore))?|\b[0-9]+(?:\.[0-9]+)?\s?(?:L|lakh|lakhs|Cr|crore)\b|\b[0-9]{1,3}(?:,[0-9]{2,3})+\b)")),
    ("date", re.compile(r"\b([0-9]{1,2}[/.-][0-9]{1,2}[/.-][0-9]{2,4})\b")),
]
NAME_STOP = {"call", "met", "send", "his", "her", "delivery", "white", "grey", "black", "car", "parked", "picks", "from", "after", "the", "to", "at",
             "boy", "on", "and", "rs", "inr", "page", "toll", "naka", "depot", "stand", "bus", "apmc", "a/c", "pay", "paid", "meet", "give", "take", "collect", "note", "cash"}
LOCALITIES = ["Swargate", "Shivajinagar", "Kurla", "Vashi", "Colaba", "Dadar", "Andheri", "Bandra", "Byculla", "Dongri", "Hadapsar", "Kothrud", "Pimpri", "Chinchwad", "Fort"]


def extract_entities(text: str) -> list[dict[str, Any]]:
    """Tag identifiers, amounts, dates, places and capitalised names in free text, with character spans
    and normalised values. Names are only candidates; resolving them needs corroboration."""
    taken = [False] * len(text)
    out: list[dict[str, Any]] = []

    def free(a: int, b: int) -> bool:
        return not any(taken[a:b])

    def take(kind: str, a: int, b: int, value: Any) -> None:
        for i in range(a, b):
            taken[i] = True
        out.append({"kind": kind, "start": a, "end": b, "text": text[a:b], "value": value})

    for kind, rx in TAG_RULES:
        for m in rx.finditer(text):
            a, b = m.span(1)
            if not free(a, b):
                continue
            raw = m.group(1)
            if kind == "phone":
                v, _ = _phone(raw)
                if not v:
                    continue
            elif kind == "account_no":
                v = digits(raw)
                if not 9 <= len(v) <= 18:
                    continue
            elif kind == "vehicle_reg":
                v, _ = _vehicle(raw)
                if not v:
                    continue
            elif kind == "amount":
                v, _ = _amount(raw)
                if v is None or v < 1000:
                    continue
            elif kind == "date":
                v = parse_date(raw)
                if not v:
                    continue
            else:
                v = raw.upper()
            take(kind, a, b, v)
    for alias, city in sorted([*CITY_ALIASES.items(), *((x.lower(), x) for x in LOCALITIES)], key=lambda kv: -len(kv[0])):
        for m in re.finditer(rf"\b{re.escape(alias)}\b", text, re.I):
            if free(*m.span()):
                take("place", *m.span(), city)
    for m in re.finditer(r"\b([A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,}){0,2})\b", text):
        a, b = m.span(1)
        words = m.group(1).split()
        while words and words[0].lower() in NAME_STOP:
            a += len(words[0]) + 1
            words = words[1:]
        if words and free(a, b) and not any(w.lower() in NAME_STOP for w in words):
            take("name", a, b, " ".join(words))
    out.sort(key=lambda t: t["start"])
    return out


# ---------------------------------------------------------------------------- profile
def profile(columns: list[str], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    n = len(rows)
    for c in columns:
        vals = [r.get(c) for r in rows]
        filled = [v for v in vals if not is_blank(v)]
        kind, share = detect_type(filled)
        shapes = Counter(shape(v) for v in filled).most_common(6)
        placeholders = sum(1 for v in vals if v is not None and str(v).strip() != "" and is_blank(v))
        # how many values the default steps would change or reject: the measured mess in the column
        changed = rejected = 0
        for v in filled:
            cur, ok = v, True
            for st in DEFAULT_STEPS.get(kind, ["trim"]):
                cur, _ = apply_step(st, cur)
                if cur is None:
                    ok = False
                    break
            if not ok:
                rejected += 1
            elif str(cur) != str(v):
                changed += 1
        ambiguous = sum(1 for v in filled if ambiguous_date(v)) if kind == "date" else 0
        mk = mask_raw if kind in SENSITIVE_KINDS else (lambda x: x)
        out.append({
            "column": c, "rows": n, "ambiguous": ambiguous, "values": [{"value": mk(str(v)), "n": k} for v, k in Counter(str(x).strip() for x in filled).most_common(8)] if kind == "category" else [], "filled": len(filled), "completeness": round(len(filled) / n, 3) if n else 0,
            "distinct": len({str(v).strip().lower() for v in filled}), "detected": kind, "detected_label": TYPE_LABEL.get(kind, kind),
            "confidence": share, "shapes": [{"shape": s, "n": k, "example": mk(next(str(v) for v in filled if shape(v) == s))} for s, k in shapes], "formats": len(Counter(shape(v) for v in filled)),
            "placeholders": placeholders, "would_change": changed, "would_reject": rejected, "suggested": DEFAULT_STEPS.get(kind, ["trim"]),
        })
    return out


def apply_recipe(rows: list[dict[str, Any]], recipe: list[dict[str, str]], required: list[str]) -> dict[str, Any]:
    """Clean every row; return cleaned rows, per-cell changes, and quarantined rows with reasons.
    A row is quarantined when a required column ends up empty or a step rejects a value in it."""
    clean, changes, quarantine = [], [], []
    by_col: dict[str, list[str]] = {}
    for r in recipe:
        by_col.setdefault(r["column"], []).append(r["step"])
    for i, row in enumerate(rows):
        new = dict(row)
        reasons = []
        for col, steps in by_col.items():
            before = row.get(col)
            cur = before
            note = ""
            for st in steps:
                cur, n = apply_step(st, cur)
                note = n or note
                if cur is None:
                    break
            new[col] = cur
            if str(cur) != str(before) and not (cur is None and is_blank(before)):
                changes.append({"row": i, "column": col, "before": before, "after": cur, "note": note})
            if cur is None and col in required:
                reasons.append(f"{col}: {note or 'empty'}")
        if any(new.get(c) in (None, "") for c in required if c not in by_col):
            reasons.append("required value missing")
        (quarantine if reasons else clean).append({"row": i, "values": new, "reasons": reasons} if reasons else {"row": i, "values": new})
    return {"clean": clean, "changes": changes, "quarantine": quarantine}


def dedupe(rows: list[dict[str, Any]], keys: list[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Exact duplicates on the key columns after cleaning: keep the first, report the rest."""
    seen: dict[tuple, int] = {}
    keep, dups = [], []
    for r in rows:
        k = tuple(str(r["values"].get(c) or "").lower() for c in keys)
        if all(k) and k in seen:
            dups.append({"row": r["row"], "duplicate_of": seen[k]})
        else:
            seen.setdefault(k, r["row"])
            keep.append(r)
    return keep, dups

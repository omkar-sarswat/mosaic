"""Probabilistic record linkage for Indian person records.

This is a self-contained Fellegi-Sunter implementation, the same model Splink uses,
with features tuned for Indian records:

* order-insensitive name alignment ("Patil Ramesh Vishnu" == "Ramesh Vishnu Patil")
* initials ("R. K. Patil" ~ "Ramesh Kumar Patil")
* phonetic keys across scripts (Devanagari, Gurmukhi, Tamil ... via names.py)
* term-frequency adjustment: a match on a common name ("Ramesh Patil") is worth
  less than a match on a rare one, exactly as Splink's tf adjustments do
* father's name, date of birth (full date when both records carry one, else the birth-year band),
  address (when both carry one, else district), shared phone, gender

Every score carries its explanation (per-feature match weights) so a reviewer sees
*why* two records were proposed (design doc safeguard 8, explainability).

Splink 5 can replace `score_pairs` for crore-scale data; see docs/research/05.
"""

from __future__ import annotations

import itertools
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Iterable

from .names import ParsedName, normalize_name

# m = P(level | same person), u = P(level | different people).
# Hand-set from the literature and calibrated on the synthetic benchmark; replace with
# EM estimates (Splink's estimate_parameters_using_expectation_maximisation) on real data.
M_U = {
    "name": {
        "exact": (0.50, 0.0008),
        "phonetic": (0.22, 0.0015),
        "subset": (0.14, 0.004),
        "initials": (0.08, 0.004),
        "partial": (0.03, 0.02),
        "weak": (0.02, 0.10),
        "none": (0.01, 0.8697),
    },
    "father": {"match": (0.70, 0.004), "partial": (0.20, 0.04), "none": (0.10, 0.956)},
    # birth: a full date when both records carry a real one (dob_*), otherwise the birth-year band
    "age": {"close": (0.80, 0.05), "near": (0.15, 0.08), "far": (0.05, 0.87),
            "dob_exact": (0.25, 0.000125), "dob_near": (0.03, 0.0015), "dob_diff": (0.01, 0.025)},
    # place: the address when both records carry one and it agrees (address_*), otherwise the district.
    # Address agreement is kept moderate: joint families share an address and often a surname.
    "district": {"same": (0.85, 0.04), "diff": (0.15, 0.96), "address_same": (0.40, 0.004), "address_near": (0.15, 0.006)},
    "phone": {"shared": (0.40, 0.00002), "diff": (0.60, 0.99998)},
    "gender": {"same": (0.99, 0.5), "diff": (0.01, 0.5)},
    # national identifiers: agreement is near-certain identity, disagreement near-certain non-identity;
    # "near" = every difference is one character edit (a keying typo), which different people almost never share
    "identity": {"same": (0.965, 1e-9), "near": (0.03, 1e-7), "diff": (0.005, 0.99999)},
}
DEFAULT_PRIOR = 1e-4  # P(two random records are the same person); re-estimated from data per run
NAME_CONFLICT_LEVELS = ("partial", "weak", "none")

# Day-month pairs Indian registers use when only the year is known; they say nothing about the date.
PLACEHOLDER_DAY_MONTH = {"01-01", "07-01"}
_ADDRESS_ABBREV = {"rd": "road", "st": "street", "apts": "apartments", "apt": "apartment", "soc": "society", "chs": "society",
                   "ngr": "nagar", "opp": "", "nr": "", "near": "", "behind": "", "flat": "", "no": "", "house": "", "h": ""}


def parse_dob(value: object) -> str | None:
    """ISO date (YYYY-MM-DD) from common forms, or None when absent, invalid or a year-only placeholder."""
    if not value:
        return None
    text = str(value).strip()
    parts = re.findall(r"\d+", text)
    if len(parts) == 1 and len(parts[0]) == 8:  # YYYYMMDD
        parts = [parts[0][:4], parts[0][4:6], parts[0][6:]]
    if len(parts) != 3:
        return None
    if len(parts[0]) == 4:
        y, m, d = parts
    elif len(parts[2]) == 4:  # DD-MM-YYYY, the usual Indian form
        d, m, y = parts
    else:
        return None
    if not (1 <= int(m) <= 12 and 1 <= int(d) <= 31 and 1890 <= int(y) <= 2030):
        return None
    m, d = m.zfill(2), d.zfill(2)
    if f"{m}-{d}" in PLACEHOLDER_DAY_MONTH:
        return None
    return f"{y}-{m}-{d}"


def parse_address(value: object) -> tuple[frozenset[str], str | None]:
    """Address tokens (lower-case Latin, abbreviations expanded, filler dropped) and the house/flat number:
    the first token with a digit. "4/B", "4-B" and "4B" are one token."""
    if not value:
        return frozenset(), None
    from .names import to_latin

    text = to_latin(str(value)).lower()
    text = re.sub(r"(\d+)\s*[/\-]?\s*([a-z])\b", r"\1\2", text)
    text = "".join(c if c.isalnum() else " " for c in text)
    toks = [t for t in (_ADDRESS_ABBREV.get(t, t) for t in text.split()) if t]
    return frozenset(toks), next((t for t in toks if any(c.isdigit() for c in t)), None)


def address_tokens(value: object) -> frozenset[str]:
    return parse_address(value)[0]


def _one_component_apart(a: str, b: str) -> bool:
    """Dates that differ by a day/month swap, or in one component by a single keying slip."""
    ya, ma, da = a.split("-")
    yb, mb, db = b.split("-")
    if ya == yb and ma == db and da == mb:
        return True
    diffs = [(x, y) for x, y in ((ya, yb), (ma, mb), (da, db)) if x != y]
    if len(diffs) != 1:
        return False
    x, y = diffs[0]
    return sum(c1 != c2 for c1, c2 in zip(x, y)) == 1 or (len(x) == 2 and x[::-1] == y)


def birth_level(a: "PersonRecord", b: "PersonRecord") -> str | None:
    if a.dob and b.dob:
        if a.dob == b.dob:
            return "dob_exact"
        if _one_component_apart(a.dob, b.dob):
            return "dob_near"
        if abs(int(a.dob[:4]) - int(b.dob[:4])) <= 1:
            return "dob_diff"
    if a.birth_year and b.birth_year:
        d = abs(a.birth_year - b.birth_year)
        return "close" if d <= 1 else "near" if d <= 3 else "far"
    return None


def place_level(a: "PersonRecord", b: "PersonRecord") -> str | None:
    if a.address and b.address:
        inter = len(a.address & b.address)
        jac = inter / len(a.address | b.address)
        same_house = bool(a.house and a.house == b.house)
        if jac >= 0.9:
            return "address_same"
        if jac >= 0.7 or (same_house and jac >= 0.5):
            return "address_near"
    if a.district and b.district:
        return "same" if a.district == b.district else "diff"
    return None


@dataclass
class PersonRecord:
    id: str
    name: ParsedName
    father: ParsedName | None = None
    birth_year: int | None = None
    gender: str | None = None
    district: str | None = None
    phones: frozenset[str] = frozenset()
    source: str = ""
    truth_id: str | None = None  # only present in synthetic benchmarks
    ids: frozenset[str] = frozenset()  # Aadhaar / PAN / passport values, prefixed by kind
    dob: str | None = None  # full date of birth (ISO), when the source records one that is not a placeholder
    address: frozenset[str] = frozenset()  # address tokens
    house: str | None = None  # the first address token with a digit (house / flat number)

    @classmethod
    def from_props(cls, obj_id: str, props: dict, phones: Iterable[str] = (), source: str = "") -> "PersonRecord":
        raw = props.get("name_native") or props.get("name") or ""
        name = normalize_name(raw)
        father_raw = props.get("father_name") or name.relation_name
        birth = props.get("birth_year")
        if birth is None and isinstance(props.get("age"), int) and props.get("age_as_of"):
            birth = int(str(props["age_as_of"])[:4]) - props["age"]
        return cls(
            id=obj_id,
            name=name,
            father=normalize_name(father_raw) if father_raw else None,
            birth_year=birth,
            gender=props.get("gender") if props.get("gender") in ("M", "F", "X") else None,
            district=props.get("district_lgd"),
            phones=frozenset(phones),
            source=source,
            truth_id=props.get("_truth_id"),
            ids=frozenset(f"{k}:{props[k]}" for k in ("aadhaar", "pan", "passport_no") if props.get(k)),
            dob=parse_dob(props.get("dob")),
            address=parse_address(props.get("address"))[0],
            house=parse_address(props.get("address"))[1],
        )

    @property
    def full_keys(self) -> list[str]:
        return [k for t, k in zip(self.name.tokens, self.name.keys) if len(t) > 1 and k]

    @property
    def father_given_keys(self) -> frozenset[str]:
        if not self.father:
            return frozenset()
        own = set(self.full_keys[-1:]) | set(self.full_keys[:1])  # surname may be first or last
        keys = {k for t, k in zip(self.father.tokens, self.father.keys) if len(t) > 1 and k}
        return frozenset(keys - own) or frozenset(keys)

    @property
    def name_signature(self) -> str:
        return " ".join(sorted(self.full_keys))


@dataclass(frozen=True)
class IdentityEvidence:
    shared_kinds: tuple[str, ...]
    agreeing_kinds: tuple[str, ...]
    conflicting_kinds: tuple[str, ...]
    typo_kinds: tuple[str, ...] = ()  # conflicting kinds whose every difference is a single-character edit


def _one_edit_apart(a: str, b: str) -> bool:
    """True if a and b differ by exactly one substitution, insertion, deletion or adjacent transposition."""
    if a == b or abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        diff = [i for i, (x, y) in enumerate(zip(a, b)) if x != y]
        return len(diff) == 1 or (len(diff) == 2 and diff[1] == diff[0] + 1 and a[diff[0]] == b[diff[1]] and a[diff[1]] == b[diff[0]])
    short, long_ = (a, b) if len(a) < len(b) else (b, a)
    i = next((k for k in range(len(short)) if short[k] != long_[k]), len(short))
    return short[i:] == long_[i + 1:]


def identity_evidence(a: PersonRecord, b: PersonRecord) -> IdentityEvidence:
    """Compare identifiers by kind, retaining agreement and contradiction independently.

    Multiple distinct values of a shared kind are contradictory even when the two
    records also share one value. Missing kinds do not count as disagreement.
    """
    by_kind = []
    for record in (a, b):
        values: dict[str, set[str]] = defaultdict(set)
        for identifier in record.ids:
            kind, value = identifier.split(":", 1)
            values[kind].add(value)
        by_kind.append(values)
    left, right = by_kind
    shared = tuple(sorted(left.keys() & right.keys()))
    conflicting = tuple(kind for kind in shared if len(left[kind] | right[kind]) > 1)

    def typo(kind: str) -> bool:
        only_l, only_r = left[kind] - right[kind], right[kind] - left[kind]
        if not only_l or not only_r or len(left[kind]) > 1 or len(right[kind]) > 1:
            return False  # one value each side, differing only by a keying slip; several values are a real conflict
        (x,), (y,) = only_l, only_r
        return min(len(x), len(y)) >= 6 and _one_edit_apart(x, y)

    return IdentityEvidence(
        shared,
        tuple(kind for kind in shared if left[kind] & right[kind]),
        conflicting,
        tuple(kind for kind in conflicting if typo(kind)),
    )


@dataclass
class PairScore:
    a: str
    b: str
    probability: float
    match_weight: float
    levels: dict[str, str] = field(default_factory=dict)
    weights: dict[str, float] = field(default_factory=dict)
    identity_conflicts: tuple[str, ...] = ()
    # The given names disagree (Ramesh vs Suresh Patil). Twins and relatives share a father, a birth date and
    # an address; only the given name tells them apart, so such a pair is never linked automatically.
    name_conflict: bool = False

    @property
    def auto_eligible(self) -> bool:
        return not self.identity_conflicts and not self.name_conflict

    def explain(self) -> list[str]:
        out = []
        for feat, lvl in self.levels.items():
            w = self.weights[feat]
            out.append(f"{feat}={lvl} ({'+' if w >= 0 else ''}{w:.1f})")
        return out


def _jaro_winkler(s1: str, s2: str) -> float:
    if s1 == s2:
        return 1.0
    l1, l2 = len(s1), len(s2)
    if not l1 or not l2:
        return 0.0
    rng = max(max(l1, l2) // 2 - 1, 0)
    m1, m2 = [False] * l1, [False] * l2
    matches = 0
    for i, c in enumerate(s1):
        for j in range(max(0, i - rng), min(i + rng + 1, l2)):
            if not m2[j] and s2[j] == c:
                m1[i] = m2[j] = True
                matches += 1
                break
    if not matches:
        return 0.0
    t, k = 0, 0
    for i in range(l1):
        if m1[i]:
            while not m2[k]:
                k += 1
            if s1[i] != s2[k]:
                t += 1
            k += 1
    jaro = (matches / l1 + matches / l2 + (matches - t / 2) / matches) / 3
    prefix = 0
    for a, b in zip(s1[:4], s2[:4]):
        if a != b:
            break
        prefix += 1
    return jaro + prefix * 0.1 * (1 - jaro)


def _tok_match(t1: str, k1: str, t2: str, k2: str) -> bool:
    return t1 == t2 or (k1 and k1 == k2) or (len(t1) > 3 and len(t2) > 3 and _jaro_winkler(t1, t2) >= 0.92)


def _maximum_token_matching(a: list[tuple[str, str]], b: list[tuple[str, str]]) -> dict[int, int]:
    """Maximum-cardinality token alignment using augmenting paths.

    Inputs are canonically sorted by the caller. Exact agreements are visited
    before phonetic and fuzzy agreements; an earlier choice can be reassigned
    when it would otherwise leave a compatible token unmatched.
    """
    edges = [sorted(
        (j for j, (tb, kb) in enumerate(b) if _tok_match(ta, ka, tb, kb)),
        key=lambda j: (ta != b[j][0], ka != b[j][1], b[j], j),
    ) for ta, ka in a]
    right_to_left: dict[int, int] = {}

    def augment(i: int, visited: set[int]) -> bool:
        for j in edges[i]:
            if j in visited:
                continue
            visited.add(j)
            if j not in right_to_left or augment(right_to_left[j], visited):
                right_to_left[j] = i
                return True
        return False

    for i in range(len(a)):
        augment(i, set())
    return {i: j for j, i in right_to_left.items()}


TYPO_JW = 0.88  # leftover name tokens this similar are one name mistyped (aidan/aidsn 0.91); different names score
                # lower (mahesh/mangesh 0.87, sachin/sagar 0.88 below the cut, ramesh/suresh 0.78)


def typo_only(a: ParsedName, b: ParsedName) -> bool:
    """True when the full name tokens left unaligned on each side pair off as typing slips (Jaro-Winkler >=
    TYPO_JW). Initials on either side, or a token with no counterpart, mean the names may truly differ."""
    if any(len(t) == 1 for t in a.tokens + b.tokens):
        return False
    fa = sorted((t, k) for t, k in zip(a.tokens, a.keys) if len(t) > 1)
    fb = sorted((t, k) for t, k in zip(b.tokens, b.keys) if len(t) > 1)
    aligned = _maximum_token_matching(fa, fb)
    ua = [t for i, (t, _) in enumerate(fa) if i not in aligned]
    used = set(aligned.values())
    ub = [t for j, (t, _) in enumerate(fb) if j not in used]
    if not ua or len(ua) != len(ub):
        return False
    for x in sorted(ua):
        best = max(ub, key=lambda y: _jaro_winkler(x, y))
        if _jaro_winkler(x, best) < TYPO_JW:
            return False
        ub.remove(best)
    return True


def compare_names(a: ParsedName, b: ParsedName, extra_ok_a: frozenset[str] = frozenset(), extra_ok_b: frozenset[str] = frozenset()) -> str:
    """Compare two parsed names. extra_ok_* are phonetic keys of tokens that may appear as an
    unmatched middle name without counting against the match: the father's given name, by
    Maharashtrian convention (Dattatray Vishnu Patil == Dattatray Patil, son of Vishnu)."""
    if not a.tokens or not b.tokens:
        return "none"
    if sorted(a.tokens) == sorted(b.tokens):
        return "exact"
    # Tamil script does not mark voicing: when either name is written in it, tokens compare on voiceless keys
    tamil = "TAMIL" in (a.script, b.script)
    ka = a.voiceless if tamil and a.voiceless else a.keys
    kb = b.voiceless if tamil and b.voiceless else b.keys
    fa = sorted((t, k) for t, k in zip(a.tokens, ka) if len(t) > 1)
    fb = sorted((t, k) for t, k in zip(b.tokens, kb) if len(t) > 1)
    ia = sorted(t for t in a.tokens if len(t) == 1)
    ib = sorted(t for t in b.tokens if len(t) == 1)
    # Fix both token order and graph orientation: ambiguous alignments must not
    # depend on source ordering, surname position, or which record was queried first.
    if (fa, ia, sorted(extra_ok_a)) > (fb, ib, sorted(extra_ok_b)):
        a, b, fa, fb, ia, ib, ka, kb, extra_ok_a, extra_ok_b = b, a, fb, fa, ib, ia, kb, ka, extra_ok_b, extra_ok_a
    alignment = _maximum_token_matching(fa, fb)
    used_b = set(alignment.values())
    matched = len(alignment)
    unmatched_a = [t for i, (t, _) in enumerate(fa) if i not in alignment]
    unmatched_b = [t for j, (t, _) in enumerate(fb) if j not in used_b]
    # initials on one side explain full tokens on the other; an initial that explains
    # nothing while the other side still has an unexplained given name is a contradiction
    # ("N. Y. Sayyed" is not "Rukhsar Yoosuf Sayyed")
    used_initials = bool(ia or ib)
    common_initials = Counter(ia) & Counter(ib)
    remaining_a = list((Counter(ia) - common_initials).elements())
    remaining_b = list((Counter(ib) - common_initials).elements())
    leftover_a, leftover_b = [], []
    for init in remaining_a:
        hit = next((t for t in unmatched_b if t[0] == init), None)
        if hit:
            unmatched_b.remove(hit)
        else:
            leftover_a.append(init)
    for init in remaining_b:
        hit = next((t for t in unmatched_a if t[0] == init), None)
        if hit:
            unmatched_a.remove(hit)
        else:
            leftover_b.append(init)
    conflict = bool((leftover_a and (leftover_b or unmatched_b)) or (leftover_b and unmatched_a))
    keys_a = dict(zip(a.tokens, ka))
    keys_b = dict(zip(b.tokens, kb))
    patronymic = [t for t in unmatched_a if keys_a.get(t) in extra_ok_b] + [t for t in unmatched_b if keys_b.get(t) in extra_ok_a]
    unmatched_a = [t for t in unmatched_a if keys_a.get(t) not in extra_ok_b]
    unmatched_b = [t for t in unmatched_b if keys_b.get(t) not in extra_ok_a]
    if matched == 0:
        return "none"
    if conflict:
        return "weak"
    if not unmatched_a and not unmatched_b:
        if used_initials:
            return "initials"
        return "phonetic" if not patronymic or matched >= 2 else "subset"
    if unmatched_a and unmatched_b:
        return "weak" if matched == 1 else "partial"  # conflicting given names: Ramesh Patil vs Suresh Patil
    # one side simply has an extra (middle) name
    if matched >= 2:
        return "subset"
    return "partial" if used_initials else "weak"


def _weight(params: dict, feature: str, level: str, u_override: float | None = None) -> float:
    m, u = params[feature][level]
    if u_override is not None:
        u = max(u, u_override)
    return math.log2(m / u)


class Matcher:
    def __init__(self, records: list[PersonRecord], *, max_block: int = 400, params: dict | None = None):
        self.records = {r.id: r for r in records}
        self.max_block = max_block
        supplied = M_U if params is None else params
        if supplied.keys() != M_U.keys() or any(supplied[f].keys() != M_U[f].keys() for f in M_U):
            raise ValueError("Matcher parameter schema does not match this runtime")
        self.params = {f: {level: tuple(float(v) for v in values) for level, values in levels.items()}
                       for f, levels in supplied.items()}
        if any(len(values) != 2 or any(not math.isfinite(v) or not 0 < v <= 1 for v in values)
               for levels in self.params.values() for values in levels.values()):
            raise ValueError("Matcher parameters must contain finite m/u probabilities in (0, 1]")
        n = max(len(records), 1)
        sig_counts = Counter(r.name_signature for r in records if r.name_signature)
        # term frequency of each full name signature, used as a floor on u for name agreement;
        # frequencies are only meaningful once there are enough records to estimate them
        self.name_tf = {s: c / n for s, c in sig_counts.items() if c >= 3} if n >= 100 else {}
        self.prior = DEFAULT_PRIOR
        self._name_cache: dict[tuple, str] = {}  # names repeat inside a surname block; compare each pair of spellings once

    def estimate_prior(self, recall: float = 0.6) -> float:
        """Splink-style estimate of P(match) for a random pair: count blocked pairs passing a
        strict deterministic rule, divide by the rule's assumed recall and by all possible pairs."""
        n = len(self.records)
        total = n * (n - 1) / 2
        strict = 0
        for a, b in self.blocks():
            ra, rb = self.records[a], self.records[b]
            lvl = self._name_level(ra, rb)
            same_birth = ra.birth_year and rb.birth_year and abs(ra.birth_year - rb.birth_year) <= 1
            if lvl in ("exact", "phonetic") and (same_birth or (ra.phones & rb.phones)):
                strict += 1
        if total and strict:
            self.prior = min(max(strict / recall / total, 1e-6), 0.01)
        return self.prior

    def blocks(self) -> Iterable[tuple[str, str]]:
        index: dict[str, list[str]] = defaultdict(list)
        for r in self.records.values():
            keys = sorted(set(r.full_keys))
            for k1, k2 in itertools.combinations(keys, 2):
                index[f"nn:{k1}|{k2}"].append(r.id)
            if keys and r.name.tokens:
                # every (full-token key, first letter of another token) pair, so "R. P. Tiwari"
                # meets "Rajesh Pankaj Tiwari" whichever way round the surname is written
                full = [(t, k) for t, k in zip(r.name.tokens, r.name.keys) if len(t) > 1 and k]
                letters = {t[0] for t in r.name.tokens}
                for t, k in full:
                    for i in (letters - {t[0]}) if len(full) > 1 else letters:
                        index[f"ni:{k}|{i}"].append(r.id)
                    if r.birth_year:
                        index[f"nb:{k}|{r.birth_year // 3}"].append(r.id)
            for ph in r.phones:
                index[f"ph:{ph}"].append(r.id)
        for r in self.records.values():
            for x in r.ids:
                index[f"id:{x}"].append(r.id)
            # a full, non-placeholder date of birth meets records whose names were mangled beyond the name keys;
            # with the place, so a common birthday does not make a large block
            if r.dob:
                index[f"db:{r.dob}|{r.district or ''}"].append(r.id)
                if r.house:
                    index[f"dh:{r.dob}|{r.house}"].append(r.id)
        # Adaptive blocking: a small block is compared as it is; a block that has grown with the
        # population is split by overlapping 5-year birth windows, then district, then gender, until
        # each part is small. Measured on a 10k-person world: half the pairs of fixed blocking at the
        # same pair completeness (99.92%); pairs then grow with the population instead of its square.
        seen: set[tuple[str, str]] = set()
        for ids in index.values():
            for part in self._refine(sorted(set(ids)), 0):
                for a, b in itertools.combinations(part, 2):
                    if (a, b) not in seen:
                        seen.add((a, b))
                        yield a, b
        # Tamil script does not mark voicing, so a Tamil-script record and its English spelling can differ in
        # every key (Murukan / Murugan). Voicing-merged name blocks meet them; only pairs with a Tamil-script
        # member are taken from these blocks, so no other language's candidate pairs grow.
        tamil = {r.id for r in self.records.values() if r.name.script == "TAMIL"}
        if tamil:
            vindex: dict[str, list[str]] = defaultdict(list)
            for r in self.records.values():
                vkeys = sorted({k for t, k in zip(r.name.tokens, r.name.voiceless) if len(t) > 1 and k})
                for k1, k2 in itertools.combinations(vkeys, 2):
                    vindex[f"vn:{k1}|{k2}"].append(r.id)
                if len(vkeys) == 1:
                    vindex[f"v1:{vkeys[0]}"].append(r.id)
            for ids in vindex.values():
                if tamil.isdisjoint(ids):
                    continue
                for part in self._refine(sorted(set(ids)), 0):
                    for a, b in itertools.combinations(part, 2):
                        if (a in tamil or b in tamil) and (a, b) not in seen:
                            seen.add((a, b))
                            yield a, b

    SMALL_BLOCK = 40

    def _refine(self, ids: list[str], depth: int) -> Iterable[list[str]]:
        if len(ids) < 2:
            return
        if len(ids) <= self.SMALL_BLOCK:
            yield ids
            return
        if depth == 3:
            if len(ids) <= self.max_block:
                yield ids
            return
        parts: dict[str, list[str]] = defaultdict(list)
        unknown: list[str] = []
        for i in ids:
            r = self.records[i]
            if depth == 0:
                keys = [f"a{r.birth_year // 5}", f"b{(r.birth_year + 2) // 5}"] if r.birth_year else []
            elif depth == 1:
                keys = [r.district] if r.district else []
            else:
                keys = [r.gender] if r.gender else []
            if not keys:
                unknown.append(i)
            for k in keys:
                parts[k].append(i)
        if not parts:  # this dimension says nothing about these records: try the next one
            yield from self._refine(ids, depth + 1)
            return
        for members in parts.values():
            # a record without the value could belong to any part
            yield from self._refine(sorted(set(members + unknown)), depth + 1)

    def _name_level(self, a: PersonRecord, b: PersonRecord, fa: frozenset[str] = frozenset(), fb: frozenset[str] = frozenset()) -> str:
        # keyed on tokens and phonetic keys, not the transliteration alone: two spellings can share
        # a transliteration yet differ in their keys (cross-script input)
        ck = (tuple(a.name.tokens), tuple(a.name.keys), a.name.script, tuple(b.name.tokens), tuple(b.name.keys), b.name.script, fa, fb)
        lvl = self._name_cache.get(ck)
        if lvl is None:
            lvl = self._name_cache[ck] = compare_names(a.name, b.name, fa, fb)
        return lvl

    def score(self, a: PersonRecord, b: PersonRecord) -> PairScore:
        levels: dict[str, str] = {}
        weights: dict[str, float] = {}

        fa, fb = a.father_given_keys, b.father_given_keys
        lvl = self._name_level(a, b, fa, fb)
        tf = None
        if lvl in ("exact", "phonetic") and a.name_signature == b.name_signature:
            tf = self.name_tf.get(a.name_signature)
        levels["name"], weights["name"] = lvl, _weight(self.params, "name", lvl, tf)

        if fa and fb:
            # compare fathers' given names only: the family surname is already in the name feature
            flvl = "match" if fa == fb else "partial" if fa & fb else "none"
            levels["father"], weights["father"] = flvl, _weight(self.params, "father", flvl)

        alvl = birth_level(a, b)
        if alvl:
            levels["age"], weights["age"] = alvl, _weight(self.params, "age", alvl)

        dl = place_level(a, b)
        if dl in ("address_same", "address_near") and alvl == "far":
            # a generation apart at one address is a household (grandfather and grandson often share a
            # name in Indian families), not one person: the address then counts only as the same district
            dl = "same"
        if dl:
            levels["district"], weights["district"] = dl, _weight(self.params, "district", dl)

        if a.phones and b.phones:
            pl = "shared" if a.phones & b.phones else "diff"
            levels["phone"], weights["phone"] = pl, _weight(self.params, "phone", pl)

        identity = identity_evidence(a, b)
        if identity.shared_kinds:
            # a typo-only difference is evidence for the match, but the pair keeps its identity conflict, so the
            # resolver never links it automatically: a person confirms that the numbers are one number mistyped
            il = ("near" if set(identity.conflicting_kinds) <= set(identity.typo_kinds) else "diff") if identity.conflicting_kinds else "same"
            levels["identity"], weights["identity"] = il, _weight(self.params, "identity", il)

        if a.gender and b.gender:
            gl = "same" if a.gender == b.gender else "diff"
            levels["gender"], weights["gender"] = gl, _weight(self.params, "gender", gl)

        w = math.log2(self.prior / (1 - self.prior)) + sum(weights.values())
        p = 1 / (1 + 2 ** (-w))
        conflict = levels["name"] in NAME_CONFLICT_LEVELS and not typo_only(a.name, b.name)
        return PairScore(a.id, b.id, p, w, levels, weights, identity.conflicting_kinds, conflict)

    def score_pairs(self, min_probability: float = 0.0) -> list[PairScore]:
        out = []
        for a, b in self.blocks():
            s = self.score(self.records[a], self.records[b])
            if s.probability >= min_probability:
                out.append(s)
        return out

    PRIOR_BOUNDS = (1e-6, 0.01)

    def score_with_prior(self, min_probability: float = 0.0, recall: float = 0.6) -> tuple[list[PairScore], float]:
        """estimate_prior() then score_pairs() in one pass over the blocks, with identical results.

        The prior enters a pair's weight only as the constant log-odds term, so each pair is scored once
        under the largest prior estimate_prior can return; pairs that could not reach `min_probability`
        even then are dropped. The prior is estimated from the same pass (strict rule / assumed recall),
        and every kept pair's weight is shifted to it exactly."""
        lo, hi = self.PRIOR_BOUNDS
        self.prior = hi
        kept: list[PairScore] = []
        strict = 0
        for a, b in self.blocks():
            ra, rb = self.records[a], self.records[b]
            lvl = self._name_level(ra, rb)
            same_birth = ra.birth_year and rb.birth_year and abs(ra.birth_year - rb.birth_year) <= 1
            if lvl in ("exact", "phonetic") and (same_birth or (ra.phones & rb.phones)):
                strict += 1
            s = self.score(ra, rb)
            if s.probability >= min_probability:
                kept.append(s)
        n = len(self.records)
        total = n * (n - 1) / 2
        prior = min(max(strict / recall / total, lo), hi) if total and strict else DEFAULT_PRIOR
        shift = math.log2(prior / (1 - prior)) - math.log2(hi / (1 - hi))
        self.prior = prior
        out = []
        for s in kept:
            w = s.match_weight + shift
            p = 1 / (1 + 2 ** (-w))
            if p >= min_probability:
                s.match_weight, s.probability = w, p
                out.append(s)
        return out, prior


def clusters(ids: Iterable[str], edges: Iterable[tuple[str, str]]) -> dict[str, str]:
    """Union-find over accepted links. Returns record id -> cluster id (smallest member)."""
    parent = {i: i for i in ids}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in edges:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)
    return {i: find(i) for i in parent}


def pairwise_metrics(records: list[PersonRecord], cluster_of: dict[str, str]) -> dict[str, float]:
    """Exact pairwise metrics using a contingency table, without enumerating pairs."""
    truth: Counter = Counter()
    pred: Counter = Counter()
    overlap: Counter = Counter()
    for r in records:
        if r.truth_id is None:
            continue
        cluster = cluster_of[r.id]
        truth[r.truth_id] += 1
        pred[cluster] += 1
        overlap[(r.truth_id, cluster)] += 1
    truth_pairs = sum(n * (n - 1) // 2 for n in truth.values())
    pred_pairs = sum(n * (n - 1) // 2 for n in pred.values())
    tp = sum(n * (n - 1) // 2 for n in overlap.values())
    precision = tp / pred_pairs if pred_pairs else 1.0
    recall = tp / truth_pairs if truth_pairs else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "true_pairs": truth_pairs,
        "predicted_pairs": pred_pairs,
        "true_positives": tp,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
    }

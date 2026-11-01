"""Indian name normalisation: script detection, transliteration, honorifics, variants.

Pipeline (design doc Section 12.2, steps 1-5):
  1. detect script            -> unicode block of the first letter
  2. transliterate to Latin   -> indic_transliteration (IAST), schwa deletion, ASCII fold
  3. normalise                -> strip honorifics and relation markers, canonicalise variants
  4. split                    -> tokens; initials kept as single letters
  5. phonetic key             -> see phonetic.py

Neural transliteration (AI4Bharat IndicXlit) can replace step 2 for better recall on
rare names; this rule-based path has no model weights and runs anywhere.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache

from .phonetic import phonetic_key, voiceless_key

try:
    from indic_transliteration import sanscript
    from indic_transliteration.sanscript import transliterate as _xlit
except ImportError:  # pragma: no cover - optional at import time, required for non-Latin input
    sanscript = None
    _xlit = None

# Unicode block start -> sanscript scheme name
_SCRIPT_BLOCKS = [
    (0x0900, 0x097F, "DEVANAGARI"),
    (0x0980, 0x09FF, "BENGALI"),
    (0x0A00, 0x0A7F, "GURMUKHI"),
    (0x0A80, 0x0AFF, "GUJARATI"),
    (0x0B00, 0x0B7F, "ORIYA"),
    (0x0B80, 0x0BFF, "TAMIL"),
    (0x0C00, 0x0C7F, "TELUGU"),
    (0x0C80, 0x0CFF, "KANNADA"),
    (0x0D00, 0x0D7F, "MALAYALAM"),
    (0x0600, 0x06FF, "ARABIC"),  # Urdu, Kashmiri (Perso-Arabic): rule-based consonant transliteration below
]

HONORIFICS = {
    "shri", "shree", "sri", "smt", "shrimati", "srimati", "kum", "kumari", "km", "mr", "mrs", "ms", "miss",
    "dr", "late", "lt", "sh", "adv", "prof", "capt", "col", "maj", "er", "ca", "hon", "janab", "sardar",
    "shriman", "thiru", "thirumathi", "selvi", "sow", "chi",
}
RELATION_MARKERS = re.compile(r"\b(s/o|d/o|w/o|c/o|son of|daughter of|wife of|husband of|alias|urf|@)\b", re.I)

# Spelling variants that are the same name. Canonical form on the right.
VARIANTS = {
    "mohd": "muhammad", "md": "muhammad", "mohammad": "muhammad", "mohammed": "muhammad", "mohamad": "muhammad",
    "mahammad": "muhammad", "muhammed": "muhammad", "mohamed": "muhammad", "mahmad": "muhammad",
    "shaikh": "shaikh", "sheikh": "shaikh", "shaik": "shaikh", "sk": "shaikh", "shekh": "shaikh", "seikh": "shaikh",
    "syed": "sayyed", "sayed": "sayyed", "saiyed": "sayyed", "saiyad": "sayyed", "sayyad": "sayyed",
    "abdul": "abdul", "abd": "abdul",
    "kumar": "kumar", "kr": "kumar",
    "laxmi": "lakshmi", "luxmi": "lakshmi",
    "chaudhary": "chaudhari", "choudhary": "chaudhari", "chaudhry": "chaudhari", "choudhari": "chaudhari",
    "kulkarni": "kulkarni",
    "dnyaneshwar": "gyaneshwar", "dnyanesh": "gyanesh",
}

# IAST -> ASCII. Order matters: aspirated "ch" (IAST छ) before plain "c" (IAST च).
_IAST_FOLD = [
    ("jñ", "gy"),  # ज्ञ is "dny" in Marathi, "gy" in Hindi; VARIANTS maps dny -> gy
    ("ch", "\x00"), ("c", "ch"), ("\x00", "chh"),
    ("ā", "a"), ("ī", "i"), ("ū", "u"), ("ṛ", "ri"), ("ṝ", "ri"), ("ḷ", "l"), ("r̥", "ri"),
    ("ē", "e"), ("ō", "o"), ("ṅ", "n"), ("ñ", "n"), ("ṭ", "t"), ("ḍ", "d"), ("ṇ", "n"),
    ("ś", "sh"), ("ṣ", "sh"), ("ṃ", "n"), ("ṁ", "n"), ("ḥ", "h"), ("ṉ", "n"), ("ṟ", "r"), ("ḻ", "l"), ("ẏ", "y"),
]
_VOWELS = set("aeiou")  # ASCII vowels (used after folding)


def detect_script(text: str) -> str:
    for ch in text:
        cp = ord(ch)
        if ch.isalpha():
            if cp < 0x0250:
                return "LATIN"
            for lo, hi, name in _SCRIPT_BLOCKS:
                if lo <= cp <= hi:
                    return name
            return "OTHER"
    return "LATIN"


_DRAVIDIAN = {"TAMIL", "TELUGU", "KANNADA", "MALAYALAM"}
# Schwa deletion runs on IAST, where the inherent short "a" is distinct from long "ā".
# (Folding to ASCII first would turn संगीता "saṃgītā" into "sangita" and then wrongly into "sangit".)
_IAST_VOWELS = ("ai", "au", "a", "ā", "i", "ī", "u", "ū", "ṛ", "ṝ", "ḷ", "ḹ", "e", "o")
_IAST_ASPIRATES = ("kh", "gh", "ch", "jh", "ṭh", "ḍh", "th", "dh", "ph", "bh")
_NASALS = ("n", "m", "ṃ", "ṁ", "ṅ", "ñ", "ṇ")


def _phonemes(word: str) -> list[str]:
    out, i = [], 0
    while i < len(word):
        for unit in _IAST_ASPIRATES + ("ai", "au"):
            if word.startswith(unit, i):
                out.append(unit)
                i += len(unit)
                break
        else:
            out.append(word[i])
            i += 1
    return out


def _is_cons(ph: str) -> bool:
    return ph not in _IAST_VOWELS


def _schwa_delete(word: str) -> str:
    """Hindi/Marathi schwa deletion on an IAST transliteration.

    * word-final inherent "a" after a single consonant is dropped (rameśa -> rameś)
      and after a nasal + consonant (siṃgha -> siṃgh, ānaṃda -> ānaṃd), but kept after
      other clusters (candra, miśra, kṛṣṇa);
    * medial "a" in the V C _ C V context is dropped (iraphāna -> irphān).
    Rule-based approximation of Ohala (1983); IndicXlit does better on rare names.
    """
    ph = _phonemes(word)
    if len(ph) > 2 and ph[-1] == "a" and _is_cons(ph[-2]):
        single = not _is_cons(ph[-3])
        nasal_stop = len(ph) > 3 and ph[-3] in _NASALS and not _is_cons(ph[-4])
        if single or nasal_stop:
            ph = ph[:-1]
    i = 2
    while i < len(ph) - 2:
        if ph[i] == "a" and _is_cons(ph[i - 1]) and not _is_cons(ph[i - 2]) and _is_cons(ph[i + 1]) and not _is_cons(ph[i + 2]):
            del ph[i]
            continue
        i += 1
    return "".join(ph)


def _fold(iast: str) -> str:
    for a, b in _IAST_FOLD:
        iast = iast.replace(a, b)
    return "".join(c for c in unicodedata.normalize("NFKD", iast) if not unicodedata.combining(c))


def _tamil_fold(word: str) -> str:
    """Tamil script does not mark voicing; apply the usual pronunciation rules."""
    word = re.sub(r"^ch", "s", word)  # initial ச is /s/ (Selvi, Subramanian)
    # single intervocalic stops are voiced: murukan -> murugan, maturai -> madurai
    word = re.sub(r"(?<=[aeiou])k(?=[aeiou])", "g", word)
    word = re.sub(r"(?<=[aeiou])t(?=[aeiou])", "d", word)
    word = re.sub(r"(?<=[aeiou])p(?=[aeiou])", "b", word)
    word = re.sub(r"(?<=[aeiou])ch(?=[aeiou])", "s", word)
    return word


# Perso-Arabic (Urdu) letters -> Latin. Urdu writes short vowels only as optional marks, which are dropped;
# the phonetic key keeps the consonant skeleton and the initial vowel, so the missing vowels do not matter.
_URDU = {
    "\u0628": "b", "\u067E": "p", "\u062A": "t", "\u0679": "t", "\u062B": "s", "\u062C": "j", "\u0686": "ch", "\u062D": "h",
    "\u062E": "kh", "\u062F": "d", "\u0688": "d", "\u0630": "z", "\u0631": "r", "\u0691": "r", "\u0632": "z", "\u0698": "zh",
    "\u0633": "s", "\u0634": "sh", "\u0635": "s", "\u0636": "z", "\u0637": "t", "\u0638": "z", "\u063A": "gh", "\u0641": "f",
    "\u0642": "q", "\u06A9": "k", "\u0643": "k", "\u06AF": "g", "\u0644": "l", "\u0645": "m", "\u0646": "n", "\u06BA": "n",
    "\u06BE": "h", "\u0627": "a", "\u0622": "a", "\u0623": "a", "\u0625": "a", "\u06D2": "e", "\u06D3": "e",
    "\u0629": "a", "\u06C3": "a", "\u0621": "", "\u0626": "", "\u0624": "u",
}
_URDU_WAW, _URDU_YEH, _URDU_HEH, _URDU_AIN = "\u0648", ("\u06CC", "\u064A", "\u0649"), ("\u06C1", "\u0647", "\u06C2"), "\u0639"
_URDU_MARKS = {chr(c) for c in range(0x064B, 0x0660)} | {"\u0670"}


def _urdu_to_latin(word: str) -> str:
    chars = [c for c in word if c not in _URDU_MARKS]
    out: list[str] = []
    for i, c in enumerate(chars):
        nxt = chars[i + 1] if i + 1 < len(chars) else ""
        prev = chars[i - 1] if i else ""
        if c == _URDU_WAW:  # consonant w/v at the start, before alif or after alif; otherwise the vowel o/u
            out.append("v" if i == 0 or nxt in ("\u0627", "\u0622") or prev == "\u0627" else "u")
        elif c in _URDU_YEH:  # y at the start or before alif (kya, liya); otherwise the vowel i/e
            out.append("y" if i == 0 or (nxt == "\u0627" and i + 1 < len(chars) - 1) else "i")
        elif c in _URDU_HEH:  # h, except a final heh after a consonant, which writes a vowel (Fatima, parda)
            out.append("a" if i == len(chars) - 1 and i > 0 else "h")
        elif c == _URDU_AIN:  # ain: a vowel at the start, silent elsewhere
            out.append("a" if i == 0 else "")
        else:
            out.append(_URDU.get(c, ""))
    return "".join(out)


@lru_cache(maxsize=65536)
def to_latin(text: str) -> str:
    """Transliterate any supported Indic script to lower-case ASCII Latin."""
    script = detect_script(text)
    if script == "ARABIC":
        out = " ".join(_urdu_to_latin(w) for w in unicodedata.normalize("NFC", text).split())
    elif script in ("LATIN", "OTHER") or _xlit is None:
        out = text
    else:
        scheme = sanscript.TAMIL_SUB if script == "TAMIL" else getattr(sanscript, script)
        out = _xlit(text, scheme, sanscript.IAST)
        words = unicodedata.normalize("NFC", out).split()
        if script == "TAMIL":
            out = " ".join(_tamil_fold(_fold(w)) for w in words)
        elif script == "BENGALI":
            out = " ".join(_fold(_schwa_delete(w)).replace("v", "b") for w in words)  # Bengali has no /v/: Basu
        elif script in _DRAVIDIAN:
            out = " ".join(_fold(w) for w in words)
        else:
            out = " ".join(_fold(_schwa_delete(w)) for w in words)
    out = unicodedata.normalize("NFKD", out)
    out = "".join(c for c in out if not unicodedata.combining(c))
    return out.lower()


@dataclass
class ParsedName:
    raw: str
    script: str
    latin: str  # transliterated, cleaned, canonical tokens joined by space
    tokens: list[str] = field(default_factory=list)
    keys: list[str] = field(default_factory=list)  # phonetic key per token
    relation_name: str | None = None  # text after s/o, d/o, w/o
    voiceless: list[str] = field(default_factory=list)  # keys with voicing merged (k~g, t~d, p~b, s~ch~j): for Tamil script

    @property
    def surname(self) -> str | None:
        full = [t for t in self.tokens if len(t) > 1]
        return full[-1] if full else None

    @property
    def given(self) -> list[str]:
        return self.tokens[:-1] if len(self.tokens) > 1 else self.tokens


def normalize_name(raw: str) -> ParsedName:
    script = detect_script(raw)
    text = raw.strip()
    relation = None
    m = RELATION_MARKERS.search(text)
    if m:
        relation = text[m.end():].strip() or None
        text = text[: m.start()]
    latin = to_latin(text)
    latin = re.sub(r"[.\-_/,']", " ", latin)
    latin = re.sub(r"[^a-z ]", "", latin)
    tokens = []
    for tok in latin.split():
        if tok in HONORIFICS and len(latin.split()) > 1:
            continue
        tokens.append(VARIANTS.get(tok, tok))
    # "RK Patil" -> initials "r", "k"; only for short all-consonant tokens that are not real names
    expanded: list[str] = []
    for tok in tokens:
        if 1 < len(tok) <= 3 and not any(c in _VOWELS for c in tok) and tok not in VARIANTS.values():
            expanded.extend(tok)
        else:
            expanded.append(tok)
    return ParsedName(
        raw=raw,
        script=script,
        latin=" ".join(expanded),
        tokens=expanded,
        keys=[phonetic_key(t) for t in expanded],
        relation_name=normalize_name(relation).latin if relation else None,
        voiceless=[voiceless_key(t) for t in expanded],
    )


def name_search_terms(raw: str) -> list[str]:
    """Tokens to put in the full-text index for a name: latin tokens + phonetic keys."""
    p = normalize_name(raw)
    return p.tokens + [f"ph{k}" for k in p.keys if k]

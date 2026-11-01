"""An Indic-aware phonetic key for romanised names.

Classic Soundex/Metaphone were built for English. Indian names romanised by different
clerks vary in predictable ways, so the key merges exactly those differences:

* aspirated / unaspirated pairs: bh~b, dh~d, th~t, kh~k, gh~g, jh~j, chh~ch, ph~f
* sibilants: sh~s, and z~j (Hindi/Urdu nukta loss)
* v~w, q~k, x~ks, ck~k
* vowel length: aa~a, ee~i, ii~i, oo~u, uu~u, ou/au~o, ai/ei~e
* doubled consonants: mm~m, tt~t
* all non-initial vowels are dropped (schwa uncertainty dominates vowel noise)

Examples: Shaikh/Sheikh/Shekh -> "sk"; Vishwas/Wishwas/Viswas -> "vsvs";
Patil/Pateel -> "ptl"; Tamboli/Tanboli -> "tmbl".
"""

from __future__ import annotations

import re
from functools import lru_cache

_SUBS = [
    ("chh", "c"), ("ksh", "ks"), ("ch", "c"), ("sh", "s"), ("ph", "f"), ("bh", "b"), ("dh", "d"),
    ("th", "t"), ("kh", "k"), ("gh", "g"), ("jh", "j"), ("ck", "k"),
    ("aa", "a"), ("ee", "i"), ("ii", "i"), ("oo", "u"), ("uu", "u"), ("ou", "o"), ("au", "o"),
    ("ai", "e"), ("ei", "e"), ("z", "j"), ("w", "v"), ("q", "k"), ("x", "ks"),
]


@lru_cache(maxsize=131072)
def phonetic_key(token: str, max_len: int = 6) -> str:
    t = re.sub(r"[^a-z]", "", token.lower())
    if not t:
        return ""
    if len(t) == 1:
        return t  # an initial stays an initial
    for a, b in _SUBS:
        t = t.replace(a, b)
    t = t[0] + t[1:].replace("y", "i")
    t = re.sub(r"n(?=[bpm])", "m", t)  # anusvara assimilates before labials: tanboli ~ tamboli  # medial y is a vowel glide (Shreya ~ Shreia); initial y is kept (Yadav)
    # trailing 'h' after a vowel is usually silent romanisation noise (Shah ~ Sha)
    t = re.sub(r"(?<=[aeiou])h$", "", t)
    t = re.sub(r"(.)\1+", r"\1", t)
    head, tail = t[0], re.sub(r"[aeiouh]", "", t[1:])
    key = head + tail
    if head in "aeiou":
        key = "a" + tail  # all initial vowels compare equal (Irfan ~ Erfan)
    return key[:max_len]


_VOICING = str.maketrans({"g": "k", "d": "t", "b": "p", "j": "s", "c": "s", "f": "p", "z": "s", "l": "l"})


@lru_cache(maxsize=131072)
def voiceless_key(token: str, max_len: int = 6) -> str:
    """The phonetic key with voicing merged (k~g, t~d, p~b, s~ch~j~z, f~p). Tamil script does not mark voicing
    and writes one letter for s/ch/j, so a Tamil-script name and its English spelling differ exactly there
    (Murukan ~ Murugan, Cevviyar ~ Saviour). Used only when one side is in Tamil script."""
    k = phonetic_key(token, max_len=max_len + 2)
    if len(k) <= 1:
        return k
    k = k[0].translate(_VOICING) + k[1:].translate(_VOICING)
    k = re.sub(r"(.)\1+", r"\1", k)
    return k[:max_len]

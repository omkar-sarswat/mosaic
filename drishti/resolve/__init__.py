"""Resolve: entity resolution for Indian records (design doc Section 12.2)."""

from .names import normalize_name, to_latin
from .phonetic import phonetic_key

__all__ = ["normalize_name", "phonetic_key", "to_latin"]

"""Mission-track pattern engine: patterns as they form in the data, with their evidence. Leads, not findings."""

from . import detectors  # noqa: F401  (registers every detector)
from .engine import REGISTRY, Context, Hit, catalog, detect, run_patterns

__all__ = ["REGISTRY", "Context", "Hit", "catalog", "detect", "run_patterns"]

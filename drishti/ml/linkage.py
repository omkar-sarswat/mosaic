"""Portable inference for a learned record-linkage model.

No training identity, source ID, protected trait, or case outcome is a feature.
The output proposes record review; it never merges records or scores a person.
"""
from __future__ import annotations

import math

from ..resolve.matcher import PersonRecord, _jaro_winkler, compare_names, identity_evidence

NAME_LEVELS = ("exact", "phonetic", "subset", "initials", "partial", "weak", "none")
FEATURES = [*("name_" + name for name in NAME_LEVELS), "name_jaro", "token_overlap",
            "father_agreement", "father_missing", "year_close", "year_near", "year_conflict", "year_missing",
            "district_same", "district_missing", "phone_shared", "phone_conflict", "phone_missing",
            "identity_same", "identity_conflict", "identity_missing"]


def features(a: PersonRecord, b: PersonRecord) -> list[float]:
    level = compare_names(a.name, b.name, a.father_given_keys, b.father_given_keys)
    ta, tb = set(a.name.tokens), set(b.name.tokens)
    fa, fb = a.father_given_keys, b.father_given_keys
    year_missing = a.birth_year is None or b.birth_year is None
    gap = abs(a.birth_year - b.birth_year) if not year_missing else 0
    identity = identity_evidence(a, b)
    return [float(level == name) for name in NAME_LEVELS] + [
        _jaro_winkler(" ".join(sorted(a.name.tokens)), " ".join(sorted(b.name.tokens))),
        len(ta & tb) / max(len(ta | tb), 1),
        len(fa & fb) / max(len(fa | fb), 1), float(not fa or not fb),
        float(not year_missing and gap <= 1), float(not year_missing and 1 < gap <= 3), float(not year_missing and gap > 3), float(year_missing),
        float(bool(a.district and b.district and a.district == b.district)), float(not a.district or not b.district),
        float(bool(a.phones & b.phones)), float(bool(a.phones and b.phones and not a.phones & b.phones)), float(not a.phones or not b.phones),
        float(bool(identity.agreeing_kinds)), float(bool(identity.conflicting_kinds)), float(not identity.shared_kinds),
    ]


def _finite_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def validate_artifact(artifact: dict) -> dict:
    """Reject malformed portable models before they can emit plausible scores."""
    if not isinstance(artifact, dict) or artifact.get("schema") != "drishti.record-linkage.v1":
        raise ValueError("Unsupported record-linkage model schema")
    model = artifact.get("model")
    if not isinstance(model, dict) or model.get("features") != FEATURES:
        raise ValueError("Model feature schema does not match this runtime")
    coefficients = model.get("coefficients")
    if not isinstance(coefficients, list) or len(coefficients) != len(FEATURES) or not all(_finite_number(w) for w in coefficients):
        raise ValueError("Model coefficients must be finite and match the feature schema")
    if not _finite_number(model.get("intercept")):
        raise ValueError("Model intercept must be finite")
    threshold = model.get("review_threshold")
    if not _finite_number(threshold) or not 0 <= threshold <= 1:
        raise ValueError("Model review threshold must be in [0, 1]")
    if not isinstance(model.get("review_enabled", True), bool):
        raise ValueError("Model review_enabled must be boolean")
    report = artifact.get("report")
    if not isinstance(report, dict) or not isinstance(report.get("version"), str) or not report["version"]:
        raise ValueError("Model version is required")
    return model


def _probability(model: dict, values: list[float]) -> float:
    if len(values) != len(FEATURES) or not all(_finite_number(v) and 0 <= v <= 1 for v in values):
        raise ValueError("Feature vector must contain one finite [0, 1] value per feature")
    try:
        score = math.fsum([model["intercept"], *(x * w for x, w in zip(values, model["coefficients"]))])
    except OverflowError as exc:
        raise ValueError("Model linear score overflow") from exc
    if not math.isfinite(score):
        raise ValueError("Model linear score must be finite")
    if score >= 0:
        return 1 / (1 + math.exp(-score))
    exp_score = math.exp(score)
    return exp_score / (1 + exp_score)


def probability(artifact: dict, values: list[float]) -> float:
    return _probability(validate_artifact(artifact), values)


def review_eligibility(a: PersonRecord, b: PersonRecord) -> str:
    """Shared decision guard used by runtime inference and offline evaluation."""
    identity = identity_evidence(a, b)
    if identity.conflicting_kinds:
        return "conflict"
    comparable = bool((a.name.tokens and b.name.tokens) or (a.father_given_keys and b.father_given_keys)
                      or (a.phones and b.phones) or identity.shared_kinds)
    return "review" if comparable else "abstain"


def predict(artifact: dict, a: PersonRecord, b: PersonRecord) -> dict:
    model = validate_artifact(artifact)
    values = features(a, b)
    p = _probability(model, values)
    threshold = model["review_threshold"]
    eligibility = review_eligibility(a, b)
    conflict = eligibility == "conflict"
    enabled = model.get("review_enabled", True)
    # A high intercept alone is not evidence. Missing names, fathers, identifiers and
    # phones cannot support a comparison based only on district or birth year.
    comparable = eligibility == "review"
    decision = "conflict" if conflict else "review" if enabled and comparable and p >= threshold else "abstain"
    recommendation = ("Resolve contradictory identifiers before any match decision" if conflict else
                      "Model abstains: validation did not meet the review precision target" if not enabled else
                      "Model abstains: insufficient comparable identity evidence" if not comparable else
                      "Candidate for human review" if decision == "review" else "Insufficient support for a match")
    contributions = [{"feature": name, "value": value, "log_odds": round(value * weight, 5)}
                     for name, value, weight in zip(FEATURES, values, model["coefficients"]) if value]
    return {"version": artifact["report"]["version"], "match_score": round(p, 6), "threshold": threshold,
            "recommendation": recommendation, "decision": decision, "review_enabled": enabled,
            "identity_conflict": conflict, "contributions": sorted(contributions, key=lambda x: -abs(x["log_odds"])),
            "limitation": "Trained on synthetic person records. This score is not a validated real-world identity probability. No automatic merge occurs."}

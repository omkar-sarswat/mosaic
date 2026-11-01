"""Exact, blocking-aware evaluation of fully labelled record-linkage fixtures.

All candidate negatives are retained. True pairs missed by blocking are false
negatives, even when a separate pair classifier could have recognised them.
These are fixture measurements, not confidence intervals for a population.
"""
from __future__ import annotations

import itertools
import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable, Sequence

from ..resolve.matcher import Matcher, PersonRecord


@dataclass(frozen=True)
class PairPopulation:
    pairs: tuple[tuple[str, str], ...]
    labels: tuple[int, ...]
    candidates: tuple[bool, ...]
    records: int


def pair_population(records: Sequence[PersonRecord], candidates: Iterable[tuple[str, str]] | None = None) -> PairPopulation:
    """Build all candidate pairs plus every true pair, in deterministic order."""
    by_id = {r.id: r for r in records}
    if len(by_id) != len(records):
        raise ValueError("Evaluation requires unique record IDs")
    if any(not r.truth_id for r in records):
        raise ValueError("Evaluation requires a truth label for every record")
    groups: dict[str, list[str]] = defaultdict(list)
    for record in records:
        groups[record.truth_id].append(record.id)
    positives = {tuple(sorted(pair)) for group in groups.values() for pair in itertools.combinations(group, 2)}
    blocked: set[tuple[str, str]] = set()
    for a, b in Matcher(list(records)).blocks() if candidates is None else candidates:
        if a == b or a not in by_id or b not in by_id:
            raise ValueError("Candidate pairs must reference two distinct evaluation records")
        blocked.add(tuple(sorted((a, b))))
    pairs = tuple(sorted(positives | blocked))
    return PairPopulation(pairs, tuple(int(pair in positives) for pair in pairs),
                          tuple(pair in blocked for pair in pairs), len(records))


def _validate_scores(population: PairPopulation, scores: Sequence[float | None]) -> None:
    if len(scores) != len(population.pairs):
        raise ValueError("Scores must align with the evaluation pairs")
    for candidate, score in zip(population.candidates, scores):
        if candidate and (score is None or not math.isfinite(score) or not 0 <= score <= 1):
            raise ValueError("Every candidate needs a finite score between zero and one")
        if not candidate and score is not None:
            raise ValueError("Pairs missed by blocking must not receive a model score")


def _eligibility(population: PairPopulation, eligible: Sequence[bool] | None) -> Sequence[bool]:
    if eligible is None:
        return population.candidates
    if len(eligible) != len(population.pairs) or any(not isinstance(value, bool) for value in eligible):
        raise ValueError("Eligibility must contain one boolean per evaluation pair")
    return eligible


def select_review_threshold(population: PairPopulation, scores: Sequence[float | None], *, target_precision: float = .98,
                            eligible: Sequence[bool] | None = None) -> dict:
    """Maximise validation recall subject to empirical candidate precision.

    Equal scores are evaluated together, as runtime uses an inclusive threshold.
    Infeasible targets disable review recommendations instead of using a fallback
    that might still recommend a score rounded to one.
    """
    _validate_scores(population, scores)
    eligible = _eligibility(population, eligible)
    if not 0 < target_precision <= 1:
        raise ValueError("Target precision must be in (0, 1]")
    grouped: dict[float, list[int]] = defaultdict(list)
    for label, candidate, score, allowed in zip(population.labels, population.candidates, scores, eligible):
        if candidate and allowed:
            grouped[score].append(label)
    tp = fp = 0
    best = None
    for threshold in sorted(grouped, reverse=True):
        labels = grouped[threshold]
        tp += sum(labels)
        fp += len(labels) - sum(labels)
        precision = tp / (tp + fp)
        if tp and precision >= target_precision and (best is None or tp > best["true_positive"]):
            best = {"review_enabled": True, "threshold": threshold, "status": "target_met",
                    "precision": precision, "true_positive": tp, "false_positive": fp, "review_pairs": tp + fp}
    if best is None:
        best = {"review_enabled": False, "threshold": 1.0, "status": "target_infeasible",
                "precision": None, "true_positive": 0, "false_positive": 0, "review_pairs": 0}
    return best | {"target_precision": target_precision, "true_pairs": sum(population.labels),
                   "scope": "Empirical precision on all original validation candidates; not a population guarantee"}


def pipeline_metrics(population: PairPopulation, scores: Sequence[float | None], threshold: float, *, review_enabled: bool = True,
                     eligible: Sequence[bool] | None = None) -> dict:
    """Measure candidate generation and review recommendations end to end."""
    _validate_scores(population, scores)
    eligible = _eligibility(population, eligible)
    if not math.isfinite(threshold) or not 0 <= threshold <= 1:
        raise ValueError("Threshold must be finite and between zero and one")
    tp = fp = fn = tn = 0
    blocked_true = 0
    bins = [{"lower": i / 10, "upper": (i + 1) / 10, "pairs": 0, "score_sum": 0.0, "positive_sum": 0} for i in range(10)]
    squared_error = 0.0
    for label, candidate, score, allowed in zip(population.labels, population.candidates, scores, eligible):
        predicted = bool(candidate and allowed and review_enabled and score >= threshold)
        tp += int(predicted and label == 1)
        fp += int(predicted and label == 0)
        fn += int(not predicted and label == 1)
        tn += int(not predicted and label == 0)
        if candidate:
            blocked_true += label
            squared_error += (score - label) ** 2
            bucket = bins[min(int(score * 10), 9)]
            bucket["pairs"] += 1
            bucket["score_sum"] += score
            bucket["positive_sum"] += label
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    n_candidates = sum(population.candidates)
    calibration = [{"lower": bucket["lower"], "upper": bucket["upper"], "pairs": bucket["pairs"],
                    "mean_score": bucket["score_sum"] / bucket["pairs"],
                    "match_fraction": bucket["positive_sum"] / bucket["pairs"]}
                   for bucket in bins if bucket["pairs"]]
    return {"precision": precision, "recall": recall, "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0.0,
            "true_positive": tp, "false_positive": fp, "true_negative": tn, "false_negative": fn,
            "pairs": len(population.pairs), "candidate_pairs": n_candidates, "true_pairs": tp + fn,
            "blocking_missed_true_pairs": tp + fn - blocked_true,
            "blocking_recall": blocked_true / (tp + fn) if tp + fn else 0.0,
            "review_pairs": tp + fp, "threshold": threshold, "review_enabled": review_enabled,
            "ineligible_candidate_pairs": sum(candidate and not allowed for candidate, allowed in zip(population.candidates, eligible)),
            "population_pairs": population.records * (population.records - 1) // 2,
            "negative_sampling": False,
            "denominator": "All blocked candidates plus all true pairs; unblocked nonmatches are not enumerated",
            "candidate_scoring": {"pairs": n_candidates, "brier": squared_error / n_candidates if n_candidates else None,
                                  "calibration_bins": calibration,
                                  "scope": "All blocked candidates in this synthetic fixture only"}}

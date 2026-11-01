"""Estimate the Fellegi-Sunter parameters from data, the way Splink does, and test them on held-out worlds.

* u (P(level | different people)) by random sampling: draw random pairs, which are almost all
  non-matches, and count each feature's comparison level. Where synthetic truth is present, the rare
  true matches are excluded.
* m (P(level | same person)) two ways:
    - by expectation maximisation over the blocked pairs with u held fixed. EM needs no labels, so it is
      the method for real data;
    - directly from synthetic ground truth (pairs of records of the same person). This is used only to
      check how well EM recovers the true m.

Parameters are adopted only when they beat the hand-set ones on worlds they were not trained on. A
synthetic world teaches the model the synthetic noise process, not India's, so a real deployment
re-estimates them on its own data with the same code.
"""

from __future__ import annotations

import copy
import itertools
import json
import math
import random
import time
from bisect import bisect_right
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from . import matcher as M
from .matcher import Matcher, PersonRecord, clusters, pairwise_metrics

HAND_SET: dict[str, dict[str, tuple[float, float]]] = copy.deepcopy(M.M_U)
ALPHA = 0.5  # Jeffreys smoothing for u: a level never seen in the sample keeps a small, non-zero probability
KAPPA = 10.0  # m is a MAP estimate under a Dirichlet prior centred on the hand-set m, worth this many pairs:
              # a feature seldom observed among matches keeps its expert value instead of collapsing to uniform


def _levels(mt: Matcher, a: PersonRecord, b: PersonRecord) -> dict[str, str]:
    return mt.score(a, b).levels


def _normalise(counts: dict[str, Counter], *, toward_hand_set_m: bool = False) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for f, levels in HAND_SET.items():
        c = counts.get(f, Counter())
        if toward_hand_set_m:
            tot = sum(c.values()) + KAPPA
            out[f] = {lvl: (c.get(lvl, 0) + KAPPA * levels[lvl][0]) / tot for lvl in levels}
        else:
            tot = sum(c.values()) + ALPHA * len(levels)
            out[f] = {lvl: (c.get(lvl, 0) + ALPHA) / tot for lvl in levels}
    return out


def support(counts: dict[str, Counter]) -> dict[str, float]:
    return {f: round(sum(counts.get(f, Counter()).values()), 1) for f in HAND_SET}


def estimate_u(records: list[PersonRecord], n_pairs: int = 400_000, seed: int = 0) -> tuple[dict[str, dict[str, float]], int]:
    """Sample uniformly among eligible record pairs without a rejection loop.

    An identity group of size c has c * (N - c) eligible ordered pairs. Sample
    groups by that mass, then one member and one record outside the group.
    Every eligible ordered pair has the same probability, including when one
    identity dominates the input. Unlabelled records form singleton groups.
    """
    if not isinstance(n_pairs, int) or isinstance(n_pairs, bool) or n_pairs <= 0:
        raise ValueError("n_pairs must be a positive integer")
    groups: dict[tuple, list[PersonRecord]] = defaultdict(list)
    for index, record in enumerate(records):
        key = ("label", record.truth_id) if record.truth_id else ("unlabelled", index)
        groups[key].append(record)
    if len(groups) < 2:
        raise ValueError("At least two records with eligible non-match pairs are required")
    flat: list[PersonRecord] = []
    boundaries, masses = [], []
    total_mass = 0
    for group in groups.values():
        boundaries.append((len(flat), len(group)))
        flat.extend(group)
        total_mass += len(group) * (len(records) - len(group))
        masses.append(total_mass)
    rng = random.Random(seed)
    mt = Matcher(records)
    counts: dict[str, Counter] = defaultdict(Counter)
    for _ in range(n_pairs):
        group_index = bisect_right(masses, rng.randrange(total_mass))
        start, size = boundaries[group_index]
        a = flat[start + rng.randrange(size)]
        outside = rng.randrange(len(flat) - size)
        b = flat[outside if outside < start else outside + size]
        for f, lvl in _levels(mt, a, b).items():
            counts[f][lvl] += 1
    return _normalise(counts), n_pairs


def m_from_truth(records: list[PersonRecord], cap: int = 40) -> tuple[dict[str, dict[str, float]], int]:
    mt = Matcher(records)
    groups: dict[str, list[PersonRecord]] = defaultdict(list)
    for r in records:
        if r.truth_id:
            groups[r.truth_id].append(r)
    counts: dict[str, Counter] = defaultdict(Counter)
    n = 0
    for g in groups.values():
        for a, b in itertools.islice(itertools.combinations(g, 2), cap):
            for f, lvl in _levels(mt, a, b).items():
                counts[f][lvl] += 1
            n += 1
    return _normalise(counts, toward_hand_set_m=True), n


def _em(patterns: Counter, u: dict[str, dict[str, float]], iterations: int, fixed: tuple[str, ...] = ()) -> tuple[dict[str, dict[str, float]], float]:
    """EM for m with u fixed, over distinct comparison vectors weighted by their counts. Pairs with the same
    vector contribute identically, so this equals per-pair EM (checked to 1e-13) at a fraction of the cost."""
    n_pairs = sum(patterns.values())
    m = {f: {lvl: HAND_SET[f][lvl][0] for lvl in lv} for f, lv in HAND_SET.items()}
    lam = 0.01
    for _ in range(iterations):
        num: dict[str, Counter] = defaultdict(Counter)
        tot_p = 0.0
        for lv, count in patterns.items():
            w = math.log(lam / (1 - lam)) + sum(math.log(m[f][l] / u[f][l]) for f, l in lv)
            p = 1 / (1 + math.exp(-max(min(w, 50), -50)))
            tot_p += p * count
            for f, l in lv:
                num[f][l] += p * count
        lam = min(max(tot_p / max(n_pairs, 1), 1e-6), 0.95)
        est = _normalise(num, toward_hand_set_m=True)
        m = {f: ({lvl: HAND_SET[f][lvl][0] for lvl in HAND_SET[f]} if f in fixed else est[f]) for f in HAND_SET}
    return m, lam


# Exact identifiers stay at their expert m: they are near-deterministic by construction, and too few true
# pairs carry them on both records for EM to estimate them (it drifted to 0.88 TV from truth on identity,
# which would have weakened the strongest evidence against a link). They still inform each session.
FIXED_M = ("phone", "identity")


def _same_name_pairs(records: list[PersonRecord]):
    """Session 1: pairs with the same full name signature (all name keys equal). This conditions on the
    name only, so it says nothing about birth year or district, the features session 1 estimates; and
    matches are common enough here for EM to find them (5% of pairs on a 33,000-person world, against
    under 0.01% in sampled surname blocks, where EM collapsed to 'no matches')."""
    by_sig: dict[str, list[PersonRecord]] = defaultdict(list)
    for r in records:
        if r.name_signature:
            by_sig[r.name_signature].append(r)
    for group in by_sig.values():
        if 2 <= len(group) <= 400:
            yield from itertools.combinations(group, 2)


def _same_year_district_pairs(records: list[PersonRecord]):
    """Session 2: pairs born the same year in the same district (independent of names)."""
    groups: dict[tuple, list[PersonRecord]] = defaultdict(list)
    for r in records:
        if r.birth_year and r.district:
            groups[(r.birth_year, r.district)].append(r)
    for group in groups.values():
        if 2 <= len(group) <= 400:
            yield from itertools.combinations(group, 2)


# A session whose match share collapses to nothing or runs to the cap has not found the two classes;
# its features then keep their expert values instead of taking a degenerate estimate.
SHARE_BOUNDS = (1e-4, 0.9)


def em_m(records: list[PersonRecord], u: dict[str, dict[str, float]], iterations: int = 20, seed: int = 0) -> tuple[dict[str, dict[str, float]], dict[str, float], int]:
    """m by EM in two sessions, each conditioned on its own blocking rule (Splink's procedure).

    A feature used to choose the candidate pairs, or correlated with one that was, cannot be estimated
    from them: name-blocked pairs agree on names (and so on gender, and within families on fathers' names)
    far more often than random pairs, so u from random pairs would make such pairs look like matches and
    drive EM's match share to its cap. Session 1 takes pairs with the same full name and estimates age and
    district; session 2 takes pairs born the same year in the same district and estimates name, father and
    gender. Each session leaves the other features out of its likelihood; exact identifiers stay fixed.
    A session whose match share leaves SHARE_BOUNDS is reported and its features keep the hand-set m."""
    mt = Matcher(records)
    sessions = {"same_name": (_same_name_pairs(records), ("age", "district", "phone", "identity"), ("age", "district")),
                "same_year_district": (_same_year_district_pairs(records), ("name", "father", "gender", "phone", "identity"), ("name", "father", "gender"))}
    m: dict[str, dict[str, float]] = {}
    lam: dict[str, float] = {}
    n_pairs = 0
    for name, (pairs, in_likelihood, estimates) in sessions.items():
        counts: Counter = Counter()
        for a, b in pairs:
            counts[tuple(sorted((f, l) for f, l in _levels(mt, a, b).items() if f in in_likelihood))] += 1
        n_pairs += sum(counts.values())
        est, lam[name] = _em(counts, u, iterations, fixed=FIXED_M)
        if SHARE_BOUNDS[0] <= lam[name] <= SHARE_BOUNDS[1]:
            for f in estimates:
                m[f] = est[f]
    return {f: m.get(f, {lvl: HAND_SET[f][lvl][0] for lvl in HAND_SET[f]}) for f in HAND_SET}, lam, n_pairs


def combine(m: dict[str, dict[str, float]], u: dict[str, dict[str, float]]) -> dict[str, dict[str, tuple[float, float]]]:
    return {f: {lvl: (round(m[f][lvl], 6), max(u[f][lvl], 1e-9)) for lvl in lv} for f, lv in HAND_SET.items()}


def evaluate(records: list[PersonRecord], params: dict[str, dict[str, tuple[float, float]]], auto: float = 0.95, review: float = 0.70) -> dict[str, Any]:
    """Model-only cluster metrics; does not simulate service reconciliation or humans."""
    mt = Matcher(records, params=params)
    scores, _ = mt.score_with_prior(min_probability=review)
    ids = [r.id for r in records]
    auto_scores = [s for s in scores if s.probability >= auto and s.auto_eligible]
    auto_only = pairwise_metrics(records, clusters(ids, [(s.a, s.b) for s in auto_scores]))
    with_review = pairwise_metrics(records, clusters(ids, [(s.a, s.b) for s in scores]))
    return {"auto": auto_only, "with_review": with_review, "review_queue": len(scores) - len(auto_scores),
            "evaluation_scope": "model-only clusters; all-review metric assumes every candidate confirmed"}


REVIEW_GRID = (0.9, 0.7, 0.5, 0.3, 0.2, 0.1, 0.05)


def select_review_threshold(records: list[PersonRecord], params: dict[str, dict[str, tuple[float, float]]], floor: float = 0.02) -> dict[str, Any]:
    """The review band's lower edge, chosen on the training world only. Sharper parameters push borderline
    true pairs below a threshold tuned for the hand-set values, where they would be dropped unseen; take the
    highest threshold that still sends essentially every reachable true pair (within 0.1 point of recall at
    `floor`) to a person."""
    mt = Matcher(records, params=params)
    scores, _ = mt.score_with_prior(min_probability=floor)
    ids = [r.id for r in records]
    recall = {t: pairwise_metrics(records, clusters(ids, [(s.a, s.b) for s in scores if s.probability >= t]))["recall"] for t in (*REVIEW_GRID, floor)}
    best = recall[floor]
    chosen = next((t for t in REVIEW_GRID if recall[t] >= best - 0.001), floor)
    return {"review_threshold": chosen, "recall_by_threshold": recall}


def train(records: list[PersonRecord], *, u_pairs: int = 400_000, seed: int = 0, log=print) -> dict[str, Any]:
    t0 = time.time()
    u, n_u = estimate_u(records, u_pairs, seed)
    log(f"u from {n_u:,} random pairs ({time.time() - t0:.0f}s)")
    m_em, lam, n_blocked = em_m(records, u)
    log(f"m by EM over {n_blocked:,} blocked pairs, match share by session {', '.join(f'{k} {v:.4f}' for k, v in lam.items())} ({time.time() - t0:.0f}s)")
    out: dict[str, Any] = {"records": len(records), "u_pairs": n_u, "blocked_pairs": n_blocked, "em_match_share": lam,
                           "params": combine(m_em, u), "seconds": round(time.time() - t0, 1)}
    if any(r.truth_id for r in records):
        m_true, n_true = m_from_truth(records)
        out["m_truth_pairs"] = n_true
        # how far EM's m is from the m measured on the truth (total variation distance per feature)
        out["em_vs_truth_tv"] = {f: round(0.5 * sum(abs(m_em[f][l] - m_true[f][l]) for l in HAND_SET[f]), 4) for f in HAND_SET}
        out["params_truth_m"] = combine(m_true, u)
    out["review_thresholds"] = {}
    for name, key in (("trained_em", "params"), ("trained_labelled", "params_truth_m")):
        if key in out:
            sel = select_review_threshold(records, out[key])
            out["review_thresholds"][name] = sel
            log(f"review threshold for {name}: {sel['review_threshold']} (chosen on the training world)")
    return out


def save(result: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=1), encoding="utf-8")


def review_threshold(path: Path) -> float | None:
    """The review threshold stored with adopted parameters (chosen on their training world)."""
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8")).get("review_threshold")


def load(path: Path) -> dict[str, dict[str, tuple[float, float]]] | None:
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    saved = {f: {lvl: tuple(v) for lvl, v in lv.items()} for f, lv in data["params"].items()}
    # forward-compatible: a comparison level added after these parameters were trained keeps its expert value
    return {f: {lvl: saved.get(f, {}).get(lvl, HAND_SET[f][lvl]) for lvl in HAND_SET[f]} for f in HAND_SET}  # type: ignore[misc]

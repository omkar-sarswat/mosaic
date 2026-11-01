"""Train CPU record linkage, with identity-disjoint splits and frozen test data.

Usage: python scripts/train_linkage.py --db var/drishti.db --output var/models/record_linkage.json
Requires the optional [ml] dependencies. Writes JSON, never executable pickle data.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import random
import sys
from collections import defaultdict
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from drishti.ml.evaluation import pair_population, pipeline_metrics, select_review_threshold
from drishti.ml.linkage import FEATURES, features, review_eligibility
from drishti.resolve.matcher import Matcher
from drishti.resolve.names import normalize_name
from drishti.resolve.service import _records
from drishti.store import Store, utcnow


def augment(records, seed):
    """Stress fixture: missing fields, initials and transcription errors.

    Augment within an already assigned identity split, never across splits.
    This is a synthetic robustness test, not additional independent evidence.
    """
    rng = random.Random(seed)
    groups = defaultdict(list)
    for record in records:
        groups[record.truth_id].append(record)
    out = list(records)
    for identity in sorted(groups):
        base = groups[identity][0]
        tokens = list(base.name.tokens)
        for variant in range(3):
            changed = list(tokens)
            if changed and variant == 0 and len(changed[0]) > 2:
                pos = rng.randrange(1, len(changed[0]) - 1)
                word = changed[0]
                changed[0] = word[:pos] + word[pos + 1:]  # a dropped character
            elif len(changed) > 1 and variant == 1:
                changed = [t[0] for t in changed[:-1]] + [changed[-1]]
            else:
                rng.shuffle(changed)
            out.append(replace(base, id=base.id + f":stress-{variant}", name=normalize_name(" ".join(changed)),
                               father=base.father if rng.random() > .35 else None,
                               birth_year=(base.birth_year + rng.choice((-1, 0, 0, 1))) if base.birth_year and rng.random() > .3 else None,
                               district=base.district if rng.random() > .25 else None,
                               ids=base.ids if rng.random() > .85 else frozenset(), phones=frozenset()))
    return out


def make_pairs(records, seed):
    rng = random.Random(seed)
    by_identity = defaultdict(list)
    by_id = {r.id: r for r in records}
    for r in records:
        by_identity[r.truth_id].append(r.id)
    positives = {tuple(sorted(pair)) for group in by_identity.values() for pair in itertools.combinations(group, 2)}
    blocked = set(Matcher(records).blocks())
    negatives = sorted(pair for pair in blocked if by_id[pair[0]].truth_id != by_id[pair[1]].truth_id)
    rng.shuffle(negatives)
    negatives = negatives[:max(1500, len(positives) * 12)]
    random_negatives = set(negatives)
    keys = sorted(by_id)
    for _ in range(max(1500, len(positives) * 6)):
        a, b = rng.sample(keys, 2)
        if by_id[a].truth_id != by_id[b].truth_id:
            random_negatives.add(tuple(sorted((a, b))))
    pairs = sorted(positives | random_negatives)
    return pairs, positives, blocked


def evaluation_data(records):
    """Complete candidate population; only training may sample negatives."""
    import numpy as np

    by_id = {r.id: r for r in records}
    population = pair_population(records)
    indices = [i for i, candidate in enumerate(population.candidates) if candidate]
    candidate_x = np.asarray([features(by_id[population.pairs[i][0]], by_id[population.pairs[i][1]])
                              for i in indices], dtype=np.float64).reshape((-1, len(FEATURES)))
    eligible = [review_eligibility(by_id[a], by_id[b]) == "review" for a, b in population.pairs]
    return population, candidate_x, indices, eligible, by_id


def score_population(model, data):
    population, candidate_x, indices, *_ = data
    scores = [None] * len(population.pairs)
    if indices:
        for index, score in zip(indices, model.predict_proba(candidate_x)[:, 1]):
            scores[index] = float(score)
    return scores


def candidate_rank_metrics(population, scores):
    from sklearn.metrics import average_precision_score, roc_auc_score

    labels = [label for label, candidate in zip(population.labels, population.candidates) if candidate]
    scored = [score for score in scores if score is not None]
    return {"average_precision": float(average_precision_score(labels, scored)) if any(labels) else None,
            "roc_auc": float(roc_auc_score(labels, scored)) if len(set(labels)) == 2 else None}


def train(db: Path, output: Path, seed: int = 20261014, max_identities: int | None = None):
    import numpy as np
    import sklearn
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import average_precision_score
    store = Store(db)
    try:
        records = sorted((r for r in _records(store) if r.truth_id), key=lambda r: r.id)
    finally:
        store.close()
    if len(records) < 100:
        raise ValueError("At least 100 truth-labelled synthetic records are required")
    groups = sorted({r.truth_id for r in records})
    random.Random(seed).shuffle(groups)
    if max_identities and len(groups) > max_identities:
        # a reproducible sample of whole identities keeps memory bounded on large worlds; no identity is split
        groups = groups[:max_identities]
        keep = set(groups)
        records = [r for r in records if r.truth_id in keep]
    cut1, cut2 = int(len(groups) * .6), int(len(groups) * .8)
    group_sets = [set(groups[:cut1]), set(groups[cut1:cut2]), set(groups[cut2:])]
    original_splits = [[r for r in records if r.truth_id in g] for g in group_sets]
    if any(not split for split in original_splits):
        raise ValueError("Training, validation and test splits must all contain identities")
    overlap = sum(len(group_sets[i] & group_sets[j]) for i in range(3) for j in range(i + 1, 3))
    if overlap:
        raise ValueError("Identity leakage between training, validation and test sets")
    training_records = augment(original_splits[0], seed + 10)
    training_by_id = {r.id: r for r in training_records}
    training_pairs, positives, blocked = make_pairs(training_records, seed)
    train_x = np.asarray([features(training_by_id[a], training_by_id[b]) for a, b in training_pairs], dtype=np.float64)
    train_y = np.asarray([int(pair in positives) for pair in training_pairs])
    if len(set(train_y)) != 2:
        raise ValueError("Training must contain positive and negative record pairs")
    validation_data = evaluation_data(original_splits[1])
    valid_population, _, valid_indices, valid_eligible, _ = validation_data
    valid_y = [valid_population.labels[i] for i in valid_indices]
    choices = []
    for regularization in (0.1, 1.0, 10.0):
        model = LogisticRegression(C=regularization, max_iter=2000, random_state=seed, solver="lbfgs")
        model.fit(train_x, train_y)
        scores = score_population(model, validation_data)
        # Only original validation records choose the model. Test data is untouched.
        ranking = float(average_precision_score(valid_y, [scores[i] for i in valid_indices])) if any(valid_y) else 0.0
        choices.append((ranking, regularization, model))
    _, regularization, model = max(choices, key=lambda x: x[0])
    validation_scores = score_population(model, validation_data)
    selection = select_review_threshold(valid_population, validation_scores, eligible=valid_eligible)
    threshold, review_enabled = selection["threshold"], selection["review_enabled"]

    # Open the original test partition after model and threshold are frozen.
    test_data = evaluation_data(original_splits[2])
    test_population, _, _, test_eligible, test_records = test_data
    scores = score_population(model, test_data)
    test_metrics = pipeline_metrics(test_population, scores, threshold, review_enabled=review_enabled, eligible=test_eligible)
    validation_metrics = pipeline_metrics(valid_population, validation_scores, threshold,
                                          review_enabled=review_enabled, eligible=valid_eligible)
    test_metrics["candidate_scoring"].update(candidate_rank_metrics(test_population, scores))
    validation_metrics["candidate_scoring"].update(candidate_rank_metrics(valid_population, validation_scores))

    stress_records = augment(original_splits[2], seed + 12)
    stress_data = evaluation_data(stress_records)
    stress_scores = score_population(model, stress_data)
    stress_metrics = pipeline_metrics(stress_data[0], stress_scores, threshold,
                                      review_enabled=review_enabled, eligible=stress_data[3])
    baseline = Matcher(original_splits[0])
    baseline.estimate_prior()
    baseline_scores = [baseline.score(test_records[a], test_records[b]).probability if candidate else None
                       for (a, b), candidate in zip(test_population.pairs, test_population.candidates)]
    exact_scores = [float(bool(test_records[a].name.tokens) and sorted(test_records[a].name.tokens) == sorted(test_records[b].name.tokens))
                   if candidate else None for (a, b), candidate in zip(test_population.pairs, test_population.candidates)]
    errors = []
    for pair, label, score, candidate, allowed in zip(test_population.pairs, test_population.labels, scores,
                                                    test_population.candidates, test_eligible):
        predicted = bool(candidate and allowed and review_enabled and score >= threshold)
        if predicted != bool(label):
            errors.append({"pair_hash": hashlib.sha256("|".join(pair).encode()).hexdigest()[:16], "label": label, "score": score,
                           "stage": "blocking" if not candidate else "eligibility" if not allowed else "threshold",
                           "name_level": FEATURES[int(np.argmax(features(test_records[pair[0]], test_records[pair[1]])[:7]))]})
    audits = [{"records": len(original_splits[0]), "augmented_records": len(training_records), "identities": len(group_sets[0]),
               "pairs": len(training_pairs), "positive_pairs": len(positives), "negative_sampling": True,
               "blocking_recall": len(positives & blocked) / max(len(positives), 1)}]
    for population, metrics in ((valid_population, validation_metrics), (test_population, test_metrics)):
        audits.append({"records": population.records, "identities": len(group_sets[len(audits)]),
                       "pairs": len(population.pairs), "positive_pairs": sum(population.labels), "negative_sampling": False,
                       "blocking_recall": metrics["blocking_recall"]})
    for audit, identities in zip(audits, group_sets):
        audit["identity_digest"] = hashlib.sha256("\n".join(sorted(identities)).encode()).hexdigest()
    manifest = hashlib.sha256(train_x.tobytes() + train_y.tobytes() + json.dumps(training_pairs).encode())
    for population, candidate_x, _, eligible, _ in (validation_data, test_data, stress_data):
        manifest.update(candidate_x.tobytes())
        manifest.update(json.dumps([population.pairs, population.labels, population.candidates, eligible]).encode())
    input_digest = manifest.hexdigest()
    fingerprint = hashlib.sha256(json.dumps([FEATURES, model.coef_[0].tolist(), float(model.intercept_[0]), threshold,
                                             review_enabled], sort_keys=True).encode()).hexdigest()
    report = {"name": "Person record linkage", "family": "L2-regularized logistic regression", "version": "lr-" + fingerprint[:12],
              "status": "experimental · synthetic validation only", "trained_at": utcnow(), "seed": seed, "runtime": "local CPU",
              "source_db": db.name, "identity_cap": max_identities,
              "training_records": len(training_records), "original_records": len(records), "features": len(FEATURES), "selected_C": regularization,
              "augmentation": "Training uses three variants per training identity. Original validation/test records are unchanged; augmented test results are reported separately.",
              "split_policy": "60/20/20 by underlying identity; no identity occurs in more than one split", "splits": dict(zip(("train", "validation", "test"), audits)),
              "identity_overlap": overlap, "validation": validation_metrics, "test": test_metrics,
              "evaluation_policy": "Original held-out records; every blocked candidate and every true pair. Blocking misses and runtime abstentions count as false negatives.",
              "threshold_selection": selection, "test_original_pipeline": test_metrics, "test_stress_pipeline": stress_metrics,
              "baselines": {"hand_set_fellegi_sunter": pipeline_metrics(test_population, baseline_scores, .95, eligible=test_eligible),
                            "exact_name": pipeline_metrics(test_population, exact_scores, .5, eligible=test_eligible)},
              "baseline_policy": "Same original test candidates and runtime eligibility; Fellegi-Sunter prior and name frequencies fitted on original training records.",
              "uncertainty": {"method": "none", "reason": "Record pairs share identities; augmented records share source observations. Pair-independent bootstrap intervals are not reported."},
              "error_examples": errors[:30], "model_sha256": fingerprint, "input_manifest_sha256": input_digest,
              "library": {"scikit_learn": sklearn.__version__, "numpy": np.__version__},
              "limitations": ["Synthetic, single-generator data is not an independent benchmark or proof of real-world accuracy.",
                              "Stress variants share a generator and source record with their identity; their count is not an independent sample size.",
                              "Negative sampling is restricted to training. It changes the fitted class prior; scores are not real-world calibrated probabilities.",
                              "The validation precision target is empirical, not a guaranteed precision bound on new data.",
                              "Pipeline metrics include missed blocking pairs. Candidate calibration and rank metrics cover scored candidates only.",
                              "No uncertainty interval is claimed because pairs and synthetic variants are dependent; independent datasets and entity-level study design are required.",
                              "Name/source/region distribution shifts and multilingual fairness need representative external labels.",
                              "The model cannot identify guilt, intent, or suspicious behaviour; it proposes record comparisons for review."]}
    artifact = {"schema": "drishti.record-linkage.v1", "model": {"features": FEATURES, "coefficients": model.coef_[0].tolist(),
                 "intercept": float(model.intercept_[0]), "review_threshold": threshold, "review_enabled": review_enabled}, "report": report}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    print(json.dumps({"artifact": str(output), "version": report["version"], "test": test_metrics, "baselines": report["baselines"], "blocking_recall": audits[2]["blocking_recall"]}, indent=2))
    return artifact


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", type=Path, default=Path("var/drishti.db"))
    ap.add_argument("--output", type=Path, default=Path("var/models/record_linkage.json"))
    ap.add_argument("--seed", type=int, default=20261014)
    ap.add_argument("--max-identities", type=int, default=None, help="sample this many whole identities (large worlds)")
    args = ap.parse_args()
    train(args.db, args.output, args.seed, args.max_identities)

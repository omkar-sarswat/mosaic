"""Compare record-linkage model artifacts on the same held-out worlds.

    python scripts/compare_linkage.py var/models/record_linkage.json var/models/record_linkage-scale.json --worlds var/eval/world_*.db

Every world is scored end to end with ml.evaluation.pipeline_metrics: every blocked candidate plus every
true pair, so pairs missed by blocking and runtime abstentions count as false negatives. Each artifact
uses its own frozen review threshold. Worlds that share identities with a model's training data must
not be used; the scale world is generated with a seed distinct from the evaluation worlds.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from drishti.ml.evaluation import pair_population, pipeline_metrics  # noqa: E402
from drishti.ml.linkage import features, probability, review_eligibility, validate_artifact  # noqa: E402
from drishti.resolve.service import _records  # noqa: E402
from drishti.store import Store  # noqa: E402


def score_world(artifacts: dict[str, dict], db: Path) -> dict[str, dict]:
    store = Store(db)
    try:
        records = sorted((r for r in _records(store) if r.truth_id), key=lambda r: r.id)
    finally:
        store.close()
    by_id = {r.id: r for r in records}
    population = pair_population(records)
    eligible = [review_eligibility(by_id[a], by_id[b]) == "review" for a, b in population.pairs]
    vectors = [features(by_id[a], by_id[b]) if c else None for (a, b), c in zip(population.pairs, population.candidates)]
    out = {}
    for name, art in artifacts.items():
        model = validate_artifact(art)
        scores = [probability(art, v) if v is not None else None for v in vectors]
        m = pipeline_metrics(population, scores, model["review_threshold"], review_enabled=model.get("review_enabled", True), eligible=eligible)
        out[name] = {k: m[k] for k in ("precision", "recall", "f1", "true_positive", "false_positive", "false_negative", "blocking_recall", "review_pairs")}
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("models", nargs="+", type=Path)
    ap.add_argument("--worlds", nargs="+", type=Path, required=True)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    artifacts = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in args.models}
    rows = []
    for db in args.worlds:
        res = score_world(artifacts, db)
        rows.append({"world": db.name, **res})
        print(db.name, " | ".join(f"{k}: P {v['precision']:.4f} R {v['recall']:.4f} F1 {v['f1']:.4f} FP {v['false_positive']}" for k, v in res.items()), flush=True)
    summary = {name: {"false_positive": sum(r[name]["false_positive"] for r in rows), "true_positive": sum(r[name]["true_positive"] for r in rows),
                      "false_negative": sum(r[name]["false_negative"] for r in rows)} for name in artifacts}
    for v in summary.values():
        tp, fp, fn = v["true_positive"], v["false_positive"], v["false_negative"]
        v |= {"precision": round(tp / (tp + fp), 4) if tp + fp else 0.0, "recall": round(tp / (tp + fn), 4) if tp + fn else 0.0,
              "f1": round(2 * tp / (2 * tp + fp + fn), 4) if tp else 0.0}
    print(json.dumps(summary, indent=1))
    if args.out:
        args.out.write_text(json.dumps({"worlds": rows, "pooled": summary}, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()

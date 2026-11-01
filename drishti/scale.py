"""Scale run: build a large synthetic world, run every stage, and measure what matters at that size.

The report answers four questions:
* Volume: how many records the world holds (objects, links, events, plus index rows).
* Time: how long each stage takes, so regressions to quadratic behaviour show up as numbers.
* Quality: entity-resolution precision and recall against synthetic truth; pattern recall on the
  planted networks, benign look-alikes raised, and false leads per 100,000 background people.
* Latency: search, identifier lookup, two-hop neighbourhood and data-studio preview on the big store.
"""

from __future__ import annotations

import json
import random
import statistics
import time
from pathlib import Path
from typing import Any

from .store import Store

EVENT_TABLES = ("txns", "cdrs", "tollhits", "travel", "procurements", "bids")
INDEX_TABLES = ("provenance", "identifiers")


def volume(store: Store) -> dict[str, Any]:
    n = {t: store.query(f"SELECT COUNT(*) n FROM {t}")[0]["n"] for t in ("objects", "links", *EVENT_TABLES, *INDEX_TABLES)}
    by_type = {r["type"]: r["n"] for r in store.query("SELECT type, COUNT(*) n FROM objects GROUP BY type ORDER BY n DESC")}
    records = n["objects"] + n["links"] + sum(n[t] for t in EVENT_TABLES)
    return {"tables": n, "objects_by_type": by_type, "records": records, "index_rows": sum(n[t] for t in INDEX_TABLES)}


def _lat(fn, items) -> dict[str, float]:
    out = []
    for x in items:
        t = time.perf_counter()
        fn(x)
        out.append((time.perf_counter() - t) * 1000)
    out.sort()
    return {"n": len(out), "median_ms": round(statistics.median(out), 2), "p95_ms": round(out[int(len(out) * 0.95) - 1], 2), "max_ms": round(out[-1], 2)} if out else {}


def latency(store: Store, seed: int = 3) -> dict[str, Any]:
    rng = random.Random(seed)
    people = [r["id"] for r in store.query("SELECT id FROM objects WHERE type='Person'")]
    names = [json.loads(r["props"])["name"] for r in store.query("SELECT props FROM objects WHERE type='Person' ORDER BY random() LIMIT 200")]
    numbers = [json.loads(r["props"])["number"] for r in store.query("SELECT props FROM objects WHERE type='Phone' ORDER BY random() LIMIT 200")]
    sample = rng.sample(people, min(100, len(people)))

    def two_hop(pid: str) -> int:
        first = {x for link in store.links_for([pid]) for x in (link["src"], link["dst"])}
        return len(store.links_for(list(first)[:200]))

    out = {"name_search": _lat(lambda n: store.search(n, types=["Person"], limit=20), names),
           "identifier_lookup": _lat(store.find_identifier, numbers),
           "two_hop_neighbourhood": _lat(two_hop, sample)}
    from .intake import pipeline as intake

    t = time.perf_counter()
    intake.run(store, "kyc")
    out["intake_preview_kyc_ms"] = round((time.perf_counter() - t) * 1000, 1)
    return out


def build_scale(path: Path, people: int, *, seed: int = 101, log=print) -> dict[str, Any]:
    from .analytics.behaviour import run_behaviour
    from .analytics.inference import run_inference
    from .analytics.money import Ledger
    from .analytics.typologies import run_typologies
    from .config import settings
    from .connectors.lgd import load_admin_units
    from .patterns.engine import run_patterns
    from .patterns.evaluate import evaluate
    from .resolve.service import run_resolution
    from .synth.world import World

    for p in path.parent.glob(path.name + "*"):
        p.unlink()
    store = Store(path)
    timings: dict[str, float] = {}
    report: dict[str, Any] = {"people_requested": people, "seed": seed, "db": str(path)}

    def stage(name: str, fn):
        t = time.time()
        r = fn()
        timings[name] = round(time.time() - t, 1)
        log(f"{name:12s} {timings[name]:>7.1f}s")
        return r

    stage("lgd", lambda: load_admin_units(store, settings.reference_dir))
    report["world"] = stage("world", lambda: World(store, settings.reference_dir, seed=seed, n_people=people).run())
    res = stage("resolution", lambda: run_resolution(store))
    report["resolution"] = {k: res.get(k) for k in ("records", "pairs_scored", "auto_links", "sent_to_review", "resolved_entities", "benchmark_auto_only", "benchmark_if_all_reviews_confirmed")}
    ledger = stage("ledger", lambda: Ledger(store))
    report["typologies"] = stage("typologies", lambda: run_typologies(store, ledger))
    report["inference"] = stage("inference", lambda: run_inference(store, ledger))
    report["behaviour"] = stage("behaviour", lambda: run_behaviour(store, ledger))
    report["patterns"] = stage("patterns", lambda: run_patterns(store, ledger))
    ev = stage("evaluate", lambda: evaluate(store))
    s = ev["summary"]
    background = store.query("SELECT COUNT(*) n FROM objects WHERE type='Person'")[0]["n"]
    report["pattern_eval"] = s | {"false_leads_per_100k_people": round(100_000 * s.get("background_false_leads", 0) / max(background, 1), 2)}
    report["volume"] = stage("volume", lambda: volume(store))
    report["latency"] = stage("latency", lambda: latency(store))
    report["timings_s"] = timings
    report["total_s"] = round(sum(timings.values()), 1)
    store.set_meta("scale_report", report)
    return report


def matcher_adoption_gate(rows: list[dict], candidate: str = "trained_em") -> dict:
    """Require no observed regression in any labelled holdout world.

    No additional false automatic links, no lower automatic-link precision, and no lower recall once the
    review queue is worked (a parameter set may not buy precision by dropping borderline true pairs before a
    person sees them); plus a higher mean automatic-link F1. This is an empirical regression gate, not a
    confidence bound or evidence of real-world accuracy. F1 alone cannot pay for additional false merges.
    """
    reasons = []
    if not rows:
        reasons.append("No independent labelled evaluation worlds")
    for row in rows:
        baseline, cand = row["hand_set"], row[candidate]
        label = row["world"]
        if cand["true_pairs"] <= 0 or cand["predicted_pairs"] <= 0:
            reasons.append(f"{label}: insufficient positive evaluation evidence")
        if cand["false_positive_pairs"] > baseline["false_positive_pairs"]:
            reasons.append(f"{label}: additional false links")
        # Compare counts, avoiding a rounded precision value concealing a regression.
        bp, cp = baseline["predicted_pairs"], cand["predicted_pairs"]
        if bp and cp and cand["true_positive_pairs"] * bp < baseline["true_positive_pairs"] * cp:
            reasons.append(f"{label}: lower automatic-link precision")
        if "review_recall" in cand and cand["review_recall"] < baseline["review_recall"] - 0.0005:
            reasons.append(f"{label}: lower recall after review")
    if rows and statistics.mean(r[candidate]["auto_f1"] for r in rows) <= statistics.mean(r["hand_set"]["auto_f1"] for r in rows):
        reasons.append("No mean automatic-link F1 improvement")
    return {"candidate": candidate, "passed": not reasons, "reasons": reasons,
            "policy": "No additional false pairs, lower precision or lower recall after review on any holdout, plus higher mean F1"}


CANDIDATE_NOTE = {
    "trained_em": "m by expectation maximisation (no labels), u by random sampling",
    "trained_labelled": "m measured on labelled same-person pairs (here synthetic truth; in deployment an audited sample of 1,000-2,000 pairs), u by random sampling",
}


def train_matcher(train_db: Path, eval_dbs: list[Path], out: Path, *, u_pairs: int = 400_000, adopt: bool = False, log=print) -> dict[str, Any]:
    from .config import settings
    from .resolve import train as T
    from .resolve.service import _records

    paths = [train_db.resolve(), *(db.resolve() for db in eval_dbs)]
    if len(set(paths)) != len(paths):
        raise ValueError("Training and evaluation databases must be distinct, without repeated holdouts")
    if any(not path.is_file() for path in paths):
        raise ValueError("Training and evaluation databases must already exist")

    def read_records(path):
        store = Store(path)
        try:
            return _records(store)
        finally:
            store.close()

    recs = read_records(train_db)
    seen_truth = {r.truth_id for r in recs if r.truth_id}
    held_out = []
    for db in eval_dbs:
        er = read_records(db)
        truth = {r.truth_id for r in er if r.truth_id}
        if not truth:
            raise ValueError(f"Evaluation world {db.name} has no identity labels")
        if seen_truth & truth:
            raise ValueError(f"Evaluation world {db.name} shares identities with training or another holdout")
        seen_truth.update(truth)
        held_out.append((db, er))
    log(f"training on {len(recs):,} person records from {train_db}")
    tr = T.train(recs, u_pairs=u_pairs, log=log)
    sets = {"hand_set": (T.HAND_SET, settings.review_threshold), "trained_em": (tr["params"], tr["review_thresholds"]["trained_em"]["review_threshold"])}
    if "params_truth_m" in tr:
        sets["trained_labelled"] = (tr["params_truth_m"], tr["review_thresholds"]["trained_labelled"]["review_threshold"])
    rows = []
    for db, er in held_out:
        row = {"world": db.name, "records": len(er)}
        for name, (params, review_at) in sets.items():
            e = T.evaluate(er, params, review=review_at)
            row[name] = {"auto_f1": e["auto"]["f1"], "auto_precision": e["auto"]["precision"], "auto_recall": e["auto"]["recall"],
                         "review_f1": e["with_review"]["f1"], "review_recall": e["with_review"]["recall"], "review_queue": e["review_queue"],
                         "review_threshold": review_at, "true_pairs": e["auto"]["true_pairs"], "predicted_pairs": e["auto"]["predicted_pairs"],
                         "true_positive_pairs": e["auto"]["true_positives"],
                         "false_positive_pairs": e["auto"]["predicted_pairs"] - e["auto"]["true_positives"]}
        rows.append(row)
        log(f"  {db.name:22s} " + " | ".join(f"{n}: F1 {row[n]['auto_f1']:.4f} false {row[n]['false_positive_pairs']} review recall {row[n]['review_recall']:.4f} queue {row[n]['review_queue']}" for n in sets))
    tr["evaluation"] = rows
    tr["mean_auto_f1"] = {n: round(statistics.mean(r[n]["auto_f1"] for r in rows), 4) for n in sets} if rows else {}
    tr["gates"] = {n: matcher_adoption_gate(rows, n) for n in sets if n != "hand_set"}
    tr["adoption_gate"] = tr["gates"]["trained_em"]
    tr["evaluation_scope"] = "Synthetic model-only clusters; independent identity labels, shared generator"
    passing = [n for n, g in tr["gates"].items() if g["passed"]]
    chosen = max(passing, key=lambda n: tr["mean_auto_f1"][n]) if passing else None
    tr["adopted"] = bool(adopt and chosen)
    T.save(tr, out)
    if tr["adopted"]:
        params, review_at = sets[chosen]
        T.save({"params": params, "review_threshold": review_at, "source": chosen, "method": CANDIDATE_NOTE[chosen],
                "trained_on": str(train_db), "records": len(recs), "trained_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "evaluation": rows, "gate": tr["gates"][chosen]}, settings.matcher_params)
        log(f"adopted {chosen} (review threshold {review_at}): {settings.matcher_params}")
    elif adopt:
        log("not adopted: " + " || ".join(f"{n}: " + "; ".join(g["reasons"]) for n, g in tr["gates"].items()))
    return tr

"""DRISHTI command line.

  drishti demo                 build everything from open + synthetic data and serve it
  drishti init                 load LGD admin units, OSM hospitals, SACHET snapshot
  drishti seed                 generate synthetic persons / FIRs / complaints with planted rings
  drishti ingest sachet --live pull current alerts from the national SACHET feed
  drishti resolve              run entity resolution and print the benchmark
  drishti serve                start the API + web UI
  drishti audit verify|alerts|seal
  drishti patterns run|eval|redteam|catalog   mission-track pattern engine
  drishti stats
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import settings


def _store():
    from .store import Store

    return Store(settings.db_target)


def cmd_init(args: argparse.Namespace) -> None:
    from .connectors.lgd import Gazetteer, load_admin_units
    from .connectors.osm import load_hospitals
    from .connectors.sachet import ingest_sachet

    s = _store()
    print("LGD admin units:", load_admin_units(s, settings.reference_dir))
    print("OSM hospitals:  ", load_hospitals(s, settings.reference_dir))
    gaz = Gazetteer.load(settings.reference_dir)
    sample = None if args.live else settings.samples_dir / "sachet"
    try:
        print("SACHET alerts:  ", ingest_sachet(s, gaz, sample_dir=sample))
    except OSError as exc:
        print("SACHET live feed unreachable, using snapshot:", exc)
        print("SACHET alerts:  ", ingest_sachet(s, gaz, sample_dir=settings.samples_dir / "sachet"))


def cmd_seed(args: argparse.Namespace) -> None:
    from .analytics.money import Ledger
    from .analytics.typologies import run_typologies
    from .pipeline import agency_cases
    from .resolve.service import run_resolution
    from .synth.world import World

    s = _store()
    if s.count("Person"):
        print("synthetic data already present; use `drishti demo --fresh` to rebuild")
        return
    print("synthetic world:", World(s, settings.reference_dir, seed=args.seed, n_people=args.people).run())
    print("resolution:", {k: v for k, v in run_resolution(s).items() if not k.startswith("benchmark")})
    print("typologies:", run_typologies(s, Ledger(s)))
    print("agency cases:", agency_cases(s))


def cmd_ingest(args: argparse.Namespace) -> None:
    from .connectors.lgd import Gazetteer
    from .connectors.sachet import ingest_sachet

    s = _store()
    gaz = Gazetteer.load(settings.reference_dir)
    if args.source == "sachet":
        print(ingest_sachet(s, gaz, sample_dir=None if args.live else settings.samples_dir / "sachet", limit=args.limit))


def cmd_resolve(_: argparse.Namespace) -> None:
    from .resolve.service import run_resolution

    print(json.dumps(run_resolution(_store()), indent=2))


def cmd_serve(args: argparse.Namespace) -> None:
    import uvicorn

    if not settings.web_dist.exists():
        print("note: web/dist not built; API only. Build the UI with: cd web && npm install && npm run build")
    print(f"Mosaic on http://{args.host}:{args.port}  (auth mode: {settings.auth_mode})")
    uvicorn.run("drishti.api.app:app", host=args.host, port=args.port, log_level="warning")


def cmd_demo(args: argparse.Namespace) -> None:
    from .pipeline import build_world

    if settings.db_path.exists() and args.fresh:
        for p in settings.db_path.parent.glob(settings.db_path.name + "*"):
            p.unlink()
    if not settings.db_path.exists() or args.fresh:
        r = build_world(_store(), settings.reference_dir, settings.samples_dir, live=args.live, people=args.people, redteam=not args.no_redteam,
                        portraits=not args.no_portraits, background=not args.no_background)
        print(f"built in {r['seconds']} s")
    if not args.no_serve:
        cmd_serve(args)


def cmd_audit(args: argparse.Namespace) -> None:
    from .guard import AuditLog

    a = AuditLog(_store())
    out = {"verify": a.verify, "alerts": a.alerts, "seal": a.seal_day}[args.what]()
    print(json.dumps(out, indent=2))


def cmd_stats(_: argparse.Namespace) -> None:
    s = _store()
    rows = s.query("SELECT type, COUNT(*) n FROM objects GROUP BY type ORDER BY n DESC")
    print(json.dumps({r["type"]: r["n"] for r in rows}, indent=2))
    print("links:", s.query("SELECT COUNT(*) n FROM links")[0]["n"], " audit rows:", s.query("SELECT COUNT(*) n FROM audit")[0]["n"])


def cmd_patterns(args: argparse.Namespace) -> None:
    from .patterns.engine import catalog, run_patterns
    from .patterns.evaluate import evaluate, markdown
    from .patterns.redteam import run_redteam

    s = _store()
    if args.what == "run":
        print(json.dumps(run_patterns(s, run_by="cli"), indent=2))
    elif args.what == "eval":
        print(markdown(evaluate(s)))
    elif args.what == "redteam":
        r = run_redteam(s)
        print(f"loopholes closed: {r['closed']}, known limits confirmed: {r['known_limits_confirmed']}, surprises: {r['surprises'] or 'none'}")
    else:
        for d in catalog():
            print(f"{d['id']:30s} {d['version']:5s} {d['scope']:10s} {', '.join(d['tracks'])}")
            print(f"    {d['question']}")


def cmd_scale(args: argparse.Namespace) -> None:
    from .scale import build_scale

    r = build_scale(Path(args.db), args.people, seed=args.seed)
    out = Path(args.report)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(r, indent=1, default=str), encoding="utf-8")
    v, e = r["volume"], r["pattern_eval"]
    print(f"records {v['records']:,} (+{v['index_rows']:,} index rows) in {r['total_s']} s; report: {out}")
    print(f"pattern recall {e.get('recall')}, precision {e.get('precision')}, benign raised {e.get('benign_fired')}, "
          f"false leads per 100k people {e.get('false_leads_per_100k_people')}")


def cmd_train(args: argparse.Namespace) -> None:
    from .scale import train_matcher

    evals = [Path(p) for p in args.eval] if args.eval else sorted(settings.db_path.parent.glob("eval/world_*.db"))
    train_matcher(Path(args.db), evals, Path(args.out), u_pairs=args.pairs, adopt=args.adopt)


def cmd_portraits(args: argparse.Namespace) -> None:
    """Add synthetic portraits to an existing database (people in case records only)."""
    from .vision.gallery import seed_portraits
    s = _store()
    try:
        print(json.dumps(seed_portraits(s, settings.samples_dir, replace=args.replace), indent=2))
    finally:
        s.close()


def cmd_enrich(_: argparse.Namespace) -> None:
    from .synth.investigations import seed_investigations
    s = _store()
    try:
        print(json.dumps(seed_investigations(s), indent=2))
    finally:
        s.close()


def cmd_background(args: argparse.Namespace) -> None:
    """Add the dense ordinary background (cell sites, cameras, FIRs, businesses, ...) to an existing database, then re-run
    the pattern engine and report any lead that appeared or disappeared (there should be none)."""
    from .patterns.engine import run_patterns
    from .synth.enrich import enrich
    s = _store()
    try:
        before = {r["id"] for r in s.query("SELECT id FROM pattern_hits WHERE status='open'")}
        out = enrich(s, force=args.force)
        print(json.dumps(out, indent=2))
        if not out.get("skipped") and not args.no_patterns:
            run_patterns(s, run_by="cli:background")
            after = {r["id"] for r in s.query("SELECT id FROM pattern_hits WHERE status='open'")}
            print(json.dumps({"open_leads_before": len(before), "open_leads_after": len(after),
                              "new": sorted(after - before), "gone": sorted(before - after)}, indent=2))
    finally:
        s.close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="drishti", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init")
    p.add_argument("--live", action="store_true", help="pull SACHET live instead of the saved snapshot")
    p.set_defaults(fn=cmd_init)
    p = sub.add_parser("seed")
    p.add_argument("--seed", type=int, default=11)
    p.add_argument("--people", type=int, default=1800)
    p.set_defaults(fn=cmd_seed)
    p = sub.add_parser("ingest")
    p.add_argument("source", choices=["sachet"])
    p.add_argument("--live", action="store_true")
    p.add_argument("--limit", type=int, default=80)
    p.set_defaults(fn=cmd_ingest)
    sub.add_parser("resolve").set_defaults(fn=cmd_resolve)
    for name, fn in (("serve", cmd_serve), ("demo", cmd_demo)):
        p = sub.add_parser(name)
        p.add_argument("--host", default="127.0.0.1")
        p.add_argument("--port", type=int, default=8000)
        if name == "demo":
            p.add_argument("--fresh", action="store_true", help="delete the database and rebuild")
            p.add_argument("--live", action="store_true")
            p.add_argument("--no-serve", action="store_true")
            p.add_argument("--people", type=int, default=1800, help="size of the synthetic background population")
            p.add_argument("--no-redteam", action="store_true", help="skip the adversary simulation (saves about a minute)")
            p.add_argument("--no-portraits", action="store_true", help="skip the synthetic portraits of people in case records")
            p.add_argument("--no-background", action="store_true", help="skip the dense ordinary background (cell sites, cameras, FIRs, businesses)")
        p.set_defaults(fn=fn)
    p = sub.add_parser("audit")
    p.add_argument("what", choices=["verify", "alerts", "seal"])
    p.set_defaults(fn=cmd_audit)
    sub.add_parser("stats").set_defaults(fn=cmd_stats)
    p = sub.add_parser("patterns", help="mission-track pattern engine: run detectors, evaluate, red-team, list the catalog")
    p.add_argument("what", choices=["run", "eval", "redteam", "catalog"])
    p.set_defaults(fn=cmd_patterns)
    p = sub.add_parser("scale", help="build a large synthetic world, run every stage, report volume, timings, quality and latency")
    p.add_argument("--people", type=int, default=40000)
    # distinct from the evaluation worlds' seeds (11, 23, 47, 91), so a scale world never shares identities with a holdout
    p.add_argument("--seed", type=int, default=101)
    p.add_argument("--db", default=str(settings.db_path.parent / "scale.db"))
    p.add_argument("--report", default=str(settings.db_path.parent / "scale-report.json"))
    p.set_defaults(fn=cmd_scale)
    p = sub.add_parser("train", help="estimate entity-resolution parameters on a large world and test them on held-out worlds")
    p.add_argument("what", choices=["matcher"])
    p.add_argument("--db", default=str(settings.db_path.parent / "scale.db"))
    p.add_argument("--eval", nargs="*")
    p.add_argument("--pairs", type=int, default=400_000)
    p.add_argument("--out", default=str(settings.db_path.parent / "models" / "matcher-trained.json"))
    p.add_argument("--adopt", action="store_true", help="use the trained parameters from now on, if they beat the hand-set ones")
    p.set_defaults(fn=cmd_train)
    p = sub.add_parser("portraits", help="give each person in a case record a synthetic portrait (faces of people who do not exist)")
    p.add_argument("--replace", action="store_true", help="take back earlier demo portraits and assign again from the current pool")
    p.set_defaults(fn=cmd_portraits)
    sub.add_parser("enrich", help="add reproducible, non-financial synthetic case files without replacing existing data").set_defaults(fn=cmd_enrich)
    p = sub.add_parser("background", help="add the dense ordinary background: 1,000+ cell sites, cameras, FIRs, businesses, firearms, tenders")
    p.add_argument("--force", action="store_true", help="add again even if this database already has it")
    p.add_argument("--no-patterns", action="store_true", help="skip re-running the pattern engine afterwards")
    p.set_defaults(fn=cmd_background)
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args.fn(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())

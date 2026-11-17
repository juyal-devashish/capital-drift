"""
Command-line entry points.

    python -m app.cli migrate
    python -m app.cli seed  --corpus ../../finqa-testdata
    python -m app.cli run   C004-FY2024
    python -m app.cli eval  --corpus ../../finqa-testdata --split dev --out runs/dev
    python -m app.cli synth --seed 7 --out data/synth      # synthetic capital-planning portfolio

``eval`` runs the real agent graph over corpus sets (same code path as the API, without HTTP),
then writes predictions.jsonl / timings.csv / sets.txt in the format the corpus' score.py reads,
and runs the scorer if it is present.
"""

import argparse
import csv
import json
import logging
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from sqlalchemy import select

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.migrate import upgrade
from app.db.models import DocumentSet, ExceptionRecord, ExceptionStatus, Run
from app.db.session import session_scope

log = logging.getLogger("finqa.cli")

SPLITS = {
    "dev": lambda r: r["kind"] == "standard" and r["fiscal_year"] == "2023",
    "test": lambda r: r["kind"] == "standard" and r["fiscal_year"] != "2023",
    "stress": lambda r: r["kind"] == "stress",
    "all": lambda r: True,
}


def cmd_seed(args) -> None:
    from app.services.seeding import seed_corpus

    with session_scope() as db:
        counts = seed_corpus(db, Path(args.corpus))
    print(json.dumps(counts))


def cmd_synth(args) -> None:
    """Generate a synthetic portfolio, write it to --out and (unless --no-load) load it."""
    from app.synth.generator import generate
    from app.synth.io import load_dataset, write_dataset

    out = Path(args.out)
    dataset, key = generate(seed=args.seed, n_associations=args.associations)
    written = write_dataset(dataset, key, out)
    result = {"out": str(out.resolve()), "written": written, "answer_key": key.summary()}
    if not args.no_load:
        with session_scope() as db:
            result["loaded"] = load_dataset(db, out, studies=args.studies)
    print(json.dumps(result, indent=2))


def _run_set(set_id: str) -> tuple[str, str, float, str]:
    from app.agents.runner import get_run_manager

    mgr = get_run_manager()
    t0 = time.perf_counter()
    run_id = mgr.create_run(set_id, "cli")
    status = mgr.execute(run_id)
    return set_id, run_id, time.perf_counter() - t0, status


def cmd_run(args) -> None:
    set_id, run_id, secs, status = _run_set(args.set_id)
    with session_scope() as db:
        run = db.get(Run, run_id)
        print(
            json.dumps(
                {
                    "run_id": run_id,
                    "status": status,
                    "seconds": round(secs, 1),
                    "error": run.error,
                    "summary": run.stats,
                },
                indent=2,
                default=str,
            )
        )


def cmd_eval(args) -> None:
    corpus = Path(args.corpus).resolve()
    with session_scope() as db:
        from app.services.seeding import seed_corpus

        seed_corpus(db, corpus)
    with open(corpus / "manifest.csv", newline="") as f:
        sets = [r["set_id"] for r in csv.DictReader(f) if SPLITS[args.split](r)]
    if args.limit:
        sets = sets[: args.limit]
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for i, res in enumerate(pool.map(_run_set, sets), start=1):
            results.append(res)
            print(f"[{i}/{len(sets)}] {res[0]:<24} {res[3]:<10} {res[2]:6.1f}s", flush=True)

    with (
        session_scope() as db,
        open(out / "predictions.jsonl", "w") as pf,
        open(out / "timings.csv", "w", newline="") as tf,
        open(out / "sets.txt", "w") as sf,
    ):
        tw = csv.writer(tf)
        tw.writerow(["set_id", "seconds", "status"])
        for set_id, run_id, secs, status in results:
            tw.writerow([set_id, f"{secs:.1f}", status])
            sf.write(set_id + "\n")
            # Predictions = exceptions this run found (open or already decided), not ones it closed.
            for e in db.scalars(
                select(ExceptionRecord).where(
                    ExceptionRecord.set_id == set_id,
                    ExceptionRecord.last_run_id == run_id,
                    ExceptionRecord.status != ExceptionStatus.RESOLVED_BY_RERUN,
                )
            ):
                pf.write(
                    json.dumps(
                        {
                            "set_id": set_id,
                            "metric": e.metric,
                            "period": e.period,
                            "type": e.type,
                            "severity": e.severity,
                        }
                    )
                    + "\n"
                )
    failed = [r for r in results if r[3] != "succeeded"]
    print(f"\n{len(results) - len(failed)}/{len(results)} runs succeeded; outputs in {out}")
    scorer = corpus / "tools" / "score.py"
    if scorer.exists():
        subprocess.run(
            [
                sys.executable,
                str(scorer),
                "--pred",
                str(out / "predictions.jsonl"),
                "--timings",
                str(out / "timings.csv"),
                "--sets-file",
                str(out / "sets.txt"),
            ],
            check=False,
        )


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    p = argparse.ArgumentParser(prog="finqa")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("migrate", help="apply database migrations")
    s = sub.add_parser("seed", help="load the test corpus (without ground truth)")
    s.add_argument("--corpus", required=True)
    r = sub.add_parser("run", help="run a review for one set synchronously")
    r.add_argument("set_id")
    e = sub.add_parser("eval", help="run the agents over a corpus split and score the result")
    e.add_argument("--corpus", required=True)
    e.add_argument("--split", choices=list(SPLITS), default="dev")
    e.add_argument("--out", default="runs/latest")
    e.add_argument("--workers", type=int, default=2)
    e.add_argument("--limit", type=int)
    y = sub.add_parser("synth", help="generate a synthetic capital-planning portfolio and load it")
    y.add_argument("--seed", type=int, default=7)
    y.add_argument("--associations", type=int, default=20)
    y.add_argument("--out", default=str(settings.data_dir / "synth"))
    y.add_argument("--no-load", action="store_true", help="write the files only")
    y.add_argument("--studies", choices=["pdf", "csv"], default="pdf", help="read reserve studies from PDF or CSV")
    args = p.parse_args()

    upgrade()  # every command works against an up-to-date schema
    if args.cmd == "seed":
        cmd_seed(args)
    elif args.cmd == "run":
        with session_scope() as db:
            if db.get(DocumentSet, args.set_id) is None:
                sys.exit(f"unknown set {args.set_id} (seed it first)")
        cmd_run(args)
    elif args.cmd == "eval":
        cmd_eval(args)
    elif args.cmd == "synth":
        cmd_synth(args)


if __name__ == "__main__":
    main()

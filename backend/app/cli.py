"""
Command-line entry points. Run from backend/: ``python -m app.cli <command>``.

    demo                  build the demo database in one step (seed 7, no API calls)
    synth --seed 7        generate a synthetic portfolio and load it
    match                 rule-match every invoice to a reserve component
    match-llm             ask Claude about invoices the rules left unsure (live calls cost money)
    warn                  raise repair-or-replace warnings from stored matches
    sync-queue            rerun warnings on reviewed matches and update the review queue
    score-matches, score-warnings, eval-warnings, eval-review, results
                          offline evaluation against the synthetic answer key
"""

import argparse
import json
import sys
from pathlib import Path

from sqlalchemy import select

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.migrate import upgrade
from app.db.session import session_scope


def cmd_demo(args) -> None:
    """Seed 7 end to end: generate, rule-match, reuse Claude's cached answers, warn, build the queue."""
    from app.services.llm_matching import run_llm_matching
    from app.services.matching import run_rule_matching
    from app.services.review import queue_counts, sync_queue
    from app.services.warnings import run_warnings
    from app.synth.generator import generate
    from app.synth.io import load_dataset, write_dataset

    out = get_settings().data_dir / "synth"
    write_dataset(*generate(seed=args.seed), out)
    with session_scope() as db:
        load_dataset(db, out)
    with session_scope() as db:
        rules = run_rule_matching(db)
    with session_scope() as db:
        llm = run_llm_matching(db, live=False)  # cached answers only: never calls the API
    with session_scope() as db:
        run_warnings(db, "rules")
        warnings = run_warnings(db, "combined")
        sync_queue(db)
        queue = queue_counts(db)
    print(
        json.dumps(
            {
                "seed": args.seed,
                "rule_matches": rules,
                "claude_answers_from_cache": llm["matches_stored"],
                "warnings": warnings["by_kind"],
                "queue": queue,
            },
            indent=2,
        )
    )
    if not llm["matches_stored"]:
        print("No cached Claude answers found; the queue is rules-only. See README.", file=sys.stderr)


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


def cmd_match(_args) -> None:
    from app.services.matching import run_rule_matching

    with session_scope() as db:
        print(json.dumps(run_rule_matching(db), indent=2))


def cmd_score_matches(args) -> None:
    """Score stored matches against a synthetic answer key (offline evaluation only)."""
    from app.db.models import Invoice
    from app.evals.matching import score_matches
    from app.services.llm_matching import combined_matches, stored_matches

    truths = json.loads(Path(args.answer_key).read_text(encoding="utf-8"))["invoices"]
    with session_scope() as db:
        invoices = list(db.scalars(select(Invoice)))
        results = combined_matches(db) if args.method == "combined" else stored_matches(db, args.method)
    if len(results) != len(invoices):
        sys.exit(
            f"{len(results)} {args.method} matches for {len(invoices)} invoices; "
            "run `match` first (or use --method combined)"
        )
    report = score_matches(results, invoices, truths)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


def cmd_match_llm(args) -> None:
    """Ask Claude about the invoices the rules left unsure. Live calls cost money; see --max-calls."""
    from app.services.llm_matching import run_llm_matching

    with session_scope() as db:
        report = run_llm_matching(db, live=not args.cached_only, max_calls=args.max_calls)
    print(json.dumps(report, indent=2))


def cmd_warn(args) -> None:
    """Watch every component's matched spend against its plan and store the warnings."""
    from app.services.warnings import run_warnings

    with session_scope() as db:
        report = run_warnings(db, args.method)
    print(json.dumps(report, indent=2))


def cmd_score_warnings(args) -> None:
    """Score stored warnings against a synthetic answer key (offline evaluation only)."""
    from app.db.models import Invoice, ReserveComponent
    from app.domain.warnings import watch_window
    from app.evals.warnings import component_years, score_warnings
    from app.services.warnings import stored_warnings

    key = json.loads(Path(args.answer_key).read_text(encoding="utf-8"))
    with session_scope() as db:
        invoices = list(db.scalars(select(Invoice)))
        n_components = len(list(db.scalars(select(ReserveComponent))))
        warnings = stored_warnings(db, args.method)
    start, through = watch_window(invoices)
    report = score_warnings(
        warnings,
        key["events"],
        key["invoices"],
        {i.id: i.invoice_date for i in invoices},
        component_years(n_components, start, through),
    )
    _emit(report, args.out)


def cmd_eval_warnings(args) -> None:
    """Generate, label, watch and score whole portfolios in memory. Touches no database; no API calls."""
    from app.evals.warnings import evaluate_seed

    _emit([evaluate_seed(seed, args.labels) for seed in args.seeds], args.out)


def cmd_eval_review(args) -> None:
    """Simulate a property manager working the overdue warnings, using the answer key (upper bound)."""
    from app.evals.review import evaluate_review_db, evaluate_review_seed

    if args.answer_key:
        key = json.loads(Path(args.answer_key).read_text(encoding="utf-8"))
        with session_scope() as db:
            _emit(evaluate_review_db(db, key, args.method), args.out)
    else:
        _emit([evaluate_review_seed(seed) for seed in args.seeds], args.out)


def cmd_results(args) -> None:
    """Write the results page's file (aggregates on synthetic data). No API calls."""
    from app.core.config import get_settings
    from app.evals.bundle import build

    key = json.loads(Path(args.answer_key).read_text(encoding="utf-8"))
    out = Path(args.out) if args.out else get_settings().capital_results_file
    with session_scope() as db:
        bundle = build(db, key)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(bundle, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out}")


def cmd_sync_queue(_args) -> None:
    """Rerun warnings on the reviewed matches and reconcile the review queue."""
    from app.services.review import queue_counts, sync_queue

    with session_scope() as db:
        changes = sync_queue(db)
        print(json.dumps({k: len(v) for k, v in changes.items()} | {"queue": queue_counts(db)}, indent=2))


def _emit(report, out: str | None) -> None:
    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    p = argparse.ArgumentParser(prog="capital-drift")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("migrate", help="apply database migrations")
    d = sub.add_parser("demo", help="build the demo database in one step (no API calls)")
    d.add_argument("--seed", type=int, default=7)
    y = sub.add_parser("synth", help="generate a synthetic capital-planning portfolio and load it")
    y.add_argument("--seed", type=int, default=7)
    y.add_argument("--associations", type=int, default=20)
    y.add_argument("--out", default=str(settings.data_dir / "synth"))
    y.add_argument("--no-load", action="store_true", help="write the files only")
    y.add_argument("--studies", choices=["pdf", "csv"], default="pdf", help="read reserve studies from PDF or CSV")
    sub.add_parser("match", help="rule-match every invoice to a reserve component")
    ml = sub.add_parser("match-llm", help="ask Claude about invoices the rules left unsure (live calls cost money)")
    ml.add_argument("--max-calls", type=int, help="cap on live calls (default: CD_MATCH_LLM_MAX_CALLS, 10)")
    ml.add_argument("--cached-only", action="store_true", help="use cached responses only; no live calls")
    sm = sub.add_parser("score-matches", help="score stored matches against a synthetic answer key")
    sm.add_argument("--answer-key", required=True)
    sm.add_argument("--method", default="rules", choices=["rules", "llm", "combined"])
    sm.add_argument("--out", help="also write the report to this JSON file")
    w = sub.add_parser("warn", help="raise repair-or-replace warnings from stored matches")
    w.add_argument("--method", default="combined", choices=["rules", "combined", "reviewed"])
    sw = sub.add_parser("score-warnings", help="score stored warnings against a synthetic answer key")
    sw.add_argument("--answer-key", required=True)
    sw.add_argument("--method", default="combined", choices=["rules", "combined", "reviewed"])
    sw.add_argument("--out", help="also write the report to this JSON file")
    ew = sub.add_parser("eval-warnings", help="score warnings on in-memory portfolios (no database, no API calls)")
    ew.add_argument("--seeds", type=int, nargs="+", default=[11, 12, 13])
    ew.add_argument("--labels", default="rules", choices=["rules", "truth"])
    ew.add_argument("--out", help="also write the report to this JSON file")
    er = sub.add_parser("eval-review", help="simulate reviewing overdue warnings with the answer key (upper bound)")
    er.add_argument("--answer-key", help="score the loaded portfolio's stored matches against this key")
    er.add_argument("--method", default="combined", choices=["rules", "combined"])
    er.add_argument("--seeds", type=int, nargs="+", default=[12, 13], help="in memory, rules-only, if no key")
    er.add_argument("--out", help="also write the report to this JSON file")
    sub.add_parser("sync-queue", help="rerun warnings on reviewed matches and update the review queue")
    rs = sub.add_parser("results", help="write the results page's file from the answer key (no API calls)")
    rs.add_argument("--answer-key", required=True)
    rs.add_argument("--out", help="default: backend/results/capital_results.json")
    args = p.parse_args()

    upgrade()  # every command works against an up-to-date schema
    commands = {
        "migrate": lambda _a: None,
        "demo": cmd_demo,
        "synth": cmd_synth,
        "match": cmd_match,
        "match-llm": cmd_match_llm,
        "score-matches": cmd_score_matches,
        "warn": cmd_warn,
        "score-warnings": cmd_score_warnings,
        "eval-warnings": cmd_eval_warnings,
        "eval-review": cmd_eval_review,
        "sync-queue": cmd_sync_queue,
        "results": cmd_results,
    }
    commands[args.cmd](args)


if __name__ == "__main__":
    main()

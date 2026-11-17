"""
One results file for the results page: aggregates only, with the caveats attached.

Built offline from the answer key (which the app never loads) and the loaded seed-7 portfolio's
stored matches. Seeds 11-13 are generated in memory with rules-only matches. Nothing here makes an
API call: Claude's answers come from the stored matches.
"""

from dataclasses import asdict
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Invoice, LLMAttemptRecord, ReserveComponent
from app.domain.matching import match_invoices
from app.domain.warnings import WatchSettings, watch_window
from app.evals.forecast import backtest_seed
from app.evals.matching import score_matches
from app.evals.review import evaluate_review_db, evaluate_review_seed
from app.evals.warnings import component_years, evaluate_seed, score_warnings
from app.services.llm_matching import combined_matches, stored_matches
from app.services.warnings import stored_warnings

HELD_OUT = (11, 12, 13)
FRESH = (14, 15, 16, 17)  # first used for the forecast backtest, after the forecast was written
CAVEATS = [
    "All data is synthetic. The same person wrote the generator, the rules and the detector, "
    "so treat every number as optimistic.",
    "Seed 7 was used to tune the rules. Seeds 11-13 were held out, but seed 11's warning false alarms "
    "were inspected before the review rule was written, so 12 and 13 are the clean held-out seeds for review.",
    "Claude was run on seed 7 only; seeds 11-13 use rules-only matches.",
    "The forecast backtest uses only data up to 2020 and compares 2021-2025. Its 10-90% band covers only the "
    "spread in replacement cost, so it holds the actual balance far less often than 80% of the time.",
    "The review numbers come from a simulated reviewer answering from the answer key: "
    "an upper bound, not a measurement of people.",
    "About 12 planted problems per seed, so each detection rate rests on very few cases.",
]


def _matching(report: dict) -> dict:
    keys = ("invoices", "coverage", "component_accuracy", "precision_on_decided", "dollar_weighted_accuracy")
    out = {k: report[k] for k in keys}
    out["repairs"] = report["by_true_type"]["repair"]["accuracy"]
    out["replacements"] = report["by_true_type"]["replacement"]["accuracy"]
    out["wrong_fund_flags"] = report["wrong_fund_flags"]
    return out


def _warnings(report: dict, seed: int, labels: str) -> dict:
    keys = ("events", "detected", "planted", "false_alarms", "false_alarms_by_kind")
    return {
        "seed": seed,
        "labels": labels,
        **{k: report[k] for k in keys},
        "per_100": report["false_alarms_per_100_component_years"],
    }


def build(db: Session, answer_key: dict) -> dict:
    from app.synth.generator import generate

    truths = answer_key["invoices"]
    invoices = list(db.scalars(select(Invoice)))
    if len(invoices) != len(truths):
        raise ValueError(
            f"the database holds {len(invoices)} invoices but the answer key {len(truths)}; load that seed"
        )
    seed = answer_key["seed"]

    matching = [
        {"seed": seed, "labels": "rules", **_matching(score_matches(stored_matches(db, "rules"), invoices, truths))},
        {"seed": seed, "labels": "rules + Claude", **_matching(score_matches(combined_matches(db), invoices, truths))},
    ]
    for s in HELD_OUT:
        ds, key = generate(s)
        t = {k: asdict(v) for k, v in key.truths.items()}
        matching.append(
            {
                "seed": s,
                "labels": "rules",
                **_matching(score_matches(match_invoices(ds.invoices, ds.components, ds.associations), ds.invoices, t)),
            }
        )

    if not stored_warnings(db, "combined"):
        raise ValueError("no stored combined warnings; run `warn --method combined` first")
    start, through = watch_window(invoices)
    n_comp = db.scalar(select(func.count()).select_from(ReserveComponent))
    combined_warn = score_warnings(
        stored_warnings(db, "combined"),
        answer_key["events"],
        truths,
        {i.id: i.invoice_date for i in invoices},
        component_years(n_comp, start, through),
    )
    warnings = [
        _warnings(evaluate_seed(seed, "truth"), seed, "perfect labels"),
        _warnings(evaluate_seed(seed, "rules"), seed, "rules"),
        _warnings(combined_warn, seed, "rules + Claude"),
    ]
    for labels in ("truth", "rules"):
        for s in HELD_OUT:
            warnings.append(_warnings(evaluate_seed(s, labels), s, "perfect labels" if labels == "truth" else "rules"))

    tradeoff = []
    for h in (4.0, 5.0, 6.0):
        for labels in ("truth", "rules"):
            runs = [evaluate_seed(s, labels, settings=WatchSettings(cusum_threshold=h)) for s in HELD_OUT]
            tradeoff.append(
                {
                    "threshold": h,
                    "labels": "perfect labels" if labels == "truth" else "rules",
                    "caught": sum(r["events"]["early_failure"]["detected"] for r in runs),
                    "planted": sum(r["events"]["early_failure"]["planted"] for r in runs),
                    "false_failing_early": sum(r["false_alarms_by_kind"].get("failing_early", 0) for r in runs),
                }
            )

    forecast_rows = []
    for mode in ("flat", "rising"):
        for group, seeds in (("development", (seed, *HELD_OUT)), ("fresh", FRESH)):
            runs = [backtest_seed(s, "rules", contributions=mode) for s in seeds]
            forecast_rows.append(
                {
                    "contributions": mode,
                    "seeds": list(seeds),
                    "group": group,
                    "ran_short": sum(r["ran_short"] for r in runs),
                    "already_below_zero": sum(r["already_below_zero"] for r in runs),
                    "called_and_ran_short": sum(r["called_and_ran_short"] for r in runs),
                    "false_calls": sum(len(r["false_calls"]) for r in runs),
                    "plain_called_and_ran_short": sum(r["plain_schedule_called_and_ran_short"] for r in runs),
                    "plain_false_calls": sum(r["plain_schedule_false_calls"] for r in runs),
                    "band_coverage": [r["band_coverage"] for r in runs],
                    "final_year_coverage": [r["final_year_coverage"] for r in runs],
                }
            )

    review = [evaluate_review_db(db, answer_key, "combined") | {"labels": "rules + Claude"}]
    review += [evaluate_review_seed(s) for s in HELD_OUT]

    latest = db.scalar(select(LLMAttemptRecord.run_id).order_by(LLMAttemptRecord.id.desc()).limit(1))
    attempts = list(db.scalars(select(LLMAttemptRecord).where(LLMAttemptRecord.run_id == latest)))
    by_status: dict[str, int] = {}
    for a in attempts:
        by_status[a.status] = by_status.get(a.status, 0) + 1
    claude = {
        "run": "the latest match-llm run (earlier runs are kept in llm_attempts too)",
        "asked": len(attempts),
        "from_cache": sum(a.from_cache for a in attempts),  # token counts include the cached answers' original call
        "by_status": dict(sorted(by_status.items())),
        "input_tokens": sum(a.input_tokens for a in attempts),
        "output_tokens": sum(a.output_tokens for a in attempts),
        "cache_read_tokens": sum(a.cache_read_tokens for a in attempts),
    }

    return {
        "label": "SYNTHETIC data. Offline evaluation; the app itself never loads the answer key.",
        "generated_on": date.today().isoformat(),
        "seed": seed,
        "held_out_seeds": list(HELD_OUT),
        "caveats": CAVEATS,
        "matching": matching,
        "claude_run": claude,
        "warnings": warnings,
        "threshold_tradeoff": tradeoff,
        "review": review,
        "forecast_backtest": forecast_rows,
    }

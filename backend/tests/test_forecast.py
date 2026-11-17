"""Reserve forecast: history arithmetic, due years, failing parts, the plain-schedule baseline, determinism."""

from dataclasses import dataclass
from datetime import date

from app.domain.forecast import (
    Completed,
    ForecastSettings,
    completed_projects,
    cost_ratios,
    first_due,
    forecast_association,
)
from app.domain.warnings import Spend


@dataclass
class Comp:
    id: str
    association_id: str = "G"
    name: str = "Roof"
    location: str | None = None
    useful_life_years: int = 20
    remaining_life_years: int = 5
    replacement_cost: float = 100_000.0
    planned_year: int = 2021


@dataclass
class Assoc:
    id: str = "G"
    study_year: int = 2016
    inflation_rate: float = 0.0
    reserve_balance_start: float = 50_000.0
    annual_contribution: float = 10_000.0


def test_completed_projects_need_half_the_plan_and_finish_on_the_crossing_invoice():
    spend = [
        Spend("D", "R", date(2019, 5, 1), 30_000, "replacement"),
        Spend("F", "R", date(2019, 7, 1), 75_000, "replacement"),
        Spend("P", "R", date(2022, 5, 1), 10_000, "replacement"),  # a partial: not a replacement
    ]
    done = completed_projects([Comp("R")], [Assoc()], spend)
    assert done == [Completed("R", date(2019, 7, 1), 105_000.0, 100_000.0)]
    assert cost_ratios(done) == [1.05]
    assert cost_ratios([Completed("X", date(2019, 1, 1), 300_000, 100_000)]) == [], "3x is a matching error"


def test_due_year_restarts_from_the_last_replacement_and_past_due_parts_are_due_now():
    done = [Completed("R", date(2015, 6, 1), 1, 1)]
    assert first_due(Comp("R"), done, 2020) == 2035
    assert first_due(Comp("R", planned_year=2018), [], 2020) == 2021, "past due, never replaced"
    assert first_due(Comp("R", planned_year=2027), [], 2020) == 2027


def test_history_and_a_certain_forecast():
    spend = [Spend("X", "R", date(2017, 3, 1), 20_000, "replacement")]
    f = forecast_association(Assoc(), [Comp("R")], spend, [], [1.0], [], 2016, 2018, ForecastSettings(years=5, runs=50))
    assert [h["balance"] for h in f.history] == [60_000.0, 50_000.0, 60_000.0]
    # planned 2021 at 100k: 60k + 3 x 10k - 100k = -10k in 2021, then +10k a year
    assert [y["p50"] for y in f.years] == [70_000.0, 80_000.0, -10_000.0, 0.0, 10_000.0]
    assert f.first_short_year == 2021 and f.share_short == 1.0
    assert all(y["p10"] == y["p90"] for y in f.years), "one ratio, nothing failing: every run agrees"


def test_a_failing_part_comes_due_within_the_early_window():
    comp = Comp("R", planned_year=2035, replacement_cost=150_000.0)
    s = ForecastSettings(years=5, runs=200, early_years=3)
    calm = forecast_association(Assoc(), [comp], [], [], [1.0], [], 2016, 2020, s)
    failing = forecast_association(Assoc(), [comp], [], [], [1.0], ["R"], 2016, 2020, s)
    assert calm.share_short == 0.0
    assert failing.share_short == 1.0, "150k due by 2023 against 110-130k of reserves"
    assert {y["year"] for y in failing.years if y["p90"] != y["p10"]} <= {2021, 2022, 2023}


def test_the_plain_schedule_ignores_history_and_cost_ratios():
    comp = Comp("R", planned_year=2018)
    plain = ForecastSettings(years=5, runs=20, adjust=False)
    f = forecast_association(Assoc(), [comp], [], [], [1.5], ["R"], 2016, 2020, plain)
    assert f.due == {"R": 2038}, "assumes the 2018 replacement happened"
    assert f.share_short == 0.0


def test_same_inputs_same_forecast():
    args = (Assoc(), [Comp("R")], [], [], [0.9, 1.0, 1.3], ["R"], 2016, 2020, ForecastSettings(years=6, runs=100))
    assert forecast_association(*args) == forecast_association(*args)


def test_backtest_regression_floor_on_seed_12():
    """Seed 12 was a development seed for the forecast. Measured 2026-11-17 (docs/results.md). Never loosen it."""
    from app.evals.forecast import backtest_seed

    r = backtest_seed(12, "rules", contributions="flat")
    assert r["called_and_ran_short"] >= 4 and len(r["false_calls"]) <= 1

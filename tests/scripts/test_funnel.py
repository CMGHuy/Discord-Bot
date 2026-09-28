"""v103/v104: grid-agnostic measurement funnel -- two tiers, plateau, folds."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))

import funnel  # noqa: E402

FAST = dict(n_resamples=400, seed=42)
GRID = (0.1, 0.25, 0.5)


def _row(ticker, outcome, value, year="2015", direction="bullish"):
    return {"ticker": ticker, "horizon_key": "4w", "direction": direction,
            "entry_date": f"{year}-06-01", "outcome": outcome, "r_multiple": value}


def _tier1_only():
    rows = [_row("T0", "win", 3.0) for _ in range(20)]
    for index in range(1, 10):
        rows += [_row(f"T{index}", "win", 0.1), _row(f"T{index}", "loss", -1.0)]
    return rows


def _tier2_only():
    rows = []
    for index in range(10):
        rows += [_row(f"T{index}", "win", 3.0) for _ in range(2)]
        rows += [_row(f"T{index}", "loss", -1.0) for _ in range(4)]
    return rows


def _losers():
    return [_row(f"T{index}", "loss", -1.0) for index in range(40)]


def test_cell_key_is_stable():
    assert [funnel.cell_key(value) for value in (0.0, 0.1, 0.618, 1.0)] == ["0", "0.1", "0.618", "1"]


def test_direction_and_year_filters_preserve_the_selected_rows():
    rows = [_row("A", "win", 1.0, "2015"), _row("B", "loss", -1.0, "2016", "bearish")]
    assert funnel.dir_rows(rows, "bullish") == [rows[0]]
    assert funnel.year_rows(rows, 2016, 2016) == [rows[1]]


def test_score_cell_assigns_tiers():
    assert funnel.score_cell(_tier1_only(), 30, **FAST)["tier"] == 1
    tier2 = funnel.score_cell(_tier2_only(), 30, **FAST)
    assert tier2["tier"] == 2 and tier2["lower_bound"] > 0 and not tier2["tier1"]["clears"]
    assert funnel.score_cell(_losers(), 30, **FAST)["tier"] is None
    assert funnel.score_cell(_tier1_only(), 30, **FAST)["tier2"]["clauses"]["lower_bound"] is False


def test_lower_bound_is_deterministic_and_none_when_empty():
    assert funnel.expr_lower_bound(_tier1_only(), **FAST) == funnel.expr_lower_bound(_tier1_only(), **FAST)
    assert funnel.expr_lower_bound([], **FAST) is None


def test_stage1_prefers_a_tier1_plateau():
    rows = {funnel.cell_key(value): _tier1_only() for value in GRID}
    result = funnel.stage1(rows, "bullish", GRID, **FAST)
    assert result["plateau_tier1"] == list(GRID) and result["winner_tier"] == 1


def test_stage1_falls_back_to_a_tier2_plateau():
    rows = {funnel.cell_key(value): _tier2_only() for value in GRID}
    result = funnel.stage1(rows, "bullish", GRID, **FAST)
    assert result["plateau_tier1"] == [] and result["winner_tier"] == 2 and result["winner"] in GRID


def test_stage1_isolated_spike_has_no_winner():
    rows = {funnel.cell_key(0.1): _losers(), funnel.cell_key(0.25): _tier1_only(), funnel.cell_key(0.5): _losers()}
    result = funnel.stage1(rows, "bullish", GRID, **FAST)
    assert result["winner"] is None and result["winner_tier"] is None


def test_fold_pick_uses_only_the_train_span():
    rows = {funnel.cell_key(value): [] for value in GRID}
    rows[funnel.cell_key(0.1)] = [_row("A", "win", 2.0, "2011") for _ in range(20)] + [_row("A", "loss", -1.0, "2011") for _ in range(15)] + [_row("A", "loss", -1.0, "2016") for _ in range(40)]
    rows[funnel.cell_key(0.25)] = [_row("A", "win", 2.0, "2011") for _ in range(5)] + [_row("A", "loss", -1.0, "2011") for _ in range(30)] + [_row("A", "win", 2.0, "2016") for _ in range(40)]
    assert funnel.fold_pick(rows, "bullish", 2013, GRID) == 0.1
    assert funnel.fold_pick(rows, "bullish", 2011, GRID) is None
    assert funnel.fold_pick(rows, "bullish", 2017, GRID) == 0.25


def test_fold_verdict_two_thirds_and_minimum_three():
    good, bad, thin = {"n": 20, "expectancy_r": 0.2}, {"n": 20, "expectancy_r": -0.1}, {"n": 5, "expectancy_r": 1.0}
    assert funnel.fold_verdict([{"tol": 0.1, "stats": stats} for stats in (good, good, bad, thin)])["clears"] is True
    assert funnel.fold_verdict([{"tol": 0.1, "stats": stats} for stats in (good, bad, bad)])["clears"] is False
    verdict = funnel.fold_verdict([{"tol": 0.1, "stats": good}, {"tol": 0.1, "stats": good}, {"tol": None, "stats": None}])
    assert verdict["clears"] is False and verdict["unselected"] == 1


def test_stage2_shape():
    rows = {funnel.cell_key(value): _tier2_only() for value in GRID}
    result = funnel.stage2(rows, "bullish", GRID)
    assert len(result["folds"]) == len(funnel.FOLD_YEARS) and set(result["verdict"]) >= {"clears", "qualifying"}


def test_stage2_accepts_custom_fold_years():
    rows = [_row(f"T{index}", "win", 1.0, year=str(year))
            for year in range(2010, 2026) for index in range(40)]
    by_cell = {funnel.cell_key(0.5): rows}
    result = funnel.stage2(by_cell, "bullish", (0.5,), fold_years=tuple(range(2013, 2026)))
    assert [fold["test_year"] for fold in result["folds"]] == list(range(2013, 2026))


def test_fixed_folds_score_one_arm_per_year():
    rows = [_row("A", "win", 1.0, year="2014")] * 16 + [_row("B", "loss", -1.0, year="2015")] * 16
    folds = funnel.fixed_folds(rows, (2014, 2015, 2016))
    assert [fold["tol"] for fold in folds] == ["fixed"] * 3
    assert folds[0]["stats"]["n"] == 16 and folds[2]["stats"]["n"] == 0
    verdict = funnel.fold_verdict(folds)
    assert verdict["qualifying"] == 2 and verdict["positive"] == 1


def test_assert_rows_before_refuses_a_future_row():
    funnel.assert_rows_before([_row("A", "win", 1.0, year="2025")], "2025-12-31")
    import pytest

    with pytest.raises(SystemExit):
        funnel.assert_rows_before([_row("A", "win", 1.0, year="2026")], "2025-12-31")

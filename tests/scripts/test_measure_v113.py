"""v113 funnel logic -- no market data: synthetic rows and fake backtests."""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "backtest"))
import measure_v113 as mv  # noqa: E402

from swingbot.core.backtesting.backtest import ALL_STRATEGIES  # noqa: E402
from swingbot.core.market.entry_filters import DEFAULT_PARAMS  # noqa: E402
from swingbot.core.market.short_entries import FADE  # noqa: E402
from swingbot.core.market.strategy_types import (LEGACY_HORIZONS, SHORT_STRATEGIES,  # noqa: E402
                                                 STRATEGY_GATES, admits)
from swingbot.core.planning import reward_floor  # noqa: E402

FAST = dict(n_resamples=200, seed=42)
YEARS = (2013, 2014, 2015, 2016)


def _rows(years, per_year, win_share, *, direction="bearish", tickers=8, risk_pct=2.0, strategy=None):
    rows = []
    for year in years:
        wins = round(per_year * win_share)
        for i in range(per_year):
            win = i < wins
            row = {"ticker": f"T{i % tickers}", "horizon_key": "1w", "direction": direction,
                   "entry_date": f"{year}-06-01", "outcome": "win" if win else "loss",
                   "r_multiple": 1.0 if win else -1.0, "risk_pct": risk_pct}
            if strategy:
                row["strategy"] = strategy
            rows.append(row)
    return rows


def _trade(direction="bullish", date="2015-01-05"):
    return SimpleNamespace(direction=direction, entry_date=date, outcome="win", r_multiple=1.0,
                           entry=100.0, stop_loss=98.0, context=None)


def test_preregistered_constants():
    assert mv.HOLDOUT_END == "2026-09-25" and mv.HZ == "1w" and mv.A_GRID == (1.0, 1.25, 1.5)
    assert mv.D_TICKERS == ("SH", "PSQ", "RWM", "DOG")
    assert len(mv.PART_B) == 22 and len(set(mv.PART_B)) == 22
    strategies = {strategy for strategy, _ in mv.PART_B}
    assert strategies == set(ALL_STRATEGIES)
    assert not strategies & (set(SHORT_STRATEGIES) | {"Fibonacci Continuation"})


def test_d_cells_are_todays_live_bullish_masks():
    cells = set(mv.d_cells())
    assert ("VWAP", "4w") in cells and ("VWAP", "2w") not in cells
    assert ("MACD", "3m") in cells and ("MACD", "2w") not in cells
    assert {("EMA Crossover", hk) for hk in LEGACY_HORIZONS} <= cells
    assert all(hk != "1w" for _, hk in cells)
    assert {strategy for strategy, _ in cells} <= set(ALL_STRATEGIES)


def test_admit_1w_admits_exactly_one_pair_and_restores():
    before = dict(STRATEGY_GATES["VWAP"])
    with mv.admit_1w("VWAP", "bearish"):
        assert admits("VWAP", "bearish", "1w") and not admits("VWAP", "bullish", "1w")
        assert admits("VWAP", "bullish", "4w") and not admits("VWAP", "bullish", "2w")
        assert not admits("VWAP", "bearish", "4w")
    assert STRATEGY_GATES["VWAP"] == before and not admits("VWAP", "bearish", "1w")
    with mv.admit_1w("EMA Crossover", "bullish"):
        assert admits("EMA Crossover", "bullish", "1w") and admits("EMA Crossover", "bearish", "2w")
    assert "EMA Crossover" not in STRATEGY_GATES


def test_collect_b_runs_1w_only_with_its_cell_admitted():
    calls = []

    def fake_run(ticker, frame, strategy, horizon, **kw):
        calls.append((horizon, admits(strategy, "bearish", "1w"), admits(strategy, "bullish", "1w")))
        return SimpleNamespace(trades=[])

    out = mv.collect_b("MACD", "bearish", {"AAA": None, "BBB": None}, {}, mv.TRAIN, run_fn=fake_run)
    assert calls == [("1w", True, False)] * 2
    assert out["rows"] == [] and out["floor"]["floor_drop_rate"] is None


def test_collect_a_runs_every_grid_value_under_its_own_m():
    seen = []

    def fake_run(ticker, frame, strategy, horizon, **kw):
        seen.append((strategy, horizon, DEFAULT_PARAMS[FADE]["m"], admits(FADE, "bearish", "1w")))
        return SimpleNamespace(trades=[])

    out = mv.collect_a({"AAA": None}, {}, mv.TRAIN, run_fn=fake_run)
    assert seen == [(FADE, "1w", m, True) for m in mv.A_GRID]
    assert set(out["rows_by_cell"]) == set(out["floor"]) == {"1", "1.25", "1.5"}
    assert DEFAULT_PARAMS[FADE]["m"] == 1.0 and not admits(FADE, "bearish", "1w")


def test_collect_d_runs_every_live_bullish_cell_and_tags_the_strategy():
    rows = mv.collect_d({"SH": None}, {}, mv.TRAIN,
                        run_fn=lambda ticker, frame, strategy, horizon, **kw: SimpleNamespace(trades=[_trade()]))
    assert len(rows) == len(mv.d_cells())
    assert {(row["strategy"], row["horizon_key"]) for row in rows} == set(mv.d_cells())


def test_floor_counts_and_cap_bind_rate():
    reward_floor.reset()
    reward_floor.DROPS[("MACD", "1w")] += 1
    reward_floor.PASSES[("MACD", "1w")] += 3
    assert mv.floor_counts("MACD") == {"floor_drops": 1, "floor_passes": 3, "floor_drop_rate": 0.25}
    reward_floor.reset()
    rows = _rows((2015,), 2, 0.5, risk_pct=2.0) + _rows((2015,), 2, 0.5, risk_pct=1.5)
    assert mv.cap_bind_rate(rows, "MACD", "bullish") == 0.5
    assert mv.cap_bind_rate([], "MACD", "bullish") is None


def test_part_b_needs_tier_1_and_a_positive_lower_bound(monkeypatch):
    collected = {"rows": _rows(YEARS, 20, 0.75), "floor": {}}
    ok = mv.evaluate_b("MACD", "bearish", collected, **FAST)
    assert ok["clauses"]["lower_bound"] and ok["stage2"]["clears"]
    assert ok["proceed_to_holdout"] and ok["tier"] == 1
    fake = {"stats": {}, "lower_bound": -0.1, "tier": 1,
            "tier1": {"clears": True, "clauses": {"wr": True, "exp_r": True, "n": True, "scratch": True}},
            "tier2": {"clears": False, "clauses": {"exp_r": True, "lower_bound": False, "n": True, "scratch": True}}}
    monkeypatch.setattr(mv.funnel, "score_cell", lambda *a, **k: fake)
    lucky = mv.evaluate_b("MACD", "bearish", collected, **FAST)
    assert not lucky["proceed_to_holdout"] and lucky["tier"] is None


def test_part_a_takes_the_plateau_winner_through_the_folds(monkeypatch):
    monkeypatch.setattr(mv.funnel, "stage1", lambda *a, **k: {"winner": 1.25, "winner_tier": 2, "cells": {}})
    monkeypatch.setattr(mv.funnel, "stage2", lambda *a, **k: {"verdict": {"clears": True}})
    collected = {"rows_by_cell": {"1": [], "1.25": [], "1.5": []}, "floor": {}}
    ok = mv.evaluate_a(collected, **FAST)
    assert ok["proceed_to_holdout"] and ok["validation_cell"] == {"value": 1.25} and ok["tier"] == 2
    monkeypatch.setattr(mv.funnel, "stage2", lambda *a, **k: {"verdict": {"clears": False}})
    no = mv.evaluate_a(collected, **FAST)
    assert not no["proceed_to_holdout"] and no["validation_cell"] is None and no["tier"] is None


def test_part_d_is_one_pooled_cell_with_reported_breakdowns():
    rows = (_rows(YEARS, 10, 0.8, direction="bullish", strategy="RSI")
            + _rows(YEARS, 10, 0.7, direction="bullish", strategy="MACD"))
    out = mv.evaluate_d(rows, **FAST)
    assert out["scored"]["stats"]["n"] == 80
    assert set(out["by_strategy"]) == {"RSI", "MACD"} and len(out["by_ticker"]) == 8
    assert out["proceed_to_holdout"] and out["tier"] in (1, 2)


def test_part_d_refuses_any_other_universe():
    with pytest.raises(SystemExit):
        mv._d_frames(SimpleNamespace(tickers="SH,PSQ", universe=None))


def test_every_part_has_an_evaluator():
    assert set(mv.EVALUATORS) == {"A", "B", "D"}

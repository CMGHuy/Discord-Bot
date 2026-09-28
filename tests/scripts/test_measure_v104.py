"""v104 funnel logic -- no market data: synthetic rows and fake backtests."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "backtest"))
import measure_v104 as mv  # noqa: E402

from swingbot import config  # noqa: E402
from swingbot.core.market.entry_filters import DEFAULT_PARAMS  # noqa: E402
from swingbot.core.market.strategy_types import HORIZONS  # noqa: E402

FAST = dict(n_resamples=200, seed=42)


def _rows(years, per_year, win_share, *, direction="bullish", tickers=8):
    rows = []
    for year in years:
        wins = round(per_year * win_share)
        for i in range(per_year):
            win = i < wins
            rows.append({"ticker": f"T{i % tickers}", "horizon_key": "4w", "direction": direction,
                         "entry_date": f"{year}-06-01", "outcome": "win" if win else "loss",
                         "r_multiple": 1.0 if win else -1.0, "risk_pct": 3.0})
    return rows


YEARS = (2013, 2014, 2015, 2016)


def test_admitted_horizons_follow_the_live_gate():
    assert mv.admitted_horizons("VWAP", "bullish") == ("4w",)
    assert mv.admitted_horizons("MACD", "bullish") == ("3m", "4m", "7m", "8m", "9m")
    assert mv.admitted_horizons("Break & Retest", "bearish") == ("2m", "3m", "4m")
    assert mv.admitted_horizons("Fibonacci", "bullish") == tuple(HORIZONS)


def test_part_a_has_fifteen_cells_matching_the_live_gates():
    assert len(mv.PART_A) == 15 and len(set(mv.PART_A)) == 15
    for strategy, direction in mv.PART_A:
        assert direction in mv.admitted_directions(strategy)


def test_scope_and_params_restore(monkeypatch):
    monkeypatch.setattr(config, "STRUCTURAL_STOP_SCOPE", "", raising=False)
    with mv.scope("Fibonacci:bullish"):
        assert config.STRUCTURAL_STOP_SCOPE == "Fibonacci:bullish"
    assert config.STRUCTURAL_STOP_SCOPE == ""
    before = dict(DEFAULT_PARAMS["Bull Trap"])
    with mv.params("Bull Trap", {"k": 1, "earnings": "exit_before"}):
        assert DEFAULT_PARAMS["Bull Trap"] == {"k": 1, "earnings": "exit_before"}
    assert DEFAULT_PARAMS["Bull Trap"] == before


def test_evaluate_a_proceeds_only_when_the_in_arm_beats_the_baseline():
    arms = {"in": _rows(YEARS, 16, 0.625), "out": _rows(YEARS, 16, 0.5)}
    ok = mv.evaluate_a("Fibonacci", "bullish", arms, **FAST)
    assert ok["beats_baseline"] and ok["stage2"]["clears"] and ok["proceed_to_holdout"] and ok["tier"] == 1
    arms["out"] = _rows(YEARS, 16, 0.75)
    worse = mv.evaluate_a("Fibonacci", "bullish", arms, **FAST)
    assert not worse["beats_baseline"] and not worse["proceed_to_holdout"] and worse["tier"] is None


def test_cell_values_skip_the_earnings_axis_for_b3():
    assert mv.cell_values(mv.MECHANISMS["B1"], 2, "exit_before") == {"k": 2, "earnings": "exit_before"}
    assert mv.cell_values(mv.MECHANISMS["B3"], 0.08, "hold") == {"g": 0.08}


def test_stage0_closes_an_earnings_setting_below_thirty():
    counts = {mv.b_key(3, "hold"): {"total": 45}, mv.b_key(3, "exit_before"): {"total": 12}}
    assert mv.stage0_closures("B1", counts) == ["exit_before"]


def test_evaluate_b_picks_tier_then_expectancy_across_earnings(monkeypatch):
    def fake_stage1(by_value, direction, grid, **kw):
        exp = by_value["marker"]
        return {"winner": 2, "winner_tier": 2, "cells": {"2": {"stats": {"expectancy_r": exp}}}}
    monkeypatch.setattr(mv.funnel, "stage1", fake_stage1)
    monkeypatch.setattr(mv.funnel, "stage2", lambda *a, **k: {"verdict": {"clears": True}})
    # measure_v104 imported cell_key by name, so patch ITS binding (b_key uses it too).
    monkeypatch.setattr(mv, "cell_key", lambda v: "marker" if v == 1 else str(v))
    rows = {mv.b_key(v, e): (0.1 if e == "hold" else 0.3) for v in (1, 2, 3) for e in ("hold", "exit_before")}
    result = mv.evaluate_b("B1", rows, closed=(), **FAST)
    assert result["validation_cell"] == {"value": 2, "earnings": "exit_before", "tier": 2}


def test_verdict_seals_a_thin_holdout_with_n_only():
    sealed = mv.verdict(_rows((2026,), 10, 0.9), None, tier=1, **FAST)
    assert sealed == {"status": "sealed-thin", "n": 10}


def test_verdict_part_a_needs_the_baseline_clause():
    rows_in = _rows((2026,), 20, 0.6)
    passes = mv.verdict(rows_in, _rows((2026,), 20, 0.5), tier=1, **FAST)
    fails = mv.verdict(rows_in, _rows((2026,), 20, 0.8), tier=1, **FAST)
    assert passes["passes"] and passes["clauses"]["beats_baseline"]
    assert not fails["passes"] and not fails["clauses"]["beats_baseline"]


@pytest.fixture
def results(tmp_path, monkeypatch):
    monkeypatch.setattr(mv, "RESULTS", tmp_path)
    monkeypatch.setattr(mv, "HOLDOUT_END", "2026-09-24")
    return tmp_path


def _prior(results, name, status):
    (results / name).write_text(json.dumps({"status": status}), encoding="utf-8")


def test_holdout_first_shot_is_allowed(results):
    mv.check_shot_allowed("b-b1", results / "2026-09-30-v104-holdout-b-b1.json")


def test_holdout_refuses_a_spent_shot_under_any_date(results):
    _prior(results, "2026-09-01-v104-holdout-b-b1.json", "scored")
    with pytest.raises(SystemExit):
        mv.check_shot_allowed("b-b1", results / "2026-12-31-v104-holdout-b-b1.json")


def test_holdout_refuses_the_thin_retry_before_twelve_months(results):
    _prior(results, "2026-09-01-v104-holdout-b-b1.json", "sealed-thin")
    with pytest.raises(SystemExit):
        mv.check_shot_allowed("b-b1", results / "2026-10-01-v104-holdout-b-b1.json")


def test_holdout_allows_exactly_one_thin_retry_after_twelve_months(results, monkeypatch):
    _prior(results, "2026-09-01-v104-holdout-b-b1.json", "sealed-thin")
    monkeypatch.setattr(mv, "HOLDOUT_END", "2026-12-31")
    mv.check_shot_allowed("b-b1", results / "2027-01-05-v104-holdout-b-b1.json")
    _prior(results, "2027-01-05-v104-holdout-b-b1.json", "sealed-thin")
    with pytest.raises(SystemExit):
        mv.check_shot_allowed("b-b1", results / "2027-02-01-v104-holdout-b-b1.json")


def test_holdout_refuses_an_existing_output(results):
    out = results / "2026-09-30-v104-holdout-b-b1.json"
    out.write_text("{}", encoding="utf-8")
    with pytest.raises(SystemExit):
        mv.check_shot_allowed("b-b1", out)


def test_holdout_window_refuses_until_frozen(monkeypatch):
    monkeypatch.setattr(mv, "HOLDOUT_END", None)
    with pytest.raises(SystemExit):
        mv.holdout_window()


def test_trade_rows_filters_direction_window_and_applies_the_laggard_rule(monkeypatch):
    trade = lambda d, date: SimpleNamespace(direction=d, entry_date=date, outcome="win", r_multiple=1.0,
                                            entry=100.0, stop_loss=97.0)
    summary = SimpleNamespace(trades=[trade("bearish", "2015-01-05"), trade("bullish", "2015-01-06"),
                                      trade("bearish", "2026-02-01")])
    calls = []
    monkeypatch.setattr(mv, "window_trades", lambda s, a, b: [t for t in s.trades if a <= t.entry_date <= b])
    monkeypatch.setattr(mv, "apply_laggard_rule", lambda raw: calls.append(len(raw)) or raw)
    rows = mv.trade_rows("Bull Trap", {"AAA": None}, {}, "bearish", mv.TRAIN, ("2w",),
                         run_fn=lambda *a, **k: summary)
    assert [r["entry_date"] for r in rows] == ["2015-01-05"] and calls == [1]
    assert rows[0]["risk_pct"] == pytest.approx(3.0)


def test_emit_refuses_a_row_missing_an_admitted_direction(tmp_path):
    payload = {"status": "scored", "passes": True, "strategy": "Break & Retest", "direction": "bullish",
               "tier": 1, "rows": _rows((2026,), 20, 0.6)}
    path = tmp_path / "h.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    args = SimpleNamespace(holdout_json=[str(path)], registry=str(tmp_path / "reg.json"), run_date="2026-10-01")
    with pytest.raises(SystemExit):
        mv._cmd_emit(args)

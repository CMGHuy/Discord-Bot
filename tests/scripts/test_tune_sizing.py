"""tune_sizing.py -- the plan v8 V17 sizing grid.

The run itself is hours long, so what is pinned here is everything that
decides *how a config is scored and selected*: the horizon-reuse correction
(V16/V49), the pre-registered constraint set (V6 Step 3), and the fact that
the grid restores every module-level knob it moves -- those knobs are shared
with the live bot's own code path.
"""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import tune_sizing as ts  # noqa: E402


def _trade(date, entry, outcome, r, direction="bullish"):
    return SimpleNamespace(entry_date=date, entry=entry, direction=direction,
                           outcome=outcome, r_multiple=r)


def test_grid_floor_axis_never_goes_below_the_pre_registered_constraint():
    # V6 Step 3 constrains "every win >= MIN_TARGET_PCT (2.5%)", so a lower
    # floor is disqualified by construction and must not be gridded.
    assert min(ts.GRID["min_target_pct"]) >= 2.5


def test_independent_n_is_the_summed_n_when_horizons_disagree():
    trades = [_trade("2020-01-02", 10.0, "win", 1.0),
              _trade("2020-02-02", 11.0, "loss", -1.0)]
    by_hz = {"2w": {("2020-01-02", 10.0, "bullish")},
             "4w": {("2020-02-02", 11.0, "bullish")}}
    s = ts.score(trades, by_hz)
    assert s["n_eval"] == 2
    assert s["horizon_overcount"] == 1.0
    assert s["n_independent"] == 2


def test_reused_signals_deflate_n_and_the_wilson_bound():
    """The V16 failure mode: the same signal counted once per horizon."""
    sig = ("2020-01-02", 10.0, "bullish")
    trades = [_trade("2020-01-02", 10.0, "win", 1.0) for _ in range(10)]
    by_hz = {hk: {sig} for hk in ("2w", "4w", "2m", "3m", "4m",
                                  "5m", "6m", "7m", "8m", "9m")}
    s = ts.score(trades, by_hz)
    assert s["n_eval"] == 10
    assert s["n_distinct_signals"] == 1
    assert s["horizon_overcount"] == 10.0
    assert s["n_independent"] == 1
    # 10/10 wins would read as a very high bound on the summed sample; on the
    # one trade it really is, it must not.
    assert s["win_rate"] == 100.0
    assert s["wilson_lb"] < 30.0


def test_partial_reuse_below_the_flag_ratio_is_left_alone():
    # 1.33x -- under V49's 1.5 threshold, so N is not deflated.
    shared = ("2020-01-02", 10.0, "bullish")
    by_hz = {"2w": {shared, ("2020-03-02", 12.0, "bullish")},
             "4w": {shared, ("2020-04-02", 13.0, "bullish")}}
    trades = [_trade("2020-01-02", 10.0, "win", 1.0) for _ in range(4)]
    s = ts.score(trades, by_hz)
    assert s["horizon_overcount"] == pytest.approx(1.33, abs=0.01)
    assert s["n_independent"] == s["n_eval"] == 4


def test_excluded_share_counts_scratches_and_timeouts_against_all_closed():
    trades = [_trade("2020-01-02", 10.0, "win", 1.0),
              _trade("2020-01-03", 10.0, "scratch", 0.0),
              _trade("2020-01-04", 10.0, "timeout", 0.1),
              _trade("2020-01-05", 10.0, "loss", -1.0)]
    s = ts.score(trades, {"2w": {("2020-01-02", 10.0, "bullish")}})
    assert s["n_eval"] == 2                    # wins+losses only
    assert s["excluded_share"] == pytest.approx(0.5)
    # expectancy is over ALL closed trades, not just the evaluated ones
    assert s["expectancy_r"] == pytest.approx(0.025)


@pytest.mark.parametrize("stats,expected", [
    ({"n_independent": 30, "expectancy_r": 0.01, "excluded_share": 0.5}, True),
    ({"n_independent": 29, "expectancy_r": 0.5, "excluded_share": 0.1}, False),
    ({"n_independent": 500, "expectancy_r": 0.0, "excluded_share": 0.1}, False),
    ({"n_independent": 500, "expectancy_r": -0.01, "excluded_share": 0.1}, False),
    ({"n_independent": 500, "expectancy_r": 0.5, "excluded_share": 0.51}, False),
    ({"n_independent": 500, "expectancy_r": None, "excluded_share": 0.1}, False),
])
def test_qualifies_is_exactly_the_pre_registered_constraint_set(stats, expected):
    assert ts.qualifies(stats) is expected


def test_qualifies_gates_on_independent_n_not_summed_n():
    """The whole point of V49's instrumentation: a config whose 300 trades are
    ~10 real ones must not clear the N>=30 sample gate."""
    assert ts.qualifies({"n_independent": 10, "n_eval": 300,
                         "expectancy_r": 0.2, "excluded_share": 0.1}) is False


def test_apply_config_moves_every_axis():
    from swingbot import config
    from swingbot.core.strategy_types import HORIZONS, STRATEGY_RR_OVERRIDE
    import swingbot.core.plan_engine as pe

    before = (config.MIN_TARGET_PCT, STRATEGY_RR_OVERRIDE.get("MACD"),
              HORIZONS["2w"]["atr_stop_multiple"], pe.EXIT_V2_PARAMS.get("MACD"))
    try:
        ts.apply_config("MACD", {"min_target_pct": 4.0, "rr": 1.75,
                                 "atr_stop_multiple": 1.25, "trail_atr_mult": 3.5},
                        {"tp2": True})
        assert config.MIN_TARGET_PCT == 4.0
        assert config.TARGET_FLOOR_ENABLED is True
        assert STRATEGY_RR_OVERRIDE["MACD"] == 1.75
        # every horizon, not just the one that happens to be tested
        assert {h["atr_stop_multiple"] for h in HORIZONS.values()} == {1.25}
        assert pe.EXIT_V2_PARAMS["MACD"] == {"tp2": True, "trail_atr_mult": 3.5}
    finally:
        config.MIN_TARGET_PCT = before[0]
        if before[1] is None:
            STRATEGY_RR_OVERRIDE.pop("MACD", None)
        else:
            STRATEGY_RR_OVERRIDE["MACD"] = before[1]
        for h in HORIZONS.values():
            h["atr_stop_multiple"] = before[2]
        if before[3] is None:
            pe.EXIT_V2_PARAMS.pop("MACD", None)
        else:
            pe.EXIT_V2_PARAMS["MACD"] = before[3]


def test_apply_config_keeps_the_adopted_tp2_choice():
    """tp2 is not a V17 axis -- Task 30 chose it per strategy and
    tune_exit_v2.py owns re-opening it."""
    import swingbot.core.plan_engine as pe
    before = pe.EXIT_V2_PARAMS.get("RSI")
    try:
        ts.apply_config("RSI", {"min_target_pct": 2.5, "rr": 0.35,
                                "atr_stop_multiple": 2.0, "trail_atr_mult": 2.0},
                        {"trail_atr_mult": 2.0, "tp2": False})
        assert pe.EXIT_V2_PARAMS["RSI"]["tp2"] is False
    finally:
        if before is None:
            pe.EXIT_V2_PARAMS.pop("RSI", None)
        else:
            pe.EXIT_V2_PARAMS["RSI"] = before

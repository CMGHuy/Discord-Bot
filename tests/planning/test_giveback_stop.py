"""v176: the give-back arithmetic, in one pure place shared by live and backtest."""
import pytest

from swingbot import config
from swingbot.core.planning import plan_engine
from swingbot.core.planning.exit_sim import (GIVEBACK_PCT_BOUNDS, giveback_level,
                                             giveback_stop, runner_giveback_pct,
                                             runner_stop_source, tighter_stop)


def test_long_giveback_is_pct_below_the_extreme():
    # The spec's worked example: long, best price 100, 5% -> 95.
    assert giveback_stop(100.0, 5.0, "bullish") == pytest.approx(95.0)


def test_short_giveback_is_pct_above_the_extreme():
    # RKLB short: best (lowest) price 49.94 -> 52.437.
    assert giveback_stop(49.94, 5.0, "bearish") == pytest.approx(52.437)


@pytest.mark.parametrize("pct", [0.0, -1.0, 100.0, 150.0])
def test_pct_outside_open_unit_interval_is_rejected(pct):
    with pytest.raises(ValueError):
        giveback_stop(100.0, pct, "bullish")


def test_pct_bounds_are_the_documented_range():
    assert GIVEBACK_PCT_BOUNDS == (0.5, 49.0)


@pytest.mark.parametrize("raw, expected", [(5.0, 5.0), (0.1, 0.5), (0.5, 0.5),
                                           (49.0, 49.0), (60.0, 49.0), (-3.0, 0.5)])
def test_runner_giveback_pct_clamps_the_config_value(monkeypatch, raw, expected):
    monkeypatch.setattr(config, "RUNNER_GIVEBACK_PCT", raw)
    assert runner_giveback_pct() == expected


def test_giveback_level_reads_the_flag_and_pct_at_call_time(monkeypatch):
    monkeypatch.setattr(config, "RUNNER_GIVEBACK_ENABLED", True)
    monkeypatch.setattr(config, "RUNNER_GIVEBACK_PCT", 10.0)
    assert giveback_level(200.0, "bullish") == pytest.approx(180.0)
    monkeypatch.setattr(config, "RUNNER_GIVEBACK_PCT", 5.0)
    assert giveback_level(200.0, "bullish") == pytest.approx(190.0)
    assert giveback_level(200.0, "bearish") == pytest.approx(210.0)


def test_giveback_level_is_none_without_an_extreme(monkeypatch):
    monkeypatch.setattr(config, "RUNNER_GIVEBACK_ENABLED", True)
    assert giveback_level(None, "bullish") is None


def test_giveback_level_is_none_with_the_flag_off(monkeypatch):
    monkeypatch.setattr(config, "RUNNER_GIVEBACK_ENABLED", False)
    assert giveback_level(200.0, "bullish") is None


@pytest.mark.parametrize("stop, other, is_bull, expected", [
    (106.0, 114.0, True, 114.0),     # long: the higher stop is tighter
    (115.0, 114.0, True, 115.0),     # long: never loosens
    (59.11, 52.437, False, 52.437),  # short: the lower stop is tighter
    (50.0, 52.437, False, 50.0),     # short: never loosens
    (106.0, None, True, 106.0),      # no give-back term
])
def test_tighter_stop(stop, other, is_bull, expected):
    assert tighter_stop(stop, other, is_bull) == expected


def test_runner_stop_source_names_the_term_that_set_the_stop():
    assert runner_stop_source(106.0, 106.0, 101.0) == "floor"
    assert runner_stop_source(114.0, 106.0, 114.0) == "giveback"
    assert runner_stop_source(115.0, 106.0, 114.0) == "trail"
    assert runner_stop_source(115.0, 106.0, None) == "trail"


def test_floor_wins_a_tie_with_the_giveback():
    # The reason label keys off the floor (tp1_runner_be); the source must agree.
    assert runner_stop_source(106.0, 106.0, 106.0) == "floor"


def test_helpers_are_re_exported_from_plan_engine():
    for name in ("giveback_stop", "runner_giveback_pct", "giveback_level",
                 "tighter_stop", "runner_stop_source"):
        assert name in plan_engine.__all__
        assert callable(getattr(plan_engine, name))

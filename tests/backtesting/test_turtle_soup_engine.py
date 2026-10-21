"""V180-7: StrategyEngine runs the masked Turtle Soup long only under TURTLE_SOUP_RESEARCH_MODE,
inside its ("bullish", "2w") research cell. Its rows are booked net of costs, every other row is
untouched, and each counted candidate leaves one event for the diagnostics.

The world (shared with V180-8): 40 flat bars with a 98.0 low ten bars before the signal; the signal
bar sweeps it (low 97.6) and closes back above (99.9); the next bar opens at the fill; three bars later
the high reaches the one resistance the level map holds (105.0)."""
from types import SimpleNamespace

import pytest

from swingbot import config
from swingbot.core.analytics import expectancy_attribution as ea
from swingbot.core.backtesting import backtest as bt
from swingbot.core.backtesting.acceptance import population_split
from swingbot.core.backtesting.arms import turtle_soup_research as tsr
from swingbot.core.backtesting.arms.strategy_engine import StrategyEngine
from swingbot.core.market import levels as levels_mod
from swingbot.core.market.indicators import atr
from swingbot.core.market.levels import Level
from swingbot.core.market.strategy_types import COMPRESSION_SHORT, STRATEGY_GATES, TURTLE_SOUP
from swingbot.core.planning import turtle_soup_plan
from swingbot.scan_params import ScanParams
from tests.backtesting.screen.helpers import random_walk
from tests.helpers import make_ohlcv

SIGNAL_POS = 40
TARGET = 105.0
PILOT = ("2018-06-01", "2020-12-31")
FLAT = (100.0, 100.5, 99.5, 100.0)
WIDE = ("2009-01-01", "2030-12-31")


def path(fill_open=100.0):
    rows = [FLAT] * SIGNAL_POS
    rows[30] = (100.0, 100.5, 98.0, 100.0)                  # L = 98.0, ten bars before the signal
    rows.append((99.8, 100.2, 97.6, 99.9))                  # the sweep: low < L, close > L
    rows.append((fill_open, max(fill_open, 100.5), min(fill_open, 99.6), 100.2))   # the fill bar
    rows += [(100.2, 101.2, 100.0, 101.0), (101.0, 102.7, 100.8, 102.5),
             (102.5, 105.2, 102.3, 104.8)]                  # the target prints on the fourth session
    rows += [(104.8, 105.0, 104.3, 104.6)] * 25
    return make_ohlcv(rows, start="2019-01-02")


FULL_PATH = path()
SIGNAL_DAY = FULL_PATH.index[SIGNAL_POS].date().isoformat()
FILL_DAY = FULL_PATH.index[SIGNAL_POS + 1].date().isoformat()


def pin_world(monkeypatch, resistances=(TARGET,)):
    """Pin the live-state flags off and the level map to the given resistances."""
    for name in ("LEVEL_LIFECYCLE_STOPS_ENABLED", "STALL_EXIT_ENABLED",
                 "REGIME_GATES_ENABLED", "DATA_DRIVEN_STOPS_ENABLED"):
        monkeypatch.setattr(config, name, False, raising=False)

    def fake(*args, **kwargs):
        return [], [Level(price=p, sources=["Swing high", "Pivot high"]) for p in resistances]

    monkeypatch.setattr(levels_mod, "build_level_map", fake)
    monkeypatch.setattr(turtle_soup_plan, "build_level_map", fake, raising=False)


@pytest.fixture(autouse=True)
def pins(monkeypatch):
    pin_world(monkeypatch)


@pytest.fixture
def structural(monkeypatch):
    monkeypatch.setattr(config, tsr.RESEARCH_KNOB, "structural")


def _run(engine, frame=FULL_PATH, horizons=("2w",), window=PILOT, ticker="TS1"):
    return list(engine.run_ticker(ticker, frame, horizons, window, ScanParams.from_config()))


def _turtle(rows):
    return [row for row in rows if row.strategy == TURTLE_SOUP]


def test_the_world_fires_exactly_one_signal():
    from swingbot.core.market.turtle_soup import turtle_soup_signal
    assert turtle_soup_signal(FULL_PATH).to_numpy().nonzero()[0].tolist() == [SIGNAL_POS]


def test_research_constants():
    assert tsr.RESEARCH_KNOB == "TURTLE_SOUP_RESEARCH_MODE"
    assert tsr.RESEARCH_MODES == ("off", "structural") and tsr.HORIZON == "2w"
    assert tsr.RESEARCH_CELL == {"directions": (), "cells": {("bullish", "2w")}}
    assert tsr.CANCEL_STATUS == {"open_through_stop": "cancelled_open_through_stop",
                                 "risk_cap": "cancelled_risk_cap_fill"}
    assert tsr.research_mode() == "off"


def test_knob_off_runs_no_turtle_soup():
    engine = StrategyEngine(strategies=("RSI",))
    assert TURTLE_SOUP not in engine._run_strategies()
    assert _turtle(_run(engine)) == [] and engine.turtle_soup_events == []


def test_structural_adds_one_net_of_cost_row(structural):
    engine = StrategyEngine(strategies=("RSI",))
    assert engine._run_strategies() == ("RSI", TURTLE_SOUP)
    (trade,) = _turtle(_run(engine))
    assert (trade.entry_date, trade.horizon_key, trade.direction, trade.outcome) == \
        (SIGNAL_DAY, "2w", "bullish", "win")
    (event,) = engine.turtle_soup_events
    assert event["status"] == "trade" and event["ticker"] == "TS1"
    assert event["signal_date"] == SIGNAL_DAY and event["entry_date"] == FILL_DAY
    assert event["entry_price"] == 100.0 and event["tp1"] == TARGET
    assert event["exit_reason"] == "tp1" and event["hold_sessions"] == 4
    expected_stop = 97.6 - 0.25 * float(atr(FULL_PATH.iloc[:SIGNAL_POS + 1], 14).iloc[-1])
    assert event["stop_loss"] == pytest.approx(expected_stop)
    legs = [{"fraction": 1.0, "exit_price": TARGET}]
    assert event["r_net"] == pytest.approx(ea.net_r(100.0, event["stop_loss"], "bullish", legs))
    assert event["r_net"] < event["r_gross"]
    assert trade.r_multiple == event["r_net"]


def test_the_cell_opens_only_bullish_2w_and_is_restored(structural):
    engine = StrategyEngine(strategies=("RSI",))
    assert _turtle(_run(engine, horizons=("4w",))) == []
    _run(engine)
    assert STRATEGY_GATES[TURTLE_SOUP] == {"directions": ()}


def test_an_open_through_the_stop_is_a_cancel_event_not_a_row(structural):
    engine = StrategyEngine(strategies=(TURTLE_SOUP,))
    assert _run(engine, frame=path(fill_open=97.0)) == []
    assert engine.turtle_soup_events == [
        {"ticker": "TS1", "signal_date": SIGNAL_DAY, "status": "cancelled_open_through_stop"}]


def test_a_stop_beyond_the_cap_at_the_fill_is_a_cancel_event(structural):
    engine = StrategyEngine(strategies=(TURTLE_SOUP,))
    assert _run(engine, frame=path(fill_open=100.8)) == []      # stop ~97.31: 3.46% from 100.8
    assert [e["status"] for e in engine.turtle_soup_events] == ["cancelled_risk_cap_fill"]


@pytest.mark.parametrize("resistances", [(), (110.0,)])
def test_no_level_in_the_band_is_a_plan_none_event(structural, monkeypatch, resistances):
    pin_world(monkeypatch, resistances)
    engine = StrategyEngine(strategies=(TURTLE_SOUP,))
    assert _run(engine) == []
    assert engine.turtle_soup_events == [
        {"ticker": "TS1", "signal_date": SIGNAL_DAY, "status": "plan_none"}]


def test_warm_up_signals_leave_no_event(structural):
    engine = StrategyEngine(strategies=(TURTLE_SOUP,))
    assert _run(engine, window=("2019-03-15", "2020-12-31")) == []
    assert engine.turtle_soup_events == []


def test_a_turtle_soup_only_engine_yields_the_same_rows(structural):
    full = _turtle(_run(StrategyEngine(strategies=("RSI", "MACD"))))
    alone = StrategyEngine(strategies=(TURTLE_SOUP,))
    assert alone._run_strategies() == (TURTLE_SOUP,)
    assert _run(alone) == full and len(full) == 1


def test_baseline_rows_are_a_subset_of_the_component(monkeypatch):
    frames = {"TS1": FULL_PATH, "RW1": random_walk(400, seed=3), "RW2": random_walk(400, seed=11)}
    strategies = ("RSI", "MACD", "Support/Resistance")
    horizons = ("2w", "4w")

    def arm(mode):
        monkeypatch.setattr(config, tsr.RESEARCH_KNOB, mode)
        engine = StrategyEngine(strategies=strategies)
        return [row for ticker, frame in frames.items()
                for row in _run(engine, frame=frame, horizons=horizons, window=WIDE, ticker=ticker)]

    baseline, component = arm("off"), arm("structural")
    split = population_split(baseline, component)
    assert split["removed"] == [] and split["changed"] == []
    assert split["added"] and all(row.strategy == TURTLE_SOUP for row in split["added"])
    assert [row for row in component if row.strategy != TURTLE_SOUP] == baseline


def test_net_r_is_the_screen_cost_model(monkeypatch):
    monkeypatch.setattr(config, "SLIPPAGE_BPS", 5.0, raising=False)
    monkeypatch.setattr(config, "COMMISSION_PER_TRADE", 1.0, raising=False)
    monkeypatch.setattr(config, "COMMISSION_RISK_BASIS", 100.0, raising=False)
    plan = SimpleNamespace(stop_loss=98.0, direction="bullish")
    result = SimpleNamespace(entry_price=100.0, legs=[{"fraction": 1.0, "exit_price": 104.0}])
    # entry 100.05, exit 103.948, risk 2.05: 3.898 / 2.05 - 2 * 1 / 100
    assert tsr.net_r(plan, result) == pytest.approx(1.8814634, abs=1e-6)


def test_cancel_and_plan_none_events():
    assert tsr.cancel_event("T", "2019-01-02", "risk_cap") == \
        {"ticker": "T", "signal_date": "2019-01-02", "status": "cancelled_risk_cap_fill"}
    assert tsr.cancel_event("T", "2019-01-02", None)["status"] == "not_triggered"
    assert tsr.plan_none_event("T", "2019-01-02") == \
        {"ticker": "T", "signal_date": "2019-01-02", "status": "plan_none"}


def test_the_signal_close_backtest_refuses_turtle_soup():
    with pytest.raises(ValueError, match="Turtle Soup"):
        bt._refuse_compression(TURTLE_SOUP)
    with pytest.raises(ValueError, match="CompressionResearchContext"):
        bt._refuse_compression(COMPRESSION_SHORT)
    assert bt._refuse_compression("RSI") is None

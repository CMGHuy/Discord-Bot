"""V192-5: with MARKET_ENTRY_NEXT_OPEN on, both builders leave market plans PENDING
with no entry price and the next-open marker; GAP_RECLAIM_ATR > 0 adds a_t and X
from bars through the creating bar. Knob off is pinned by the V192-1 plan golden."""
import dataclasses
import types

import pytest

from swingbot import config
from swingbot.core.backtesting.backtest import ALL_STRATEGIES
from swingbot.core.market.strategy_types import TURTLE_SOUP
from swingbot.core.planning import gap_reclaim as gr
from swingbot.core.planning.builders import build_confluence_plan, build_strategy_plan
from swingbot.core.planning.plan_types import PlanStatus, plan_to_dict
from tests.backtesting.test_v74_fixture import load_v74_fixture
from tests.helpers import make_ohlcv

V192_KEYS = {"reclaim_atr", "reclaim_level", "reclaim_session", "waits_next_open"}
#: dict keys the knob is allowed to change on a market plan
WAITING_KEYS = {"plan_id", "status", "status_history", "entry_price"} | V192_KEYS


@pytest.fixture
def knobs(monkeypatch):
    def set_(next_open, g):
        monkeypatch.setattr(config, "MARKET_ENTRY_NEXT_OPEN", next_open)
        monkeypatch.setattr(config, "GAP_RECLAIM_ATR", g)
    return set_


def _wavy(entry, n=60):
    """Bars whose ATR14 is real (H - L = 10% of the price) and flat closes at `entry`.
    The 5% half-range keeps the 104 / 96 targets inside the 20-bar range, so
    scenario_is_breakout leaves the plan a market plan, not a stop entry."""
    return make_ohlcv([entry] * n, spread=0.05)


def _confluence(direction="bullish", entry=100.0, stop=98.4, target=104.0, df=None):
    if direction == "bearish":
        stop, target = 2 * entry - stop, 2 * entry - target
    scenario = types.SimpleNamespace(direction=direction, entry=entry, stop_loss=stop,
                                     take_profit=target, target_sources=["Rolling S/R"],
                                     stop_sources=["Rolling S/R"])
    return build_confluence_plan(scenario, df if df is not None else _wavy(entry), ticker="XYZ",
                                 horizon_key="4w", primary_strategy="S/R Confluence")


@pytest.mark.parametrize("direction", ["bullish", "bearish"])
def test_knob_off_confluence_market_plan_is_active_as_today(knobs, direction):
    knobs(False, 0.0)
    plan = _confluence(direction)
    assert plan.entry_type == "market" and plan.status == PlanStatus.ACTIVE
    assert plan.entry_price == plan.trigger_price == 100.0
    assert [h["reason"] for h in plan.status_history] == ["market_entry"]
    assert not V192_KEYS & set(plan_to_dict(plan))


@pytest.mark.parametrize("direction", ["bullish", "bearish"])
def test_next_open_alone_builds_a_waiting_plan_without_a_veto(knobs, direction):
    knobs(True, 0.0)
    plan = _confluence(direction)
    assert plan.entry_type == "market" and plan.status == PlanStatus.PENDING
    assert plan.entry_price is None and plan.trigger_price == 100.0
    assert plan.waits_next_open is True and plan.status_history == []
    assert plan.reclaim_atr is None and plan.reclaim_level is None
    assert gr.waits_for_open(plan)


@pytest.mark.parametrize("direction, sign", [("bullish", -1), ("bearish", 1)])
def test_gap_knob_stamps_atr_and_level_from_the_creating_bar(knobs, direction, sign):
    knobs(True, 0.25)
    df = _wavy(100.0)
    plan = _confluence(direction, df=df)
    a_t = gr.atr_at(df, len(df) - 1)
    assert plan.reclaim_atr == a_t
    assert plan.reclaim_level == gr.reclaim_level_for(100.0, a_t, 0.25, direction)
    assert (plan.reclaim_level - 100.0) * sign > 0


def test_unusable_atr_leaves_the_plan_waiting_without_a_veto(knobs, monkeypatch):
    knobs(True, 0.25)
    monkeypatch.setattr(gr, "atr_at", lambda df, index: None)
    plan = _confluence()
    assert plan.waits_next_open is True and plan.status == PlanStatus.PENDING
    assert plan.reclaim_atr is None and plan.reclaim_level is None


def test_the_knob_moves_nothing_but_the_entry_state(knobs):
    knobs(False, 0.0)
    off = plan_to_dict(_confluence())
    knobs(True, 0.25)
    on = plan_to_dict(_confluence())
    assert {k: v for k, v in off.items() if k not in WAITING_KEYS} == {
        k: v for k, v in on.items() if k not in WAITING_KEYS}


def _strategy_pairs(limit=8):
    """(index, strategy, direction, knob-off plan, knob-on plan) over the v74 AAPL frame."""
    df = load_v74_fixture()["AAPL"]
    strategies = tuple(ALL_STRATEGIES) + (() if TURTLE_SOUP in ALL_STRATEGIES else (TURTLE_SOUP,))
    pairs = []
    for index in range(120, len(df), 11):
        for strategy in strategies:
            for direction in ("bullish", "bearish"):
                with pytest.MonkeyPatch.context() as mp:
                    mp.setattr(config, "MARKET_ENTRY_NEXT_OPEN", False)
                    mp.setattr(config, "GAP_RECLAIM_ATR", 0.0)
                    off = build_strategy_plan(df, index, ticker="AAPL", strategy=strategy,
                                              horizon_key="4w", direction=direction)
                    mp.setattr(config, "MARKET_ENTRY_NEXT_OPEN", True)
                    mp.setattr(config, "GAP_RECLAIM_ATR", 0.25)
                    on = build_strategy_plan(df, index, ticker="AAPL", strategy=strategy,
                                             horizon_key="4w", direction=direction)
                if off is not None:
                    pairs.append((index, strategy, direction, off, on))
            if sum(1 for p in pairs if p[3].entry_type == "market") >= limit:
                return df, pairs
    return df, pairs


@pytest.mark.slow
def test_strategy_builder_waits_only_for_market_plans():
    df, pairs = _strategy_pairs()
    market = [p for p in pairs if p[3].entry_type == "market" and p[1] != TURTLE_SOUP]
    assert len(market) >= 5, "the sweep must reach real market plans"
    for index, strategy, direction, off, on in pairs:
        d_off, d_on = plan_to_dict(off), plan_to_dict(on)
        if off.entry_type == "market" and strategy != TURTLE_SOUP:
            assert on.status == PlanStatus.PENDING and on.entry_price is None
            assert on.waits_next_open is True and on.trigger_price == off.trigger_price
            assert on.reclaim_atr == gr.atr_at(df, index)
            assert {k: v for k, v in d_off.items() if k not in WAITING_KEYS} == {
                k: v for k, v in d_on.items() if k not in WAITING_KEYS}
        else:                    # stop-entry, limit and Turtle Soup: untouched
            d_off.pop("plan_id"), d_on.pop("plan_id")
            assert d_off == d_on, (strategy, direction, index)


@pytest.mark.slow
def test_strategy_stamp_ignores_bars_after_the_creating_bar(knobs):
    """NO-LOOKAHEAD: the builder's a_t and X are unchanged when every bar after t moves."""
    knobs(True, 0.25)
    df, pairs = _strategy_pairs(limit=1)
    index, strategy, direction, _off, on = next(p for p in pairs if p[4].waits_next_open)
    moved = df.copy()
    moved.iloc[index + 1:, moved.columns.get_loc("High")] *= 1.5
    moved.iloc[index + 1:, moved.columns.get_loc("Low")] *= 0.5
    again = build_strategy_plan(moved, index, ticker="AAPL", strategy=strategy,
                                horizon_key="4w", direction=direction)
    assert (again.reclaim_atr, again.reclaim_level) == (on.reclaim_atr, on.reclaim_level)

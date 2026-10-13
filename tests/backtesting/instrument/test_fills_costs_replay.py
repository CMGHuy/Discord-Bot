"""v157 FC6: the v2 replay walks every plan through the instrument's fills and
costs. A v2 trade row's entry_date is its fill bar and its signal_date the
signal bar (the cross-plan contract with v158); a v1 row carries
signal_date == entry_date."""
import dataclasses

import pandas as pd
import pytest

from swingbot.core.backtesting import backtest as bt
from swingbot.core.backtesting.instrument.contract import ZERO_COSTS, resolve
from swingbot.core.planning.exit_sim import simulate_exit
from swingbot.core.planning.plan_engine import PlanStatus, TradePlanV2
from tests.backtesting.test_pullback_dryup_witness import pin_code_defaults
from tests.fixtures.ohlcv_parity import load_ohlcv
from tests.helpers import make_ohlcv

TICKER, STRATEGY, HORIZON = "DOCU", "RSI", "4w"
V2 = resolve("v2")
FREE = dataclasses.replace(V2, cost_model=ZERO_COSTS)
V2_EXIT = {"exit_model": "v2", "scale_out": True}
SIGNAL = (100.0, 100.5, 99.5, 100.0)
HOLD = (101.0, 101.5, 100.5, 101.0)
UP = (101.0, 102.5, 100.5, 102.0)


@pytest.fixture(autouse=True)
def _pinned(monkeypatch):
    pin_code_defaults(monkeypatch)


@pytest.fixture
def frame():
    return load_ohlcv(TICKER)


def _plan(**kw):
    base = dict(
        plan_id="p1", ticker="T", created_at="2024-01-02", source="strategy",
        strategy="Probe", horizon_key="4w", direction="bullish",
        entry_type="market", trigger_price=100.0, entry_price=None, expiry_bars=3,
        stop_loss=95.0, tp1=110.0, tp1_fraction=1.0, tp2=None,
        breakeven_trigger_fraction=0.5, trail_atr_mult=1.0,
        quality_score=0, quality_breakdown=[],
        badge="WEAK", badge_stats={}, status=PlanStatus.PENDING, status_history=[],
    )
    base.update(kw)
    return TradePlanV2(**base)


def _day(df, k):
    return str(df.index[k].date())


def _row(**kw):
    base = dict(entry_date="2021-03-01", exit_date="2021-03-05", direction="bullish",
                entry=100.0, stop_loss=95.0, take_profit=110.0, outcome="win",
                exit_price=110.0, return_pct=10.0, r_multiple=2.0, holding_days=4)
    base.update(kw)
    return bt.BacktestTrade(**base)


# --- the field ----------------------------------------------------------------

def test_signal_date_defaults_to_the_entry_date():
    assert _row().signal_date == "2021-03-01"


def test_an_explicit_signal_date_is_kept():
    assert _row(signal_date="2021-02-26").signal_date == "2021-02-26"


def test_signal_date_is_the_last_field_so_positional_rows_are_unchanged():
    names = [f.name for f in dataclasses.fields(bt.BacktestTrade)]
    assert names[-1] == "signal_date"
    assert names[:-1] == ["entry_date", "exit_date", "direction", "entry", "stop_loss",
                          "take_profit", "outcome", "exit_price", "return_pct",
                          "r_multiple", "holding_days", "runner_outcome", "context"]


# --- _live_trade: one row from one walked plan ---------------------------------

@pytest.mark.parametrize("instrument", [FREE, V2], ids=["free", "costed"])
def test_live_trade_dates_and_entry_come_from_the_fill(monkeypatch, instrument):
    seen = {}

    def context(window, **kwargs):
        seen.update(rows=len(window), **kwargs)
        return {"probe": True}

    monkeypatch.setattr(bt, "entry_context", context)
    df = make_ohlcv([SIGNAL, HOLD, HOLD, UP, HOLD])
    plan = _plan()
    res = simulate_exit(df, 0, plan, scale_out=True, max_holding_days=2, instrument=instrument)
    assert (res.entry_index, res.entry_price) == (1, 101.0)   # next open, raw
    trade = bt._live_trade(df, 0, plan, res, "4w", None)
    assert (trade.signal_date, trade.entry_date) == (_day(df, 0), _day(df, 1))
    assert trade.exit_date == _day(df, res.exit_index)
    assert trade.entry == 101.0                               # costs never move the price
    assert trade.holding_days == res.exit_index - 1           # counted from the fill bar
    assert trade.r_multiple == round(res.r_total, 3)
    assert trade.return_pct == round(res.r_total * (6.0 / 101.0) * 100, 3)
    assert trade.exit_price == round(res.legs[-1]["exit_price"], 4)
    assert (trade.stop_loss, trade.take_profit) == (95.0, 110.0)
    # The context is the signal bar's: the plan is known at the signal close.
    assert seen["rows"] == 1 and seen["entry"] == 101.0
    assert trade.context == {"probe": True}


# --- run_backtest under v2, end to end on a synthetic tape ----------------------

def test_v2_replay_row_carries_the_fill_bar_and_the_signal_bar(monkeypatch):
    signal = bt.MIN_BARS["2w"]
    df = make_ohlcv([100.0] * signal + [SIGNAL, HOLD, HOLD, UP] + [100.0] * 6)

    def one_signal(frame, strategy, horizon_key):
        bull = pd.Series(False, index=frame.index)
        bull.iloc[signal] = True
        return bull, pd.Series(False, index=frame.index)

    monkeypatch.setattr(bt, "_signal_masks", one_signal)
    monkeypatch.setattr(bt, "_live_plan_at", lambda frame, i, **kw: _plan(horizon_key="2w"))
    monkeypatch.setattr(bt, "entry_context", lambda window, **kw: {})
    summary = bt.run_backtest("T", df, STRATEGY, "2w", **V2_EXIT, instrument=FREE)
    [trade] = summary.trades
    assert (trade.signal_date, trade.entry_date) == (_day(df, signal), _day(df, signal + 1))
    assert trade.entry == 101.0
    exit_index = df.index.get_loc(pd.Timestamp(trade.exit_date))
    assert trade.holding_days == exit_index - (signal + 1)


# --- run_backtest under v2 on the frozen DOCU tape -------------------------------

def test_v2_replay_hands_the_instrument_to_simulate_exit(monkeypatch, frame):
    seen = []
    real = bt.simulate_exit

    def spy(df, index, plan, **kwargs):
        seen.append(kwargs.get("instrument"))
        return real(df, index, plan, **kwargs)

    monkeypatch.setattr(bt, "simulate_exit", spy)
    bt.run_backtest(TICKER, frame, STRATEGY, HORIZON, **V2_EXIT, instrument=V2)
    assert seen and all(spec is V2 for spec in seen)


def test_v2_rows_are_the_simulators_fills_net_of_costs(frame):
    summary = bt.run_backtest(TICKER, frame, STRATEGY, HORIZON, **V2_EXIT, instrument=V2)
    index_of = {_day(frame, k): k for k in range(len(frame))}
    assert summary.trades, "fixture case must trade under v2 or this proves nothing"
    for trade in summary.trades:
        i = index_of[trade.signal_date]
        plan = bt._live_plan_at(frame, i, ticker=TICKER, strategy=STRATEGY,
                                horizon_key=HORIZON, direction=trade.direction)
        res = simulate_exit(frame, i, plan, scale_out=True, instrument=V2)
        assert trade.entry_date == _day(frame, res.entry_index)
        assert trade.signal_date < trade.entry_date    # v2 never fills on the signal bar
        assert trade.entry == round(res.entry_price, 4)
        assert trade.r_multiple == round(res.r_total, 3)
        assert trade.holding_days == res.exit_index - res.entry_index


def test_costs_move_r_and_nothing_else(frame):
    costed = bt.run_backtest(TICKER, frame, STRATEGY, HORIZON, **V2_EXIT, instrument=V2).trades
    free = bt.run_backtest(TICKER, frame, STRATEGY, HORIZON, **V2_EXIT, instrument=FREE).trades
    assert costed

    def events(trades):
        return [(t.signal_date, t.entry_date, t.exit_date, t.outcome, t.entry, t.exit_price)
                for t in trades]

    assert events(costed) == events(free)              # labels follow the event
    assert [t.r_multiple for t in costed] != [t.r_multiple for t in free]
    for c, f in zip(costed, free):
        if c.outcome == "win":
            assert c.r_multiple < f.r_multiple         # slippage never helps a winner


# --- v1 rows ---------------------------------------------------------------------

@pytest.mark.parametrize("instrument", [None, resolve("v1")], ids=["default", "explicit_v1"])
def test_v1_rows_carry_signal_date_equal_to_entry_date(frame, instrument):
    summary = bt.run_backtest(TICKER, frame, STRATEGY, HORIZON, exit_model="v2",
                              scale_out=True, tp2_mode="levels", instrument=instrument)
    assert summary.trades
    assert all(t.signal_date == t.entry_date for t in summary.trades)

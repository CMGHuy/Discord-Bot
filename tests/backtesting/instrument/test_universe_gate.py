"""v158 WC5: causal point-in-time universe gate and the watchlist-slice verdict
(v136 spec section 1 "Universe"; partner decision 1)."""
import math
from types import SimpleNamespace

import pandas as pd
import pytest

from swingbot.core.backtesting.instrument import universe_gate as ug
from swingbot.core.backtesting.instrument.contract import (V2_LIQUIDITY_FLOOR, LiquidityFloor,
                                                           resolve)
from swingbot.core.marketdata.universe import liquidity_reason

FLOOR = LiquidityFloor(min_avg_dollar_vol=20_000_000.0, min_price=5.0, lookback_bars=20)


def _frame(closes, volumes, start="2021-01-04"):
    index = pd.bdate_range(start, periods=len(closes))
    return pd.DataFrame({"Open": closes, "High": closes, "Low": closes,
                         "Close": closes, "Volume": volumes}, index=index)


def _day(df, i):
    return str(df.index[i].date())


def _trade(entry, signal=None):
    fields = {"entry_date": entry, "exit_date": None, "r_multiple": 1.0}
    if signal is not None:
        fields["signal_date"] = signal
    return SimpleNamespace(**fields)


# --- the floor is the contract's -------------------------------------------

def test_v2_floor_is_the_frozen_contract_floor_and_v1_has_none():
    assert resolve("v2").liquidity_floor == V2_LIQUIDITY_FLOOR == FLOOR
    assert resolve("v1").liquidity_floor is None


# --- signal_day: the v157 field, with the entry_date fallback ---------------

def test_signal_day_falls_back_to_entry_date_before_v157_lands():
    assert ug.signal_day(_trade("2021-03-02")) == "2021-03-02"


def test_signal_day_reads_signal_date_when_present():
    assert ug.signal_day(_trade("2021-03-02", signal="2021-03-01")) == "2021-03-01"


def test_signal_day_treats_a_none_signal_date_as_absent():
    assert ug.signal_day(_trade("2021-03-02", signal=None)) == "2021-03-02"
    trade = SimpleNamespace(entry_date="2021-03-02", signal_date=None)
    assert ug.signal_day(trade) == "2021-03-02"


def test_signal_day_normalises_timestamps_to_iso_days():
    assert ug.signal_day(_trade(pd.Timestamp("2021-03-02"))) == "2021-03-02"


# --- causal_liquidity_reason ------------------------------------------------

def test_liquid_ticker_passes():
    df = _frame([50.0] * 40, [1_000_000] * 40)            # $50M a day
    assert ug.causal_liquidity_reason(df, _day(df, 30), FLOOR) is None


def test_fewer_than_lookback_bars_through_the_signal_day_is_refused():
    df = _frame([50.0] * 40, [1_000_000] * 40)
    assert ug.causal_liquidity_reason(df, _day(df, 18), FLOOR).startswith(
        "insufficient history (<20 bars)")
    assert ug.causal_liquidity_reason(df, _day(df, 19), FLOOR) is None   # exactly 20 bars


def test_price_floor_reads_the_signal_bars_close():
    df = _frame([50.0] * 30 + [4.0] * 10, [1_000_000] * 40)
    assert ug.causal_liquidity_reason(df, _day(df, 29), FLOOR) is None
    assert ug.causal_liquidity_reason(df, _day(df, 30), FLOOR).startswith(
        "price 4.00 < 5.00 floor")


def test_dollar_volume_averages_exactly_the_lookback_bars_ending_at_the_signal():
    df = _frame([50.0] * 40, [100_000] * 20 + [1_000_000] * 20)   # $5M then $50M
    # bars 6..25: 14 x $5M + 6 x $50M = $370M / 20 = $18.5M
    assert ug.causal_liquidity_reason(df, _day(df, 25), FLOOR).startswith(
        "avg dollar vol $18.5M < $20M floor")
    # bars 19..38: 1 x $5M + 19 x $50M = $47.75M
    assert ug.causal_liquidity_reason(df, _day(df, 38), FLOOR) is None


def test_a_non_trading_signal_day_uses_the_last_bar_on_or_before_it():
    df = _frame([50.0] * 5, [1_000_000] * 5)              # Mon 2021-01-04 .. Fri 2021-01-08
    small = LiquidityFloor(min_avg_dollar_vol=1.0, min_price=1.0, lookback_bars=5)
    assert ug.causal_liquidity_reason(df, "2021-01-09", small) is None    # Saturday
    assert ug.causal_liquidity_reason(df, "2021-01-07", small).startswith(
        "insufficient history (<5 bars)")


# --- no lookahead (partner decision 1) ---------------------------------------

def _mixed_frame():
    closes = [50.0] * 20 + [3.0] * 10 + [50.0] * 20 + [1.0] * 10
    volumes = [1_000_000] * 10 + [10_000] * 20 + [2_000_000] * 20 + [0] * 10
    return _frame(closes, volumes)


def test_reason_on_every_day_equals_the_reason_on_the_frame_cut_at_that_day():
    """The floor reads no bar after the signal date: cutting the future off
    never changes the answer, on any day of a frame whose regime flips."""
    df = _mixed_frame()
    for i in range(len(df)):
        day = _day(df, i)
        assert ug.causal_liquidity_reason(df, day, FLOOR) == \
            ug.causal_liquidity_reason(df.iloc[: i + 1], day, FLOOR), day


def test_rewriting_the_future_never_changes_the_verdict():
    df = _frame([50.0] * 60, [1_000_000] * 60)
    day = _day(df, 30)
    before = ug.causal_liquidity_reason(df, day, FLOOR)
    poisoned = df.copy()
    poisoned.iloc[31:, poisoned.columns.get_loc("Close")] = 0.01
    poisoned.iloc[31:, poisoned.columns.get_loc("Volume")] = 0
    assert before is None
    assert ug.causal_liquidity_reason(poisoned, day, FLOOR) is None


def test_causal_floor_keeps_a_name_that_later_collapsed_unlike_the_legacy_floor():
    """The survivorship trap the legacy last-20-bars floor carries for `_pit` runs."""
    df = _frame([50.0] * 31 + [1.0] * 29, [1_000_000] * 31 + [0] * 29)
    assert liquidity_reason(df, min_avg_dollar_vol=20_000_000.0, min_price=5.0) is not None
    assert ug.causal_liquidity_reason(df, _day(df, 30), FLOOR) is None


def test_causal_floor_drops_a_name_illiquid_at_the_signal_that_later_grew():
    df = _frame([50.0] * 60, [1_000] * 31 + [1_000_000] * 29)
    assert liquidity_reason(df, min_avg_dollar_vol=20_000_000.0, min_price=5.0) is None
    assert ug.causal_liquidity_reason(df, _day(df, 30), FLOOR).startswith("avg dollar vol")


# --- eligible_trades ----------------------------------------------------------

SPANS = [("2021-02-01", "2021-03-01")]   # [start, end) like pit_membership


def test_membership_is_checked_on_the_signal_day_not_the_entry_day():
    signal_in = _trade("2021-03-01", signal="2021-02-26")   # fills the day the span ends
    signal_out = _trade("2021-02-01", signal="2021-01-29")  # fills the day the span starts
    df = _frame([50.0] * 60, [1_000_000] * 60)
    assert ug.eligible_trades([signal_in, signal_out], SPANS, df, None) == [signal_in]


def test_spans_none_is_unmasked_and_an_empty_span_list_keeps_nothing():
    df = _frame([50.0] * 60, [1_000_000] * 60)
    trades = [_trade(_day(df, 30)), _trade(_day(df, 40))]
    assert ug.eligible_trades(trades, None, df, None) == trades
    assert ug.eligible_trades(trades, [], df, None) == []


def test_the_floor_is_applied_on_the_signal_day():
    df = _frame([50.0] * 60, [10_000] * 25 + [1_000_000] * 35)
    early = _trade(_day(df, 23), signal=_day(df, 22))    # illiquid window at the signal
    late = _trade(_day(df, 46), signal=_day(df, 45))     # bars 26..45 all liquid
    assert ug.eligible_trades([early, late], None, df, FLOOR) == [late]


def test_eligible_trades_keeps_order_and_every_trade_of_a_shared_day():
    df = _frame([50.0] * 60, [1_000_000] * 60)
    day = _day(df, 30)
    a, b, c = _trade(day), _trade(_day(df, 40)), _trade(day)
    assert ug.eligible_trades([a, b, c], None, df, FLOOR) == [a, b, c]


# --- watchlist_slice_verdict --------------------------------------------------

def test_slice_minimum_is_thirty():
    assert ug.WATCHLIST_SLICE_MIN_N == 30


@pytest.mark.parametrize("n, exp_r, status", [
    (0, None, "thin"),
    (29, -0.5, "thin"),          # below 30: reported, never blocks
    (30, -0.01, "fail"),
    (30, 0.0, "pass"),           # the guard is ExpR < 0, not <= 0
    (120, 0.21, "pass"),
])
def test_slice_verdict(n, exp_r, status):
    verdict = ug.watchlist_slice_verdict(n, exp_r)
    assert verdict == ug.SliceVerdict(status=status, n=n, expectancy_r=exp_r)


def test_slice_min_n_is_overridable():
    assert ug.watchlist_slice_verdict(10, -0.1, min_n=10).status == "fail"


@pytest.mark.parametrize("exp_r", [None, math.nan, math.inf])
def test_a_full_slice_without_a_finite_expectancy_is_an_error(exp_r):
    with pytest.raises(ValueError, match="no finite ExpR"):
        ug.watchlist_slice_verdict(30, exp_r)


def test_nan_volume_inside_the_window_is_refused_as_insufficient_history():
    """A NaN Volume must not be skipped by the mean (that would average fewer
    than lookback_bars bars): the day is refused like a short history."""
    volumes = [1_000_000.0] * 40
    volumes[25] = float("nan")
    df = _frame([50.0] * 40, volumes)
    assert ug.causal_liquidity_reason(df, _day(df, 30), FLOOR).startswith(
        "insufficient history (<20 valid bars)")
    assert ug.causal_liquidity_reason(df, _day(df, 24), FLOOR) is None    # before the NaN
    assert ug.causal_liquidity_reason(df, _day(df, 39), FLOOR).startswith(
        "insufficient history")                                         # NaN still in window

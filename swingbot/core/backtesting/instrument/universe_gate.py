"""Causal point-in-time universe gate for instrument v2 (v136 spec section 1,
"Universe"; v158 partner decision 1).

A v2 trade counts only when, on its SIGNAL day:

- the ticker was an index member (``pit_membership`` spans, [start, end)), and
- the ticker cleared the causal liquidity floor: the average Close*Volume of
  the ``lookback_bars`` bars ending AT the signal bar, and that bar's close.

``universe.liquidity_reason`` reads the last bars of the whole cached history,
which is lookahead inside a replay (that is why ``run_backtest_range`` skips it
for ``_pit`` runs). Nothing here reads a bar dated after the signal day;
tests/backtesting/instrument/test_universe_gate.py proves it.

The watchlist is a reported slice of the same run: its verdict fails when the
slice's ExpR < 0 with N >= ``WATCHLIST_SLICE_MIN_N``, and is ``thin`` (never
blocking) below that.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd

from swingbot.core.backtesting.instrument.contract import LiquidityFloor
from swingbot.core.marketdata.pit_membership import is_member

WATCHLIST_SLICE_MIN_N = 30


def signal_day(trade) -> str:
    """ISO day of the trade's signal bar.

    v157 adds ``BacktestTrade.signal_date``: under v2 ``entry_date`` is the
    next-open fill, one bar after the signal. Until v157 lands the attribute
    is absent and this falls back to ``entry_date``; under v1 both are the
    same bar, so the fallback is exact there."""
    value = getattr(trade, "signal_date", None) or trade.entry_date
    return str(value)[:10]


def _bars_through(df: pd.DataFrame, day: str, count: int) -> pd.DataFrame:
    """The last `count` bars dated on or before `day` (index sorted ascending)."""
    end = int(df.index.searchsorted(pd.Timestamp(day), side="right"))
    return df.iloc[max(0, end - count):end]


def causal_liquidity_reason(df: pd.DataFrame, day: str, floor: LiquidityFloor) -> str | None:
    """None when the ticker cleared `floor` on `day`, else a loggable reason.
    Reads only the `floor.lookback_bars` bars dated on or before `day`. A NaN
    Close or Volume in that window refuses the day like a short history: the
    mean never silently averages fewer than `lookback_bars` bars."""
    window = _bars_through(df, day, floor.lookback_bars)
    if len(window) < floor.lookback_bars:
        return f"insufficient history (<{floor.lookback_bars} bars) at {day}"
    dollar = window["Close"] * window["Volume"]
    if int(dollar.notna().sum()) < floor.lookback_bars:
        return f"insufficient history (<{floor.lookback_bars} valid bars) at {day}"
    close = float(window["Close"].iloc[-1])
    if not close >= floor.min_price:
        return f"price {close:.2f} < {floor.min_price:.2f} floor at {day}"
    dollar_vol = float(dollar.mean())
    if not dollar_vol >= floor.min_avg_dollar_vol:
        return (f"avg dollar vol ${dollar_vol / 1e6:.1f}M < "
                f"${floor.min_avg_dollar_vol / 1e6:.0f}M floor at {day}")
    return None


def _eligible_on(day: str, spans, df: pd.DataFrame, floor: LiquidityFloor | None) -> bool:
    if not is_member(day, spans):
        return False
    return floor is None or causal_liquidity_reason(df, day, floor) is None


def eligible_trades(trades, spans, df: pd.DataFrame, floor: LiquidityFloor | None) -> list:
    """Trades whose signal day passes PIT membership (`spans`; None = unmasked,
    [] = never a member) and, when `floor` is set, the causal liquidity floor.
    Input order is kept; each signal day is evaluated once."""
    verdicts: dict[str, bool] = {}
    kept = []
    for trade in trades:
        day = signal_day(trade)
        if day not in verdicts:
            verdicts[day] = _eligible_on(day, spans, df, floor)
        if verdicts[day]:
            kept.append(trade)
    return kept


@dataclass(frozen=True)
class SliceVerdict:
    """The watchlist slice's verdict: "pass", "fail" or "thin" (N below the minimum)."""

    status: str
    n: int
    expectancy_r: float | None


def watchlist_slice_verdict(n: int, expectancy_r: float | None,
                            min_n: int = WATCHLIST_SLICE_MIN_N) -> SliceVerdict:
    """Spec section 1: the slice fails the verdict when ExpR < 0 with N >= min_n;
    below min_n it is reported as thin and never blocks."""
    if n < min_n:
        return SliceVerdict("thin", n, expectancy_r)
    if expectancy_r is None or not math.isfinite(expectancy_r):
        raise ValueError(f"watchlist slice has N={n} but no finite ExpR ({expectancy_r!r})")
    return SliceVerdict("fail" if expectancy_r < 0 else "pass", n, expectancy_r)

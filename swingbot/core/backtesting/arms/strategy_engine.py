"""Strategy-source population through the live plan constructor (v100).

At signal bar ``i`` the constructor receives only ``df.iloc[:i + 1]``;
``simulate_exit`` alone walks later bars to determine the outcome.

The v119 compression short is research-only here: it runs when a
``CompressionResearchContext`` is supplied (the stamped research knob), under a
scoped ``gate_override`` of its own ("bearish", "2w") cell -- the global mask is
never mutated -- and every candidate passes the same pre-entry decision the live
pass calls (``compression_context.decide_compression_entry``).
"""
from __future__ import annotations

import datetime as dt
from collections import Counter
from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd

from swingbot.core.backtesting import backtest as bt
from swingbot.core.backtesting.acceptance import arm_trade_from_plan
from swingbot.core.backtesting.arms.confluence_engine import SKIPPED
from swingbot.core.market import entry_filters
from swingbot.core.market.levels import build_level_map
from swingbot.core.market.strategy_types import COMPRESSION_SHORT, HORIZONS, MIN_BARS
from swingbot.core.planning.builders import build_strategy_plan
from swingbot.core.planning.plan_engine import exit_params_for, simulate_exit

# ExitResult.cancel_reason -> the scan-level reason it is counted under.
_CANCEL_REASONS = {"expired": "expired", "risk_cap": "gap_risk_cancel", "invalidated": "invalidated"}


class CompressionContextError(RuntimeError):
    """The compression-short replay needs an explicit as-of context; none was supplied."""


@dataclass(frozen=True)
class CompressionResearchContext:
    """As-of inputs for the compression short's pre-entry decision.

    `spy`: SPY's daily frame. `sector_of(ticker)`: that ticker's dated sector-ETF frame as it stood
    then (never today's static sector map). `snapshot_of(ticker, decided_at)`: the earnings snapshot
    observed at or before `decided_at`, or None when no historical archive holds one -- the candidate
    is then excluded as unmeasurable, never assumed clear.
    """

    spy: pd.DataFrame
    sector_of: Callable[[str], pd.DataFrame | None]
    snapshot_of: Callable[[str, dt.datetime], object]


class StrategyEngine:
    engine_id = "strategy"

    def __init__(self, strategies=None, compression_context: CompressionResearchContext | None = None):
        self.strategies = tuple(strategies or bt.ALL_STRATEGIES)
        self.compression_context = compression_context
        self.compression_reasons: Counter = Counter()
        self.compression_reasons_by_mode: Counter = Counter()

    def run_ticker(self, ticker, df, horizons, signal_window, params) -> list:
        out = []
        for horizon_key in horizons:
            for strategy in self.strategies:
                out.extend(self.iter_trades_for_strategy(
                    ticker, df, strategy, horizon_key, signal_window, params))
        return out

    def iter_trades_for_strategy(self, ticker, df, strategy, horizon_key, signal_window, params):
        """One (strategy, horizon) cell's stamped ArmTrade rows, in signal order."""
        for date, plan, result in self.iter_trades(
                ticker, df, strategy, horizon_key, signal_window, params):
            yield arm_trade_from_plan(
                plan, entry_date=date, outcome=result.outcome,
                r_multiple=result.r_total,
            )

    def _entries(self, df, strategy, horizon_key):
        """Entry series; the compression short alone is read under its scoped research cell."""
        if strategy != COMPRESSION_SHORT:
            return bt._vectorized_entries(df, strategy, horizon_key)
        if self.compression_context is None:
            raise CompressionContextError(
                "compression-short replay needs a CompressionResearchContext (SPY, as-of sector "
                "frames, as-of earnings snapshots); refusing a silent empty cohort")
        cell = {"directions": ("bearish",), "horizons": (horizon_key,),
                "cells": {("bearish", "2w")}}
        with entry_filters.gate_override(COMPRESSION_SHORT, cell):
            return bt._vectorized_entries(df, strategy, horizon_key)

    def _compression_stamp(self, ticker, window):
        """(stamp, reason) from the shared pre-entry decision, as of the signal bar's close."""
        from swingbot.core.scanning import compression_context as cc
        context = self.compression_context
        decided_at = cc.decision_time_for(window.index[-1].date())
        mode, why = cc.compression_mode_for(window, context.spy, context.sector_of(ticker), now=decided_at)
        snapshot = context.snapshot_of(ticker, decided_at) if mode is not None else None
        return cc.decide_compression_entry(ticker, window, mode=mode, mode_reason=why,
                                           snapshot=snapshot, now=decided_at)

    def _count(self, stamp, reason) -> None:
        self.compression_reasons[reason] += 1
        self.compression_reasons_by_mode[f"{stamp.get('compression_mode') or 'none'}:{reason}"] += 1

    def iter_trades(self, ticker, df, strategy, horizon_key, signal_window, params):
        start, end = signal_window
        min_bars = MIN_BARS[horizon_key]
        if len(df) < min_bars + 10:
            return
        bull, bear = self._entries(df, strategy, horizon_key)
        if bt.ENTRY_SHIFT:
            bull = pd.Series(np.roll(bull.values, bt.ENTRY_SHIFT), index=df.index)
            bear = pd.Series(np.roll(bear.values, bt.ENTRY_SHIFT), index=df.index)
        wants_tp2 = bool(exit_params_for(strategy)["tp2"])
        open_until, level_map_key, level_map = -1, None, None
        for index in np.where(bull.values | bear.values)[0]:
            if index < min_bars or index <= open_until:
                continue
            date = str(df.index[index].date())
            if date > end:
                break
            direction = "bullish" if bull.values[index] else "bearish"
            window = df.iloc[:index + 1]
            if wants_tp2 and index // 5 != level_map_key:
                level_map = build_level_map(
                    window, HORIZONS[horizon_key], float(df["Close"].iloc[index]))
                level_map_key = index // 5
            counted = date >= start        # warm-up candidates are never counted, same predicate as the yield
            plan, stamp = self._candidate_plan(
                ticker, window, index, strategy, horizon_key, direction, params,
                level_map if wants_tp2 else None, counted)
            if plan is None:
                continue
            result = simulate_exit(df, index, plan, scale_out=True)
            if self._skipped(result, strategy, stamp, counted):
                continue
            open_until = result.exit_index
            if counted:
                yield date, plan, result

    def _candidate_plan(self, ticker, window, index, strategy, horizon_key, direction, params, level_map,
                        counted=True):
        """(plan | None, stamp): the shared pre-entry decision (compression short only), then the live
        constructor on bars <= index. A rejection is counted (when `counted`) and returns no plan."""
        stamp = {}
        if strategy == COMPRESSION_SHORT:
            stamp, reason = self._compression_stamp(ticker, window)
            if reason is not None:
                if counted:
                    self._count(stamp, reason)
                return None, stamp
        plan = build_strategy_plan(
            window, index, ticker=ticker, strategy=strategy,
            horizon_key=horizon_key, direction=direction,
            level_map=level_map, scan_params=params,
        )
        if plan is None:
            if counted:
                self._count_plan_none(strategy, window, horizon_key, stamp)
            return None, stamp
        if stamp:
            plan.entry_context = {**(plan.entry_context or {}), **stamp}
        return plan, stamp

    def _skipped(self, result, strategy, stamp, counted=True) -> bool:
        """Whether the walk produced no scored trade; a compression row says why (expiry, gap-risk...)."""
        if result.outcome not in SKIPPED:
            return False
        if strategy == COMPRESSION_SHORT and counted:
            self._count(stamp, _CANCEL_REASONS.get(result.cancel_reason, "not_triggered"))
        return True

    def _count_plan_none(self, strategy, window, horizon_key, stamp) -> None:
        if strategy != COMPRESSION_SHORT:
            return
        from swingbot.core.planning.short_builders import compression_rejection_reason
        self._count(stamp, compression_rejection_reason(window, len(window) - 1, horizon_key))

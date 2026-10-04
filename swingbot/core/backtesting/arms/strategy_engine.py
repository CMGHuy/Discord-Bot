"""Strategy-source population through the live plan constructor (v100).

At signal bar ``i`` the constructor receives only ``df.iloc[:i + 1]``;
``simulate_exit`` alone walks later bars to determine the outcome.

The v119 compression short is research-only here: it runs when a
``CompressionResearchContext`` is supplied or the research knob
``COMPRESSION_SHORT_RESEARCH_MODE`` is not ``off``, under a scoped ``gate_override``
of its own ("bearish", "2w") cell -- the global mask is never mutated -- and every
candidate passes the same pre-entry decision the live pass calls
(``compression_context.decide_compression_entry``). Under the knob only that one
weakness mode is admitted, so a broad run and an isolated run are separate cohorts.
"""
from __future__ import annotations

import datetime as dt
from collections import Counter
from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd

from swingbot import config
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

#: The research engine's one open cell: the live mask ({"directions": ()}) plus ("bearish", "2w").
#: Fixed, never the horizon being replayed, so no legacy horizon opens with it.
RESEARCH_CELL = {"directions": (), "cells": {("bearish", "2w")}}
RESEARCH_KNOB = "COMPRESSION_SHORT_RESEARCH_MODE"


def research_mode() -> str:
    """The research knob's current value ("off" | "broad" | "isolated")."""
    return getattr(config, RESEARCH_KNOB, "off")


class CompressionContextError(RuntimeError):
    """The compression-short replay needs an explicit as-of context; none was supplied."""


@dataclass(frozen=True)
class CompressionResearchContext:
    """As-of inputs for the compression short's pre-entry decision.

    `spy`: SPY's daily frame. `sector_of(ticker)`: that ticker's dated sector-ETF frame as it stood
    then (never today's static sector map). `snapshot_of(ticker, decided_at)`: the earnings snapshot
    observed at or before `decided_at`, or None when no historical archive holds one -- the candidate
    is then excluded as unmeasurable, never assumed clear.

    Optional point-in-time hooks (v119-10): `member_on(ticker, day)` -- was the ticker an index member
    on that signal date (None: every ticker counts); `sector_on(ticker, day)` -- the sector-ETF frame
    of the sector the ticker was mapped to on that date (None: fall back to `sector_of`).
    """

    spy: pd.DataFrame
    sector_of: Callable[[str], pd.DataFrame | None]
    snapshot_of: Callable[[str, dt.datetime], object]
    member_on: Callable[[str, dt.date], bool] | None = None
    sector_on: Callable[[str, dt.date], pd.DataFrame | None] | None = None

    def is_member(self, ticker: str, day: dt.date) -> bool:
        return True if self.member_on is None else bool(self.member_on(ticker, day))

    def sector_for(self, ticker: str, day: dt.date):
        return self.sector_of(ticker) if self.sector_on is None else self.sector_on(ticker, day)


class StrategyEngine:
    engine_id = "strategy"

    def __init__(self, strategies=None, compression_context: CompressionResearchContext | None = None):
        self.strategies = tuple(strategies or bt.ALL_STRATEGIES)
        self.compression_context = compression_context
        self.compression_reasons: Counter = Counter()
        self.compression_reasons_by_mode: Counter = Counter()
        # Supplemental research diagnostics -- never part of a stamped ArmTrade row.
        self.compression_signals: list[dict] = []
        self.compression_exit_reasons: Counter = Counter()

    def run_ticker(self, ticker, df, horizons, signal_window, params) -> list:
        out = []
        strategies = self._run_strategies()
        for horizon_key in horizons:
            for strategy in strategies:
                out.extend(self.iter_trades_for_strategy(
                    ticker, df, strategy, horizon_key, signal_window, params))
        return out

    def _run_strategies(self) -> tuple:
        """This run's strategies: the compression short joins (once) when the research knob is on,
        reading its as-of inputs from the explicit offline context unless one was supplied."""
        if research_mode() == "off":
            return self.strategies
        if self.compression_context is None:
            from swingbot.core.backtesting.arms import compression_research
            self.compression_context = compression_research.offline_context()
        if COMPRESSION_SHORT in self.strategies:
            return self.strategies
        return self.strategies + (COMPRESSION_SHORT,)

    def iter_trades_for_strategy(self, ticker, df, strategy, horizon_key, signal_window, params):
        """One (strategy, horizon) cell's stamped ArmTrade rows, in signal order."""
        for date, plan, result in self.iter_trades(
                ticker, df, strategy, horizon_key, signal_window, params):
            if strategy == COMPRESSION_SHORT:
                self._record_signal(ticker, df, date, plan, result)
            yield arm_trade_from_plan(
                plan, entry_date=date, outcome=result.outcome,
                r_multiple=result.r_total,
            )

    def _record_signal(self, ticker, df, date, plan, result) -> None:
        """One supplemental row per scored compression signal: dates, mode and why it closed."""
        leg = result.legs[-1] if result.legs else {}
        reason = leg.get("reason") or result.outcome
        self.compression_exit_reasons[reason] += 1
        self.compression_signals.append({
            "ticker": ticker, "signal_date": date,
            "entry_date": str(df.index[result.entry_index].date()),
            "exit_date": str(df.index[result.exit_index].date()),
            "hold_sessions": int(result.exit_index - result.entry_index + 1),
            "mode": (plan.entry_context or {}).get("compression_mode"),
            "outcome": result.outcome, "r_multiple": result.r_total, "exit_reason": reason,
            "price_basis": leg.get("price_basis"), "entry_price": result.entry_price,
            "stop_loss": plan.stop_loss, "tp1": plan.tp1,
        })

    def _entries(self, df, strategy, horizon_key):
        """Entry series; the compression short alone is read under its scoped research cell."""
        if strategy != COMPRESSION_SHORT:
            return bt._vectorized_entries(df, strategy, horizon_key)
        if self.compression_context is None:
            raise CompressionContextError(
                "compression-short replay needs a CompressionResearchContext (SPY, as-of sector "
                "frames, as-of earnings snapshots); refusing a silent empty cohort")
        with entry_filters.gate_override(COMPRESSION_SHORT, RESEARCH_CELL):
            return bt._vectorized_entries(df, strategy, horizon_key)

    def _compression_stamp(self, ticker, window):
        """(stamp, reason) from the shared pre-entry decision, as of the signal bar's close.

        NO-LOOKAHEAD: membership and sector are read for the signal bar's own date."""
        from swingbot.core.scanning import compression_context as cc
        context = self.compression_context
        bar_day = window.index[-1].date()
        if not context.is_member(ticker, bar_day):
            return {}, "not_pit_member"
        decided_at = cc.decision_time_for(bar_day)
        mode, why = cc.compression_mode_for(window, context.spy, context.sector_for(ticker, bar_day),
                                            now=decided_at)
        snapshot = context.snapshot_of(ticker, decided_at) if mode is not None else None
        knob = research_mode()
        allowlist = (knob,) if knob in cc.COMPRESSION_MODES else cc.COMPRESSION_MODES
        return cc.decide_compression_entry(ticker, window, mode=mode, mode_reason=why,
                                           snapshot=snapshot, now=decided_at, allowlist=allowlist)

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

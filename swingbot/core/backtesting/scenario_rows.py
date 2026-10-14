"""v146 I3: one TRAIN per-trade row for a confluence-replay hit, carrying a
confidence score computed exactly as the live scan computes it
(analyze.py: score_confidence with the SPY regime trend, target and stop
confluence, on the decision frame).

NO-LOOKAHEAD: every as-of field (signal_fields) is computed on
window = df.iloc[:i+1] and on SPY sliced to the signal bar's timestamp.
Only the exit fields -- outcome, runner_outcome, r_total, entry_price,
legs -- come from the ExitResult, which walked the later bars by design.

Production runs the legacy scorer (UNIFIED_CONFIDENCE defaults false), so
the unified-only inputs (htf_bias, rs_percentile, breadth, macro_verdict)
are not supplied here.
"""
from __future__ import annotations

import dataclasses

from swingbot.core.backtesting.backtest_scenarios import REPLAY_CONFLUENCE_TOLERANCE_PCT
from swingbot.core.market import levels
from swingbot.core.market.strategy_types import HORIZONS
from swingbot.core.scanning.confidence import score_confidence
from swingbot.core.scanning.regime import get_market_regime

#: Frozen before the v146 TRAIN run (spec I3). A replayed trade has no live
#: track record, and the legacy scorer's expectancy step at
#: track_record=None is NOT neutral (assumed 50% win rate, +-1 level by
#: reward:risk), so the TRAIN score neutralises it. Never flip after the run.
TRAIN_NEUTRAL_EXPECTANCY = True

#: The row's keys, in order (the ledger contract V146-12 reads).
ROW_KEYS = ("ticker", "horizon_key", "signal_date", "direction", "entry", "stop_loss",
            "take_profit", "risk_reward_ratio", "outcome", "runner_outcome", "r_total",
            "entry_price", "legs", "entry_context", "confluence_count", "confidence_score",
            "confidence_level", "confidence_points", "confidence_unevaluated")


def _regime_trend(spy_df, signal_ts) -> str | None:
    """Live passes get_market_regime(SPY).trend; None when SPY is absent or
    too short (< 220 bars) -- the live scan's 'regime unavailable'."""
    if spy_df is None:
        return None
    try:
        return get_market_regime(spy_df[spy_df.index <= signal_ts]).trend
    except ValueError:
        return None


def _scoring_copy(scenario):
    """The legacy scorer appends to target_sources (squeeze / candlestick
    lines); scoring a copy leaves the replay's scenario and plan untouched."""
    return dataclasses.replace(
        scenario,
        target_sources=list(scenario.target_sources),
        stop_sources=list(scenario.stop_sources),
        target2_sources=(list(scenario.target2_sources)
                         if scenario.target2_sources is not None else None),
        constraints=dict(scenario.constraints))


def signal_fields(horizon_key: str, df, hit, spy_df) -> dict:
    """The as-of half of the row: signal date, confluence count and the
    confidence score, from df.iloc[:hit.i+1] and SPY up to that bar only."""
    window = df.iloc[:hit.i + 1]
    price = float(window["Close"].iloc[-1])
    scenario = hit.scenario
    stop_confluence = levels.count_confirming_strategies(
        window, HORIZONS[horizon_key], price, scenario.stop_loss,
        tolerance_pct=REPLAY_CONFLUENCE_TOLERANCE_PCT)
    conf = score_confidence(
        _scoring_copy(scenario), regime_trend=_regime_trend(spy_df, window.index[-1]), df=window,
        target_confluence=hit.target_confluence, stop_confluence=stop_confluence,
        track_record=None, neutral_expectancy=TRAIN_NEUTRAL_EXPECTANCY)
    return {
        "signal_date": str(window.index[-1].date()),
        "confluence_count": int(hit.target_confluence[0]),
        "confidence_score": int(conf.score),
        "confidence_level": int(conf.level),
        "confidence_points": dict(conf.points),
        "confidence_unevaluated": list(conf.unevaluated),
    }


def _planned_rr(plan) -> float | None:
    risk = abs(plan.trigger_price - plan.stop_loss)
    return round(abs(plan.tp1 - plan.trigger_price) / risk, 2) if risk else None


def scenario_trade_row(ticker: str, horizon_key: str, df, hit, result, spy_df) -> dict:
    """One self-contained TRAIN row (keys: ROW_KEYS). R is gross: the
    replay's exit_sim applies no frictions; the v146 study nets them."""
    plan = hit.plan
    row = {
        "ticker": ticker,
        "horizon_key": horizon_key,
        "signal_date": None,                       # set by signal_fields below
        "direction": plan.direction,
        "entry": float(plan.trigger_price),
        "stop_loss": float(plan.stop_loss),
        "take_profit": float(plan.tp1),
        "risk_reward_ratio": _planned_rr(plan),
        "outcome": result.outcome,
        "runner_outcome": result.runner_outcome,
        "r_total": float(result.r_total),
        "entry_price": None if result.entry_price is None else float(result.entry_price),
        "legs": [dict(leg) for leg in (result.legs or [])],
        "entry_context": dict(getattr(plan, "entry_context", None) or {}),
    }
    row.update(signal_fields(horizon_key, df, hit, spy_df))
    return row

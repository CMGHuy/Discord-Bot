"""v93 strategy-sourced alert pass helpers."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
import pandas as pd

from swingbot.core.market import market_context
from swingbot.core.market.entry_filters import ENTRY_FUNCS, entries_for
from swingbot.core.planning.builders import build_strategy_plan
from swingbot.core.planning.params import stamp_badge, stamp_cohort, stamp_entry_context
from swingbot.core.planning.stop_scope import risk_sizing_ok
from swingbot.core.tracking import ledger as ledger_mod
from swingbot.core.edge.rs_gate import rs_verdict
from swingbot.core.scanning.alert_embeds import (build_strategy_alert_embed,
                                                 build_strategy_simple_embed)

log = logging.getLogger(__name__)
from swingbot.core.market.session import is_regular_session, session_date


def completed_frame(df: pd.DataFrame, now) -> pd.DataFrame:
    """Remove only today's still-forming daily bar during the regular session."""
    if df is None or len(df) == 0:
        return df
    if df.index[-1].date().isoformat() == session_date(now) and is_regular_session(now):
        return df.iloc[:-1]
    return df


def already_emitted(store, ticker: str, strategy: str, horizon_key: str, bar_date: str) -> bool:
    """Whether a persisted strategy plan already represents this completed bar."""
    return any(getattr(plan, "source", None) == "strategy"
               and plan.ticker == ticker and plan.strategy == strategy
               and plan.horizon_key == horizon_key and plan.created_at == bar_date
               for plan in store.all())


def strategy_signals(df_completed: pd.DataFrame, horizon_key: str, *, spy_df) -> list[tuple[str, str]]:
    """Return entry-rule signals firing on the last completed bar only."""
    if spy_df is None or len(spy_df) == 0:
        import logging
        logging.getLogger(__name__).warning("strategy pass: no SPY frame this scan -- strategy signals skipped (fail-closed)")
        return []
    frame = df_completed if market_context.has_context(df_completed) else market_context.attach(df_completed, spy_df=spy_df)
    fired = []
    for strategy in ENTRY_FUNCS:
        try:
            bullish, bearish = entries_for(strategy, frame, horizon_key)
        except Exception:
            import logging
            logging.getLogger(__name__).warning("strategy pass: %s/%s raised -- skipped", strategy, horizon_key, exc_info=True)
            continue
        if len(bullish) and bool(bullish.iloc[-1]):
            fired.append((strategy, "bullish"))
        if len(bearish) and bool(bearish.iloc[-1]):
            fired.append((strategy, "bearish"))
    return fired


def build_strategy_plan_at(df_completed: pd.DataFrame, *, ticker: str, strategy: str,
                           horizon_key: str, direction: str, regime2_state: str | None, asof: dict | None = None):
    """Build and freeze all immutable issuance stamps for one strategy signal."""
    plan = build_strategy_plan(df_completed, len(df_completed) - 1, ticker=ticker,
                               strategy=strategy, horizon_key=horizon_key, direction=direction)
    if plan is None:
        return None
    stamp_badge(plan)
    stamp_cohort(plan, regime2_state)
    stamp_entry_context(plan, df_completed, {**(asof or {}), "regime2_state": regime2_state})
    plan.ledger = ledger_mod.ledger_for(plan.source, plan.badge)
    return plan


@dataclass
class PassResult:
    plans: list = field(default_factory=list)
    alerts: list = field(default_factory=list)
    opened: int = 0
    stored_only: int = 0
    rs_blocked: int = 0
    skipped_dup: int = 0
    sizing_blocked: int = 0


@dataclass
class _PassDeps:
    """The collaborators one strategy pass threads through every signal."""

    plan_store: object
    trade_log: object
    mode: str
    live_allow: set
    rs_combined_of: object
    asof_of: object = None


def _regime_for(regimes, frame):
    if regimes is None:
        return None
    # Lazy import avoids scan engine's analyze <-> engine import cycle.
    from swingbot.core.scanning import analyze

    return analyze._regime_at(regimes, frame.index[-1])


def _rs_blocked(ticker: str, direction: str, rs_combined_of) -> bool:
    """Return whether the live v93 laggard rule blocks a bearish signal."""
    if direction != "bearish":
        return False
    rs_value = rs_combined_of(ticker)
    verdict = rs_verdict(ticker, direction, rs_value if rs_value is not None else 50.0,
                         rs_available=rs_value is not None)
    return verdict["status"] == "block"


def _open_trade(deps: _PassDeps, plan, *, ticker, strategy, horizon, direction) -> None:
    deps.trade_log.log_trade(
        ticker=ticker, strategy=strategy, horizon_key=horizon, direction=direction,
        confidence_level=None, confidence_label="strategy signal", entry=plan.trigger_price,
        stop_loss=plan.stop_loss, take_profit=plan.tp1, target2=plan.tp2,
        plan_id=plan.plan_id, badge=plan.badge, quality_score=plan.quality_score,
        source=plan.source, cohort_label=plan.cohort_label,
        cohort_stats=plan.cohort_stats, risk_features=plan.risk_features,
        ledger=plan.ledger, entry_context=plan.entry_context)


def _emit_signal(result: PassResult, frame, *, ticker, strategy, direction, horizon,
                 bar_date, regime, deps: _PassDeps) -> None:
    """Store and, when eligible, alert one fired strategy signal."""
    if already_emitted(deps.plan_store, ticker, strategy, horizon, bar_date):
        result.skipped_dup += 1
        return
    if _rs_blocked(ticker, direction, deps.rs_combined_of):
        result.rs_blocked += 1
        return
    plan = build_strategy_plan_at(
        frame, ticker=ticker, strategy=strategy, horizon_key=horizon,
        direction=direction, regime2_state=regime,
        asof=deps.asof_of(ticker) if deps.asof_of else None)
    if plan is None:
        return
    if not risk_sizing_ok(plan):
        log.error(
            "strategy pass: %s %s %s %s uses structural stops but has no risk-based sizing "
            "-- not stored, not posted (v104 fail-closed)",
            ticker, strategy, horizon, direction)
        result.sizing_blocked += 1
        return
    deps.plan_store.add(plan)
    result.plans.append(plan)
    goes_live = deps.mode == "live" and (not deps.live_allow or strategy in deps.live_allow)
    if not goes_live or deps.trade_log.open_trade_for_ticker(ticker) is not None:
        result.stored_only += 1
        return
    _open_trade(deps, plan, ticker=ticker, strategy=strategy, horizon=horizon, direction=direction)
    result.opened += 1
    # v110 §6.1: the simple-channel mirror is an embed like every other alert's.
    result.alerts.append((build_strategy_alert_embed(plan), None, plan,
                          build_strategy_simple_embed(plan)))


def run_strategy_pass(tickers, fresh_data, *, now, horizons, spy_df, regimes,
                      rs_combined_of, mode: str, live_allow: set, trade_log, plan_store,
                      asof_of=None) -> PassResult:
    """Build strategy plans after confluence; only eligible live plans open trades."""
    result = PassResult()
    deps = _PassDeps(plan_store, trade_log, mode, live_allow, rs_combined_of, asof_of)
    for ticker in tickers:
        raw = fresh_data.get(ticker)
        if raw is None or len(raw) == 0:
            continue
        try:
            frame = completed_frame(raw, now)
            if frame is None or len(frame) == 0:
                continue
            bar_date = frame.index[-1].date().isoformat()
            regime = _regime_for(regimes, frame)
            for horizon in horizons:
                for strategy, direction in strategy_signals(frame, horizon, spy_df=spy_df):
                    _emit_signal(result, frame, ticker=ticker, strategy=strategy, direction=direction,
                                 horizon=horizon, bar_date=bar_date, regime=regime, deps=deps)
        except Exception:
            log.warning("strategy pass: %s failed -- continuing", ticker, exc_info=True)
    return result

"""v93 strategy-sourced alert pass helpers."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
import pandas as pd

from swingbot.core.market import market_context
from swingbot.core.market.entry_filters import ENTRY_FUNCS, entries_for
from swingbot.core.planning.builders import build_strategy_plan
from swingbot.core.planning.params import stamp_badge, stamp_cohort, stamp_entry_context
from swingbot.core.tracking import ledger as ledger_mod
from swingbot.core.edge.rs_gate import rs_verdict
from swingbot.core.scanning.alert_embeds import build_strategy_alert_embed

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


def simple_line(plan) -> str:
    return (f"{plan.ticker} {plan.direction} · {plan.strategy} {plan.horizon_key} · "
            f"entry {plan.trigger_price:.2f} stop {plan.stop_loss:.2f} TP1 {plan.tp1:.2f} · "
            f"{plan.badge} · ledger {plan.ledger}")


@dataclass
class PassResult:
    plans: list = field(default_factory=list)
    alerts: list = field(default_factory=list)
    opened: int = 0
    stored_only: int = 0
    rs_blocked: int = 0
    skipped_dup: int = 0


def run_strategy_pass(tickers, fresh_data, *, now, horizons, spy_df, regimes,
                      rs_combined_of, mode: str, live_allow: set, trade_log, plan_store, asof_of=None) -> PassResult:
    """Build strategy plans after confluence; only eligible live plans open trades."""
    result = PassResult()
    for ticker in tickers:
        raw = fresh_data.get(ticker)
        if raw is None or len(raw) == 0:
            continue
        try:
            frame = completed_frame(raw, now)
            if frame is None or len(frame) == 0:
                continue
            bar_date = frame.index[-1].date().isoformat()
            if regimes is not None:
                # Lazy import avoids scan engine's analyze <-> engine import cycle.
                from swingbot.core.scanning import analyze
                regime = analyze._regime_at(regimes, frame.index[-1])
            else:
                regime = None
            for horizon in horizons:
                for strategy, direction in strategy_signals(frame, horizon, spy_df=spy_df):
                    if already_emitted(plan_store, ticker, strategy, horizon, bar_date):
                        result.skipped_dup += 1
                        continue
                    if direction == "bearish":
                        rs_value = rs_combined_of(ticker)
                        verdict = rs_verdict(ticker, direction, rs_value if rs_value is not None else 50.0,
                                             rs_available=rs_value is not None)
                        if verdict["status"] == "block":
                            result.rs_blocked += 1
                            continue
                    plan = build_strategy_plan_at(frame, ticker=ticker, strategy=strategy,
                                                  horizon_key=horizon, direction=direction, regime2_state=regime,
                                                  asof=asof_of(ticker) if asof_of else None)
                    if plan is None:
                        continue
                    plan_store.add(plan)
                    result.plans.append(plan)
                    goes_live = mode == "live" and (not live_allow or strategy in live_allow)
                    if not goes_live or trade_log.open_trade_for_ticker(ticker) is not None:
                        result.stored_only += 1
                        continue
                    trade_log.log_trade(ticker=ticker, strategy=strategy, horizon_key=horizon, direction=direction,
                                        confidence_level=None, confidence_label="strategy signal", entry=plan.trigger_price,
                                        stop_loss=plan.stop_loss, take_profit=plan.tp1, target2=plan.tp2,
                                        plan_id=plan.plan_id, badge=plan.badge, quality_score=plan.quality_score,
                                        source=plan.source, cohort_label=plan.cohort_label,
                                        cohort_stats=plan.cohort_stats, risk_features=plan.risk_features,
                                        ledger=plan.ledger, entry_context=plan.entry_context)
                    result.opened += 1
                    result.alerts.append((build_strategy_alert_embed(plan), None, plan, simple_line(plan)))
        except Exception:
            log.warning("strategy pass: %s failed -- continuing", ticker, exc_info=True)
    return result

"""v93 strategy-sourced alert pass helpers."""
from __future__ import annotations

import pandas as pd

from swingbot.core.market import market_context
from swingbot.core.market.entry_filters import ENTRY_FUNCS, entries_for
from swingbot.core.planning.builders import build_strategy_plan
from swingbot.core.planning.params import stamp_badge, stamp_cohort
from swingbot.core.tracking import ledger as ledger_mod
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
                           horizon_key: str, direction: str, regime2_state: str | None):
    """Build and freeze all immutable issuance stamps for one strategy signal."""
    plan = build_strategy_plan(df_completed, len(df_completed) - 1, ticker=ticker,
                               strategy=strategy, horizon_key=horizon_key, direction=direction)
    if plan is None:
        return None
    stamp_badge(plan)
    stamp_cohort(plan, regime2_state)
    plan.ledger = ledger_mod.ledger_for(plan.source, plan.badge)
    return plan


def simple_line(plan) -> str:
    return (f"{plan.ticker} {plan.direction} · {plan.strategy} {plan.horizon_key} · "
            f"entry {plan.trigger_price:.2f} stop {plan.stop_loss:.2f} TP1 {plan.tp1:.2f} · "
            f"{plan.badge} · ledger {plan.ledger}")

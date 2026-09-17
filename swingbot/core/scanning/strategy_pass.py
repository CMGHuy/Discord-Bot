"""v93 strategy-sourced alert pass helpers."""
from __future__ import annotations

import pandas as pd

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

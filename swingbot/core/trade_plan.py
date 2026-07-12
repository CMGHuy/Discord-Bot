"""
Deprecated compatibility shim over plan_engine.build_strategy_plan.

This module used to hold the full pre-extraction sizing architecture
(fibonacci/support-resistance/elliott-wave/volatility plans, entry
suggestion, confluence notes). That logic has moved to plan_engine.py
(Tasks 8-15 of the unified-plan-engine-v2 rewrite); this file now just
adapts plan_engine's TradePlanV2 into the legacy TradePlan shape so old
call sites keep working until they migrate. Scheduled for deletion at
the v2 cutover (plan Task 91).
"""
import warnings
from dataclasses import dataclass

import pandas as pd

from .plan_engine import build_strategy_plan
from .strategy_types import BREAKEVEN_TRIGGER_FRACTION

MANAGEMENT_NOTE = (
    f"After price covers {BREAKEVEN_TRIGGER_FRACTION:.0%} of the distance to target, "
    "move the stop to entry. A break-even exit is a scratch, not a loss -- this is "
    "the rule the backtest numbers assume."
)


@dataclass
class TradePlan:
    entry: float
    market_price: float
    entry_note: str
    entry_confluence: str | None
    stop_loss: float
    take_profit: float
    risk_per_share: float
    reward_per_share: float
    risk_reward_ratio: float
    method: str
    management_note: str = MANAGEMENT_NOTE


def compute_trade_plan(result, df: pd.DataFrame) -> TradePlan | None:
    warnings.warn(
        "trade_plan.compute_trade_plan is deprecated; use "
        "plan_engine.build_strategy_plan (deleted at v2 cutover, plan Task 91)",
        DeprecationWarning, stacklevel=2)
    plan = build_strategy_plan(
        df, len(df) - 1, ticker=result.ticker, strategy=result.strategy,
        horizon_key=result.horizon_key, direction=result.trend)
    if plan is None:
        return None
    risk_per_share = abs(plan.trigger_price - plan.stop_loss)
    reward_per_share = abs(plan.tp1 - plan.trigger_price)
    rr_ratio = reward_per_share / risk_per_share if risk_per_share > 0 else 0.0
    return TradePlan(
        entry=round(plan.trigger_price, 4),
        market_price=round(result.close, 4),
        entry_note="Sizing delegated to plan_engine.build_strategy_plan.",
        entry_confluence=None,
        stop_loss=round(plan.stop_loss, 4),
        take_profit=round(plan.tp1, 4),
        risk_per_share=round(risk_per_share, 4),
        reward_per_share=round(reward_per_share, 4),
        risk_reward_ratio=round(rr_ratio, 2),
        method=f"plan_engine.build_strategy_plan ({result.strategy}, {result.horizon_key})",
    )

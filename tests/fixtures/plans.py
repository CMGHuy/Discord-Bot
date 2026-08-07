"""Minimal TradePlanV2 factory.

Written for the gatekeeper's tests and lived at `tests/fixtures/gate/plans.py`
until that tree was deleted (2026-08-06). It was never gate-specific -- it just
builds a valid TradePlanV2 -- so it moved up here beside
`legacy_trade_plan_at.py` rather than keeping a package named after a subsystem
that no longer exists. Used by the plan-orphaning and unowned-target-close tests.
"""
from swingbot.core.plan_engine import TradePlanV2


def make_plan(**overrides) -> TradePlanV2:
    base = dict(
        plan_id="p_test_0001", ticker="TEST", created_at="2026-07-14",
        source="strategy", strategy="Break & Retest", horizon_key="2w",
        direction="bullish", entry_type="stop_entry", trigger_price=101.0,
        entry_price=None, expiry_bars=5, stop_loss=97.0, tp1=107.0,
        tp1_fraction=0.5, tp2=112.0, breakeven_trigger_fraction=0.5,
        trail_atr_mult=1.5, quality_score=70, quality_breakdown=[],
        tier="B", badge="VALIDATED", badge_stats={}, status="pending",
    )
    base.update(overrides)
    return TradePlanV2(**base)

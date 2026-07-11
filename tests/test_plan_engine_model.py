import pytest

from swingbot.core.plan_engine import PlanStatus, TradePlanV2, record_transition


def _plan(**kw):
    base = dict(
        plan_id="p1", ticker="AAPL", created_at="2026-07-11", source="strategy",
        strategy="Fibonacci", horizon_key="4w", direction="bullish",
        entry_type="market", trigger_price=100.0, entry_price=None, expiry_bars=5,
        stop_loss=95.0, tp1=102.0, tp1_fraction=0.5, tp2=105.0,
        breakeven_trigger_fraction=0.5, trail_atr_mult=2.5,
        quality_score=0, quality_breakdown=[], tier="C",
        badge="WEAK", badge_stats={}, status=PlanStatus.PENDING, status_history=[],
    )
    base.update(kw)
    return TradePlanV2(**base)


def test_legal_lifecycle():
    p = _plan()
    record_transition(p, PlanStatus.ACTIVE, at="2026-07-11T10:00:00")
    record_transition(p, PlanStatus.PARTIAL, at="2026-07-11T11:00:00")
    record_transition(p, PlanStatus.CLOSED, reason="tp1_runner_trail", at="2026-07-11T12:00:00")
    assert p.status == PlanStatus.CLOSED
    assert [h["status"] for h in p.status_history] == ["ACTIVE", "PARTIAL", "CLOSED"]


def test_illegal_transition_rejected():
    p = _plan()
    with pytest.raises(ValueError):
        record_transition(p, PlanStatus.PARTIAL, at="t")  # PENDING cannot skip ACTIVE


def test_pending_can_cancel():
    p = _plan()
    record_transition(p, PlanStatus.CANCELLED, reason="expired", at="t")
    assert p.status == PlanStatus.CANCELLED

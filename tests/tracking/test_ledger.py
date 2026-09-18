from swingbot.core.tracking import ledger
from swingbot.core.planning.plan_types import TradePlanV2, PlanStatus, plan_from_dict, plan_to_dict


def test_weak_only_for_strategy_source_with_weak_badge():
    assert ledger.ledger_for("strategy", "WEAK") == "weak"
    assert ledger.ledger_for("strategy", "VALIDATED") == "main"
    assert ledger.ledger_for("confluence", "WEAK") == "main"
    assert ledger.ledger_for(None, None) == "main"


def test_missing_field_is_main():
    assert ledger.is_main({"ticker": "AAPL"}) is True
    assert ledger.is_weak({"ticker": "AAPL"}) is False
    assert ledger.is_main({"ledger": "weak"}) is False
    assert ledger.is_weak({"ledger": "weak"}) is True


def test_split_never_overlaps_or_drops():
    trades = [{"id": "a"}, {"id": "b", "ledger": "weak"}, {"id": "c", "ledger": "main"}]
    main, weak = ledger.split_by_ledger(trades)
    assert [t["id"] for t in main] == ["a", "c"]
    assert [t["id"] for t in weak] == ["b"]


def _plan(**kw):
    base = dict(plan_id="p", ticker="AAPL", created_at="2026-09-17", source="strategy",
                strategy="MACD", horizon_key="3m", direction="bullish", entry_type="market",
                trigger_price=100.0, entry_price=100.0, expiry_bars=5, stop_loss=95.0,
                tp1=110.0, tp1_fraction=0.5, tp2=None, breakeven_trigger_fraction=0.5,
                trail_atr_mult=2.0, quality_score=0, quality_breakdown=[], badge="WEAK",
                badge_stats={}, status=PlanStatus.PENDING)
    base.update(kw)
    return TradePlanV2(**base)


def test_plan_ledger_field_defaults_and_round_trips():
    p = _plan()
    assert p.ledger == "main"
    p.ledger = "weak"
    assert plan_from_dict(plan_to_dict(p)).ledger == "weak"
    d = plan_to_dict(_plan()); d.pop("ledger")
    assert plan_from_dict(d).ledger == "main"

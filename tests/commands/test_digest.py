import datetime as dt
import types

from swingbot.commands.scanning import digest_payload

TODAY = dt.date(2026, 7, 11)


def _plan(ticker, badge="VALIDATED", status="PENDING", quality_score=50):
    return types.SimpleNamespace(
        plan_id=f"id-{ticker}", ticker=ticker, status=status, badge=badge, tier="A",
        quality_score=quality_score, direction="bullish", entry_type="market",
        trigger_price=100.0, stop_loss=95.0, tp1=110.0, tp2=None,
        regime_aligned=True, created_at="2026-07-11",
    )


def test_digest_payload_excludes_weak_caps_and_ranks():
    plans = [
        _plan("AAA", badge="WEAK", quality_score=95),   # excluded despite high quality -- WEAK
        _plan("BBB", badge="VALIDATED", quality_score=90),
        _plan("CCC", badge="VALIDATED", quality_score=70),
        _plan("DDD", badge="VALIDATED", quality_score=50),
        _plan("EEE", badge="VALIDATED", quality_score=30),
    ]
    payload = digest_payload(plans, TODAY, max_n=3)
    assert [p.ticker for p in payload] == ["BBB", "CCC", "DDD"]


def test_digest_payload_empty_when_no_validated_plans():
    plans = [_plan("AAA", badge="WEAK")]
    assert digest_payload(plans, TODAY, max_n=3) == []

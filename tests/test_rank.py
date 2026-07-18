import datetime as dt

from swingbot.core.analytics.rank import follow_score, rank_plans

TODAY = dt.date(2026, 7, 11)


def test_validated_a_beats_weak_a():
    val = {"badge": "VALIDATED", "quality_score": 80, "regime_aligned": True,
           "created_at": "2026-07-11"}
    weak = dict(val, badge="WEAK")
    assert follow_score(val, today=TODAY) == 40 + 32 + 10 + 10  # 92.0
    assert follow_score(weak, today=TODAY) == 52.0
    assert rank_plans([weak, val], today=TODAY)[0] is val


def test_stale_plan_loses_freshness():
    p = {"badge": "VALIDATED", "quality_score": 80, "regime_aligned": True,
         "created_at": "2026-07-01"}
    assert follow_score(p, today=TODAY) == 82.0  # freshness floor 0


def test_missing_fields_degrade_to_zero_component_not_error():
    p = {"badge": "VALIDATED", "created_at": "2026-07-11"}  # no quality_score, no regime_aligned
    assert follow_score(p, today=TODAY) == 40 + 0 + 0 + 10  # 50.0


def test_rank_plans_tie_break_quality_then_ticker():
    a = {"badge": "VALIDATED", "quality_score": 70, "created_at": "2026-07-11", "ticker": "MSFT"}
    b = {"badge": "VALIDATED", "quality_score": 70, "created_at": "2026-07-11", "ticker": "AAPL"}
    c = {"badge": "VALIDATED", "quality_score": 90, "created_at": "2026-07-11", "ticker": "ZZZZ"}
    ranked = rank_plans([a, b, c], today=TODAY)
    assert [p["ticker"] for p in ranked] == ["ZZZZ", "AAPL", "MSFT"]


def test_follow_score_accepts_dataclass_instances():
    from dataclasses import dataclass

    @dataclass
    class FakePlan:
        badge: str
        quality_score: int
        created_at: str
        ticker: str = "AAPL"

    p = FakePlan(badge="VALIDATED", quality_score=50, created_at="2026-07-11")
    assert follow_score(p, today=TODAY) == 40 + 20 + 0 + 10  # regime_aligned absent -> 0

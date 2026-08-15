import datetime as dt

from swingbot.core.analytics.rank import follow_breakdown, follow_score, rank_plans

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


def test_future_dated_created_at_clamps_freshness():
    """Negative age_days (future-dated created_at) should clamp freshness to FRESHNESS_MAX."""
    # created_at is 5 days in the future relative to TODAY
    p = {"badge": "VALIDATED", "quality_score": 80, "regime_aligned": True,
         "created_at": "2026-07-16"}
    # Without clamping: freshness = 10 - 2.0 * (-5) = 10 + 10 = 20, exceeding max
    # With clamping: freshness = min(10, max(0, 20)) = 10
    assert follow_score(p, today=TODAY) == 40 + 32 + 10 + 10  # 92.0 (freshness clamped to 10)


def test_non_string_created_at_datetime_object_degrades_gracefully():
    """Non-string created_at (e.g., datetime.date object) should not raise, degrade to 0 freshness."""
    # Pass a datetime.date object instead of string
    p = {"badge": "VALIDATED", "quality_score": 80, "regime_aligned": True,
         "created_at": dt.date(2026, 7, 11)}
    # Should not raise; freshness component should be computed from the date object
    score = follow_score(p, today=TODAY)
    assert score == 40 + 32 + 10 + 10  # 92.0 (freshness = 10 at age 0 days)


def test_non_string_created_at_datetime_instance_degrades_gracefully():
    """Non-string created_at (e.g., datetime.datetime object) should not raise."""
    p = {"badge": "VALIDATED", "quality_score": 80, "regime_aligned": True,
         "created_at": dt.datetime(2026, 7, 11, 12, 30, 45)}
    # Should not raise; datetime should be converted to date for comparison
    score = follow_score(p, today=TODAY)
    assert score == 40 + 32 + 10 + 10  # 92.0


def test_follow_breakdown_sums_to_follow_score():
    fixtures = [
        {"badge": "VALIDATED", "quality_score": 80, "regime_aligned": True, "created_at": "2026-07-11"},
        {"badge": "WEAK", "quality_score": 80, "regime_aligned": True, "created_at": "2026-07-11"},
        {"badge": "VALIDATED", "quality_score": 0, "regime_aligned": False, "created_at": "2026-07-01"},
        {"badge": "VALIDATED", "quality_score": 50, "regime_aligned": False, "created_at": "2026-07-11"},
        {"badge": "WEAK", "created_at": "2026-07-11"},  # no quality_score, no regime_aligned
    ]
    for p in fixtures:
        breakdown = follow_breakdown(p, TODAY)
        assert abs(sum(pts for _, pts in breakdown) - follow_score(p, today=TODAY)) < 1e-9


def test_follow_breakdown_labels_and_zero_components_omitted():
    p = {"badge": "WEAK", "quality_score": 0, "regime_aligned": False, "created_at": "2020-01-01"}
    breakdown = follow_breakdown(p, TODAY)
    labels = [label for label, _ in breakdown]
    assert not any("validated" in label.lower() for label in labels)
    assert breakdown == []  # WEAK + 0 quality + no regime + fully stale -> nothing contributed


def test_out_of_range_quality_score_clamped():
    """Out-of-range quality_score (negative or >100) should be clamped to [0, 100]."""
    # Negative quality_score
    p_neg = {"badge": "VALIDATED", "quality_score": -10, "regime_aligned": True,
             "created_at": "2026-07-11"}
    # Should clamp to 0, contributing 0 to the score
    assert follow_score(p_neg, today=TODAY) == 40 + 0 + 10 + 10  # 60.0

    # Quality score > 100
    p_over = {"badge": "VALIDATED", "quality_score": 150, "regime_aligned": True,
              "created_at": "2026-07-11"}
    # Should clamp to 100, contributing max 40
    assert follow_score(p_over, today=TODAY) == 40 + 40 + 10 + 10  # 100.0

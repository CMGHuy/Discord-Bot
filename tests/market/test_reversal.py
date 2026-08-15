"""evaluate_reversal: the four whipsaw guards, each rejecting in isolation.

A reversal rule with no brakes bleeds money in chop, so the interesting cases
here are the refusals -- including the two "refuse rather than assume" paths
(missing opened_at, missing confidence score), which must never default to
allowing a flip.
"""
from datetime import datetime, timedelta, timezone

import pytest

from swingbot.core.market.reversal import (
    ReversalDecision, evaluate_reversal, reversals_for_ticker)

NOW = datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc)


def _open(direction="bullish", score=60, held_hours=48):
    return {
        "id": "t1", "ticker": "AAPL", "status": "open", "direction": direction,
        "confidence_score": score,
        "opened_at": (NOW - timedelta(hours=held_hours)).isoformat(),
    }


def _flip(hours_ago):
    return {"ticker": "AAPL", "close_reason": "reversed",
            "closed_at": (NOW - timedelta(hours=hours_ago)).isoformat()}


def _ev(existing=None, direction="bearish", score=80, flips=None, **kw):
    return evaluate_reversal(
        existing if existing is not None else _open(),
        direction, score, now=NOW, recent_flips=flips or [], **kw)


def test_allows_a_clean_flip():
    d = _ev()
    assert d.allowed and bool(d) is True
    assert "scores 80 vs 60" in d.reason


def test_disabled_flag_blocks_everything():
    d = _ev(enabled=False)
    assert not d.allowed and "disabled" in d.reason


def test_same_direction_never_flips():
    d = _ev(direction="bullish")
    assert not d.allowed and "opposite direction" in d.reason


def test_non_open_trade_is_not_reversible():
    d = _ev(existing=dict(_open(), status="win"))
    assert not d.allowed and "no open trade" in d.reason


def test_minimum_hold_blocks_a_young_trade():
    d = _ev(existing=_open(held_hours=3), min_hold_hours=24)
    assert not d.allowed and "minimum" in d.reason


def test_cooldown_blocks_a_recent_flip():
    d = _ev(flips=[_flip(hours_ago=5)], cooldown_hours=48, max_per_day=99)
    assert not d.allowed and "cooldown" in d.reason


def test_daily_cap_blocks_even_after_cooldown():
    # cooldown satisfied (0h) but one flip already booked today
    d = _ev(flips=[_flip(hours_ago=1)], cooldown_hours=0, max_per_day=1)
    assert not d.allowed and "today" in d.reason


def test_confidence_margin_blocks_a_marginal_setup():
    d = _ev(score=65, min_conf_margin=10)      # 65 < 60 + 10
    assert not d.allowed and "margin" in d.reason


def test_confidence_margin_boundary_is_inclusive():
    assert _ev(score=70, min_conf_margin=10).allowed      # 70 >= 60 + 10
    assert not _ev(score=69.9, min_conf_margin=10).allowed


def test_missing_opened_at_refuses_rather_than_assumes():
    d = _ev(existing=dict(_open(), opened_at=None))
    assert not d.allowed and "opened_at" in d.reason


def test_unparseable_opened_at_refuses():
    d = _ev(existing=dict(_open(), opened_at="not-a-date"))
    assert not d.allowed


def test_missing_confidence_score_refuses_rather_than_assumes():
    assert not _ev(existing=dict(_open(), confidence_score=None)).allowed
    assert not _ev(score=None).allowed


def test_naive_timestamps_are_treated_as_utc_not_rejected():
    naive = (NOW - timedelta(hours=48)).replace(tzinfo=None).isoformat()
    assert _ev(existing=dict(_open(), opened_at=naive)).allowed


def test_old_flips_outside_cooldown_and_day_do_not_block():
    assert _ev(flips=[_flip(hours_ago=200)], cooldown_hours=48, max_per_day=1).allowed


@pytest.mark.parametrize("kw", [
    {"enabled": False},
    {"min_hold_hours": 999},
    {"min_conf_margin": 999},
])
def test_every_guard_can_veto_on_its_own(kw):
    assert _ev(**kw).allowed is False


def test_reversals_for_ticker_filters_and_orders():
    closed = [
        {"ticker": "AAPL", "close_reason": "reversed", "closed_at": "2026-08-01T00:00:00+00:00"},
        {"ticker": "AAPL", "close_reason": "reversed", "closed_at": "2026-08-05T00:00:00+00:00"},
        {"ticker": "AAPL", "close_reason": "manual", "closed_at": "2026-08-06T00:00:00+00:00"},
        {"ticker": "MSFT", "close_reason": "reversed", "closed_at": "2026-08-06T00:00:00+00:00"},
    ]
    got = reversals_for_ticker(closed, "AAPL")
    assert [t["closed_at"][:10] for t in got] == ["2026-08-05", "2026-08-01"]


def test_decision_is_falsy_when_blocked():
    assert not ReversalDecision(False, "nope")
    assert ReversalDecision(True, "yes")

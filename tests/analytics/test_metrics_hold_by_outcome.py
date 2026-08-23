"""Winner vs loser holding time -- the disposition ratio, applied to a bot."""
from __future__ import annotations

import pytest

from swingbot.core.analytics import metrics


def _t(status, days):
    return {"status": status,
            "opened_at": "2026-01-01T00:00:00",
            "closed_at": f"2026-01-{1 + int(days):02d}T00:00:00"}


def _many(status, days, k):
    return [_t(status, days) for _ in range(k)]


def test_ratio_is_losers_over_winners():
    closed = _many("win", 4, 5) + _many("loss", 8, 5)
    out = metrics.hold_by_outcome(closed)
    assert out["avg_winner_days"] == pytest.approx(4.0)
    assert out["avg_loser_days"] == pytest.approx(8.0)
    assert out["ratio"] == pytest.approx(2.0)


@pytest.mark.parametrize("w,l,expected", [(4, 8, "high"), (4, 5.2, "medium"), (4, 4, "low")])
def test_severity_bands(w, l, expected):
    closed = _many("win", w, 5) + _many("loss", l, 5)
    assert metrics.hold_by_outcome(closed)["severity"] == expected


def test_below_min_trades_ratio_is_none_not_zero():
    closed = _many("win", 4, 2) + _many("loss", 8, 2)
    out = metrics.hold_by_outcome(closed)
    assert out["ratio"] is None
    assert out["severity"] is None
    assert out["n_winners"] == 2


def test_the_floor_applies_to_each_side_independently():
    # Plenty of losers cannot license a ratio built on two winners.
    closed = _many("win", 4, 2) + _many("loss", 8, 40)
    out = metrics.hold_by_outcome(closed)
    assert out["n_losers"] == 40
    assert out["avg_winner_days"] == pytest.approx(4.0)  # still reported
    assert out["ratio"] is None and out["severity"] is None


def test_no_winners_gives_none_rather_than_infinity():
    out = metrics.hold_by_outcome(_many("loss", 8, 6))
    assert out["ratio"] is None
    assert out["avg_winner_days"] is None


def test_scratches_and_timeouts_are_excluded_from_both_sides():
    # They are neither a winner nor a loser; folding them in would make the
    # ratio a statement about horizon length, not exit design.
    closed = _many("win", 4, 5) + _many("loss", 8, 5) + [
        {"status": "closed", "close_reason": "timeout",
         "opened_at": "2026-01-01T00:00:00", "closed_at": "2026-03-01T00:00:00"}]
    out = metrics.hold_by_outcome(closed)
    assert out["n_winners"] == 5 and out["n_losers"] == 5
    assert out["ratio"] == pytest.approx(2.0)


def test_trades_missing_timestamps_are_skipped():
    closed = _many("win", 4, 5) + _many("loss", 8, 5) + [{"status": "loss"}]
    assert metrics.hold_by_outcome(closed)["n_losers"] == 5


def test_empty_input_is_all_none():
    out = metrics.hold_by_outcome([])
    assert out["ratio"] is None and out["n_winners"] == 0

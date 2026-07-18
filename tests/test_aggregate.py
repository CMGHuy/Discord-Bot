import pytest

from swingbot.core.analytics.aggregate import DIMENSIONS, StatRow, stats_by


def _t(strategy_sources, status, pnl, direction="bullish", entry=100.0, stop_loss=95.0, exit_price=None):
    return {"target_sources": strategy_sources, "status": status, "direction": direction,
            "entry": entry, "stop_loss": stop_loss,
            "exit_price": exit_price if exit_price is not None else (104.0 if status == "win" else 96.0),
            "realized_pnl_amount": pnl, "closed_at": "2026-03-10T10:00:00+00:00"}


def test_stats_by_strategy_groups_and_sums():
    closed = [
        _t(["EMA20"], "win", 80.0),
        _t(["EMA20"], "loss", -40.0),
        _t(["Fib 61.8%"], "win", 60.0),
    ]
    rows = stats_by(closed, "strategy")
    assert isinstance(rows[0], StatRow)
    by_key = {r.key: r for r in rows}
    assert by_key["EMA20"].n == 2 and by_key["EMA20"].wins == 1 and by_key["EMA20"].losses == 1
    assert by_key["EMA20"].total_pnl == 40.0
    assert by_key["Fib 61.8%"].n == 1 and by_key["Fib 61.8%"].total_pnl == 60.0


def test_stats_by_missing_pnl_counts_as_zero():
    closed = [_t(["EMA20"], "win", None)]
    rows = stats_by(closed, "strategy")
    assert rows[0].total_pnl == 0.0


def test_stats_by_sorted_by_n_desc():
    closed = [_t(["EMA20"], "win", 10.0), _t(["EMA20"], "loss", -5.0), _t(["Fib 61.8%"], "win", 5.0)]
    rows = stats_by(closed, "strategy")
    assert [r.key for r in rows] == ["EMA20", "Fib 61.8%"]


def _full_trade():
    return {
        "target_sources": ["EMA20"], "status": "win", "direction": "bullish",
        "entry": 100.0, "stop_loss": 95.0, "exit_price": 104.0, "realized_pnl_amount": 80.0,
        "horizon_key": "4w", "tier": "A", "badge": "VALIDATED", "source": "confluence",
        "confidence_level": 4, "ticker": "AAPL",
        # 2026-03-09 is a Monday in both UTC and Europe/Berlin.
        "opened_at": "2026-03-06T10:00:00+00:00", "closed_at": "2026-03-09T10:00:00+00:00",
    }


def test_all_ten_dimensions_present():
    assert set(DIMENSIONS) == {"strategy", "horizon", "tier", "badge", "confidence",
                               "direction", "dow", "month", "ticker", "source"}


def test_dimension_extractors():
    closed = [_full_trade()]
    assert stats_by(closed, "tier")[0].key == "A"
    assert stats_by(closed, "badge")[0].key == "VALIDATED"
    assert stats_by(closed, "source")[0].key == "confluence"
    assert stats_by(closed, "horizon")[0].key == "4w"
    assert stats_by(closed, "confidence")[0].key == "4"
    assert stats_by(closed, "direction")[0].key == "bullish"
    assert stats_by(closed, "ticker")[0].key == "AAPL"
    assert stats_by(closed, "dow")[0].key == "Monday"
    assert stats_by(closed, "month")[0].key == "2026-03"


def test_unknown_fields_bucket_as_unknown():
    closed = [{"target_sources": [], "status": "win", "direction": "bullish",
              "entry": 100.0, "stop_loss": 95.0, "exit_price": 104.0}]
    assert stats_by(closed, "tier")[0].key == "unknown"
    assert stats_by(closed, "badge")[0].key == "unknown"
    assert stats_by(closed, "source")[0].key == "unknown"
    assert stats_by(closed, "confidence")[0].key == "unknown"


def test_stats_by_raises_on_unknown_dimension():
    with pytest.raises(ValueError):
        stats_by([], "nope")

"""`expand_realized_legs` -- every realized leg as its own closed trade.

The Dashboard's chips and the P&L calendar both count a scaled-out position
as one trade per realized leg, the population `get_stats` already counts.
Hand-computed throughout: 10 shares, entry 100, stop 95 (risk 5).
"""
import pytest

from swingbot.core.analytics import metrics
from swingbot.core.tracking.performance import expand_realized_legs


def _trade(*, status="win", legs=(), pnl=75.0, closed_at="2026-08-05T19:00:00+00:00",
           exit_price=107.5):
    return {"id": "t1", "ticker": "AAPL", "direction": "bullish", "status": status,
            "entry": 100.0, "stop_loss": 95.0, "exit_price": exit_price, "shares": 10,
            "realized_pnl_amount": pnl, "opened_at": "2026-08-01T14:00:00+00:00",
            "closed_at": closed_at, "legs": list(legs)}


TP1 = {"fraction": 0.5, "exit_price": 110.0, "r": 2.0, "closed_at": "2026-08-03T15:00:00+00:00"}
RUNNER = {"fraction": 0.5, "exit_price": 105.0, "r": 1.0, "closed_at": "2026-08-05T19:00:00+00:00"}


def test_a_trade_that_never_scaled_out_is_itself():
    [row] = expand_realized_legs(_trade())
    assert (row["leg_index"], row["leg_total"]) == (0, 1)
    assert row["realized_pnl_amount"] == 75.0
    assert row["closed_at"] == "2026-08-05T19:00:00+00:00"


def test_an_open_trade_with_no_legs_has_nothing_realized():
    assert expand_realized_legs(_trade(status="open", pnl=None, closed_at=None)) == []


def test_each_leg_is_its_own_trade_with_its_own_day_outcome_r_and_dollars():
    rows = expand_realized_legs(_trade(legs=[TP1, RUNNER]))
    assert [r["closed_at"][:10] for r in rows] == ["2026-08-03", "2026-08-05"]
    assert [r["status"] for r in rows] == ["win", "win"]
    assert [(r["leg_index"], r["leg_total"]) for r in rows] == [(0, 2), (1, 2)]
    # Each leg's R is its own: (110-100)/5 = +2R, (105-100)/5 = +1R.
    assert [metrics.r_multiple(r) for r in rows] == pytest.approx([2.0, 1.0])
    # 5 shares x +10 = +50, 5 shares x +5 = +25.
    assert [r["realized_pnl_amount"] for r in rows] == pytest.approx([50.0, 25.0])


def test_the_closing_leg_absorbs_the_remainder_so_the_trade_total_never_moves():
    """Legs can disagree with the trade log's own total by a rounding cent
    (or more, on legacy records). The trade's figure stays authoritative."""
    rows = expand_realized_legs(_trade(legs=[TP1, RUNNER], pnl=74.99))
    assert [r["realized_pnl_amount"] for r in rows] == pytest.approx([50.0, 24.99])


def test_the_banked_tp1_leg_of_a_still_open_runner_is_realized():
    rows = expand_realized_legs(_trade(status="open", legs=[TP1], pnl=None, closed_at=None))
    assert len(rows) == 1
    row = rows[0]
    assert row["status"] == "win"
    assert row["closed_at"] == "2026-08-03T15:00:00+00:00"
    assert row["realized_pnl_amount"] == pytest.approx(50.0)
    # The still-open runner is the second of two.
    assert (row["leg_index"], row["leg_total"]) == (0, 2)


def test_a_losing_bearish_leg_prices_against_the_direction():
    legs = [{"fraction": 0.5, "exit_price": 104.0, "r": -0.8, "closed_at": "2026-08-03T15:00:00+00:00"}]
    trade = {**_trade(status="open", legs=legs, pnl=None, closed_at=None),
             "direction": "bearish", "stop_loss": 105.0}
    [row] = expand_realized_legs(trade)
    assert row["status"] == "loss"
    assert row["realized_pnl_amount"] == pytest.approx(-20.0)


def test_the_input_trade_is_not_mutated():
    trade = _trade(legs=[TP1, RUNNER])
    expand_realized_legs(trade)
    assert trade["realized_pnl_amount"] == 75.0
    assert "leg_index" not in trade

import pytest

from swingbot.core.tracking.performance import closed_pnl_pct


def test_no_legs_matches_plain_exit_vs_entry():
    # Every loss (a stop-out closes the whole position at once, before any
    # scale-out could happen) and every legacy/v1 trade takes this path.
    t = {
        "direction": "bullish", "entry": 100.0, "exit_price": 95.0,
        "legs": [],
    }
    assert closed_pnl_pct(t) == pytest.approx(-5.0)


def test_no_legs_bearish_sign_flip():
    t = {
        "direction": "bearish", "entry": 100.0, "exit_price": 95.0,
        "legs": [],
    }
    assert closed_pnl_pct(t) == pytest.approx(5.0)


def test_scaled_out_win_stays_positive_when_runner_gives_back_gain():
    # Reproduces the live production bug: TP1 banked a real gain, the
    # runner then closed at (near) break-even -- realized_pnl_amount is a
    # solid positive $, but the OLD formula (naively pricing off
    # exit_price, which close_plan_trade() sets to only the LAST leg's
    # exit) went negative because the runner's own leg alone lost ground
    # relative to entry. A win trade must never show a negative %.
    t = {
        "direction": "bullish", "entry": 91.59, "exit_price": 91.41,  # last leg only
        "shares": 10.92, "realized_pnl_amount": 3.11,
        "legs": [
            {"fraction": 0.5, "exit_price": 92.34, "reason": "tp1"},
            {"fraction": 0.5, "exit_price": 91.41, "reason": "tp1_runner_be"},
        ],
    }
    pct = closed_pnl_pct(t)
    assert pct is not None
    assert pct > 0, "a winning trade's blended %% must be sign-consistent with its $ gain"
    # realized_pnl_amount / (shares * entry) * 100
    assert pct == pytest.approx(3.11 / (10.92 * 91.59) * 100, abs=0.01)


def test_scaled_out_win_matches_fraction_weighted_average_of_legs():
    t = {
        "direction": "bullish", "entry": 100.0, "exit_price": 100.0,
        "shares": 100.0, "realized_pnl_amount": 17.5,
        "legs": [
            {"fraction": 0.5, "exit_price": 100.35, "r": 0.35, "reason": "tp1"},
            {"fraction": 0.5, "exit_price": 100.0, "r": 0.0, "reason": "tp1_runner_be"},
        ],
    }
    # leg1: +0.35% * 0.5 = 0.175; leg2: 0% * 0.5 = 0 -> blended 0.175%
    assert closed_pnl_pct(t) == pytest.approx(0.175, abs=0.01)


def test_missing_sizing_snapshot_on_legged_trade_returns_none():
    t = {
        "direction": "bullish", "entry": 100.0, "exit_price": 100.0,
        "shares": None, "realized_pnl_amount": None,
        "legs": [{"fraction": 1.0, "exit_price": 105.0, "reason": "tp1"}],
    }
    assert closed_pnl_pct(t) is None


def test_missing_price_data_returns_none():
    assert closed_pnl_pct({"direction": "bullish", "legs": []}) is None
    assert closed_pnl_pct({"direction": "bullish", "entry": 100.0, "legs": []}) is None

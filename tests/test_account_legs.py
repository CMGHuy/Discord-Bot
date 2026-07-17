import json

import pytest

from swingbot.core import account


def test_self_healing_recompute_sums_legs(tmp_path):
    # A two-leg closed trade whose realized_pnl_amount was written by
    # settle_legs: base 10_000, 100 risked, rr=0.35, TP1 on 50% -> +17.50,
    # runner BE -> +0. The self-healing recompute must reproduce +17.50
    # from the record itself.
    trades = [{
        "id": "t1", "ticker": "AAPL", "direction": "bullish", "status": "win",
        "entry": 100.0, "stop_loss": 99.0, "take_profit": 100.35,
        "shares": 100.0,                       # risk 100 @ 1.0/share
        "realized_pnl_amount": 17.50,
        "legs": [
            {"fraction": 0.5, "exit_price": 100.35, "r": 0.35, "reason": "tp1"},
            {"fraction": 0.5, "exit_price": 100.0, "r": 0.0,
             "reason": "tp1_runner_be"},
        ],
    }]
    path = tmp_path / "trades.json"
    path.write_text(json.dumps(trades))
    assert account._sum_realized_pnl(trades_path=str(path)) == pytest.approx(17.50)


def test_recompute_falls_back_to_settle_legs_when_amount_missing(tmp_path):
    # Older v2 rows might carry legs but no realized_pnl_amount (e.g. a crash
    # between leg append and settle) -- the recompute derives it from legs.
    trades = [{
        "id": "t2", "ticker": "AAPL", "direction": "bullish", "status": "win",
        "entry": 100.0, "stop_loss": 99.0, "shares": 100.0,
        "realized_pnl_amount": None,
        "legs": [{"fraction": 0.5, "exit_price": 100.35, "r": 0.35,
                  "reason": "tp1"},
                 {"fraction": 0.5, "exit_price": 100.0, "r": 0.0,
                  "reason": "tp1_runner_be"}],
    }]
    path = tmp_path / "trades.json"
    path.write_text(json.dumps(trades))
    assert account._sum_realized_pnl(trades_path=str(path)) == pytest.approx(17.50)

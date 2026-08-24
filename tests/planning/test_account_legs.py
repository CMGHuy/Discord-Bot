import json

import pytest

from swingbot import config
from swingbot.core.planning import account


def test_account_functions_use_data_dir_at_call_time_not_import_time(tmp_path, monkeypatch):
    """account.py's path defaults used to bake in whatever config.DATA_DIR
    was at MODULE IMPORT time (a module-level `path: str = CONFIG_PATH`
    constant) -- monkeypatching config.DATA_DIR afterwards, the normal test
    isolation pattern, had no effect on any caller that omits `path`
    (e.g. performance.py's _settle_account_balance -> apply_realized_pnl
    with no path= at all). Confirmed live: tests/tracking/
    test_one_trade_per_ticker.py's manual-close/reversal tests passed
    serially (the real data/account.json happened to exist and be valid)
    but failed under xdist parallel workers, which all raced writes to
    that SAME real file at once. Every account.py function must resolve
    DATA_DIR fresh on each call instead."""
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))

    result = account.apply_realized_pnl(50.0, {"trade_id": "t1"})

    # The write must land at tmp_path/account.json -- not wherever a stale,
    # import-time-bound default would have pointed -- with the balance this
    # call actually computed (base_balance + 50), not left at the default.
    on_disk = json.loads((tmp_path / "account.json").read_text())
    assert on_disk["balance"] == pytest.approx(result["balance"])
    assert result["balance"] == pytest.approx(config.ACCOUNT_BALANCE + 50.0)


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


def test_get_balance_history_points_adapts_to_date_balance_tuples(tmp_path):
    # get_balance_history_points() feeds growth_path(), which expects
    # [(date_str, balance), ...] with the date truncated to YYYY-MM-DD.
    cfg = {
        "base_balance": 10_000.0,
        "risk_pct": 1.0,
        "max_open_positions": 5,
        "max_position_pct": 20.0,
        "sizing_mode": "risk_pct",
        "position_pct": 5.0,
        "max_position_value_absolute": 0,
        "max_risk_amount_absolute": 0,
        "balance": 15_000.0,
        "balance_history": [
            {
                "ts": "2025-07-12T00:00:00+00:00",
                "balance": 10_000.0,
                "pnl_amount": None,
                "reason": "account created",
            },
            {
                "ts": "2026-07-12T09:30:00+00:00",
                "balance": 15_000.0,
                "pnl_amount": 5_000.0,
                "reason": "trade settled",
            },
        ],
    }
    path = tmp_path / "account.json"
    path.write_text(json.dumps(cfg))
    points = account.get_balance_history_points(path=str(path))
    assert points == [("2025-07-12", 10_000.0), ("2026-07-12", 15_000.0)]

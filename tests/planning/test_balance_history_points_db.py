"""Balance history comes from timestamptz/numeric columns;
get_balance_history_points() must still hand growth_path() and the scan
kill-switch (date_str, float) pairs."""
from swingbot.core.planning import account
from tests.store_seed import seed_store


def test_history_points_are_date_string_float_pairs():
    seed_store("account", {
        "base_balance": 10_000.0, "risk_pct": 1.0, "balance": 15_000.0,
        "balance_history": [
            {"ts": "2025-07-12T00:00:00+00:00", "balance": 10_000.0,
             "pnl_amount": None, "reason": "account created"},
            {"ts": "2026-07-12T09:30:00+00:00", "balance": 15_000.0,
             "pnl_amount": 5_000.0, "reason": "trade settled"},
        ],
    })
    points = account.get_balance_history_points()
    assert points == [("2025-07-12", 10_000.0), ("2026-07-12", 15_000.0)]
    assert all(isinstance(balance, float) for _, balance in points)

"""The balance history lives in its own table, not in the
account config blob, so get_daily_summary() must read it from there."""
from datetime import datetime, timedelta, timezone

import pytest

from swingbot.core.planning import account
from tests.store_seed import seed_store


def test_daily_summary_reads_history_from_the_history_table():
    now = datetime.now(timezone.utc)
    seed_store("account", {
        "base_balance": 10_100.0, "risk_pct": 1.0,
        "balance_history": [
            {"ts": (now - timedelta(days=3)).isoformat(), "balance": 10_000.0,
             "pnl_amount": None, "reason": "account created"},
            {"ts": now.isoformat(), "balance": 10_100.0,
             "pnl_amount": 100.0, "reason": "trade settled"},
        ],
    })
    summary = account.get_daily_summary()
    assert summary["balance_start_of_day"] == pytest.approx(10_000.0)
    assert summary["pnl_today"] == pytest.approx(100.0)
    assert summary["trades_closed_today"] == 1

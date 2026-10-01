"""At the db stage the balance history lives in its own table, not in the
account config blob, so get_daily_summary() must read it from there."""
from datetime import datetime, timedelta, timezone

import pytest

from swingbot import config
from swingbot.core.planning import account as acct


@pytest.fixture
def db_url(db_engine, monkeypatch):
    monkeypatch.setattr(
        config, "DATABASE_URL", db_engine.url.render_as_string(hide_password=False)
    )
    from swingbot.core.db.engine import reset_engine
    reset_engine()


def _seed(history):
    from swingbot.core.db.repositories.account import AccountRepository
    AccountRepository().save(
        {"base_balance": 10_000.0, "risk_pct": 1.0, "balance_history": history}
    )


def test_daily_summary_reads_history_from_the_history_table(monkeypatch, db_committed, db_url):
    monkeypatch.setattr(config, "DB_STORES", "account:db")
    now = datetime.now(timezone.utc)
    _seed([
        {"ts": (now - timedelta(days=3)).isoformat(), "balance": 10_000.0,
         "pnl_amount": None, "reason": "account created"},
        {"ts": now.isoformat(), "balance": 10_100.0,
         "pnl_amount": 100.0, "reason": "trade settled"},
    ])
    summary = acct.get_daily_summary()
    assert summary["balance_start_of_day"] == pytest.approx(10_000.0)
    assert summary["pnl_today"] == pytest.approx(100.0)
    assert summary["trades_closed_today"] == 1

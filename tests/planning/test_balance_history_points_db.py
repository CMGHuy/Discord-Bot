"""At the db stage balance history lives in its own table and comes back as
datetime/Decimal rows; the account helpers must still hand callers the
json-shaped data (ISO strings, floats) they were written against."""
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


def test_history_points_are_date_string_float_pairs(monkeypatch, db_committed, db_url):
    monkeypatch.setattr(config, "DB_STORES", "account:db")
    _seed([
        {"ts": "2025-07-12T00:00:00+00:00", "balance": 10_000.0,
         "pnl_amount": None, "reason": "account created"},
        {"ts": "2026-07-12T09:30:00+00:00", "balance": 15_000.0,
         "pnl_amount": 5_000.0, "reason": "trade settled"},
    ])
    points = acct.get_balance_history_points()
    assert points == [("2025-07-12", 10_000.0), ("2026-07-12", 15_000.0)]
    assert all(isinstance(balance, float) for _, balance in points)

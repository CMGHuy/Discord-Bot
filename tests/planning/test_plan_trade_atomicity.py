"""Several repository writes share one transaction when callers opt in."""
import pytest

from swingbot import config
from swingbot.core.db.engine import transaction
from swingbot.core.db.repositories.plans import PlanRepository
from swingbot.core.db.repositories.trades import TradeRepository


@pytest.fixture
def db_url(monkeypatch, db_engine):
    from swingbot.core.db import engine as db_engine_module
    monkeypatch.setattr(config, "DATABASE_URL", db_engine.url.render_as_string(hide_password=False))
    db_engine_module.reset_engine()
    yield
    db_engine_module.reset_engine()


def _seed(conn):
    PlanRepository().insert({"plan_id": "P1", "ticker": "AAPL", "strategy": "RSI",
                             "horizon_key": "2w", "status": "ACTIVE",
                             "created_at": "2026-01-02T15:00:00+00:00"}, conn=conn)
    TradeRepository().insert({"trade_id": "T1", "ticker": "AAPL", "strategy": "RSI",
                              "horizon": "2w", "direction": "bullish", "status": "open",
                              "opened_at": "2026-01-02T15:00:00+00:00", "plan_id": "P1"}, conn=conn)


def test_transaction_commits_or_rolls_back_every_write(db_committed, db_url):
    _seed(db_committed)
    db_committed.commit()
    with pytest.raises(RuntimeError):
        with transaction() as conn:
            PlanRepository().patch("P1", {"status": "CLOSED"}, conn=conn)
            TradeRepository().patch("T1", {"status": "win"}, conn=conn)
            raise RuntimeError("simulate the second write failing")
    assert PlanRepository().get("P1", conn=db_committed)["status"] == "ACTIVE"
    assert TradeRepository().get("T1", conn=db_committed)["status"] == "open"

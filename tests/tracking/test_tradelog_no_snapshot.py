"""TradeLog holds no snapshot: a long-lived instance reads the table each time."""
from swingbot.core.db.repositories.trades import TradeRepository
from swingbot.core.tracking.performance import TradeLog


def _record(trade_id):
    return {"trade_id": trade_id, "ticker": "AAPL", "strategy": "RSI", "horizon": "2w",
            "direction": "bullish", "status": "open", "opened_at": "2026-01-02T15:00:00+00:00"}


def test_long_lived_instance_sees_new_rows():
    log = TradeLog()
    assert log.get_trades(status="open", limit=None) == []
    TradeRepository().upsert(_record("LATER"))
    assert [row["id"] for row in log.get_trades(status="open", limit=None)] == ["LATER"]

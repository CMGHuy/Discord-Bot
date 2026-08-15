import json
from unittest.mock import patch

from swingbot.core.performance import TradeLog


def _near_tp_trade(plan_id=None):
    t = {"id": "t1", "ticker": "AAPL", "direction": "bullish", "status": "open",
         "entry": 100.0, "stop_loss": 95.0, "take_profit": 110.0,
         "opened_at": "2026-07-01T10:00:00+00:00",
         "near_tp_since": "2026-07-01T10:00:00+00:00", "near_tp_snapshots": []}
    if plan_id:
        t["plan_id"] = plan_id
    return t


def test_manager_owned_trades_skip_near_tp_timeout(tmp_path, monkeypatch):
    monkeypatch.setattr("swingbot.core.analytics.journal.config.DATA_DIR", str(tmp_path))
    path = tmp_path / "trades.json"
    path.write_text(json.dumps([_near_tp_trade(plan_id="p1")]))
    log = TradeLog(path=str(path))
    with patch("swingbot.core.data.get_daily_data", return_value=None):
        # 109.5 = 95% of the way to target; stall clock long expired
        closed = log.check_near_tp_timeout("AAPL", live_price=109.5)
    assert closed == []                       # runner/trail owns this decision


def test_legacy_trades_still_timeout(tmp_path, monkeypatch):
    monkeypatch.setattr("swingbot.core.analytics.journal.config.DATA_DIR", str(tmp_path))
    path = tmp_path / "trades.json"
    path.write_text(json.dumps([_near_tp_trade()]))
    log = TradeLog(path=str(path))
    with patch("swingbot.core.data.get_daily_data", return_value=None):
        closed = log.check_near_tp_timeout("AAPL", live_price=109.5)
    assert len(closed) == 1                   # unchanged legacy behavior

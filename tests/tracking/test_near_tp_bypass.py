import json
from unittest.mock import patch

from swingbot.core.tracking.performance import TradeLog
from swingbot.core.presentation import tokens
from swingbot.core.scanning.lifecycle_embeds import build_near_close_embed


def _near_tp_trade(plan_id=None):
    t = {"id": "t1", "ticker": "AAPL", "direction": "bullish", "status": "open",
         "entry": 100.0, "stop_loss": 95.0, "take_profit": 110.0,
         "strategy": "RSI Pullback", "horizon_key": "2w",
         "confidence_label": "High", "confidence_level": 4,
         "opened_at": "2026-07-01T10:00:00+00:00",
         "near_tp_since": "2026-07-01T10:00:00+00:00", "near_tp_snapshots": []}
    if plan_id:
        t["plan_id"] = plan_id
    return t


def _warning(which: str):
    return {"trade": _near_tp_trade(), "near_which": which,
            "sl_dist_pct": 1.0, "tp_dist_pct": 1.0, "current_price": 105.0}


def test_near_stop_warns_in_the_ramps_red():
    assert build_near_close_embed(_warning("stop-loss")).color.value == tokens.ACCENT_RAMP[1]


def test_near_target_uses_the_ramps_green_and_explicit_title():
    stop = build_near_close_embed(_warning("stop-loss"))
    target = build_near_close_embed(_warning("take-profit"))
    assert target.color.value == tokens.ACCENT_RAMP[5]
    assert "stop" in stop.title.lower()


def test_manager_owned_trades_skip_near_tp_timeout(tmp_path, monkeypatch):
    monkeypatch.setattr("swingbot.core.analytics.journal.config.DATA_DIR", str(tmp_path))
    path = tmp_path / "trades.json"
    path.write_text(json.dumps([_near_tp_trade(plan_id="p1")]))
    log = TradeLog(path=str(path))
    with patch("swingbot.core.marketdata.data.get_daily_data", return_value=None):
        # 109.5 = 95% of the way to target; stall clock long expired
        closed = log.check_near_tp_timeout("AAPL", live_price=109.5)
    assert closed == []                       # runner/trail owns this decision


def test_legacy_trades_still_timeout(tmp_path, monkeypatch):
    monkeypatch.setattr("swingbot.core.analytics.journal.config.DATA_DIR", str(tmp_path))
    path = tmp_path / "trades.json"
    path.write_text(json.dumps([_near_tp_trade()]))
    log = TradeLog(path=str(path))
    with patch("swingbot.core.marketdata.data.get_daily_data", return_value=None):
        closed = log.check_near_tp_timeout("AAPL", live_price=109.5)
    assert len(closed) == 1                   # unchanged legacy behavior

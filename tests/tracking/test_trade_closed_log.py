"""v111 §3: every trade close logs outcome, realised R and hold days at INFO."""
import logging
import re

from swingbot.core.tracking import performance as perf
from swingbot.core.tracking.performance import TradeLog
from tests.store_seed import seed_store


def _closed_lines(caplog):
    return [r.getMessage() for r in caplog.records
            if r.name == perf.log.name and r.getMessage().startswith("Trade closed:")]


def test_close_plan_trade_logs_outcome_r_and_hold(monkeypatch, caplog):
    trades = TradeLog()
    seed_store("trades", [{
        "id": "t-close-123456789", "plan_id": "p-close", "ticker": "AAPL",
        "status": "open", "direction": "bullish", "entry": 100.0,
        "stop_loss": 95.0, "shares": None, "legs": [], "horizon_key": "2w", "strategy": "RSI",
        "opened_at": "2026-09-20T14:00:00+00:00",
    }])
    monkeypatch.setattr(perf, "_journal_close_safely", lambda trade: None)
    monkeypatch.setattr(perf, "_refresh_snapshot_safely", lambda: None)

    with caplog.at_level(logging.INFO, logger=perf.log.name):
        trades.close_plan_trade("p-close", {"fraction": 1.0, "exit_price": 105.0, "r": 1.0}, "win")

    [line] = _closed_lines(caplog)
    assert re.fullmatch(r"Trade closed: AAPL bullish id=t-close- outcome=win R=\+1\.00 hold=\d+\.\dd", line)


def test_the_journal_hook_still_runs_after_the_line(monkeypatch):
    journaled = []
    trades = TradeLog()
    seed_store("trades", [{"id": "t1", "plan_id": "p1", "ticker": "MSFT", "status": "open",
                           "direction": "bearish", "entry": 100.0, "stop_loss": 105.0,
                           "shares": None, "legs": [], "horizon_key": "2w", "strategy": "RSI",
                           "opened_at": "2026-09-20T14:00:00+00:00"}])
    monkeypatch.setattr(perf, "_journal_close_safely", journaled.append)
    monkeypatch.setattr(perf, "_refresh_snapshot_safely", lambda: None)

    trades.close_plan_trade("p1", {"fraction": 1.0, "exit_price": 105.0, "r": -1.0}, "loss")

    assert [t["id"] for t in journaled] == ["t1"]


def test_missing_fields_log_n_a_rather_than_raise(caplog):
    with caplog.at_level(logging.INFO, logger=perf.log.name):
        perf._log_trade_closed({"status": "closed", "ticker": "X"})
    assert _closed_lines(caplog) == ["Trade closed: X - id=- outcome=closed R=n/a hold=n/a"]


def test_hold_days_is_none_for_bad_timestamps():
    assert perf._hold_days({"opened_at": "2026-09-20T14:00:00+00:00", "closed_at": "garbage"}) is None
    assert perf._hold_days({"opened_at": "2026-09-20T14:00:00", "closed_at": "2026-09-21T14:00:00+00:00"}) is None
    assert perf._hold_days({"opened_at": "2026-09-20T00:00:00+00:00",
                            "closed_at": "2026-09-22T12:00:00+00:00"}) == 2.5

"""Reply-parity cases for swingbot/commands/trades.py (v153 SP10, SP11).

`trade_log` is replaced by an in-memory _FakeLog; chart rendering returns a
tiny PNG on disk (discord.File opens it); the currency lookup is fixed; the
embed clock is frozen because apply_chrome stamps utcnow().
"""
import datetime as dt
import os
import tempfile

import discord

from swingbot.commands import trades as trades_mod
from tests.commands.reply_harness import ParityCase

_NOW = dt.datetime(2026, 10, 9, 14, 30, tzinfo=dt.timezone.utc)

OPEN_TRADE = {
    "id": "T0001", "ticker": "AAPL", "strategy": "S/R Confluence",
    "target_sources": ["Fibonacci 61.8%"], "stop_sources": [], "horizon_key": "4w",
    "direction": "bullish", "confidence_level": 4, "entry": 180.0, "stop_loss": 172.0,
    "take_profit": 196.0, "target2": 204.0, "risk_reward_ratio": 2.0, "status": "open",
    "opened_at": "2026-10-09T08:45:00+00:00", "shares": 5, "plan_id": "p-aapl-0001",
}
WIN_TRADE = {
    "id": "T0002", "ticker": "MSFT", "strategy": "S/R Confluence",
    "target_sources": [], "stop_sources": [], "horizon_key": "2w",
    "direction": "bearish", "confidence_level": 3, "entry": 430.0, "stop_loss": 440.0,
    "take_profit": 410.0, "status": "win", "opened_at": "2026-10-06T09:00:00+00:00",
    "closed_at": "2026-10-09T13:10:00+00:00", "exit_price": 412.0,
    "realized_pnl_amount": 90.0, "shares": 5, "close_reason": "TP1 hit",
}
LOSS_TRADE = {
    **WIN_TRADE, "id": "T0003", "ticker": "NVDA", "status": "loss", "direction": "bullish",
    "entry": 120.0, "stop_loss": 114.0, "take_profit": 132.0, "exit_price": 114.0,
    "realized_pnl_amount": -30.0, "close_reason": "stop hit",
}
ALL_TRADES = [OPEN_TRADE, WIN_TRADE, LOSS_TRADE]


class _FakeLog:
    """The slice of TradeLog that trades.py calls."""

    def __init__(self, trades):
        self.trades = list(trades)

    def get_trades(self, status="all", limit=None, sort_by=None, ledger=None):
        rows = [t for t in self.trades if status == "all" or t["status"] == status]
        return rows[:limit] if limit else rows

    def clear_open(self):
        return sum(1 for t in self.trades if t["status"] == "open")

    def clear_history(self):
        return sum(1 for t in self.trades if t["status"] != "open")

    def get_trade_by_id(self, trade_id):
        return next((t for t in self.trades if t["id"] == trade_id), None)

    def delete_trade(self, trade_id):
        return self.get_trade_by_id(trade_id) is not None

    def get_stats(self, level=None, ledger=None):
        rows = [t for t in self.trades if level is None or t["confidence_level"] == level]
        wins = sum(1 for t in rows if t["status"] == "win")
        losses = sum(1 for t in rows if t["status"] == "loss")
        closed = wins + losses
        return {"total": len(rows), "open": sum(1 for t in rows if t["status"] == "open"),
                "closed": closed, "wins": wins, "losses": losses,
                "win_rate": wins / closed * 100 if closed else None}

    def get_stats_by_confidence(self):
        return {lvl: self.get_stats(lvl) for lvl in range(1, 6)}

    def weak_summary(self):
        return {"wins": 1, "losses": 2, "n": 3, "total_pnl": -12.5}


def _freeze_clock(monkeypatch):
    monkeypatch.setattr(discord.utils, "utcnow", lambda: _NOW)


def _png(name: str) -> str:
    path = os.path.join(tempfile.mkdtemp(prefix="v153-trades-"), name)
    with open(path, "wb") as fh:
        fh.write(b"\x89PNG\r\n\x1a\n")
    return path


def _chart_for_open(trade):
    return _png(f"{trade['id']}_chart.png") if trade["status"] == "open" else None


def _stub(trades=ALL_TRADES, chart=_chart_for_open):
    def stub(monkeypatch):
        monkeypatch.setattr(trades_mod, "trade_log", _FakeLog(trades))
        monkeypatch.setattr(trades_mod.scan_engine, "regenerate_chart_for_trade", chart)
        monkeypatch.setattr(trades_mod, "get_currency_symbol", lambda ticker, default: "$")
        _freeze_clock(monkeypatch)
    return stub


CASES = [
    ParityCase("trades_all", trades_mod.handle_trades, stub=_stub()),
    ParityCase("trades_open_two_per_page", trades_mod.handle_trades, args=("open", 2), stub=_stub()),
    ParityCase("trades_empty", trades_mod.handle_trades, args=("win",), stub=_stub([OPEN_TRADE])),
    ParityCase("trades_bad_status", trades_mod.handle_trades, args=("pending",),
               stub=_stub(), expect="error"),
    ParityCase("trades_clear", trades_mod.handle_trades_clear, stub=_stub()),
    ParityCase("trades_clear_history", trades_mod.handle_trades_clear_history, stub=_stub()),
    ParityCase("trade_show_with_chart", trades_mod.handle_trade_show, args=("T0001",), stub=_stub()),
    ParityCase("trade_show_closed_no_chart", trades_mod.handle_trade_show, args=("T0002",), stub=_stub()),
    ParityCase("trade_show_missing", trades_mod.handle_trade_show, args=("NOPE",),
               stub=_stub(), expect="error"),
    ParityCase("trade_delete", trades_mod.handle_trade_delete, args=("T0003",), stub=_stub()),
    ParityCase("trade_delete_missing", trades_mod.handle_trade_delete, args=("NOPE",),
               stub=_stub(), expect="error"),
    ParityCase("tradecharts_all", trades_mod.handle_tradecharts, args=("all", 3),
               stub=_stub(), expect="multi_send"),
    ParityCase("tradecharts_empty", trades_mod.handle_tradecharts, args=("loss",),
               stub=_stub([OPEN_TRADE])),
    ParityCase("tradecharts_bad_status", trades_mod.handle_tradecharts, args=("pending",),
               stub=_stub(), expect="error"),
]

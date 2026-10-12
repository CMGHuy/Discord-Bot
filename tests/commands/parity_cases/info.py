"""Reply-parity cases for swingbot/commands/info.py (v153 SP9).

Data seams are stubbed: the snapshot worker, the regime, the chart worker,
daily data and the currency lookup. `ui.apply_chrome` stamps
discord.utils.utcnow() on the /help embed, so that case freezes the clock.
"""
import datetime as dt
import os
import tempfile
import types

import discord
import pandas as pd

from swingbot.commands import info as info_mod
from swingbot.core.planning import plan_engine
from tests.commands.reply_harness import ParityCase

_NOW = dt.datetime(2026, 10, 9, 14, 30, tzinfo=dt.timezone.utc)
_REGIME = types.SimpleNamespace(
    label="Bullish (above 200EMA)", ticker="SPY", close=571.2, ema200=540.0,
    pct_above_ema=5.8, ema_slope_pct=0.42,
)
_PLAN = types.SimpleNamespace(
    strategy="MACD", horizon_key="4w", badge="VALIDATED", badge_stats={"win_rate": 61.2},
    trigger_price=159.5, stop_loss=150.0, tp1=170.0, tp2=181.25,
)


def _freeze_clock(monkeypatch):
    monkeypatch.setattr(discord.utils, "utcnow", lambda: _NOW)


def _df(rows: int = 60) -> pd.DataFrame:
    return pd.DataFrame({
        "Close": [100.0 + i for i in range(rows)],
        "Volume": [1_000_000 + i for i in range(rows)],
    })


def _result(strategy: str, horizon: str, trend: str, triggered: bool):
    return types.SimpleNamespace(strategy=strategy, horizon_key=horizon, trend=trend, triggered=triggered)


def _png(name: str) -> str:
    path = os.path.join(tempfile.mkdtemp(prefix="v153-info-"), name)
    with open(path, "wb") as fh:
        fh.write(b"\x89PNG\r\n\x1a\n")
    return path


def _stub_ping(monkeypatch):
    # bot.latency is NaN while the bot is not connected; round(NaN) raises.
    monkeypatch.setattr(info_mod, "bot", types.SimpleNamespace(latency=0.042))


def _stub_regime(regime):
    def stub(monkeypatch):
        monkeypatch.setattr(info_mod.scan_engine, "get_regime", lambda: regime)
    return stub


def _stub_ticker(results, plan=None):
    def stub(monkeypatch):
        monkeypatch.setattr(info_mod, "_sync_ticker_snapshot", lambda ticker: (_df(), results, _REGIME))
        monkeypatch.setattr(plan_engine, "build_strategy_plan", lambda *a, **k: plan)
    return stub


def _ticker_down(monkeypatch):
    def boom(ticker):
        raise RuntimeError("yahoo down")
    monkeypatch.setattr(info_mod, "_sync_ticker_snapshot", boom)


def _stub_charts(rows: int = 400, paths=lambda: {
        "EMA": _png("AAPL_strategy_EMA.png"), "VWAP": _png("AAPL_strategy_VWAP.png")}):
    def stub(monkeypatch):
        monkeypatch.setattr(info_mod, "get_daily_data", lambda ticker, period: _df(rows))
        monkeypatch.setattr(info_mod, "get_currency_symbol", lambda ticker, default: "$")
        monkeypatch.setattr(info_mod, "_sync_strategy_charts", lambda *a: paths())
    return stub


def _charts_down(monkeypatch):
    def boom(ticker, period):
        raise RuntimeError("no data")
    monkeypatch.setattr(info_mod, "get_daily_data", boom)


_TRIGGERED = [_result("MACD", "4w", "bullish", True), _result("RSI", "2w", "bearish", False)]
_MANY = [_result(f"Strategy{i:02d}", "4w", "bullish", False) for i in range(80)]

CASES = [
    ParityCase("info_strategies", info_mod.handle_strategies),
    ParityCase("info_confidence", info_mod.handle_confidence),
    ParityCase("info_ping", info_mod.handle_ping, stub=_stub_ping),
    ParityCase("info_help", info_mod.handle_help, stub=_freeze_clock),
    ParityCase("info_regime", info_mod.handle_regime, stub=_stub_regime(_REGIME)),
    ParityCase("info_regime_unavailable", info_mod.handle_regime,
               stub=_stub_regime(None), expect="error"),
    ParityCase("info_ticker_no_setup", info_mod.handle_ticker, args=("aapl",),
               stub=_stub_ticker(_TRIGGERED), fail_stub=_ticker_down, expect="multi_send"),
    ParityCase("info_ticker_with_plan", info_mod.handle_ticker, args=("aapl",),
               stub=_stub_ticker(_TRIGGERED, _PLAN), expect="multi_send"),
    ParityCase("info_ticker_long_message", info_mod.handle_ticker, args=("aapl",),
               stub=_stub_ticker(_MANY), expect="multi_send"),
    ParityCase("info_strategycharts", info_mod.handle_strategycharts, args=("aapl", "4w", "bullish"),
               stub=_stub_charts(), fail_stub=_charts_down, expect="multi_send"),
    ParityCase("info_strategycharts_no_paths", info_mod.handle_strategycharts, args=("aapl",),
               stub=_stub_charts(paths=dict), expect="multi_send"),
    ParityCase("info_strategycharts_short_history", info_mod.handle_strategycharts, args=("aapl",),
               stub=_stub_charts(rows=5), expect="error"),
    ParityCase("info_strategycharts_bad_horizon", info_mod.handle_strategycharts,
               args=("aapl", "zz"), expect="error"),
    ParityCase("info_strategycharts_bad_direction", info_mod.handle_strategycharts,
               args=("aapl", "4w", "sideways"), expect="error"),
]

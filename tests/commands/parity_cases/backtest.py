"""Reply-parity cases for swingbot/commands/backtest.py (v153 SP13)."""
from types import SimpleNamespace

from swingbot.commands import backtest as backtest_mod
from tests.commands.reply_harness import ParityCase

_TRADE = SimpleNamespace(outcome="win", r_multiple=1.2, exit_date="2024-02-01", direction="bullish",
                         entry=100.0, stop_loss=95.0, take_profit=110.0, entry_date="2024-01-15")


def _summary(ticker="AAA", strategy=None, evaluated=6, trades=()):
    return SimpleNamespace(
        ticker=ticker, strategy=strategy or backtest_mod.ALL_STRATEGIES[0], horizon_key="4w",
        total_signals=8, evaluated=evaluated, scratches=1, timeouts=1, wins=evaluated - 1, losses=1,
        win_rate=66.7, expectancy_r=0.35, max_drawdown_pct=9.5, avg_holding_days=6.0,
        trades=list(trades),
    )


def _stub_one(summaries):
    def stub(monkeypatch):
        monkeypatch.setattr(backtest_mod, "_sync_backtest_one", lambda *a: (250, list(summaries)))
    return stub


def _fetch_fails(monkeypatch):
    def boom(*a):
        raise RuntimeError("yahoo down")
    monkeypatch.setattr(backtest_mod, "_sync_backtest_one", boom)


def _stub_watchlist(summaries, errors=()):
    def stub(monkeypatch):
        monkeypatch.setattr(backtest_mod, "load_watchlist", lambda: ["AAA", "BBB", "CCC"])
        monkeypatch.setattr(backtest_mod, "_sync_backtest_watchlist",
                            lambda *a: (list(summaries), list(errors)))
    return stub


_ONE = [_summary()]
_WITH_TRADES = [_summary(trades=[_TRADE, _TRADE])]
# 40 strategy rows push the table past the 1950-char single-message limit.
_MANY = [_summary(strategy=backtest_mod.ALL_STRATEGIES[i % len(backtest_mod.ALL_STRATEGIES)])
         for i in range(40)]
_BOARD = [_summary("AAA"), _summary("BBB", evaluated=9), _summary("CCC", evaluated=2)]
_THIN = [_summary("AAA", evaluated=2), _summary("BBB", evaluated=3)]

CASES = [
    ParityCase("backtest_table", backtest_mod.handle_backtest, args=("aapl",),
               stub=_stub_one(_ONE), fail_stub=_fetch_fails, expect="multi_send"),
    ParityCase("backtest_setups_in_range", backtest_mod.handle_backtest, args=("aapl", "4w", "MACD"),
               kwargs={"date_from": "2024-01-01", "date_to": "2024-06-30", "list_setups": True},
               stub=_stub_one(_WITH_TRADES), expect="multi_send"),
    ParityCase("backtest_long_table_chunks", backtest_mod.handle_backtest, args=("aapl",),
               stub=_stub_one(_MANY), expect="multi_send"),
    ParityCase("backtest_fetch_fails", backtest_mod.handle_backtest, args=("aapl",),
               stub=_fetch_fails, expect="error"),
    ParityCase("backtestwatchlist_leaderboard", backtest_mod.handle_backtestwatchlist,
               stub=_stub_watchlist(_BOARD), expect="multi_send"),
    ParityCase("backtestwatchlist_skips_and_no_combo", backtest_mod.handle_backtestwatchlist,
               kwargs={"date_from": "2024-01-01"},
               stub=_stub_watchlist(_THIN, errors=[("DDD", "no data")]), expect="multi_send"),
]

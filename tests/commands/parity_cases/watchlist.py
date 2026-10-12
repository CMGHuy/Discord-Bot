"""Reply-parity cases for swingbot/commands/watchlist.py (v153 SP14).

The spec's /watchlist edge cases are here as `expect="error"` cases: a
missing ticker for add and for remove, and an unknown action, must give the
same send_error text on both surfaces."""
from swingbot.commands import watchlist as watchlist_mod
from tests.commands.reply_harness import ParityCase


def _stub(tickers=("AAPL", "MSFT"), fetch_fails=False):
    def stub(monkeypatch):
        monkeypatch.setattr(watchlist_mod, "load_watchlist", lambda: list(tickers))
        monkeypatch.setattr(watchlist_mod, "add_ticker", lambda t: [*tickers, t])
        monkeypatch.setattr(watchlist_mod, "remove_ticker", lambda t: [x for x in tickers if x != t])
        monkeypatch.setattr(watchlist_mod, "clear_watchlist", lambda: None)
        monkeypatch.setattr(watchlist_mod, "ensure_cached_background", lambda t: None)

        def fetch(ticker, period):
            if fetch_fails:
                raise RuntimeError("no such symbol")
            return None
        monkeypatch.setattr(watchlist_mod, "get_daily_data", fetch)
    return stub


CASES = [
    ParityCase("watchlist_show", watchlist_mod.handle_watchlist, stub=_stub()),
    ParityCase("watchlist_show_empty", watchlist_mod.handle_watchlist, args=("show",), stub=_stub(())),
    ParityCase("watchlist_add_lowercase", watchlist_mod.handle_watchlist, args=("add", "nvda"), stub=_stub()),
    ParityCase("watchlist_add_fetch_fails", watchlist_mod.handle_watchlist, args=("add", "gold"),
               stub=_stub(fetch_fails=True), expect="multi_send"),
    ParityCase("watchlist_remove", watchlist_mod.handle_watchlist, args=("remove", "msft"), stub=_stub()),
    ParityCase("watchlist_clear", watchlist_mod.handle_watchlist, args=("clear",), stub=_stub()),
    ParityCase("watchlist_add_missing_ticker", watchlist_mod.handle_watchlist, args=("add",),
               stub=_stub(), expect="error"),
    ParityCase("watchlist_remove_missing_ticker", watchlist_mod.handle_watchlist, args=("remove", ""),
               stub=_stub(), expect="error"),
    ParityCase("watchlist_unknown_action", watchlist_mod.handle_watchlist, args=("rename", "AAPL"),
               stub=_stub(), expect="error"),
]

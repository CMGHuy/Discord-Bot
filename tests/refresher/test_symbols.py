"""v201: the refresher's symbol set -- open trades, open plans, watchlist, tape."""
from swingbot.core.marketdata.shared import tape
from swingbot.refresher import symbols


def test_union_is_upper_cased_deduped_sorted_and_the_tape_is_separate(monkeypatch):
    monkeypatch.setattr(symbols, "_open_trade_tickers", lambda: ["aapl", " MSFT ", None])
    monkeypatch.setattr(symbols, "_open_plan_tickers", lambda: ["MSFT", "nvda", ""])
    monkeypatch.setattr(symbols, "_watchlist", lambda: ["AAPL", "XAUUSD", "^GSPC"])
    got = symbols.symbol_set()
    assert got.quotes == ("AAPL", "MSFT", "NVDA", "XAUUSD")
    assert got.index == tuple(tape.TAPE_FIXED)
    assert got.held == ("AAPL", "MSFT", "NVDA")      # the watchlist-only XAUUSD is not held


def test_empty_book_still_refreshes_the_tape(monkeypatch):
    for name in ("_open_trade_tickers", "_open_plan_tickers", "_watchlist"):
        monkeypatch.setattr(symbols, name, lambda: [])
    assert symbols.symbol_set() == symbols.SymbolSet((), tuple(tape.TAPE_FIXED))

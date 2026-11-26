"""v201: the quote and FX steps, their marks, and the market NOTIFYs (marks set, values landed)."""
import pathlib
from datetime import datetime, timedelta, timezone

import pytest

from swingbot import config
from swingbot.admin.market_values import MarketQuote
from swingbot.core.marketdata.shared.kinds import Asker, QuoteDetail
from swingbot.refresher import loop, quotes
from swingbot.refresher.symbols import SymbolSet
from tests.refresher.test_loop import FakeBeat, FakeQueue

UTC = timezone.utc
REGULAR = datetime(2026, 10, 28, 15, 0, tzinfo=UTC)
REPO = pathlib.Path(__file__).resolve().parents[2]


class FakeMarks:
    def __init__(self):
        self.events = []

    def mark(self, keys, *, timeout_s, now=None, conn=None):
        self.events.append(("mark", tuple(keys), timeout_s))

    def clear(self, keys, *, error=None, now=None, conn=None):
        if keys:
            self.events.append(("clear", tuple(keys), error))


@pytest.fixture
def cycle(monkeypatch):
    marks, published, batches, tapes = FakeMarks(), [], [], []

    def batch(tickers, *, yf_limit):
        batches.append((list(tickers), yf_limit))
        return {t: QuoteDetail(t, 1.0, REGULAR, None, None, REGULAR,
                               "yfinance-1m" if t == "YF" else "alpaca-iex")
                for t in tickers if t != "BAD"}
    monkeypatch.setattr(quotes, "refresh_mark_repo", lambda: marks)
    monkeypatch.setattr(quotes.data, "refresh_quote_batch", batch)
    monkeypatch.setattr(quotes.tape, "refresh_tape",
                        lambda syms, *, asker, max_age_s=None: tapes.append((list(syms), asker)) or {})
    monkeypatch.setattr(loop, "refresh_queue_repo", FakeQueue)
    monkeypatch.setattr(loop, "refresher_heartbeat_repo", FakeBeat)
    monkeypatch.setattr(loop, "symbol_set", lambda: SymbolSet(("AAPL", "BAD", "YF"), ("^GSPC",)))
    monkeypatch.setattr(loop, "_scan_running", lambda: False)
    # tests/conftest.py forces MARKETDATA_LAYER off; the cycle idles under that kill switch.
    monkeypatch.setattr(loop.config, "ADMIN_REFRESHER", "on")
    monkeypatch.setattr(loop.config, "MARKETDATA_LAYER", "on")
    monkeypatch.setattr(loop, "_last_full", None)
    monkeypatch.setattr(loop, "STEPS", [quotes.quote_step])
    monkeypatch.setattr(loop.notify, "publish", published.append)
    monkeypatch.setattr(quotes, "_held_primed", False)
    monkeypatch.setattr(quotes.market_values, "read_quotes", lambda symbols, **kw: {})
    return marks, published, batches, tapes


def test_failed_symbol_clears_mark_with_error(cycle):
    marks, published, batches, tapes = cycle
    report = loop.run_cycle(REGULAR)
    assert batches == [(["AAPL", "BAD", "YF"], 150)]
    assert ("clear", ("quote:AAPL", "quote:YF"), None) in marks.events
    assert ("clear", ("quote:BAD",), "no quote") in marks.events
    assert marks.events[0] == ("mark", ("quote:AAPL", "quote:BAD", "quote:YF"), 120.0)
    assert (report.quotes_ok, report.quotes_missed, report.fallback_used) == (("AAPL", "YF"), ("BAD",), 1)
    assert tapes == [(["^GSPC"], Asker.ADMIN_REFRESH)]
    assert published == ["market", "market"] and report.changed is True   # marks set, then values landed


def test_provider_raises_keeps_last_values_and_still_beats(cycle, monkeypatch):
    marks, published, _batches, _tapes = cycle
    beats = FakeBeat()
    monkeypatch.setattr(loop, "refresher_heartbeat_repo", lambda: beats)

    def down(tickers, *, yf_limit):
        raise RuntimeError("alpaca 503")
    monkeypatch.setattr(quotes.data, "refresh_quote_batch", down)
    report = loop.run_cycle(REGULAR)
    assert report.error == "RuntimeError: alpaca 503"
    assert ("clear", ("quote:AAPL", "quote:BAD", "quote:YF"), "RuntimeError: alpaca 503") in marks.events
    assert beats.beats[-1]["last_error"] == "RuntimeError: alpaca 503"


def test_scan_running_skips_yfinance_and_the_yahoo_tape(cycle, monkeypatch):
    marks, _published, batches, tapes = cycle
    monkeypatch.setattr(loop, "_scan_running", lambda: True)
    loop.run_cycle(REGULAR)
    assert batches[0][1] == 0 and tapes == []
    assert ("clear", ("quote:BAD",), "no quote (yfinance fallback skipped during a scan)") in marks.events


def test_scan_running_keeps_yfinance_for_held_symbols_only(cycle, monkeypatch):
    marks, _published, batches, _tapes = cycle
    monkeypatch.setattr(loop, "_scan_running", lambda: True)
    monkeypatch.setattr(loop, "symbol_set",
                        lambda: SymbolSet(("AAPL", "BAD", "YF"), ("^GSPC",), ("BAD", "YF")))
    loop.run_cycle(REGULAR)
    assert batches == [(["BAD", "YF"], 150), (["AAPL"], 0)]
    # BAD is held and still missed: a plain miss, not "skipped during a scan".
    assert ("clear", ("quote:BAD",), "no quote") in marks.events


def test_scan_running_with_nothing_held_makes_one_batch_without_yfinance(cycle, monkeypatch):
    _marks, _published, batches, _tapes = cycle
    monkeypatch.setattr(loop, "_scan_running", lambda: True)
    loop.run_cycle(REGULAR)
    assert batches == [(["AAPL", "BAD", "YF"], 0)]


def test_nothing_to_do_publishes_nothing(cycle, monkeypatch):
    _marks, published, batches, _tapes = cycle
    monkeypatch.setattr(loop, "symbol_set", lambda: SymbolSet((), ()))
    loop.run_cycle(REGULAR)
    assert batches == [] and published == []


def test_fx_step_resolves_codes_for_every_traded_ticker_and_refreshes_pairs(monkeypatch):
    seen = {}
    monkeypatch.setattr(quotes, "_traded_tickers", lambda: ["ASML.AS", "AAPL"])
    monkeypatch.setattr(quotes.fx, "refresh_quote_codes", lambda syms, *, now=None: seen.setdefault("codes", syms))
    monkeypatch.setattr(quotes, "quote_currency_repo", lambda: type("R", (), {"get_many": staticmethod(
        lambda syms, conn=None: {"ASML.AS": {"code": "EUR"}, "AAPL": {"code": "USD"}, "X": {"code": None}})})())
    monkeypatch.setattr(quotes.fx, "refresh_pair_frames", lambda codes: seen.setdefault("pairs", set(codes)))
    full = loop.CycleContext(REGULAR, "regular", SymbolSet(("AAPL", "X"), ()), ["NEW"], [], False,
                             loop.CycleReport("regular", 30.0))
    quotes.fx_step(full)
    assert seen["codes"] == ["AAPL", "X", "NEW", "ASML.AS"] and seen["pairs"] == {"EUR", "USD"}
    seen.clear()
    quotes.fx_step(loop.CycleContext(REGULAR, "regular", SymbolSet((), ()), ["NEW"], [], False,
                                     loop.CycleReport("regular", 30.0)))
    assert seen == {"codes": ["NEW"]}          # queue-only cycle: no traded sweep, no pair refresh


def test_refresher_never_sets_the_admin_lock_timeout_or_writes_ohlcv():
    for path in (REPO / "swingbot" / "refresher").glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for banned in ("set_default_lock_timeout", "update_cache", "refresh_symbol", "data_refresh"):
            assert banned not in text, (path.name, banned)


# -- v248 § 3: held tickers first ---------------------------------------------------

HELD = SymbolSet(("AAPL", "BAD", "YF"), ("^GSPC",), ("AAPL", "YF"))


def _door(sym, price, minutes_ago):
    as_of = REGULAR - timedelta(minutes=minutes_ago)
    return MarketQuote(symbol=sym, price=price, as_of=as_of.isoformat(),
                       age_s=minutes_ago * 60.0, refreshing=False, error=None)


def _next_full_cycle(monkeypatch):
    monkeypatch.setattr(loop, "_last_full", None)     # same clock, but a full cycle again
    loop.run_cycle(REGULAR)


def test_first_cycle_fetches_every_held_ticker_first_with_the_full_cap(cycle, monkeypatch):
    _marks, _published, batches, _tapes = cycle
    monkeypatch.setattr(loop, "symbol_set", lambda: HELD)
    loop.run_cycle(REGULAR)
    assert batches == [(["AAPL", "YF"], 150), (["BAD"], 148)]
    assert quotes._held_primed is True


def test_first_cycle_held_batch_keeps_the_full_cap_during_a_scan(cycle, monkeypatch):
    marks, _published, batches, _tapes = cycle
    monkeypatch.setattr(loop, "symbol_set", lambda: HELD)
    monkeypatch.setattr(loop, "_scan_running", lambda: True)
    loop.run_cycle(REGULAR)
    assert batches == [(["AAPL", "YF"], 150), (["BAD"], 0)]
    assert ("clear", ("quote:BAD",), quotes.NO_QUOTE_DURING_SCAN) in marks.events


def test_later_cycle_puts_only_held_without_a_session_price_first(cycle, monkeypatch):
    _marks, _published, batches, _tapes = cycle
    monkeypatch.setattr(loop, "symbol_set", lambda: HELD)
    loop.run_cycle(REGULAR)
    batches.clear()
    asked = []

    def door(symbols, **kw):
        asked.append((list(symbols), kw.get("enqueue")))
        return {"AAPL": _door("AAPL", 190.5, 1), "YF": _door("YF", None, 1)}   # YF: bid/ask only
    monkeypatch.setattr(quotes.market_values, "read_quotes", door)
    _next_full_cycle(monkeypatch)
    assert asked == [(["AAPL", "YF"], False)]                 # never enqueues
    assert batches == [(["YF"], 150), (["AAPL", "BAD"], 149)]


def test_later_cycle_with_every_held_priced_keeps_todays_ordering(cycle, monkeypatch):
    _marks, _published, batches, _tapes = cycle
    monkeypatch.setattr(loop, "symbol_set", lambda: HELD)
    loop.run_cycle(REGULAR)
    monkeypatch.setattr(quotes.market_values, "read_quotes",
                        lambda symbols, **kw: {s: _door(s, 10.0, 2) for s in symbols})
    batches.clear()
    _next_full_cycle(monkeypatch)
    assert batches == [(["AAPL", "BAD", "YF"], 150)]
    monkeypatch.setattr(loop, "_scan_running", lambda: True)
    batches.clear()
    _next_full_cycle(monkeypatch)
    assert batches == [(["AAPL", "YF"], 150), (["BAD"], 0)]   # today's scan split


def test_unreadable_door_puts_every_held_ticker_first(cycle, monkeypatch):
    _marks, _published, batches, _tapes = cycle
    monkeypatch.setattr(loop, "symbol_set", lambda: HELD)
    loop.run_cycle(REGULAR)

    def down(symbols, **kw):
        raise RuntimeError("side pool busy")
    monkeypatch.setattr(quotes.market_values, "read_quotes", down)
    batches.clear()
    _next_full_cycle(monkeypatch)
    assert batches[0] == (["AAPL", "YF"], 150)


def test_a_failed_first_fetch_keeps_the_first_cycle_rule(cycle, monkeypatch):
    monkeypatch.setattr(loop, "symbol_set", lambda: HELD)

    def down(tickers, *, yf_limit):
        raise RuntimeError("alpaca 503")
    monkeypatch.setattr(quotes.data, "refresh_quote_batch", down)
    loop.run_cycle(REGULAR)
    assert quotes._held_primed is False

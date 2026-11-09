"""v201: the quote and FX steps, their marks, and the market NOTIFYs (marks set, values landed)."""
import pathlib
from datetime import datetime, timezone

import pytest

from swingbot import config
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

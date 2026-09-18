"""get_current_price's last-known-good fallback, and the US-session clock.

The fallback exists so a dashboard does not blank on one failed quote. It was
also what every trading caller got: the plan manager, the 60s SL/TP monitor, a
reversal's fill and a manual close's fill all took a price of ANY age when
Yahoo failed. With EXTENDED_HOURS_DEBOUNCE_TICKS=2 that let one real thin
premarket print confirm itself on the next tick -- the cached copy of the same
print is the "second" tick -- and close a plan the debounce exists to protect.
"""
import datetime as dt
import time

import pytest

from swingbot.core.marketdata import data as data_mod


class _YahooDown:
    def __init__(self, symbol):
        pass

    def history(self, **kw):
        raise RuntimeError("yahoo down")

    @property
    def fast_info(self):
        raise RuntimeError("yahoo down")


@pytest.fixture(autouse=True)
def _isolated_cache(monkeypatch):
    monkeypatch.setattr(data_mod, "_price_cache", {})
    monkeypatch.setattr(data_mod, "candidate_symbols", lambda ticker: [ticker])
    monkeypatch.setattr(data_mod.yf, "Ticker", _YahooDown)


def _cache_an_hour_old(ticker: str, price: float, *, stale: bool = False) -> None:
    data_mod._price_cache[ticker] = (price, time.monotonic() - 3600, stale)


def test_a_trading_caller_gets_none_rather_than_an_hour_old_price():
    _cache_an_hour_old("AAPL", 94.0)
    assert data_mod.get_current_price("AAPL", allow_stale=False) is None


def test_a_display_caller_still_gets_the_last_known_price():
    _cache_an_hour_old("AAPL", 94.0)
    assert data_mod.get_current_price("AAPL") == 94.0


def test_a_fresh_cached_price_is_served_to_both():
    data_mod._price_cache["AAPL"] = (101.0, time.monotonic(), False)
    assert data_mod.get_current_price("AAPL", allow_stale=False) == 101.0
    assert data_mod.get_current_price("AAPL") == 101.0


# -- get_current_price_detail / PriceQuote.stale ----------------------------
#
# The MRNA incident (2026-09-18): the admin dashboard rendered a "Near
# stop-loss" reading from a price that was actually yesterday's regular-
# session close, echoed back by yfinance's fast_info during early premarket
# because the primary 1-minute-history fetch failed (a real, logged
# YFRateLimitError). The trading engine never saw it -- it always calls with
# allow_stale=False, and a `None` is safe -- but the dashboard's `allow_stale=
# True` default rendered the number with no indication it was not a live
# tick. `get_current_price` itself is unchanged (still a bare float-or-None,
# so every trading call site is untouched); `get_current_price_detail` is
# the new, richer sibling the display path uses instead.

def test_detail_marks_the_primary_history_price_as_not_stale(monkeypatch):
    monkeypatch.setattr(data_mod, "candidate_symbols", lambda ticker: [ticker])

    class _Live:
        def __init__(self, symbol):
            pass

        def history(self, **kw):
            import pandas as pd
            return pd.DataFrame({"Close": [160.86]})

    monkeypatch.setattr(data_mod.yf, "Ticker", _Live)

    detail = data_mod.get_current_price_detail("MRNA")

    assert detail == data_mod.PriceQuote(160.86, stale=False)


def test_detail_marks_the_fast_info_fallback_as_stale(monkeypatch):
    """yfinance's fast_info can echo the previous session's close during
    early extended hours (`_fast_info_price`'s own docstring) -- exactly
    the MRNA misread. `get_current_price` only reaches this branch when the
    primary history call has already failed."""
    monkeypatch.setattr(data_mod, "candidate_symbols", lambda ticker: [ticker])

    class _HistoryDownFastInfoUp:
        def __init__(self, symbol):
            pass

        def history(self, **kw):
            raise RuntimeError("yahoo down")

        @property
        def fast_info(self):
            return {"lastPrice": 158.07}

    monkeypatch.setattr(data_mod.yf, "Ticker", _HistoryDownFastInfoUp)

    detail = data_mod.get_current_price_detail("MRNA")

    assert detail == data_mod.PriceQuote(158.07, stale=True)


def test_detail_marks_the_last_known_good_fallback_as_stale():
    _cache_an_hour_old("AAPL", 94.0, stale=False)
    detail = data_mod.get_current_price_detail("AAPL")
    assert detail == data_mod.PriceQuote(94.0, stale=True)


def test_detail_returns_none_for_a_trading_caller_past_the_hour_old_fallback():
    _cache_an_hour_old("AAPL", 94.0)
    assert data_mod.get_current_price_detail("AAPL", allow_stale=False) is None


def test_detail_preserves_the_stored_staleness_on_a_fresh_cache_hit():
    """A price warmed moments ago by a fast_info fallback is still that
    fallback -- cache AGE resets on every write, but the underlying quote's
    trustworthiness does not, so a hit inside the TTL must not silently
    launder it into "fresh"."""
    data_mod._price_cache["MRNA"] = (158.07, time.monotonic(), True)
    assert data_mod.get_current_price_detail("MRNA") == data_mod.PriceQuote(158.07, stale=True)


def test_get_current_price_is_unaffected_by_the_detail_refactor(monkeypatch):
    """The bare float-or-None contract every trading call site relies on
    must be byte-identical after get_current_price becomes a thin wrapper
    over get_current_price_detail."""
    monkeypatch.setattr(data_mod, "candidate_symbols", lambda ticker: [ticker])

    class _HistoryDownFastInfoUp:
        def __init__(self, symbol):
            pass

        def history(self, **kw):
            raise RuntimeError("yahoo down")

        @property
        def fast_info(self):
            return {"lastPrice": 158.07}

    monkeypatch.setattr(data_mod.yf, "Ticker", _HistoryDownFastInfoUp)

    assert data_mod.get_current_price("MRNA") == 158.07


# -- is_us_market_active ----------------------------------------------------
# US daylight time starts the second Sunday of March and ends the first
# Sunday of November; a month-number guess is an hour wrong either side.

@pytest.mark.parametrize("utc, active", [
    # Mon 2 Mar 2026, before DST starts: 08:30 UTC is 03:30 EST -- premarket
    # opens at 04:00, so NOT active (the month guess called it 04:30 EDT).
    (dt.datetime(2026, 3, 2, 8, 30, tzinfo=dt.timezone.utc), False),
    (dt.datetime(2026, 3, 2, 9, 30, tzinfo=dt.timezone.utc), True),
    # Mon 9 Mar 2026, DST in force: 08:30 UTC is 04:30 EDT.
    (dt.datetime(2026, 3, 9, 8, 30, tzinfo=dt.timezone.utc), True),
    # DST ended Sun 1 Nov 2026: Tue 3 Nov 00:30 UTC is Mon 2 Nov 19:30 EST,
    # still after-hours (the month guess called it 20:30 EDT, closed).
    (dt.datetime(2026, 11, 3, 0, 30, tzinfo=dt.timezone.utc), True),
    (dt.datetime(2026, 11, 3, 1, 30, tzinfo=dt.timezone.utc), False),
])
def test_is_us_market_active_uses_the_real_new_york_clock(utc, active):
    assert data_mod.is_us_market_active(now=utc) is active

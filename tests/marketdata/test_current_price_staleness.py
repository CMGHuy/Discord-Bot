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


def _cache_an_hour_old(ticker: str, price: float) -> None:
    data_mod._price_cache[ticker] = (price, time.monotonic() - 3600)


def test_a_trading_caller_gets_none_rather_than_an_hour_old_price():
    _cache_an_hour_old("AAPL", 94.0)
    assert data_mod.get_current_price("AAPL", allow_stale=False) is None


def test_a_display_caller_still_gets_the_last_known_price():
    _cache_an_hour_old("AAPL", 94.0)
    assert data_mod.get_current_price("AAPL") == 94.0


def test_a_fresh_cached_price_is_served_to_both():
    data_mod._price_cache["AAPL"] = (101.0, time.monotonic())
    assert data_mod.get_current_price("AAPL", allow_stale=False) == 101.0
    assert data_mod.get_current_price("AAPL") == 101.0


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

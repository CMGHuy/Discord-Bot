"""Market columns for the Watchlist, built from the daily cache in one batch.

Spec v85 D33. The rule that shapes this module: **one batch call for the whole
watchlist, never one call per row.** A ninety-symbol watchlist rendered with a
per-row fetch is ninety network round trips on every page view, and the cache
already holds every number this page needs.

`as_of` is the date of the bar the figures came from, not the time the request
was served. A page that prints "as of now" over Friday's close on a Sunday is
the failure this field exists to prevent.
"""

from __future__ import annotations

import pandas as pd

from swingbot.core.marketdata.data import (
    get_current_price_batch,
    get_daily_data_batch,
    is_us_market_active,
)

#: Trading-day offsets for the three change columns. 5 and 21 are a week and a
#: month of *business* days, which is what the cache is indexed by -- calendar
#: arithmetic here would silently straddle holidays.
_WINDOWS = {"change_1d_pct": 1, "change_1w_pct": 5, "change_1m_pct": 21}

_SPARK_BARS = 30


def _pct_change(closes: pd.Series, back: int) -> float | None:
    """Percentage change over `back` bars, or None when history is too short.

    None, never 0.0: a symbol listed three days ago has no one-month change,
    and 0.0 would claim it was flat.
    """
    if len(closes) <= back:
        return None
    prev = float(closes.iloc[-1 - back])
    if prev == 0:
        return None
    return round((float(closes.iloc[-1]) / prev - 1.0) * 100.0, 2)


def _empty_row() -> dict:
    return {
        "price": None,
        "as_of": None,
        "change_1d_pct": None,
        "change_1w_pct": None,
        "change_1m_pct": None,
        "spark": [],
    }


def build_market_rows(tickers: list[str]) -> dict[str, dict]:
    """Price, changes and a 30-bar sparkline for every ticker, keyed by symbol.

    Every requested symbol gets a row. A symbol the cache has nothing for gets
    a row of nulls rather than being dropped -- the Watchlist must still list
    it, and an omitted row would read as "removed from the watchlist".
    """
    if not tickers:
        return {}

    frames = get_daily_data_batch(list(tickers), period="6mo") or {}

    live: dict[str, float] = {}
    if is_us_market_active():
        try:
            live = get_current_price_batch(list(tickers)) or {}
        except Exception:
            # An intraday overlay is a nicety. Losing it must not lose the
            # closes, which are the page's actual content.
            live = {}

    rows: dict[str, dict] = {}
    for symbol in tickers:
        frame = frames.get(symbol)
        if frame is None or getattr(frame, "empty", True) or "Close" not in frame:
            rows[symbol] = _empty_row()
            continue

        closes = frame["Close"].dropna()
        if closes.empty:
            rows[symbol] = _empty_row()
            continue

        row = _empty_row()
        row["price"] = round(float(live.get(symbol) or closes.iloc[-1]), 4)
        row["as_of"] = str(pd.Timestamp(closes.index[-1]).date())
        for field, back in _WINDOWS.items():
            row[field] = _pct_change(closes, back)
        row["spark"] = [round(float(v), 4) for v in closes.iloc[-_SPARK_BARS:]]
        rows[symbol] = row

    return rows

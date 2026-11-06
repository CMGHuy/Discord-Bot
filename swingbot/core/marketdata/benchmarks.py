"""v208 benchmark bars for one symbol and one NYSE session.

Readers use day_pct for returns. Proxy bars carry only the proxy's daily
change (v171). Provisional intraday bars feed the Today card.
"""

import math
from collections.abc import Callable, Sequence
from datetime import date, datetime, timedelta

import pandas as pd

from swingbot import config
from swingbot.core.market.session import nyse_calendar
from swingbot.core.marketdata import data, yf_safe
from swingbot.core.marketdata.providers import router

BENCHMARK_SYMBOLS: tuple[str, ...] = ("SPY", "QQQ", "^IXIC", "^DJI")
TOTAL_RETURN: frozenset[str] = frozenset({"SPY", "QQQ"})


def benchmark_proxy_map() -> dict[str, str]:
    """Map each configured index to its ETF, splitting on the last equals sign."""
    out: dict[str, str] = {}
    for item in str(config.BENCHMARK_PROXY_SYMBOLS or "").split(","):
        symbol, sep, proxy = item.rpartition("=")
        if sep and symbol.strip() and proxy.strip():
            out[symbol.strip().upper()] = proxy.strip().upper()
    return out


def fetch_history(symbols: Sequence[str], start: date) -> dict[str, pd.DataFrame]:
    """Fetch Yahoo daily bars with raw and adjusted closes."""
    syms = list(dict.fromkeys(symbols))
    if not syms:
        return {}
    raw = yf_safe.download(" ".join(syms), start=start.isoformat(), interval="1d",
                           group_by="ticker", auto_adjust=False, progress=False)
    return {symbol: frame for symbol in syms if (frame := _symbol_frame(raw, symbol)) is not None}


def _symbol_frame(raw: pd.DataFrame | None, symbol: str) -> pd.DataFrame | None:
    if raw is None or raw.empty:
        return None
    if isinstance(raw.columns, pd.MultiIndex):
        if symbol not in raw.columns.get_level_values(0):
            return None
        raw = raw[symbol]
    if "Close" not in raw.columns:
        return None
    frame = raw.dropna(subset=["Close"])
    return None if frame.empty else frame


def _previous_session(day: date) -> date | None:
    earlier = nyse_calendar().sessions(day - timedelta(days=10), day - timedelta(days=1))
    return earlier[-1] if earlier else None


def _valid_price(price: float | None) -> bool:
    return price is not None and math.isfinite(price) and price > 0


def _by_day(frame: pd.DataFrame, column: str) -> dict[date, float]:
    if column not in frame.columns:
        return {}
    return {
        ts.date(): float(value)
        for ts, value in frame[column].dropna().items()
        if _valid_price(value)
    }


def _bar(
    symbol: str, session: date, *, close: float | None, adj_close: float | None,
    day_pct: float | None, source_symbol: str, final: bool, now: datetime,
) -> dict:
    return {
        "symbol": symbol,
        "session": session,
        "close": close,
        "adj_close": adj_close,
        "day_pct": day_pct,
        "source_symbol": source_symbol,
        "final": final,
        "as_of": now,
    }


def history_rows(
    symbol: str, frame: pd.DataFrame, *, source_symbol: str, sessions: Sequence[date],
    final_through: date, now: datetime,
) -> list[dict]:
    """Build final bars using levels from the current and immediately prior session."""
    own = source_symbol == symbol
    closes = _by_day(frame, "Close")
    adjs = _by_day(frame, "Adj Close")
    levels = adjs if own and symbol in TOTAL_RETURN else closes
    rows = []
    for day in sessions:
        if day > final_through or day not in levels:
            continue
        prev = _previous_session(day)
        day_pct = levels[day] / levels[prev] - 1 if prev in levels else None
        rows.append(_bar(
            symbol, day, close=closes.get(day) if own else None,
            adj_close=adjs.get(day) if own else None, day_pct=day_pct,
            source_symbol=source_symbol, final=True, now=now,
        ))
    return rows


def history_with_fallback(
    symbol: str, start: date, *, sessions: Sequence[date], final_through: date, now: datetime,
    fetch: Callable[[Sequence[str], date], dict[str, pd.DataFrame]] = fetch_history,
) -> list[dict]:
    """Try the configured ETF when Yahoo yields no usable bars for the symbol."""
    window = {"sessions": sessions, "final_through": final_through, "now": now}
    own = fetch([symbol], start).get(symbol)
    rows = history_rows(symbol, own, source_symbol=symbol, **window) if own is not None else []
    proxy = benchmark_proxy_map().get(symbol)
    if rows or not proxy:
        return rows
    frame = fetch([proxy], start).get(proxy)
    return history_rows(symbol, frame, source_symbol=proxy, **window) if frame is not None else []


def latest_benchmark_prices(symbols: Sequence[str]) -> dict[str, float]:
    """Fetch fresh positive quotes for the Today card."""
    prices = data.get_current_price_batch(
        list(symbols), allow_stale=False, asker=router.current_asker(),
    ) or {}
    return {
        symbol: float(price)
        for symbol, price in prices.items()
        if _valid_price(price)
    }


def intraday_row(
    symbol: str, prev: dict | None, price: float | None, session: date, now: datetime,
) -> dict | None:
    """Use the previous raw close even on ex-dividend mornings.

    The post-close final bar replaces this provisional price return.
    """
    if not _valid_price(price):
        return None
    if not prev or not prev["final"] or prev["source_symbol"] != symbol:
        return None
    prev_close = prev["close"]
    if not _valid_price(prev_close):
        return None
    if prev["session"] != _previous_session(session):
        return None
    return _bar(
        symbol, session, close=float(price), adj_close=None, day_pct=float(price) / float(prev_close) - 1,
        source_symbol=symbol, final=False, now=now,
    )

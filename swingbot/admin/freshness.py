"""v171 D2: how the admin pages ask the shared market-data layer for prices.

Reload means fresh (the SPA marks the request with `X-Swingbot-Fresh: 1`),
in-app navigation means reuse (60 s page window, 15 s on the Dashboard), and
every price the layer serves carries its age. An empty cache with a short
budget reads exactly as a failed fetch does today (`None` / `—`): no error,
no spinner.

The `data` and `layer` modules are imported inside the functions that need
them -- admin modules import lazily (see the circular-import note in app.py).
"""

from __future__ import annotations

import contextvars
import logging
import threading
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlparse

from flask import g, has_request_context, request

from swingbot import config
from swingbot.core.infra.swallowed import swallowed
from swingbot.core.marketdata.shared import kinds
from swingbot.core.marketdata.shared.kinds import Asker, DataKind, Entry, QuoteDetail

log = logging.getLogger(__name__)

FRESH_HEADER = "X-Swingbot-Fresh"


def install(app) -> None:
    """Mark a request that carries the fresh header, for exactly that request."""

    @app.before_request
    def _enter_fresh_mark():
        if request.headers.get(FRESH_HEADER) == "1":
            stack = ExitStack()
            stack.enter_context(kinds.fresh_request())
            g._swingbot_fresh_stack = stack

    @app.teardown_request
    def _exit_fresh_mark(_exc=None):
        stack = g.pop("_swingbot_fresh_stack", None)
        if stack is not None:
            stack.close()


def layer_on() -> bool:
    return config.MARKETDATA_LAYER == "on"


def from_dashboard() -> bool:
    """True inside a request whose Referer is the Dashboard page."""
    if not has_request_context():
        return False
    return urlparse(request.referrer or "").path.startswith("/dashboard")


def page_asker(*, dashboard: bool = False) -> Asker:
    return Asker.ADMIN_DASHBOARD if dashboard else Asker.ADMIN_PAGE


def page_window_s(*, dashboard: bool = False) -> float:
    window = kinds.resolve_asker(page_asker(dashboard=dashboard)).window_s(DataKind.QUOTE)
    return 0.0 if window is None else float(window)


def page_quotes(tickers: list[str], *, dashboard: bool = False) -> dict[str, QuoteDetail]:
    """One batch through the layer; any failure reads as no prices."""
    try:
        from swingbot.core.marketdata import data
        quotes = data.get_quote_batch(tickers, asker=page_asker(dashboard=dashboard))
        return {str(t).upper(): q for t, q in (quotes or {}).items()}
    except Exception as exc:
        swallowed(log, "marketdata.freshness.page_quotes", exc, "page_quotes failed",
                  level=logging.DEBUG, exc_info=True)
        return {}


def cached_quotes(tickers: list[str]) -> dict[str, Entry]:
    """Whatever the shared cache holds, any age; never fetches."""
    try:
        from swingbot.core.marketdata.shared import layer
        stored = layer.last_cached(DataKind.QUOTE, tickers)
        return {sym: Entry(QuoteDetail.from_doc(e.value), e.fetched_at, e.source, e.outcome)
                for sym, e in stored.items()}
    except Exception as exc:
        swallowed(log, "marketdata.freshness.cached_quotes", exc, "cached_quotes failed",
                  level=logging.DEBUG, exc_info=True)
        return {}


def warm_quotes_background(tickers: list[str], *, dashboard: bool = False) -> threading.Thread:
    """Fill the shared cache off the request; the fresh mark rides along."""
    ctx = contextvars.copy_context()
    thread = threading.Thread(
        target=ctx.run, args=(page_quotes, list(tickers)), kwargs={"dashboard": dashboard},
        daemon=True, name="admin-quote-warm")
    thread.start()
    return thread


def quote_age(q: Optional[QuoteDetail], now: Optional[datetime] = None) -> tuple[Optional[float], Optional[str]]:
    """(seconds since the trade or quote time, that time as ISO), else (None, None)."""
    at = None if q is None else (q.trade_at or q.quote_at)
    if at is None:
        return None, None
    now = now or datetime.now(timezone.utc)
    return max(0.0, (now - at).total_seconds()), at.isoformat()


# ---------------------------------------------------------------------------
# Daily bars for the chart, risk and watchlist pages (V171-26)
# ---------------------------------------------------------------------------
_PERIOD_DAYS = {"6mo": 183, "1y": 366, "2y": 731, "5y": 1827}


def _daily_stale(ticker: str) -> bool:
    """The yfinance daily file is missing or older than the page window."""
    import os
    import time
    from swingbot.core.marketdata import data, data_store
    path = data_store.cache_path(ticker, "daily")
    try:
        age = time.time() - os.path.getmtime(path)
    except OSError:
        return True
    limit = page_window_s() if data.is_us_market_active() else config.SCAN_CACHE_MAX_AGE_HOURS * 3600
    return age > limit


def _refresh_yf_daily(ticker: str, asker: Asker) -> None:
    """Full depth for a cold file, an incremental union otherwise; failures serve the disk."""
    import os
    from swingbot.core.marketdata import data_refresh, data_store
    from swingbot.core.marketdata.providers import router
    try:
        with router.asker_scope(asker):
            if os.path.exists(data_store.cache_path(ticker, "daily")):
                data_store.update_cache([ticker], "1d")
            else:
                data_refresh.refresh_symbol(ticker, "daily")
    except Exception as exc:
        swallowed(log, "marketdata.freshness.yf_refresh", exc, "yfinance daily refresh failed for %s",
                  ticker, level=logging.DEBUG, exc_info=True)


def _read_yf(ticker: str):
    from swingbot.core.marketdata import daily_delta
    return daily_delta.read_daily(ticker, basis=daily_delta.BASIS_YF)


def _daily_for(ticker: str):
    """One ticker's yfinance-basis frame, refreshed under the shared daily lease when stale."""
    df = _read_yf(ticker)
    if df is not None and not _daily_stale(ticker):
        return df
    from swingbot.core.marketdata.shared import layer
    asker = kinds.resolve_asker(Asker.ADMIN_PAGE)
    with layer.lease(DataKind.DAILY_BARS, ticker, asker=asker, deadline_s=10.0) as held:
        df = _read_yf(ticker)
        if (held and _daily_stale(ticker)) or df is None:
            _refresh_yf_daily(ticker, asker)
            df = _read_yf(ticker)
    return df


def _trim(df, period: str):
    days = _PERIOD_DAYS.get(period)
    if days is None or df is None or not len(df):
        return df
    return df[df.index >= df.index[-1] - timedelta(days=days)]


def page_daily(tickers: list[str], *, period: str = "2y") -> dict:
    """Daily frames for an admin page: spot metals as today, the rest from the shared file."""
    from swingbot.core.marketdata import data, spot_metals
    names = [str(t).upper().strip() for t in tickers]
    spot, regular = spot_metals.split_spot(names)
    out: dict = dict(data.get_daily_data_batch(list(spot), period=period) or {}) if spot else {}
    for t in regular:
        frame = _trim(_daily_for(t), period)
        if frame is not None and len(frame):
            out[t] = frame
    return out

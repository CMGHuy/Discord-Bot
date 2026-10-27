"""Read-side FX for the admin's money figures (v194 B7).

Every stored `realized_pnl_amount` is `shares * (exit - entry)` in its
instrument's quote currency; the admin shows money in the account currency.
This module answers the three questions that conversion needs and nothing
more: what the account currency is, what a ticker is quoted in, and what one
unit of one currency was worth in another on a given day.

Rates are Yahoo FX pairs (`USDEUR=X` is EUR per USD), daily closes, kept in
the yfinance daily cache `market_data/daily/` through
`data_refresh.refresh_symbol` -- the writer every other yfinance daily frame
uses -- so there is no third cache (docs/claude/known-traps.md). Not
`router.daily_bars_between`: that path is Alpaca-only and never serves an FX
pair.

Display only. Nothing here feeds sizing, the account balance, the
kill-switch or a stored record; a missing rate is `None`, never 1.0, so a
caller can flag the row instead of showing a dollar amount as euros.
"""
from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta

import pandas as pd

from swingbot import config
from swingbot.core.infra.swallowed import swallowed
from swingbot.core.marketdata import data, data_refresh, data_store
from swingbot.core.marketdata.providers import router
from swingbot.core.marketdata.shared import kinds
from swingbot.core.marketdata.shared.kinds import Asker

log = logging.getLogger(__name__)

#: How far back a missing exit-date bar may fall back. A long weekend plus a
#: holiday is four days; a week covers every market closure without letting
#: a stale rate stand in for a missing one.
FALLBACK_DAYS = 7

#: How long this process trusts a loaded pair frame (or a miss) before asking
#: the cache again: one admin page converts hundreds of rows.
FRAME_TTL_S = 15 * 60

#: Yahoo quotes some exchanges in a minor unit: LSE pence, JSE cents, TASE agorot.
MINOR_UNITS: dict[str, tuple[str, float]] = {
    "GBp": ("GBP", 0.01), "ZAc": ("ZAR", 0.01), "ILA": ("ILS", 0.01),
}

#: `CURRENCY_SYMBOL`'s default (swingbot/config.py) and the answer for an
#: unrecognised symbol.
DEFAULT_ACCOUNT_CODE = "EUR"

_frames: dict[str, tuple[float, pd.DataFrame | None]] = {}
_quote_codes: dict[str, str] = {}


def account_currency_code() -> str:
    """The account currency's ISO code, from `CURRENCY_SYMBOL`.

    The inverse of `data.CURRENCY_SYMBOLS`, first upper-case code in its
    order: '$' is USD (not MXN), '£' is GBP (not pence), '¥' is JPY. A symbol
    that is itself a listed code ('USD') is that code; anything else is EUR.
    """
    symbol = str(getattr(config, "CURRENCY_SYMBOL", "") or "").strip()
    if symbol.isupper() and symbol in data.CURRENCY_SYMBOLS:
        return symbol
    for code, sign in data.CURRENCY_SYMBOLS.items():
        if code.isupper() and symbol and sign.strip() == symbol:
            return code
    return DEFAULT_ACCOUNT_CODE


def quote_currency_code(ticker: str) -> str | None:
    """The currency `ticker` is quoted in, as Yahoo reports it ('USD', 'EUR',
    'GBp'), or None. A known answer is remembered for the process; an
    unknown one is not, so a later lookup can still succeed."""
    key = str(ticker or "").upper().strip()
    if not key:
        return None
    if key in _quote_codes:
        return _quote_codes[key]
    try:
        with router.asker_scope(kinds.resolve_asker(Asker.ADMIN_PAGE)):
            code, answered = data._provider_currency_code(key)
    except Exception as exc:
        swallowed(log, "marketdata.fx.quote_code", exc, level=logging.DEBUG)
        return None
    if not answered or not code:
        return None
    _quote_codes[key] = str(code)
    return _quote_codes[key]


def fx_rate(from_code: str, to_code: str, on: date) -> float | None:
    """The multiplier turning an amount in `from_code` into `to_code` on `on`.

    1.0 for equal codes, with no fetch. Otherwise the `{FROM}{TO}=X` close on
    `on`, else the last close within FALLBACK_DAYS before it, else None.
    Minor units scale (GBp -> GBP x 0.01).
    """
    if not from_code or not to_code:
        return None
    src, src_scale = _major(from_code)
    dst, dst_scale = _major(to_code)
    scale = src_scale / dst_scale
    if src == dst:
        return scale
    day = on.date() if isinstance(on, datetime) else on
    close = _close_on_or_before(_pair_frame(f"{src}{dst}=X"), day)
    return None if close is None else close * scale


def _major(code: str) -> tuple[str, float]:
    raw = str(code).strip()
    if raw in MINOR_UNITS:
        return MINOR_UNITS[raw]
    return raw.upper(), 1.0


def _clock() -> float:
    """The memo's clock; a seam so tests never patch the stdlib `time`."""
    return time.monotonic()


def _pair_frame(pair: str) -> pd.DataFrame | None:
    """The pair's cached daily frame, refreshed at most once per FRAME_TTL_S."""
    now = _clock()
    hit = _frames.get(pair)
    if hit is not None and now - hit[0] < FRAME_TTL_S:
        return hit[1]
    frame = _refreshed_frame(pair)
    _frames[pair] = (now, frame)
    return frame


def _refreshed_frame(pair: str) -> pd.DataFrame | None:
    """Bring the cache file up to date (a fresh file costs one mtime check),
    then read it. A failed refresh still serves whatever is on disk."""
    try:
        with router.asker_scope(kinds.resolve_asker(Asker.ADMIN_PAGE)):
            data_refresh.refresh_symbol(pair, "daily")
    except Exception as exc:
        swallowed(log, "marketdata.fx.refresh", exc, "FX refresh failed for %s: %s",
                  pair, exc, level=logging.DEBUG)
    return data_store.load_normalized(pair, "daily")


def _close_on_or_before(frame: pd.DataFrame | None, day: date) -> float | None:
    """The last positive close dated within [day - FALLBACK_DAYS, day]."""
    if frame is None or not len(frame) or "Close" not in frame.columns:
        return None
    earliest = day - timedelta(days=FALLBACK_DAYS)
    dates = [stamp.date() for stamp in pd.to_datetime(frame.index)]
    keep = [earliest <= d <= day for d in dates]
    closes = pd.to_numeric(frame["Close"][keep], errors="coerce").dropna()
    closes = closes[closes > 0]
    return float(closes.iloc[-1]) if len(closes) else None

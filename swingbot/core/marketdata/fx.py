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

v205: a request reads one rate per pair per Berlin day from `fx_daily_rates`
(`fx_daily.lookup`): the last positive close dated strictly before the day,
written by the refresher's 08:00 snap (`fx_snap`) from these same files. With
the refresher off, a missing row is computed by the same rule from the frame.

Display only. Nothing here feeds sizing, the account balance, the
kill-switch or a stored record; a missing rate is `None`, never 1.0, so a
caller can flag the row instead of showing a dollar amount as euros.
"""
from __future__ import annotations

import logging
import time
from collections.abc import Iterable
from datetime import date, datetime, timedelta, timezone

import pandas as pd

from swingbot import config
from swingbot.core.db.repositories.market_refresh import quote_currency_repo
from swingbot.core.infra.swallowed import swallowed
from swingbot.core.marketdata import data, data_refresh, data_store, fx_daily, spot_metals
from swingbot.core.marketdata.providers import router
from swingbot.core.marketdata.shared import kinds
from swingbot.core.marketdata.shared.kinds import Asker

log = logging.getLogger(__name__)

#: How old the bar behind a rate may be (a week covers every market closure
#: without letting a stale rate stand in for a missing one). The same object as
#: fx_daily.FALLBACK_DAYS: one rule for the table, the snap and the fallback.
FALLBACK_DAYS = fx_daily.FALLBACK_DAYS

#: How long this process trusts a loaded pair frame (or a miss) before asking
#: the cache again: one admin page converts hundreds of rows.
FRAME_TTL_S = 15 * 60
#: v205 L1-b: how long an unknown (or absent) stored quote code is remembered,
#: so a request never re-asks the store per ticker, and a code the refresher
#: resolves meanwhile shows within this long.
UNKNOWN_MEMO_S = 300

#: Yahoo quotes some exchanges in a minor unit: LSE pence, JSE cents, TASE agorot.
MINOR_UNITS: dict[str, tuple[str, float]] = {
    "GBp": ("GBP", 0.01), "ZAc": ("ZAR", 0.01), "ILA": ("ILS", 0.01),
}

#: `CURRENCY_SYMBOL`'s default (swingbot/config.py) and the answer for an
#: unrecognised symbol.
DEFAULT_ACCOUNT_CODE = "EUR"

#: XAUUSD / XAGUSD are priced in dollars (spot_metals rescales the futures to
#: the gold-api.com USD quote) but Yahoo reports no currency for them, so the
#: refresher stores "unknown" and their closed trades were left out of money.
SPOT_METAL_QUOTE = "USD"

_frames: dict[str, tuple[float, pd.DataFrame | None]] = {}
_quote_codes: dict[str, str] = {}
_unknown_until: dict[str, float] = {}


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


def quote_currency_code(ticker: str, *, fetch: bool = True) -> str | None:
    """The currency `ticker` is quoted in, as Yahoo reports it ('USD', 'EUR',
    'GBp'), or None. A known answer is remembered for the process; an
    unknown one is not, so a later lookup can still succeed.

    v201: `fetch=False` (the refresher is on) never touches the network: the
    process memo, else the refresher's persisted answer, else None."""
    key = str(ticker or "").upper().strip()
    if not key:
        return None
    if spot_metals.is_spot_metal(key):
        return SPOT_METAL_QUOTE   # Yahoo has no currency for spot metals
    if key in _quote_codes:
        return _quote_codes[key]
    if not fetch:
        return _stored_code(key)
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


def _stored_code(key: str) -> str | None:
    """v201: the refresher's persisted answer; never the network. Unknown/missing -> None."""
    return stored_codes([key]).get(key)


def stored_codes(keys: Iterable[str]) -> dict[str, str | None]:
    """v205 L1-b: the refresher's persisted answers for many tickers in one query.

    A known code is memoised for the process (`_quote_codes`); an unknown or
    absent one for UNKNOWN_MEMO_S (`_unknown_until`, monotonic `_clock()`).
    Keys in neither memo cost one `get_many` together. A store error answers
    None for those keys and memoises nothing, so the next call asks again."""
    now = _clock()
    out: dict[str, str | None] = {}
    ask: list[str] = []
    for key in dict.fromkeys(str(k or "").upper().strip() for k in keys):
        if not key:
            continue
        if spot_metals.is_spot_metal(key):
            out[key] = SPOT_METAL_QUOTE   # same rule as quote_currency_code
        elif key in _quote_codes:
            out[key] = _quote_codes[key]
        elif _unknown_until.get(key, 0.0) > now:
            out[key] = None
        else:
            ask.append(key)
    if ask:
        out.update(_ask_store(ask, now))
    return out


def _ask_store(keys: list[str], now: float) -> dict[str, str | None]:
    """One `get_many` for `keys`; memoise every answer (see `stored_codes`)."""
    try:
        rows = quote_currency_repo().get_many(keys)
    except Exception as exc:
        swallowed(log, "marketdata.fx.stored_code", exc, level=logging.DEBUG)
        return dict.fromkeys(keys)
    out: dict[str, str | None] = {}
    for key in keys:
        row = rows.get(key)
        if row and row.get("outcome") == "known" and row.get("code"):
            _quote_codes[key] = str(row["code"])
            out[key] = _quote_codes[key]
        else:
            _unknown_until[key] = now + UNKNOWN_MEMO_S
            out[key] = None
    return out


def _ask_provider(key: str) -> tuple[str | None, bool]:
    """One provider lookup at the refresher tier; an exception is unanswered."""
    try:
        with router.asker_scope(Asker.ADMIN_REFRESH):
            return data._provider_currency_code(key)
    except Exception as exc:
        swallowed(log, "marketdata.fx.refresh_code", exc, level=logging.DEBUG)
        return None, False


def refresh_quote_codes(symbols, *, now: datetime | None = None) -> dict[str, str | None]:
    """v201 refresher FX job: ask the provider for every due symbol and persist the
    answer; an 'unknown' answer is stored with a retry_after backoff, an unanswered
    call (provider error) is not stored and is retried next cycle."""
    now = now or datetime.now(timezone.utc)
    repo = quote_currency_repo()
    keys = list(dict.fromkeys(str(s or "").upper().strip() for s in symbols if str(s or "").strip()))
    out: dict[str, str | None] = {}
    for key in repo.due(keys, now):
        code, answered = _ask_provider(key)
        if not answered:
            continue
        if code:
            repo.put(key, str(code), "known", checked_at=now)
            _quote_codes[key] = str(code)
        else:
            retry = now + timedelta(seconds=float(config.ADMIN_REFRESH_FX_UNKNOWN_RETRY_S))
            repo.put(key, None, "unknown", checked_at=now, retry_after=retry)
        out[key] = str(code) if code else None
    return out


def refresh_pair_frames(codes: Iterable[str]) -> list[str]:
    """v201 refresher FX job: bring every quote currency's pair into the account
    currency up to date (the same pair files `fx_rate` reads). Returns the pairs
    whose frame loaded, sorted."""
    account = _major(account_currency_code())[0]
    pairs = sorted({f"{_major(c)[0]}{account}=X" for c in codes
                    if c and _major(c)[0] != account})
    loaded = []
    for pair in pairs:
        frame = _refreshed_frame(pair, asker=Asker.ADMIN_REFRESH)
        _frames[pair] = (_clock(), frame)
        if frame is not None:
            loaded.append(pair)
    return loaded


def fx_rate(from_code: str, to_code: str, on: date, *, refresh: bool = True) -> float | None:
    """The multiplier turning an amount in `from_code` into `to_code` on `on`.

    The scale alone for equal majors (GBp -> GBP is 0.01), with no lookup.
    Otherwise v205's day rate: the `fx_daily_rates` row for (FROM, TO, day),
    the last positive `{FROM}{TO}=X` close strictly before the day, times the
    minor-unit scale. On a missing row, `refresh=True` (the refresher is off)
    applies the same rule to the pair frame and writes nothing; `refresh=False`
    (the refresher is on) is None. Never 1.0 for a missing rate.
    """
    if not from_code or not to_code:
        return None
    src, src_scale = _major(from_code)
    dst, dst_scale = _major(to_code)
    scale = src_scale / dst_scale
    if src == dst:
        return scale
    day = on.date() if isinstance(on, datetime) else on
    rate = _day_rate(src, dst, day, refresh=refresh)
    return None if rate is None else rate * scale


def _day_rate(src: str, dst: str, day: date, *, refresh: bool) -> float | None:
    """The stored row's rate, else (refresh only) the same rule over the pair frame."""
    stored = fx_daily.lookup(src, dst, day)
    if stored is not None or not refresh:
        return stored
    found = fx_daily.rate_before(_pair_frame(f"{src}{dst}=X", refresh=True), day)
    return None if found is None else found[0]


def _major(code: str) -> tuple[str, float]:
    raw = str(code).strip()
    if raw in MINOR_UNITS:
        return MINOR_UNITS[raw]
    return raw.upper(), 1.0


def _clock() -> float:
    """The memo's clock; a seam so tests never patch the stdlib `time`."""
    return time.monotonic()


def _pair_frame(pair: str, *, refresh: bool = True) -> pd.DataFrame | None:
    """The pair's cached daily frame, refreshed at most once per FRAME_TTL_S;
    `refresh=False` loads the file as it stands."""
    now = _clock()
    hit = _frames.get(pair)
    if hit is not None and now - hit[0] < FRAME_TTL_S:
        return hit[1]
    frame = _refreshed_frame(pair) if refresh else _disk_frame(pair)
    _frames[pair] = (now, frame)
    return frame


def _disk_frame(pair: str) -> pd.DataFrame | None:
    """The pair's cache file as it stands; no fetch, a read error is None."""
    try:
        return data_store.load_normalized(pair, "daily")
    except Exception as exc:
        swallowed(log, "marketdata.fx.disk_frame", exc, level=logging.DEBUG)
        return None


def _refreshed_frame(pair: str, asker: Asker = Asker.ADMIN_PAGE) -> pd.DataFrame | None:
    """Bring the cache file up to date (a fresh file costs one mtime check),
    then read it. A failed refresh still serves whatever is on disk."""
    try:
        with router.asker_scope(kinds.resolve_asker(asker)):
            data_refresh.refresh_symbol(pair, "daily")
    except Exception as exc:
        swallowed(log, "marketdata.fx.refresh", exc, "FX refresh failed for %s: %s",
                  pair, exc, level=logging.DEBUG)
    return data_store.load_normalized(pair, "daily")


"""
Checks for a known scheduled event -- currently just earnings dates --
that could affect a trade within its intended holding window. This is
what "events happening with the stock" means here: a concrete, fetchable
date, not sentiment analysis of news text.

Best-effort: if Yahoo doesn't have the data (delisted, no analyst
coverage, temporary API hiccup), this silently returns None rather than
blocking a trade recommendation. An earnings date is a real risk factor
for a swing trade -- surprises in either direction can blow through both
the stop-loss and the take-profit overnight -- so when one falls inside
the holding window, the bot flags it rather than pretending it isn't there.
"""
import datetime as dt
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

import yfinance as yf

from swingbot import config
from swingbot.core.infra.swallowed import swallowed
from swingbot.core.marketdata import yf_safe
from swingbot.core.marketdata.providers import router
from swingbot.core.marketdata.shared import counters, layer
from swingbot.core.marketdata.shared.kinds import PROVIDER_YF, Asker, DataKind
from swingbot.core.marketdata.spot_metals import is_spot_metal
from swingbot.core.marketdata.ticker_utils import candidate_symbols
from swingbot.core.marketdata.universe import is_etf
from swingbot.core.market.session import market_today

log = logging.getLogger(__name__)

# An earnings date is essentially static for weeks at a time -- nothing like
# get_current_price's 15s TTL is warranted, and the cost of NOT caching this
# is severe: GET /watchlist/tickers calls get_next_earnings_datetime once per
# watchlist ticker on every page load, uncached, and each call is a live
# Yahoo round trip with no local-data fallback (unlike company-name lookups,
# which resolve most US symbols from a local directory). Measured on a
# ~34-ticker watchlist: 23 seconds per load before this cache existed --
# severe enough to read as "the page shows nothing" rather than "slow".
# Same {ticker: (value, fetched_at)} shape _price_cache in marketdata/data.py
# used before it grew a third `stale` element, just a much longer TTL.
_EARNINGS_DATETIME_CACHE_TTL_SECONDS = 6 * 60 * 60
_earnings_datetime_cache: dict[str, tuple[dt.datetime | None, float]] = {}
_earnings_datetimes_cache: dict[str, tuple[list[dt.datetime], float]] = {}

#: Distinguishes "checked Yahoo, confirmed nothing" (a real cached `None`)
#: from "never checked, or the entry expired" -- callers that must not
#: block (the watchlist endpoint) need to tell those apart.
_NOT_CACHED = object()


def _never_reports(ticker: str) -> bool:
    """Funds and spot metals (v109) never report earnings: never gate, never fetch."""
    return is_etf(ticker) or is_spot_metal(ticker)


def get_next_earnings_date(ticker: str, *, asker: Asker = Asker.BACKGROUND) -> dt.date | None:
    """Returns the next known earnings date for a ticker, or None if unavailable.

    v171: `on` reads the shared earnings doc (6 h window)."""
    if _never_reports(ticker):
        return None  # funds don't report earnings; never gate or fetch
    if config.MARKETDATA_LAYER == "on":
        return _next_date(_earnings_doc(ticker, asker=asker))
    _count_legacy(asker)
    return _next_earnings_date_legacy(ticker)


def _next_earnings_date_legacy(ticker: str) -> dt.date | None:
    for candidate in candidate_symbols(ticker):
        try:
            calendar = yf.Ticker(candidate).calendar
        except Exception as e:
            swallowed(log, "earnings.next_date", e, "Calendar fetch failed for %s: %s", candidate, e,
                      level=logging.DEBUG)
            continue

        if not calendar:
            continue
        dates = calendar.get("Earnings Date")
        if not dates:
            continue

        today = market_today()
        upcoming = [d for d in dates if isinstance(d, dt.date) and d >= today]
        if upcoming:
            return min(upcoming)

    return None


def get_next_earnings_datetime(ticker: str, *, asker: Asker = Asker.BACKGROUND) -> dt.datetime | None:
    """Like `get_next_earnings_date`, but with a time-of-day and timezone
    attached when Yahoo has one.

    `Ticker.calendar["Earnings Date"]` (what `get_next_earnings_date` reads)
    is a plain date list with no time. `Ticker.get_earnings_dates()` is a
    separate yfinance call that returns a real, per-company,
    `America/New_York`-zoned timestamp -- confirmed empirically: AAPL/MSFT/
    NVDA consistently report after close (16:00 ET) while JPM/WMT
    consistently report before open (06:00-08:00 ET), correctly shifting
    across the EST/EDT boundary. Admin-display use only (the Watchlist
    Earnings calendar) -- kept independent of `get_next_earnings_date`
    rather than sharing an implementation, because that function backs the
    earnings-blackout gate, a trading-safety check with its own tests, and
    this path must never be able to shift its behaviour.

    For a future date, Yahoo has not necessarily confirmed the exact time
    (some companies announce it only weeks ahead) -- treat every returned
    value as an estimate, never as confirmed.

    Cached in-memory per ticker for `_EARNINGS_DATETIME_CACHE_TTL_SECONDS`
    (6h) -- see that constant's comment for why this one needs a cache at
    all where `get_next_earnings_date` (below) has gone without one.

    v171: `on` reads the shared earnings doc instead (and primes this cache).
    """
    ticker_key = ticker.upper().strip()
    if config.MARKETDATA_LAYER == "on":
        if _never_reports(ticker_key):
            return None
        return _next_datetime(_earnings_doc(ticker_key, asker=asker))
    cached = _earnings_datetime_cache.get(ticker_key)
    now_monotonic = time.monotonic()
    if cached and (now_monotonic - cached[1]) < _EARNINGS_DATETIME_CACHE_TTL_SECONDS:
        return cached[0]

    _count_legacy(asker)
    result = _fetch_next_earnings_datetime(ticker_key)
    _earnings_datetime_cache[ticker_key] = (result, now_monotonic)
    return result


def peek_cached_earnings_datetime(ticker: str):
    """Read-only: the cached value if fresh, or `_NOT_CACHED` -- never
    fetches, never blocks.

    For a caller that must answer instantly (the watchlist endpoint) and
    would rather show "unknown for now" than make a request wait on a live
    Yahoo call. Pair with `warm_earnings_cache_background` to fill the gap
    for next time without making THIS request pay for it.
    """
    ticker_key = ticker.upper().strip()
    cached = _earnings_datetime_cache.get(ticker_key)
    if cached and (time.monotonic() - cached[1]) < _EARNINGS_DATETIME_CACHE_TTL_SECONDS:
        return cached[0]
    return _NOT_CACHED


def warm_earnings_cache_background(tickers: list[str], *,
                                   asker: Asker = Asker.ADMIN_PAGE) -> threading.Thread:
    """Fire-and-forget: populate the cache for `tickers` on a daemon thread.

    Same shape as `marketdata.backtest_cache.ensure_cached_background` --
    the caller gets an immediate return and the next request (or the next
    poll of the same page) sees the warmed cache instead of paying for it.

    The per-ticker fetches run on a small pool (same `max_workers=min(10, n)`
    shape as `watchlist.py`'s `_company_names`), not sequentially: a
    sequential loop over a full watchlist (75+ tickers measured live) took
    over a minute of live Yahoo round trips, which starved the frontend's
    one bounded refresh (`EARNINGS_REFRESH_DELAY_MS` in `watchlist.store.ts`)
    -- the Earnings calendar rendered near-empty until a full manual reload.
    Everything here already runs off the request thread, so this pool adds
    no response latency; it only shortens how long the cache stays cold.

    v171: `on` is one daemon thread making one `_earnings_docs` call.
    """
    if config.MARKETDATA_LAYER == "on":
        return _start_warm_thread(lambda: _earnings_docs(tickers, asker=asker))
    return _start_warm_thread(lambda: _warm_legacy(tickers))


def _start_warm_thread(work) -> threading.Thread:
    def _run():
        try:
            work()
        except Exception as exc:
            swallowed(log, "earnings.warmup", exc, "background earnings warm-up failed",
                      level=logging.DEBUG, exc_info=True)

    t = threading.Thread(target=_run, name="earnings-cache-warm", daemon=True)
    t.start()
    return t


def _warm_legacy(tickers: list[str]) -> None:
    with ThreadPoolExecutor(max_workers=min(10, len(tickers))) as pool:
        futures = {pool.submit(get_next_earnings_datetime, t): t for t in tickers}
        for fut in as_completed(futures):
            ticker = futures[fut]
            try:
                fut.result()
            except Exception as exc:
                swallowed(log, "earnings.warmup", exc,
                          "background earnings warm-up failed for %s", ticker,
                          level=logging.DEBUG, exc_info=True)


def _fetch_next_earnings_datetime(ticker: str) -> dt.datetime | None:
    if _never_reports(ticker):
        return None

    for candidate in candidate_symbols(ticker):
        try:
            earnings = yf.Ticker(candidate).get_earnings_dates(limit=6)
        except Exception as e:
            swallowed(log, "earnings.next_datetime", e, "Earnings-dates fetch failed for %s: %s",
                      candidate, e, level=logging.DEBUG)
            continue
        if earnings is None or earnings.empty:
            continue

        now = dt.datetime.now(dt.timezone.utc)
        upcoming = [ts for ts in earnings.index if ts.to_pydatetime() >= now]
        if upcoming:
            return min(upcoming).to_pydatetime()

    return None


def get_earnings_datetimes(ticker: str, *, refresh: bool = False,
                           asker: Asker = Asker.BACKGROUND) -> list[dt.datetime]:
    """Return Yahoo's recent and upcoming earnings timestamps, ascending.

    Unlike the display-only singular lookup, this preserves a before-open
    report on its own date so calendar consumers can correctly see today.
    """
    if _never_reports(ticker):
        return []
    if config.MARKETDATA_LAYER == "on":
        return _datetimes(_earnings_doc(ticker, asker=asker, max_age_s=0.0 if refresh else None))
    _count_legacy(asker, will_fetch=_datetimes_will_fetch(ticker, refresh))
    return _earnings_datetimes_legacy(ticker, refresh)


def _datetimes_will_fetch(ticker: str, refresh: bool) -> bool:
    """Mirrors the legacy cache test exactly (a cached [] inside 6 h is a hit)."""
    cached = _earnings_datetimes_cache.get(ticker.upper().strip())
    fresh = bool(cached) and time.monotonic() - cached[1] < _EARNINGS_DATETIME_CACHE_TTL_SECONDS
    return refresh or not fresh


def _earnings_datetimes_legacy(ticker: str, refresh: bool) -> list[dt.datetime]:
    key, now_monotonic = ticker.upper().strip(), time.monotonic()
    cached = _earnings_datetimes_cache.get(key)
    if not refresh and cached and now_monotonic - cached[1] < _EARNINGS_DATETIME_CACHE_TTL_SECONDS:
        return list(cached[0])
    result: list[dt.datetime] = []
    for candidate in candidate_symbols(ticker):
        try:
            frame = yf.Ticker(candidate).get_earnings_dates(limit=8)
        except Exception as exc:
            swallowed(log, "earnings.datetimes", exc, "Earnings-dates fetch failed for %s: %s",
                      candidate, exc, level=logging.DEBUG)
            continue
        if frame is not None and not frame.empty:
            result = sorted(ts.to_pydatetime() for ts in frame.index)
            break
    _earnings_datetimes_cache[key] = (result, now_monotonic)
    # A forced weekly refresh also warms the singular display cache consumed
    # by the Watchlist API, so the next page response immediately shows the
    # refreshed upcoming date instead of scheduling a second Yahoo request.
    if refresh:
        now = dt.datetime.now(dt.timezone.utc)
        upcoming = [value for value in result if value >= now]
        _earnings_datetime_cache[key] = (min(upcoming) if upcoming else None, now_monotonic)
    return list(result)


def peek_cached_earnings_datetimes(ticker: str) -> list[dt.datetime] | None:
    """Read-only twin of `get_earnings_datetimes`: the fresh cached list, or
    None when nothing usable is cached -- never fetches, never blocks.

    A cached empty list is answered None as well: `get_earnings_datetimes`
    caches [] for a failed fetch exactly as for "no reports", so an empty
    entry cannot be trusted as an answer here (v146 panel fix)."""
    cached = _earnings_datetimes_cache.get(ticker.upper().strip())
    if not cached or time.monotonic() - cached[1] >= _EARNINGS_DATETIME_CACHE_TTL_SECONDS:
        return None
    return list(cached[0]) or None


def _utc(value: dt.datetime, what: str) -> dt.datetime:
    """Tz-aware UTC instant; a naive timestamp is ambiguous and rejected."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{what} must be timezone-aware, got naive {value!r}")
    return value.astimezone(dt.timezone.utc)


@dataclass(frozen=True)
class EarningsSnapshot:
    """What one earnings query answered, and when. `query_ok` separates a
    confirmed empty answer from a failed fetch -- an empty list alone cannot."""

    observed_at: dt.datetime
    reports: tuple[dt.datetime, ...]
    query_ok: bool
    source: str

    def __post_init__(self):
        object.__setattr__(self, "observed_at", _utc(self.observed_at, "observed_at"))
        object.__setattr__(self, "reports", tuple(sorted(_utc(r, "report") for r in self.reports)))


def earnings_snapshot(ticker: str, *, now: dt.datetime | None = None,
                      asker: Asker = Asker.BACKGROUND) -> EarningsSnapshot:
    """Typed earnings observation (fresh fetch in off/count; in `on` mode up to the 6 h window old). The display API above is untouched.

    A fund or spot metal is answered explicitly as `nonreporting_instrument`;
    a stock whose every fetch raised is `query_ok=False`, never an empty clear.

    `now` is for live/test use only. It is NOT a historical as-of: never use it to
    stamp a present-day fetch as past knowledge (that is lookahead).
    """
    observed = now if now is not None else dt.datetime.now(dt.timezone.utc)
    if _never_reports(ticker):
        return EarningsSnapshot(observed, (), True, "nonreporting_instrument")
    if config.MARKETDATA_LAYER == "on":
        return _snapshot_from_doc(_earnings_doc(ticker, asker=asker), now)
    _count_legacy(asker)
    return _snapshot_legacy(ticker, observed)


def _snapshot_legacy(ticker: str, observed: dt.datetime) -> EarningsSnapshot:
    for candidate in candidate_symbols(ticker):
        try:
            frame = yf.Ticker(candidate).get_earnings_dates(limit=8)
        except Exception as exc:
            swallowed(log, "earnings.snapshot", exc, "Earnings snapshot fetch failed for %s: %s",
                      candidate, exc, level=logging.DEBUG)
            continue
        reports = () if frame is None or frame.empty else tuple(ts.to_pydatetime() for ts in frame.index)
        return EarningsSnapshot(observed, reports, True, "yahoo")
    return EarningsSnapshot(observed, (), False, "yahoo")


def earnings_within_window(ticker: str, max_holding_days: int):
    """
    Returns (earnings_date, days_away) if the next known earnings date
    falls within the next `max_holding_days` calendar days, else None.
    """
    next_date = get_next_earnings_date(ticker, asker=Asker.SCAN)
    if next_date is None:
        return None

    days_away = (next_date - market_today()).days
    if 0 <= days_away <= max_holding_days:
        return next_date, days_away
    return None


# --- v171: the shared earnings doc ------------------------------------------

_EARNINGS_CHUNK = 10
_EMPTY_DOC = {"calendar": [], "datetimes": [], "query_ok": False, "fetched_at": None}


def _count_legacy(asker: Asker, will_fetch: bool = True) -> None:
    """`count` mode: one counted fetch per real legacy Yahoo call."""
    if config.MARKETDATA_LAYER == "count" and will_fetch:
        counters.count(PROVIDER_YF, DataKind.EARNINGS, asker, "fetched")


def _next_date(doc: dict) -> dt.date | None:
    today = market_today()
    upcoming = [d for d in map(dt.date.fromisoformat, doc["calendar"]) if d >= today]
    return min(upcoming) if upcoming else None


def _datetimes(doc: dict) -> list[dt.datetime]:
    return sorted(dt.datetime.fromisoformat(s) for s in doc["datetimes"])


def _next_datetime(doc: dict) -> dt.datetime | None:
    now = dt.datetime.now(dt.timezone.utc)
    upcoming = [ts for ts in _datetimes(doc) if ts >= now]
    return min(upcoming) if upcoming else None


def _snapshot_from_doc(doc: dict, now: dt.datetime | None) -> EarningsSnapshot:
    stamp = doc["fetched_at"]
    observed = now if now is not None else (
        dt.datetime.fromisoformat(stamp) if stamp else dt.datetime.now(dt.timezone.utc))
    return EarningsSnapshot(observed, tuple(_datetimes(doc)), doc["query_ok"], "yahoo")


def _earnings_doc(ticker: str, *, asker: Asker, max_age_s: float | None = None) -> dict:
    key = ticker.upper().strip()
    return _earnings_docs([key], asker=asker, max_age_s=max_age_s).get(key, dict(_EMPTY_DOC))


def _earnings_docs(tickers: list[str], *, asker: Asker, max_age_s: float | None = None) -> dict[str, dict]:
    keys = [k for k in dict.fromkeys(t.upper().strip() for t in tickers) if not _never_reports(k)]
    docs: dict[str, dict] = {}
    with router.asker_scope(asker):
        for i in range(0, len(keys), _EARNINGS_CHUNK):
            got = layer.get(DataKind.EARNINGS, keys[i:i + _EARNINGS_CHUNK], _fetch_earnings_docs,
                            asker=asker, provider=PROVIDER_YF, max_age_s=max_age_s)
            for sym, entry in got.items():
                docs[sym] = _primed_doc(sym, entry)
    return docs


def _primed_doc(symbol: str, entry) -> dict:
    """The stored doc plus its stamp; primes both peek caches at the doc's true age."""
    doc = {**entry.value, "fetched_at": entry.fetched_at.isoformat()}
    stamp = time.monotonic() - entry.age_s()
    _earnings_datetime_cache[symbol] = (_next_datetime(doc), stamp)
    _earnings_datetimes_cache[symbol] = (_datetimes(doc), stamp)
    return doc


def _fetch_earnings_docs(symbols: list[str]) -> dict[str, dict | None]:
    for _ in range(2 * len(symbols)):
        yf_safe._take_yf_token()
    with ThreadPoolExecutor(max_workers=min(10, len(symbols))) as pool:
        return dict(zip(symbols, pool.map(_fetch_one_doc, symbols)))


def _walk_calendar(candidates: list[str]) -> tuple[list[str], bool]:
    """(ISO dates from the first non-empty calendar, whether any call returned)."""
    answered = False
    for candidate in candidates:
        try:
            calendar = yf.Ticker(candidate).calendar
        except Exception as exc:
            swallowed(log, "earnings.next_date", exc, "Calendar fetch failed for %s: %s",
                      candidate, exc, level=logging.DEBUG)
            continue
        answered = True
        dates = calendar.get("Earnings Date") if calendar else None
        found = [d.isoformat() for d in dates or [] if isinstance(d, dt.date)]
        if found:
            return found, True
    return [], answered


def _walk_dates(candidates: list[str]) -> tuple[list[str], bool]:
    """(sorted ISO stamps from the first candidate that did not raise, whether one did not)."""
    for candidate in candidates:
        try:
            frame = yf.Ticker(candidate).get_earnings_dates(limit=8)
        except Exception as exc:
            swallowed(log, "earnings.datetimes", exc, "Earnings-dates fetch failed for %s: %s",
                      candidate, exc, level=logging.DEBUG)
            continue
        if frame is None or frame.empty:
            return [], True
        return [ts.isoformat() for ts in sorted(i.to_pydatetime() for i in frame.index)], True
    return [], False


def _fetch_one_doc(symbol: str) -> dict | None:
    """One doc per symbol; None (a miss, never written) when every call raised."""
    candidates = candidate_symbols(symbol)
    calendar, cal_ok = _walk_calendar(candidates)
    datetimes, query_ok = _walk_dates(candidates)
    if not (cal_ok or query_ok):
        return None
    return {"calendar": calendar, "datetimes": datetimes, "query_ok": query_ok}

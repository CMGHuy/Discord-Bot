"""GET/POST/DELETE /api/v1/watchlist/* — the watchlist.

Spec 3's Watchlist workspace. Spec v11 Decision 4 collapses the Jinja UI's
separate `/watchlist/add` and `/watchlist/bulk_add` into ONE endpoint whose
body is always a list: those two exist only because an HTML form cannot
post an array, which stops being a constraint the moment the client is JSON.

Bulk add reports per-symbol outcomes rather than failing the batch on one
bad symbol. Pasting thirty tickers and being told only that "something was
invalid" is the behaviour the Jinja page's summary string was already
working around; the SPA gets the structured version.
"""
from __future__ import annotations

import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

from flask import jsonify, request

from swingbot import config

from . import api_v1, error
from .auth import require_auth


def _watchlist_path() -> str:
    """Resolved per call, NOT taken from watchlist.DEFAULT_PATH.

    That module computes its default at import time from config.DATA_DIR, so
    it keeps pointing at whatever DATA_DIR was when it was first imported --
    which in a test run is the real project's data/ directory, monkeypatch or
    not. Reading through it is merely wrong; WRITING through it edits the
    user's actual watchlist from a test. Every call below therefore passes an
    explicit path. Same value in production, isolable everywhere else.
    """
    return os.path.join(config.DATA_DIR, "watchlist.json")

# Same shape the Jinja bulk-add applies: length cap plus an alphanumeric
# test that tolerates the punctuation real symbols use (BRK.B, RDS-A, EURUSD=X).
_MAX_TICKER_LEN = 10


def _is_valid(ticker: str) -> bool:
    return (
        0 < len(ticker) <= _MAX_TICKER_LEN
        and ticker.replace(".", "").replace("-", "").replace("=", "").isalnum()
    )


def _company_names(tickers: list[str]) -> dict[str, str | None]:
    """Resolved concurrently, as the Jinja page does.

    US-listed symbols come from the local NASDAQ/NYSE directory instantly;
    only OTC and international ones hit the network, and doing those
    sequentially stalls the whole response.
    """
    from swingbot.core.marketdata.data import get_company_name

    if not tickers:
        return {}
    names: dict[str, str | None] = {}
    with ThreadPoolExecutor(max_workers=min(10, len(tickers))) as pool:
        futures = {pool.submit(get_company_name, t): t for t in tickers}
        for fut in as_completed(futures):
            t = futures[fut]
            try:
                names[t] = fut.result()
            except Exception:
                names[t] = None
    return names


def _next_earnings_dates(tickers: list[str]) -> dict[str, str | None]:
    """Same concurrency shape as `_company_names` -- `get_next_earnings_date`
    is an uncached, per-ticker Yahoo call (`events.py`), so this is one live
    round trip per symbol regardless; doing them sequentially would stall the
    response by roughly `len(tickers)` times whatever one call costs.

    ISO date strings (`YYYY-MM-DD`), not raw `date` objects, matching every
    other date this API returns -- `jsonify` on a bare `date` is not a
    convention exercised anywhere else here, so this stays consistent rather
    than being the one endpoint that relies on it.
    """
    from swingbot.core.market.events import get_next_earnings_date

    if not tickers:
        return {}
    dates: dict[str, str | None] = {}
    with ThreadPoolExecutor(max_workers=min(10, len(tickers))) as pool:
        futures = {pool.submit(get_next_earnings_date, t): t for t in tickers}
        for fut in as_completed(futures):
            t = futures[fut]
            try:
                result = fut.result()
                dates[t] = result.isoformat() if result else None
            except Exception:
                dates[t] = None
    return dates


@api_v1.route("/watchlist/tickers", methods=["GET"])
@require_auth
def list_tickers():
    from swingbot.core.tracking.performance import TradeLog
    from swingbot.core.marketdata.watchlist import load_watchlist

    tickers = list(load_watchlist(_watchlist_path()))
    counts = {t: {"open": 0, "closed": 0} for t in tickers}
    for tr in TradeLog().get_trades(status=None, limit=None) or []:
        bucket = counts.get(tr.get("ticker"))
        if bucket is None:
            continue  # a trade on a ticker no longer watched
        bucket["open" if tr.get("status") == "open" else "closed"] += 1

    names = _company_names(tickers)
    earnings = _next_earnings_dates(tickers)
    return jsonify({"tickers": [
        {"symbol": t, "company_name": names.get(t),
         "open_trades": counts[t]["open"], "closed_trades": counts[t]["closed"],
         "next_earnings_date": earnings.get(t)}
        for t in tickers
    ]})


@api_v1.route("/watchlist/tickers", methods=["POST"])
@require_auth
def add_tickers():
    """One endpoint for single and bulk add: the body is always a list.

    Reports per-symbol outcomes instead of failing the batch, so pasting
    thirty symbols with one typo adds twenty-nine and names the one.
    """
    from swingbot.core.marketdata.backtest_cache import ensure_cached_background
    from swingbot.core.marketdata.watchlist import add_ticker, load_watchlist

    payload = request.get_json(silent=True) or {}
    raw = payload.get("tickers")
    if isinstance(raw, str):
        # Tolerate a pasted blob, which is how the bulk form is actually used.
        raw = [t for t in re.split(r"[,\s]+", raw) if t.strip()]
    if not isinstance(raw, list):
        return error("invalid", "Body must contain a 'tickers' list.", 400)

    candidates = [str(t).strip().upper() for t in raw if str(t).strip()]
    path = _watchlist_path()
    existing = set(load_watchlist(path))

    added, already, invalid = [], [], []
    for ticker in candidates:
        if not _is_valid(ticker):
            invalid.append(ticker)
        elif ticker in existing:
            already.append(ticker)
        else:
            add_ticker(ticker, path)
            added.append(ticker)

    # Non-blocking history warm-up for genuinely new symbols; cached ones
    # return instantly, so a re-import does not refetch.
    for ticker in added:
        ensure_cached_background(ticker)

    return jsonify({
        "added": added, "already_present": already, "invalid": invalid,
        "total": len(load_watchlist(path)),
    })


@api_v1.route("/watchlist/tickers/<symbol>", methods=["DELETE"])
@require_auth
def remove_ticker_route(symbol: str):
    from swingbot.core.marketdata.watchlist import load_watchlist, remove_ticker

    symbol = symbol.strip().upper()
    path = _watchlist_path()
    if symbol not in set(load_watchlist(path)):
        return error("not_found", f"{symbol!r} is not in the watchlist.", 404)
    remaining = remove_ticker(symbol, path)
    return jsonify({"removed": symbol, "total": len(remaining)})


@api_v1.route("/watchlist/suggest", methods=["GET"])
@require_auth
def suggest():
    from swingbot.core.marketdata.ticker_directory import search_tickers

    return jsonify({"results": search_tickers(request.args.get("q", ""))})

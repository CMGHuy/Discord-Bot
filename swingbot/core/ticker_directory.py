"""
US-exchange ticker directory (NASDAQ + NYSE/AMEX) for the Watchlist page's
"Add ticker" autocomplete -- lets the admin UI suggest matches as you type
instead of you having to already know the exact symbol.

Source: NASDAQ Trader's own publicly-published, free symbol directory
files (no API key, no rate limit beyond plain HTTP):
  - https://ftp.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt   (NASDAQ)
  - https://ftp.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt    (NYSE, AMEX, etc.)
Both are simple pipe-delimited text files, refreshed by NASDAQ several
times a day; downloading once and caching locally for a week is more than
fresh enough for an autocomplete list (new listings are rare events, not
something that needs to show up within the hour).

Degrades gracefully if the network fetch fails or is blocked (e.g. no
outbound internet from the container) -- search_tickers() just returns an
empty list and a warning is logged once, matching this codebase's existing
pattern for other optional/best-effort features (logo fetching, trendln).
"""
import io
import logging
import os
import time
import urllib.request

from swingbot import config

log = logging.getLogger(__name__)

NASDAQ_LISTED_URL = "https://ftp.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
OTHER_LISTED_URL = "https://ftp.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"

_CACHE_PATH = os.path.join(config.DATA_DIR, "ticker_directory.json")
_REFRESH_INTERVAL_SECONDS = 7 * 24 * 3600  # re-download at most once a week

# In-memory copy for the life of the process, avoiding a JSON re-parse of a
# multi-thousand-row file on every single autocomplete keystroke.
_directory: list[dict] | None = None
_loaded_at = 0.0
_fetch_failed_once = False


def _parse_nasdaq_listed(text: str) -> list[dict]:
    rows = []
    lines = text.splitlines()
    for line in lines[1:]:  # skip header
        if not line or line.startswith("File Creation Time"):
            continue
        parts = line.split("|")
        if len(parts) < 2:
            continue
        symbol, name = parts[0].strip(), parts[1].strip()
        if not symbol or not name:
            continue
        # Test issues (parts[3] == 'Y' in this file's schema) are ETFs/SPACs
        # test-listings NASDAQ itself uses internally -- not real tradeable
        # tickers, so keep them out of the suggestion list.
        if len(parts) > 3 and parts[3].strip().upper() == "Y":
            continue
        rows.append({"symbol": symbol, "name": name})
    return rows


def _parse_other_listed(text: str) -> list[dict]:
    rows = []
    lines = text.splitlines()
    for line in lines[1:]:
        if not line or line.startswith("File Creation Time"):
            continue
        parts = line.split("|")
        if len(parts) < 8:
            continue
        # otherlisted.txt columns: ACT Symbol | Security Name | Exchange | ... | Test Issue | ...
        symbol, name, test_issue = parts[0].strip(), parts[1].strip(), parts[6].strip().upper()
        if not symbol or not name or test_issue == "Y":
            continue
        rows.append({"symbol": symbol, "name": name})
    return rows


def _download(url: str, timeout: int = 15) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "swingbot/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _build_directory() -> list[dict]:
    rows = []
    seen = set()
    for url, parser in ((NASDAQ_LISTED_URL, _parse_nasdaq_listed), (OTHER_LISTED_URL, _parse_other_listed)):
        try:
            text = _download(url)
            for row in parser(text):
                if row["symbol"] in seen:
                    continue
                seen.add(row["symbol"])
                rows.append(row)
        except Exception as exc:
            log.warning("Could not download ticker directory from %s: %s", url, exc)
    return rows


def _save_cache(rows: list[dict]) -> None:
    import json
    try:
        os.makedirs(config.DATA_DIR, exist_ok=True)
        with open(_CACHE_PATH, "w") as f:
            json.dump({"fetched_at": time.time(), "rows": rows}, f)
    except OSError as exc:
        log.warning("Could not write ticker directory cache: %s", exc)


def _load_cache() -> tuple[list[dict], float]:
    import json
    if not os.path.exists(_CACHE_PATH):
        return [], 0.0
    try:
        with open(_CACHE_PATH, "r") as f:
            data = json.load(f)
        return data.get("rows", []), data.get("fetched_at", 0.0)
    except (OSError, ValueError):
        return [], 0.0


def _ensure_loaded() -> None:
    """
    Loads the directory into memory, refreshing from the network if the
    on-disk cache is missing or older than _REFRESH_INTERVAL_SECONDS. A
    failed refresh falls back to whatever's already cached (even if
    stale) rather than leaving autocomplete empty over a transient
    network hiccup.
    """
    global _directory, _loaded_at, _fetch_failed_once
    if _directory is not None:
        return

    rows, fetched_at = _load_cache()
    age = time.time() - fetched_at if fetched_at else float("inf")
    if not rows or age > _REFRESH_INTERVAL_SECONDS:
        fresh = _build_directory()
        if fresh:
            rows = fresh
            _save_cache(rows)
        elif not rows and not _fetch_failed_once:
            log.warning(
                "Ticker directory could not be downloaded and no cache exists yet -- "
                "the Add-ticker autocomplete will show no suggestions until this succeeds."
            )
            _fetch_failed_once = True

    _directory = rows
    _loaded_at = time.time()


def search_tickers(query: str, limit: int = 15) -> list[dict]:
    """
    Returns up to `limit` {"symbol", "name"} matches for `query` (case
    insensitive), symbol-prefix matches first, then substring matches
    anywhere in the symbol or company name -- so typing "AAP" surfaces
    AAPL immediately, and typing "apple" still finds it via the name.
    Empty query returns an empty list rather than the entire ~10k-row
    directory.
    """
    query = (query or "").strip().upper()
    if not query:
        return []
    _ensure_loaded()
    if not _directory:
        return []

    starts_with = []
    contains = []
    for row in _directory:
        symbol = row["symbol"].upper()
        name = row["name"].upper()
        if symbol.startswith(query):
            starts_with.append(row)
        elif query in symbol or query in name:
            contains.append(row)
        if len(starts_with) >= limit:
            break

    results = (starts_with + contains)[:limit]
    return results

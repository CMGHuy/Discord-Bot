"""Financial Modeling Prep (FMP) API client -- crawls all available data for
a stock, tier-agnostic.

The SAME code works on the free and paid tiers: every endpoint call is
isolated, and an endpoint the current key can't reach (free-tier gating,
premium-only, or a legacy/renamed path) is recorded as ``gated``/``error``
rather than aborting the crawl. So the free tier yields whatever it's allowed
(profile, EOD prices, ~5yr annual statements) and a paid key yields more --
with no code change. Follows this repo's stdlib-urllib + degrade-gracefully
convention (see core/ticker_directory.py); no new dependency.

Get a key at https://financialmodelingprep.com and set it in the environment
(or .env) as FMP_API_KEY, or pass api_key= explicitly.

Usage:
    c = FMPClient()                      # reads FMP_API_KEY from env
    prof = c.profile("AAPL")             # one endpoint
    results = c.crawl_all("AAPL")        # everything, failures isolated
    for r in c.probe("AAPL"):            # what does my tier allow?
        print(r.name, r.status, r.n, r.detail)

Endpoint paths target FMP's current "stable" API. They're collected in one
registry (`_endpoints`) so any path FMP renames is a one-line fix; run
`probe()` (or `scripts/fmp_crawl.py --probe`) to see exactly which resolve on
your key.
"""
import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable

from swingbot import config

log = logging.getLogger("swing-bot.fmp_client")

STABLE_BASE = "https://financialmodelingprep.com/stable"

VALID_INTERVALS = ("1min", "5min", "15min", "30min", "1hour", "4hour")

# Default intraday resolutions crawl_all pulls (the user's swing use case cares
# about 15min + 1hour; override via crawl_all(intervals=...)).
DEFAULT_INTRADAY = ("1hour", "15min")


class FMPError(Exception):
    """Any FMP request failure."""


class FMPAccessError(FMPError):
    """Endpoint unreachable with the current key: tier-gated / premium-only /
    invalid key (HTTP 401/402/403) or an FMP 'upgrade'/'premium' message.
    This is the expected signal on the free tier -- crawl_all records it and
    moves on."""


class FMPRateLimitError(FMPError):
    """HTTP 429 -- rate/daily limit hit even after retries."""


@dataclass
class FMPResult:
    """Outcome of one endpoint in a crawl/probe."""
    name: str
    status: str            # "ok" | "empty" | "gated" | "ratelimited" | "error"
    n: int = 0             # row count (list) or 1 (object)
    detail: str = ""
    data: Any = None


@dataclass
class FMPClient:
    api_key: str = ""
    base_url: str = STABLE_BASE
    min_interval_s: float = 0.2   # throttle: ~300 req/min ceiling, tune per tier
    max_retries: int = 3
    timeout: float = 30.0
    _last_call: float = field(default=0.0, repr=False)

    def __post_init__(self):
        if not self.api_key:
            self.api_key = os.environ.get("FMP_API_KEY", "") or getattr(config, "FMP_API_KEY", "")

    # ------------------------------------------------------------------ core

    def _build_url(self, path: str, params: dict) -> str:
        q = {k: v for k, v in params.items() if v is not None}
        q["apikey"] = self.api_key or "MISSING"
        return f"{self.base_url}/{path.lstrip('/')}?{urllib.parse.urlencode(q)}"

    def _raw_get(self, url: str) -> tuple[int, str]:
        """Perform the HTTP GET. Split out so tests can monkeypatch it.
        Returns (status_code, body_text). Raises urllib HTTPError for non-2xx."""
        req = urllib.request.Request(url, headers={"User-Agent": "swingbot-fmp/1.0"})
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")

    def _throttle(self):
        if self.min_interval_s <= 0:
            return
        wait = self.min_interval_s - (time.monotonic() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.monotonic()

    def _get(self, path: str, **params) -> Any:
        """Fetch and parse one endpoint. Classifies failures into the FMP*
        exception types. Returns parsed JSON (list or dict)."""
        if not self.api_key:
            raise FMPAccessError(f"{path}: no API key (set FMP_API_KEY)")
        url = self._build_url(path, params)
        attempt = 0
        while True:
            self._throttle()
            try:
                status, body = self._raw_get(url)
            except urllib.error.HTTPError as e:
                code = e.code
                if code in (401, 402, 403):
                    raise FMPAccessError(f"{path}: HTTP {code} (tier-gated or invalid key)") from e
                if code == 429:
                    attempt += 1
                    if attempt > self.max_retries:
                        raise FMPRateLimitError(f"{path}: HTTP 429 after {self.max_retries} retries") from e
                    time.sleep(min(2 ** attempt, 30))
                    continue
                raise FMPError(f"{path}: HTTP {code}") from e
            except (urllib.error.URLError, TimeoutError) as e:
                raise FMPError(f"{path}: {e}") from e
            return self._parse(path, body)

    @staticmethod
    def _parse(path: str, body: str) -> Any:
        try:
            data = json.loads(body)
        except json.JSONDecodeError as e:
            raise FMPError(f"{path}: non-JSON response ({e})") from e
        # FMP frequently returns HTTP 200 with an error/notice dict.
        if isinstance(data, dict):
            msg = data.get("Error Message") or data.get("error") or data.get("message")
            if msg:
                low = str(msg).lower()
                gated_words = ("premium", "upgrade", "exclusive", "not available",
                               "legacy", "special", "plan", "subscription")
                if any(w in low for w in gated_words):
                    raise FMPAccessError(f"{path}: {msg}")
                raise FMPError(f"{path}: {msg}")
        return data

    # -------------------------------------------------- price & reference

    def profile(self, symbol: str) -> Any:
        return self._get("profile", symbol=symbol)

    def quote(self, symbol: str) -> Any:
        return self._get("quote", symbol=symbol)

    def peers(self, symbol: str) -> Any:
        return self._get("stock-peers", symbol=symbol)

    def historical_eod(self, symbol: str, from_: str = None, to: str = None) -> Any:
        """Daily OHLCV (split/dividend adjusted)."""
        return self._get("historical-price-eod/full", symbol=symbol, **{"from": from_, "to": to})

    def intraday(self, symbol: str, interval: str = "1hour",
                 from_: str = None, to: str = None) -> Any:
        """Intraday bars. interval in VALID_INTERVALS."""
        if interval not in VALID_INTERVALS:
            raise ValueError(f"interval must be one of {VALID_INTERVALS}, got {interval!r}")
        return self._get(f"historical-chart/{interval}", symbol=symbol,
                         **{"from": from_, "to": to})

    def dividends(self, symbol: str) -> Any:
        return self._get("dividends", symbol=symbol)

    def splits(self, symbol: str) -> Any:
        return self._get("splits", symbol=symbol)

    def historical_market_cap(self, symbol: str, limit: int = 5000) -> Any:
        return self._get("historical-market-capitalization", symbol=symbol, limit=limit)

    def shares_float(self, symbol: str) -> Any:
        return self._get("shares-float", symbol=symbol)

    # ------------------------------------------------------- fundamentals

    def income_statement(self, symbol: str, period: str = "annual", limit: int = 120) -> Any:
        return self._get("income-statement", symbol=symbol, period=period, limit=limit)

    def balance_sheet(self, symbol: str, period: str = "annual", limit: int = 120) -> Any:
        return self._get("balance-sheet-statement", symbol=symbol, period=period, limit=limit)

    def cash_flow(self, symbol: str, period: str = "annual", limit: int = 120) -> Any:
        return self._get("cash-flow-statement", symbol=symbol, period=period, limit=limit)

    def ratios(self, symbol: str, period: str = "annual", limit: int = 120) -> Any:
        return self._get("ratios", symbol=symbol, period=period, limit=limit)

    def key_metrics(self, symbol: str, period: str = "annual", limit: int = 120) -> Any:
        return self._get("key-metrics", symbol=symbol, period=period, limit=limit)

    def financial_growth(self, symbol: str, period: str = "annual", limit: int = 120) -> Any:
        return self._get("financial-growth", symbol=symbol, period=period, limit=limit)

    def enterprise_values(self, symbol: str, period: str = "annual", limit: int = 120) -> Any:
        return self._get("enterprise-values", symbol=symbol, period=period, limit=limit)

    # -------------------------------------------------- earnings & analysts

    def earnings(self, symbol: str, limit: int = 200) -> Any:
        """Historical earnings (reported vs estimate, dates)."""
        return self._get("earnings", symbol=symbol, limit=limit)

    def earnings_transcript_dates(self, symbol: str) -> Any:
        return self._get("earnings-call-transcript-dates", symbol=symbol)

    def earnings_transcript(self, symbol: str, year: int, quarter: int) -> Any:
        return self._get("earnings-call-transcript", symbol=symbol, year=year, quarter=quarter)

    def analyst_estimates(self, symbol: str, period: str = "annual", limit: int = 120) -> Any:
        return self._get("analyst-estimates", symbol=symbol, period=period, limit=limit)

    def price_target_summary(self, symbol: str) -> Any:
        return self._get("price-target-summary", symbol=symbol)

    def grades(self, symbol: str) -> Any:
        """Analyst upgrades/downgrades."""
        return self._get("grades", symbol=symbol)

    def rating(self, symbol: str) -> Any:
        return self._get("ratings-snapshot", symbol=symbol)

    # --------------------------------------------- ownership, filings, news

    def insider_trades(self, symbol: str, limit: int = 500) -> Any:
        return self._get("insider-trading/search", symbol=symbol, limit=limit)

    def institutional_ownership(self, symbol: str, limit: int = 500) -> Any:
        return self._get("institutional-ownership/extract-analytics/holder",
                         symbol=symbol, limit=limit)

    def sec_filings(self, symbol: str, limit: int = 500) -> Any:
        return self._get("sec-filings-search/symbol", symbol=symbol, limit=limit)

    def news(self, symbol: str, limit: int = 200) -> Any:
        return self._get("news/stock", symbols=symbol, limit=limit)

    # --------------------------------------------------- crawl / probe

    def _endpoints(self, symbol: str, intervals=DEFAULT_INTRADAY,
                   period: str = "annual") -> list[tuple[str, Callable[[], Any]]]:
        """Registry of (name, zero-arg callable) covering every method above.
        crawl_all and probe both iterate this."""
        eps: list[tuple[str, Callable[[], Any]]] = [
            ("profile", lambda: self.profile(symbol)),
            ("quote", lambda: self.quote(symbol)),
            ("peers", lambda: self.peers(symbol)),
            ("historical_eod", lambda: self.historical_eod(symbol)),
            ("dividends", lambda: self.dividends(symbol)),
            ("splits", lambda: self.splits(symbol)),
            ("historical_market_cap", lambda: self.historical_market_cap(symbol)),
            ("shares_float", lambda: self.shares_float(symbol)),
            ("income_statement", lambda: self.income_statement(symbol, period)),
            ("balance_sheet", lambda: self.balance_sheet(symbol, period)),
            ("cash_flow", lambda: self.cash_flow(symbol, period)),
            ("ratios", lambda: self.ratios(symbol, period)),
            ("key_metrics", lambda: self.key_metrics(symbol, period)),
            ("financial_growth", lambda: self.financial_growth(symbol, period)),
            ("enterprise_values", lambda: self.enterprise_values(symbol, period)),
            ("earnings", lambda: self.earnings(symbol)),
            ("earnings_transcript_dates", lambda: self.earnings_transcript_dates(symbol)),
            ("analyst_estimates", lambda: self.analyst_estimates(symbol, period)),
            ("price_target_summary", lambda: self.price_target_summary(symbol)),
            ("grades", lambda: self.grades(symbol)),
            ("rating", lambda: self.rating(symbol)),
            ("insider_trades", lambda: self.insider_trades(symbol)),
            ("institutional_ownership", lambda: self.institutional_ownership(symbol)),
            ("sec_filings", lambda: self.sec_filings(symbol)),
            ("news", lambda: self.news(symbol)),
        ]
        for iv in intervals:
            eps.append((f"intraday_{iv}", lambda iv=iv: self.intraday(symbol, iv)))
        return eps

    @staticmethod
    def _classify(data: Any) -> tuple[str, int]:
        if data is None:
            return "empty", 0
        if isinstance(data, list):
            return ("ok" if data else "empty"), len(data)
        if isinstance(data, dict):
            return ("ok" if data else "empty"), 1
        return "ok", 1

    def _run_one(self, name: str, fn: Callable[[], Any]) -> FMPResult:
        try:
            data = fn()
        except FMPAccessError as e:
            return FMPResult(name, "gated", 0, str(e))
        except FMPRateLimitError as e:
            return FMPResult(name, "ratelimited", 0, str(e))
        except (FMPError, ValueError) as e:
            return FMPResult(name, "error", 0, str(e))
        status, n = self._classify(data)
        return FMPResult(name, status, n, "", data)

    def crawl_all(self, symbol: str, intervals=DEFAULT_INTRADAY,
                  period: str = "annual") -> dict[str, FMPResult]:
        """Fetch every endpoint for `symbol`. Per-endpoint failures are
        isolated (never abort the crawl); returns {name: FMPResult}."""
        symbol = symbol.upper()
        results: dict[str, FMPResult] = {}
        for name, fn in self._endpoints(symbol, intervals, period):
            r = self._run_one(name, fn)
            results[name] = r
            log.debug("fmp crawl %s.%s -> %s (%d)", symbol, name, r.status, r.n)
        return results

    def probe(self, symbol: str, intervals=DEFAULT_INTRADAY,
              period: str = "annual") -> list[FMPResult]:
        """Like crawl_all but drops the payloads -- a lightweight report of
        which endpoints your current key/tier can reach."""
        out = []
        for name, res in self.crawl_all(symbol, intervals, period).items():
            out.append(FMPResult(name, res.status, res.n, res.detail, data=None))
        return out

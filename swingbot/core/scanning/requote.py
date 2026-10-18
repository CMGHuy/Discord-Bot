"""v171 D5: the pre-post re-quote. One batched fresh quote for the symbols
about to alert, a re-quote once per symbol whose quote aged past
QUOTE_MAX_AGE_REQUOTE_S, and the 5 s clock from fetch completion to persist."""
from __future__ import annotations

import dataclasses
import logging
import time
from datetime import datetime, timezone
from typing import Any, Callable, Iterator

from swingbot import config
from swingbot.core.marketdata.shared.kinds import Asker, QuoteDetail
from swingbot.core.planning.rebuild import RebuildOutcome, RebuildPrice, choose_rebuild_price

log = logging.getLogger(__name__)


def _wants_quote(item) -> bool:
    """Only an item meeting every requirement can alert, so only it is quoted."""
    return getattr(item, "all_requirements_met", True)


def _ticker(item) -> str:
    return item.result.ticker


def _scan_price(item) -> float:
    return getattr(item, "scan_price", None) or item.result.close


def _default_quote_fn(tickers: list[str]) -> dict[str, QuoteDetail]:
    """A fresh fetch at tier 2: a 0 s window is never served from cache."""
    from swingbot.core.marketdata import data
    return data.get_quote_batch(tickers, asker=Asker.REQUOTE, max_age_s=0.0)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Requote:
    """Re-quote and rebuild the alerting items of one scan, flag-gated."""

    def __init__(self, items, *,
                 quote_fn: Callable[[list[str]], dict[str, QuoteDetail]] | None = None,
                 clock=time.monotonic, now_fn=None):
        self.enabled = bool(config.PLAN_REBUILD_ENABLED)
        self._tickers = list(dict.fromkeys(_ticker(i) for i in items if _wants_quote(i)))
        self._quote_fn = quote_fn if quote_fn is not None else _default_quote_fn
        self._clock = clock
        self._now_fn = now_fn if now_fn is not None else _utc_now
        self._quotes: dict[str, QuoteDetail] = {}
        self._fetched_at: dict[str, float] = {}
        self._ages: dict[str, float] = {}
        self._prices: dict[str, RebuildPrice] = {}
        self._requoted: set[str] = set()
        self._batched = False
        self.kept = 0
        self.dropped = 0
        self._misses = 0

    def _fetch(self, tickers: list[str]) -> None:
        try:
            got = self._quote_fn(list(tickers)) or {}
        except Exception as exc:
            log.warning("Re-quote failed for %d symbol(s): %s", len(tickers), exc)
            got = {}
        done = self._clock()
        for ticker in tickers:
            quote = got.get(ticker)
            if quote is not None:
                self._quotes[ticker] = quote
                self._fetched_at[ticker] = done
            else:
                self._fetched_at.setdefault(ticker, done)

    def _ensure_fresh(self, ticker: str) -> None:
        if not self._batched:
            self._batched = True
            self._fetch(self._tickers)
            return
        if ticker in self._requoted:
            return
        age = self._clock() - self._fetched_at.get(ticker, float("-inf"))
        if age > config.QUOTE_MAX_AGE_REQUOTE_S:
            self._requoted.add(ticker)
            self._fetch([ticker])

    def _rebuild(self, item, rebuild: Callable[[Any, RebuildPrice], RebuildOutcome]) -> RebuildOutcome:
        ticker = _ticker(item)
        self._ensure_fresh(ticker)
        price = choose_rebuild_price(self._quotes.get(ticker), _scan_price(item), self._now_fn())
        price = dataclasses.replace(price, fetched_at=self._fetched_at.get(ticker))
        outcome = rebuild(item, price)
        if outcome.kept:
            self._prices[ticker] = outcome.price
        return outcome

    def iter_fresh(self, items, *,
                   rebuild: Callable[[Any, RebuildPrice], RebuildOutcome]) -> Iterator:
        """Yield the items to post, each rebuilt at its fresh price; a dropped
        item is logged and never yielded. Flag off: the items, untouched."""
        if not self.enabled:
            yield from items
            return
        for item in items:
            if not _wants_quote(item):
                yield item
                continue
            outcome = self._rebuild(item, rebuild)
            if outcome.kept:
                self.kept += 1
                yield item
                continue
            self.dropped += 1
            result = item.result
            log.info("%s (%s, %s): not posted -- %s (rebuild at %.2f, %s)",
                     result.ticker, result.horizon_key, result.trend, outcome.reason,
                     outcome.price.price, outcome.price.kind)

    def age_at_persist(self, ticker: str) -> float | None:
        """Seconds from the symbol's quote fetch to now, frozen at the first
        call (the persist); a first reading over the limit counts a miss."""
        if ticker in self._ages:
            return self._ages[ticker]
        fetched_at = self._fetched_at.get(ticker)
        if fetched_at is None:
            return None
        age = round(self._clock() - fetched_at, 2)
        self._ages[ticker] = age
        if age > config.QUOTE_MAX_AGE_REQUOTE_S:
            self._misses += 1
        return age

    def price_for(self, ticker: str) -> RebuildPrice | None:
        """The price the symbol's last kept item was built from."""
        return self._prices.get(ticker)

    @property
    def misses(self) -> int:
        return self._misses

    def stats(self) -> dict:
        return {"kept": self.kept, "dropped": self.dropped, "misses": self._misses}

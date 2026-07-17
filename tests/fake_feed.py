"""Deterministic price feed for PlanManager tests -- no network, no clock."""
from collections import defaultdict, deque


class FakePriceFeed:
    def __init__(self, ticks=None):
        self._queues: dict[str, deque] = defaultdict(deque)
        self._last: dict[str, float] = {}
        for ticker, price in ticks or []:
            self._queues[ticker].append(float(price))

    def set_series(self, ticker: str, prices) -> None:
        self._queues[ticker].extend(float(p) for p in prices)

    def get_price(self, ticker: str) -> float:
        q = self._queues.get(ticker)
        if q:
            self._last[ticker] = q.popleft()
        if ticker not in self._last:
            raise KeyError(f"no ticks queued for {ticker}")
        return self._last[ticker]

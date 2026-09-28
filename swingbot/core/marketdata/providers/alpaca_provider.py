"""v106 Alpaca market-data provider (alpaca-py). Bars: SIP, >=16 min old,
fully adjusted. Live: last trade on the configured feed, never its volume.
Every failure is an AlpacaMiss so the router can fall back per symbol."""
from datetime import datetime, time as dtime, timedelta, timezone

import pandas as pd
from alpaca.data.enums import Adjustment, DataFeed
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest, StockSnapshotRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

from swingbot.core.marketdata.providers.base import (
    NY, to_alpaca_symbol, to_yf_daily, to_yf_hourly)

SIP_DELAY = timedelta(minutes=16)
HISTORY_FLOOR = datetime(2016, 1, 1, tzinfo=timezone.utc)
_PERIOD_DAYS = {"1d": 5, "5d": 7, "1mo": 31, "3mo": 92, "6mo": 183, "1y": 366,
                "2y": 731, "5y": 1827, "10y": 3653}
INTRADAY_DAYS = 700
ROWS_PER_PAGE = 10_000      # Alpaca bars page size; a request past it paginates serially


class AlpacaMiss(Exception):
    """Alpaca could not answer; the router falls back to yfinance."""


class AlpacaAuthError(AlpacaMiss):
    """401/403 -- the router latches its breaker until the keys change."""


def _start_for(period: str, now: datetime) -> datetime:
    days = _PERIOD_DAYS.get(period)
    return HISTORY_FLOOR if days is None else max(HISTORY_FLOOR, now - timedelta(days=days))


def symbols_per_request(period: str, now: datetime = None) -> int:
    """Symbols whose daily bars for `period` fit one 10k-row page (v106 T13a)."""
    now = now or datetime.now(timezone.utc)
    rows = (now - _start_for(period, now)).days * 252 // 365 + 10
    return max(1, ROWS_PER_PAGE // rows)


def _in_regular_session(now: datetime) -> bool:
    ny = now.astimezone(NY)
    return ny.weekday() < 5 and dtime(9, 30) <= ny.time() < dtime(16, 0)


class AlpacaProvider:
    def __init__(self, key_id: str, secret: str, live_feed: str = "iex", *,
                 client=None, now=None):
        self._client = client or StockHistoricalDataClient(key_id, secret)
        self._live_feed = DataFeed(live_feed.lower())
        self._now = now or (lambda: datetime.now(timezone.utc))

    def _call(self, method, req):
        try:
            return getattr(self._client, method)(req)
        except Exception as exc:
            if getattr(exc, "status_code", None) in (401, 403):
                raise AlpacaAuthError(str(exc)) from exc
            raise AlpacaMiss(str(exc)) from exc

    def _bars(self, tickers, timeframe, start):
        by_symbol = {to_alpaca_symbol(t): t for t in tickers}
        req = StockBarsRequest(symbol_or_symbols=list(by_symbol), timeframe=timeframe,
                               start=start, end=self._now() - SIP_DELAY,
                               feed=DataFeed.SIP, adjustment=Adjustment.ALL)
        df = self._call("get_stock_bars", req).df
        if df is None or df.empty:
            return {}
        present = set(df.index.get_level_values("symbol"))
        return {by_symbol[s]: df.xs(s, level="symbol") for s in by_symbol if s in present}

    def daily_bars(self, tickers, period):
        now = self._now()
        raw = self._bars(tickers, TimeFrame.Day, _start_for(period, now))
        return {t: to_yf_daily(df) for t, df in raw.items() if not df.empty}

    def intraday_bars(self, ticker, interval):
        if interval != "1h":
            return None
        start = self._now() - timedelta(days=INTRADAY_DAYS)
        raw = self._bars([ticker], TimeFrame(30, TimeFrameUnit.Minute), start)
        df = raw.get(ticker)
        return None if df is None or df.empty else to_yf_hourly(df)

    def _fresh_price(self, snap, now, max_age_s):
        trade = getattr(snap, "latest_trade", None)
        if trade is None or not trade.price or trade.price <= 0:
            return None
        if _in_regular_session(now) and (now - trade.timestamp).total_seconds() > max_age_s:
            return None
        return float(trade.price)

    def latest_prices(self, tickers, max_trade_age_s):
        by_symbol = {to_alpaca_symbol(t): t for t in tickers}
        req = StockSnapshotRequest(symbol_or_symbols=list(by_symbol), feed=self._live_feed)
        snaps = self._call("get_stock_snapshot", req) or {}
        now = self._now()
        out = {}
        for sym, snap in snaps.items():
            price = self._fresh_price(snap, now, max_trade_age_s) if sym in by_symbol else None
            if price is not None:
                out[by_symbol[sym]] = price
        return out

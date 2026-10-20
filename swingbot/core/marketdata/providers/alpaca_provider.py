"""v106 Alpaca market-data provider (alpaca-py). Bars: SIP, >=16 min old,
fully adjusted. Live: last trade on the configured feed, never its volume.
Every failure is an AlpacaMiss so the router can fall back per symbol."""
import logging
from datetime import datetime, time as dtime, timedelta, timezone

import pandas as pd
from alpaca.data.enums import Adjustment, DataFeed
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest, StockSnapshotRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

from swingbot.core.marketdata.providers.base import (
    NY, to_alpaca_symbol, to_yf_daily, to_yf_hourly)
from swingbot.core.marketdata.shared.kinds import QuoteDetail

log = logging.getLogger(__name__)

SIP_DELAY = timedelta(minutes=16)
HISTORY_FLOOR = datetime(2016, 1, 1, tzinfo=timezone.utc)
_PERIOD_DAYS = {"1d": 5, "5d": 7, "1mo": 31, "3mo": 92, "6mo": 183, "1y": 366,
                "2y": 731, "5y": 1827, "10y": 3653}
INTRADAY_DAYS = 700
ROWS_PER_PAGE = 10_000      # Alpaca bars page size; a request past it paginates serially

#: v162 history store timeframes -> Alpaca bar size. Native 1Hour bars are
#: clock-aligned and never used: hourly is rebuilt from 30-minute bars.
HISTORY_TIMEFRAMES = {
    "15min": TimeFrame(15, TimeFrameUnit.Minute),
    "30min": TimeFrame(30, TimeFrameUnit.Minute),
    "1d": TimeFrame.Day,
}


_RAW_COLS = ["t", "o", "h", "l", "c", "v"]
_FRAME_COLS = ["open", "high", "low", "close", "volume"]


def _frames_from_raw(raw: dict) -> dict:
    """{alpaca symbol: frame} from a raw_data=True bars response, in the shape
    BarSet.df.xs(symbol) had: lowercase OHLCV columns over a tz-aware UTC
    index. Every symbol's timestamps are parsed in one vectorised pass."""
    symbols = [s for s, bars in raw.items() if bars]
    if not symbols:
        return {}
    flat = pd.DataFrame.from_records([b for s in symbols for b in raw[s]], columns=_RAW_COLS)
    index = pd.DatetimeIndex(pd.to_datetime(flat["t"], utc=True, format="ISO8601"), name="timestamp")
    values = flat[_RAW_COLS[1:]].to_numpy(dtype="float64")
    out, start = {}, 0
    for symbol in symbols:
        end = start + len(raw[symbol])
        out[symbol] = pd.DataFrame(values[start:end], columns=_FRAME_COLS, index=index[start:end])
        start = end
    return out


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
        # Bars come back as raw dicts (v106 T13b): alpaca-py's model path
        # (Bar objects, then BarSet.df) costs ~0.45 s of GIL-bound CPU per
        # 10k-row page, which serialises the router's parallel batches.
        # An injected client serves both roles.
        self._bars_client = client or StockHistoricalDataClient(key_id, secret, raw_data=True)
        self._live_feed = DataFeed(live_feed.lower())
        self._now = now or (lambda: datetime.now(timezone.utc))

    def _call(self, method, req, client=None):
        try:
            return getattr(client or self._client, method)(req)
        except Exception as exc:
            if getattr(exc, "status_code", None) in (401, 403):
                raise AlpacaAuthError(str(exc)) from exc
            raise AlpacaMiss(str(exc)) from exc

    def _bars(self, tickers, timeframe, start, end=None):
        latest = self._now() - SIP_DELAY
        by_symbol = {to_alpaca_symbol(t): t for t in tickers}
        req = StockBarsRequest(symbol_or_symbols=list(by_symbol), timeframe=timeframe,
                               start=start, end=latest if end is None else min(end, latest),
                               feed=DataFeed.SIP, adjustment=Adjustment.ALL)
        raw = self._call("get_stock_bars", req, self._bars_client) or {}
        return {by_symbol[s]: df for s, df in _frames_from_raw(raw).items() if s in by_symbol}

    def daily_bars(self, tickers, period):
        now = self._now()
        raw = self._bars(tickers, TimeFrame.Day, _start_for(period, now))
        return {t: to_yf_daily(df) for t, df in raw.items() if not df.empty}

    def daily_bars_between(self, tickers, start, end):
        """v171 D4: daily bars dated start..end (inclusive), SIP, Adjustment.ALL."""
        lo = datetime(start.year, start.month, start.day, tzinfo=timezone.utc)
        hi = datetime(end.year, end.month, end.day, tzinfo=timezone.utc) + timedelta(days=1)
        raw = self._bars(tickers, TimeFrame.Day, lo, hi)
        return {t: to_yf_daily(df) for t, df in raw.items() if not df.empty}

    def intraday_bars(self, ticker, interval):
        if interval != "1h":
            return None
        start = self._now() - timedelta(days=INTRADAY_DAYS)
        raw = self._bars([ticker], TimeFrame(30, TimeFrameUnit.Minute), start)
        df = raw.get(ticker)
        return None if df is None or df.empty else to_yf_hourly(df)

    def history_bars(self, ticker, timeframe, start, end):
        """v162: one symbol's raw bars over [start, end] for the history store.

        SIP feed, Adjustment.ALL, `end` clamped to now - SIP_DELAY (the free
        plan's delay). alpaca-py pages inside the one call, so callers bound
        memory by asking for one calendar year at a time. Returns the raw
        frame (lowercase open..volume, tz-aware UTC index) or None when there
        are no bars. Live callers keep using _bars; this method is research-only.
        """
        bar_size = HISTORY_TIMEFRAMES.get(timeframe)
        if bar_size is None:
            raise ValueError(f"unknown history timeframe {timeframe!r}; "
                             f"expected one of {sorted(HISTORY_TIMEFRAMES)}")
        end = min(end, self._now() - SIP_DELAY)
        if start >= end:
            return None
        symbol = to_alpaca_symbol(ticker)
        req = StockBarsRequest(symbol_or_symbols=[symbol], timeframe=bar_size,
                               start=start, end=end,
                               feed=DataFeed.SIP, adjustment=Adjustment.ALL)
        raw = self._call("get_stock_bars", req, self._bars_client) or {}
        df = _frames_from_raw(raw).get(symbol)
        return None if df is None or df.empty else df

    def _fresh_price(self, snap, now, max_age_s):
        trade = getattr(snap, "latest_trade", None)
        if trade is None or not trade.price or trade.price <= 0:
            return None
        if _in_regular_session(now) and (now - trade.timestamp).total_seconds() > max_age_s:
            return None
        return float(trade.price)

    def _quote_sides(self, snap):
        """(bid, ask, quote_at) from the snapshot's latest quote; a missing or
        non-positive side is None, and quote_at is None unless both sides exist."""
        quote = getattr(snap, "latest_quote", None)
        if quote is None:
            return None, None, None
        bid = float(quote.bid_price) if quote.bid_price and quote.bid_price > 0 else None
        ask = float(quote.ask_price) if quote.ask_price and quote.ask_price > 0 else None
        return bid, ask, (quote.timestamp if bid and ask else None)

    def _detail(self, ticker, snap, now, max_age_s):
        price = self._fresh_price(snap, now, max_age_s)
        bid, ask, quote_at = self._quote_sides(snap)
        if price is None and quote_at is None:
            return None
        trade_at = snap.latest_trade.timestamp if price is not None else None
        return QuoteDetail(symbol=ticker, price=price, trade_at=trade_at, bid=bid, ask=ask,
                           quote_at=quote_at, source=f"alpaca-{self._live_feed.value}")

    def latest_quotes(self, tickers, max_trade_age_s):
        """v171: latest_prices with timestamps and the IEX bid/ask. One snapshot call."""
        by_symbol = {to_alpaca_symbol(t): t for t in tickers}
        req = StockSnapshotRequest(symbol_or_symbols=list(by_symbol), feed=self._live_feed)
        snaps = self._call("get_stock_snapshot", req) or {}
        now = self._now()
        out = {}
        for sym, snap in snaps.items():
            detail = self._detail(by_symbol[sym], snap, now, max_trade_age_s) if sym in by_symbol else None
            if detail is not None:
                out[detail.symbol] = detail
        return out

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
        missing = [t for t in tickers if t not in out]
        if missing:
            log.debug("Alpaca snapshot: no fresh price for %s", ", ".join(missing[:10]))
        return out

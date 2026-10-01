#!/usr/bin/env python3
"""Read-only health check of both market-data sources.

Run inside the bot container:  python scripts/ops/data_sources_check.py [TICKER ...]

For 3 liquid tickers it measures Alpaca (2y daily bars, latest price, 1h bars)
and yfinance (2y daily bars, latest price) DIRECTLY -- bypassing the router and
its circuit breaker -- then compares the two sources' daily closes and checks
the router's own scan-path frame is at least as deep as the on-disk cache.
Exit 0 only when both sources are retrievable and agree; non-zero otherwise.
Guarded by __main__ because the provider path uses a process pool.
"""
from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

TICKERS = ("AAPL", "MSFT", "SPY")
TOLERANCE = 0.005          # 0.5 %
OVERLAP_BARS = 250
MIN_OVERLAP = 20


@dataclass
class Probe:
    source: str
    what: str
    ok: bool
    seconds: float
    rows: int = 0
    last_close: float = None
    error: str = ""


def _last_close(value):
    """Last close of a daily frame, the float itself, or None."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if getattr(value, "empty", True):
        return None
    return float(value["Close"].iloc[-1])


def probe(source: str, what: str, fn) -> Probe:
    """Run one fetch; any exception or empty result is a FAIL, never a raise."""
    t0 = time.monotonic()
    try:
        value = fn()
    except Exception as exc:
        return Probe(source, what, False, time.monotonic() - t0, error=f"{type(exc).__name__}: {exc}")
    elapsed = time.monotonic() - t0
    rows = 0 if value is None or isinstance(value, (int, float)) else len(value)
    last = _last_close(value)
    ok = last is not None and last > 0
    return Probe(source, what, ok, elapsed, rows, last, "" if ok else "empty result")


def format_probe(ticker: str, p: Probe) -> str:
    close = "-" if p.last_close is None else f"{p.last_close:.2f}"
    note = f"  [{p.error}]" if p.error else ""
    return (f"{ticker:<6} {p.source:<9} {p.what:<7} {p.seconds:6.2f}s rows={p.rows:<5} "
            f"last={close:<10} {'OK' if p.ok else 'FAIL'}{note}")


def _date_indexed(frame):
    """Copy of `frame` indexed by tz-naive midnight dates, so sources that stamp
    bars differently (tz-aware, 04:00 / 05:00 UTC) still line up."""
    idx = frame.index
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_localize(None)
    out = frame.copy()
    out.index = idx.normalize()
    return out


def compare_frames(alpaca, yf, tolerance: float = TOLERANCE, bars: int = OVERLAP_BARS):
    """(ok, detail): last close of both frames and the median close ratio over
    the most recent `bars` shared dates must each be within `tolerance`."""
    if alpaca is None or yf is None or alpaca.empty or yf.empty:
        return False, "a frame is missing"
    alpaca, yf = _date_indexed(alpaca), _date_indexed(yf)
    common = alpaca.index.intersection(yf.index)[-bars:]
    if len(common) < MIN_OVERLAP:
        return False, f"only {len(common)} overlapping bars"
    ratios = (alpaca.loc[common, "Close"] / yf.loc[common, "Close"]).dropna()
    last = float(alpaca["Close"].iloc[-1]) / float(yf["Close"].iloc[-1])
    median = float(ratios.median())
    ok = abs(last - 1) <= tolerance and abs(median - 1) <= tolerance
    return ok, f"last-close ratio {last:.4f}, median ratio {median:.4f} over {len(common)} bars"


def depth_ok(router_frame, cached_frame):
    """(ok, detail): the router's scan-path frame must be at least as deep as
    the cache (no cache = nothing to compare = ok)."""
    have = 0 if router_frame is None else len(router_frame)
    if cached_frame is None or len(cached_frame) == 0:
        return have > 0, f"{have} rows, no cache"
    return have >= len(cached_frame), f"{have} rows vs cache {len(cached_frame)}"


def decide(probes: list, comparisons: list, depths: list):
    """(exit_code, messages). 0 only if every probe passed (the Alpaca-only 1h
    probe included) and every comparison/depth agrees."""
    messages = [f"FAIL {p.source} {p.what}: {p.error}" for p in probes if not p.ok]
    messages += [f"FAIL compare {name}: {detail}" for name, ok, detail in comparisons if not ok]
    messages += [f"FAIL depth {name}: {detail}" for name, ok, detail in depths if not ok]
    return (1 if messages else 0), messages


def _alpaca_provider():
    from swingbot import config
    from swingbot.core.marketdata.providers.alpaca_provider import AlpacaProvider
    if not config.ALPACA_API_KEY_ID:
        raise RuntimeError("ALPACA_API_KEY_ID is not set")
    return AlpacaProvider(config.ALPACA_API_KEY_ID, config.ALPACA_API_SECRET_KEY,
                          config.ALPACA_DATA_FEED_LIVE)


def _probe_ticker(ticker: str, alp):
    from swingbot.core.marketdata import data
    from swingbot import config
    frames, probes = {}, []

    def grab(source, what, fn, key=None):
        p = probe(source, what, lambda: frames.setdefault(key, fn()) if key else fn())
        probes.append(p)
        print(format_probe(ticker, p))

    grab("alpaca", "daily", lambda: alp.daily_bars([ticker], "2y").get(ticker), "alpaca")
    grab("alpaca", "price", lambda: alp.latest_prices(
        [ticker], int(config.ALPACA_MAX_TRADE_AGE_SECONDS)).get(ticker))
    grab("alpaca", "1h", lambda: alp.intraday_bars(ticker, "1h"))
    grab("yfinance", "daily", lambda: data._yf_daily_batch([ticker], "2y").get(ticker), "yf")
    grab("yfinance", "price", lambda: data._yf_batch_prices([ticker]).get(ticker))
    return frames, probes


def _router_depth(ticker: str):
    from swingbot.core.marketdata import data, data_store
    from swingbot.core.scanning import fetch
    live = data.get_daily_data_batch([ticker]).get(ticker)
    cached = data_store.load_normalized(ticker, "daily")
    return depth_ok(fetch._with_cached_depth(ticker, live), cached)


def _guarded(fn, *args):
    """(ok, detail) from a glue step that returns that pair; an exception is a
    FAIL line `<ExcType>: msg`, never a raise."""
    try:
        return fn(*args)
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def _check_ticker(ticker: str, alp):
    """(probes, comparison, depth) for one ticker; no step can abort the run."""
    try:
        frames, probes = _probe_ticker(ticker, alp)
    except Exception as exc:
        frames = {}
        probes = [Probe("glue", "probe", False, 0.0, error=f"{type(exc).__name__}: {exc}")]
    ok, detail = _guarded(compare_frames, frames.get("alpaca"), frames.get("yf"))
    print(f"{ticker:<6} compare   {'OK' if ok else 'FAIL'}  {detail}")
    d_ok, d_detail = _guarded(_router_depth, ticker)
    print(f"{ticker:<6} depth     {'OK' if d_ok else 'FAIL'}  {d_detail}")
    return probes, (ticker, ok, detail), (ticker, d_ok, d_detail)


def run(tickers) -> int:
    probes, comparisons, depths = [], [], []
    try:
        alp = _alpaca_provider()
    except Exception as exc:
        print(f"FAIL alpaca provider: {exc}")
        return 1
    for ticker in tickers:
        got, comparison, depth = _check_ticker(ticker, alp)
        probes += got
        comparisons.append(comparison)
        depths.append(depth)
    code, messages = decide(probes, comparisons, depths)
    print("\n".join(messages) if messages else "OK: both sources retrievable and in agreement")
    return code


if __name__ == "__main__":
    sys.exit(run(tuple(sys.argv[1:]) or TICKERS))

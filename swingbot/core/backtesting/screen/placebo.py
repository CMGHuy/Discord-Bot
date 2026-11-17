"""v230 A1: the placebo harness -- universes with no edge by construction.

Each universe is a screen cache directory on a given trading calendar:
<T>.csv (Date,Open,High,Low,Close,Volume), membership.csv (one span per
ticker from the first session, open end), a synthetic SPY.csv built as the
equal-weight index after generation, and universe.json (written last: its
presence marks a complete universe).

gbm: driftless (martingale) geometric random walks. Daily sd = level /
ATR_PER_SIGMA, x STRESS_MULT while stressed; stressed = the ticker's own
two-state Markov chain OR one shared market chain, so volatility clusters
and ATR14 lags it. Overnight gap and open-to-close legs split the variance
(GAP_SHARE); wicks widen max/min(open, close). ATR_PER_SIGMA (1.9) was
fitted by simulating this model: median ATR14 % of close / calm sd = 1.89.
One seed per ticker, [seed, crc32(ticker)], so a ticker's path does not
depend on the ticker count.

shuffled: the real cached bars with whole trading days 1..n-1 permuted, one
permutation shared by every ticker. Each day carries its close-to-close
return, open/high/low-to-close ratios and volume, so each day's
cross-section survives and no serial structure does.

No date literal lives here: the calendar is always a parameter.
"""
from __future__ import annotations

import hashlib
import json
import zlib
from pathlib import Path
from typing import Mapping

import numpy as np
import pandas as pd

from swingbot.core.backtesting.screen import indicators
from swingbot.core.backtesting.screen.context import CONTEXT_ONLY_STEMS

PLACEBO_SEED = 42
GBM_TICKERS = 200
INDEX_TICKER = "SPY"
MEMBERSHIP_FILE = "membership.csv"
MANIFEST_FILE = "universe.json"
OHLCV = ("Open", "High", "Low", "Close", "Volume")

STRESS_ENTER = 0.02     # P(calm -> stressed) per session
STRESS_EXIT = 0.10      # P(stressed -> calm) per session
STRESS_MULT = 2.0
GAP_SHARE = 0.4         # overnight gap sd as a share of the daily sd
WICK_SHARE = 0.5        # wick sd as a share of the open-to-close sd
ATR_PER_SIGMA = 1.9     # median ATR14 % of close per unit of calm daily sd (simulated)
QUARTILE_POINTS = (12.5, 37.5, 62.5, 87.5)
GBM_VOLUME = 1_000_000.0
PRICE_FORMAT = "%.6f"
_MARKET_STREAM = zlib.crc32(b"market")
_LEVEL_STREAM = 1


def ticker_seed(ticker: str, base: int = PLACEBO_SEED) -> list:
    return [base, zlib.crc32(ticker.encode("utf-8"))]


def read_frame(path) -> pd.DataFrame:
    """One cache CSV, tz-naive, sorted, duplicates dropped, OHLCV only."""
    df = pd.read_csv(path, parse_dates=["Date"], index_col="Date")
    if getattr(df.index, "tz", None) is not None:
        df.index = df.index.tz_localize(None)
    df = df[~df.index.duplicated(keep="first")].sort_index()
    return df.loc[:, list(OHLCV)].dropna()


def trading_calendar(spy_csv, start: str, end: str) -> pd.DatetimeIndex:
    """The index ticker's sessions in [start, end]."""
    idx = read_frame(spy_csv).index
    idx = idx[(idx >= pd.Timestamp(start)) & (idx <= pd.Timestamp(end))]
    if len(idx) == 0:
        raise ValueError(f"{spy_csv}: no session in {start}..{end}")
    return pd.DatetimeIndex(idx, name="Date")


def _source_files(cache_dir, tickers=None) -> list[Path]:
    """Ticker CSVs only: no index, context-only, ^-prefixed or _-prefixed files."""
    paths = sorted(Path(cache_dir).glob("*.csv"))
    keep = [p for p in paths if p.stem != INDEX_TICKER and p.stem not in CONTEXT_ONLY_STEMS
            and not p.stem.startswith(("^", "_"))]
    return keep if tickers is None else [p for p in keep if p.stem in set(tickers)]


def _on_calendar(path, calendar: pd.DatetimeIndex) -> pd.DataFrame:
    df = read_frame(path)
    return df.loc[(df.index >= calendar[0]) & (df.index <= calendar[-1])]


def atr_pct_quartiles(cache_dir, calendar, tickers=None) -> tuple[float, float, float, float]:
    """Quartile midpoints (QUARTILE_POINTS) of the per-ticker median ATR14 % of close."""
    medians = []
    for path in _source_files(cache_dir, tickers):
        df = _on_calendar(path, calendar)
        if len(df) < 15:
            continue
        value = float(np.nanmedian((indicators.atr(df) / df["Close"]).to_numpy(dtype=float)))
        if np.isfinite(value):
            medians.append(value)
    if not medians:
        raise ValueError(f"no ATR% could be measured in {cache_dir}")
    return tuple(float(v) for v in np.percentile(medians, QUARTILE_POINTS))


def _markov(rng, n: int) -> np.ndarray:
    """A two-state chain starting calm; True = stressed."""
    draws = rng.random(n)
    out = np.zeros(n, dtype=bool)
    for t in range(1, n):
        out[t] = draws[t] >= STRESS_EXIT if out[t - 1] else draws[t] < STRESS_ENTER
    return out


def market_states(calendar, seed) -> np.ndarray:
    """The shared market chain (True = stressed), one per universe seed."""
    return _markov(np.random.default_rng([seed, _MARKET_STREAM]), len(calendar))


def _lognormal(rng, sd: np.ndarray) -> np.ndarray:
    """Log-returns with mean -sd^2/2: exp() of them has expectation one."""
    return rng.normal(-sd ** 2 / 2.0, sd)


def gbm_frame(ticker: str, calendar, *, level: float, stressed,
              seed: int = PLACEBO_SEED) -> pd.DataFrame:
    """One driftless OHLCV path whose median ATR14 % of close sits near ``level``."""
    rng = np.random.default_rng(ticker_seed(ticker, seed))
    n = len(calendar)
    regime = _markov(rng, n) | np.asarray(stressed, dtype=bool)
    sd = level / ATR_PER_SIGMA * np.where(regime, STRESS_MULT, 1.0)
    day_sd = np.sqrt(1.0 - GAP_SHARE ** 2) * sd
    gap, day = _lognormal(rng, GAP_SHARE * sd), _lognormal(rng, day_sd)
    close = rng.uniform(20.0, 200.0) * np.exp(np.cumsum(gap + day))
    open_ = close * np.exp(-day)
    up = np.abs(rng.normal(0.0, WICK_SHARE * day_sd))
    down = np.abs(rng.normal(0.0, WICK_SHARE * day_sd))
    return pd.DataFrame({"Open": open_, "High": np.maximum(open_, close) * np.exp(up),
                         "Low": np.minimum(open_, close) * np.exp(-down), "Close": close,
                         "Volume": np.full(n, GBM_VOLUME)},
                        index=pd.DatetimeIndex(calendar, name="Date"))

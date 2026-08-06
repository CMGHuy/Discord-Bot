"""Task 13: full-corpus sizing-parity harness (pytest side).

Compares `backtest._trade_plan_at` (CURRENT -- it already delegates to
`plan_engine`, see swingbot/core/backtest.py) against
`tests.fixtures.legacy_trade_plan_at.legacy_trade_plan_at`, a FROZEN copy of
`_trade_plan_at` as it stood pre-extraction (commit ac91654, before Task 14
rewired it to call plan_engine). That frozen copy is the only remaining
independent "old" implementation -- tests/test_plan_engine_sizing.py already
compares plan_engine against the *current* (post-delegation)
`backtest._trade_plan_at`, which is plan_engine calling itself through one
layer of indirection and can no longer prove extraction correctness on its
own.

Runs on 3 fixed cached tickers x all 11 strategies x horizons {"4w", "3m"}
for speed; `scripts/parity_sizing.py` runs the same comparison over every
cached ticker, every strategy, every horizon, every TRAIN-window entry bar.

Skipped (not failed) when data/backtest_cache/ is absent, so CI without the
(git-ignored) OHLCV cache stays green.
"""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from swingbot.core import backtest
from swingbot.core.backtest import ALL_STRATEGIES
from swingbot.core.indicators import atr, elliott_wave3_entries
from swingbot.core.strategy_types import HORIZONS, MIN_BARS

from tests.fixtures.legacy_trade_plan_at import legacy_trade_plan_at

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "data" / "backtest_cache"
TOLERANCE = 1e-6
HORIZON_KEYS = ["4w", "3m"]
SAMPLE_TICKERS = ["AAPL", "MSFT", "TSLA"]

pytestmark = pytest.mark.skipif(
    not CACHE_DIR.is_dir(),
    reason="data/backtest_cache/ not present -- no OHLCV cache to run parity against",
)


def _load_cached(ticker):
    path = CACHE_DIR / f"{ticker}.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path, index_col="Date", parse_dates=True)
    return df if len(df) else None


def _precomputed_series(df, strategy, horizon_key):
    """Mirrors the precomputation run_backtest() does before calling
    _trade_plan_at for each bar -- same series shape both old and new sides
    are handed."""
    atr_series = atr(df, 14)
    swing_high_series = swing_low_series = None
    if strategy == "Fibonacci":
        lookback = HORIZONS[horizon_key]["fib_lookback"]
        swing_high_series = df["High"].rolling(lookback).max()
        swing_low_series = df["Low"].rolling(lookback).min()
    volume_ratio_series = None
    if strategy == "Support/Resistance":
        vol_avg20 = df["Volume"].rolling(20).mean()
        volume_ratio_series = df["Volume"] / vol_avg20
    entry_levels = None
    if strategy == "Elliott Wave":
        threshold_pct = HORIZONS[horizon_key]["max_risk_pct"]
        _, _, entry_levels = elliott_wave3_entries(df, threshold_pct)
    return atr_series, swing_high_series, swing_low_series, volume_ratio_series, entry_levels


@pytest.mark.parametrize("horizon_key", HORIZON_KEYS)
@pytest.mark.parametrize("strategy", ALL_STRATEGIES)
@pytest.mark.parametrize("ticker", SAMPLE_TICKERS)
def test_sizing_parity(ticker, strategy, horizon_key):
    df = _load_cached(ticker)
    if df is None:
        pytest.skip(f"{ticker}.csv not present in data/backtest_cache/")

    min_bars = MIN_BARS[horizon_key]
    if len(df) < min_bars + 10:
        pytest.skip(f"{ticker}: not enough bars for {horizon_key}")

    bullish, bearish = backtest._vectorized_entries(df, strategy, horizon_key)
    atr_series, swing_high_series, swing_low_series, volume_ratio_series, entry_levels = (
        _precomputed_series(df, strategy, horizon_key)
    )

    entry_idx = np.where(bullish.values | bearish.values)[0]
    checked = 0
    for i in entry_idx:
        if i < min_bars:
            continue
        direction = "bullish" if bullish.values[i] else "bearish"

        _, old_stop, old_tp = legacy_trade_plan_at(
            df, i, direction, strategy, horizon_key, atr_series,
            swing_high_series, swing_low_series, volume_ratio_series, entry_levels,
        )
        _, new_stop, new_tp = backtest._trade_plan_at(
            df, i, direction, strategy, horizon_key, atr_series,
            swing_high_series, swing_low_series, volume_ratio_series, entry_levels,
        )

        assert old_stop == pytest.approx(new_stop, abs=TOLERANCE), (
            f"{ticker}/{strategy}/{horizon_key} bar {i} ({direction}): "
            f"stop mismatch old={old_stop!r} new={new_stop!r}"
        )
        assert old_tp == pytest.approx(new_tp, abs=TOLERANCE), (
            f"{ticker}/{strategy}/{horizon_key} bar {i} ({direction}): "
            f"tp1 mismatch old={old_tp!r} new={new_tp!r}"
        )
        checked += 1

    if checked == 0:
        pytest.skip(f"no entry signals for {ticker}/{strategy}/{horizon_key}")

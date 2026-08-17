"""Task 13: full-corpus sizing-parity harness (pytest side).

Compares `backtest._trade_plan_at` (CURRENT -- it already delegates to
`plan_engine`, see swingbot/core/backtesting/backtest.py) against
`tests.fixtures.legacy_trade_plan_at.legacy_trade_plan_at`, a FROZEN copy of
`_trade_plan_at` as it stood pre-extraction (commit ac91654, before Task 14
rewired it to call plan_engine). That frozen copy is the only remaining
independent "old" implementation -- tests/test_plan_engine_sizing.py already
compares plan_engine against the *current* (post-delegation)
`backtest._trade_plan_at`, which is plan_engine calling itself through one
layer of indirection and can no longer prove extraction correctness on its
own.

STOP ONLY as of plan v31 (docs/superpowers/plans/implemented/2026-08-16-v31-structural-targets.md,
Task 15): the frozen reference's target arithmetic is now permanently stale
-- plan_engine prices every target off a real structural level instead of a
fixed per-strategy reward:risk ratio, and the frozen module (deliberately;
see its own docstring) was never taught the new selector. Comparing tp1
would just assert a known, designed-in divergence forever. Stop derivation
is genuinely unchanged by v31 and remains a real, meaningful check. A bar
where the new selector finds no qualifying target (`_trade_plan_at` returns
None) is skipped, not compared -- the frozen side has no such concept.

Runs on 3 fixed cached tickers x all 11 strategies x horizons {"4w", "3m"}
for speed; `scripts/reports/parity_sizing.py` runs the same comparison over every
cached ticker, every strategy, every horizon, every TRAIN-window entry bar.

Skipped (not failed) when data/backtest_cache/ is absent, so CI without the
(git-ignored) OHLCV cache stays green.
"""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from swingbot.core.backtesting import backtest
from swingbot.core.backtesting.backtest import ALL_STRATEGIES
from swingbot.core.market.indicators import atr, elliott_wave3_entries
from swingbot.core.market.strategy_types import HORIZONS, MIN_BARS

from tests.fixtures.legacy_trade_plan_at import legacy_trade_plan_at

ROOT = Path(__file__).resolve().parent.parent.parent
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


@pytest.fixture(autouse=True)
def _lifecycle_off(monkeypatch):
    """Pin the level-lifecycle flag OFF for this module.

    This harness compares the CURRENT `_trade_plan_at` against
    `legacy_trade_plan_at`, a frozen pre-extraction copy. The level lifecycle
    (P1) is a deliberate behaviour change made long after that freeze -- the
    frozen copy cannot have it and must never be taught it, or it stops being
    an independent witness to the extraction.

    So with LEVEL_LIFECYCLE_STOPS_ENABLED default-on (2026-08-08) the two sides
    diverge by design, on exactly the entry bars where a tested level moves the
    stop. Pinning the flag keeps this harness answering its own question --
    "did the Task-14 extraction change sizing?" -- rather than re-detecting a
    feature that is already measured in
    docs/superpowers/results/2026-08-08-level-lifecycle-*.md. (Its
    stops-only sibling, the "pull TP1 back inside a blocking level" flag,
    was measured inert and removed by v31 Task 14 -- there is only the one
    flag to pin now.)

    scripts/reports/parity_sizing.py (the full-corpus version of this comparison)
    forces the same flag off in main(), for the same reason.
    """
    monkeypatch.setattr("swingbot.config.LEVEL_LIFECYCLE_STOPS_ENABLED", False,
                        raising=False)


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
    none_count = 0
    for i in entry_idx:
        if i < min_bars:
            continue
        direction = "bullish" if bullish.values[i] else "bearish"

        _, old_stop, old_tp = legacy_trade_plan_at(
            df, i, direction, strategy, horizon_key, atr_series,
            swing_high_series, swing_low_series, volume_ratio_series, entry_levels,
        )
        new_plan = backtest._trade_plan_at(
            df, i, direction, strategy, horizon_key, atr_series,
            swing_high_series, swing_low_series, volume_ratio_series, entry_levels,
        )
        if new_plan is None:
            # v31: a real "no qualifying target" answer -- no level clears
            # MIN_RISK_REWARD_RATIO against this bar's risk. Not a parity
            # failure (the frozen legacy side has no such concept and always
            # returns a tuple); just not comparable at this bar.
            none_count += 1
            continue
        _, new_stop, new_tp = new_plan

        assert old_stop == pytest.approx(new_stop, abs=TOLERANCE), (
            f"{ticker}/{strategy}/{horizon_key} bar {i} ({direction}): "
            f"stop mismatch old={old_stop!r} new={new_stop!r}"
        )
        # tp1 is NOT compared. It diverges from the frozen reference BY
        # DESIGN as of plan v31 (docs/superpowers/plans/implemented/2026-08-16-v31-structural-targets.md):
        # plan_engine now prices every target off a real structural level
        # (plan_engine.select_structural_target) instead of the frozen
        # module's fixed per-strategy reward:risk arithmetic. A tp1
        # mismatch here is expected, not a regression -- do not add this
        # assertion back.
        checked += 1

    if checked == 0:
        pytest.skip(f"no entry signals for {ticker}/{strategy}/{horizon_key} "
                    f"({none_count} bar(s) had no qualifying v31 target)")

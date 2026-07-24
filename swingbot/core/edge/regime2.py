"""Four-state market regime: (bull|bear) x (quiet|volatile).

Trend: SPY close vs its 200-EMA. Vol: 20-day realized volatility vs the
60th percentile of its own trailing year. All thresholds are module
constants -- transparent enough for the fold harness to audit, dumb
enough not to overfit. Regime v1 (scanning/regime.py) stays untouched;
consumers migrate deliberately."""
from __future__ import annotations

import numpy as np
import pandas as pd

REGIMES = ("bull_quiet", "bull_volatile", "bear_quiet", "bear_volatile")
TREND_EMA = 200
VOL_WINDOW = 20
VOL_HISTORY = 252
VOL_PCTILE_SPLIT = 0.60
EMA_TIE_BAND_PCT = 1.0     # within +-1% of the EMA the trend call is a coin flip
BREADTH_TIEBREAK = 50.0    # ...so breadth (E28), when available, decides
# rv and vol_threshold are computed via different pandas paths (rolling().std()
# vs rolling().quantile()) that can disagree at the machine-epsilon level on
# a perfectly deterministic series (e.g. a synthetic test fixture) even when
# they are mathematically equal -- without this floor, classify() and
# regime_series() (which MUST agree, see regime_series' docstring) can
# diverge on such inputs. 1e-12 carries orders of magnitude more headroom
# than the ~1e-17/1e-18 noise actually observed, while still being far
# below any realistic realized-volatility value (~1e-3 to 1e-1) so it can
# never affect a real classification.
_VOL_THRESHOLD_EPSILON = 1e-12


def _trend_and_vol(spy_df: pd.DataFrame):
    close = spy_df["Close"]
    ema = close.ewm(span=TREND_EMA, adjust=False).mean()
    rv = close.pct_change().rolling(VOL_WINDOW).std()
    vol_threshold = rv.rolling(VOL_HISTORY, min_periods=VOL_WINDOW * 3).quantile(VOL_PCTILE_SPLIT)
    return close, ema, rv, vol_threshold


def classify(spy_df: pd.DataFrame, breadth: float | None = None) -> str:
    close, ema, rv, thr = _trend_and_vol(spy_df)
    c, e = float(close.iloc[-1]), float(ema.iloc[-1])
    if breadth is not None and abs(c - e) / e * 100 <= EMA_TIE_BAND_PCT:
        bull = breadth >= BREADTH_TIEBREAK
    else:
        bull = c >= e
    t = thr.iloc[-1]
    volatile = bool(not np.isnan(t) and rv.iloc[-1] >= t + _VOL_THRESHOLD_EPSILON)
    return f"{'bull' if bull else 'bear'}_{'volatile' if volatile else 'quiet'}"


def regime_series(spy_df: pd.DataFrame) -> pd.Series:
    """Vectorized per-bar labels for backtests (no breadth history -> pure
    price rule; identical to classify(breadth=None) at every bar)."""
    close, ema, rv, thr = _trend_and_vol(spy_df)
    bull = close >= ema
    volatile = (rv >= thr + _VOL_THRESHOLD_EPSILON).fillna(False)
    labels = np.where(bull, "bull", "bear") + np.where(volatile, "_volatile", "_quiet")
    return pd.Series(labels, index=spy_df.index)

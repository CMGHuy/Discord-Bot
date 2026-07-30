"""Deterministic OHLCV scenario builders for gate detector tests.

All return daily frames in the repo convention (Open,High,Low,Close,Volume,
DatetimeIndex) built on tests.conftest.make_ohlcv — signature verified
2026-07-29 as make_ohlcv(closes, spread_pct=1.0, volumes=None,
start="2019-01-01"). make_ohlcv sets Open = prior close and symmetric H/L
around the close; builders that need asymmetric bars (wicks, gaps) patch
individual cells afterwards.
"""
import numpy as np
import pandas as pd

from tests.conftest import make_ohlcv

BASE_VOL = 1_000_000.0


def uptrend_daily(n=260, start_price=100.0, daily_pct=0.4):
    closes = start_price * (1 + daily_pct / 100) ** np.arange(n)
    return make_ohlcv(closes, spread_pct=2.0)


def downtrend_daily(n=260, start_price=100.0, daily_pct=0.4):
    closes = start_price * (1 - daily_pct / 100) ** np.arange(n)
    return make_ohlcv(closes, spread_pct=2.0)


def range_daily(lo=90.0, hi=110.0, n=120):
    mid, amp = (lo + hi) / 2.0, (hi - lo) / 2.0
    closes = mid + amp * np.sin(np.arange(n) * 2 * np.pi / 20)
    return make_ohlcv(closes, spread_pct=1.5)


def breakout_and_fail(level=100.0, n=80):
    """Grind up to the level, close above it on DEAD volume, close back
    inside the next bar — the rf_fake_breakout golden scenario."""
    closes = np.concatenate([
        np.linspace(level * 0.90, level * 0.99, n - 2),
        [level * 1.02],      # breakout close above the level...
        [level * 0.985],     # ...next bar closes back inside
    ])
    volumes = np.full(n, BASE_VOL)
    volumes[-2] = BASE_VOL * 0.6
    return make_ohlcv(closes, spread_pct=1.5, volumes=volumes)


def sweep_wick(level=100.0, n=60):
    """Long lower wick through the level with a close back above, then a
    no-follow-through bar — the rf_stop_sweep golden scenario."""
    closes = np.linspace(level * 1.08, level * 1.01, n)
    df = make_ohlcv(closes, spread_pct=1.0)
    sweep = df.index[-2]
    df.loc[sweep, "Open"] = level * 1.010
    df.loc[sweep, "Close"] = level * 1.005          # body 0.5
    df.loc[sweep, "Low"] = level * 0.970            # wick 3.5 -> ratio 7x
    last = df.index[-1]
    df.loc[last, "Close"] = level * 1.004           # no follow-through
    df.loc[last, "High"] = level * 1.012
    return df


def dead_cat(n_down=40, bounce_pct=8.0, start_price=150.0):
    """Flat lead-in (history for 250-bar lookbacks), -1%/day grind, then a
    V-bounce with no higher-low structure — the rf_dead_cat golden scenario."""
    lead_in = np.full(220, start_price)
    down = start_price * (1 - 0.01) ** np.arange(n_down)
    low = down[-1]
    bounce = np.linspace(low, low * (1 + bounce_pct / 100), 6)
    closes = np.concatenate([lead_in, down, bounce[1:]])
    return make_ohlcv(closes, spread_pct=2.0)


def climax_overbought(n=120, level=120.0):
    """30-bar blow-off into resistance; RSI(14) finishes > 75."""
    closes = np.concatenate([np.linspace(90, 100, n - 30),
                             np.linspace(100, level, 30)])
    return make_ohlcv(closes, spread_pct=1.5)


def gap_spike(pct=12.0, n=80):
    """Flat series, last bar +pct% close-to-close on 5x volume — the
    news-gap geometry the rf_news_whipsaw golden scenario builds on."""
    closes = np.full(n, 100.0)
    closes[-1] = 100.0 * (1 + pct / 100)
    volumes = np.full(n, BASE_VOL)
    volumes[-1] = BASE_VOL * 5
    return make_ohlcv(closes, spread_pct=1.0, volumes=volumes)


def to_weekly(df: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({
        "Open": df["Open"].resample("W-FRI").first(),
        "High": df["High"].resample("W-FRI").max(),
        "Low": df["Low"].resample("W-FRI").min(),
        "Close": df["Close"].resample("W-FRI").last(),
        "Volume": df["Volume"].resample("W-FRI").sum(),
    }).dropna()

import numpy as np
import pandas as pd

from swingbot.core.market.entry_filters import support_resistance_entries
from tests.conftest import make_ohlcv, make_trend_df

GATED = {"base_atr": 4.0, "close_frac": 0.4, "gap_pct": 3.0,
         "min_level_touches": 2}


# `make_ohlcv`/`make_trend_df` always place Close exactly at the midpoint of
# High-Low, so `strong_close_bull` (close must be in the top 40% of the bar)
# can never fire and every Support/Resistance bullish entry is permanently
# empty on those fixtures -- the vacuous-assertion trap this plan has hit on
# R14/R16/R20. The two fixtures below hand-build OHLCV instead, so a real
# entry actually occurs and the gate has something to filter.

def _tested_breakout_df(n_warmup=260, n_base=15, base_price=100.0, drift_pct=0.15,
                         base_low=118.0, base_high=120.0, breakout_margin=1.5,
                         spread_pct=2.0, start="2019-01-01"):
    """A slow uptrend into a 15-bar consolidation right under `base_high`
    (the level gets tested repeatedly via the gradual grind up to it), then a
    clean breakout above it with a strong close and volume confirmation.
    Level is well-tested -> the gate should let this through."""
    n = n_warmup + n_base + 1
    idx = pd.bdate_range(start, periods=n)
    closes = base_price * (1 + drift_pct / 100) ** np.arange(n_warmup)
    closes = closes * (base_low * 0.98 / closes[-1])
    half = closes * (spread_pct / 100) / 2
    opens = np.concatenate([[closes[0]], closes[:-1]])
    highs = closes + half
    lows = closes - half
    vols = np.full(n_warmup, 1_000_000.0)

    base_closes = np.linspace(closes[-1], base_high * 0.995, n_base)
    base_highs = np.full(n_base, base_high)
    base_lows = base_closes - (base_high - base_closes) * 0.3 - 0.3
    base_opens = np.concatenate([[closes[-1]], base_closes[:-1]])
    base_vols = np.full(n_base, 1_000_000.0)

    bo_open = base_closes[-1]
    bo_high = base_high + breakout_margin
    bo_low = base_closes[-1] - 0.5
    bo_close = bo_high - 0.05 * (bo_high - bo_low)
    bo_vol = 5_000_000.0

    Open = np.concatenate([opens, base_opens, [bo_open]])
    High = np.concatenate([highs, base_highs, [bo_high]])
    Low = np.concatenate([lows, base_lows, [bo_low]])
    Close = np.concatenate([closes, base_closes, [bo_close]])
    Volume = np.concatenate([vols, base_vols, [bo_vol]])
    return pd.DataFrame({"Open": Open, "High": High, "Low": Low,
                          "Close": Close, "Volume": Volume}, index=idx)


def _untested_peak_breakout_df(n_warmup=259, base_price=70.0, drift_pct=0.15,
                                peak_delta=6.0, crash_frac=0.10, n_flat=58,
                                breakout_delta=2.0, spread_pct=2.0,
                                start="2019-01-01"):
    """A slow uptrend, then a single decisive bar pokes to a new high
    (`peak`) and closes near it -- a breakout of its own trailing range, not
    a rejection. Immediately after, price gaps far below the peak and stays
    flat there (well outside 0.5*ATR of the peak, so none of those bars
    register as a "touch" of it) for the rest of the 60-bar S/R lookback.
    The final bar then breaks back above the peak. That peak was approached
    and rejected zero times before this breakout -- an untested ceiling --
    so the gate should reject it while the ungated run still fires."""
    idx_n = n_warmup + 1 + 1 + n_flat + 1
    idx = pd.bdate_range(start, periods=idx_n)
    closes = base_price * (1 + drift_pct / 100) ** np.arange(n_warmup)
    half = closes * (spread_pct / 100) / 2
    opens = np.concatenate([[closes[0]], closes[:-1]])
    highs = closes + half
    lows = closes - half
    vols = np.full(n_warmup, 1_000_000.0)

    # peak bar: a decisive new high, closing near its own top (a crossing,
    # not a rejection, of its own prior trailing max)
    peak_open = closes[-1]
    peak_high = closes[-1] + peak_delta
    peak_low = closes[-1] - 0.3
    peak_close = peak_high - 0.1 * (peak_high - peak_low)
    peak_vol = 1_000_000.0

    # crash bar: gaps down hard immediately, never lingering near the peak
    crash_open = peak_close * (1 - crash_frac)
    crash_high = crash_open + 0.2
    crash_low = crash_open - 3.0
    crash_close = crash_open - 2.0
    crash_vol = 1_000_000.0

    # flat consolidation far below the peak -- never approaches it
    flat_level = crash_close
    flat_closes = np.full(n_flat, flat_level)
    flat_half = flat_closes * (spread_pct / 100) / 2
    flat_highs = flat_closes + flat_half
    flat_lows = flat_closes - flat_half
    flat_opens = np.concatenate([[crash_close], flat_closes[:-1]])
    flat_vols = np.full(n_flat, 1_000_000.0)

    # breakout bar: clears the untested peak with a strong close and volume
    bo_open = flat_closes[-1]
    bo_high = peak_high + breakout_delta
    bo_low = flat_closes[-1] - 0.5
    bo_close = bo_high - 0.05 * (bo_high - bo_low)
    bo_vol = 5_000_000.0

    Open = np.concatenate([opens, [peak_open], [crash_open], flat_opens, [bo_open]])
    High = np.concatenate([highs, [peak_high], [crash_high], flat_highs, [bo_high]])
    Low = np.concatenate([lows, [peak_low], [crash_low], flat_lows, [bo_low]])
    Close = np.concatenate([closes, [peak_close], [crash_close], flat_closes, [bo_close]])
    Volume = np.concatenate([vols, [peak_vol], [crash_vol], flat_vols, [bo_vol]])
    return pd.DataFrame({"Open": Open, "High": High, "Low": Low,
                          "Close": Close, "Volume": Volume}, index=idx)


def test_gate_off_is_byte_identical():
    df = make_trend_df(300, +0.2)
    a, _ = support_resistance_entries(df, "2m")
    b, _ = support_resistance_entries(
        df, "2m", params={"base_atr": 4.0, "close_frac": 0.4,
                          "gap_pct": 3.0, "min_level_touches": 0})
    assert (a == b).all()


def test_filter_never_adds_entries():
    """A well-tested level (the slow grind up to `base_high` counts as
    repeated touches) should clear the gate -- entries only ever shrink,
    never grow, when the gate is switched on."""
    df = _tested_breakout_df()
    off, _ = support_resistance_entries(df, "2m")
    on, _ = support_resistance_entries(df, "2m", params=GATED)
    assert off.sum() > 0
    assert on.sum() <= off.sum()
    assert (on & ~off).sum() == 0


def test_untested_single_spike_high_is_rejected():
    """A lone spike high that was never revisited is not a tested ceiling:
    with the gate on, a breakout over it must not fire."""
    df = _untested_peak_breakout_df()
    off, _ = support_resistance_entries(df, "2m")
    on, _ = support_resistance_entries(df, "2m", params=GATED)
    assert off.sum() > 0
    assert on.sum() <= off.sum()
    assert on.sum() < off.sum()  # the untested peak must actually get excluded


def test_no_lookahead():
    df = make_trend_df(300, +0.3)
    full, _ = support_resistance_entries(df, "2m", params=GATED)
    trunc, _ = support_resistance_entries(df.iloc[:-1], "2m", params=GATED)
    assert (full.iloc[:-1] == trunc).all()

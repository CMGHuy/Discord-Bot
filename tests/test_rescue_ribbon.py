import numpy as np
import pandas as pd
from swingbot.core.entry_filters import ma_ribbon_entries
from tests.conftest import make_ohlcv, make_trend_df

GATED = {"ext_pct": 8.0, "min_width_pctile": 0.4, "require_expanding": True}


def _taper_frame(n=400, drift=0.08, burn=80, period=15, amp=5.0,
                  taper_start=360, taper_amp=2.0):
    """Steady oscillating uptrend (so the un-gated strategy fires several
    ribbon crossovers) whose ribbon compresses over the final stretch
    (amplitude tapered down) so the entries that land in that tail have a
    low trailing-126-bar width percentile -- exactly the case the expansion
    gate exists to suppress."""
    t = np.arange(n)
    base = 100 * (1 + drift / 100) ** t
    osc = np.zeros(n)
    for i in range(burn, n):
        a = amp
        if i >= taper_start:
            frac = min(1.0, (i - taper_start) / (n - taper_start))
            a = amp + (taper_amp - amp) * frac
        osc[i] = a * np.sin(2 * np.pi * (i - burn) / period)
    closes = base + osc
    return make_ohlcv(closes)


def test_chop_frame_suppressed_when_gated():
    # oscillating uptrend whose ribbon compresses (tapers) into the final
    # bars -> width percentile there drops low -> gate suppresses those fires
    df = _taper_frame()
    bull_on, bear_on = ma_ribbon_entries(df, "4w", params=GATED)
    bull_off, bear_off = ma_ribbon_entries(df, "4w")
    assert bull_off.iloc[-30:].any()         # sanity: ungated DOES fire late
    assert bull_on.sum() <= bull_off.sum()
    assert not bull_on.iloc[-30:].any()      # late compressed bars all gated out


def test_expanding_trend_passes():
    df = make_trend_df(400, +0.4)            # strong steady uptrend
    bull_on, _ = ma_ribbon_entries(df, "4w", params=GATED)
    bull_off, _ = ma_ribbon_entries(df, "4w")
    fired_off = bull_off[bull_off].index
    # every ungated entry late enough to have percentile history survives
    late = [d for d in fired_off if bull_off.index.get_loc(d) > 200]
    assert all(bull_on.loc[d] for d in late)


def test_gate_off_is_byte_identical():
    df = make_trend_df(300, +0.2)
    a, _ = ma_ribbon_entries(df, "4w")
    b, _ = ma_ribbon_entries(df, "4w",
        params={"ext_pct": 8.0, "min_width_pctile": None,
                "require_expanding": False})
    assert (a == b).all()


def test_no_lookahead():
    df = make_trend_df(300, +0.3)
    full, _ = ma_ribbon_entries(df, "4w", params=GATED)
    trunc, _ = ma_ribbon_entries(df.iloc[:-1], "4w", params=GATED)
    assert (full.iloc[:-1] == trunc).all()

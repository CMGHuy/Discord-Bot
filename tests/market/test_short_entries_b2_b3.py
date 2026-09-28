"""v104 §3.2 B2 Vol Expansion Breakdown and §3.3 B3 Earnings Gap Drift."""
import numpy as np
import pytest

from swingbot.core.market import entry_filters as ef
from swingbot.core.market import short_entries as se
from swingbot.core.market.indicators import atr
from tests.helpers import make_ohlcv

HZ = "2w"                                          # sr_lookback 10


def _breakdown():
    """80 flat bars, a 20-bar grind lower, a wide high-volume breakdown bar, then
    3 trailing flat bars. The brief's fixture ended at the crash bar (index 100,
    len(df)=101), which made the truncation case cut=100 compare iloc[:101] --
    the whole frame -- against itself: vacuous per the truncation-invariance
    rule (cut must be strictly < len(df)-1). Grown by 3 flat bars at the crash
    price/volume so len(df)-1 == 103 and cut=100 is a real truncation."""
    pad = [(100.0, 101.0, 99.0, 100.0)] * 80
    grind = []
    close = 100.0
    for _ in range(20):
        close -= 0.5
        grind.append((close + 0.3, close + 1.0, close - 1.0, close))
    crash = [(89.0, 89.5, 84.0, 84.5)]
    tail = [(84.5, 85.0, 84.0, 84.5)] * 3
    df = make_ohlcv(pad + grind + crash + tail, start="2015-01-02")
    t = len(pad) + len(grind)                     # crash bar, no longer the last row
    df.loc[df.index[t], "Volume"] = 3_000_000.0
    df["ctx_spy_down"] = 1.0
    df["ctx_spy_ret63"] = 0.0
    return df, t


def test_breakdown_fires_on_the_crash_bar_only():
    df, t = _breakdown()
    frame = se.vol_breakdown_frame(df, HZ)
    assert list(np.flatnonzero(frame["signal"].to_numpy())) == [t]
    support = df["Low"].rolling(10).min().shift(1).iloc[t]
    assert frame["stop"].iloc[t] == pytest.approx(support + se.STOP_ATR * float(atr(df, 14).iloc[t]))


def test_breakdown_needs_expanding_volatility_per_m():
    df, t = _breakdown()
    ratio = float(atr(df, 14).iloc[t] / atr(df, 14).rolling(60).mean().iloc[t])
    assert 1.0 <= ratio < 1.4, "fixture must sit between the loosest and tightest m"
    assert bool(se.vol_breakdown_frame(df, HZ, params={"m": 1.0})["signal"].iloc[t])
    assert not se.vol_breakdown_frame(df, HZ, params={"m": 1.4})["signal"].any()


@pytest.mark.parametrize("change", [
    {"ctx_spy_down": 0.0},                         # market not falling
    {"ctx_spy_ret63": -0.50},                      # stock not weaker than SPY
])
def test_breakdown_needs_a_falling_market_and_relative_weakness(change):
    df, _ = _breakdown()
    for col, value in change.items():
        df[col] = value
    assert not se.vol_breakdown_frame(df, HZ)["signal"].any()


def test_breakdown_without_market_context_is_silent():
    df, _ = _breakdown()
    df = df.drop(columns=["ctx_spy_down", "ctx_spy_ret63"])
    assert not se.vol_breakdown_frame(df, HZ)["signal"].any()


def _gap(open_=93.0, next_close=91.0):
    pad = [(100.0, 101.0, 99.0, 100.0)] * 80
    gap_day = (open_, 94.0, 91.5, 92.0)
    after = [(92.0, 92.5, 90.5, next_close), (91.0, 91.5, 90.0, 90.5)]
    df = make_ohlcv(pad + [gap_day] + after, start="2015-01-02")
    df["evt_reaction"] = 0.0
    df.loc[df.index[80], "evt_reaction"] = 1.0
    df["evt_bars_to_next"] = np.nan
    return df, 81


def test_gap_drift_enters_the_day_after_a_held_gap():
    df, t = _gap()
    frame = se.gap_drift_frame(df, HZ)
    assert list(np.flatnonzero(frame["signal"].to_numpy())) == [t]
    assert frame["stop"].iloc[t] == pytest.approx(94.0 + se.STOP_ATR * float(atr(df, 14).iloc[t]))


def test_gap_drift_grid_and_recovery():
    df, _ = _gap(open_=93.0)
    assert not se.gap_drift_frame(df, HZ, params={"g": 0.08})["signal"].any()    # 7% gap < 8%
    df, _ = _gap(next_close=92.5)                                                # recovered
    assert not se.gap_drift_frame(df, HZ)["signal"].any()


def test_gap_drift_needs_earnings_context_and_a_reaction_day():
    df, _ = _gap()
    assert not se.gap_drift_frame(df.drop(columns=["evt_reaction"]), HZ)["signal"].any()
    df["evt_reaction"] = 0.0
    assert not se.gap_drift_frame(df, HZ)["signal"].any()


@pytest.mark.parametrize("builder,cut", [(_breakdown, 95), (_breakdown, 100), (_gap, 80), (_gap, 81)])
def test_b2_b3_are_truncation_invariant(builder, cut):
    df, _ = builder()
    frame_fn = se.vol_breakdown_frame if builder is _breakdown else se.gap_drift_frame
    full = frame_fn(df, HZ).iloc[cut]
    part = frame_fn(df.iloc[:cut + 1], HZ).iloc[cut]
    assert bool(full["signal"]) == bool(part["signal"])
    assert full["stop"] == pytest.approx(part["stop"], nan_ok=True)


def test_registration():
    assert ef.DEFAULT_PARAMS["Vol Expansion Breakdown"] == {"m": 1.0, "earnings": "hold"}
    assert ef.DEFAULT_PARAMS["Earnings Gap Drift"] == {"g": 0.05}
    for name in ("Vol Expansion Breakdown", "Earnings Gap Drift"):
        assert name in ef.ENTRY_FUNCS and name in se.FRAMES

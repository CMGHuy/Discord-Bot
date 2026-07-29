from swingbot.core.indicators import rsi
from tests.fixtures.gate import (
    breakout_and_fail, climax_overbought, dead_cat, downtrend_daily,
    gap_spike, range_daily, sweep_wick, to_weekly, uptrend_daily,
)


def test_trend_slopes():
    up, down = uptrend_daily(), downtrend_daily()
    assert up["Close"].iloc[-1] > up["Close"].iloc[0] * 1.5
    assert down["Close"].iloc[-1] < down["Close"].iloc[0] * 0.6
    rng = range_daily(90, 110)
    assert rng["Close"].min() > 85 and rng["Close"].max() < 115


def test_breakout_and_fail_geometry():
    df = breakout_and_fail(level=100.0)
    assert df["Close"].iloc[-2] > 100.0                 # broke out...
    assert df["Close"].iloc[-1] < 100.0                 # ...failed back inside next bar
    assert df["Volume"].iloc[-2] < df["Volume"].iloc[:-2].mean()   # on dead volume


def test_sweep_wick_geometry():
    df = sweep_wick(level=100.0)
    bar = df.iloc[-2]
    body = abs(bar["Close"] - bar["Open"])
    lower_wick = min(bar["Close"], bar["Open"]) - bar["Low"]
    assert bar["Low"] < 100.0 < bar["Close"]            # swept through, closed back above
    assert lower_wick >= 1.5 * body


def test_dead_cat_geometry():
    df = dead_cat(bounce_pct=8.0)
    recent_low = df["Close"].iloc[-25:].min()
    assert df["Close"].iloc[-1] >= recent_low * 1.05    # >=5% bounce off a recent low
    assert df["Close"].iloc[-1] < df["Close"].iloc[0]   # still deep below the old range


def test_climax_overbought_rsi():
    assert rsi(climax_overbought()["Close"]).iloc[-1] > 75


def test_gap_spike_geometry():
    df = gap_spike(pct=12.0)
    assert df["Close"].iloc[-1] / df["Close"].iloc[-2] >= 1.10
    assert df["Volume"].iloc[-1] >= 4 * df["Volume"].iloc[:-1].mean()


def test_to_weekly_shape():
    wk = to_weekly(uptrend_daily(260))
    assert 45 <= len(wk) <= 60
    assert (wk["High"] >= wk["Low"]).all()

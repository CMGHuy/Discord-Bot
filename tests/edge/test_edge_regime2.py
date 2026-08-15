import numpy as np

from tests.conftest import make_ohlcv, make_trend_df
from swingbot.core.edge.regime2 import REGIMES, classify, regime_series


def _vol_walk(daily_pct, vol, n=400, seed=3):
    rng = np.random.default_rng(seed)
    rets = rng.normal(daily_pct / 100, vol / 100, n)
    return make_ohlcv(100 * np.cumprod(1 + rets))


def test_quiet_uptrend_is_bull_quiet():
    assert classify(make_trend_df(400, +0.15)) == "bull_quiet"


def test_quiet_downtrend_is_bear_quiet():
    assert classify(make_trend_df(400, -0.15)) == "bear_quiet"


def test_late_vol_spike_flips_to_volatile():
    df = _vol_walk(+0.08, 0.5)
    spiky = _vol_walk(+0.08, 3.5, n=40, seed=4)

    df.iloc[-40:] = spiky.values
    assert classify(df).endswith("_volatile")


def test_breadth_breaks_ties_near_the_ema():
    flat = make_ohlcv(np.full(400, 100.0), spread_pct=0.2)  # price == EMA
    assert classify(flat, breadth=70.0).startswith("bull")
    assert classify(flat, breadth=30.0).startswith("bear")


def test_regime_series_aligned_and_labeled():
    df = make_trend_df(400, +0.15)
    s = regime_series(df)
    assert s.index.equals(df.index)
    assert set(s.dropna().unique()) <= set(REGIMES)
    assert s.iloc[-1] == "bull_quiet"


def test_classify_and_regime_series_agree_on_last_bar():
    # regime_series' own docstring requires it to be "identical to
    # classify(breadth=None) at every bar" -- the downtrend fixture is a
    # real regression case: rv/vol_threshold take different pandas
    # computation paths (rolling().std() vs rolling().quantile()) that can
    # disagree at machine-epsilon precision on a perfectly deterministic
    # series, which previously made classify() and regime_series() disagree
    # right at the vol threshold (see _VOL_THRESHOLD_EPSILON's docstring).
    for df in (make_trend_df(400, +0.15), make_trend_df(400, -0.15)):
        assert classify(df) == regime_series(df).iloc[-1]


def test_regime_gate_masks_disallowed_bars(monkeypatch):
    import pandas as pd
    from swingbot.core.market import entry_filters
    from swingbot.core.market import strategy_types
    from swingbot import config

    idx = pd.bdate_range("2024-01-01", periods=6)
    bull = pd.Series([True] * 6, index=idx)
    bear = pd.Series([False] * 6, index=idx)
    regimes = pd.Series(["bull_quiet"] * 3 + ["bear_volatile"] * 3, index=idx)

    monkeypatch.setattr(config, "REGIME_GATES_ENABLED", True, raising=False)
    monkeypatch.setitem(strategy_types.REGIME_ALLOW, "RSI", ("bull_quiet",))

    b2, s2 = entry_filters.apply_regime_gate(bull, bear, "RSI", regimes)
    assert b2.tolist() == [True, True, True, False, False, False]


def test_regime_gate_noop_when_unconfigured(monkeypatch):
    import pandas as pd
    from swingbot.core.market import entry_filters
    from swingbot import config
    monkeypatch.setattr(config, "REGIME_GATES_ENABLED", True, raising=False)
    idx = pd.bdate_range("2024-01-01", periods=3)
    bull = pd.Series([True, True, True], index=idx)
    bear = pd.Series(False, index=idx)
    regimes = pd.Series(["bear_volatile"] * 3, index=idx)
    b2, _ = entry_filters.apply_regime_gate(bull, bear, "MACD", regimes)  # no REGIME_ALLOW entry
    assert b2.tolist() == [True, True, True]

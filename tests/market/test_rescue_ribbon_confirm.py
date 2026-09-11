import numpy as np

from swingbot.core.market.entry_filters import ma_ribbon_entries
from tests.conftest import make_ohlcv, make_trend_df

GATED = {"confirm_bars": 3}


def _oscillating_uptrend_df(n=400, drift=0.08, burn=80, period=15, amp=5.0):
    """Steady uptrend with a sine oscillation layered on top after a burn-in
    stretch, so fast/mid EMAs actually cross the slow SMA repeatedly (a pure
    make_trend_df monotonic series never reverses, so diff = fast-mid never
    goes negative after warmup and crossed_up/crossed_down never fire --
    the same vacuous-fixture trap R14/R16 hit; see task-R20-report.md)."""
    t = np.arange(n)
    base = 100 * (1 + drift / 100) ** t
    osc = np.zeros(n)
    for i in range(burn, n):
        osc[i] = amp * np.sin(2 * np.pi * (i - burn) / period)
    closes = base + osc
    return make_ohlcv(closes)


def test_gate_off_is_byte_identical():
    df = make_trend_df(300, +0.2)
    a, _ = ma_ribbon_entries(df, "4w")
    b, _ = ma_ribbon_entries(df, "4w", params={"confirm_bars": 1})
    assert (a == b).all()


def test_confirmation_never_adds_entries():
    df = make_trend_df(400, +0.4)
    on, _ = ma_ribbon_entries(df, "4w", params=GATED)
    off, _ = ma_ribbon_entries(df, "4w")
    assert on.sum() <= off.sum()
    assert (on & ~off).sum() == 0


def test_every_gated_entry_had_k_bars_of_alignment():
    """The mechanism's actual claim: an entry only fires where fast/mid sat
    above slow for K consecutive bars ending at the crossover."""
    from swingbot.core.market.indicators import ema
    df = _oscillating_uptrend_df()
    on, _ = ma_ribbon_entries(df, "4w", params=GATED)
    close = df["Close"]
    fast, mid = ema(close, 10), ema(close, 20)
    slow = close.rolling(50).mean()
    above = (fast > slow) & (mid > slow)
    assert on.sum() > 0, (
        "fixture produced zero gated entries -- loop below would pass vacuously"
    )
    for d in on[on].index:
        i = on.index.get_loc(d)
        assert above.iloc[i - 2:i + 1].all()


def test_closed_width_params_still_default_off():
    from swingbot.core.market.entry_filters import DEFAULT_PARAMS
    p = DEFAULT_PARAMS["MA Ribbon"]
    assert p["min_width_pctile"] is None
    assert p["require_expanding"] is False


def test_no_lookahead():
    df = make_trend_df(300, +0.3)
    full, _ = ma_ribbon_entries(df, "4w", params=GATED)
    trunc, _ = ma_ribbon_entries(df.iloc[:-1], "4w", params=GATED)
    assert (full.iloc[:-1] == trunc).all()

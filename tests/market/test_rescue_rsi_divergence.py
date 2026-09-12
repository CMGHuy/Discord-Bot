import numpy as np

from swingbot.core.market.entry_filters import rsi_divergence_entries
from tests.conftest import make_ohlcv, make_trend_df

GATED = {"min_consecutive_rsi_turn": 3}


def _one_bar_turn_frame():
    """250-bar steady uptrend (long enough for the 200-bar `bull_regime`
    lookback to mature) followed by a real hidden-bullish-divergence setup:
    a 40-bar pullback where price stays above its prior 20-40-bar-ago low
    (`price_hl`) while RSI grinds down to a genuine 20-bar-vs-prior-20-bar
    low (`rsi_ll`). One bar in the middle of that decline gets a single
    sharp uptick just large enough to push RSI back through the 45 reclaim
    threshold for exactly one bar before the decline resumes -- the noisy
    one-uptick reclaim the persistence gate exists to reject.

    NOTE: the plan's original saw-tooth-on-uptrend fixture was vacuous --
    every combination of amplitude/period tried left `off_bull.sum() == 0`
    (no entry ever fired at all, gate or no gate), because a symmetric
    saw-tooth stabilizes RSI near 50 instead of producing a real 20-bar
    lower low, and/or fired before `bull_regime`'s 200+ bar lookback had
    matured. Replaced with this hand-tuned single-event fixture, verified
    against the *current* (pre-gate) code to produce exactly one bullish
    entry, at the single-bar-turn bar, before writing the assertions below.
    """
    phase_a_len, phase_a_pct = 250, 0.15
    decline_pct, decline_len = -0.15, 40
    bump_day, bump_amt = 13, 0.003

    a = 100 * (1 + phase_a_pct / 100) ** np.arange(phase_a_len)
    b = a[-1] * (1 + decline_pct / 100) ** (np.arange(decline_len) + 1)
    closes = np.concatenate([a, b]).copy()
    idx = phase_a_len + bump_day
    closes[idx] = closes[idx - 1] * (1 + bump_amt)
    return make_ohlcv(closes)


def test_gate_off_is_byte_identical():
    df = make_trend_df(300, +0.2)
    a_bull, a_bear = rsi_divergence_entries(df, "4w")
    b_bull, b_bear = rsi_divergence_entries(
        df, "4w", params={"min_consecutive_rsi_turn": 1})
    assert (a_bull == b_bull).all()
    assert (a_bear == b_bear).all()


def test_persistence_gate_never_adds_entries():
    df = make_trend_df(400, +0.3)
    on_bull, on_bear = rsi_divergence_entries(df, "4w", params=GATED)
    off_bull, off_bear = rsi_divergence_entries(df, "4w")
    assert on_bull.sum() <= off_bull.sum()
    assert on_bear.sum() <= off_bear.sum()
    assert (on_bull & ~off_bull).sum() == 0


def test_single_bar_turns_are_suppressed():
    df = _one_bar_turn_frame()
    on_bull, _ = rsi_divergence_entries(df, "4w", params=GATED)
    off_bull, _ = rsi_divergence_entries(df, "4w")
    assert off_bull.sum() >= on_bull.sum()
    assert on_bull.sum() == 0


def test_no_lookahead():
    df = make_trend_df(300, +0.3)
    full, _ = rsi_divergence_entries(df, "4w", params=GATED)
    trunc, _ = rsi_divergence_entries(df.iloc[:-1], "4w", params=GATED)
    assert (full.iloc[:-1] == trunc).all()


def test_closed_rescue_params_still_default_off():
    from swingbot.core.market.entry_filters import DEFAULT_PARAMS
    p = DEFAULT_PARAMS["RSI Divergence"]
    assert p["min_volume_ratio"] is None
    assert p["min_reclaim_strength"] is None

"""v245 V245-11 (doc U2): the horizon zigzag resumes from a cached prefix walk.

zigzag_pivots(df, t, state=...) must return exactly what the walk from bar 0
returns, for every frame, threshold and prefix length; a state that does not
match the frame is ignored.
"""
import dataclasses

import numpy as np
import pandas as pd
import pytest

from swingbot.core.market import indicators
from swingbot.core.market.indicators import zigzag_pivots, zigzag_prefix_state, zigzag_prefix_states
from swingbot.core.market.strategy_types import HORIZONS


def _old_zigzag(df, threshold_pct):
    """zigzag_pivots before V245-11, verbatim (indicators.py:73)."""
    closes = df["Close"].values
    n = len(closes)
    pivots = []
    if n == 0:
        return pivots
    start_idx = 0
    start_price = closes[0]
    last_extreme_idx = 0
    last_extreme_price = closes[0]
    direction = None
    for i in range(1, n):
        price = closes[i]
        if last_extreme_price == 0:
            continue
        change_pct = (price - last_extreme_price) / last_extreme_price * 100
        if direction is None:
            if change_pct >= threshold_pct:
                pivots.append((start_idx, start_price, "low"))
                direction = "up"
                last_extreme_price, last_extreme_idx = price, i
            elif change_pct <= -threshold_pct:
                pivots.append((start_idx, start_price, "high"))
                direction = "down"
                last_extreme_price, last_extreme_idx = price, i
        elif direction == "up":
            if price >= last_extreme_price:
                last_extreme_price, last_extreme_idx = price, i
            elif (last_extreme_price - price) / last_extreme_price * 100 >= threshold_pct:
                pivots.append((last_extreme_idx, last_extreme_price, "high"))
                direction = "down"
                last_extreme_price, last_extreme_idx = price, i
        elif direction == "down":
            if price <= last_extreme_price:
                last_extreme_price, last_extreme_idx = price, i
            elif (price - last_extreme_price) / last_extreme_price * 100 >= threshold_pct:
                pivots.append((last_extreme_idx, last_extreme_price, "low"))
                direction = "up"
                last_extreme_price, last_extreme_idx = price, i
    return pivots


def _closes(values) -> pd.DataFrame:
    return pd.DataFrame({"Close": np.asarray(values, dtype=float)},
                        index=pd.bdate_range("2020-01-01", periods=len(values)))


def _walk(n, seed, vol=0.012):
    rng = np.random.RandomState(seed)
    return np.round(100.0 * np.exp(np.cumsum(rng.normal(0.0, vol, n))), 4)


FRAMES = {
    "walk": _closes(_walk(600, 3)),
    "volatile": _closes(_walk(400, 8, vol=0.03)),
    "flat_start": _closes(np.concatenate([np.full(60, 100.0), _walk(300, 5)])),
    "zero_start": _closes(np.concatenate([[0.0], _walk(120, 9)])),
    "two_bars": _closes([100.0, 112.0]),
    "one_bar": _closes([100.0]),
}
THRESHOLDS = sorted({h["max_risk_pct"] for h in HORIZONS.values()} | {3.0})


def _same(got, want):
    assert got == want
    assert [tuple(map(type, p)) for p in got] == [tuple(map(type, p)) for p in want]


@pytest.mark.parametrize("name", FRAMES)
def test_no_state_is_unchanged(name):
    for t in THRESHOLDS:
        _same(zigzag_pivots(FRAMES[name], t), _old_zigzag(FRAMES[name], t))


@pytest.mark.parametrize("name", FRAMES)
def test_resumed_walk_equals_full_walk(name):
    df = FRAMES[name]
    n = len(df)
    for t in THRESHOLDS:
        for m in sorted({1, 2, 37, n // 2, n - 1, n} & set(range(1, n + 1))):
            _same(zigzag_pivots(df, t, state=zigzag_prefix_state(df, t, m)), _old_zigzag(df, t))


def test_yesterdays_state_resumes_today():
    df = FRAMES["walk"]
    for t in THRESHOLDS:
        state = zigzag_prefix_state(df.iloc[:-1], t, len(df) - 2)
        _same(zigzag_pivots(df, t, state=state), _old_zigzag(df, t))


def _starts(monkeypatch) -> list:
    seen, real = [], indicators._zigzag_walk

    def spy(closes, threshold_pct, carry, stop):
        seen.append(carry[0])
        return real(closes, threshold_pct, carry, stop)

    monkeypatch.setattr(indicators, "_zigzag_walk", spy)
    return seen


def test_a_matching_state_skips_the_prefix_and_a_mismatch_restarts(monkeypatch):
    df = FRAMES["walk"]
    t, m = 5.0, len(df) - 1
    state = zigzag_prefix_state(df, t, m)
    revised = df.copy()
    revised.iloc[m // 2, 0] = round(float(revised["Close"].iloc[m // 2]) * 0.9, 4)
    short = df.iloc[:100]
    seen = _starts(monkeypatch)
    _same(zigzag_pivots(df, t, state=state), _old_zigzag(df, t))
    _same(zigzag_pivots(revised, t, state=state), _old_zigzag(revised, t))   # digest differs
    _same(zigzag_pivots(df, 7.0, state=state), _old_zigzag(df, 7.0))         # threshold differs
    _same(zigzag_pivots(short, t, state=state), _old_zigzag(short, t))       # state.m > len(frame)
    assert seen == [m, 1, 1, 1]


def test_empty_frames_and_prefixes():
    assert zigzag_pivots(_closes([]), 3.0) == []
    assert zigzag_prefix_state(FRAMES["walk"], 3.0, 0) is None
    assert zigzag_prefix_states(FRAMES["walk"], (3.0,), 0) is None


def test_prefix_states_are_frozen_pairs():
    df = FRAMES["walk"]
    states = zigzag_prefix_states(df, (2.0, 3.0), len(df) - 1)
    assert isinstance(states, tuple) and [t for t, _ in states] == [2.0, 3.0]
    state = states[0][1]
    assert isinstance(state.pivots, tuple) and isinstance(state.walk, tuple) and len(state.digest) == 16
    with pytest.raises(dataclasses.FrozenInstanceError):
        state.m = 1

"""v108: EMA Crossover re-arm -- the first K pullback touch *events* per held cross.

A touch event is a touching bar whose previous bar did not touch; the first
touching bar inside a cross's window always opens one (K=1 parity with the
pre-v108 first-touch rule, including when the cross bar itself touched).
"""
import math

import numpy as np
import pytest

from swingbot.core.market import entry_filters as ef
from swingbot.core.market.indicators import ema
from swingbot.core.market.strategy_types import HORIZONS
from tests.conftest import make_ohlcv
from tests.market.test_rescue_ema import _cross_then_pullback

WINDOW = 15


def _legacy_first_touch(cross, touch, window):
    """The pre-v108 nested `_first_touch_after`, verbatim in logic: first touch only."""
    out = np.zeros(len(touch), dtype=bool)
    for ci in np.flatnonzero(cross):
        for j in range(ci + 1, min(ci + 1 + window, len(touch))):
            if touch[j]:
                out[j] = True
                break
    return out


def _mask(n, *on):
    mask = np.zeros(n, dtype=bool)
    mask[list(on)] = True
    return mask


def _hits(cross, touch, window=WINDOW, k=1):
    return np.flatnonzero(ef._touch_events_after(cross, touch, window, k)).tolist()


def _multi_cross():
    """Gentle uptrend plus a 45-bar sine: 16 held bullish crosses on 4w."""
    closes = [100 * 1.0006 ** i + 6 * math.sin(2 * math.pi * i / 45) for i in range(700)]
    return make_ohlcv(closes, spread_pct=2.0)


def _held_bull_crosses(df, horizon_key):
    h = HORIZONS[horizon_key]
    diff = ema(df["Close"], h["ema_fast"]) - ema(df["Close"], h["ema_slow"])
    return int(((diff.shift(2) <= 0) & (diff.shift(1) > 0) & (diff > 0)).sum())


# --- the pure helper ---------------------------------------------------------

def test_k1_equals_legacy_first_touch_on_random_masks():
    rng = np.random.default_rng(108)
    for _ in range(2000):
        cross = rng.random(60) < 0.08
        touch = rng.random(60) < 0.4
        assert np.array_equal(ef._touch_events_after(cross, touch, WINDOW, 1),
                              _legacy_first_touch(cross, touch, WINDOW))


def test_cross_bar_touch_still_opens_the_first_event():
    # The K=1 parity trap: the cross bar (0) touches and the run carries into
    # the window. Bar 1's predecessor touched, yet bar 1 must open an event.
    cross, touch = _mask(20, 0), _mask(20, 0, 1, 2)
    assert _hits(cross, touch, k=1) == [1]
    assert _hits(cross, touch, k=3) == [1]


def test_consecutive_touching_bars_are_one_event():
    cross, touch = _mask(20, 0), _mask(20, 2, 3, 4, 7)
    assert _hits(cross, touch, k=2) == [2, 7]
    assert _hits(cross, touch, k=3) == [2, 7]


def test_k_caps_the_event_count():
    cross, touch = _mask(20, 0), _mask(20, 2, 4, 6, 8)
    assert _hits(cross, touch, k=1) == [2]
    assert _hits(cross, touch, k=2) == [2, 4]
    assert _hits(cross, touch, k=3) == [2, 4, 6]


def test_touches_past_the_window_are_ignored():
    # window=5 after a cross at 0 covers bars 1..5; bar 7 is outside.
    cross, touch = _mask(20, 0), _mask(20, 3, 5, 7)
    assert _hits(cross, touch, window=5, k=3) == [3, 5]


def test_a_new_cross_resets_the_count():
    cross, touch = _mask(30, 0, 6), _mask(30, 2, 4, 8, 10)
    assert _hits(cross, touch, k=1) == [2, 8]
    assert _hits(cross, touch, k=2) == [2, 4, 8, 10]


def test_max_touches_below_one_is_rejected():
    with pytest.raises(ValueError):
        ef._touch_events_after(_mask(5, 0), _mask(5, 1), WINDOW, 0)


def test_helper_truncation_never_changes_an_earlier_event():
    rng = np.random.default_rng(7)
    cross = rng.random(80) < 0.1
    touch = rng.random(80) < 0.4
    full = ef._touch_events_after(cross, touch, WINDOW, 3)
    for cut in range(1, 81):
        part = ef._touch_events_after(cross[:cut], touch[:cut], WINDOW, 3)
        assert np.array_equal(part, full[:cut]), cut


# --- wired into ema_cross_entries ---------------------------------------------

def test_fixtures_exercise_several_crosses_and_a_real_entry():
    assert _held_bull_crosses(_multi_cross(), "4w") >= 3
    assert ef.ema_cross_entries(_cross_then_pullback(), "4w")[0].any()


@pytest.mark.parametrize("fixture", [_cross_then_pullback, _multi_cross])
def test_default_entries_identical_to_the_legacy_path(monkeypatch, fixture):
    df = fixture()
    new = {hk: ef.ema_cross_entries(df, hk) for hk in HORIZONS}
    monkeypatch.setattr(ef, "_touch_events_after",
                        lambda cross, touch, window, max_touches: _legacy_first_touch(cross, touch, window))
    old = {hk: ef.ema_cross_entries(df, hk) for hk in HORIZONS}
    for hk in HORIZONS:
        assert new[hk][0].equals(old[hk][0]) and new[hk][1].equals(old[hk][1]), hk


def test_each_direction_gets_its_own_k(monkeypatch):
    seen = []

    def spy(cross, touch, window, max_touches):
        seen.append((window, max_touches))
        return np.zeros(len(touch), dtype=bool)

    monkeypatch.setattr(ef, "_touch_events_after", spy)
    ef.ema_cross_entries(_multi_cross(), "4w", params={"max_touches_bull": 3, "max_touches_bear": 2})
    assert seen == [(15, 3), (15, 2)]


def test_cross_mode_ignores_max_touches():
    df = _cross_then_pullback()
    base = {"entry_mode": "cross"}
    a = ef.ema_cross_entries(df, "4w", params=base)
    b = ef.ema_cross_entries(df, "4w", params={**base, "max_touches_bull": 3, "max_touches_bear": 3})
    assert a[0].equals(b[0]) and a[1].equals(b[1])


def test_frame_truncation_never_changes_an_earlier_entry():
    df = _cross_then_pullback()
    params = {"max_touches_bull": 3, "max_touches_bear": 3}
    full_bull, full_bear = ef.ema_cross_entries(df, "4w", params=params)
    for cut in range(255, len(df)):
        bull, bear = ef.ema_cross_entries(df.iloc[:cut], "4w", params=params)
        assert bull.equals(full_bull.iloc[:cut]) and bear.equals(full_bear.iloc[:cut]), cut


def test_defaults_ship_inert():
    params = ef.DEFAULT_PARAMS["EMA Crossover"]
    assert (params["max_touches_bull"], params["max_touches_bear"]) == (1, 1)

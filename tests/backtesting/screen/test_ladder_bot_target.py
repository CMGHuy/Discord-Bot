"""v238 rung 4: the bot's target band on the event bar, attrition, book survival."""
from types import SimpleNamespace

import numpy as np
import pytest

from swingbot.core.backtesting.screen import ladder_bot as lb
from swingbot.core.backtesting.screen.ladder import LadderEvent
from tests.backtesting.screen.helpers import frame, random_walk

BAND = SimpleNamespace(min_risk_reward_ratio=1.5, max_risk_reward_ratio=2.5)


def _calm():
    return frame(np.linspace(1000.0, 1010.0, 80), start="2017-03-01")


def _quiet_walk(n=300, seed=9):
    """A random walk squeezed to ~0.3% daily moves, so 2 ATR stays inside 2%."""
    df = random_walk(n, seed=seed, start="2016-01-04")
    for col in ("Open", "High", "Low", "Close"):
        df[col] = 100.0 + (df[col] - 100.0) * 0.2
    return df


@pytest.fixture
def band(monkeypatch):
    monkeypatch.setattr(lb, "_scan_params", lambda: BAND)

    def use(levels):
        monkeypatch.setattr(lb, "_target_candidates",
                            lambda frame_, close, side: [close + d for d in levels])
    return use


@pytest.mark.parametrize("offsets, expected_r, reason", [
    ([5.0], None, "no_level_in_band"),            # 1.25 R: below the 1.5 floor
    ([], None, "no_level_in_band"),
    ([7.0, 9.0], 1.75, None),                      # nearest qualifying level
    ([20.0], 2.5, None),                           # beyond the cap: synthetic price at 2.5 R
])
def test_rung4_target_band(band, offsets, expected_r, reason):
    df, t = _calm(), 60
    close = float(df["Close"].iloc[t])
    band(offsets)
    stop, target, why = lb.rung4_levels(df, t, direction="long")
    assert stop == pytest.approx(lb.bot_stop(df, t, direction="long"))
    assert why == reason
    if expected_r is None:
        assert target is None
    else:
        assert (target - close) / (close - stop) == pytest.approx(expected_r, rel=1e-3)


def test_a_stop_past_the_cap_keeps_rung_three_stop_and_gets_a_band_target(band):
    """Rung 4 changes only the target: a wide stop is sized down, never dropped."""
    df, t = random_walk(200, seed=3), 150
    close = float(df["Close"].iloc[t])
    stop = lb.bot_stop(df, t, direction="long")
    assert lb.clamp_would_drop(close, stop, direction="long")      # past the 2% cap
    band([2.0 * (close - stop)])
    got_stop, target, why = lb.rung4_levels(df, t, direction="long")
    assert why is None and got_stop == pytest.approx(stop)
    assert (target - close) / (close - stop) == pytest.approx(2.0, rel=1e-6)


def test_attrition_is_only_a_missing_target_or_stop(monkeypatch):
    assert set(lb.ATTRITION) == {"no_level_in_band", "no_stop"}
    monkeypatch.setattr(lb, "bot_stop", lambda *a, **k: None)
    assert lb.rung4_levels(_calm(), 60, direction="long") == (None, None, "no_stop")


def test_the_live_level_map_lands_inside_the_band():
    df = _quiet_walk()
    params = lb._scan_params()
    seen = set()
    for t in range(120, 300, 30):
        for direction in ("long", "short"):
            stop, target, why = lb.rung4_levels(df, t, direction=direction)
            seen.add(why)
            assert why in (None, *lb.ATTRITION)
            if why is None:
                close = float(df["Close"].iloc[t])
                rr = abs(target - close) / abs(close - stop)
                assert params.min_risk_reward_ratio - 1e-6 <= rr <= params.max_risk_reward_ratio + 1e-6
                assert (target > close) == (direction == "long")
    assert "risk_cap" not in seen


def test_rung4_levels_never_read_a_bar_after_the_signal():
    df = _quiet_walk()
    for t in (150, 250):
        altered = df.copy()
        altered.iloc[t + 1:] = altered.iloc[t + 1:] * 3.0
        for direction in ("long", "short"):
            full = lb.rung4_levels(df, t, direction=direction)
            assert lb.rung4_levels(df.iloc[: t + 1], t, direction=direction) == full
            assert lb.rung4_levels(altered, t, direction=direction) == full


def _e(ticker, signal, entry, exit_):
    return LadderEvent(ticker, signal, entry, exit_, 0.1, 0.1, "target")


EVENTS = [
    _e("AAA", "2017-03-01", "2017-03-02", "2017-03-08"),
    _e("AAA", "2017-03-03", "2017-03-06", "2017-03-10"),   # inside AAA's open trade: dropped
    _e("AAA", "2017-03-08", "2017-03-09", "2017-03-15"),   # signal on the exit date: kept
    _e("BBB", "2017-03-03", "2017-03-06", "2017-03-07"),
]


def test_book_survival_one_per_ticker_and_concurrent_limit():
    wide = lb.book_survival(EVENTS, max_open=30)
    assert wide["one_per_ticker_share"] == pytest.approx(0.75)
    assert wide["concurrent_share"] == pytest.approx(0.75)
    tight = lb.book_survival(list(reversed(EVENTS)), max_open=1)
    assert tight["one_per_ticker_share"] == pytest.approx(0.75)
    assert tight["concurrent_share"] == pytest.approx(0.5)    # BBB waits on AAA's 03-08 exit


def test_book_survival_signals_per_day():
    out = lb.book_survival(EVENTS, max_open=30)
    assert out["signals_per_day_max"] == 2
    assert out["signals_per_day_p95"] == pytest.approx(float(np.percentile([1, 2, 1], 95)))


def test_book_survival_empty_and_bad_limit():
    assert lb.book_survival([], max_open=30) == {
        "one_per_ticker_share": None, "concurrent_share": None,
        "signals_per_day_p95": None, "signals_per_day_max": 0}
    with pytest.raises(ValueError):
        lb.book_survival(EVENTS, max_open=0)

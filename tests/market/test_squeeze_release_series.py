"""V119-1: vectorised squeeze series; the scalar wrapper must keep its old contract.

Witness dicts below were captured from the pre-refactor scalar function.
"""
import numpy as np
import pandas as pd
import pytest

from swingbot.core.market.volatility import (
    squeeze_breakout_confirmation, squeeze_release_series,
)

BASE_N = 56


def _base_close():
    rng = np.random.default_rng(3)
    return np.concatenate([100 + rng.normal(0, 1.5, 30),
                           100 + rng.normal(0, 0.03, BASE_N - 30)])


def _frame(extra, extra_volume=3000.0, base_volume=1000.0):
    close = np.concatenate([_base_close(), np.asarray(extra, float)])
    vol = np.full(len(close), base_volume)
    vol[BASE_N:] = extra_volume
    return pd.DataFrame(
        {"Open": close, "High": close + 0.05, "Low": close - 0.05,
         "Close": close, "Volume": vol},
        index=pd.date_range("2026-01-01", periods=len(close), freq="B"))


def _d(confirmed, is_sq, off, width, vol, brk):
    return {"confirmed": confirmed, "is_squeeze": is_sq, "squeeze_off": off,
            "width_pct": width, "volume_confirmed": vol, "breakout_confirmed": brk}


WITNESSES = {
    "first_release_up": ([104], _d(True, False, True, 3.57, True, True),
                         _d(False, False, True, 3.57, True, False)),
    "first_release_down": ([96], _d(False, False, True, 3.59, True, False),
                           _d(True, False, True, 3.59, True, True)),
    "later_outside_bar": ([104, 106], _d(False, False, False, 6.26, True, True),
                          _d(False, False, False, 6.26, True, False)),
    "continuing_squeeze": ([100.0], _d(False, True, False, 0.1, True, False),
                           _d(False, True, False, 0.1, True, False)),
}


@pytest.mark.parametrize("name", list(WITNESSES))
def test_scalar_witnesses_unchanged(name):
    extra, bull, bear = WITNESSES[name]
    frame = _frame(extra)
    assert squeeze_breakout_confirmation(frame, "bullish") == bull
    assert squeeze_breakout_confirmation(frame, "bearish") == bear


def test_short_history_returns_all_false():
    frame = _frame([104]).iloc[:24]
    assert squeeze_breakout_confirmation(frame, "bullish") == _d(False, False, False, 0.0, False, False)


@pytest.mark.parametrize("bad_volume", [0.0, np.nan])
def test_zero_or_nan_prior_volume_not_confirmed(bad_volume):
    frame = _frame([104], base_volume=bad_volume)
    out = squeeze_breakout_confirmation(frame, "bullish")
    assert out["volume_confirmed"] is False and out["confirmed"] is False
    row = squeeze_release_series(frame).iloc[-1]
    assert not bool(row["volume_confirmed"]) and not bool(row["bullish_confirmed"])


def test_series_columns_and_release_row():
    series = squeeze_release_series(_frame([104]))
    assert set(series.columns) == {
        "is_squeeze", "squeeze_off", "bullish_breakout", "bearish_breakout",
        "volume_confirmed", "bullish_confirmed", "bearish_confirmed"}
    assert all(series[c].dtype == bool for c in series.columns)
    last = series.iloc[-1]
    assert bool(last["bullish_confirmed"]) and not bool(last["bearish_confirmed"])


def test_series_has_no_confirmation_before_enough_history():
    series = squeeze_release_series(_frame([104]))
    assert not series.iloc[:24][["bullish_confirmed", "bearish_confirmed"]].any().any()


@pytest.mark.parametrize("extra", [[104], [96], [104, 106]])
def test_series_truncation_matches_full(extra):
    frame = _frame(extra)
    full = squeeze_release_series(frame)
    for cut in range(25, len(frame) + 1):
        prefix = squeeze_release_series(frame.iloc[:cut]).iloc[-1]
        for col in full.columns:
            assert bool(prefix[col]) == bool(full.iloc[cut - 1][col]), (cut, col)


def test_series_last_row_matches_scalar_flags():
    for extra, _bull, _bear in WITNESSES.values():
        frame = _frame(extra)
        row = squeeze_release_series(frame).iloc[-1]
        bull = squeeze_breakout_confirmation(frame, "bullish")
        bear = squeeze_breakout_confirmation(frame, "bearish")
        assert bool(row["bullish_confirmed"]) == bull["confirmed"]
        assert bool(row["bearish_confirmed"]) == bear["confirmed"]
        assert bool(row["is_squeeze"]) == bull["is_squeeze"]
        assert bool(row["squeeze_off"]) == bull["squeeze_off"]

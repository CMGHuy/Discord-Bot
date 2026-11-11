"""v214 G3: fvg_overhead_aged. The live FVG detector per bar on df.iloc[:t+1];
bearish gaps aged >= 5 bars; within reach = Close[t] < bottom <= Close[t] +
3 x ATR14[t]; one event per gap bar_index, at its first qualifying bar;
control = no gap within reach but an aged gap beyond it."""
import numpy as np
import pandas as pd
import pytest

from swingbot.core.backtesting.screen import indicators
from swingbot.core.backtesting.screen.errors import IdeaError
from swingbot.core.backtesting.screen.ideas import fvg_overhead_aged as idea
from swingbot.core.market import fvg
from tests.backtesting.screen.helpers import frame, random_walk
from tests.market.fvg_frames import BEAR_THIRD, FLAT, STRONG_BEAR, bar_frame

N_FLAT = 40          # helpers.frame([100]*40): TR 2, ATR14 exactly 2.0 from bar 13, reach 106.0


def _on(col, df):
    return np.flatnonzero(idea.states(df)[col].to_numpy()).tolist()


def _descending(count=20, start=95.5):
    """Overlapping bars falling 1.0 a bar: no new gap, gap 31 never filled."""
    return [(start - k, start - k + 1.5, start - k - 1.5, start - k) for k in range(count)]


def _frame_a(wick_at=None, wick_high=None):
    """Flat 30 bars, then a bearish gap 98.5..99.0 formed at bar 31, then a slide."""
    bars = [FLAT] * 30 + [STRONG_BEAR, BEAR_THIRD] + _descending()
    if wick_at is not None:
        close = bars[wick_at][3]
        bars[wick_at] = (close, wick_high, close - 1.5, close)
    return bar_frame(bars)


def _gap(bottom, bar_index, direction="bearish"):
    return {"bottom": float(bottom), "top": float(bottom) + 0.5,
            "mid": float(bottom) + 0.25, "bar_index": bar_index, "direction": direction}


def _script(monkeypatch, gaps_at):
    """The detector sees gaps_at(t) on df.iloc[:t+1]; returns the call log."""
    calls = []

    def fake(part, *args, **kwargs):
        calls.append((len(part), args, kwargs))
        return list(gaps_at(len(part) - 1))

    monkeypatch.setattr(fvg, "scan_fair_value_gaps", fake)
    return calls


def test_the_frozen_definition():
    assert (idea.CAP, idea.MODE, idea.RACE, idea.DIRECTION, idea.ENTRY) == (
        20, "avoid", "fixed", "long", "next_open")
    assert (idea.MIN_AGE_BARS, idea.REACH_ATR) == (5, 3.0)
    assert idea.STATE_COLUMNS == ("event", "control_condition", "condition", "bottom")
    assert idea.PARAMS["lookback"] == fvg.LOOKBACK_BARS == 100
    assert idea.PARAMS["max_per_side"] == fvg.MAX_GAPS_PER_SIDE == 3
    assert idea.SOURCE.startswith("docs/superpowers/results/2026-11-06-loss-review-sep-nov.md")


def test_the_flat_fixture_reach_is_exactly_106():
    atr = indicators.atr(frame([100.0] * N_FLAT), 14)
    assert atr.iloc[:13].isna().all() and (atr.iloc[13:] == 2.0).all()


def test_the_states_frame_shape():
    df = random_walk(300, seed=7)
    out = idea.states(df)
    assert tuple(out.columns) == idea.STATE_COLUMNS and out.index.equals(df.index)
    assert [str(out[c].dtype) for c in idea.STATE_COLUMNS] == ["bool", "bool", "bool", "float64"]
    ev = idea.events(df)
    assert ev.name == "fvg_overhead_aged" and ev.dtype == bool
    pd.testing.assert_series_equal(ev, out["event"], check_names=False)


def test_a_real_gap_fires_once_when_five_bars_old_and_in_reach():
    df = _frame_a()                 # gap at bar 31; bar 35 is in reach but only 4 bars old
    assert _on("event", df) == [36] and _on("condition", df) == [36]
    assert _on("control_condition", df) == list(range(37, 52))   # slid out of reach
    bottom = idea.states(df)["bottom"]
    assert bottom.iloc[36] == 98.5 and bottom.drop(df.index[36]).isna().all()


def test_a_gap_parked_within_reach_fires_once_and_stays_a_condition():
    df = bar_frame([FLAT] * 30 + [STRONG_BEAR, BEAR_THIRD] + [(96.5, 97.0, 96.0, 96.5)] * 20)
    assert _on("event", df) == [36]
    assert _on("condition", df) == list(range(36, 52)) and _on("control_condition", df) == []


def test_a_wick_touching_the_bottom_exactly_fills_the_gap_as_live():
    touched = _frame_a(wick_at=34, wick_high=98.5)         # High == bottom: filled
    assert _on("event", touched) == _on("condition", touched) == []
    assert _on("control_condition", touched) == []
    assert _on("event", _frame_a(wick_at=34, wick_high=98.49)) == [36]


def test_age_four_is_too_young_and_age_five_qualifies(monkeypatch):
    _script(monkeypatch, lambda t: [_gap(103.0, 10)] if t >= 10 else [])
    df = frame([100.0] * N_FLAT)
    assert _on("event", df) == [15] and _on("condition", df) == list(range(15, N_FLAT))
    assert _on("control_condition", df) == []


@pytest.mark.parametrize("bottom, where", [
    (106.0, "condition"), (np.nextafter(106.0, np.inf), "control_condition"),
    (100.0, None), (100.01, "condition")])
def test_the_reach_bounds(monkeypatch, bottom, where):
    """Close < bottom (strict) and bottom <= Close + 3 ATR (inclusive)."""
    _script(monkeypatch, lambda t: [_gap(bottom, 2)])
    df = frame([100.0] * N_FLAT)
    for col in ("condition", "control_condition"):
        assert _on(col, df) == (list(range(13, N_FLAT)) if col == where else [])
    assert _on("event", df) == ([13] if where == "condition" else [])


def test_bullish_gaps_are_ignored(monkeypatch):
    _script(monkeypatch, lambda t: [_gap(103.0, 2, "bullish"), _gap(110.0, 2, "bullish")])
    df = frame([100.0] * N_FLAT)
    assert not idea.states(df)[["event", "condition", "control_condition"]].to_numpy().any()


def test_several_gaps_on_one_bar_are_one_event_with_the_lowest_bottom(monkeypatch):
    _script(monkeypatch, lambda t: [_gap(104.5, 2), _gap(103.0, 3)] + (
        [_gap(105.0, 20)] if t >= 25 else []))
    out = idea.states(frame([100.0] * N_FLAT))
    assert np.flatnonzero(out["event"]).tolist() == [13, 25]
    assert out["bottom"].iloc[13] == 103.0 and out["bottom"].iloc[25] == 103.0


def test_an_evicted_gap_that_comes_back_never_fires_again(monkeypatch):
    """Top-3 eviction or a window exit drops a gap; a later fill of a newer gap
    can bring it back. It keeps its bar_index, so it never re-fires."""
    a, b = _gap(103.0, 2), _gap(104.0, 20)
    _script(monkeypatch, lambda t: ([a] if 13 <= t <= 20 or t >= 26 else []) + (
        [b] if t >= 30 else []))
    df = frame([100.0] * N_FLAT)
    assert _on("event", df) == [13, 30]
    assert _on("condition", df) == list(range(13, 21)) + list(range(26, N_FLAT))


def test_control_needs_no_gap_in_reach_and_an_aged_gap_beyond(monkeypatch):
    near, far, young_far = _gap(103.0, 2), _gap(110.0, 2), _gap(110.0, 30)
    _script(monkeypatch, lambda t: [far] + ([near] if t <= 20 else []) + [young_far])
    df = frame([100.0] * N_FLAT)
    assert _on("condition", df) == list(range(13, 21))
    assert _on("control_condition", df) == list(range(21, N_FLAT))


def test_warm_up_bars_neither_call_the_detector_nor_mark_a_gap_fired(monkeypatch):
    calls = _script(monkeypatch, lambda t: [_gap(103.0, 2)] if t >= 2 else [])
    df = frame([100.0] * N_FLAT)
    assert _on("event", df) == [13]          # in reach and aged from t = 7; ATR from 13
    assert [n for n, _, _ in calls] == list(range(14, N_FLAT + 1))


def test_the_live_detector_is_called_per_bar_on_the_truncated_frame(monkeypatch):
    real, seen = fvg.scan_fair_value_gaps, []

    def spy(part, *args, **kwargs):
        seen.append((part.index, args, kwargs))
        return real(part, *args, **kwargs)

    monkeypatch.setattr(fvg, "scan_fair_value_gaps", spy)
    df = _frame_a()
    assert _on("event", df) == [36]
    assert [len(i) for i, _, _ in seen] == list(range(14, len(df) + 1))
    assert all(i.equals(df.index[: len(i)]) for i, _, _ in seen)
    assert all(args == (100, 3) and not kw for _, args, kw in seen)


def test_a_detector_failure_raises_an_idea_error_naming_the_bar(monkeypatch):
    def gaps_at(t):
        if t == 20:
            raise RuntimeError("bad frame")
        return []

    _script(monkeypatch, gaps_at)
    with pytest.raises(IdeaError, match=r"fvg_overhead_aged.*bar 20") as info:
        idea.states(frame([100.0] * N_FLAT))
    assert isinstance(info.value.__cause__, RuntimeError)
    assert issubclass(IdeaError, RuntimeError)


def test_a_frame_the_idea_cannot_read_raises_an_idea_error():
    with pytest.raises(IdeaError, match="fvg_overhead_aged"):
        idea.states(frame([100.0] * N_FLAT).drop(columns=["High"]))


@pytest.mark.parametrize("seed", [7, 21])
def test_no_bar_reads_a_later_bar(seed):
    """Appending bars after t never changes the event or the condition at t."""
    df = random_walk(700, seed=seed)
    full = idea.states(df)
    assert full["event"].sum() >= 3 and full["control_condition"].sum() >= 3
    for t in (100, 250, 400, 699):
        pd.testing.assert_frame_equal(idea.states(df.iloc[: t + 1]), full.iloc[: t + 1])


@pytest.mark.parametrize("seed", [7, 21])
def test_condition_and_control_exclude_each_other_and_events_are_conditions(seed):
    out = idea.states(random_walk(700, seed=seed))
    assert not (out["condition"] & out["control_condition"]).any()
    assert not (out["event"] & ~out["condition"]).any()
    assert out["bottom"].notna().equals(out["event"])

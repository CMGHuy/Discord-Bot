"""v211 Idea 2 (spec v209 § Track 2): a failed bounce after a >= 1 ATR decline
inside a SHOCK episode, short at the next open."""
import numpy as np

from swingbot.core.backtesting.screen import indicators
from swingbot.core.backtesting.screen.ideas import _shock_breakdown as sb
from swingbot.core.backtesting.screen.ideas import shock_failed_bounce_short as idea
from tests.backtesting.screen.helpers import (assert_prefix_stable, episodes_covering,
                                              frame, random_walk, shock_context)

FLAT = [100.0] * 33                       # High 101, Low 99, ATR14 = 2.0
#: decline 33..35, bounce bar b = 36 (Low 95), 37 holds above 95, 38 fails.
A = FLAT + [98.0, 96.0, 94.0, 96.0, 95.5, 94.0, 93.0] + [93.0] * 10
#: two bounce bars, 36 (Low 95) and 38 (Low 94.6): 39 is below 95 only, 40 below 94.6.
B = FLAT + [98.0, 96.0, 94.0, 96.0, 95.2, 95.6, 94.8, 94.0] + [94.0] * 8
#: b = 36, then five closes at 95.5; 42 closes below 95 with b six bars back.
C = FLAT + [98.0, 96.0, 94.0, 96.0] + [95.5] * 5 + [94.0] * 6
#: a decline of less than 1 ATR: Close[b-1] = 99.2 > 101 - 2.0.
D = FLAT + [99.5, 99.2, 99.6, 98.0] + [98.0] * 6


def _hits(series):
    return np.flatnonzero(series.to_numpy()).tolist()


def _reference(df) -> list:
    """The spec's five conditions read literally, one bar at a time."""
    atr = indicators.atr(df).to_numpy()
    high, low, close = (df[c].to_numpy() for c in ("High", "Low", "Close"))
    out = []
    for t in range(len(close)):
        latest = None
        for b in range(t - 1, t - 6, -1):                      # latest b first
            if b - 10 < 0 or not np.isfinite(atr[b - 2]):
                continue
            hh = high[b - 10:b - 1].max()                      # High[b-10 .. b-2]
            if close[b - 1] <= hh - 1.0 * atr[b - 2] and close[b] > close[b - 1] and high[b] < hh:
                latest = b
                break
        if latest is not None and close[t] < low[latest] and all(
                close[j] >= low[latest] for j in range(latest + 1, t)):
            out.append(t)
    return out


def test_the_constants_are_the_frozen_spec_values():
    assert (idea.CAP, idea.RACE, idea.DIRECTION) == (10, "fixed", "short")
    assert idea.CONTEXT == ("BREADTH_ATR1", "^VIX") and idea.CONTEXT_KIND == "level"
    assert idea.FAMILY == sb.FAMILY and idea.SOURCE == sb.SOURCE
    assert (idea.DECLINE_ATR, idea.HIGH_FROM, idea.HIGH_TO,
            idea.BOUNCE_FROM, idea.BOUNCE_TO) == (1.0, 10, 2, 5, 1)
    assert idea.PARAMS == {"breadth": "BREADTH_ATR1", "vix": "^VIX", "enter": 0.40,
                           "release": 0.10, "decline_atr": 1.0, "high_from": 10,
                           "high_to": 2, "bounce_from": 5, "bounce_to": 1, "side": "short"}
    assert idea.SUMMARY.strip() and not hasattr(idea, "levels")


def test_the_bounce_bar_is_seen_from_the_next_five_bars_only():
    b = idea.bounce_bar(frame(A)).to_numpy()
    assert np.flatnonzero(np.isfinite(b)).tolist() == [37, 38, 39, 40, 41]
    assert set(b[37:42]) == {36.0}


def test_fires_on_the_first_failure_below_the_bounce_low_inside_shock():
    df = frame(A)
    out = idea.events(df, shock_context(df.index, [(35, 45)]))
    assert _hits(out) == [38]
    assert out.dtype == bool and out.name == "shock_failed_bounce_short"
    assert out.index.equals(df.index)


def test_shock_must_be_on_at_t():
    df = frame(A)
    assert not idea.events(df, shock_context(df.index, [(30, 37)])).any()  # released on 37
    assert _hits(idea.control_events(df)) == [38]


def test_the_latest_bounce_bar_counts():
    df = frame(B)
    assert _hits(idea.events(df, shock_context(df.index, [(35, 45)]))) == [40]
    assert _hits(idea.control_events(df)) == [40]


def test_a_bounce_bar_six_bars_back_is_out_of_the_window():
    assert _hits(idea.control_events(frame(C))) == []


def test_a_decline_under_one_atr_is_no_setup():
    assert _hits(idea.control_events(frame(D))) == []


def test_a_bounce_high_at_the_recent_high_is_no_lower_high():
    highs = np.asarray(A) + 1.0
    highs[36] = 101.0                                          # == max(High[26..34])
    assert _hits(idea.control_events(frame(A, highs=highs))) == []


def test_the_control_equals_the_literal_reading_on_random_walks():
    for seed in (21, 31, 41):
        df = random_walk(800, seed=seed)
        expected = _reference(df)
        assert len(expected) >= 20                             # non-vacuous
        assert _hits(idea.control_events(df)) == expected
        assert idea.control_events(df).name == "shock_failed_bounce_short_control"


def test_events_on_t_read_no_later_stock_or_context_bar():
    df = random_walk(700, seed=21)
    ctx = shock_context(df.index, episodes_covering(_hits(idea.control_events(df)), len(df)))

    def fn(d):
        return idea.events(d, {k: v.loc[: d.index[-1]] for k, v in ctx.items()})

    assert fn(df).sum() >= 3                                   # non-vacuous
    for f in (fn, idea.control_events, idea.bounce_bar):
        assert_prefix_stable(f, df, [100, 250, 400, 699])

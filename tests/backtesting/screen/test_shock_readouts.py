"""v211 shock read-outs (spec § Printed alongside each verdict): gap
buckets, day of the episode, the shock-day null and the outcome-blind
preflight. Pure functions; printed by the runner, never gating."""
import types

import numpy as np
import pandas as pd
import pytest

from swingbot.core.backtesting.screen import null, verdict
from swingbot.core.backtesting.screen import shock_readouts as sr
from tests.backtesting.screen.helpers import frame, random_walk


def test_the_frozen_constants():
    assert sr.SHOCK_STRESS_SLIPPAGE_FACTOR == 3
    assert sr.GAP_BUCKETS == ("<= -1%", "-1% .. +1%", ">= +1%")
    assert sr.EPISODE_DAYS == ("peak", "later")


@pytest.mark.parametrize("gap, bucket", [
    (-5.0, "<= -1%"), (-1.0, "<= -1%"), (-0.999, "-1% .. +1%"), (0.0, "-1% .. +1%"),
    (0.999, "-1% .. +1%"), (1.0, ">= +1%"), (7.5, ">= +1%")])
def test_gap_bucket_edges_fall_on_the_outer_buckets(gap, bucket):
    assert sr.gap_bucket(gap) == bucket


def test_a_missing_gap_has_no_bucket():
    assert sr.gap_bucket(float("nan")) is None


# --- event tags ----------------------------------------------------------------

def _tag_inputs():
    """Eight bars at Close 100. Opens: bar 1 = 99 (-1 % gap after bar 0),
    bar 2 = 101 (+1 %), bar 3 = 100.5 (+0.5 %). Episode 1 on bars 1-3,
    episode 2 on bars 5-6 (its breadth stays below episode 1's peak)."""
    closes = np.full(8, 100.0)
    opens = closes.copy()
    opens[1], opens[2], opens[3] = 99.0, 101.0, 100.5
    df = frame(closes, opens=opens)
    shock = np.array([False, True, True, True, False, True, True, False])
    episode = np.array([0, 1, 1, 1, 0, 2, 2, 0])
    state = pd.DataFrame({"shock": shock, "episode": episode}, index=df.index)
    breadth = pd.Series([0.0, 0.45, 0.30, 0.50, 0.05, 0.42, 0.41, 0.0], index=df.index)
    return df, state, breadth


SIGNALS = np.array([0, 1, 2, 3, 5, 6, 7])


def test_event_tags_bucket_the_gap_and_the_day_of_the_episode():
    df, state, breadth = _tag_inputs()
    tags = sr.event_tags(df, state, breadth, SIGNALS)
    assert [t["signal_date"] for t in tags] == [d.strftime("%Y-%m-%d") for d in df.index[SIGNALS]]
    assert [t["gap_bucket"] for t in tags] == [
        "<= -1%", ">= +1%", "-1% .. +1%", "-1% .. +1%", "-1% .. +1%", "-1% .. +1%", None]
    assert [t["episode_day"] for t in tags] == [None, "peak", "later", "peak", "peak", "later", None]
    assert tags[0]["gap_pct"] == pytest.approx(-1.0)
    assert tags[2]["gap_pct"] == pytest.approx(0.5)
    assert np.isnan(tags[-1]["gap_pct"])


def test_event_tags_never_read_a_later_breadth():
    df, state, breadth = _tag_inputs()
    before = sr.event_tags(df, state, breadth, np.array([1, 2]))
    later = breadth.copy()
    later.iloc[3] = 0.99          # a higher peak after the signals
    assert sr.event_tags(df, state, later, np.array([1, 2])) == before


def test_event_tags_read_breadth_on_a_wider_context_calendar():
    df, state, breadth = _tag_inputs()
    wide = pd.concat([pd.Series([0.9], index=[pd.Timestamp("2009-12-31")]), breadth])
    assert _same(sr.event_tags(df, state, wide, SIGNALS), sr.event_tags(df, state, breadth, SIGNALS))


def _same(a, b):
    """Tag lists equal, NaN gaps equal to each other."""
    strip = lambda tags: [{k: v for k, v in t.items() if k != "gap_pct"} for t in tags]  # noqa: E731
    gaps = lambda tags: [t["gap_pct"] for t in tags]  # noqa: E731
    return strip(a) == strip(b) and np.allclose(gaps(a), gaps(b), equal_nan=True)


def test_event_tags_of_no_signal_are_empty():
    df, state, breadth = _tag_inputs()
    assert sr.event_tags(df, state, breadth, np.array([], dtype=int)) == []


# --- the shock-day null --------------------------------------------------------

@pytest.fixture
def raced(monkeypatch):
    """Replace the race with one whose R is the bar position, and record the call."""
    seen = {}

    def fake_race(df, positions, cap, *, atr=None, slippage_bps=None, commission=None, **extra):
        seen.update(positions=np.asarray(positions), cap=cap, extra=extra,
                    slippage_bps=slippage_bps, commission=commission)
        return types.SimpleNamespace(r=np.asarray(positions, dtype=float))

    def race_for(shape):
        seen["shape"] = shape
        return fake_race

    monkeypatch.setattr(sr.race, "race_for", race_for)
    return seen


POOL_BARS = [40, 50, 60, 70, 80, 90, 100]


def _pool(bars=POOL_BARS, n=300):
    pool = np.zeros(n, dtype=bool)
    pool[bars] = True
    return pool


def _null(pool, k=20, events=(10, 20), direction="short", **costs):
    return sr.shock_null(random_walk(300), np.array(events, dtype=int), pool, k,
                         null.null_seed("x", "AAA"), cap=10, atr=None, shape="fixed",
                         direction=direction, **costs)


def test_the_shock_null_draws_only_pool_bars_without_replacement(raced):
    out = _null(_pool(), slippage_bps=5.0, commission=0.01)
    assert out.event_pos.tolist() == [10, 20] and out.dropped == 0
    assert raced["shape"] == "fixed" and raced["cap"] == 10
    assert raced["extra"] == {"direction": "short"}
    assert (raced["slippage_bps"], raced["commission"]) == (5.0, 0.01)
    # k = 20 > 7 pool bars: each group is the whole pool, once each
    assert sorted(raced["positions"].tolist()) == sorted(POOL_BARS * 2)
    assert out.null_mean_r.tolist() == [70.0, 70.0]


def test_a_smaller_k_draws_k_distinct_pool_bars_per_event(raced):
    out = _null(_pool(), k=3)
    groups = raced["positions"].reshape(2, 3)
    for group in groups:
        assert len(set(group.tolist())) == 3 and set(group.tolist()) <= set(POOL_BARS)
    assert out.null_mean_r.tolist() == pytest.approx(groups.mean(axis=1).tolist())


def test_the_shock_null_is_deterministic(raced):
    first = _null(_pool(), k=3)
    second = _null(_pool(), k=3)
    assert first.null_mean_r.tolist() == second.null_mean_r.tolist()


def test_a_long_idea_passes_no_direction(raced):
    _null(_pool(), direction="long")
    assert raced["extra"] == {}


def test_a_pool_below_the_floor_drops_every_event_and_races_nothing(raced):
    out = _null(_pool(POOL_BARS[: null.MIN_CANDIDATES - 1]))
    assert out.event_pos.tolist() == [] and out.null_mean_r.tolist() == []
    assert out.dropped == 2 and raced == {}


def test_no_event_races_nothing(raced):
    out = _null(_pool(), events=())
    assert out.event_pos.tolist() == [] and out.dropped == 0 and raced == {}


# --- the outcome-blind preflight -----------------------------------------------

def _preflight_state():
    index = pd.bdate_range("2010-12-27", "2015-01-09")
    shock = pd.Series(False, index=index)
    for day in ("2010-12-28", "2011-03-01", "2011-03-02", "2011-03-08",
                "2014-12-31", "2015-01-02"):
        shock[pd.Timestamp(day)] = True
    return pd.DataFrame({"shock": shock, "episode": shock.astype(int)})


def test_preflight_counts_shock_days_iso_weeks_and_events_per_year():
    events = ["2011-03-02", "2011-03-03", "2014-12-31", "2010-12-29"]
    table = sr.preflight_years(_preflight_state(), events)
    assert list(table) == list(verdict.YEARS)
    assert table[2011] == {"shock_days": 3, "shock_weeks": 2, "events": 2}
    assert table[2012] == {"shock_days": 0, "shock_weeks": 0, "events": 0}
    # 2014-12-31 and 2015-01-02 share ISO week 2015-W01: once in each calendar year
    assert table[2014] == {"shock_days": 1, "shock_weeks": 1, "events": 1}
    assert table[2015] == {"shock_days": 1, "shock_weeks": 1, "events": 0}


def test_preflight_takes_timestamps_and_ignores_years_outside_the_rule():
    events = pd.to_datetime(["2010-12-29", "2011-03-02"])
    table = sr.preflight_years(_preflight_state(), events)
    assert 2010 not in table and table[2011]["events"] == 1

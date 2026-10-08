# tests/market/test_structure_events.py
import numpy as np
import pandas as pd
import pytest

from swingbot.core.market import structure as st
from tests.conftest import make_ohlcv
from tests.fixtures.ohlcv_parity import load_ohlcv
from tests.market.structure_fixtures import UP, frame, wavy_frame
from tests.market.structure_tier_fixtures import DOWN, tier_frame

SIDES = [(False, "bearish", "bullish"), (True, "bullish", "bearish")]   # mirror, trend side, counter side


def _fired(df):
    events = st.structure_events(df)
    first = events[events["event_pos"].notna()].drop_duplicates("event_pos")
    return [(int(row.event_pos), row.event_kind, row.event_direction) for row in first.itertuples()]


def _same(a, b):
    return all((pd.isna(x) and pd.isna(y)) or x == y for x, y in zip(a, b))


def _random_walk(n=300, seed=7):
    closes = 100 * np.exp(np.cumsum(np.random.default_rng(seed).normal(0.0003, 0.015, n)))
    return make_ohlcv(closes, spread_pct=2.0)


@pytest.mark.parametrize("mirror,trend,counter", SIDES)
def test_the_fixture_fires_exactly_its_four_events(mirror, trend, counter):
    assert _fired(tier_frame(DOWN, mirror=mirror)) == [
        (70, "bos", trend), (94, "choch", counter), (102, "bos", trend), (110, "bos", counter)]


@pytest.mark.parametrize("mirror,trend,counter", SIDES)
def test_a_break_with_the_trend_is_a_bos(mirror, trend, counter):
    df = tier_frame(DOWN, mirror=mirror)
    assert st._major_state(st.major_pivots(df).iloc[69]) == ("up" if mirror else "down")
    assert tuple(st.structure_events(df).iloc[70]) == ("bos", trend, 70)


@pytest.mark.parametrize("mirror,trend,counter", SIDES)
def test_a_break_against_the_trend_is_a_choch(mirror, trend, counter):
    df = tier_frame(DOWN, mirror=mirror)
    assert st._major_state(st.major_pivots(df).iloc[93]) == ("up" if mirror else "down")
    assert tuple(st.structure_events(df).iloc[94]) == ("choch", counter, 94)


@pytest.mark.parametrize("mirror", [False, True])
def test_later_closes_beyond_the_same_pivot_fire_nothing(mirror):
    df = tier_frame(DOWN, mirror=mirror)
    close, level = df["Close"].to_numpy(), st.major_pivots(df)["last_msl" if mirror else "last_msh"].iloc[93]
    beyond = close[95:98] < level if mirror else close[95:98] > level
    assert beyond.all()                                   # bars 95..97 also close beyond the broken pivot
    assert (st.structure_events(df)["event_pos"].iloc[94:102] == 94).all()


@pytest.mark.parametrize("mirror", [False, True])
def test_no_event_before_structure_exists(mirror):
    events = st.structure_events(tier_frame(DOWN, mirror=mirror)).iloc[:70]
    assert events["event_kind"].isna().all() and events["event_pos"].isna().all()


def test_a_clean_uptrend_fires_nothing():
    assert _fired(frame(UP)) == []                         # no major high exists, so major state is None


@pytest.mark.parametrize("df", [wavy_frame(), _random_walk(), tier_frame(DOWN), tier_frame(DOWN, mirror=True)],
                         ids=["wavy", "walk", "down", "up"])
def test_events_are_truncation_stable_on_every_cut(df):
    full = st.structure_events(df)
    assert tuple(full.columns) == st.EVENT_COLUMNS and full.index.equals(df.index)
    for t in range(len(df)):
        assert _same(st.structure_events(df.iloc[:t + 1]).iloc[-1], full.iloc[t]), t


def test_events_are_truncation_stable_on_a_real_symbol():
    df = load_ohlcv("TSLA").iloc[:700]
    full = st.structure_events(df)
    assert {kind for _, kind, _ in _fired(df)} == {"bos", "choch"}
    for t in range(60, len(df), 7):
        assert _same(st.structure_events(df.iloc[:t + 1]).iloc[-1], full.iloc[t]), t


@pytest.mark.parametrize("df", [_random_walk(600), load_ohlcv("TSLA").iloc[:700]], ids=["walk", "tsla"])
def test_an_event_reads_only_majors_known_the_bar_before(df):
    majors, close = st.major_pivots(df), df["Close"].to_numpy()
    tiers = st.pivot_tiers(df)
    major_bar = {(r.kind, int(r.pos)): r.major_pos for r in tiers.itertuples()}
    fired = _fired(df)
    assert fired
    for bar, _, direction in fired:
        before = majors.iloc[bar - 1]
        kind, pos, level = (("sh", before["last_msh_pos"], before["last_msh"]) if direction == "bullish"
                            else ("sl", before["last_msl_pos"], before["last_msl"]))
        assert major_bar[(kind, int(pos))] < bar            # never on the bar the pivot became major
        assert close[bar] > level if direction == "bullish" else close[bar] < level


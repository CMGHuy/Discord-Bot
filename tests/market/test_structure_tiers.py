# tests/market/test_structure_tiers.py
import numpy as np
import pandas as pd
import pytest

from swingbot.core.market import structure as st
from swingbot.core.market.indicators import atr
from tests.conftest import make_ohlcv
from tests.fixtures.ohlcv_parity import load_ohlcv
from tests.market.structure_fixtures import UP, frame, wavy_frame
from tests.market.structure_tier_fixtures import (EARLY, IMPACT_LATER, NO_BREAK, NO_REF, UNDERCUT, tier_frame,
                                                  weak_frame)

MIRRORS = [(False, "sl"), (True, "sh")]


def _major_pos(df, kind, pos):
    tiers = st.pivot_tiers(df)
    row = tiers[(tiers["kind"] == kind) & (tiers["pos"] == pos)]
    assert len(row) == 1, tiers
    value = row["major_pos"].iloc[0]
    return None if pd.isna(value) else int(value)


def _same(a, b):
    return all((pd.isna(x) and pd.isna(y)) or x == y for x, y in zip(a, b))


def _reference_side(own, other, ext, opp, close, atr14, k, m):
    """Low-side reading of the spec, one bar at a time (slow on purpose)."""
    out = {}
    for i in own:
        refs, major = [p for p in other if p < i], None
        for j in range(i + 1, len(close) if refs and atr14[i] > 0 else 0):
            if ext[j] < ext[i]:
                break
            if j >= i + k and close[j] > opp[refs[-1]] and opp[i:j + 1].max() - ext[i] >= m * atr14[i]:
                major = j
                break
        out[int(i)] = major
    return out


def _reference(df, m=2.0, k=3):
    sh, sl = st.pivot_confirmations(df, k)
    sh_pos, sl_pos = list(np.flatnonzero(sh) - k), list(np.flatnonzero(sl) - k)
    high, low, close = (df[c].to_numpy(float) for c in ("High", "Low", "Close"))
    atr14 = atr(df, 14).to_numpy(float)
    lows = _reference_side(sl_pos, sh_pos, low, high, close, atr14, k, m)
    highs = _reference_side(sh_pos, sl_pos, -high, -low, -close, atr14, k, m)
    return {("sl", i): bar for i, bar in lows.items()} | {("sh", i): bar for i, bar in highs.items()}


def _random_walk(n=600, seed=7):
    closes = 100 * np.exp(np.cumsum(np.random.default_rng(seed).normal(0.0003, 0.015, n)))
    return make_ohlcv(closes, spread_pct=2.0)


@pytest.mark.parametrize("mirror,kind", MIRRORS)
def test_break_with_under_two_atr_of_reaction_stays_minor(mirror, kind):
    df = weak_frame(mirror=mirror)
    close = float(df["Close"].iloc[36])
    broken = close < float(df["Low"].iloc[24]) if mirror else close > float(df["High"].iloc[24])
    assert broken                                        # the reference swing IS closed through at bar 36
    assert atr(df, 14).iloc[32] == pytest.approx(4.0)
    assert _major_pos(df.iloc[:38], kind, 32) is None    # through bar 37: 1.9 ATR of reaction, still minor


@pytest.mark.parametrize("mirror,kind", MIRRORS)
def test_major_at_the_bar_the_reaction_arrives(mirror, kind):
    assert _major_pos(weak_frame(mirror=mirror), kind, 32) == 38


@pytest.mark.parametrize("mirror,kind", MIRRORS)
def test_big_reaction_without_a_break_stays_minor(mirror, kind):
    assert _major_pos(tier_frame(NO_BREAK, mirror=mirror), kind, 16) is None


@pytest.mark.parametrize("mirror,kind", MIRRORS)
def test_major_at_the_bar_the_break_arrives(mirror, kind):
    df = tier_frame(IMPACT_LATER, mirror=mirror)
    assert _major_pos(df.iloc[:20], kind, 16) is None    # bar 19: confirmed, reaction there, no break yet
    assert _major_pos(df, kind, 16) == 20


@pytest.mark.parametrize("mirror,kind", MIRRORS)
def test_never_major_before_the_pivot_is_confirmed(mirror, kind):
    df = tier_frame(EARLY, mirror=mirror)
    early = st.pivot_tiers(df.iloc[:19])                 # bar 18: both conditions hold, the low is unconfirmed
    assert early[early["pos"] == 16].empty
    assert _major_pos(df, kind, 16) == 19                # i + 3


@pytest.mark.parametrize("mirror,kind", MIRRORS)
def test_an_undercut_low_can_never_become_major(mirror, kind):
    df = tier_frame(UNDERCUT, mirror=mirror)
    assert _major_pos(df, kind, 16) is None
    assert _major_pos(df, kind, 32) == 36                # the low that undercut it does qualify


@pytest.mark.parametrize("mirror,kind", MIRRORS)
def test_no_reference_swing_stays_minor(mirror, kind):
    df = tier_frame(NO_REF, mirror=mirror, leg=16)
    assert atr(df, 14).iloc[16] > 0                      # not the ATR guard: there is simply no reference
    assert _major_pos(df, kind, 16) is None


@pytest.mark.parametrize("df", [wavy_frame(), _random_walk(), frame(UP), frame(UP, mirror=True),
                                load_ohlcv("TSLA").iloc[:700]], ids=["wavy", "walk", "up", "down", "tsla"])
def test_tiers_match_the_literal_spec_reading(df):
    tiers = st.pivot_tiers(df)
    got = {(r.kind, int(r.pos)): None if pd.isna(r.major_pos) else int(r.major_pos) for r in tiers.itertuples()}
    assert got == _reference(df)
    assert tuple(tiers.columns) == st.TIER_COLUMNS


def test_a_clean_uptrend_has_major_lows_and_no_major_high():
    majors = st.major_pivots(frame(UP)).iloc[-1]
    assert (majors["last_msl_pos"], majors["prior_msl_pos"]) == (64, 48)
    assert pd.isna(majors["last_msh_pos"])               # no high was ever followed by a close below a swing low


@pytest.mark.parametrize("df", [wavy_frame(), _random_walk(300)], ids=["wavy", "walk"])
def test_major_pivots_are_truncation_stable_on_every_cut(df):
    full = st.major_pivots(df)
    assert tuple(full.columns) == st.MAJOR_COLUMNS and full.index.equals(df.index)
    for t in range(len(df)):
        assert _same(st.major_pivots(df.iloc[:t + 1]).iloc[-1], full.iloc[t]), t


def test_major_pivots_are_truncation_stable_on_a_real_symbol():
    df = load_ohlcv("TSLA").iloc[:700]
    full = st.major_pivots(df)
    assert full["last_msh_pos"].notna().any() and full["last_msl_pos"].notna().any()
    for t in range(60, len(df), 7):
        assert _same(st.major_pivots(df.iloc[:t + 1]).iloc[-1], full.iloc[t]), t


def test_a_major_is_never_known_before_its_qualifying_bar():
    df = _random_walk()
    tiers, majors = st.pivot_tiers(df), st.major_pivots(df)
    major = tiers[tiers["major_pos"].notna()]
    assert len(major) > 10
    assert (major["major_pos"] >= major["pos"] + st.PIVOT_K).all()
    for row in major.itertuples():
        column = "last_msh_pos" if row.kind == "sh" else "last_msl_pos"
        assert not (majors[column].iloc[:int(row.major_pos)] == row.pos).any(), row


def test_majors_sort_by_pivot_index_not_by_when_they_qualified():
    majors = st.major_pivots(weak_frame())               # low 32 qualifies at 38, the OLDER low 16 at 39
    assert majors["last_msl_pos"].iloc[38] == 32 and pd.isna(majors["prior_msl_pos"].iloc[38])
    assert (majors["last_msl_pos"].iloc[39], majors["prior_msl_pos"].iloc[39]) == (32, 16)


def test_flat_and_nan_frames_do_not_raise():
    assert st.pivot_tiers(make_ohlcv(np.full(80, 100.0), spread_pct=0.0)).empty
    df = wavy_frame().copy()
    df.iloc[40:42, df.columns.get_loc("High")] = np.nan
    assert len(st.major_pivots(df)) == len(df)


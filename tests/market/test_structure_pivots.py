import numpy as np
import pandas as pd

from swingbot.core.market import structure as st
from tests.conftest import make_ohlcv
from tests.market.structure_fixtures import UP, frame, wavy_frame


def _same(a, b):
    return all((pd.isna(x) and pd.isna(y)) or x == y for x, y in zip(a, b))


def test_pivots_are_truncation_stable_on_every_cut():
    df = wavy_frame()
    full = st.confirmed_pivots(df)
    for t in range(len(df)):
        assert _same(st.confirmed_pivots(df.iloc[:t + 1]).iloc[-1], full.iloc[t]), t


def test_a_pivot_appears_exactly_k_bars_after_it_forms():
    pivots = st.confirmed_pivots(frame(UP))
    assert pivots["last_sh_pos"].iloc[8:11].isna().all()   # peak at bar 8 not yet known
    assert pivots["last_sh_pos"].iloc[11] == 8              # known from bar 8 + k
    assert pivots["last_sl_pos"].iloc[16:19].isna().all()
    assert pivots["last_sl_pos"].iloc[19] == 16


def test_no_pivot_is_ever_newer_than_t_minus_k():
    pivots = st.confirmed_pivots(wavy_frame())
    rows = np.arange(len(pivots))
    for column in ("last_sh_pos", "prior_sh_pos", "last_sl_pos", "prior_sl_pos"):
        known = pivots[column].notna().to_numpy()
        assert (pivots[column].to_numpy()[known] <= rows[known] - st.PIVOT_K).all(), column


def test_prior_is_the_pivot_before_last():
    pivots = st.confirmed_pivots(frame(UP)).iloc[-1]
    assert pivots["prior_sh_pos"] < pivots["last_sh_pos"]
    assert pivots["prior_sh"] < pivots["last_sh"]             # higher highs
    assert pivots["prior_sl"] < pivots["last_sl"]             # higher lows


def test_equal_highs_label_the_first_bar_only():
    closes = np.array([100, 101, 102, 103, 105, 105, 103, 102, 101, 100, 99, 98], dtype=float)
    pivots = st.confirmed_pivots(make_ohlcv(closes, spread_pct=1.0))
    assert pivots["last_sh_pos"].iloc[:7].isna().all()
    assert pivots["last_sh_pos"].iloc[7:].tolist() == [4.0] * 5


def test_columns_and_index_match_the_contract():
    df = frame(UP)
    pivots = st.confirmed_pivots(df)
    assert tuple(pivots.columns) == st.PIVOT_COLUMNS
    assert pivots.index.equals(df.index)
    assert st.PIVOT_K == 3

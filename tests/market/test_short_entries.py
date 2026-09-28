"""v104 §3.1: B1 Bull Trap -- a breakout that closes back below its level within k bars."""
import numpy as np
import pandas as pd
import pytest

from swingbot.core.market import entry_filters as ef
from swingbot.core.market import short_entries as se
from swingbot.core.market.indicators import atr
from swingbot.core.market.strategy_types import SHORT_STRATEGIES, STRATEGY_GATES
from swingbot.core.planning.params import STRUCTURE_BUFFER_ATR
from tests.helpers import make_ohlcv

HZ = "2w"                              # sr_lookback 10
PAD = [(100.0, 101.0, 99.0, 100.0)] * 40
# 6 trailing bars (brief listed 3): the truncation case k=45 must stay strictly
# inside the 48-row frame, or iloc[:k+1] is the whole frame and proves nothing.
FLAT = [(100.0, 101.0, 99.0, 100.0)] * 6


def _frame(tail):
    return make_ohlcv(PAD + tail + FLAT, start="2015-01-02")


def _trap_next_bar():
    # b=40 closes 102 > R=101; b+1 closes 100.5 < 101 -> trap at 41
    return _frame([(100.5, 102.5, 100.0, 102.0), (101.5, 102.0, 100.0, 100.5)]), 41


def test_trap_fires_once_with_its_structure():
    df, t = _trap_next_bar()
    frame = se.bull_trap_frame(df, HZ)
    assert frame["signal"].tolist().count(True) == 1 and bool(frame["signal"].iloc[t])
    row = frame.iloc[t]
    assert row["level"] == 101.0
    assert row["stop"] == pytest.approx(102.5 + se.STOP_ATR * float(atr(df, 14).iloc[t]))
    assert row["target_a"] == 99.0 and row["target_b"] == 99.0


def test_k_bounds_how_late_the_failure_may_come():
    df = _frame([(100.5, 102.5, 100.0, 102.0), (101.8, 102.2, 101.2, 101.5),
                 (101.2, 101.6, 100.0, 100.5)])              # fails at b+2
    assert not se.bull_trap_frame(df, HZ, params={"k": 1})["signal"].any()
    assert bool(se.bull_trap_frame(df, HZ, params={"k": 2})["signal"].iloc[42])


def test_consecutive_breakouts_fire_on_distinct_bars_only():
    df = _frame([(100.5, 102.5, 100.0, 102.0),              # b1: level 101
                 (102.2, 103.5, 102.0, 103.0),              # b2: level 102.5
                 (102.4, 102.8, 101.6, 102.0),              # < 102.5 -> trap of b2 at 42
                 (101.2, 101.4, 99.5, 100.0)])              # < 101   -> trap of b1 at 43
    frame = se.bull_trap_frame(df, HZ)
    fired = list(np.flatnonzero(frame["signal"].to_numpy()))
    assert fired == [42, 43]
    assert frame["level"].iloc[42] == 102.5 and frame["level"].iloc[43] == 101.0


@pytest.mark.parametrize("k", [40, 41, 42, 45])
def test_bull_trap_frame_is_truncation_invariant(k):
    df, _ = _trap_next_bar()
    full = se.bull_trap_frame(df, HZ).iloc[k]
    cut = se.bull_trap_frame(df.iloc[:k + 1], HZ).iloc[k]
    assert bool(full["signal"]) == bool(cut["signal"])
    for col in ("level", "stop", "target_a", "target_b"):
        assert full[col] == pytest.approx(cut[col], nan_ok=True)


def test_exit_before_blocks_a_report_within_one_bar_and_needs_the_column():
    df, t = _trap_next_bar()
    with pytest.raises(ValueError):
        se.bull_trap_frame(df, HZ, params={"earnings": "exit_before"})
    df["evt_bars_to_next"] = np.nan
    assert bool(se.bull_trap_frame(df, HZ, params={"earnings": "exit_before"})["signal"].iloc[t])
    df.loc[df.index[t], "evt_bars_to_next"] = 1
    assert not se.bull_trap_frame(df, HZ, params={"earnings": "exit_before"})["signal"].any()


def test_registered_short_only_and_masked():
    df, t = _trap_next_bar()
    bull, bear = ef.ENTRY_FUNCS["Bull Trap"](df, HZ)
    assert not bull.any() and bool(bear.iloc[t])
    assert ef.DEFAULT_PARAMS["Bull Trap"] == {"k": 3, "earnings": "hold"}
    for name in SHORT_STRATEGIES:
        assert STRATEGY_GATES[name] == {"directions": ()}
    masked_bull, masked_bear = ef.entries_for("Bull Trap", df, HZ)
    assert not masked_bull.any() and not masked_bear.any()


def test_structure_at_matches_the_frame_row():
    df, t = _trap_next_bar()
    structure = se.structure_at("Bull Trap", df, t, HZ)
    assert structure["stop"] == pytest.approx(se.bull_trap_frame(df, HZ)["stop"].iloc[t])
    assert se.structure_at("Bull Trap", df, t - 1, HZ) is None
    assert se.structure_at("Bull Trap", df, -len(FLAT) - 1, HZ) is not None   # negative index


def test_stop_buffer_is_the_planning_structure_buffer():
    assert se.STOP_ATR == STRUCTURE_BUFFER_ATR

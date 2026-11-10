"""v214 G4: the FVG scan splits into a raising helper (the screen's) and the
live wrapper that keeps its blanket swallow, byte-identical to before."""
import hashlib
import json

import pandas as pd
import pytest

from swingbot.core.market import fvg
from tests.backtesting.screen.helpers import random_walk
from tests.market.fvg_frames import BEAR_THIRD, FLAT, bar_frame, gap_frame, witness_frame

#: sha256 of json.dumps([[gap rounded to 10 dp, ...] per prefix df.iloc[:t+1]],
#: sort_keys=True), captured from find_fair_value_gaps_detailed BEFORE v214
#: (main at 5c5d1990). A change to the scan body changes these.
PRE_V214_DIGESTS = {
    ("witness", 126): "0d1d8ef4d366db583ae4eccd6aa7a4188e7027608ed807c17605881012bda6b9",
    ("witness", 7): "6a231876944681381aa681e6fec9b1cfcbe6dfc9326bc3b12a261ba96ea7033b",
    ("witness", 3): "6b719750d698d25684f8c358778e47fed8a2e2e18e20ef3cd2a72a0d522e5bd5",
    ("random_walk", 21): "0690f8482987d35fed2e0415d57e1513f90df542982fb8c809b1856814ac8be2",
}


def _frame(kind, seed):
    return witness_frame(seed=seed) if kind == "witness" else random_walk(700, seed=seed)


def _rounded(gap):
    return {k: (round(v, 10) if isinstance(v, float) else v) for k, v in gap.items()}


def _digest(fn, df):
    out = [[_rounded(g) for g in fn(df.iloc[: t + 1])] for t in range(len(df))]
    return hashlib.sha256(json.dumps(out, sort_keys=True).encode()).hexdigest()


@pytest.mark.parametrize("key", sorted(PRE_V214_DIGESTS))
def test_the_live_detector_output_is_byte_identical_to_before(key):
    assert _digest(fvg.find_fair_value_gaps_detailed, _frame(*key)) == PRE_V214_DIGESTS[key]


@pytest.mark.parametrize("key", sorted(PRE_V214_DIGESTS))
def test_the_helper_returns_exactly_what_the_live_detector_returns(key):
    df = _frame(*key)
    for t in range(len(df)):
        part = df.iloc[: t + 1]
        assert fvg.scan_fair_value_gaps(part) == fvg.find_fair_value_gaps_detailed(part)


def test_the_helper_passes_lookback_and_max_per_side_through():
    df = witness_frame(seed=126)
    for lookback, per_side in ((20, 1), (100, 3), (260, 5)):
        assert (fvg.scan_fair_value_gaps(df, lookback, per_side)
                == fvg.find_fair_value_gaps_detailed(df, lookback, per_side))


def test_a_hand_built_bearish_gap_keeps_its_exact_geometry():
    gap = {"bottom": 98.5, "top": 99.0, "mid": 98.75, "bar_index": 21, "direction": "bearish"}
    df = gap_frame(FLAT, BEAR_THIRD)
    assert fvg.scan_fair_value_gaps(df) == [gap]
    assert fvg.find_fair_value_gaps_detailed(df) == [gap]


def test_fewer_than_three_bars_is_no_gap_in_both():
    df = bar_frame([FLAT, FLAT])
    assert fvg.scan_fair_value_gaps(df) == [] == fvg.find_fair_value_gaps_detailed(df)


@pytest.mark.parametrize("bad", [None, pd.DataFrame({"Low": [1.0, 2.0, 3.0]})])
def test_the_helper_raises_where_the_live_detector_swallows(bad):
    with pytest.raises(Exception):
        fvg.scan_fair_value_gaps(bad)
    assert fvg.find_fair_value_gaps_detailed(bad) == []


def test_the_live_detector_swallows_whatever_the_helper_raises(monkeypatch):
    def boom(*_args, **_kwargs):
        raise RuntimeError("scan failed")

    monkeypatch.setattr(fvg, "scan_fair_value_gaps", boom)
    assert fvg.find_fair_value_gaps_detailed(witness_frame(seed=126)) == []


def test_the_live_wrapper_callers_are_unchanged():
    df = gap_frame(FLAT, BEAR_THIRD)
    assert fvg.find_fair_value_gaps(df) == [(98.75, "FVG (bearish)")]

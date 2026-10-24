"""v182 partner rule: every long result stays byte-identical. The golden was
captured in V182-1 on engine code identical to main; never regenerate it to
make this pass."""
import json

import pytest

from tests.backtesting.screen import long_golden


@pytest.fixture(scope="module")
def payload():
    return long_golden.capture()


@pytest.fixture(scope="module")
def golden():
    return json.loads(long_golden.GOLDEN_PATH.read_text(encoding="utf-8"))


def test_every_long_output_is_byte_identical_to_the_golden(payload, golden):
    now = long_golden.digests(payload)
    assert set(now) == set(golden["digests"])
    changed = sorted(key for key in now if now[key] != golden["digests"][key])
    assert changed == []


def test_the_golden_is_not_vacuous(payload, golden):
    assert long_golden.counts(payload) == golden["counts"]
    assert all(n > 0 for n in golden["counts"].values())
    assert set(golden["counts"]) == set(long_golden.LONG_IDEAS) | {long_golden.TRAIL_VARIANT}


def test_the_fixture_frame_is_well_formed_and_deterministic():
    df = long_golden.fixture_frame(7, n=300)
    assert df.equals(long_golden.fixture_frame(7, n=300))
    assert (df["High"] >= df[["Open", "Close"]].max(axis=1)).all()
    assert (df["Low"] <= df[["Open", "Close"]].min(axis=1)).all()
    assert (df["Low"] > 0).all()


def test_the_capture_never_reads_the_growing_registry():
    assert long_golden.LONG_IDEAS == (
        "high52w", "uptrend_pullback", "gap_volume", "turn_of_month", "turtle_soup",
        "quiet_pullback", "bond_spike_rebound", "dollar_drop", "sweep_reclaim_bos")

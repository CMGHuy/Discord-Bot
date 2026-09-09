# tests/backtesting/test_v68_fixture_shape.py
"""The v68 fixture is this plan's regression anchor.

data/v68_validation_dcb.json was gitignored and is gone from this machine,
as is the .log its results doc cites. That is why the population is
regenerated and COMMITTED here: an instrument tested against a fixture
that can evaporate is not tested.
"""
import json
from pathlib import Path

FIXTURE = (Path(__file__).parent / "fixtures" / "v68_validation_arms.json")


def test_fixture_exists():
    assert FIXTURE.exists(), (
        "run: python scripts/backtest/make_v68_fixture.py")


def test_fixture_has_both_arms_and_provenance():
    blob = json.loads(FIXTURE.read_text())
    assert set(blob) == {"baseline", "component", "meta"}
    meta = blob["meta"]
    assert meta["cell"] == "d15_gN_voff"
    assert meta["window"] == ["2024-01-01", "2025-12-31"]
    assert meta["horizons"] == ["4w", "2m", "3m", "4m", "6m"]
    assert "generated_by" in meta


def test_arms_carry_every_field_the_clauses_read():
    blob = json.loads(FIXTURE.read_text())
    row = blob["baseline"][0]
    assert set(row) >= {"ticker", "strategy", "horizon_key", "entry_date",
                        "outcome", "r_multiple", "planned_rr"}


def test_component_is_a_subset_of_baseline():
    """The dcb veto only removes bullish scenarios; it changes no surviving
    outcome. Anything else would mean the regeneration diverged from what
    v68 actually measured."""
    blob = json.loads(FIXTURE.read_text())
    key = lambda r: (r["ticker"], r["strategy"], r["horizon_key"],
                     r["entry_date"])
    b = {key(r) for r in blob["baseline"]}
    c = {key(r) for r in blob["component"]}
    assert c < b


def test_arm_sizes_are_close_to_the_published_run():
    """v68's published VALIDATION numbers: baseline N=859, component N=844
    decided trades. The regeneration uses the same tickers, horizons, gates
    and window, so it must land near them -- a wide tolerance, because this
    asserts 'the same measurement', not bit-identity."""
    blob = json.loads(FIXTURE.read_text())
    decided = lambda arm: sum(1 for r in arm if r["outcome"] in ("win", "loss"))
    assert 800 <= decided(blob["baseline"]) <= 920
    assert 790 <= decided(blob["component"]) <= 905

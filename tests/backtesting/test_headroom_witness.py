"""v135 defaults-off witness: with both knobs at default, replay trades are byte-identical
to the trades captured before the veto existed, and the strategy engine builds exactly the
level maps it built before (spec: Testing -- Defaults-off witness)."""
import json
from pathlib import Path

import pytest

from swingbot import config
from swingbot.core.backtesting.arms import strategy_engine
from swingbot.core.backtesting.arms.engine import run_arm
from tests.backtesting.test_v74_fixture import load_v74_fixture

WITNESS = Path(__file__).resolve().parent.parent / "fixtures" / "v135" / "defaults_off_witness.json"
HORIZONS = ("4w", "3m")
WINDOW = ("1900-01-01", "2100-12-31")


def witness(delta=None) -> dict:
    """Replay rows plus the number of level maps the strategy engine built on its own."""
    builds = []
    original = strategy_engine.build_level_map

    def counting(*args, **kwargs):
        builds.append(1)
        return original(*args, **kwargs)

    strategy_engine.build_level_map = counting
    try:
        rows = []
        for ticker, frame in sorted(load_v74_fixture().items()):
            for trade in run_arm(ticker, frame, ("confluence", "strategy"), HORIZONS, WINDOW,
                                 delta or {}):
                r_multiple = None if trade.r_multiple is None else round(trade.r_multiple, 6)
                planned_rr = None if trade.planned_rr is None else round(trade.planned_rr, 9)
                rows.append([list(trade.key), trade.outcome, r_multiple, planned_rr])
    finally:
        strategy_engine.build_level_map = original
    return {"rows": sorted(rows, key=repr), "strategy_level_map_builds": len(builds)}


@pytest.mark.slow
def test_defaults_off_replay_matches_the_pre_gate_witness():
    assert config.HEADROOM_SCOPE == "off"
    assert config.HEADROOM_MIN_R == 0.0
    current = json.loads(json.dumps(witness()))
    assert current["rows"], "fixture must produce trades or the witness proves nothing"
    assert current["strategy_level_map_builds"] > 0, "fixture must exercise the TP2 map build"
    stored = json.loads(WITNESS.read_text(encoding="utf-8"))
    # planned_rr carries ~1e-14 platform float noise; it is compared at 9 decimals.
    for row in stored["rows"]:
        row[3] = None if row[3] is None else round(row[3], 9)
    assert current == stored

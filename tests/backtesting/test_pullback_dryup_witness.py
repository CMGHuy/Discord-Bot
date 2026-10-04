"""v122 defaults-off witness captured before the replay call sites change."""

import json
from pathlib import Path

import pytest

from swingbot import config
from swingbot.core.backtesting.arms.engine import run_arm
from tests.backtesting.test_v74_fixture import load_v74_fixture


WITNESS = Path(__file__).resolve().parent.parent / "fixtures" / "v122" / "defaults_off_witness.json"
HORIZONS = ("4w", "3m")
WINDOW = ("1900-01-01", "2100-12-31")


def witness_rows() -> list:
    rows = []
    for ticker, frame in sorted(load_v74_fixture().items()):
        for trade in run_arm(ticker, frame, ("confluence", "strategy"), HORIZONS, WINDOW, {}):
            r_multiple = None if trade.r_multiple is None else round(trade.r_multiple, 6)
            rows.append([list(trade.key), trade.outcome, r_multiple, trade.planned_rr])
    return sorted(rows, key=repr)


@pytest.mark.slow
def test_defaults_off_replay_matches_the_pre_gate_witness():
    assert config.PULLBACK_DRYUP_SCOPE == "off"
    assert config.PULLBACK_DRYUP_MAX_RATIO == 0.0
    current = json.loads(json.dumps(witness_rows()))
    assert current, "fixture must produce trades or the witness proves nothing"
    assert current == json.loads(WITNESS.read_text(encoding="utf-8"))

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


def pin_code_defaults(monkeypatch) -> None:
    """Set every config field to its code default for this test only.

    The witness was captured on code defaults. A developer's .env, or a
    variable inherited from the shell, can override a field such as
    MIN_STOP_DISTANCE_PCT and change which scenarios the replay admits.
    """
    for field in config.FIELDS:
        monkeypatch.setattr(config, field.attr, config._cast(field, field.default))


def witness_rows() -> list:
    rows = []
    for ticker, frame in sorted(load_v74_fixture().items()):
        for trade in run_arm(ticker, frame, ("confluence", "strategy"), HORIZONS, WINDOW, {}):
            r_multiple = None if trade.r_multiple is None else round(trade.r_multiple, 6)
            rows.append([list(trade.key), trade.outcome, r_multiple, trade.planned_rr])
    return sorted(rows, key=repr)


def test_pin_code_defaults_overrides_an_environment_value(monkeypatch):
    field = next(f for f in config.FIELDS if f.attr == "MIN_STOP_DISTANCE_PCT")
    monkeypatch.setattr(config, "MIN_STOP_DISTANCE_PCT", 99.0)
    pin_code_defaults(monkeypatch)
    assert config.MIN_STOP_DISTANCE_PCT == config._cast(field, field.default)


@pytest.mark.slow
def test_defaults_off_replay_matches_the_pre_gate_witness(monkeypatch):
    pin_code_defaults(monkeypatch)
    assert config.PULLBACK_DRYUP_SCOPE == "off"
    assert config.PULLBACK_DRYUP_MAX_RATIO == 0.0
    current = json.loads(json.dumps(witness_rows()))
    assert current, "fixture must produce trades or the witness proves nothing"
    assert current == json.loads(WITNESS.read_text(encoding="utf-8"))

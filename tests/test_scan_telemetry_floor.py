"""Plan v8 Task V12: floor + reachability survival telemetry.

V12 Step 2 runs the screen log-only for a week to measure how many setups it
would remove. That measurement only exists if the counters are written while
the screen is NOT rejecting anything -- so the row must carry the reason
breakdown, not just a reject count that reads zero by construction.
"""
import json

import pytest

from swingbot import config
from swingbot.core.scanning import engine


class _Level:
    def __init__(self, price):
        self.price = price


def _scenario(direction="bullish", entry=100.0):
    import types
    return types.SimpleNamespace(direction=direction, entry=entry)


@pytest.fixture(autouse=True)
def floor_settings(monkeypatch):
    monkeypatch.setattr(config, "TARGET_FLOOR_ENABLED", True)
    monkeypatch.setattr(config, "MIN_TARGET_PCT", 2.5)


def test_reason_helper_classifies_each_case():
    walled = (([], [_Level(100.8)]))
    clear = (([], [_Level(103.0)]))
    assert engine._reachability_reason(_scenario(), walled) == "wall"
    assert engine._reachability_reason(_scenario(), clear) == "level_beyond_floor"
    assert engine._reachability_reason(_scenario(), ([], [])) == "no_levels"


def test_reason_helper_returns_none_without_a_level_map():
    assert engine._reachability_reason(_scenario(), None) is None


def test_reason_is_reported_even_while_the_floor_is_off(monkeypatch):
    """The whole point of the log-only week: the verdict is still computed
    and still says "wall" while nothing is being rejected."""
    monkeypatch.setattr(config, "TARGET_FLOOR_ENABLED", False)
    assert engine._reachability_reason(_scenario(), ([], [_Level(100.8)])) == "wall"


def test_telemetry_row_round_trips_the_new_keys(tmp_path):
    """log_scan_telemetry is a thin append -- what matters is that the keys
    survive to disk in the shape the weekly survival read expects."""
    path = str(tmp_path / "scan_telemetry.jsonl")
    engine.log_scan_telemetry({
        "duration_s": 12.3, "tickers": 83, "signals": 40, "alerts": 3,
        "target_floor_pct": 2.5, "target_floor_enforced": False,
        "rejected_unreachable": 0,
        "reachability_wall": 27, "reachability_clear": 11,
        "reachability_no_levels": 2,
    }, path=path)

    [row] = [json.loads(line) for line in open(path) if line.strip()]
    assert row["target_floor_enforced"] is False
    assert row["rejected_unreachable"] == 0        # nothing removed yet...
    assert row["reachability_wall"] == 27          # ...but 27 would have been
    assert row["reachability_clear"] + row["reachability_no_levels"] == 13
    assert "at" in row                             # timestamp still stamped


def test_survival_rate_is_computable_from_one_row(tmp_path):
    """The number V12 Step 2 exists to produce, and that risk #4 reads: what
    fraction of setups survive the floor. If it is so low that V36's forward
    gate cannot reach N, the plan drops the V14 tier floor rather than
    abandoning the gate -- so this has to be derivable from the log alone."""
    path = str(tmp_path / "t.jsonl")
    engine.log_scan_telemetry({
        "reachability_wall": 30, "reachability_clear": 15,
        "reachability_no_levels": 5,
    }, path=path)
    [row] = engine.recent_telemetry(10, path=path)
    judged = (row["reachability_wall"] + row["reachability_clear"]
              + row["reachability_no_levels"])
    survival = (judged - row["reachability_wall"]) / judged
    assert survival == pytest.approx(0.4)

"""v245 V245-1/V245-1b: `_scan_one` output pinned byte for byte (spec § Testing).

A golden failure after a v245 change is a behaviour change: stop and report,
never regenerate (index § Global Constraints)."""
from datetime import timezone

import numpy as np
import pandas as pd
import pytest

from swingbot import config
from swingbot.core.scanning import analyze
from tests.scanning.v245_golden_cases import (CASE_BY_NAME, CASES, GOLDEN_NOW, first_diff,
                                              frozen_clock, run_case, snapshot)


def test_clock_is_frozen_for_analyze(monkeypatch):
    frozen_clock(monkeypatch)
    assert analyze.datetime.now(timezone.utc) == GOLDEN_NOW
    assert analyze.datetime.now() == GOLDEN_NOW


def test_case_names_are_unique():
    assert len(CASE_BY_NAME) == len(CASES)


def test_forming_frame_is_the_completed_frame_plus_one_row():
    forming = CASE_BY_NAME["wave_forming"].frame()
    completed = CASE_BY_NAME["wave_completed"].frame()
    assert forming.index[-1].date().isoformat() == "2024-03-15"
    assert completed.index[-1].date().isoformat() == "2024-03-14"
    pd.testing.assert_frame_equal(forming.iloc[:-1], completed)
    assert len(CASE_BY_NAME["long_completed"].frame()) > 1500


def test_frames_are_rebuilt_per_call():
    case = CASE_BY_NAME["wave_completed"]
    first = case.frame()
    first.iloc[-1, 0] = -1.0
    assert case.frame().iloc[-1, 0] != -1.0


def test_run_case_is_deterministic(monkeypatch):
    frozen_clock(monkeypatch)
    case = CASE_BY_NAME["wave_forming"]
    assert run_case(case) == run_case(case)


def test_run_case_ignores_dotenv_tuning(monkeypatch):
    frozen_clock(monkeypatch)
    case = CASE_BY_NAME["wave_completed"]
    before = run_case(case)
    monkeypatch.setattr(config, "AVWAP_LEVELS_ENABLED", not config.AVWAP_LEVELS_ENABLED)
    assert run_case(case) == before


def test_no_frame_snapshot():
    doc = run_case(CASE_BY_NAME["no_frame"])
    assert doc["data_quality_failed"] is True
    assert doc["items"] == [] and doc["checked"] == 0


def test_snapshot_is_exact_and_json_shaped():
    stats = {"checked": 1, "no_entry_point": 0, "scenarios_found": 0, "fully_qualifying": 0,
             "mtf_misaligned": 0, "failed_counts": {"b": 1, "a": 2}, "conf_level_counts": {3: 1},
             "data_quality_failed": np.bool_(False), "funnel_events": [("bullish", "base", None, "s", "r")],
             "newly_closed": [], "near_close_warnings": [{}], "items": []}
    doc = snapshot(stats)
    assert list(doc["failed_counts"]) == ["a", "b"]
    assert doc["conf_level_counts"] == {"3": 1}
    assert doc["data_quality_failed"] is False
    assert doc["funnel_events"] == [["bullish", "base", None, "s", "r"]]
    assert doc["near_close_warnings"] == 1


def test_snapshot_rejects_types_without_an_exact_form():
    stats = dict.fromkeys(("checked", "no_entry_point", "scenarios_found", "fully_qualifying",
                           "mtf_misaligned", "failed_counts", "conf_level_counts",
                           "data_quality_failed"), 0)
    stats.update(funnel_events=[object()], newly_closed=[], near_close_warnings=[], items=[])
    with pytest.raises(TypeError):
        snapshot(stats)


def test_first_diff_names_the_path():
    assert first_diff({"a": [1, 2]}, {"a": [1, 2]}) is None
    assert first_diff({"a": [1, 2]}, {"a": [1, 3]}) == "$.a[1]: 2 != 3"
    assert first_diff({"a": 1}, {"b": 1}) == "$.a: present on one side only"
    assert first_diff([1], [1, 2]) == "$: length 1 != 2"

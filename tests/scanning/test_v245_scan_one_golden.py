"""v245 V245-1/V245-1b: `_scan_one` output pinned byte for byte (spec § Testing).

A golden failure after a v245 change is a behaviour change: stop and report,
never regenerate (index § Global Constraints)."""
import os
from datetime import timezone

import numpy as np
import pandas as pd
import pytest

from swingbot import config
from swingbot.core.scanning import analyze
from tests.scanning.v245_golden_cases import (CASE_BY_NAME, CASES, GOLDEN_NOW, GOLDEN_PATH,
                                              REGEN_ENV, first_diff, frozen_clock, load_golden,
                                              run_case, snapshot, write_golden)

REGEN = os.environ.get(REGEN_ENV) == "1"
LONG_HORIZONS = {"4m", "5m", "6m", "7m", "8m", "9m"}


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


@pytest.mark.skipif(not REGEN, reason=f"set {REGEN_ENV}=1 to rewrite the golden")
def test_regenerate_golden(monkeypatch):
    frozen_clock(monkeypatch)
    write_golden({case.name: run_case(case) for case in CASES})


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.name)
def test_scan_one_matches_golden(case, monkeypatch):
    frozen_clock(monkeypatch)
    golden = load_golden()
    assert case.name in golden, f"{case.name} missing from {GOLDEN_PATH.name}"
    got = run_case(case)
    assert got == golden[case.name], first_diff(got, golden[case.name])


def test_golden_holds_exactly_the_cases():
    assert sorted(load_golden()) == sorted(case.name for case in CASES)


def test_golden_exercises_the_analysis():
    """The fixture frames reach every stage the v245 refactors touch."""
    golden = load_golden()
    items = [item for doc in golden.values() for item in doc["items"]]
    assert len(items) >= 10
    assert {item["plan"]["direction"] for item in items} == {"bullish", "bearish"}
    assert {item["all_requirements_met"] for item in items} == {True, False}
    assert len({item["result"]["horizon_key"] for item in items}) >= 3
    assert any(item["trendline_candidates"] for item in items), "custom trendline scanner never fired"
    assert any(item["level_map"] for item in items), "no fully qualifying item staged a level map"
    assert golden["long_completed"]["checked"] == 10
    short = {item["result"]["horizon_key"] for item in golden["short_history_completed"]["items"]}
    assert not short & LONG_HORIZONS
    assert golden["short_history_completed"]["checked"] <= 4

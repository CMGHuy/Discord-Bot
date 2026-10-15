"""v147: the gate-counterfactual report file -- atomic, light to import, verdict of record frozen."""
from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from swingbot import config
from swingbot.core.infra import gate_counterfactual_store as store

REPO = Path(__file__).resolve().parents[2]
RECORD = {"verdict": "COSTS", "date": "2026-12-04", "n": 31}


def _cell(gate="risk_cap", population="live", *, verdict="INCONCLUSIVE", n=40, record=None):
    return {"gate": gate, "population": population, "verdict": verdict, "n": n,
            "verdict_of_record": record,
            "latest": {"difference": 0.12, "ci_low": -0.05, "ci_high": 0.3, "q": 0.4},
            "in_sample": False, "note": None}


def _result(*cells, generated_at="2026-12-04T21:00:00+00:00"):
    return {"generated_at": generated_at, "live_window": "2026-10-01..2026-12-04",
            "cells": list(cells), "rows": [{"gate": "risk_cap", "reason": "risk_cap", "population": "live",
                                            "over_cap": True, "in_sample": False}]}


@pytest.fixture
def path(tmp_path):
    return tmp_path / "reports" / "gate-counterfactual.json"


def test_the_default_path_is_under_data_reports_and_follows_data_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    assert store.report_path() == tmp_path / "reports" / "gate-counterfactual.json"


def test_load_is_none_before_the_first_run(path):
    assert store.load_report(path) is None


@pytest.mark.parametrize("content", ["", "{not json", "[1, 2]", "\"text\""])
def test_load_is_none_for_an_empty_corrupt_or_non_object_file(path, content):
    path.parent.mkdir(parents=True)
    path.write_text(content, encoding="utf-8")
    assert store.load_report(path) is None


def test_write_then_load_round_trips_and_is_json_serialisable(path):
    written = store.write_report(_result(_cell(record=RECORD)), path)
    loaded = store.load_report(path)
    assert loaded == written == _result(_cell(record=RECORD))
    json.dumps(loaded)


def test_the_write_is_atomic_and_leaves_no_temp_file(path):
    store.write_report(_result(_cell()), path)
    assert sorted(p.name for p in path.parent.iterdir()) == ["gate-counterfactual.json"]


def test_the_first_reading_seeds_the_record_and_later_readings_never_replace_it(path):
    store.write_report(_result(_cell(verdict="COSTS", n=31, record=RECORD)), path)
    later = _cell(verdict="INCONCLUSIVE", n=55, record={"verdict": "INCONCLUSIVE", "date": "2027-01-08", "n": 55})
    written = store.write_report(_result(later, generated_at="2027-01-08T21:00:00+00:00"), path)
    (cell,) = written["cells"]
    assert cell["verdict_of_record"] == RECORD                       # frozen at the first reading
    assert (cell["verdict"], cell["n"]) == ("INCONCLUSIVE", 55)      # the latest reading is descriptive
    assert written["generated_at"] == "2027-01-08T21:00:00+00:00"
    assert store.load_report(path) == written


@pytest.mark.parametrize("partial", [None, {"verdict": "COSTS", "date": None, "n": 31}, {"verdict": "COSTS"}])
def test_an_incomplete_record_on_disk_is_not_carried_forward(path, partial):
    store.write_report(_result(_cell(verdict="WAITING", n=12, record=partial)), path)
    written = store.write_report(_result(_cell(verdict="COSTS", n=31, record=RECORD)), path)
    assert written["cells"][0]["verdict_of_record"] == RECORD


def test_cells_are_matched_on_gate_and_population(path):
    store.write_report(_result(_cell("risk_cap", "live", record=RECORD)), path)
    written = store.write_report(_result(_cell("risk_cap", "train", record=None),
                                         _cell("compression", "live", record=None),
                                         _cell("risk_cap", "live", record=None)), path)
    records = {(c["gate"], c["population"]): c["verdict_of_record"] for c in written["cells"]}
    assert records == {("risk_cap", "train"): None, ("compression", "live"): None, ("risk_cap", "live"): RECORD}


def test_the_input_is_never_mutated(path):
    store.write_report(_result(_cell(record=RECORD)), path)
    fresh = _result(_cell(record=None))
    before = copy.deepcopy(fresh)
    store.write_report(fresh, path)
    assert fresh == before


def test_a_corrupt_file_on_disk_is_overwritten_with_the_new_reading(path):
    path.parent.mkdir(parents=True)
    path.write_text("{torn", encoding="utf-8")
    written = store.write_report(_result(_cell(record=None)), path)
    assert store.load_report(path) == written


@pytest.mark.parametrize("heavy", ["pandas", "numpy", "swingbot.core.backtesting"])
def test_loader_imports_without_heavy_modules(heavy):
    code = ("import sys\n"
            "from swingbot.core.infra.gate_counterfactual_store import load_report\n"
            f"loaded = sorted(m for m in sys.modules if m.startswith({heavy!r}))\n"
            "assert not loaded, loaded\n"
            "print('light')\n")
    done = subprocess.run([sys.executable, "-c", code], cwd=str(REPO), capture_output=True, text=True,
                          timeout=120)
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "light"

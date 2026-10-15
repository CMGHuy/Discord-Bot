"""v146: the Expectancy attribution report store -- atomic overwrite-latest
file, the verdict of record carried forward, and a loader cheap enough for
the v150 Reports page to import."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from swingbot import config
from swingbot.core.infra import expectancy_attribution_store as store
from swingbot.core.infra import jsonio

REPO = Path(__file__).resolve().parents[2]


def _result(verdict="WEAK", generated_at="2026-10-10T12:00:00+00:00",
            live_n=120, train_n=300, **over):
    result = {
        "generated_at": generated_at,
        "verdict": verdict,
        "looks": 41,
        "seed": 42,
        "provenance": {},
        "populations": {
            "live": {"n": live_n, "monotonicity": {"n": live_n}},
            "train": {"n": train_n, "monotonicity": {"n": train_n}},
        },
    }
    result.update(over)
    return result


def test_report_path_is_under_data_reports():
    assert store.REPORT_PATH == (Path(config.DATA_DIR) / "reports"
                                 / "expectancy-attribution.json")


def test_load_latest_returns_none_when_missing(tmp_path):
    assert store.load_latest(tmp_path / "absent.json") is None


def test_load_latest_returns_none_for_a_corrupt_file(tmp_path):
    path = tmp_path / "expectancy-attribution.json"
    path.write_text("{not json", encoding="utf-8")
    assert store.load_latest(path) is None


def test_load_latest_returns_none_for_a_non_object(tmp_path):
    path = tmp_path / "expectancy-attribution.json"
    path.write_text("[1, 2]", encoding="utf-8")
    assert store.load_latest(path) is None


def test_load_latest_defaults_to_report_path(tmp_path, monkeypatch):
    path = tmp_path / "reports" / "expectancy-attribution.json"
    monkeypatch.setattr(store, "REPORT_PATH", path)
    store.write_latest(_result())
    assert store.load_latest()["verdict"] == "WEAK"


def test_write_creates_the_reports_directory_and_round_trips(tmp_path):
    path = tmp_path / "reports" / "expectancy-attribution.json"
    written = store.write_latest(_result(), path)
    assert path.exists()
    assert store.load_latest(path) == written
    assert json.loads(path.read_text(encoding="utf-8")) == written


def test_first_write_derives_the_verdict_of_record_from_the_result(tmp_path):
    path = tmp_path / "expectancy-attribution.json"
    written = store.write_latest(_result(verdict="WEAK"), path)
    assert written["verdict_of_record"] == {"verdict": "WEAK",
                                            "date": "2026-10-10", "n": 420}
    assert written["looks"] == 41


def test_first_write_keeps_a_complete_record_the_result_carries(tmp_path):
    path = tmp_path / "expectancy-attribution.json"
    record = {"verdict": "NOT PREDICTIVE", "date": "2026-10-11", "n": 77}
    written = store.write_latest(_result(verdict_of_record=record), path)
    assert written["verdict_of_record"] == record


def test_later_write_carries_the_verdict_of_record_forward(tmp_path):
    path = tmp_path / "expectancy-attribution.json"
    store.write_latest(_result(verdict="WEAK"), path)
    later = _result(verdict="PREDICTIVE", generated_at="2026-12-01T09:00:00+00:00",
                    live_n=400,
                    verdict_of_record={"verdict": "PREDICTIVE",
                                       "date": "2026-12-01", "n": 700})
    written = store.write_latest(later, path)
    assert written["verdict_of_record"] == {"verdict": "WEAK",
                                            "date": "2026-10-10", "n": 420}
    assert written["verdict"] == "PREDICTIVE"   # the later run's reading, descriptive
    assert store.load_latest(path)["verdict_of_record"]["verdict"] == "WEAK"


def test_an_incomplete_record_on_disk_is_not_carried(tmp_path):
    path = tmp_path / "expectancy-attribution.json"
    jsonio.atomic_write_json(str(path), {"verdict_of_record": {"verdict": "WEAK"}})
    written = store.write_latest(_result(verdict="PREDICTIVE"), path)
    assert written["verdict_of_record"]["verdict"] == "PREDICTIVE"


def test_overwrite_latest_leaves_one_file_and_no_temp(tmp_path):
    path = tmp_path / "expectancy-attribution.json"
    store.write_latest(_result(), path)
    store.write_latest(_result(verdict="PREDICTIVE"), path)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["expectancy-attribution.json"]


def test_write_goes_through_the_atomic_writer(tmp_path, monkeypatch):
    calls = []
    real = jsonio.atomic_write_json

    def spy(path, obj):
        calls.append(path)
        real(path, obj)

    monkeypatch.setattr(jsonio, "atomic_write_json", spy)
    path = tmp_path / "expectancy-attribution.json"
    store.write_latest(_result(), path)
    assert calls == [str(path)]


def test_write_latest_does_not_mutate_its_input(tmp_path):
    result = _result()
    store.write_latest(result, tmp_path / "expectancy-attribution.json")
    assert "verdict_of_record" not in result


@pytest.mark.parametrize("heavy", ["pandas", "numpy", "swingbot.core.backtesting"])
def test_loader_imports_without_heavy_modules(heavy):
    code = ("import sys\n"
            "from swingbot.core.infra.expectancy_attribution_store import load_latest\n"
            f"loaded = sorted(m for m in sys.modules if m.startswith({heavy!r}))\n"
            "assert not loaded, loaded\n"
            "print('light')\n")
    done = subprocess.run([sys.executable, "-c", code], cwd=str(REPO),
                          capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "light"

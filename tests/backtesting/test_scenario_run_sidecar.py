"""v226 V226-3: the run sidecar <trades_jsonl>.run.json -- git HEAD, window,
universe (watchlist + membership as-of), command line and the three stop
settings, beside the store provenance sidecar."""
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from swingbot import config

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))

import run_backtest_range as rr  # noqa: E402


@pytest.fixture
def stops(monkeypatch):
    monkeypatch.setattr(config, "CLAMP_STOP_TO_HARD_CAP", True)
    monkeypatch.setattr(config, "MIN_STOP_DISTANCE_PCT", 1.75)
    monkeypatch.setattr(config, "MAX_STOP_LOSS_PCT", 2.0)


def _sidecar(**over):
    kwargs = dict(date_from="2020-01-06", date_to="2023-12-29", tickers=["MSFT", "AAPL"],
                  universe=None, membership=None,
                  argv=["--scenarios", "--train", "--trades-jsonl", "rows.jsonl"],
                  today="2026-11-12")
    kwargs.update(over)
    return rr.run_sidecar(**kwargs)


def test_the_sidecar_carries_exactly_its_six_fields_in_order(monkeypatch, stops):
    monkeypatch.setattr(rr, "_git_head", lambda: "a" * 40)

    sidecar = _sidecar()

    assert tuple(sidecar) == rr.RUN_SIDECAR_KEYS == (
        "git_head", "window", "watchlist", "membership_asof", "command", "stop_settings")
    assert sidecar == {
        "git_head": "a" * 40,
        "window": {"from": "2020-01-06", "to": "2023-12-29"},
        "watchlist": {"universe": "watchlist", "tickers": ["AAPL", "MSFT"]},
        "membership_asof": "2026-11-12",
        "command": ["--scenarios", "--train", "--trades-jsonl", "rows.jsonl"],
        "stop_settings": {"CLAMP_STOP_TO_HARD_CAP": True, "MIN_STOP_DISTANCE_PCT": 1.75,
                          "MAX_STOP_LOSS_PCT": 2.0},
    }
    json.dumps(sidecar)          # serialisable as written


def test_a_named_universe_and_a_pit_map_are_recorded(monkeypatch, stops):
    monkeypatch.setattr(rr, "_git_head", lambda: None)
    membership = {"AAA": [("2019-01-01", "2021-06-30"), ("2022-01-03", None)],
                  "BBB": [], "CCC": [["2018-05-01", "2020-02-01"]]}

    sidecar = _sidecar(universe="sp500_pit", membership=membership)

    assert sidecar["git_head"] is None
    assert sidecar["watchlist"]["universe"] == "sp500_pit"
    assert sidecar["membership_asof"] == "2022-01-03"


@pytest.mark.parametrize("membership", [None, {}, {"AAA": []}, {"AAA": [(None, None)]}])
def test_membership_asof_falls_back_to_today(membership):
    assert rr._membership_asof(membership, "2026-11-12") == "2026-11-12"


def test_stop_settings_reads_config_at_call_time(monkeypatch, stops):
    first = rr.stop_settings()
    monkeypatch.setattr(config, "MIN_STOP_DISTANCE_PCT", 2.5)

    assert tuple(first) == rr.STOP_SETTING_NAMES
    assert rr.stop_settings()["MIN_STOP_DISTANCE_PCT"] == 2.5
    assert first["MIN_STOP_DISTANCE_PCT"] == 1.75


def test_write_run_sidecar_writes_beside_the_rows_and_round_trips(tmp_path, monkeypatch, stops):
    monkeypatch.setattr(rr, "_git_head", lambda: "b" * 40)
    target = tmp_path / "reports" / "rows.jsonl"            # the directory does not exist yet
    sidecar = _sidecar()

    path = rr.write_run_sidecar(target, sidecar)

    assert path == rr._run_sidecar_path(target) == Path(str(target) + ".run.json")
    assert path.read_text(encoding="utf-8") == json.dumps(sidecar, indent=1, sort_keys=True) + "\n"
    assert json.loads(path.read_text(encoding="utf-8")) == sidecar
    assert not target.exists()                              # the rows file is not touched


def test_git_head_reads_the_repository_head():
    head = rr._git_head()
    assert head is None or re.fullmatch(r"[0-9a-f]{40}", head)


def test_git_head_is_none_when_git_fails(monkeypatch):
    def boom(*args, **kwargs):
        raise OSError("git not found")

    monkeypatch.setattr(rr.subprocess, "run", boom)
    assert rr._git_head() is None

    def bad_exit(*args, **kwargs):
        raise subprocess.CalledProcessError(128, args[0])

    monkeypatch.setattr(rr.subprocess, "run", bad_exit)
    assert rr._git_head() is None

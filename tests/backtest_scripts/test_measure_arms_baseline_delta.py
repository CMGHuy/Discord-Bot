"""V192-14: measure_arms --baseline-knob -- the baseline arm runs under its own delta, the stamp
records it beside knob_delta (absent when empty, so every older stamp is unchanged), and the static
and population refusals run on it before any compute. validate_component's reachability stage
classifies it too."""
import dataclasses
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))
import measure_arms as ma  # noqa: E402

from swingbot import config  # noqa: E402
from swingbot.core.backtesting.arms import provenance as pv  # noqa: E402
from swingbot.core.backtesting.arms.engine import run_arm  # noqa: E402
from swingbot.core.backtesting.arms.windows import ALL_HORIZONS, StageSpec  # noqa: E402
from tests.backtesting.test_v74_fixture import load_v74_fixture  # noqa: E402

FIXTURE = load_v74_fixture()
PILOT = StageSpec("pilot", ("2024-01-01", "2025-12-31"), full_width=False)
NEXT_OPEN = {"MARKET_ENTRY_NEXT_OPEN": True}
VETO = {"MARKET_ENTRY_NEXT_OPEN": True, "GAP_RECLAIM_ATR": 0.25}


@pytest.fixture(autouse=True)
def _world(monkeypatch):
    from swingbot.core.marketdata import training_data
    monkeypatch.setattr(config, "TRAINING_DATA_SOURCE", "yfinance")   # v162: no store in tests
    training_data.reset()
    monkeypatch.setattr(ma, "load_frame", lambda ticker: FIXTURE.get(ticker))
    monkeypatch.setattr(ma, "cached_universe", lambda: ["AAPL"])
    yield
    training_data.reset()


def _stamp(**over):
    kw = dict(stage="pilot", signal_window=("2018-06-01", "2020-12-31"), universe=["AAPL"],
              horizons=ALL_HORIZONS, engines=("confluence", "strategy"), knob_delta=VETO,
              engine_hash_baseline="h", engine_hash_component="h", changed_outcomes=1)
    kw.update(over)
    return pv.build_stamp(**kw)


def test_the_stamp_has_no_baseline_key_when_the_delta_is_empty():
    assert "baseline_knob_delta" not in _stamp()
    assert "baseline_knob_delta" not in _stamp(baseline_knob_delta={})
    assert "baseline_knob_delta" not in _stamp(baseline_knob_delta=None)


def test_the_stamp_records_a_non_empty_baseline_delta_beside_knob_delta():
    stamp = _stamp(baseline_knob_delta=NEXT_OPEN)
    assert stamp["baseline_knob_delta"] == NEXT_OPEN and stamp["knob_delta"] == VETO


def _recording(monkeypatch):
    seen = []

    def fake_run_arm(ticker, frame, engine_ids, horizons, signal_window, delta):
        seen.append(dict(delta))
        return []
    monkeypatch.setattr(ma, "run_arm", fake_run_arm)
    return seen


def test_produce_runs_the_baseline_under_its_own_delta(monkeypatch):
    seen = _recording(monkeypatch)
    blob = ma.produce("pilot", VETO, baseline_delta=NEXT_OPEN, universe=["AAPL"], spec=PILOT,
                      horizons=("4w",), engines=("confluence",), workers=1)
    assert seen == [NEXT_OPEN, VETO]
    assert blob["provenance"]["baseline_knob_delta"] == NEXT_OPEN


def test_produce_without_a_baseline_delta_is_todays_empty_baseline(monkeypatch):
    seen = _recording(monkeypatch)
    blob = ma.produce("pilot", NEXT_OPEN, universe=["AAPL"], spec=PILOT,
                      horizons=("4w",), engines=("confluence",), workers=1)
    assert seen == [{}, NEXT_OPEN]
    assert "baseline_knob_delta" not in blob["provenance"]


def test_the_population_path_takes_the_baseline_delta_too(monkeypatch):
    seen = []
    monkeypatch.setattr(ma, "population_engine_for", lambda delta: "pop")
    monkeypatch.setattr(ma, "population_symbols", lambda: [])
    monkeypatch.setattr(ma, "_population_arm",
                        lambda engine_id, frames, universe, horizons, window, delta: seen.append(dict(delta)) or [])
    blob = ma.produce("pilot", VETO, baseline_delta=NEXT_OPEN, universe=["AAPL"], spec=PILOT,
                      horizons=("4w",), workers=1)
    assert seen == [NEXT_OPEN, VETO]
    assert blob["provenance"]["engines"] == ["pop"]


def test_the_baseline_rows_are_the_rows_of_its_delta():
    blob = ma.produce("pilot", VETO, baseline_delta=NEXT_OPEN, universe=["AAPL"], spec=PILOT,
                      horizons=("4w",), engines=("confluence",), workers=1)
    direct = run_arm("AAPL", FIXTURE["AAPL"], ("confluence",), ("4w",), PILOT.signal_window, NEXT_OPEN)
    start, end = PILOT.signal_window
    assert blob["baseline"] == [dataclasses.asdict(t) for t in direct if start <= t.entry_date <= end]


def _main(tmp_path, *extra):
    return ma.main(["--knob", "MARKET_ENTRY_NEXT_OPEN=true", "--knob", "GAP_RECLAIM_ATR=0.25",
                    "--stage", "pilot", "--out", str(tmp_path / "arms.json"), "--workers", "1", *extra])


def test_main_passes_the_parsed_baseline_delta_to_produce(monkeypatch, tmp_path):
    captured = {}

    def fake_produce(stage, delta, **kw):
        captured.update(stage=stage, delta=delta, **kw)
        return {"provenance": {"changed_outcomes": 3}}
    monkeypatch.setattr(ma, "produce", fake_produce)
    monkeypatch.setattr(ma, "_write_sidecar_or_warn", lambda *a: None)
    monkeypatch.setattr(ma.training_data, "write_provenance", lambda out: None)
    assert _main(tmp_path, "--baseline-knob", "MARKET_ENTRY_NEXT_OPEN=true") == 0
    assert captured["delta"] == VETO and captured["baseline_delta"] == NEXT_OPEN


def test_main_without_the_flag_passes_an_empty_baseline_delta(monkeypatch, tmp_path):
    captured = {}
    monkeypatch.setattr(ma, "produce", lambda stage, delta, **kw: captured.update(kw) or
                        {"provenance": {"changed_outcomes": 3}})
    monkeypatch.setattr(ma, "_write_sidecar_or_warn", lambda *a: None)
    monkeypatch.setattr(ma.training_data, "write_provenance", lambda out: None)
    assert ma.main(["--knob", "MIN_REWARD_PCT=4", "--stage", "pilot",
                    "--out", str(tmp_path / "arms.json"), "--workers", "1"]) == 0
    assert captured["baseline_delta"] == {}


@pytest.mark.parametrize("knob,token", [
    ("STALL_EXIT_ENABLED=true", "refused:unreachable:journal_dependent"),
    ("LOG_LEVEL=DEBUG", "refused:unreachable:unclassified"),
    ("MIN_REWARD_PCT=abc", "refused:bad-knob"),
])
def test_a_bad_baseline_knob_is_refused_before_any_compute(monkeypatch, tmp_path, capsys, knob, token):
    monkeypatch.setattr(ma, "run_arm", lambda *a, **k: pytest.fail("computed"))
    assert _main(tmp_path, "--baseline-knob", knob) == 1
    assert token in capsys.readouterr().err
    assert not (tmp_path / "arms.json").exists()


def test_a_baseline_delta_routing_to_another_population_engine_is_refused(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(ma, "run_arm", lambda *a, **k: pytest.fail("computed"))
    monkeypatch.setattr(ma, "population_engine_for",
                        lambda delta: "pop" if "MIN_REWARD_PCT" in delta else None)
    monkeypatch.setattr(ma, "get_population_engine", lambda engine_id, **kw: object())
    assert _main(tmp_path, "--baseline-knob", "MIN_REWARD_PCT=4") == 1
    assert "refused:baseline-population-mismatch" in capsys.readouterr().err


def test_a_lone_gap_knob_in_the_baseline_trips_the_apply_knobs_guard(tmp_path):
    with pytest.raises(RuntimeError, match="needs MARKET_ENTRY_NEXT_OPEN on"):
        ma.main(["--knob", "MARKET_ENTRY_NEXT_OPEN=true", "--baseline-knob", "GAP_RECLAIM_ATR=0.25",
                 "--stage", "pilot", "--out", str(tmp_path / "arms.json"), "--workers", "1"])


# --- validate_component's reachability stage reads the baseline delta too -----------------------

def _vc_arms(tmp_path, baseline_delta):
    from tests.backtesting.test_validate_component_stamps import rows
    baseline, component = rows()
    stamp = _stamp(knob_delta={"MIN_REWARD_PCT": 4.0}, baseline_knob_delta=baseline_delta)
    path = tmp_path / "vc-arms.json"
    path.write_text(json.dumps({"provenance": stamp, "baseline": baseline, "component": component}),
                    encoding="utf-8")
    return path


def _reachability(path):
    from tests.backtesting.test_validate_component_stamps import vc
    return vc.main(["--stage", "reachability", "--arms", str(path), "--title", "t", "--window", "pilot"])


def test_reachability_prints_a_reachable_baseline_delta(tmp_path, capsys):
    assert _reachability(_vc_arms(tmp_path, NEXT_OPEN)) == 0
    out = capsys.readouterr().out
    assert "baseline knobs: {'MARKET_ENTRY_NEXT_OPEN': True}" in out and "REACHABLE" in out


def test_reachability_without_a_baseline_delta_prints_no_baseline_line(tmp_path, capsys):
    assert _reachability(_vc_arms(tmp_path, None)) == 0
    assert "baseline knobs:" not in capsys.readouterr().out


def test_reachability_refuses_an_unreachable_baseline_knob(tmp_path, capsys):
    assert _reachability(_vc_arms(tmp_path, {"STALL_EXIT_ENABLED": True})) == 1
    assert "refused:unreachable:journal_dependent" in capsys.readouterr().err

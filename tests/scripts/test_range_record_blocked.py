"""v147: `run_backtest_range.py --record-blocked` -- TRAIN-only, confluence scenarios only."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))
import run_backtest_range as rr  # noqa: E402

from swingbot import config  # noqa: E402
from swingbot.core.backtesting.blocked_recorder import gate_row  # noqa: E402
from swingbot.core.marketdata import training_data  # noqa: E402


@pytest.fixture(autouse=True)
def _legacy_source(monkeypatch):
    monkeypatch.setattr(config, "TRAINING_DATA_SOURCE", "yfinance")   # v162: no store in tests
    training_data.reset()
    yield
    training_data.reset()


def _main(monkeypatch, *argv):
    monkeypatch.setattr(sys, "argv", ["run_backtest_range.py", *argv])
    return rr.main()


@pytest.fixture
def replay_calls(monkeypatch):
    calls = []
    monkeypatch.setattr(rr, "run_scenario_mode", lambda *a, **k: calls.append((a, k)))
    return calls


@pytest.mark.parametrize("argv", [
    ("--validation", "--scenarios", "--scale-out"),
    ("--from", "2019-06-01", "--to", "2021-12-31", "--scenarios", "--scale-out"),
    ("--from", "2022-01-01", "--to", "2024-03-31", "--scenarios", "--scale-out"),
    ("--train", "--scale-out"),          # no --scenarios: compression rows come from measure_arms.py
    ("--train", "--scenarios"),          # no --scale-out: the counterfactual walk is scale_out=True
    ("--train", "--scenarios", "--scale-out", "--trades-jsonl", "rows-v146.jsonl"),   # exclusive with v146's rows
])
def test_record_blocked_refuses_before_any_replay(monkeypatch, replay_calls, tmp_path, argv):
    out = tmp_path / "rows.jsonl"
    with pytest.raises(SystemExit) as exc:
        _main(monkeypatch, *argv, "--record-blocked", str(out))
    assert exc.value.code == 2
    assert replay_calls == [] and not out.exists()


def test_train_scenarios_pass_the_path_to_scenario_mode(monkeypatch, replay_calls, tmp_path):
    out = tmp_path / "rows.jsonl"
    _main(monkeypatch, "--train", "--scenarios", "--scale-out", "--record-blocked", str(out))
    ((args, kwargs),) = replay_calls
    assert args[:2] == ("2020-01-01", "2023-12-31")
    assert kwargs["record_blocked"] == str(out) and kwargs["scale_out"] is True


def test_a_custom_train_slice_is_accepted(monkeypatch, replay_calls, tmp_path):
    _main(monkeypatch, "--from", "2021-01-01", "--to", "2021-06-30", "--scenarios", "--scale-out",
          "--record-blocked", str(tmp_path / "rows.jsonl"))
    assert len(replay_calls) == 1


def test_without_the_flag_nothing_is_refused_and_none_is_passed(monkeypatch, replay_calls):
    _main(monkeypatch, "--from", "2024-01-01", "--to", "2024-06-30", "--scenarios")
    assert replay_calls[0][1]["record_blocked"] is None


def test_write_blocked_writes_the_gate_rows_and_skips_without_a_path(tmp_path):
    row = gate_row(population="train", arm="blocked", source="confluence", ticker="AAPL",
                   strategy="S/R Confluence", horizon="4w", direction="bullish", signal_date="2021-03-01",
                   gate="plan_rejected", reason="no_qualifying_target", margin=None, cf_status="no-plan",
                   cf_r=None, win=None)
    out = tmp_path / "rows.jsonl"
    rr._write_blocked({"pooled": {}, "gate_rows": [row]}, str(out))
    assert [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()] == [row]
    rr._write_blocked({"pooled": {}}, None)                          # no flag: nothing to do, no error

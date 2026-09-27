import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))
import validate_component as vc  # noqa: E402
from swingbot.core.backtesting.arms.provenance import build_stamp  # noqa: E402
from swingbot.core.backtesting.arms.windows import ALL_HORIZONS  # noqa: E402

UNIVERSE = [f"T{k}" for k in range(25)]

def rows(drop_from=8, flip=False):
    baseline, component = [], []
    for ticker in range(25):
        for index in range(10):
            win = index < 4
            row = {"ticker": f"T{ticker}", "strategy": "MACD", "horizon_key": "3m", "entry_date": f"2019-03-{index + 1:02d}", "outcome": "win" if win else "loss", "r_multiple": 2.0 if win else -1.0, "planned_rr": 2.0, "source": "strategy", "direction": "bullish"}
            baseline.append(row)
            if index < drop_from: component.append(dict(row, outcome="win", r_multiple=2.0) if flip and index == 5 else row)
    return baseline, component

def write(tmp_path, stage, knobs, baseline, component, universe=UNIVERSE):
    window = ("2018-06-01", "2020-12-31") if stage == "pilot" else ("2018-06-01", "2022-12-31")
    stamp = build_stamp(stage=stage, signal_window=window, universe=universe, horizons=ALL_HORIZONS, engines=("strategy",), knob_delta=knobs, engine_hash_baseline="h", engine_hash_component="h", changed_outcomes=0)
    path = tmp_path / "arms.json"; path.write_text(json.dumps({"provenance": stamp, "baseline": baseline, "component": component})); return path

@pytest.fixture(autouse=True)
def universe(monkeypatch): monkeypatch.setattr(vc, "_full_universe", lambda: UNIVERSE)

def test_reachability_passes_a_reachable_knob_that_changed_trades(tmp_path, capsys):
    assert vc.main(["--stage", "reachability", "--arms", str(write(tmp_path, "pilot", {"MIN_REWARD_PCT": 4.0}, *rows())), "--title", "t", "--window", "pilot"]) == 0
    assert "REACHABLE" in capsys.readouterr().out

@pytest.mark.parametrize("knobs,stage,token", [({"RS_GATE": True}, "pilot", "refused:unreachable:live_scan_only"), ({"MIN_REWARD_PCT": 4.0}, "pilot", "refused:stage-mismatch")])
def test_refusals(tmp_path, capsys, knobs, stage, token):
    arms = write(tmp_path, stage, knobs, *rows())
    funnel_stage = "reachability" if token.startswith("refused:unreachable") else "mde"
    assert vc.main(["--stage", funnel_stage, "--arms", str(arms), "--title", "t", "--window", "w", "--train-effect-pp", "5"]) == 1
    assert token in capsys.readouterr().err

def test_unstamped_arms_are_refused_or_bespoke(tmp_path, capsys):
    baseline, component = rows(); path = tmp_path / "a.json"; path.write_text(json.dumps({"baseline": baseline, "component": component}))
    assert vc.main(["--stage", "mde", "--arms", str(path), "--title", "t", "--window", "w", "--train-effect-pp", "5"]) == 1
    assert "refused:unstamped" in capsys.readouterr().err
    vc.main(["--stage", "mde", "--arms", str(path), "--title", "t", "--window", "w", "--train-effect-pp", "5", "--bespoke-instrument", "reason"])
    assert "BESPOKE INSTRUMENT: reason" in capsys.readouterr().out

def test_mde_prints_paired_and_harvest(tmp_path, capsys):
    arms = write(tmp_path, "selection", {"MIN_REWARD_PCT": 4.0}, *rows(flip=True))
    vc.main(["--stage", "mde", "--arms", str(arms), "--title", "t", "--window", "w", "--train-effect-pp", "5", "--target-days", "730"])
    assert "paired MDE" in capsys.readouterr().out
    vc.main(["--stage", "mde", "--arms", str(arms), "--title", "t", "--window", "w", "--gate", "harvest", "--train-effect-r", "0.05"])
    assert "dExpR" in capsys.readouterr().out

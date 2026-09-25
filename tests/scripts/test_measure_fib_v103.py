"""v103 measurement funnel logic and refusal tests; no backtest calls."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from tests.helpers import make_ohlcv

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))
FAST = dict(n_resamples=400, seed=42)


def _module():
    import measure_fib_v103
    return measure_fib_v103


def _row(ticker, outcome, value, direction="bullish", year="2015"):
    return {"ticker": ticker, "horizon_key": "4w", "direction": direction,
            "entry_date": f"{year}-06-01", "outcome": outcome, "r_multiple": value}


def _tier2(direction="bullish"):
    return [row for index in range(10) for row in (
        [_row(f"T{index}", "win", 3.0, direction) for _ in range(2)]
        + [_row(f"T{index}", "loss", -1.0, direction) for _ in range(4)]
    )]


def test_mechanism_cell_sets_and_restores():
    module = _module()
    from swingbot import config
    from swingbot.core.market import entry_filters
    before = config.FIB_LEVEL_STOP_ATR, config.FIB_LEVEL_STOP_DIRECTIONS
    with module.mechanism_cell("A", 0.25):
        assert entry_filters._fib_level_stop_config() == (0.25, frozenset({"bullish", "bearish"}))
    with module.mechanism_cell("A", 0.0):
        assert entry_filters._fib_level_stop_config() == (0.0, frozenset())
    assert (config.FIB_LEVEL_STOP_ATR, config.FIB_LEVEL_STOP_DIRECTIONS) == before
    before = entry_filters.DEFAULT_PARAMS["Fibonacci Continuation"]["d_max"]
    with module.mechanism_cell("C", 0.786):
        assert entry_filters.DEFAULT_PARAMS["Fibonacci Continuation"]["d_max"] == 0.786
    assert entry_filters.DEFAULT_PARAMS["Fibonacci Continuation"]["d_max"] == before


def test_direction_gate_uses_live_or_unmasked_population():
    module = _module()
    with module.direction_gate("Fibonacci", "bullish"):
        assert module.STRATEGY_GATES["Fibonacci"]["directions"] == ("bullish",)
    with module.direction_gate("Fibonacci", "bearish"):
        assert set(module.STRATEGY_GATES["Fibonacci"]["directions"]) == {"bullish", "bearish"}
    with module.direction_gate("Fibonacci Continuation", "bullish"):
        assert set(module.STRATEGY_GATES["Fibonacci Continuation"]["directions"]) == {"bullish", "bearish"}
    assert module.STRATEGY_GATES["Fibonacci Continuation"] == {"directions": ()}


def test_collect_trades_applies_window_laggard_and_direction():
    module, frame, seen = _module(), make_ohlcv([100.0] * 300, start="2012-01-02"), []
    def run_fn(ticker, df, strategy, horizon, **kwargs):
        seen.append((strategy, tuple(module.STRATEGY_GATES[strategy]["directions"])))
        return NS(trades=[NS(direction="bullish", entry_date="2012-06-01", outcome="win", r_multiple=2.0, context={}), NS(direction="bullish", entry_date="2024-06-01", outcome="win", r_multiple=2.0, context={}), NS(direction="bearish", entry_date="2012-06-01", outcome="loss", r_multiple=-1.0, context={"rs_combined": 10.0}), NS(direction="bearish", entry_date="2012-06-01", outcome="win", r_multiple=2.0, context={"rs_combined": 80.0})])
    rows = module.collect_trades("C", {"AAA": frame}, {}, 0.618, module.TRAIN_EXT, horizons=("4w",), run_fn=run_fn, progress=NS(tick=lambda label: None))
    assert [(row["direction"], row["entry_date"]) for row in rows] == [("bullish", "2012-06-01"), ("bearish", "2012-06-01")]
    assert all(strategy == "Fibonacci Continuation" and set(directions) == {"bullish", "bearish"} for strategy, directions in seen)


def test_collect_trades_honors_an_explicit_direction():
    module, frame = _module(), make_ohlcv([100.0] * 300, start="2012-01-02")
    def run_fn(*args, **kwargs):
        return NS(trades=[NS(direction="bullish", entry_date="2012-06-01", outcome="win", r_multiple=2.0, context={}), NS(direction="bearish", entry_date="2012-06-01", outcome="loss", r_multiple=-1.0, context={"rs_combined": 10.0})])
    rows = module.collect_trades("C", {"AAA": frame}, {}, 0.618, module.TRAIN_EXT, directions=("bearish",), horizons=("4w",), run_fn=run_fn, progress=NS(tick=lambda label: None))
    assert {row["direction"] for row in rows} == {"bearish"}


def test_count_signals_totals_years_and_horizons(monkeypatch):
    module = _module()
    import pandas as pd
    monkeypatch.setattr(module, "entries_for", lambda strategy, df, horizon: (pd.Series(True, index=df.index), pd.Series(True, index=df.index)))
    frame = make_ohlcv([100.0] * 10, start="2012-12-27")
    cell = module.count_signals("C", {"AAA": frame}, (0.5,), horizons=("2w", "4w"))["0.5|bullish"]
    assert cell == {"total": 20, "by_year": {"2012": 6, "2013": 14}, "by_horizon": {"2w": 10, "4w": 10}}


def test_stage0_closes_only_below_the_loosest_cell_floor():
    assert _module().stage0_closures({"0.1|bullish": {"total": 30}, "0.1|bearish": {"total": 29}}, "A") == ["bearish"]


def test_evaluate_reports_closed_direction_and_a_baseline():
    module = _module()
    rows = {"0": _tier2(), "0.1": _tier2(), "0.25": _tier2(), "0.5": _tier2()}
    result = module.evaluate("A", rows, closed=("bearish",), **FAST)
    assert result["bearish"]["closed_at"] == "stage0"
    assert result["bullish"]["baseline"]["n"] == 60 and result["bullish"]["stage1"]["winner_tier"] == 2


def test_validation_verdict_uses_the_assigned_tier_only():
    module = _module()
    assert module.validation_verdict(_tier2(), 2, **FAST)["passes"] is True
    assert module.validation_verdict(_tier2(), 1, **FAST)["passes"] is False


def test_validation_refuses_a_second_shot(tmp_path):
    module, output = _module(), tmp_path / "validation.json"
    output.write_text("{}", encoding="utf-8")
    with pytest.raises(SystemExit):
        module.main(["validation", "--mechanism", "A", "--direction", "bullish", "--evaluate", "e.json", "--preregistration", "p.md", "--out", str(output)])


def test_require_committed_refuses_untracked_file(tmp_path):
    module = _module()
    path = tmp_path / "p.md"
    path.write_text("x", encoding="utf-8")
    with pytest.raises(SystemExit): module.require_committed(path)
    module.require_committed(ROOT / "bot.py")


def test_validation_refuses_nonproceeding_or_other_mechanism(monkeypatch, tmp_path):
    module = _module()
    monkeypatch.setattr(module, "require_committed", lambda path: None)
    evaluated = tmp_path / "e.json"
    evaluated.write_text(json.dumps({"mechanism": "A", "bullish": {"proceed_to_validation": False}}), encoding="utf-8")
    base = ["validation", "--direction", "bullish", "--evaluate", str(evaluated), "--preregistration", "p.md", "--out", str(tmp_path / "v.json")]
    with pytest.raises(SystemExit): module.main(base[:1] + ["--mechanism", "A"] + base[1:])
    with pytest.raises(SystemExit): module.main(base[:1] + ["--mechanism", "C"] + base[1:])


def test_emit_refuses_mixed_mechanisms_and_failures(tmp_path):
    module, registry = _module(), str(tmp_path / "registry.json")
    ok = {"mechanism": "A", "strategy": "Fibonacci", "verdict": {"passes": True, "tier": 2}, "rows": []}
    paths = []
    for name, payload in (("a", ok), ("c", {**ok, "mechanism": "C"}), ("f", {**ok, "verdict": {"passes": False, "tier": 2}})):
        path = tmp_path / f"{name}.json"; path.write_text(json.dumps(payload), encoding="utf-8"); paths.append(str(path))
    with pytest.raises(SystemExit): module.main(["emit-registry", "--validation-json", paths[0], paths[1], "--registry", registry, "--run-date", "2026-10-01"])
    with pytest.raises(SystemExit): module.main(["emit-registry", "--validation-json", paths[2], "--registry", registry, "--run-date", "2026-10-01"])


def test_registry_status_and_record():
    module = _module(); rows = [_row("A", "win", 2.0) for _ in range(10)] + [_row("A", "loss", -1.0) for _ in range(5)]
    assert module.registry_status([{"verdict": {"tier": 1}}], rows) == "VALIDATED"
    assert module.registry_status([{"verdict": {"tier": 1}}, {"verdict": {"tier": 2}}], rows) == "WEAK"
    record = module.registry_record("Fibonacci Continuation", rows, "WEAK", "2026-10-01")
    assert record["strategy"] == "Fibonacci Continuation" and record["horizon"] is None and record["n"] == 15

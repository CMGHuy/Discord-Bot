import importlib.util
import json
import pathlib

import pytest

spec = importlib.util.spec_from_file_location(
    "rbr", pathlib.Path(__file__).parent.parent / "scripts" / "backtest" / "run_backtest_range.py")
rbr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rbr)


def test_build_registry_records_status():
    summaries = [
        {"strategy": "Fibonacci", "n": 100, "win_rate": 82.0, "expectancy_r": 0.10},
        {"strategy": "RSI", "n": 100, "win_rate": 70.0, "expectancy_r": -0.01},
        {"strategy": "AtFloor", "n": 15, "win_rate": 70.0, "expectancy_r": 0.30},
    ]
    recs = rbr.build_registry_records(summaries, source="strategy",
                                      window="w", run_date="d")
    by = {r["strategy"]: r for r in recs}
    assert by["Fibonacci"]["status"] == "VALIDATED"
    assert by["RSI"]["status"] == "WEAK"
    # N exactly at the floor is evidence, but still WEAK on the win-rate gate.
    assert by["AtFloor"]["status"] == "WEAK"


def test_merge_registry_replaces_same_key(tmp_path):
    path = tmp_path / "reg.json"
    path.write_text(json.dumps([
        {"source": "strategy", "strategy": "RSI", "horizon": None, "status": "WEAK",
         "n": 1, "win_rate": 1.0, "expectancy_r": 0.0, "window": "old", "run_date": "old"},
        {"source": "confluence", "strategy": "ALL", "horizon": "4w", "status": "WEAK",
         "n": 2, "win_rate": 2.0, "expectancy_r": 0.0, "window": "keep", "run_date": "keep"},
    ]))
    merged = rbr.merge_registry(path, [
        {"source": "strategy", "strategy": "RSI", "horizon": None, "status": "VALIDATED",
         "n": 99, "win_rate": 85.0, "expectancy_r": 0.1, "window": "new", "run_date": "new"},
    ])
    assert len(merged) == 2
    rsi = next(r for r in merged if r["strategy"] == "RSI")
    assert rsi["status"] == "VALIDATED" and rsi["window"] == "new"
    assert any(r["window"] == "keep" for r in merged)


# --- Hard gates: an unhealthy run emits no row at all (v52) -------------------

HEALTHY = {"source": "strategy", "strategy": "RSI", "horizon": None, "n": 100,
           "win_rate": 70.0, "expectancy_r": 0.10,
           "window": "2024-01-01..2025-12-31", "run_date": "2026-08-22"}


def test_refusal_tokens_are_stable_literals():
    # Downstream tooling matches these without parsing prose -- assert exactly.
    assert rbr.REFUSAL_TOKENS == (
        "hard-gate:zero-trades",
        "hard-gate:below-min-n",
        "hard-gate:nonfinite-metric",
        "hard-gate:missing-window",
    )


def test_healthy_run_is_not_refused():
    assert rbr.registry_refusal(dict(HEALTHY)) is None


@pytest.mark.parametrize("patch,token", [
    ({"n": 0}, "hard-gate:zero-trades"),
    ({"n": None}, "hard-gate:zero-trades"),
    ({"n": 14}, "hard-gate:below-min-n"),
    ({"win_rate": float("nan")}, "hard-gate:nonfinite-metric"),
    ({"expectancy_r": float("inf")}, "hard-gate:nonfinite-metric"),
    ({"expectancy_r": None}, "hard-gate:nonfinite-metric"),
    ({"window": ""}, "hard-gate:missing-window"),
    ({"run_date": ""}, "hard-gate:missing-window"),
])
def test_each_gate_returns_its_token(patch, token):
    result = dict(HEALTHY)
    result.update(patch)
    assert rbr.registry_refusal(result) == token


def test_below_min_n_boundary_belongs_to_the_healthy_side():
    assert rbr.registry_refusal({**HEALTHY, "n": 15}) is None
    assert rbr.registry_refusal({**HEALTHY, "n": 14}) == "hard-gate:below-min-n"


def test_refused_row_is_dropped_entirely_not_partially(capsys):
    summaries = [
        {"strategy": "Healthy", "n": 100, "win_rate": 82.0, "expectancy_r": 0.10},
        {"strategy": "Empty", "n": 0, "win_rate": 0.0, "expectancy_r": 0.0},
    ]
    recs = rbr.build_registry_records(summaries, source="strategy",
                                      window="2024-01-01..2025-12-31",
                                      run_date="2026-08-22")
    assert [r["strategy"] for r in recs] == ["Healthy"]   # one bad cell, not the sweep


def test_refusal_token_is_printed_to_stderr(capsys):
    rbr.build_registry_records(
        [{"strategy": "Empty", "n": 0, "win_rate": 0.0, "expectancy_r": 0.0}],
        source="strategy", window="2024-01-01..2025-12-31", run_date="2026-08-22")
    err = capsys.readouterr().err
    assert "hard-gate:zero-trades" in err and "Empty" in err


def test_missing_window_refuses_even_a_large_healthy_looking_run():
    recs = rbr.build_registry_records(
        [{"strategy": "Undated", "n": 900, "win_rate": 85.0, "expectancy_r": 0.4}],
        source="strategy", window="2024-01-01..2025-12-31", run_date="")
    assert recs == []

import importlib.util
import json
import pathlib

spec = importlib.util.spec_from_file_location(
    "rbr", pathlib.Path(__file__).parent.parent / "scripts" / "run_backtest_range.py")
rbr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rbr)


def test_build_registry_records_status():
    summaries = [
        {"strategy": "Fibonacci", "n": 100, "win_rate": 82.0, "expectancy_r": 0.10},
        {"strategy": "RSI", "n": 100, "win_rate": 70.0, "expectancy_r": -0.01},
        {"strategy": "Tiny", "n": 5, "win_rate": 100.0, "expectancy_r": 0.30},
    ]
    recs = rbr.build_registry_records(summaries, source="strategy",
                                      window="w", run_date="d")
    by = {r["strategy"]: r for r in recs}
    assert by["Fibonacci"]["status"] == "VALIDATED"
    assert by["RSI"]["status"] == "WEAK"
    assert by["Tiny"]["status"] == "WEAK"  # N below floor never VALIDATED


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

import importlib.util
import json
import pathlib

spec = importlib.util.spec_from_file_location(
    "rbr", pathlib.Path(__file__).parent.parent / "scripts" / "run_backtest_range.py")
rbr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rbr)


def _s(strategy, n, win_rate, expectancy_r, excluded_share=0.0):
    return {"strategy": strategy, "n": n, "win_rate": win_rate,
            "expectancy_r": expectancy_r, "excluded_share": excluded_share}


def test_build_registry_records_status():
    recs = rbr.build_registry_records(
        [_s("Fibonacci", 100, 82.0, 0.10),
         _s("RSI", 100, 70.0, -0.01),
         _s("Tiny", 5, 100.0, 0.30)],
        source="strategy", window="w", run_date="d")
    by = {r["strategy"]: r for r in recs}
    assert by["Fibonacci"]["status"] == "VALIDATED"
    assert by["RSI"]["status"] == "WEAK"       # negative expectancy
    assert by["Tiny"]["status"] == "WEAK"      # N below floor never VALIDATED


# -- V25: the emitter scored against the gate V6 voided ----------------------
# V49 replaced `win_rate >= 80` with passes() and fixed the PASS/FAIL report
# column in five scripts, but build_registry_records kept a private copy of
# the old rule -- so the report and the registry disagreed inside one file,
# and the registry is the one the LIVE BOT reads (get_badge -> WEAK_CAUTION_TEXT
# and 20 points of quality score).

def test_a_profitable_strategy_below_80_wr_is_validated():
    """The regression. RSI Divergence in the committed registry: n=1099,
    WR 75.8%, ExpR +0.208 -- marked WEAK solely by the voided clause."""
    recs = rbr.build_registry_records([_s("RSI Divergence", 1099, 75.8, 0.208)],
                                      source="strategy", window="w", run_date="d")
    assert recs[0]["status"] == "VALIDATED"


def test_the_dead_trade_criterion_is_applied():
    """V6 Step 3's third clause. Positive expectancy and ample N are not
    enough if more than half the closed trades died flat."""
    ok = rbr.build_registry_records([_s("X", 100, 60.0, 0.2, excluded_share=0.5)],
                                    source="strategy", window="w", run_date="d")
    dead = rbr.build_registry_records([_s("X", 100, 60.0, 0.2, excluded_share=0.51)],
                                      source="strategy", window="w", run_date="d")
    assert ok[0]["status"] == "VALIDATED"
    assert dead[0]["status"] == "WEAK"


def test_a_summary_without_excluded_share_raises():
    """Silently defaulting it would apply two of V6's three criteria and call
    the result validated -- a partial gate that looks like a full one."""
    import pytest
    with pytest.raises(KeyError, match="excluded_share"):
        rbr.build_registry_records(
            [{"strategy": "X", "n": 100, "win_rate": 90.0, "expectancy_r": 0.2}],
            source="strategy", window="w", run_date="d")


def test_win_rate_is_recorded_but_never_gates():
    """WR is the ranking objective, not a threshold -- it must still land in
    the record so the registry stays readable."""
    recs = rbr.build_registry_records([_s("Low", 100, 12.0, 0.05)],
                                      source="strategy", window="w", run_date="d")
    assert recs[0]["win_rate"] == 12.0
    assert recs[0]["status"] == "VALIDATED"


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

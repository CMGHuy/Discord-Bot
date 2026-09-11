import json
import subprocess
import sys


def test_emits_both_arms(tmp_path):
    out = tmp_path / "arms.json"
    r = subprocess.run(
        [sys.executable, "scripts/backtest/measure_fib_extension.py",
         "--stage", "mde", "--tickers", "AAPL", "--out", str(out)],
        capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    arms = json.loads(out.read_text())
    assert set(arms) == {"baseline", "component"}
    assert arms["baseline"] and arms["component"]
    for t in arms["baseline"] + arms["component"]:
        assert set(t) >= {"ticker", "entry_date", "outcome", "r_multiple", "planned_rr"}
        assert t["outcome"] in {"win", "loss", "scratch", "timeout", "not_triggered"}

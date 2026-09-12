import json
import subprocess
import sys
from pathlib import Path

import pytest

# Same guard as tests/backtesting/test_sizing_parity.py and its siblings:
# this drives measure_fib_extension.py against the real (gitignored,
# network-fetched) OHLCV cache. Without the guard, a fresh checkout or
# worktree that has never run scripts/data/fetch_backtest_data.py fails hard
# here instead of skipping -- confirmed live (2026-09-11): AAPL's cache file
# was absent and the script legitimately returned empty "baseline"/"component"
# arms, which read as a real assertion failure rather than "no data yet".
CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "backtest_cache"

pytestmark = pytest.mark.skipif(
    not (CACHE_DIR / "AAPL.csv").exists(),
    reason="data/backtest_cache/AAPL.csv not present -- run scripts/data/fetch_backtest_data.py first",
)


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

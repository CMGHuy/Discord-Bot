"""tune_strategy.py's --json output flag."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import tune_strategy as ts  # noqa: E402


def test_tune_strategy_writes_json_output(tmp_path, monkeypatch):
    monkeypatch.setattr(ts, "load_watchlist", lambda: ["AAA"])
    monkeypatch.setattr(ts, "load_cached", lambda ticker: object())  # never read -- run_config is stubbed below
    monkeypatch.setattr(ts, "run_config", lambda strategy, dfs, exit_model="v1", scale_out=False: {
        "n_eval": 40, "win_rate": 82.0, "expectancy_r": 0.09, "excluded_share": 0.2,
    })
    out_path = tmp_path / "result.json"
    monkeypatch.setattr(sys, "argv", ["tune_strategy.py", "--strategy", "MACD", "--json", str(out_path)])
    ts.main()
    payload = json.loads(out_path.read_text())
    assert payload["strategy"] == "MACD"
    assert len(payload["grid"]) == 3  # MACD's PARAM_GRID has one key ("ext_atr"), 3 values
    assert payload["best"]["win_rate"] == 82.0

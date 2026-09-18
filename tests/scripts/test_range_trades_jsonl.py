import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))


def test_write_trades_jsonl_one_row_per_trade(tmp_path):
    import run_backtest_range as rr
    from swingbot.core.backtesting.backtest import BacktestTrade

    trade = BacktestTrade(entry_date="2021-03-01", exit_date="2021-03-05", direction="bullish", entry=100.0,
                          stop_loss=95.0, take_profit=110.0, outcome="win", exit_price=110.0, return_pct=10.0,
                          r_multiple=2.0, holding_days=4, context={"rsi_14": 40.0})
    output = tmp_path / "trades.jsonl"
    rr.write_trades_jsonl([("AAPL", "MACD", "3m", trade)], output)
    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert rows == [{"ticker": "AAPL", "strategy": "MACD", "horizon_key": "3m", "entry_date": "2021-03-01",
                     "exit_date": "2021-03-05", "direction": "bullish", "entry": 100.0, "stop_loss": 95.0,
                     "take_profit": 110.0, "outcome": "win", "exit_price": 110.0, "return_pct": 10.0,
                     "r_multiple": 2.0, "holding_days": 4, "runner_outcome": None,
                     "context": {"rsi_14": 40.0}}]

import json
import os

from swingbot.core.performance import TradeLog


def test_tradelog_writes_atomically_no_tmp_left_behind(tmp_path):
    path = str(tmp_path / "trades.json")
    log = TradeLog(path=path)
    log.log_trade(
        ticker="AAPL", strategy="Fibonacci", horizon_key="4w", direction="bullish",
        confidence_level=4, confidence_label="Strong", entry=100.0, stop_loss=95.0,
        take_profit=110.0,
    )
    assert os.path.exists(path)
    assert not os.path.exists(path + ".tmp")
    with open(path) as f:
        data = json.load(f)
    assert len(data) == 1 and data[0]["ticker"] == "AAPL"


def test_tradelog_recovers_from_corrupt_file(tmp_path):
    path = str(tmp_path / "trades.json")
    with open(path, "w") as f:
        f.write("{not valid json")
    log = TradeLog(path=path)
    # A corrupt file must never crash the bot on startup -- it starts
    # with an empty trade list instead of raising.
    assert log.get_trades(limit=None) == []

import json
import os

from swingbot.core.tracking.performance import TradeLog


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


def test_log_trade_persists_plan_pedigree(tmp_path):
    log = TradeLog(path=str(tmp_path / "trades.json"))
    trade_id = log.log_trade(
        ticker="AAPL", strategy="Fibonacci", horizon_key="4w", direction="bullish",
        confidence_level=4, confidence_label="Strong", entry=100.0, stop_loss=95.0,
        take_profit=110.0, plan_id="p1", badge="VALIDATED", quality_score=82,
        source="confluence",
    )
    log.refresh()
    t = log.get_trade_by_id(trade_id)
    assert t["plan_id"] == "p1"
    assert t["badge"] == "VALIDATED"
    assert t["quality_score"] == 82
    assert t["source"] == "confluence"


def test_log_trade_without_plan_metadata_defaults_to_none(tmp_path):
    log = TradeLog(path=str(tmp_path / "trades.json"))
    trade_id = log.log_trade(
        ticker="MSFT", strategy="EMA Crossover", horizon_key="2w", direction="bearish",
        confidence_level=3, confidence_label="Moderate", entry=50.0, stop_loss=52.0,
        take_profit=46.0,
    )
    t = log.get_trade_by_id(trade_id)
    assert t["plan_id"] is None and t["badge"] is None
    assert t["quality_score"] is None and t["source"] is None
    assert t["cohort_label"] is None
    assert t["cohort_stats"] == {}
    assert t["risk_features"] == {}


def test_log_trade_persists_v86_cohort_and_risk_features(tmp_path):
    log = TradeLog(path=str(tmp_path / "trades.json"))
    trade_id = log.log_trade(
        ticker="AAPL", strategy="Fibonacci", horizon_key="4w", direction="bullish",
        confidence_level=4, confidence_label="Strong", entry=100.0, stop_loss=95.0,
        take_profit=110.0, plan_id="p1", badge="VALIDATED", quality_score=82,
        source="confluence",
        cohort_label="COHORT_POOR",
        cohort_stats={"run_date": "2026-09-14", "expectancy_r": -0.38},
        risk_features={"regime2_state": "bear_volatile", "session_bucket": "close"},
    )
    log.refresh()
    t = log.get_trade_by_id(trade_id)
    assert t["cohort_label"] == "COHORT_POOR"
    assert t["cohort_stats"] == {"run_date": "2026-09-14", "expectancy_r": -0.38}
    assert t["risk_features"] == {"regime2_state": "bear_volatile", "session_bucket": "close"}

import json

from scripts.backtest.measure_strategy_arm import build_fold_arms, trade_to_arm
from swingbot.core.backtesting.backtest import BacktestSummary, BacktestTrade


def _summary(ticker, outcome, r, entry=100.0, sl=95.0, tp=110.0):
    t = BacktestTrade(entry_date="2021-03-01", exit_date="2021-04-01",
                      direction="long", entry=entry, stop_loss=sl,
                      take_profit=tp, outcome=outcome, exit_price=tp,
                      return_pct=1.0, r_multiple=r, holding_days=30)
    return BacktestSummary(ticker=ticker, strategy="RSI Divergence",
                           horizon_key="4w", total_signals=1, evaluated=1,
                           wins=1, losses=0, timeouts=0, scratches=0,
                           win_rate=100.0, avg_return_pct=1.0,
                           avg_r_multiple=r, expectancy_r=r,
                           max_drawdown_pct=-1.0, avg_holding_days=30.0,
                           trades=[t])


def test_trade_to_arm_carries_arm_fields_and_derives_planned_rr():
    s = _summary("AAPL", "win", 2.0)
    arm = trade_to_arm(s, s.trades[0])
    assert arm["ticker"] == "AAPL"
    assert arm["strategy"] == "RSI Divergence"
    assert arm["horizon_key"] == "4w"
    assert arm["entry_date"] == "2021-03-01"
    assert arm["outcome"] == "win"
    assert arm["r_multiple"] == 2.0
    # planned_rr = (tp - entry) / (entry - stop) = 10 / 5
    assert arm["planned_rr"] == 2.0


def test_short_planned_rr_is_direction_correct():
    s = _summary("AAPL", "loss", -1.0, entry=100.0, sl=105.0, tp=90.0)
    s.trades[0].direction = "short"
    arm = trade_to_arm(s, s.trades[0])
    assert arm["planned_rr"] == 2.0


def test_build_fold_arms_shape_is_validate_component_ready(monkeypatch):
    calls = []

    def fake_run(ticker, df, strategy, horizon_key, date_from, date_to, **kw):
        calls.append(date_from)
        return _summary(ticker, "win", 1.5)

    arms = build_fold_arms(
        strategy="RSI Divergence", overrides={"X": 1},
        symbols=["AAPL"], horizons=["4w"],
        frame_for=lambda s: object(), run_fn=fake_run)

    assert [f["test_year"] for f in arms["folds"]] == ["2021", "2022", "2023"]
    for fold in arms["folds"]:
        assert fold["baseline"] and fold["component"]
        assert set(fold["baseline"][0]) == {
            "ticker", "strategy", "horizon_key", "entry_date",
            "outcome", "r_multiple", "planned_rr"}
    # baseline + component leg per fold
    assert len(calls) == 6

import pytest

from swingbot.core.backtesting.arms.strategy_engine import StrategyEngine
from swingbot.core.backtesting.backtest import ALL_STRATEGIES, run_backtest
from swingbot.scan_params import ScanParams
from tests.backtesting.test_v74_fixture import load_v74_fixture

WINDOW = ("1900-01-01", "2100-12-31")
HORIZONS_UNDER_TEST = ("4w", "3m")


@pytest.fixture(scope="module")
def frame():
    return load_v74_fixture()["AAPL"]


@pytest.mark.slow
@pytest.mark.parametrize("horizon_key", HORIZONS_UNDER_TEST)
@pytest.mark.parametrize("strategy", ALL_STRATEGIES)
def test_parity_with_run_backtest(frame, strategy, horizon_key):
    ref = run_backtest("AAPL", frame, strategy, horizon_key, one_at_a_time=True,
                       exit_model="v2", scale_out=True, tp2_mode="levels", frictions=True)
    ours = list(StrategyEngine().iter_trades(
        "AAPL", frame, strategy, horizon_key, WINDOW, ScanParams.from_config()))
    assert [trade.entry_date for trade in ref.trades] == [date for date, _plan, _result in ours]
    for trade, (_date, plan, result) in zip(ref.trades, ours):
        assert round(plan.stop_loss, 4) == trade.stop_loss
        assert round(plan.tp1, 4) == trade.take_profit
        assert result.outcome == trade.outcome


def test_run_ticker_emits_keyed_strategy_trades(frame):
    trades = StrategyEngine(strategies=("MACD",)).run_ticker(
        "AAPL", frame, ("4w",), WINDOW, ScanParams.from_config())
    assert all(trade.source == "strategy" and trade.strategy == "MACD" for trade in trades)
    assert len({trade.key for trade in trades}) == len(trades)


def test_run_ticker_is_the_horizon_major_concatenation_of_iter_trades_for_strategy(frame):
    """v119 seam: run_ticker's rows, in order, are iter_trades_for_strategy per (horizon, strategy)."""
    strategies = ("Support/Resistance", "RSI Divergence", "Fibonacci")
    engine, params = StrategyEngine(strategies=strategies), ScanParams.from_config()
    expected = [trade for horizon in ("4w", "3m") for strategy in strategies
                for trade in engine.iter_trades_for_strategy("AAPL", frame, strategy, horizon, WINDOW, params)]
    assert engine.run_ticker("AAPL", frame, ("4w", "3m"), WINDOW, params) == expected
    assert expected


def test_signal_window_filters_but_dedup_state_survives(frame):
    engine, params = StrategyEngine(strategies=("MACD",)), ScanParams.from_config()
    full = engine.run_ticker("AAPL", frame, ("4w",), WINDOW, params)
    partial = engine.run_ticker("AAPL", frame, ("4w",), ("2025-01-01", "2100-12-31"), params)
    assert partial == [trade for trade in full if trade.entry_date >= "2025-01-01"]


def test_truncation_preserves_plans_at_prior_signal_bars(frame):
    """At bar i, plan construction may see only bars through i."""
    cutoff = frame.index[-60]
    engine, params = StrategyEngine(strategies=("MACD",)), ScanParams.from_config()
    full = list(engine.iter_trades("AAPL", frame, "MACD", "4w",
                                   ("1900-01-01", str(cutoff.date())), params))
    truncated = list(engine.iter_trades("AAPL", frame.loc[:cutoff], "MACD", "4w",
                                        WINDOW, params))
    assert [(date, plan.stop_loss, plan.tp1) for date, plan, _result in full] == [
        (date, plan.stop_loss, plan.tp1) for date, plan, _result in truncated]

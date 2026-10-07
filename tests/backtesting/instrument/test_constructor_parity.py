"""v136 section 3 / rule 3: under the v2 instrument the backtest's plan IS the live plan.

At sampled signal bars, backtest._live_plan_at (the v2 replay's only constructor
call) must equal what the live scan's strategy_pass.build_strategy_plan_at returns
for the same completed frame, on every constructor field, not only stop and target.
build_strategy_plan_at then adds issuance stamps (cohort, entry context, ledger);
those belong to the scan, which spec phase 5 replays, and are not compared here.
"""
import numpy as np
import pytest

from swingbot.core.backtesting import backtest as bt
from swingbot.core.backtesting.instrument.contract import resolve
from swingbot.core.scanning.strategy_pass import build_strategy_plan_at
from tests.backtesting.test_pullback_dryup_witness import pin_code_defaults
from tests.fixtures.ohlcv_parity import PARITY_CASES, load_ohlcv

CONSTRUCTOR_FIELDS = (
    "ticker", "created_at", "source", "strategy", "horizon_key", "direction",
    "entry_type", "trigger_price", "entry_price", "expiry_bars", "stop_loss", "tp1",
    "tp1_fraction", "tp2", "breakeven_trigger_fraction", "trail_atr_mult",
    "hold_cap_bars", "stop_mult_applied", "tp2_r_applied", "time_stop_days",
    "stall_exit_day", "badge", "badge_stats", "status",
)
SAMPLES_PER_CASE = 12


def _first_case_per_strategy():
    cases = {}
    for case in PARITY_CASES:
        cases.setdefault(case[1], case)
    return list(cases.values())


CASES = _first_case_per_strategy()


def _fields(plan):
    return {name: getattr(plan, name) for name in CONSTRUCTOR_FIELDS}


def _live(df, i, ticker, strategy, horizon, direction):
    return build_strategy_plan_at(df.iloc[:i + 1], ticker=ticker, strategy=strategy,
                                  horizon_key=horizon, direction=direction, regime2_state=None)


def _sampled_signals(df, strategy, horizon):
    bullish, bearish = bt._signal_masks(df, strategy, horizon)
    bars = [int(i) for i in np.where(bullish.values | bearish.values)[0]
            if i >= bt.MIN_BARS[horizon]]
    step = max(1, len(bars) // SAMPLES_PER_CASE)
    return [(i, "bullish" if bullish.values[i] else "bearish") for i in bars[::step]]


def test_cases_cover_every_parity_strategy():
    assert {case[1] for case in CASES} == {case[1] for case in PARITY_CASES}


@pytest.mark.slow
@pytest.mark.parametrize(("ticker", "strategy", "horizon"), CASES)
def test_v2_replay_plan_equals_the_live_constructor_at_sampled_bars(monkeypatch, ticker,
                                                                     strategy, horizon):
    pin_code_defaults(monkeypatch)
    df = load_ohlcv(ticker)
    signals = _sampled_signals(df, strategy, horizon)
    assert signals, f"{ticker}/{strategy}/{horizon} has no signal bar on the fixture"
    built = 0
    for i, direction in signals:
        replay = bt._live_plan_at(df, i, ticker=ticker, strategy=strategy,
                                  horizon_key=horizon, direction=direction)
        live = _live(df, i, ticker, strategy, horizon, direction)
        assert (replay is None) == (live is None), (ticker, strategy, horizon, i)
        if replay is not None:
            assert _fields(replay) == _fields(live), (ticker, strategy, horizon, i)
            built += 1
    assert built, f"no sampled bar built a plan for {ticker}/{strategy}/{horizon}"


def test_run_backtest_v2_simulates_exactly_the_live_plans(monkeypatch):
    """End to end: every plan the v2 replay hands simulate_exit is the live plan
    at that bar (fields snapshotted before the simulator can touch the plan)."""
    pin_code_defaults(monkeypatch)
    ticker, strategy, horizon = "DOCU", "RSI", "4w"
    df = load_ohlcv(ticker)
    seen = []
    real = bt.simulate_exit

    def spy(frame, index, plan, **kwargs):
        seen.append((int(index), plan.direction, _fields(plan)))
        return real(frame, index, plan, **kwargs)

    monkeypatch.setattr(bt, "simulate_exit", spy)
    bt.run_backtest(ticker, df, strategy, horizon, one_at_a_time=False,
                    exit_model="v2", scale_out=True, instrument=resolve("v2"))
    assert seen
    for index, direction, fields in seen:
        live = _live(df, index, ticker, strategy, horizon, direction)
        assert live is not None and fields == _fields(live), index

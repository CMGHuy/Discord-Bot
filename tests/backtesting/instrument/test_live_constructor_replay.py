"""v137 IC3: under the v2 instrument run_backtest builds every plan through
builders.build_strategy_plan on the frame truncated at the signal bar; v1 is
unchanged (the golden)."""
import dataclasses

import pytest

from swingbot.core.backtesting import backtest as bt
from swingbot.core.backtesting.instrument.contract import resolve
from swingbot.core.planning import builders
from tests.backtesting.instrument.golden import golden_text, render_v1_golden
from tests.backtesting.test_pullback_dryup_witness import pin_code_defaults
from tests.fixtures.ohlcv_parity import load_ohlcv

TICKER, STRATEGY, HORIZON = "DOCU", "RSI", "4w"
V2_EXIT = {"exit_model": "v2", "scale_out": True}


@pytest.fixture
def frame():
    return load_ohlcv(TICKER)


def _run(frame, **kwargs):
    return bt.run_backtest(TICKER, frame, STRATEGY, HORIZON, **kwargs)


def _forbidden(*_args, **_kwargs):
    raise AssertionError("the v2 instrument must never reach the v1 plan path")


def test_v2_refuses_the_frozen_v1_exit_loop(frame):
    with pytest.raises(ValueError, match="exit_model='v2'"):
        _run(frame, exit_model="v1", instrument=resolve("v2"))


def test_v2_refuses_the_v1_tp2_knob(frame):
    with pytest.raises(ValueError, match="tp2_mode"):
        _run(frame, exit_model="v2", tp2_mode="levels", instrument=resolve("v2"))


@pytest.mark.parametrize("flag", bt._LIVE_STATE_FLAGS)
def test_v2_refuses_a_flag_that_reads_live_state(monkeypatch, frame, flag):
    """DATA_DRIVEN_STOPS_ENABLED and STALL_EXIT_ENABLED make the builder read the
    live journal. OPEX_CAUTION_ENABLED makes it read today's opex tier from the
    wall clock. Either is lookahead inside a historical replay."""
    from swingbot import config
    pin_code_defaults(monkeypatch)
    monkeypatch.setattr(config, flag, True)
    with pytest.raises(ValueError, match=rf"lookahead.*{flag}"):
        _run(frame, **V2_EXIT, instrument=resolve("v2"))


def test_the_live_state_guard_names_the_real_config_flags():
    from swingbot import config
    names = {field.attr for field in config.FIELDS}
    assert set(bt._LIVE_STATE_FLAGS) <= names
    assert bt._LIVE_STATE_FLAGS == ("DATA_DRIVEN_STOPS_ENABLED", "STALL_EXIT_ENABLED",
                                    "OPEX_CAUTION_ENABLED")


def test_v1_ignores_the_live_state_flags(monkeypatch, frame):
    """The guard applies only to v2. v1 never calls the builder, so the flags cannot reach it."""
    from swingbot import config
    pin_code_defaults(monkeypatch)
    for flag in bt._LIVE_STATE_FLAGS:
        monkeypatch.setattr(config, flag, True)
    _run(frame, **V2_EXIT, instrument=resolve("v1"))


def test_v2_builds_every_plan_on_the_frame_truncated_at_its_signal_bar(monkeypatch, frame):
    pin_code_defaults(monkeypatch)
    calls = []
    real = builders.build_strategy_plan

    def spy(df, index, **kwargs):
        calls.append((len(df), int(index)))
        return real(df, index, **kwargs)

    monkeypatch.setattr(builders, "build_strategy_plan", spy)
    monkeypatch.setattr(bt, "_trade_plan_at", _forbidden)
    summary = _run(frame, **V2_EXIT, instrument=resolve("v2"))
    assert summary.trades, "fixture case must trade under v2 or this proves nothing"
    assert calls and all(length == index + 1 for length, index in calls)
    assert len(calls) >= len(summary.trades)


def test_v2_trade_rows_carry_the_live_plans_levels(monkeypatch, frame):
    pin_code_defaults(monkeypatch)
    summary = _run(frame, **V2_EXIT, instrument=resolve("v2"))
    index_of = {str(day.date()): k for k, day in enumerate(frame.index)}
    assert summary.trades
    for trade in summary.trades:
        plan = bt._live_plan_at(frame, index_of[trade.entry_date], ticker=TICKER,
                                strategy=STRATEGY, horizon_key=HORIZON,
                                direction=trade.direction)
        assert (trade.entry, trade.stop_loss, trade.take_profit) == (
            round(plan.trigger_price, 4), round(plan.stop_loss, 4), round(plan.tp1, 4))


def test_v2_summary_is_built_by_the_shared_summariser(monkeypatch, frame):
    pin_code_defaults(monkeypatch)
    summary = _run(frame, **V2_EXIT, instrument=resolve("v2"))
    again = bt._summarize(TICKER, STRATEGY, HORIZON, summary.total_signals,
                          summary.trades, {"runner_tp2": summary.runner_tp2,
                                           "runner_trail": summary.runner_trail,
                                           "runner_be": summary.runner_be,
                                           "runner_timeout": summary.runner_timeout})
    # trades compared by identity: their context dicts can hold NaN, and NaN != NaN.
    assert again.trades is summary.trades
    assert dataclasses.replace(again, trades=[]) == dataclasses.replace(summary, trades=[])


def test_daterange_threads_the_instrument(monkeypatch, frame):
    pin_code_defaults(monkeypatch)
    seen = {}
    real = bt.run_backtest

    def spy(*args, **kwargs):
        seen.update(kwargs)
        return real(*args, **kwargs)

    monkeypatch.setattr(bt, "run_backtest", spy)
    spec = resolve("v2")
    bt.run_backtest_daterange(TICKER, frame, STRATEGY, HORIZON, "2020-01-01", "2023-12-31",
                              **V2_EXIT, instrument=spec)
    assert seen["instrument"] is spec


@pytest.mark.slow
def test_explicit_v1_instrument_reproduces_the_golden(monkeypatch):
    pin_code_defaults(monkeypatch)
    assert render_v1_golden(instrument=resolve("v1")) == golden_text()

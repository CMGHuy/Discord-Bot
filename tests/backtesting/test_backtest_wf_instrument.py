"""v157 FC8: backtest_wf takes an optional instrument. v1 (None or
resolve("v1")) keeps the exact E22 harness call; any other instrument runs
with its own fills and costs and the tp2_mode the live constructor requires.
The "friction-adjusted" label is gone: under exit_model="v2" the frictions
flag never booked a cost."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from swingbot.core.backtesting import backtest_wf as wf
from swingbot.core.backtesting.instrument.contract import resolve

ROOT = Path(__file__).resolve().parents[2]
V2 = resolve("v2")
V1_CALL = {"frictions": True, "exit_model": "v2", "scale_out": True, "tp2_mode": "levels"}
V2_CALL = {"exit_model": "v2", "scale_out": True, "tp2_mode": "none", "instrument": V2}
WINDOW = ("2021-01-01", "2021-12-31")
FOLD = ("2018-06-01", "2020-12-31", *WINDOW)


def _trade():
    return SimpleNamespace(r_multiple=0.5, exit_date="2021-03-05", entry_date="2021-03-01",
                           signal_date="2021-02-26", outcome="win", direction="bullish",
                           entry=100.0, stop_loss=95.0, take_profit=110.0)


@pytest.fixture
def calls(monkeypatch):
    seen = []

    def fake(sym, df, strat, hk, start, end, **kwargs):
        seen.append(kwargs)
        return SimpleNamespace(trades=[_trade()])

    monkeypatch.setattr("swingbot.core.backtesting.backtest.run_backtest_daterange", fake)
    monkeypatch.setattr(wf, "_symbols_for_folds", lambda: ["FAKE"])
    monkeypatch.setattr(wf, "_frame_for", lambda sym: object())
    monkeypatch.setattr("swingbot.core.marketdata.universe.liquidity_ok", lambda df: True)
    monkeypatch.setattr("swingbot.core.marketdata.universe.sector_map",
                        lambda universe: {"FAKE": "Tech"})
    return seen


@pytest.mark.parametrize("instrument", [None, resolve("v1")], ids=["default", "explicit_v1"])
def test_v1_exit_kwargs_are_the_e22_harness_call(instrument):
    assert wf._exit_kwargs(instrument) == V1_CALL


def test_v2_exit_kwargs_carry_the_instrument_and_no_frictions():
    assert wf._exit_kwargs(V2) == V2_CALL


def test_default_run_v1_call_is_unchanged(calls):
    out = wf._default_run(*WINDOW, {}, strategies=["RSI"], horizons=["4w"], tickers=["FAKE"])
    assert calls == [V1_CALL]
    assert out == {"expectancy_r": 0.5, "n": 1}


def test_default_run_threads_the_instrument(calls):
    wf._default_run(*WINDOW, {}, strategies=["RSI"], horizons=["4w"], tickers=["FAKE"],
                    instrument=V2)
    assert calls == [V2_CALL]


@pytest.mark.parametrize(("instrument", "expected"), [(None, V1_CALL), (V2, V2_CALL)],
                         ids=["v1", "v2"])
def test_run_folds_threads_the_instrument_into_both_legs(calls, instrument, expected):
    result = wf.run_folds({}, folds=(FOLD,), tickers=["FAKE"], instrument=instrument)
    assert len(result["folds"]) == 1
    assert calls and all(kwargs == expected for kwargs in calls)


@pytest.mark.parametrize(("instrument", "expected"), [(None, V1_CALL), (V2, V2_CALL)],
                         ids=["v1", "v2"])
def test_collect_portfolio_signals_threads_the_instrument(calls, instrument, expected):
    signals = wf.collect_portfolio_signals(*WINDOW, strategies=["RSI"], horizons=["4w"],
                                           instrument=instrument)
    assert calls == [expected]
    assert [s["date"] for s in signals] == ["2021-03-01"]    # the trade's entry (fill) date


@pytest.mark.parametrize("path", ["swingbot/core/backtesting/backtest_wf.py",
                                  "scripts/backtest/wf_components.py"])
def test_the_friction_adjusted_label_is_gone(path):
    assert "friction-adjusted" not in (ROOT / path).read_text(encoding="utf-8")

"""v226 V226-2: run_scenario_backtest's per-ticker result hook. Fires in
task order with (ticker, exits, rows) only when rows are collected, before
the progress callback for the same ticker, and leaves every stat unchanged."""
from types import SimpleNamespace

import numpy as np
import pytest

from swingbot import config
from swingbot.core.backtesting import backtest_scenarios as bs
from tests.helpers import make_ohlcv

GATES = {"min_reward_pct": 1.0, "min_stop_distance_pct": 0.5,
         "max_stop_distance_pct": 15.0, "min_risk_reward": 0.0,
         "min_confluence": 1, "cooldown_bars": 5}


def _exit(outcome, r_total=0.0, runner=None):
    return SimpleNamespace(outcome=outcome, runner_outcome=runner, r_total=r_total)


def _fake_rows_worker(monkeypatch):
    """Each ticker: one closed and one untriggered exit on 4w, one row per closed exit."""
    def fake_rows(args):
        ticker = args[0]
        r = 2.0 if ticker == "AAA" else -1.0
        exits = {"4w": [_exit("win" if r > 0 else "loss", r), _exit("not_triggered")]}
        return exits, [{"ticker": ticker, "r_total": r}], []

    monkeypatch.setattr(bs, "_replay_ticker_rows", fake_rows)


def test_the_hook_fires_in_task_order_with_ticker_exits_and_rows(monkeypatch):
    _fake_rows_worker(monkeypatch)
    calls = []
    frames = {"BBB": "frame-b", "AAA": "frame-a", "CCC": "frame-c"}

    out = bs.run_scenario_backtest(
        frames, None, None, gates=GATES, horizons=["4w"], workers=1, collect_rows=True,
        on_ticker_result=lambda ticker, exits, rows: calls.append((ticker, exits, rows)))

    assert [ticker for ticker, _, _ in calls] == list(frames)
    assert [rows for _, _, rows in calls] == [[row] for row in out["rows"]]
    assert all(list(exits) == ["4w"] and len(exits["4w"]) == 2 for _, exits, _ in calls)


def test_stats_and_rows_are_identical_with_and_without_the_hook(monkeypatch):
    _fake_rows_worker(monkeypatch)
    frames = {"AAA": "frame-a", "BBB": "frame-b"}
    kwargs = dict(gates=GATES, horizons=["4w"], workers=1, collect_rows=True)

    plain = bs.run_scenario_backtest(frames, None, None, **kwargs)
    hooked = bs.run_scenario_backtest(frames, None, None, on_ticker_result=lambda *a: None, **kwargs)

    assert hooked == plain


def test_the_hook_is_ignored_when_rows_are_not_collected(monkeypatch):
    monkeypatch.setattr(bs, "_replay_ticker_gate_rows", lambda args: ({"4w": []}, []))
    calls = []

    bs.run_scenario_backtest({"AAA": "frame-a"}, None, None, gates=GATES, horizons=["4w"],
                             workers=1, on_ticker_result=lambda *a: calls.append(a))

    assert calls == []


def test_on_result_fires_before_the_progress_callback_for_each_result():
    events = []

    out = bs._drain(iter(["r0", "r1"]), 2,
                    lambda done, total: events.append(("done", done, total)),
                    on_result=lambda index, result: events.append(("result", index, result)))

    assert out == ["r0", "r1"]
    assert events == [("result", 0, "r0"), ("done", 1, 2), ("result", 1, "r1"), ("done", 2, 2)]


def test_drain_without_on_result_keeps_its_old_behaviour():
    events = []

    assert bs._drain(iter([1, 2]), 2, lambda done, total: events.append((done, total))) == [1, 2]
    assert events == [(1, 2), (2, 2)]


@pytest.mark.slow
def test_the_pool_path_passes_task_indices_in_order():
    """Two processes; `abs` is a picklable builtin worker."""
    seen = []

    out = bs._run_replay_tasks(abs, [-1, -2, -3], 2,
                               on_result=lambda index, result: seen.append((index, result)))

    assert out == [1, 2, 3]
    assert seen == [(0, 1), (1, 2), (2, 3)]


def _structured_df(seed=7):
    """Trend up, then a 60-bar box (test_scenario_rows.py's fixture family)."""
    rng = np.random.RandomState(seed)
    trend = list(100 * np.cumprod(1 + rng.normal(0.002, 0.01, 120)))
    box = [trend[-1] * (1 + 0.05 * np.sin(i / 4)) for i in range(60)]
    return make_ohlcv(trend + box)


@pytest.mark.slow
def test_on_a_real_replay_the_hooked_rows_concatenate_to_the_collected_rows(monkeypatch):
    monkeypatch.setattr(config, "UNIFIED_CONFIDENCE", False)
    frames = {"AAPL": _structured_df(7), "MSFT": _structured_df(11)}
    spy = make_ohlcv([300.0 + 0.1 * k for k in range(500)], start="2023-01-02")
    calls = []

    out = bs.run_scenario_backtest(
        frames, None, None, gates=GATES, horizons=["4w"], workers=1, spy_df=spy,
        collect_rows=True, on_ticker_result=lambda t, exits, rows: calls.append((t, exits, rows)))

    assert [t for t, _, _ in calls] == ["AAPL", "MSFT"]
    assert [row for _, _, rows in calls for row in rows] == out["rows"]
    closed = [r for _, exits, _ in calls for r in exits["4w"] if r.outcome != "not_triggered"]
    assert len(closed) == len(out["rows"])
    assert bs._aggregate([r for _, exits, _ in calls for r in exits["4w"]]) == out["by_horizon"]["4w"]

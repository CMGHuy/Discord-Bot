"""v180 A2 (v119 amendment A2): the circular entry-shift null for an ADDITIVE arm.
permutation_test.arm_pair_permutation's removal-label null cannot model an arm that removes
nothing (its null equals the component for every shift, so p == 1.0). This replays only the
added strategy with bt.ENTRY_SHIFT rolled and keeps the real baseline fixed."""
import dataclasses
import runpy
from pathlib import Path

import numpy as np
import pytest

from swingbot import config
from swingbot.core.backtesting import backtest as bt
from swingbot.core.backtesting.acceptance import ArmTrade, delta_pooled_win_rate
from swingbot.core.backtesting.arms import shift_permutation as sp
from tests.backtesting.test_acceptance_pooled_wr import _arms, _trade

ROOT = Path(__file__).resolve().parents[3]
KEYS = {"observed", "p_value", "n", "n_valid", "seed", "shift_range", "added", "statistic"}


def _added(baseline, component):
    keys = {t.key for t in baseline}
    return [t for t in component if t.key not in keys]


def _no_edge_replay(added, calls=None):
    """Shift 0 reproduces the observed added rows; any other shift redraws their outcomes at
    the baseline's 40% win rate -- a trigger with no edge."""
    def replay(shift):
        if calls is not None:
            calls.append(shift)
        if shift == 0:
            return list(added)
        rng = np.random.default_rng(shift)
        return [dataclasses.replace(t, outcome="win" if rng.random() < 0.4 else "loss")
                for t in added]
    return replay


def test_additive_added_returns_the_added_rows():
    baseline, component = _arms(n_tickers=5)
    assert sp.additive_added(baseline, component) == component[50:]


def test_a_removal_or_a_changed_outcome_is_not_additive():
    baseline, component = _arms(n_tickers=5)
    with pytest.raises(sp.NotAdditive):
        sp.additive_added(baseline, component[1:])
    flipped = [dataclasses.replace(component[0], outcome="loss")] + component[1:]
    assert component[0].outcome == "win"
    with pytest.raises(sp.NotAdditive):
        sp.additive_added(baseline, flipped)


def test_a_real_effect_beats_the_shifted_null():
    baseline, component = _arms()
    out = sp.shift_permutation(baseline, component, _no_edge_replay(_added(baseline, component)),
                               delta_pooled_win_rate, n_perm=200, seed=42)
    assert set(out) == KEYS
    assert out["observed"] == pytest.approx(20.0) and out["p_value"] < 0.05
    assert (out["n"], out["n_valid"], out["seed"], out["added"]) == (200, 200, 42, 400)
    assert out["shift_range"] == [20, 200] and out["statistic"] == "delta_pooled_win_rate"


def test_a_trigger_with_no_edge_is_indistinguishable():
    baseline, component = _arms()
    added = _added(baseline, component)
    out = sp.shift_permutation(baseline, component, lambda shift: list(added),
                               delta_pooled_win_rate, n_perm=50)
    assert out["p_value"] == 1.0


def test_the_shift_draw_is_the_permutation_scripts():
    baseline, component = _arms(n_tickers=5)
    calls = []
    sp.shift_permutation(baseline, component, _no_edge_replay(_added(baseline, component), calls),
                         delta_pooled_win_rate, n_perm=50, seed=42)
    assert calls[0] == 0
    assert calls[1:] == [int(s) for s in np.random.default_rng(42).integers(20, 200, size=50)]
    script = runpy.run_path(str(ROOT / "scripts" / "backtest" / "permutation_test.py"))
    assert sp.SHIFT_RANGE == script["SHIFT_RANGE"]


def test_verify_zero_catches_a_replay_that_does_not_reproduce_the_arm():
    baseline, component = _arms(n_tickers=5)
    added = _added(baseline, component)
    broken = lambda shift: added[:-1] if shift == 0 else list(added)   # noqa: E731
    with pytest.raises(sp.ReplayMismatch):
        sp.shift_permutation(baseline, component, broken, delta_pooled_win_rate, n_perm=5)
    calls = []
    sp.shift_permutation(baseline, component, _no_edge_replay(added, calls),
                         delta_pooled_win_rate, n_perm=5, verify_zero=False)
    assert 0 not in calls and len(calls) == 5


def test_a_non_additive_arm_is_refused_before_any_replay():
    baseline, component = _arms(n_tickers=5)

    def never(_shift):
        raise AssertionError("replayed a non-additive arm")
    with pytest.raises(sp.NotAdditive):
        sp.shift_permutation(baseline, component[1:], never, delta_pooled_win_rate, n_perm=5)


def test_progress_reports_every_shift():
    baseline, component = _arms(n_tickers=5)
    seen = []
    sp.shift_permutation(baseline, component, _no_edge_replay(_added(baseline, component)),
                         delta_pooled_win_rate, n_perm=10,
                         progress=lambda done, total: seen.append((done, total)))
    assert seen == [(i, 10) for i in range(1, 11)]


class _FakeEngine:
    seen: list = []
    fail = False

    def __init__(self, strategies=None, instrument=None, **_kwargs):
        self.strategies, self.instrument = strategies, instrument

    def run_ticker(self, ticker, df, horizons, signal_window, params):
        if _FakeEngine.fail:
            raise RuntimeError("engine blew up")
        _FakeEngine.seen.append((ticker, self.strategies, tuple(horizons), tuple(signal_window),
                                 bt.ENTRY_SHIFT, config.STALL_EXIT_ENABLED, type(params).__name__))
        return [_trade(ticker, "Turtle Soup", "2w", 0, "win"),               # 2022-01-01
                ArmTrade(ticker, "Turtle Soup", "2w", "2021-12-31", "win", 2.0, 2.0,
                         "strategy", "bullish")]


@pytest.fixture
def fake_engine(monkeypatch):
    monkeypatch.setattr(sp, "StrategyEngine", _FakeEngine)
    monkeypatch.setattr(config, "STALL_EXIT_ENABLED", False, raising=False)
    _FakeEngine.seen, _FakeEngine.fail = [], False
    return _FakeEngine


def test_replay_runs_one_strategy_shifted_under_the_knobs(fake_engine):
    window = ("2022-01-01", "2022-12-31")
    replay = sp.strategy_shift_replay({"B": None, "A": None}, "Turtle Soup", ["2w"], window,
                                      {"STALL_EXIT_ENABLED": True})
    rows = replay(37)
    assert [r.ticker for r in rows] == ["A", "B"]
    assert all(window[0] <= r.entry_date <= window[1] for r in rows)
    assert [s[:6] for s in fake_engine.seen] == [
        (t, ("Turtle Soup",), ("2w",), window, 37, True) for t in ("A", "B")]
    assert fake_engine.seen[0][6] == "ScanParams"
    assert bt.ENTRY_SHIFT == 0 and config.STALL_EXIT_ENABLED is False


def test_replay_restores_entry_shift_after_an_error(fake_engine):
    fake_engine.fail = True
    replay = sp.strategy_shift_replay({"A": None}, "Turtle Soup", ["2w"],
                                      ("2022-01-01", "2022-12-31"), {"STALL_EXIT_ENABLED": True})
    with pytest.raises(RuntimeError):
        replay(55)
    assert bt.ENTRY_SHIFT == 0 and config.STALL_EXIT_ENABLED is False


def test_shift_zero_reproduces_the_real_engine():
    from swingbot.core.backtesting.arms.strategy_engine import StrategyEngine
    from swingbot.scan_params import ScanParams
    from tests.backtesting.screen.helpers import random_walk

    frames = {"RW": random_walk(700, seed=3, start="2019-01-02")}
    window = ("2020-01-01", "2021-06-30")
    expected = StrategyEngine(strategies=("RSI",)).run_ticker(
        "RW", frames["RW"], ("4w",), window, ScanParams.from_config())
    rows = sp.strategy_shift_replay(frames, "RSI", ("4w",), window, {})(0)
    assert rows == [t for t in expected if window[0] <= t.entry_date <= window[1]]

# tests/backtesting/arms/test_headroom_replay.py
"""v135 replay call sites: the same decision points as live. Strategy: after the plan is
built, on a level map built at the signal bar itself (never the engine's 5-bar TP2 bucket).
Confluence: on the lists the scenario came from."""
from types import SimpleNamespace

import pytest

from swingbot import config
from swingbot.core.backtesting.arms import strategy_engine
from swingbot.core.backtesting.arms.engine import run_arm
from swingbot.core.edge import gates
from swingbot.core.market.levels import Level
from tests.backtesting.test_v74_fixture import load_v74_fixture

WINDOW = ("1900-01-01", "2100-12-31")
STRATEGY_ON = {"HEADROOM_SCOPE": "strategy", "HEADROOM_MIN_R": 1.0}
CONFLUENCE_ON = {"HEADROOM_SCOPE": "confluence", "HEADROOM_MIN_R": 1.0}
INACTIVE = [{"HEADROOM_SCOPE": "off", "HEADROOM_MIN_R": 1.0},
            {"HEADROOM_SCOPE": "confluence", "HEADROOM_MIN_R": 0.0},
            {"HEADROOM_SCOPE": "strategy", "HEADROOM_MIN_R": 0.0}]
# The stub plan below is bullish, entry 100.0, stop 98.0 (risk 2.0).
BLOCKED_MAP = ([], [Level(101.0, ["EMA50", "Rolling S/R"])])    # 0.5R ahead: inside 0.75R
CLEAR_MAP = ([], [Level(120.0, ["EMA50", "Rolling S/R"])])      # 10R ahead


@pytest.fixture(scope="module")
def frame():
    return load_v74_fixture()["AAPL"]


def boom(*args, **kwargs):
    raise AssertionError("an inactive headroom veto must not read or build any level")


@pytest.fixture
def always(monkeypatch):
    monkeypatch.setattr(gates, "headroom_rejects", lambda *args: True)


def _map_builds(monkeypatch, frame, delta) -> int:
    calls = []
    original = strategy_engine.build_level_map
    monkeypatch.setattr(strategy_engine, "build_level_map",
                        lambda *args, **kwargs: calls.append(1) or original(*args, **kwargs))
    run_arm("AAPL", frame, ("strategy",), ("3m",), WINDOW, delta)
    monkeypatch.setattr(strategy_engine, "build_level_map", original)
    return len(calls)


@pytest.mark.parametrize("delta", INACTIVE)
def test_inactive_gate_never_computes_and_changes_nothing(frame, monkeypatch, delta):
    base = run_arm("AAPL", frame, ("confluence", "strategy"), ("4w",), WINDOW, {})
    assert base
    monkeypatch.setattr(gates, "nearest_blocker", boom)
    assert run_arm("AAPL", frame, ("confluence", "strategy"), ("4w",), WINDOW, delta) == base


def test_confluence_scope_removes_what_the_predicate_rejects(frame, always):
    assert run_arm("AAPL", frame, ("confluence",), ("4w",), WINDOW, {})
    assert run_arm("AAPL", frame, ("confluence",), ("4w",), WINDOW, CONFLUENCE_ON) == []


def test_strategy_scope_leaves_confluence_untouched(frame, monkeypatch):
    base = run_arm("AAPL", frame, ("confluence",), ("4w",), WINDOW, {})
    assert base
    monkeypatch.setattr(gates, "nearest_blocker", boom)
    assert run_arm("AAPL", frame, ("confluence",), ("4w",), WINDOW, STRATEGY_ON) == base


def test_confluence_scope_leaves_strategy_untouched(frame, monkeypatch):
    base = run_arm("AAPL", frame, ("strategy",), ("4w",), WINDOW, {})
    assert base
    monkeypatch.setattr(gates, "nearest_blocker", boom)
    assert run_arm("AAPL", frame, ("strategy",), ("4w",), WINDOW, CONFLUENCE_ON) == base


@pytest.mark.slow
@pytest.mark.parametrize("horizon", ["4w", "3m"])
def test_strategy_scope_gates_only_the_frozen_list(frame, always, horizon):
    base = run_arm("AAPL", frame, ("strategy",), (horizon,), WINDOW, {})
    assert any(trade.strategy in gates.HEADROOM_STRATEGIES for trade in base)
    gated = run_arm("AAPL", frame, ("strategy",), (horizon,), WINDOW, STRATEGY_ON)
    assert gated == [trade for trade in base if trade.strategy not in gates.HEADROOM_STRATEGIES]


@pytest.mark.slow
def test_an_inactive_gate_builds_no_extra_level_map(frame, monkeypatch):
    """Spec: with the gate off the strategy engine builds nothing it did not build before."""
    baseline = _map_builds(monkeypatch, frame, {})
    assert baseline > 0
    for delta in INACTIVE + [CONFLUENCE_ON]:
        assert _map_builds(monkeypatch, frame, delta) == baseline
    assert _map_builds(monkeypatch, frame, STRATEGY_ON) > baseline


def test_strategy_map_at_bar_t_ignores_every_later_bar(frame):
    """NO-LOOKAHEAD: truncating or rewriting the frame after t leaves the map at t unchanged."""
    t = 300
    full = strategy_engine.level_map_at(frame, t, "4w")
    assert full[0] or full[1], "fixture must yield levels or the test proves nothing"
    assert strategy_engine.level_map_at(frame.iloc[:t + 1], t, "4w") == full
    poisoned = frame.copy()
    poisoned.iloc[t + 1:] = poisoned.iloc[t + 1:] * 10.0
    assert strategy_engine.level_map_at(poisoned, t, "4w") == full


def _stub_plan():
    return SimpleNamespace(trigger_price=100.0, entry_price=None, stop_loss=98.0,
                           direction="bullish")


def _gated(frame, monkeypatch, strategy, *, bucket_map, signal_map, min_r=0.75):
    """Run _gated_plan the way iter_trades does: window = frame up to the signal bar.
    `bucket_map` is the engine's TP2 bucket argument; `signal_map` is what a map build at the
    signal bar returns. Returns (result, plan, maps the builder got, map builds asked for)."""
    monkeypatch.setattr(config, "HEADROOM_SCOPE", "strategy")
    monkeypatch.setattr(config, "HEADROOM_MIN_R", min_r)
    plan, built, asked = _stub_plan(), [], []
    monkeypatch.setattr(strategy_engine, "build_strategy_plan",
                        lambda *args, **kwargs: built.append(kwargs["level_map"]) or plan)
    monkeypatch.setattr(strategy_engine, "build_level_map",
                        lambda df, h, price: asked.append((len(df), price)) or signal_map)
    index = len(frame) - 10
    result = strategy_engine.StrategyEngine._gated_plan(
        frame.iloc[:index + 1], index, ticker="AAPL", strategy=strategy, horizon_key="4w",
        direction="bullish", level_map=bucket_map, params=None)
    return result, plan, built, asked, index


@pytest.mark.parametrize("strategy,blocked", [("Fibonacci", True), ("MACD", False)])
def test_gated_plan_vetoes_after_the_plan_is_built(frame, monkeypatch, strategy, blocked):
    result, plan, built, asked, _index = _gated(frame, monkeypatch, strategy,
                                                bucket_map=None, signal_map=BLOCKED_MAP)
    assert result is (None if blocked else plan)
    assert built == [None]                              # the builder's own argument is unchanged
    assert len(asked) == int(blocked)                   # an out-of-scope strategy builds no map


def test_the_veto_map_is_built_at_the_signal_bar(frame, monkeypatch):
    """The map is built on the frame truncated at the signal bar, split at that bar's close."""
    _result, _plan, _built, asked, index = _gated(frame, monkeypatch, "Fibonacci",
                                                  bucket_map=None, signal_map=CLEAR_MAP)
    assert asked == [(index + 1, float(frame["Close"].iloc[index]))]


def test_the_veto_never_reads_the_tp2_bucket_map(frame, monkeypatch):
    """Partner decision 2026-10-06. When the bucket lags, its map and the signal-bar map
    differ. The verdict must follow the signal-bar map in both directions, and the builder
    must still receive the bucket map untouched."""
    result, plan, built, _asked, _index = _gated(frame, monkeypatch, "Fibonacci",
                                                 bucket_map=BLOCKED_MAP, signal_map=CLEAR_MAP)
    assert result is plan and built == [BLOCKED_MAP]    # a stale blocker in the bucket is ignored
    result, plan, built, _asked, _index = _gated(frame, monkeypatch, "Fibonacci",
                                                 bucket_map=CLEAR_MAP, signal_map=BLOCKED_MAP)
    assert result is None and built == [CLEAR_MAP]      # a fresh blocker the bucket misses still vetoes


@pytest.mark.parametrize("scope,min_r", [("off", 0.75), ("confluence", 0.75), ("strategy", 0.0)])
def test_an_inactive_gated_plan_builds_no_map_and_returns_the_plan(frame, monkeypatch, scope, min_r):
    monkeypatch.setattr(config, "HEADROOM_SCOPE", scope)
    monkeypatch.setattr(config, "HEADROOM_MIN_R", min_r)
    sentinel = object()
    monkeypatch.setattr(strategy_engine, "build_strategy_plan", lambda *args, **kwargs: sentinel)
    monkeypatch.setattr(strategy_engine, "build_level_map", boom)
    result = strategy_engine.StrategyEngine._gated_plan(
        frame, len(frame) - 1, ticker="AAPL", strategy="Fibonacci", horizon_key="4w",
        direction="bullish", level_map=None, params=None)
    assert result is sentinel


def test_no_plan_means_no_map_build(frame, monkeypatch):
    monkeypatch.setattr(config, "HEADROOM_SCOPE", "strategy")
    monkeypatch.setattr(config, "HEADROOM_MIN_R", 0.75)
    monkeypatch.setattr(strategy_engine, "build_strategy_plan", lambda *args, **kwargs: None)
    monkeypatch.setattr(strategy_engine, "build_level_map", boom)
    assert strategy_engine.StrategyEngine._gated_plan(
        frame, len(frame) - 1, ticker="AAPL", strategy="Fibonacci", horizon_key="4w",
        direction="bullish", level_map=None, params=None) is None

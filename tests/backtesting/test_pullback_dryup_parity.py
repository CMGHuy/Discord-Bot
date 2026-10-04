"""Live and replay dry-up gates agree on completed bars for both entry sources."""

from datetime import datetime, timezone
from types import SimpleNamespace

import pandas as pd
import pytest

from swingbot import config
from swingbot.core.backtesting import backtest_scenarios
from swingbot.core.backtesting.arms import strategy_engine
from swingbot.core.edge import gates
from swingbot.core.scanning import analyze
from swingbot.core.scanning import strategy_pass as sp
from tests.edge.pullback_frames import IMPULSE_VOLUME, mirror, pullback_frame
from tests.scanning.test_strategy_pass_emit import _Log, _Store


BOUNDARY = [(0.75, True), (0.90, False)]


def _frame(direction):
    frame = pullback_frame(0.9 * IMPULSE_VOLUME)
    return frame if direction == "bullish" else mirror(frame)


def _knobs(monkeypatch, scope, max_ratio):
    monkeypatch.setattr(config, "PULLBACK_DRYUP_SCOPE", scope)
    monkeypatch.setattr(config, "PULLBACK_DRYUP_MAX_RATIO", max_ratio)


def _live_strategy_rejects(monkeypatch, frame, direction, strategy):
    built = []
    monkeypatch.setattr(sp, "build_strategy_plan_at", lambda *a, **k: built.append(1) or None)
    deps = sp._PassDeps(plan_store=_Store(), trade_log=_Log(), mode="shadow", live_allow=set(),
                        rs_combined_of=lambda ticker: None, asof_of=None)
    result = sp.PassResult()
    sp._emit_signal(result, frame, ticker="T", strategy=strategy, direction=direction,
                    horizon="4w", bar_date=frame.index[-1].date().isoformat(), regime=None, deps=deps)
    assert (result.pullback_volume == 1) == (not built)
    return result.pullback_volume == 1


def _replay_strategy_rejects(monkeypatch, frame, direction, strategy):
    monkeypatch.setattr(strategy_engine, "build_strategy_plan", lambda *a, **k: "plan")
    plan = strategy_engine.StrategyEngine._gated_plan(
        frame, len(frame) - 1, ticker="T", strategy=strategy, horizon_key="4w",
        direction=direction, level_map=None, params=None)
    return plan is None


@pytest.mark.parametrize("direction", ["bullish", "bearish"])
@pytest.mark.parametrize("max_ratio,rejects", BOUNDARY)
@pytest.mark.parametrize("strategy", ["Fibonacci", "MACD"])
def test_strategy_live_and_replay_agree(monkeypatch, direction, max_ratio, rejects, strategy):
    _knobs(monkeypatch, "strategy", max_ratio)
    frame = _frame(direction)
    live = _live_strategy_rejects(monkeypatch, frame, direction, strategy)
    replay = _replay_strategy_rejects(monkeypatch, frame, direction, strategy)
    assert live == replay == (rejects and strategy == "Fibonacci")


@pytest.mark.parametrize("direction", ["bullish", "bearish"])
@pytest.mark.parametrize("max_ratio,rejects", BOUNDARY)
def test_confluence_live_and_replay_agree(monkeypatch, direction, max_ratio, rejects):
    _knobs(monkeypatch, "confluence", max_ratio)
    frame, scenario = _frame(direction), SimpleNamespace(direction=direction)
    stats = {"failed_counts": {"pullback_volume": 0}}
    live = analyze._apply_pullback_dryup([scenario], frame, stats, "T", "4w") == []
    replay = backtest_scenarios._dryup_kept([scenario], frame) == []
    assert live == replay == rejects
    assert stats["failed_counts"]["pullback_volume"] == int(rejects)


def _with_forming_bar(frame, direction):
    """A high-volume unfinished bar that would reverse the completed-bar verdict."""
    nxt = frame.index[-1] + pd.offsets.BDay(1)
    last = float(frame["Close"].iloc[-1])
    close = last - 1.0 if direction == "bullish" else last + 1.0
    bar = pd.DataFrame({"Open": [last], "High": [max(last, close) + 0.5],
                        "Low": [min(last, close) - 0.5], "Close": [close],
                        "Volume": [10 * IMPULSE_VOLUME]}, index=[nxt])
    return pd.concat([frame, bar]), datetime(nxt.year, nxt.month, nxt.day, 16, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize("direction", ["bullish", "bearish"])
def test_forming_bar_never_reaches_the_predicate(monkeypatch, direction):
    completed = _frame(direction)
    raw, now = _with_forming_bar(completed, direction)
    assert gates.pullback_dryup_rejects(raw, direction, 0.90) is True
    _knobs(monkeypatch, "strategy", 0.90)
    live = _live_strategy_rejects(monkeypatch, sp.completed_frame(raw, now), direction, "Fibonacci")
    replay = _replay_strategy_rejects(monkeypatch, completed, direction, "Fibonacci")
    assert live is False and replay is False
    _knobs(monkeypatch, "confluence", 0.90)
    stats = {"failed_counts": {"pullback_volume": 0}}
    scenario = SimpleNamespace(direction=direction)
    assert analyze._apply_pullback_dryup([scenario], raw, stats, "T", "4w", now=now) == [scenario]
    assert backtest_scenarios._dryup_kept([scenario], completed) == [scenario]

# tests/backtesting/test_headroom_parity.py
"""v135 parity: one fixture through the live and the replay call site of each scope gives
the same accept/reject, for both directions and both sides of the boundary, including a
frame that carries today's forming bar (spec: Live / replay parity, Testing -- Parity)."""
from datetime import datetime, timezone
from types import SimpleNamespace

import pandas as pd
import pytest

from swingbot import config
from swingbot.core.backtesting import backtest_scenarios
from swingbot.core.backtesting.arms import strategy_engine
from swingbot.core.market.levels import build_level_map, strategy_family
from swingbot.core.market.strategy_types import HORIZONS
from swingbot.core.scanning import analyze
from swingbot.core.scanning import strategy_pass as sp
from tests.scanning.test_engine_v2_plans import _structured_df
from tests.scanning.test_strategy_pass_emit import _Log, _Store

FRAME = _structured_df()
CLOSE = float(FRAME["Close"].iloc[-1])
BLOCKER_R = 0.6                              # the fixture's nearest confirmed level sits 0.6R away
BOUNDARY = [(0.75, True), (0.5, False)]      # 0.6R is inside 0.75R and outside 0.5R


def _level_map():
    return build_level_map(FRAME, HORIZONS["4w"], CLOSE)


def _blocker(direction):
    supports, resistances = _level_map()
    side = resistances if direction == "bullish" else supports
    return next(level for level in side
                if len({strategy_family(source) for source in level.sources}) >= 2)


def _stop(direction):
    """A stop that puts the nearest confirmed opposing level exactly BLOCKER_R x risk away."""
    risk = abs(_blocker(direction).price - CLOSE) / BLOCKER_R
    return CLOSE - risk if direction == "bullish" else CLOSE + risk


def _plan(direction, strategy):
    return SimpleNamespace(plan_id="p1", source="strategy", strategy=strategy, direction=direction,
                           horizon_key="4w", trigger_price=CLOSE, entry_price=None,
                           stop_loss=_stop(direction), tp1=None, tp2=None, badge="WEAK",
                           quality_score=0, cohort_label="COHORT_UNKNOWN", cohort_stats={},
                           risk_features={}, ledger="weak", entry_context={}, ticker="T")


def _knobs(monkeypatch, scope, min_r):
    monkeypatch.setattr(config, "HEADROOM_SCOPE", scope)
    monkeypatch.setattr(config, "HEADROOM_MIN_R", min_r)


def _live_strategy_rejects(monkeypatch, frame, direction, strategy):
    monkeypatch.setattr(sp, "build_strategy_plan_at", lambda *a, **k: _plan(direction, strategy))
    monkeypatch.setattr(sp, "risk_sizing_ok", lambda plan: True)
    deps = sp._PassDeps(plan_store=_Store(), trade_log=_Log(), mode="shadow", live_allow=set(),
                        rs_combined_of=lambda ticker: None, asof_of=None)
    result = sp.PassResult()
    sp._emit_signal(result, frame, ticker="T", strategy=strategy, direction=direction,
                    horizon="4w", bar_date=frame.index[-1].date().isoformat(), regime=None,
                    deps=deps)
    assert (result.headroom == 1) == (result.plans == [])
    return result.headroom == 1


def _replay_strategy_rejects(monkeypatch, frame, direction, strategy):
    monkeypatch.setattr(strategy_engine, "build_strategy_plan",
                        lambda *a, **k: _plan(direction, strategy))
    plan = strategy_engine.StrategyEngine._gated_plan(
        frame, len(frame) - 1, ticker="T", strategy=strategy, horizon_key="4w",
        direction=direction, level_map=None, params=None)
    return plan is None


def test_the_fixture_holds_a_confirmed_level_on_both_sides():
    assert _blocker("bullish").price > CLOSE > _blocker("bearish").price


@pytest.mark.parametrize("direction", ["bullish", "bearish"])
@pytest.mark.parametrize("min_r,rejects", BOUNDARY)
@pytest.mark.parametrize("strategy", ["Fibonacci", "MACD"])
def test_strategy_live_and_replay_agree(monkeypatch, direction, min_r, rejects, strategy):
    _knobs(monkeypatch, "strategy", min_r)
    live = _live_strategy_rejects(monkeypatch, FRAME, direction, strategy)
    replay = _replay_strategy_rejects(monkeypatch, FRAME, direction, strategy)
    assert live == replay == (rejects and strategy == "Fibonacci")


@pytest.mark.parametrize("direction", ["bullish", "bearish"])
@pytest.mark.parametrize("min_r,rejects", BOUNDARY)
def test_confluence_live_and_replay_agree(monkeypatch, direction, min_r, rejects):
    _knobs(monkeypatch, "confluence", min_r)
    supports, resistances = _level_map()
    scenario = SimpleNamespace(direction=direction, entry=CLOSE, stop_loss=_stop(direction))
    stats = {"failed_counts": {"headroom": 0}}
    live = analyze._apply_headroom([scenario], supports, resistances, stats, "T", "4w") == []
    replay = backtest_scenarios._headroom_kept([scenario], supports, resistances) == []
    assert live == replay == rejects
    assert stats["failed_counts"]["headroom"] == int(rejects)


@pytest.mark.parametrize("scope", ["strategy", "confluence"])
def test_scopes_never_cross_at_the_call_sites(monkeypatch, scope):
    """`strategy` never touches a confluence scenario and vice versa."""
    _knobs(monkeypatch, scope, 0.75)
    supports, resistances = _level_map()
    scenario = SimpleNamespace(direction="bullish", entry=CLOSE, stop_loss=_stop("bullish"))
    confluence_rejects = backtest_scenarios._headroom_kept([scenario], supports, resistances) == []
    strategy_rejects = _replay_strategy_rejects(monkeypatch, FRAME, "bullish", "Fibonacci")
    assert confluence_rejects == (scope == "confluence")
    assert strategy_rejects == (scope == "strategy")


def _with_forming_bar(frame):
    """Append today's unfinished bar, far above the fixture's range. If it reached the map
    builder, the map would be split at a different price and built on a different frame."""
    nxt = frame.index[-1] + pd.offsets.BDay(1)
    last = float(frame["Close"].iloc[-1])
    bar = pd.DataFrame({"Open": [last], "High": [last * 1.2], "Low": [last],
                        "Close": [last * 1.2], "Volume": [10_000_000.0]}, index=[nxt])
    return pd.concat([frame, bar]), datetime(nxt.year, nxt.month, nxt.day, 16, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize("direction", ["bullish", "bearish"])
def test_live_and_replay_build_the_identical_signal_bar_map(monkeypatch, direction):
    """Live composes completed_frame(raw, now) then _emit_signal, exactly as
    run_strategy_pass does. Replay builds its map at the signal bar. Both must ask the map
    builder for the same frame and the same split price, and today's forming bar must reach
    neither."""
    raw, now = _with_forming_bar(FRAME)
    completed = sp.completed_frame(raw, now)
    assert len(completed) == len(FRAME) and completed.index[-1] == FRAME.index[-1]
    live_seen, replay_seen = [], []
    live_real, replay_real = sp.build_level_map, strategy_engine.build_level_map
    monkeypatch.setattr(sp, "build_level_map", lambda df, h, price:
                        live_seen.append((len(df), df.index[-1], price)) or live_real(df, h, price))
    monkeypatch.setattr(strategy_engine, "build_level_map", lambda df, h, price:
                        replay_seen.append((len(df), df.index[-1], price)) or replay_real(df, h, price))
    _knobs(monkeypatch, "strategy", 0.75)
    live = _live_strategy_rejects(monkeypatch, completed, direction, "Fibonacci")
    replay = _replay_strategy_rejects(monkeypatch, FRAME, direction, "Fibonacci")
    assert live is True and replay is True
    assert live_seen == replay_seen == [(len(FRAME), FRAME.index[-1], CLOSE)]

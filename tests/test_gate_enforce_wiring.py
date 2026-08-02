"""Plan v8 Task V14 Step 2: does the gatekeeper actually block?

The plan's premise was that the gate has had no effect because `inform`
is the default mode. That was only half of it. Two defects made enforce
mode unable to change anything even when switched on, and neither is
visible from `decide()`'s own unit tests -- both live in the scan loop,
so every test here drives the real `_sync_run_scan`:

  1. The alert loop assigned a LOCAL named `gate_candidate`, shadowing the
     scan_integration function of the same name that the enforce decision
     ~60 lines above calls. Python scopes per function, so that call raised
     UnboundLocalError on the first candidate of a pass and TypeError on
     every one after, and the broad "a gate bug must never cost an alert"
     except swallowed both. The gate could not block in ANY mode.

  2. The block arrived after the candidate's paper trade and plan record
     were already written, and only suppressed the Discord alert. The trade
     stayed open (so the book -- what every cohort analysis reads -- was
     identical gate-on vs gate-off) and the plan stayed live in PlanStore,
     where PlanManager.poll() would log a brand-new trade at fill.
"""
import datetime as dt
from types import SimpleNamespace

import pytest

import swingbot.config as config
from swingbot.commands.scanning import GateContext
from swingbot.core.gate.types import GateResult
from swingbot.core.performance import TradeLog
from swingbot.core.plan_store import PlanStore
from swingbot.core.scanning import engine

from tests.test_engine_v2_plans import _structured_df


def _run(monkeypatch, tmp_path, *, mode, tier="C", min_tier="A", hard_blocks=(),
         progress=None):
    """One real scan pass with the gate enabled and every candidate scored
    at `tier`. Returns (alerts, trade_log, plan_store)."""
    df = _structured_df()

    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "MIN_REWARD_PCT", 0.5)
    monkeypatch.setattr(config, "MIN_STOP_DISTANCE_PCT", 0.0)
    monkeypatch.setattr(config, "MAX_STOP_LOSS_PCT", 50.0)
    monkeypatch.setattr(config, "MIN_RISK_REWARD_RATIO", 0.0)
    monkeypatch.setattr(config, "TARGET_FLOOR_ENABLED", False)
    monkeypatch.setattr(config, "MIN_ALERT_CONFIDENCE_LEVEL", 1)
    monkeypatch.setattr(config, "GATE_ENABLED", True)
    monkeypatch.setattr(config, "GATE_MODE", mode)
    monkeypatch.setattr(config, "GATE_MIN_TIER", min_tier)
    monkeypatch.setattr(config, "MACRO_ENABLED", False)
    monkeypatch.setitem(engine.HORIZONS["4w"], "sr_target_min_pct", 1.0)
    # gate persistence/telemetry resolve their paths at IMPORT time from
    # config.DATA_DIR, so patching DATA_DIR alone still writes blocked.jsonl /
    # shadow.jsonl / telemetry.jsonl into the repo's real data/gate directory.
    monkeypatch.setattr(engine.gate_persistence, "BLOCKED_PATH",
                        str(tmp_path / "blocked.jsonl"))
    monkeypatch.setattr(engine.gate_persistence, "SHADOW_PATH",
                        str(tmp_path / "shadow.jsonl"))
    monkeypatch.setattr(engine.gate_telemetry, "TELEMETRY_PATH",
                        str(tmp_path / "telemetry.jsonl"))

    trade_log = TradeLog(path=str(tmp_path / "trades.json"))
    monkeypatch.setattr(engine, "load_watchlist", lambda: ["TEST"])
    monkeypatch.setattr(engine, "get_daily_data",
                        lambda ticker, period=None: df.copy() if ticker == "TEST" else None)
    monkeypatch.setattr(engine, "get_current_price", lambda ticker: None)
    monkeypatch.setattr(engine, "trade_log", trade_log)
    monkeypatch.setattr(engine, "is_stop_requested", lambda: False)
    monkeypatch.setattr(engine, "earnings_within_window", lambda t, d: None)
    monkeypatch.setattr(engine, "get_market_events", lambda d: [])
    monkeypatch.setattr(engine, "generate_trade_chart", lambda *a, **k: str(tmp_path / "c.png"))
    monkeypatch.setattr(engine, "notify_secondary", lambda *a, **k: None)
    monkeypatch.setattr(engine, "build_embed", lambda *a, **k: SimpleNamespace(fields=[]))

    monkeypatch.setattr(
        engine, "run_checklist",
        lambda ticker, strategy, plan, df_, **kw: GateResult(
            ticker=ticker, strategy=strategy, as_of="2026-08-02", checks=(),
            score=10.0, tier=tier, hard_blocks=tuple(hard_blocks), macro_stale=False))

    ctx = GateContext(macro_snap={}, open_plans=[], spy_df=None, now=dt.datetime.now())
    result = engine._sync_run_scan("4w", require_confirmation=False,
                                   progress=progress, min_confluence=0, gate_ctx=ctx)

    alerts = []
    if isinstance(result, tuple):
        alerts = next((p for p in result if isinstance(p, list)), [])
    elif isinstance(result, list):
        alerts = result
    return alerts, trade_log, PlanStore(path=str(tmp_path / "plans.json"))


def test_enforce_actually_blocks_through_the_real_scan_loop(monkeypatch, tmp_path, caplog):
    """Regression for the shadowed `gate_candidate`. Asserting "0 alerts" is
    not enough on its own -- before the fix the call raised and was swallowed,
    which ALSO produced alerts, so this additionally pins that no candidate
    took the "ships ungated" escape hatch."""
    caplog.set_level("WARNING")
    alerts, _, _ = _run(monkeypatch, tmp_path, mode="enforce", tier="C", min_tier="A")
    assert alerts == []
    assert "ships ungated" not in caplog.text, \
        "the gate raised and was swallowed -- it is not evaluating at all"


def test_inform_still_never_blocks(monkeypatch, tmp_path):
    """The contrast: the same C-tier candidates that enforce refuses must
    still post in inform mode, or the fix above turned the default into a
    silent blocker."""
    alerts, _, _ = _run(monkeypatch, tmp_path, mode="inform", tier="C", min_tier="A")
    assert alerts, "inform must never drop an alert"


def test_a_blocked_candidate_leaves_no_open_paper_trade(monkeypatch, tmp_path):
    """The trade is written ~150 lines before the gate is consulted. If the
    block only suppresses the alert, the book is unchanged by the gate --
    and the book is what every cohort/win-rate analysis reads."""
    alerts, trade_log, _ = _run(monkeypatch, tmp_path, mode="enforce", tier="C", min_tier="A")
    assert alerts == []
    assert trade_log.get_trades(status="open", limit=None) == []


def test_a_blocked_plan_cannot_be_refilled_by_the_intraday_manager(monkeypatch, tmp_path):
    """PlanManager.poll() walks store.open_plans() and logs a NEW trade on the
    fill transition; its trigger-time re-check only re-runs the "trigger"
    subset and never re-reads tier/min_tier. So a blocked plan left in an open
    status would simply refill itself once price crossed."""
    _, _, store = _run(monkeypatch, tmp_path, mode="enforce", tier="C", min_tier="A")
    assert store.open_plans() == []
    # The record itself survives, terminal-stated -- the block is auditable,
    # not erased.
    assert store.all(), "the plan record should survive the block, just not live"


def test_a_hard_block_is_rolled_back_the_same_way(monkeypatch, tmp_path):
    """The other route into `decision == "block"`: hard_blocks force it
    regardless of tier, and must not take a different rollback path."""
    alerts, trade_log, store = _run(monkeypatch, tmp_path, mode="enforce",
                                    tier="A+", min_tier="C",
                                    hard_blocks=("rf_fake_breakout",))
    assert alerts == []
    assert trade_log.get_trades(status="open", limit=None) == []
    assert store.open_plans() == []


def test_a_passing_candidate_keeps_its_trade_and_live_plan(monkeypatch, tmp_path):
    """The rollback must be reachable ONLY on a block -- an A+ candidate at a
    C floor passes, and its trade and plan must be untouched."""
    alerts, trade_log, store = _run(monkeypatch, tmp_path, mode="enforce",
                                    tier="A+", min_tier="C")
    assert alerts, "an A+ candidate must not be blocked at a C floor"
    assert trade_log.get_trades(status="open", limit=None)
    assert store.open_plans()


def test_blocks_are_counted_into_the_funnel(monkeypatch, tmp_path):
    """A gate that silently eats every alert is indistinguishable from a dead
    scanner unless the count is reported."""
    progress = engine.ScanProgress()
    progress.funnel = {}
    _run(monkeypatch, tmp_path, mode="enforce", tier="C", min_tier="A",
         progress=progress)
    assert progress.funnel["skipped_gate_blocked"] > 0

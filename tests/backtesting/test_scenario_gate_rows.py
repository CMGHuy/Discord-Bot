"""v147 T2/T3: the confluence replay's record-only gate rows.

T2 -- `no_qualifying_target`: a scenario whose plan build returned None is a
`blocked`/`no-plan` row. T3 -- `risk_cap`: a record-only shadow of
`analyze.attach_plan_v2`'s plan-time 2% check on every replayed plan; an
over-cap plan's already-simulated outcome moves from `taken` to `blocked`.
The replay's own results never change.
"""
from __future__ import annotations

import numpy as np
import pytest

from swingbot.core.backtesting import backtest_scenarios as bs
from swingbot.core.planning.exit_sim import ExitResult, _not_triggered
from swingbot.core.planning.plan_engine import PlanStatus, TradePlanV2
from swingbot.core.risk_limits import HARD_MAX_PLANNED_LOSS_PCT, planned_loss_pct
from tests.helpers import make_ohlcv

GATES = {"min_reward_pct": 1.0, "min_stop_distance_pct": 0.5,
         "max_stop_distance_pct": 15.0, "min_risk_reward": 0.0,
         "min_confluence": 1, "cooldown_bars": 5}


def _structured_df():
    """Trend up, then a 60-bar box: the fixture tests/backtesting/test_backtest_scenarios.py
    uses (local copy, same reason as there: fixtures stay uncoupled)."""
    rng = np.random.RandomState(7)
    trend = list(100 * np.cumprod(1 + rng.normal(0.002, 0.01, 120)))
    box = [trend[-1] * (1 + 0.05 * np.sin(i / 4)) for i in range(60)]
    return make_ohlcv(trend + box)


def _plan(stop_loss: float, *, direction: str = "bullish") -> TradePlanV2:
    return TradePlanV2(
        plan_id="p1", ticker="AAPL", created_at="2024-01-02", source="confluence",
        strategy="S/R Confluence", horizon_key="4w", direction=direction, entry_type="stop_entry",
        trigger_price=100.0, entry_price=None, expiry_bars=3, stop_loss=stop_loss, tp1=104.0,
        tp1_fraction=0.5, tp2=108.0, breakeven_trigger_fraction=0.5, trail_atr_mult=2.5,
        quality_score=0, quality_breakdown=[], badge="WEAK", badge_stats={},
        status=PlanStatus.PENDING, status_history=[])


def _filled(r_total: float) -> ExitResult:
    return ExitResult(outcome="win" if r_total > 0 else "loss", runner_outcome=None, entry_index=3,
                      exit_index=6, entry_price=100.0, r_total=r_total,
                      legs=[{"fraction": 1.0, "exit_price": 101.0, "r": r_total, "reason": "tp1"}])


def _analyze_rejects(plan) -> bool:
    """analyze.attach_plan_v2's plan-time check, verbatim (swingbot/core/scanning/analyze.py)."""
    return planned_loss_pct(plan.trigger_price, plan.stop_loss) > HARD_MAX_PLANNED_LOSS_PCT + 1e-9


DF = make_ohlcv([100.0 + 0.1 * i for i in range(12)])


# -- T3: the risk_cap shadow on fixed plans ----------------------------------------------------------

@pytest.mark.parametrize("stop", [98.5, 98.0, 97.99, 97.0, 95.0, 90.0])
def test_risk_cap_shadow_agrees_with_the_live_plan_time_check(stop):
    plan = _plan(stop)
    row = bs._plan_gate_row("AAPL", DF, "4w", 5, plan, _filled(0.8))
    assert (row["arm"] == "blocked") is _analyze_rejects(plan)
    assert row["gate"] == "plan_rejected" and row["population"] == "train"
    assert row["source"] == "confluence" and row["in_sample"] is False
    assert row["signal_date"] == str(DF.index[5].date()) == row["entry_date"]


def test_an_over_cap_plan_is_a_blocked_risk_cap_row_with_margin_and_dollar_risk():
    plan = _plan(97.0)                                  # 3% planned loss
    row = bs._plan_gate_row("AAPL", DF, "4w", 5, plan, _filled(1.2))
    loss = planned_loss_pct(plan.trigger_price, plan.stop_loss)
    assert (row["arm"], row["reason"]) == ("blocked", "risk_cap")
    assert row["margin"] == pytest.approx(loss - HARD_MAX_PLANNED_LOSS_PCT)
    assert row["planned_loss_pct"] == pytest.approx(loss)
    assert row["cf_status"] == "filled" and row["cf_r"] == pytest.approx(1.2)
    assert row["dollar_risk"] == pytest.approx(1.2 * loss / HARD_MAX_PLANNED_LOSS_PCT)
    assert row["expiry_bars"] == 3


def test_an_in_cap_plan_is_a_taken_row_without_cap_fields():
    row = bs._plan_gate_row("AAPL", DF, "4w", 5, _plan(98.5), _filled(-1.0))
    assert (row["arm"], row["reason"], row["margin"]) == ("taken", None, None)
    assert row["planned_loss_pct"] is None and row["dollar_risk"] is None
    assert row["cf_status"] == "filled" and row["cf_r"] == pytest.approx(-1.0)


def test_a_never_triggered_plan_is_no_fill_with_no_r_in_either_arm():
    for stop in (98.5, 97.0):
        row = bs._plan_gate_row("AAPL", DF, "4w", 5, _plan(stop), _not_triggered("expired"))
        assert row["cf_status"] == "no-fill"
        assert row["cf_r"] is None and row["win"] is None


# -- T2: no_qualifying_target through the real replay ------------------------------------------------

@pytest.mark.slow
def test_replay_records_no_target_scenarios_and_still_returns_nothing(monkeypatch):
    df = _structured_df()
    monkeypatch.setattr(bs, "build_confluence_plan", lambda *a, **k: None)
    blocked: list = []
    assert bs.replay_scenarios("AAPL", df, "4w", gates=GATES, blocked=blocked) == []
    assert bs.replay_scenarios("AAPL", df, "4w", gates=GATES) == []       # default: no sink
    assert blocked, "fixture must produce scenarios"
    assert all(0 <= i < len(df) and sc.direction in ("bullish", "bearish") for i, sc in blocked)


@pytest.mark.slow
def test_no_target_rows_are_blocked_no_plan_rows(monkeypatch):
    df = _structured_df()
    monkeypatch.setattr(bs, "build_confluence_plan", lambda *a, **k: None)
    out, rows = bs._replay_ticker_gate_rows(("AAPL", df, ["4w"], None, None, GATES, True, None, None, None, None, True))
    assert out == {"4w": []}
    assert rows
    for row in rows:
        assert (row["arm"], row["gate"], row["reason"]) == ("blocked", "plan_rejected", "no_qualifying_target")
        assert row["cf_status"] == "no-plan" and row["cf_r"] is None and row["margin"] is None
        assert row["source"] == "confluence" and row["horizon"] == "4w"
        assert row["strategy"]                                           # primary_strategy_for label


@pytest.mark.slow
def test_recording_leaves_the_replay_stats_identical_and_writes_no_rs_row():
    df = _structured_df()
    kwargs = dict(gates=GATES, scale_out=True, horizons=["4w"], workers=1)
    plain = bs.run_scenario_backtest({"AAPL": df}, None, None, **kwargs)
    recorded = bs.run_scenario_backtest({"AAPL": df}, None, None, record_blocked=True, **kwargs)
    assert "gate_rows" not in plain
    assert {k: recorded[k] for k in ("pooled", "by_horizon")} == plain
    rows = recorded["gate_rows"]
    assert rows and {row["gate"] for row in rows} == {"plan_rejected"}
    assert {row["population"] for row in rows} == {"train"}
    out, _ = bs._replay_ticker_gate_rows(("AAPL", df, ["4w"], None, None, GATES, True, None, None, None, None, True))
    simulated = [row for row in rows if row["reason"] != "no_qualifying_target"]
    assert len(simulated) == len(out["4w"])                              # one row per replayed plan


@pytest.mark.slow
def test_a_failing_recorder_leaves_the_replay_stats_identical(monkeypatch):
    """Measurement only: a row builder that raises costs the rows, never the replay's results."""
    df = _structured_df()
    kwargs = dict(gates=GATES, scale_out=True, horizons=["4w"], workers=1)
    plain = bs.run_scenario_backtest({"AAPL": df}, None, None, **kwargs)

    def _boom(*a, **k):
        raise RuntimeError("recorder down")

    monkeypatch.setattr(bs, "_horizon_gate_rows", _boom)
    recorded = bs.run_scenario_backtest({"AAPL": df}, None, None, record_blocked=True, **kwargs)
    assert {k: recorded[k] for k in ("pooled", "by_horizon")} == plain
    assert recorded["gate_rows"] == []


@pytest.mark.slow
def test_rows_respect_the_signal_window():
    df = _structured_df()
    start, end = str(df.index[100].date()), str(df.index[150].date())
    _, rows = bs._replay_ticker_gate_rows(("AAPL", df, ["4w"], start, end, GATES, True, None, None, None, None, True))
    assert rows and all(start <= row["signal_date"] <= end for row in rows)


def test_the_legacy_tuples_still_return_a_horizon_dict(monkeypatch):
    monkeypatch.setattr(bs, "replay_scenarios", lambda *a, **k: [(0, "p0")])
    monkeypatch.setattr(bs, "simulate_exit", lambda df, i, plan, scale_out: plan)
    df = make_ohlcv([1.0, 2.0])
    base = ("T", df, ["2w"], None, None, {}, True, None, None)
    assert bs._replay_ticker(base) == {"2w": ["p0"]}
    assert bs._replay_ticker_gate_rows(base + (None, None, None)) == ({"2w": ["p0"]}, [])   # record flag (args[11]) None: no rows

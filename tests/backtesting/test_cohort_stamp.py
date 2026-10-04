import json

import pytest

from swingbot.core.backtesting import cohort_registry as cr
from swingbot.core.planning.params import stamp_cohort
from swingbot.core.planning.plan_types import PlanStatus, TradePlanV2, plan_from_dict, plan_to_dict


@pytest.fixture
def poor_registry(tmp_path):
    path = tmp_path / "cohort_registry.json"
    path.write_text(
        json.dumps(
            {
                "run_date": "2026-09-14",
                "window": "TRAIN+LIVE",
                "pool_mean_r": -0.136,
                "cells": {
                    "bearish|bear_volatile": {
                        "n_live": 100,
                        "n_backtest": 500,
                        "win_rate_live": 41.0,
                        "win_rate_backtest": 41.4,
                        "expectancy_r_live": -0.38,
                        "expectancy_r_backtest": -0.38,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    cr.load_registry(path)
    yield
    cr.reload_registry()


def _plan(direction="bearish"):
    return TradePlanV2(
        plan_id="p1", ticker="AAPL", created_at="2026-09-14", source="confluence",
        strategy="RSI", horizon_key="2w", direction=direction, entry_type="market",
        trigger_price=100.0, entry_price=100.0, expiry_bars=5, stop_loss=98.0,
        tp1=104.0, tp1_fraction=0.5, tp2=None, breakeven_trigger_fraction=0.5,
        trail_atr_mult=2.0, quality_score=0, quality_breakdown=[], badge="WEAK",
        badge_stats={}, status=PlanStatus.PENDING,
    )


def test_plan_defaults_to_unknown_before_stamping():
    assert _plan().cohort_label == "COHORT_UNKNOWN"
    assert _plan().cohort_stats == {}


def test_stamp_marks_a_poor_cohort_and_records_what_it_was_told(poor_registry):
    plan = _plan()
    stamp_cohort(plan, "bear_volatile")
    assert plan.cohort_label == "COHORT_POOR"
    assert plan.cohort_stats["run_date"] == "2026-09-14"
    assert plan.cohort_stats["n_live"] == 100
    assert plan.cohort_stats["n_backtest"] == 500
    assert plan.cohort_stats["expectancy_r"] == pytest.approx(-0.38, abs=1e-6)
    assert plan.cohort_stats["regime2_state"] == "bear_volatile"


def test_stamp_without_a_regime_is_unknown_not_a_guess(poor_registry):
    plan = _plan()
    stamp_cohort(plan, None)
    assert plan.cohort_label == "COHORT_UNKNOWN"


def test_cohort_survives_a_json_round_trip(poor_registry):
    plan = _plan()
    stamp_cohort(plan, "bear_volatile")
    restored = plan_from_dict(json.loads(json.dumps(plan_to_dict(plan))))
    assert restored.cohort_label == "COHORT_POOR"
    assert restored.cohort_stats["n_backtest"] == 500


def test_a_plan_persisted_before_v86_still_loads():
    payload = plan_to_dict(_plan())
    payload.pop("cohort_label")
    payload.pop("cohort_stats")
    assert plan_from_dict(payload).cohort_label == "COHORT_UNKNOWN"

"""PENDING plan-view projection behaviour."""

import pytest

from swingbot.core.presentation.plan_view import plan_view


class FakePlan:
    def __init__(self, **kw):
        defaults = dict(
            status="PENDING", direction="bullish", trigger_price=100.0,
            entry_price=None, stop_loss=90.0, tp1=120.0, tp2=None,
            expiry_bars=5, created_at="2026-09-01", working_stop=None,
            legs_realized=[], tp1_fraction=0.5,
        )
        defaults.update(kw)
        for key, value in defaults.items():
            setattr(self, key, value)


def test_phase_is_the_plans_status():
    assert plan_view(FakePlan()).phase == "PENDING"


def test_at_trigger_is_zero_r_and_full_approach_bar():
    view = plan_view(FakePlan(), price=100.0)
    assert view.distance_to_trigger_r == pytest.approx(0.0)
    assert view.bar_kind == "approach"
    assert view.bar.pos == pytest.approx(100.0)


def test_one_r_below_trigger_empties_bar():
    view = plan_view(FakePlan(), price=90.0)
    assert view.distance_to_trigger_r == pytest.approx(1.0)
    assert view.bar.pos == pytest.approx(0.0)


def test_half_r_away_fills_bar_halfway():
    view = plan_view(FakePlan(), price=95.0)
    assert view.distance_to_trigger_r == pytest.approx(0.5)
    assert view.bar.pos == pytest.approx(50.0)


def test_past_trigger_clamps_bar_not_distance():
    view = plan_view(FakePlan(), price=105.0)
    assert view.distance_to_trigger_r == pytest.approx(-0.5)
    assert view.bar.pos == pytest.approx(100.0)


def test_bearish_distance_is_signed_the_same_way():
    plan = FakePlan(direction="bearish", trigger_price=100.0, stop_loss=110.0,
                    tp1=80.0)
    view = plan_view(plan, price=110.0)
    assert view.distance_to_trigger_r == pytest.approx(1.0)
    assert view.bar.pos == pytest.approx(0.0)


def test_no_price_means_no_bar_but_expiry_remains():
    view = plan_view(FakePlan(), price=None, bars_since_created=2)
    assert view.bar_kind == "none"
    assert view.bar is None
    assert view.distance_to_trigger_r is None
    assert view.bars_to_expiry == 3


def test_bars_to_expiry_counts_down_and_floors_at_zero():
    assert plan_view(FakePlan(), bars_since_created=0).bars_to_expiry == 5
    assert plan_view(FakePlan(), bars_since_created=5).bars_to_expiry == 0
    assert plan_view(FakePlan(), bars_since_created=9).bars_to_expiry == 0


def test_bars_to_expiry_is_none_when_unknown():
    assert plan_view(FakePlan()).bars_to_expiry is None


def test_zero_risk_degrades_without_division_by_zero():
    view = plan_view(FakePlan(trigger_price=100.0, stop_loss=100.0), price=99.0)
    assert view.distance_to_trigger_r is None
    assert view.bar_kind == "none"


def test_pending_has_no_banked_or_partial_readouts():
    view = plan_view(FakePlan(), price=95.0)
    assert view.banked is None
    assert view.target_is_banked_tp1 is False
    assert (view.floor_r, view.price_r, view.headroom_r) == (None, None, None)

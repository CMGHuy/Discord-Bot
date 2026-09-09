"""ACTIVE plan-view projection behaviour."""
import pytest

from swingbot.core.presentation.plan_view import plan_view


class FakePlan:
    def __init__(self, **kw):
        defaults = dict(status="ACTIVE", direction="bullish", trigger_price=100.0,
                        entry_price=100.0, stop_loss=90.0, tp1=120.0, tp2=None,
                        expiry_bars=5, created_at="2026-09-01", working_stop=None,
                        legs_realized=[], tp1_fraction=0.5)
        defaults.update(kw)
        for key, value in defaults.items():
            setattr(self, key, value)


def test_active_uses_original_levels():
    view = plan_view(FakePlan(), price=110.0)
    assert (view.entry, view.stop, view.target) == (100.0, 90.0, 120.0)
    assert view.stop_kind == "risk"
    assert view.target_is_banked_tp1 is False


def test_bar_spans_stop_to_target_with_entry_marked():
    view = plan_view(FakePlan(), price=105.0)
    assert view.bar_kind == "progress"
    assert (view.bar.lo, view.bar.hi) == (90.0, 120.0)
    assert view.bar.pos == pytest.approx(50.0)
    assert view.bar.entry_pos == pytest.approx(100 / 3, abs=0.1)


def test_bearish_bar_runs_other_way():
    plan = FakePlan(direction="bearish", entry_price=100.0, stop_loss=110.0, tp1=80.0)
    assert plan_view(plan, price=95.0).bar.pos == pytest.approx(50.0)


def test_price_past_target_clamps_bar():
    assert plan_view(FakePlan(), price=130.0).bar.pos == pytest.approx(100.0)


def test_active_working_stop_is_break_even_risk_stop():
    view = plan_view(FakePlan(working_stop=100.0), price=110.0)
    assert (view.stop, view.stop_kind, view.bar.lo) == (100.0, "risk", 100.0)


def test_no_price_means_no_bar():
    view = plan_view(FakePlan())
    assert (view.bar_kind, view.bar) == ("none", None)


def test_malformed_record_degrades_without_backwards_bar():
    view = plan_view(FakePlan(stop_loss=130.0, tp1=120.0), price=125.0)
    assert (view.bar_kind, view.bar) == ("none", None)

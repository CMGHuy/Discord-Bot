"""PARTIAL runners project their live leg rather than their original plan."""
import pytest

from swingbot.core.presentation.plan_view import plan_view


class FakePlan:
    def __init__(self, **kw):
        defaults = dict(status="PARTIAL", direction="bullish", trigger_price=100.0,
                        entry_price=100.0, stop_loss=90.0, tp1=120.0, tp2=None,
                        expiry_bars=5, created_at="2026-09-01", working_stop=113.3333333,
                        legs_realized=[{"fraction": 0.5, "exit_price": 121.0,
                                        "r": 2.1, "reason": "tp1"}],
                        tp1_fraction=0.5)
        defaults.update(kw)
        for key, value in defaults.items():
            setattr(self, key, value)


def test_entry_is_tp1_legs_actual_fill():
    assert plan_view(FakePlan(), price=125.0).entry == 121.0


def test_entry_falls_back_to_tp1_without_banked_leg():
    assert plan_view(FakePlan(legs_realized=[]), price=125.0).entry == 120.0


def test_stop_is_working_stop_and_trailing():
    view = plan_view(FakePlan(), price=125.0)
    assert (view.stop, view.stop_kind) == (pytest.approx(113.3333333), "trailing")


def test_missing_working_stop_uses_runner_floor_never_original_stop():
    view = plan_view(FakePlan(working_stop=None), price=125.0)
    assert view.stop == pytest.approx(113.3333333)
    assert view.stop != 90.0
    assert view.stop_kind == "derived_floor"


def test_no_tp2_has_no_target_and_flags_banked_tp1():
    view = plan_view(FakePlan(tp2=None), price=125.0)
    assert (view.target, view.target_is_banked_tp1) == (None, True)


def test_no_tp2_has_trailing_readouts_in_r():
    view = plan_view(FakePlan(tp2=None), price=125.0)
    assert (view.bar_kind, view.bar) == ("trailing", None)
    assert view.floor_r == pytest.approx(1.3333333)
    assert view.price_r == pytest.approx(2.5)
    assert view.headroom_r == pytest.approx(1.1666667)


def test_tp2_restores_real_progress_bar():
    view = plan_view(FakePlan(tp2=140.0), price=125.0)
    assert (view.target, view.target_is_banked_tp1, view.bar_kind) == (140.0, False, "progress")
    assert (view.bar.lo, view.bar.hi) == (pytest.approx(113.3333333), 140.0)
    assert view.floor_r is None


def test_banked_leg_is_reported():
    banked = plan_view(FakePlan(), price=125.0).banked
    assert (banked.fraction, banked.exit_price, banked.r) == (0.5, 121.0, 2.1)


def test_banked_is_none_without_leg():
    assert plan_view(FakePlan(legs_realized=[]), price=125.0).banked is None


def test_bearish_partial_has_equivalent_floor_and_r_readouts():
    plan = FakePlan(direction="bearish", entry_price=100.0, stop_loss=110.0,
                    tp1=80.0, tp2=None, working_stop=None,
                    legs_realized=[{"fraction": 0.5, "exit_price": 79.0,
                                    "r": 2.1, "reason": "tp1"}])
    view = plan_view(plan, price=75.0)
    assert view.stop == pytest.approx(86.6666667)
    assert (view.stop_kind, view.entry, view.target, view.bar_kind) == (
        "derived_floor", 79.0, None, "trailing")
    assert (view.price_r, view.floor_r) == (pytest.approx(2.5), pytest.approx(1.3333333))


def test_no_price_preserves_floor_but_not_live_readouts():
    view = plan_view(FakePlan(tp2=None), price=None)
    assert view.floor_r == pytest.approx(1.3333333)
    assert (view.price_r, view.headroom_r, view.bar_kind) == (None, None, "trailing")

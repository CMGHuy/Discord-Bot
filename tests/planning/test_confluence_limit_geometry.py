"""v212 limit geometry (spec § The rule 1-5): scope by clamped_distance, the
limit partway to the level rounded toward the price, the stop 0.25% beyond
the level rounded away from the limit, and the three drop reasons."""
import pytest

from swingbot.core.planning import builders
from swingbot.core.planning.builders import (LIMIT_DROP_REASONS, LIMIT_EXPIRY_BARS,
                                             LIMIT_STOP_BUFFER, LimitGeometry,
                                             apply_confluence_limit,
                                             confluence_limit_geometry, to_limit_plan)
from swingbot.core.planning.plan_types import PlanStatus, TradePlanV2, plan_to_dict

THIRD, HALF, TWO_THIRDS = 1 / 3, 0.5, 2 / 3


def _geo(entry, level, is_bull, tp1, f, min_rr=1.5):
    return confluence_limit_geometry(entry, level, is_bull, tp1, f, min_rr)


def test_frozen_constants():
    assert LIMIT_STOP_BUFFER == 0.0025
    assert LIMIT_EXPIRY_BARS == 3
    assert LIMIT_DROP_REASONS == ("limit_scope", "limit_stop_beyond_cap", "limit_rr_fail")


@pytest.mark.parametrize("f,limit", [(HALF, 98.5), (TWO_THIRDS, 98.0)])
def test_long_limit_partway_with_the_stop_under_the_support(f, limit):
    geo = _geo(100.0, 97.0, True, 104.0, f)
    assert isinstance(geo, LimitGeometry)
    assert (geo.limit, geo.stop_loss) == (limit, 96.75)          # 97 * 0.9975 = 96.7575 -> floor
    assert geo.level_distance_pct == pytest.approx(3.0)


@pytest.mark.parametrize("f,limit", [(HALF, 101.5), (TWO_THIRDS, 102.0)])
def test_short_limit_mirrors_with_the_stop_over_the_resistance(f, limit):
    geo = _geo(100.0, 103.0, False, 96.0, f)
    assert (geo.limit, geo.stop_loss) == (limit, 103.26)         # 103 * 1.0025 = 103.2575 -> ceil


@pytest.mark.parametrize("is_bull,level,tp1,limit,stop", [
    (True, 96.9, 104.0, 97.94, 96.65),     # 97.9333 ceil toward 100; 96.65775 floor
    (False, 103.1, 96.0, 102.06, 103.36),  # 102.0667 floor toward 100; 103.35775 ceil
])
def test_tick_rounding_limit_toward_price_stop_away_from_limit(is_bull, level, tp1, limit, stop):
    geo = _geo(100.0, level, is_bull, tp1, TWO_THIRDS)
    assert (geo.limit, geo.stop_loss) == (limit, stop)


@pytest.mark.parametrize("is_bull,level,tp1", [(True, 97.0, 104.0), (False, 103.0, 96.0)])
def test_stop_beyond_two_percent_of_the_limit_is_dropped(is_bull, level, tp1):
    # f = 1/3: long 99.00 vs 96.75 is 2.27%; short 101.00 vs 103.26 is 2.24%
    assert _geo(100.0, level, is_bull, tp1, THIRD) == "limit_stop_beyond_cap"


@pytest.mark.parametrize("is_bull,level,tp1", [(True, 97.0, 101.0), (False, 103.0, 99.0)])
def test_target_failing_min_rr_from_the_limit_is_dropped(is_bull, level, tp1):
    # long: (101 - 98.5) / 1.75 = 1.43R; short: (101.5 - 99) / 1.76 = 1.42R
    assert _geo(100.0, level, is_bull, tp1, HALF) == "limit_rr_fail"


@pytest.mark.parametrize("is_bull,tp1", [(True, None), (True, 97.5), (False, 102.5)])
def test_missing_or_wrong_side_target_is_an_rr_drop(is_bull, tp1):
    level = 97.0 if is_bull else 103.0
    assert _geo(100.0, level, is_bull, tp1, HALF) == "limit_rr_fail"


@pytest.mark.parametrize("is_bull,level", [
    (True, 98.0), (False, 102.0),            # exactly 2%: clamped_distance is None
    (True, 98.5), (False, 101.5),            # inside 2%: stop already on structure
    (True, None), (False, None),             # missing level
    (True, float("nan")), (True, 101.0), (False, 99.0),   # non-finite, wrong side
])
def test_out_of_scope_returns_none(is_bull, level):
    assert _geo(100.0, level, is_bull, 104.0 if is_bull else 96.0, HALF) is None


@pytest.mark.parametrize("f", [0.0, -0.5])
def test_non_positive_f_is_out_of_scope(f):
    assert _geo(100.0, 97.0, True, 104.0, f) is None


def test_degenerate_rounding_is_a_scope_drop():
    # 1.00 - (1/3) * 0.025 = 0.99167 ceils to 1.00 == the price
    assert _geo(1.0, 0.975, True, 1.05, THIRD) == "limit_scope"


def test_short_degenerate_rounding_is_a_scope_drop():
    # 1.00 + (1/3) * 0.025 = 1.00833 floors to 1.00 == the price
    assert _geo(1.0, 1.025, False, 0.95, THIRD) == "limit_scope"


def _market(direction="bullish", **kw):
    bull = direction == "bullish"
    base = dict(plan_id="p1", ticker="XYZ", created_at="2026-11-06", source="confluence",
                strategy="S/R Confluence", horizon_key="4w", direction=direction,
                entry_type="market", trigger_price=100.0, entry_price=100.0, expiry_bars=5,
                stop_loss=98.25 if bull else 101.75, tp1=104.0 if bull else 96.0,
                tp1_fraction=0.5, tp2=None, breakeven_trigger_fraction=0.5,
                trail_atr_mult=2.5, quality_score=0, quality_breakdown=[], badge="WEAK",
                badge_stats={}, status=PlanStatus.ACTIVE,
                status_history=[{"status": "ACTIVE", "reason": "market_entry", "at": "2026-11-06"}],
                acceptance_level=97.0 if bull else 103.0)
    base.update(kw)
    return TradePlanV2(**base)


def test_to_limit_plan_rewrites_only_the_entry_fields_and_copies():
    plan = _market(reclaim_level=99.0, waits_next_open=True, working_stop=99.0,
                   reclaim_atr=1.2, reclaim_session="rth")
    before = plan_to_dict(plan)
    out = to_limit_plan(plan, LimitGeometry(98.5, 96.75, 3.0), HALF)
    assert plan_to_dict(plan) == before                          # never mutates
    assert (out.entry_type, out.trigger_price, out.entry_price) == ("limit", 98.5, None)
    assert (out.stop_loss, out.tp1, out.tp2) == (96.75, 104.0, None)
    assert (out.status, out.status_history) == (PlanStatus.PENDING, [])
    assert (out.expiry_bars, out.limit_cancel_level, out.limit_strict_fill) == (3, 104.0, True)
    assert (out.limit_entry_f, out.stop_ceiling_pct) == (HALF, None)
    assert (out.reclaim_level, out.waits_next_open) == (None, None)
    assert (out.working_stop, out.reclaim_atr, out.reclaim_session) == (None, None, None)
    assert out.acceptance_level == 97.0 and out.plan_id == "p1"


@pytest.mark.parametrize("direction", ["bullish", "bearish"])
def test_apply_converts_an_in_scope_market_plan(direction):
    level = 97.0 if direction == "bullish" else 103.0
    out = apply_confluence_limit(_market(direction), level, HALF, 1.5)
    assert out.entry_type == "limit"
    assert out.trigger_price == (98.5 if direction == "bullish" else 101.5)


def test_apply_returns_the_drop_reason():
    assert apply_confluence_limit(_market(), 97.0, THIRD, 1.5) == "limit_stop_beyond_cap"


@pytest.mark.parametrize("plan,level,f", [
    (_market(), 97.0, 0.0),                                   # knob off
    (_market(entry_type="stop_entry", entry_price=None), 97.0, HALF),   # breakout
    (_market(source="strategy"), 97.0, HALF),                 # strategy-source
    (_market(), 98.5, HALF),                                  # level within 2%
    (_market(), None, HALF),                                  # missing level
])
def test_apply_leaves_out_of_scope_plans_as_the_same_object(plan, level, f):
    assert apply_confluence_limit(plan, level, f, 1.5) is plan


def test_limit_entry_f_is_omitted_while_none():
    assert "limit_entry_f" not in plan_to_dict(_market())
    converted = to_limit_plan(_market(), LimitGeometry(98.5, 96.75, 3.0), HALF)
    assert plan_to_dict(converted)["limit_entry_f"] == HALF


def test_helpers_live_in_builders():
    assert builders.confluence_limit_geometry is confluence_limit_geometry

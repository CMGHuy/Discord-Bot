"""v157 FC2: instrument/fills.py -- the v2 compare-and-fill rules and their
parity with the live gap helpers and the v1 lifecycle touch/fill rules."""
import ast
import itertools
from pathlib import Path

import pytest

from swingbot.core.backtesting.instrument import fills
from swingbot.core.backtesting.instrument.contract import V1_FILLS, V2_FILLS, FillModel
from swingbot.core.planning import lifecycle, plan_manager
from swingbot.core.planning.plan_engine import PlanStatus, TradePlanV2

DIRECTIONS = ("bullish", "bearish")
PRICES = (94.0, 95.0, 96.0, 100.0, 104.0, 105.0, 106.0)
NO_GAP = FillModel(market_entry="next_open", gap_through=False, same_bar="stop_first")


def _plan(direction, *, trigger=100.0, stop=95.0, strict=False):
    if direction == "bearish" and stop < trigger:
        stop = 2 * trigger - stop
    return TradePlanV2(
        plan_id="p1", ticker="T", created_at="2024-01-02", source="strategy",
        strategy="Probe", horizon_key="2w", direction=direction,
        entry_type="limit", trigger_price=trigger, entry_price=None, expiry_bars=3,
        stop_loss=stop, tp1=110.0 if direction == "bullish" else 90.0, tp1_fraction=0.5,
        tp2=None, breakeven_trigger_fraction=0.5, trail_atr_mult=2.5,
        quality_score=0, quality_breakdown=[], badge="WEAK", badge_stats={},
        status=PlanStatus.PENDING, status_history=[], limit_strict_fill=strict)


# --- exits: gap-through in both directions ---------------------------------

def test_bullish_stop_gapped_through_fills_at_the_open():
    assert fills.exit_fill(V2_FILLS, "stop", 95.0, 93.0, "bullish") == 93.0


def test_bullish_stop_touched_intrabar_fills_at_the_stop():
    assert fills.exit_fill(V2_FILLS, "stop", 95.0, 98.0, "bullish") == 95.0


def test_bearish_stop_gapped_through_fills_at_the_open():
    assert fills.exit_fill(V2_FILLS, "stop", 105.0, 107.0, "bearish") == 107.0


def test_bullish_target_gapped_through_fills_at_the_better_open():
    assert fills.exit_fill(V2_FILLS, "target", 110.0, 112.0, "bullish") == 112.0


def test_bearish_target_gapped_through_fills_at_the_better_open():
    assert fills.exit_fill(V2_FILLS, "target", 90.0, 88.0, "bearish") == 88.0


def test_target_touched_intrabar_fills_at_the_target():
    assert fills.exit_fill(V2_FILLS, "target", 110.0, 105.0, "bullish") == 110.0


def test_without_gap_through_both_kinds_fill_at_the_level():
    assert fills.exit_fill(NO_GAP, "stop", 95.0, 93.0, "bullish") == 95.0
    assert fills.exit_fill(NO_GAP, "target", 110.0, 112.0, "bullish") == 110.0


def test_unknown_exit_kind_is_refused():
    with pytest.raises(ValueError, match="exit kind"):
        fills.exit_fill(V2_FILLS, "close", 95.0, 93.0, "bullish")


# --- entries ---------------------------------------------------------------

def test_market_entry_fills_at_the_bar_open():
    assert fills.entry_fill(V2_FILLS, "market", "bullish", bar_open=101.25) == 101.25


def test_market_entry_needs_a_next_open_model():
    with pytest.raises(ValueError, match="next_open"):
        fills.entry_fill(V1_FILLS, "market", "bullish", bar_open=101.0)


@pytest.mark.parametrize("direction,bar_open,expected", [
    ("bullish", 99.0, 100.0), ("bullish", 102.0, 102.0),
    ("bearish", 101.0, 100.0), ("bearish", 98.0, 98.0)])
def test_stop_entry_fills_at_the_trigger_or_the_worse_open(direction, bar_open, expected):
    assert fills.entry_fill(V2_FILLS, "stop_entry", direction, bar_open=bar_open,
                            level=100.0) == expected


@pytest.mark.parametrize("direction,bar_open,expected", [
    ("bullish", 101.0, 100.0), ("bullish", 99.5, 99.5),
    ("bearish", 99.0, 100.0), ("bearish", 100.5, 100.5)])
def test_limit_fills_at_the_limit_or_the_better_open(direction, bar_open, expected):
    assert fills.entry_fill(V2_FILLS, "limit", direction, bar_open=bar_open,
                            level=100.0) == expected


def test_resting_entry_without_a_level_is_refused():
    with pytest.raises(ValueError, match="needs its level"):
        fills.entry_fill(V2_FILLS, "limit", "bullish", bar_open=100.0)


def test_unknown_entry_type_is_refused():
    with pytest.raises(ValueError, match="unknown entry_type"):
        fills.entry_fill(V2_FILLS, "moc", "bullish", bar_open=100.0)
    with pytest.raises(ValueError, match="no resting order"):
        fills.entry_touched("market", "bullish", 101.0, 99.0, 100.0)


def test_require_supported_accepts_v2_and_refuses_v1_market_entries():
    fills.require_supported(V2_FILLS)
    fills.require_supported(NO_GAP)
    with pytest.raises(ValueError, match="next_open"):
        fills.require_supported(V1_FILLS)
    with pytest.raises(ValueError, match="stop_first"):
        fills.require_supported(FillModel("next_open", True, "target_first"))


# --- parity with the live gap helpers and the v1 lifecycle rules -----------

@pytest.mark.parametrize("direction", DIRECTIONS)
def test_gap_helpers_match_plan_manager(direction):
    for bar_open, level in itertools.product(PRICES, PRICES):
        assert fills.gap_stop_fill(bar_open, level, direction) == \
            plan_manager.gap_stop_fill(bar_open, level, direction)
        assert fills.gap_target_fill(bar_open, level, direction) == \
            plan_manager.gap_target_fill(bar_open, level, direction)


@pytest.mark.parametrize("direction", DIRECTIONS)
def test_touches_match_lifecycle(direction):
    plan = _plan(direction)
    for high, low in itertools.product(PRICES, PRICES):
        if low > high:
            continue
        assert fills.entry_touched("stop_entry", direction, high, low, plan.trigger_price) == \
            lifecycle.trigger_hit(plan, high, low)
        assert fills.entry_touched("limit", direction, high, low, plan.trigger_price) == \
            lifecycle.limit_hit(plan, high, low)
        assert fills.stop_touched(high, low, plan.stop_loss, direction) == \
            lifecycle.stop_touched(plan, high, low)


@pytest.mark.parametrize("direction", DIRECTIONS)
def test_strict_limit_touch_matches_lifecycle(direction):
    plan = _plan(direction, strict=True)
    for high, low in itertools.product(PRICES, PRICES):
        if low <= high:
            assert fills.entry_touched("limit", direction, high, low, plan.trigger_price,
                                       strict=True) == lifecycle.limit_hit(plan, high, low)


@pytest.mark.parametrize("direction", DIRECTIONS)
def test_entry_fills_and_stop_side_match_lifecycle(direction):
    plan = _plan(direction)
    for price in PRICES:
        assert fills.entry_fill(V2_FILLS, "stop_entry", direction, bar_open=price,
                                level=plan.trigger_price) == lifecycle.fill_price(plan, price)
        assert fills.entry_fill(V2_FILLS, "limit", direction, bar_open=price,
                                level=plan.trigger_price) == lifecycle.limit_fill_price(plan, price)
        assert fills.at_or_beyond_stop(price, plan.stop_loss, direction) == \
            lifecycle.at_or_beyond_stop(plan, price)


@pytest.mark.parametrize("direction,high,low,expected", [
    ("bullish", 110.0, 104.0, True), ("bullish", 109.9, 104.0, False),
    ("bearish", 96.0, 90.0, True), ("bearish", 96.0, 90.1, False)])
def test_target_touched_counts_an_exact_touch(direction, high, low, expected):
    target = 110.0 if direction == "bullish" else 90.0
    assert fills.target_touched(high, low, target, direction) is expected


def test_fills_imports_nothing_from_swingbot_but_the_contract():
    src = Path(fills.__file__).read_text(encoding="utf-8")
    imported = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.ImportFrom):
            imported.add(("." * node.level) + (node.module or ""))
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
    assert imported <= {"__future__", ".contract"}

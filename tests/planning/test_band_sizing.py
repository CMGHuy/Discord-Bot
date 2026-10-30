"""V191-11: a band plan is sized on the worst fill its stored ceiling accepts
(plus the p99 gap allowance when the stamp has one), shares floored to 0.01,
so shares x distance never exceeds balance x risk_pct / 100."""
import pytest

from swingbot import config
from swingbot.core.planning import account
from swingbot.core.planning import gap_sizing as gs
from swingbot.core.planning.plan_types import PlanStatus, TradePlanV2
from swingbot.core.planning.stop_scope import band_sizing_verdict
from swingbot.core.risk_limits import planned_loss_pct
from tests.market.test_atr_band import _frame

CFG = {"balance": 10_000.0, "risk_pct": 1.0, "sizing_mode": "risk_pct", "position_pct": 10.0,
       "max_position_pct": 100.0, "max_position_value_absolute": 0, "max_risk_amount_absolute": 0}
BUDGET = 100.0


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setattr(account.opex, "size_mult", lambda *a, **k: 1.0)
    monkeypatch.setattr(account, "load_account_config", lambda: dict(CFG))
    monkeypatch.setattr(config, "LONG_GAP_SIZING", False)
    monkeypatch.setattr(config, "SHORT_GAP_SIZING", True)


def _plan(direction, d, *, moved="floor", trigger=100.0):
    bull = direction == "bullish"
    stop = trigger * (1 - d / 100) if bull else trigger * (1 + d / 100)
    return TradePlanV2(
        plan_id="p1", ticker="ZZZ", created_at="2026-10-20", source="confluence", strategy="S/R Confluence",
        horizon_key="4w", direction=direction, entry_type="stop_entry", trigger_price=trigger, entry_price=None,
        expiry_bars=5, stop_loss=stop, tp1=trigger * (1.1 if bull else 0.9), tp1_fraction=0.5, tp2=None,
        breakeven_trigger_fraction=0.5, trail_atr_mult=2.0, quality_score=0, quality_breakdown=[],
        badge="WEAK", badge_stats={}, status=PlanStatus.PENDING,
        stop_ceiling_pct=d + 0.25, stop_moved_by=moved)


def test_worst_fill_distance_long_and_short():
    assert gs.worst_fill_distance(95.0, 5.25, "bullish") == pytest.approx(95.0 * 5.25 / 94.75)
    assert gs.worst_fill_distance(105.0, 5.25, "bearish") == pytest.approx(105.0 * 5.25 / 105.25)
    fill = 95.0 + gs.worst_fill_distance(95.0, 5.25, "bullish")
    assert planned_loss_pct(fill, 95.0) == pytest.approx(5.25)     # the edge of the headroom


def test_band_sizing_distance_takes_the_gap_allowance_only_from_a_usable_p99():
    worst = gs.worst_fill_distance(95.0, 5.25, "bullish")
    assert gs.band_sizing_distance(100.0, 95.0, 5.25, "bullish", None) == pytest.approx(worst)
    stop_rule = {"rule": gs.RULE_STOP, "down_gap_p99_pct": 9.0, "n_down_gaps": 120}
    assert gs.band_sizing_distance(100.0, 95.0, 5.25, "bullish", stop_rule) == pytest.approx(worst)
    gap_rule = {"rule": gs.RULE_GAP, "down_gap_p99_pct": 9.0, "n_down_gaps": 120}
    assert gs.band_sizing_distance(100.0, 95.0, 5.25, "bullish", gap_rule) == pytest.approx(9.0)


def test_a_band_long_is_stamped_with_the_long_flag_off():
    plan = _plan("bullish", 5.0)
    gs.stamp_gap_sizing(plan, _frame())
    assert plan.gap_sizing == {"rule": gs.RULE_STOP, "down_gap_p99_pct": None, "n_down_gaps": 0,
                               gs.BAND_KEY: pytest.approx(gs.worst_fill_distance(95.0, 5.25, "bullish"))}


def test_a_non_band_long_with_the_flag_off_is_still_unstamped():
    plan = _plan("bullish", 1.5, moved=None)
    gs.stamp_gap_sizing(plan, _frame())
    assert plan.gap_sizing is None


def test_a_stamp_failure_still_stamps_the_band_distance(monkeypatch):
    monkeypatch.setattr(gs, "gap_sizing_stamp", lambda *a, **k: 1 / 0)
    plan = _plan("bearish", 5.0)
    gs.stamp_gap_sizing(plan, None)
    assert plan.gap_sizing[gs.BAND_KEY] == pytest.approx(gs.worst_fill_distance(105.0, 5.25, "bearish"))


@pytest.mark.parametrize("direction", ["bullish", "bearish"])
@pytest.mark.parametrize("d", [1.5, 4.0, 9.0])
def test_the_dollar_invariant(direction, d):
    plan = _plan(direction, d)
    gs.stamp_gap_sizing(plan, _frame())
    sizing = gs.size_for_plan(plan)
    distance = plan.gap_sizing[gs.BAND_KEY]
    assert sizing[gs.BAND_KEY] == distance
    assert sizing["shares"] * distance <= BUDGET + 1e-9
    assert sizing["shares"] * 100 == pytest.approx(round(sizing["shares"] * 100))   # 0.01 steps
    assert (sizing["shares"] + 0.01) * distance > BUDGET                            # floored, not over-cut
    assert band_sizing_verdict(plan) is None


def test_shares_floor_where_rounding_would_overshoot():
    stamp = {"rule": gs.RULE_STOP, "down_gap_p99_pct": None, "n_down_gaps": 0, gs.BAND_KEY: 6.0}
    got = gs.size_for(100.0, 95.0, direction="bullish", gap_sizing=stamp)
    assert got["shares"] == 16.66                     # 16.666..., round() would give 16.67 -> $100.02


def test_a_long_with_the_gap_flag_on_sizes_on_the_down_gap():
    stamp = {"rule": gs.RULE_GAP, "down_gap_p99_pct": 9.0, "n_down_gaps": 120}
    plan = _plan("bullish", 4.0)
    plan.gap_sizing = {**stamp, gs.BAND_KEY: gs.band_sizing_distance(100.0, 96.0, 4.25, "bullish", stamp)}
    sizing = gs.size_for_plan(plan)
    assert sizing["shares"] * 9.0 <= BUDGET + 1e-9 and sizing["gap_floor_pct"] == 9.0


def test_a_pre_v191_stamp_sizes_exactly_as_today():
    stamp = {"rule": gs.RULE_GAP, "up_gap_p99_pct": 3.0, "n_up_gaps": 125}
    got = gs.size_for(100.0, 102.0, direction="bearish", gap_sizing=stamp)
    assert got == account.compute_position_size(100.0, 102.0, None, gap_floor_pct=3.0)
    assert gs.BAND_KEY not in got


def test_verdicts(monkeypatch):
    plan = _plan("bullish", 20.0)
    gs.stamp_gap_sizing(plan, _frame())
    monkeypatch.setattr(account, "load_account_config", lambda: {**CFG, "balance": 10.0})
    assert band_sizing_verdict(plan) == "band_size_zero"            # $0.10 / ~$20 -> 0.00 shares
    monkeypatch.setattr(account, "load_account_config", lambda: {**CFG, "sizing_mode": "account_pct"})
    assert band_sizing_verdict(plan) == "risk_sizing"
    assert band_sizing_verdict(plan, sizing_fn=lambda p: 1 / 0) == "risk_sizing"
    over = lambda p: {"mode": "risk_pct", "balance": 10_000.0, "risk_pct": 1.0, "shares": 50.0,
                      gs.BAND_KEY: p.gap_sizing[gs.BAND_KEY]}
    assert band_sizing_verdict(plan, sizing_fn=over) == "risk_sizing"
    assert band_sizing_verdict(_plan("bullish", 1.5, moved=None)) is None   # not a band plan


@pytest.mark.parametrize("result", [None, "error"])
def test_unavailable_account_sizing_leaves_a_band_plan_unsized(monkeypatch, result):
    def unavailable(*args, **kwargs):
        if result == "error":
            raise ValueError("account unavailable")
        return None

    plan = _plan("bullish", 5.0)
    gs.stamp_gap_sizing(plan, _frame())
    monkeypatch.setattr(account, "compute_position_size", unavailable)
    assert gs.size_for_plan(plan) is None
    assert band_sizing_verdict(plan) == "risk_sizing"


def test_band_stamp_uses_only_the_supplied_completed_frame(monkeypatch):
    from tests.planning.test_gap_sizing import _signed_gaps

    monkeypatch.setattr(config, "LONG_GAP_SIZING", True)
    full = _signed_gaps()
    creating_frame = full.iloc[:-1].copy()
    before = _plan("bullish", 5.0)
    gs.stamp_gap_sizing(before, creating_frame)
    full.iloc[-1, full.columns.get_loc("Open")] = 1.0
    after = _plan("bullish", 5.0)
    gs.stamp_gap_sizing(after, full.iloc[:-1])
    assert before.gap_sizing == after.gap_sizing
    assert before.gap_sizing["down_gap_p99_pct"] == pytest.approx(6.0)
    sizing = gs.size_for_plan(before)
    monkeypatch.setattr(config, "LONG_GAP_SIZING", False)
    assert gs.size_for_plan(before) == sizing

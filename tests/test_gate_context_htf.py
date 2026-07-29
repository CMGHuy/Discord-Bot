from swingbot.core.gate.context_htf import check_htf_alignment, htf_trend
from swingbot.core.gate.registry import CHECKS
from tests.fixtures.gate import downtrend_daily, make_plan, range_daily, uptrend_daily


def test_htf_trend_three_states():
    assert htf_trend(uptrend_daily())["weekly"] == "up"
    assert htf_trend(downtrend_daily())["weekly"] == "down"
    assert htf_trend(range_daily(90, 110, n=300))["weekly"] == "range"


def test_short_history_is_range_with_detail():
    result = htf_trend(uptrend_daily(n=100))     # ~20 weekly bars
    assert result["weekly"] == "range"
    assert "insufficient" in result["detail"]


def test_daily_state_present():
    assert htf_trend(uptrend_daily())["daily"] == "up"


def test_htf_alignment_four_outcomes():
    up, down = uptrend_daily(), downtrend_daily()
    bull, bear = make_plan(direction="bullish"), make_plan(direction="bearish")
    assert check_htf_alignment(up, bull, None).status == "pass"
    assert check_htf_alignment(down, bear, None).status == "pass"     # mirror
    assert check_htf_alignment(down, bull, None).status == "fail"     # against trend
    assert check_htf_alignment(uptrend_daily(n=100), bull, None).status == "warn"  # range
    result = check_htf_alignment(down, bull, None)
    assert result.evidence["weekly"] == "down" and "daily" in result.evidence


def test_htf_alignment_registered():
    spec = CHECKS["htf_alignment"]
    assert spec.section == "context" and spec.weight == 12.0
    assert spec.hard_block is False and spec.applies_to is None

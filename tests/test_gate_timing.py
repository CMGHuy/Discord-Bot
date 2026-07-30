from swingbot.core.gate.registry import CHECKS
from swingbot.core.gate.timing import check_trigger_objective
from tests.fixtures.gate import uptrend_daily
from tests.fixtures.gate.plans import make_plan


def test_well_formed_plan_passes():
    assert check_trigger_objective(uptrend_daily(), make_plan(), None).status == "pass"


def test_priceless_plan_fails_hard():
    broken = make_plan(trigger_price=None)
    result = check_trigger_objective(uptrend_daily(), broken, None)
    assert result.status == "fail"
    assert CHECKS["trigger_objective"].hard_block is True


def test_unknown_entry_type_fails():
    weird = make_plan(entry_type="vibes")
    assert check_trigger_objective(uptrend_daily(), weird, None).status == "fail"

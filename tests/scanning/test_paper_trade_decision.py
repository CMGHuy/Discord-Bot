"""v81 paper-trade decision shared by scan_run and the order ticket."""
from swingbot.core.scanning.analyze import ScanItem, paper_trade_decision
from swingbot.core.scanning.embeds import RequirementCheck


def _item(*passed):
    requirements = [RequirementCheck(key=f"k{i}", label=f"Gate {i}", passed=ok,
                                     detail=f"detail {i}")
                    for i, ok in enumerate(passed)]
    return ScanItem(result=None, plan=None, conf=None, requirements=requirements)


def test_clean_and_empty_items_are_logged():
    assert paper_trade_decision(_item(True, True), False) == (True, None)
    assert paper_trade_decision(_item(), False) == (True, None)


def test_already_open_wins_over_failed_gates():
    assert paper_trade_decision(_item(False), True) == (False, "already open")


def test_unmet_requirements_are_named():
    assert paper_trade_decision(_item(True, False, False), False) == (
        False, "unmet: Gate 1: detail 1; Gate 2: detail 2")


def test_scan_items_default_to_not_logged():
    assert (_item().paper_logged, _item().not_logged_reason) == (False, None)

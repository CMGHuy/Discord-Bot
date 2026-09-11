from swingbot.core.planning.plan_engine import badge_stats_line, stamp_badge
from swingbot.core.backtesting.registry import get_badge

from tests.helpers import registry_strategy_row
from tests.planning.test_plan_engine_model import _plan


def test_stamp_validated():
    row = registry_strategy_row("VALIDATED")
    p = _plan(strategy=row["strategy"])
    stamp_badge(p)
    assert p.badge == "VALIDATED"
    assert p.badge_stats["win_rate"] == row["win_rate"]


def test_stamp_weak():
    p = _plan(strategy=registry_strategy_row("WEAK")["strategy"])
    stamp_badge(p)
    assert p.badge == "WEAK"


def test_stats_line():
    row = registry_strategy_row("VALIDATED")
    line = badge_stats_line(get_badge("strategy", row["strategy"]))
    assert f"N={row['n']}" in line and f"{row['win_rate']:.1f}%" in line

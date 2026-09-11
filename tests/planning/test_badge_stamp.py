from swingbot.core.planning.plan_engine import badge_stats_line, stamp_badge
from swingbot.core.backtesting.registry import get_badge

from tests.planning.test_plan_engine_model import _plan


def test_stamp_fibonacci_current_weak_badge():
    p = _plan(strategy="Fibonacci")
    stamp_badge(p)
    assert p.badge == "WEAK"
    assert p.badge_stats["win_rate"] == 35.4


def test_stamp_weak():
    # EMA Crossover stays WEAK under the current registry.
    p = _plan(strategy="EMA Crossover")
    stamp_badge(p)
    assert p.badge == "WEAK"


def test_stats_line():
    line = badge_stats_line(get_badge("strategy", "Fibonacci"))
    assert "N=246" in line and "35.4%" in line

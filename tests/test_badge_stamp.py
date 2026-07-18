from swingbot.core.plan_engine import badge_stats_line, stamp_badge
from swingbot.core.registry import get_badge

from tests.test_plan_engine_model import _plan


def test_stamp_validated():
    # Numbers from the exit-v2 validation single run (Task 32, 2026-07-18).
    p = _plan(strategy="Fibonacci")
    stamp_badge(p)
    assert p.badge == "VALIDATED"
    assert p.badge_stats["win_rate"] == 82.3


def test_stamp_weak():
    # EMA Crossover stayed WEAK through the rescue round (RSI, the previous
    # exemplar, was rescued to VALIDATED in Tasks 95-97).
    p = _plan(strategy="EMA Crossover")
    stamp_badge(p)
    assert p.badge == "WEAK"


def test_stats_line():
    line = badge_stats_line(get_badge("strategy", "Fibonacci"))
    assert "N=203" in line and "82.3%" in line

from swingbot.core.plan_engine import badge_stats_line, stamp_badge
from swingbot.core.registry import get_badge

from tests.test_plan_engine_model import _plan


def test_stamp_validated():
    p = _plan(strategy="Fibonacci")
    stamp_badge(p)
    assert p.badge == "VALIDATED"
    assert p.badge_stats["win_rate"] == 81.6


def test_stamp_weak():
    p = _plan(strategy="RSI")
    stamp_badge(p)
    assert p.badge == "WEAK"


def test_stats_line():
    line = badge_stats_line(get_badge("strategy", "Fibonacci"))
    assert "N=206" in line and "81.6%" in line

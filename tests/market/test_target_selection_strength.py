"""v36 Task 4: prefer better-tested levels as a TIEBREAKER in target
selection. Distance/method-count remain primary -- strength only decides
among candidates the distance logic already judges comparable. See
plan_engine._select_target for the full contract."""
from swingbot import config
from swingbot.core.market.levels import Level
from swingbot.core.planning.plan_engine import _select_target


def test_better_tested_level_wins_between_two_equal_candidates(monkeypatch):
    """Two candidates at the same distance with the same method count: the one
    price has actually respected should win."""
    monkeypatch.setattr(config, "LEVEL_TOUCH_STRENGTH", True)
    weak = Level(price=110.0, sources=["EMA"],
                 strength={"score": 0.2, "touches": 4, "rejections": 0,
                           "breaks": 4, "available": True})
    strong = Level(price=110.2, sources=["EMA"],
                   strength={"score": 0.9, "touches": 4, "rejections": 4,
                             "breaks": 0, "available": True})
    assert _select_target([weak, strong], entry=100.0).price == 110.2


def test_ungraded_level_is_not_penalised_against_a_graded_one(monkeypatch):
    """available=False is neutral, not weak. A brand-new level must still be
    selectable on its other merits."""
    monkeypatch.setattr(config, "LEVEL_TOUCH_STRENGTH", True)
    ungraded = Level(price=110.0, sources=["EMA", "VWAP", "Fibonacci"],
                     strength={"score": 0.5, "touches": 0, "rejections": 0,
                               "breaks": 0, "available": False})
    graded = Level(price=110.2, sources=["EMA"],
                   strength={"score": 0.6, "touches": 2, "rejections": 1,
                             "breaks": 1, "available": True})
    assert _select_target([ungraded, graded], entry=100.0).price == 110.0


def test_selection_unchanged_when_flag_off(monkeypatch):
    monkeypatch.setattr(config, "LEVEL_TOUCH_STRENGTH", False)
    weak = Level(price=110.0, sources=["EMA"],
                 strength={"score": 0.1, "touches": 4, "rejections": 0,
                           "breaks": 4, "available": True})
    strong = Level(price=110.2, sources=["EMA"],
                   strength={"score": 0.9, "touches": 4, "rejections": 4,
                             "breaks": 0, "available": True})
    assert _select_target([weak, strong], entry=100.0).price == 110.0

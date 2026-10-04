from swingbot import config
from swingbot.core.backtesting.arms import reachability as reach

KNOBS = ("RUNNER_STRUCTURE_EXIT", "RUNNER_HL_TRAIL_ATR_BUFFER", "RUNNER_STALL_RANGE_MAX")


def _field(attr):
    return next(f for f in config.FIELDS if f.attr == attr)


def test_defaults_and_search_class():
    assert config._cast(_field("RUNNER_STRUCTURE_EXIT"), "off") == "off"
    assert config._cast(_field("RUNNER_HL_TRAIL_ATR_BUFFER"), _field("RUNNER_HL_TRAIL_ATR_BUFFER").default) == 0.0
    assert config._cast(_field("RUNNER_STALL_RANGE_MAX"), _field("RUNNER_STALL_RANGE_MAX").default) == 1.0
    assert set(KNOBS) <= set(config.searchable_attrs())


def test_invalid_mode_falls_back_to_off():
    assert config._cast(_field("RUNNER_STRUCTURE_EXIT"), "HL_TRAIL") == "hl_trail"
    assert config._cast(_field("RUNNER_STRUCTURE_EXIT"), "bogus") == "off"


def test_unwired_knobs_are_refused_by_the_producer():
    for attr in KNOBS:
        assert reach.classify(attr) == reach.OUTSIDE_REPLAY

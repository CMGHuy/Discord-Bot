from swingbot import config

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


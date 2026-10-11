"""v135 knobs: a three-way scope and a minimum-room multiple, both off by default."""

from swingbot import config


GRID = (0.5, 0.75, 1.0)


def _field(key):
    return next(field for field in config.FIELDS if field.key == key)


def test_scope_is_a_three_way_select_defaulting_off():
    field = _field("HEADROOM_SCOPE")
    assert field.type == "select" and field.default == "off" and field.hot_reloadable
    assert [value for value, _ in field.options] == ["off", "strategy", "confluence"]
    assert config.HEADROOM_SCOPE == "off"


def test_a_malformed_scope_falls_back_to_off():
    field = _field("HEADROOM_SCOPE")
    assert config._cast(field, "Strategy") == "strategy"
    assert config._cast(field, "CONFLUENCE") == "confluence"
    for bad in ("both", "", "strategy,confluence"):
        assert config._cast(field, bad) == "off"


def test_min_r_defaults_to_zero_meaning_off():
    field = _field("HEADROOM_MIN_R")
    assert field.type == "float" and config._cast(field, field.default) == 0.0
    assert config.HEADROOM_MIN_R == 0.0


def test_the_frozen_grid_fits_inside_the_field_bounds():
    field = _field("HEADROOM_MIN_R")
    assert all(field.min <= value <= field.max for value in GRID)


def test_the_field_cannot_exceed_one_r():
    """Above 1.0 the plan's own TP1 (floor MIN_RISK_REWARD_RATIO = 1.5) could become its blocker."""
    assert _field("HEADROOM_MIN_R").max == 1

"""v122 knobs: a three-way scope and a ratio, both off by default."""

from swingbot import config


GRID = (0.60, 0.75, 0.90)


def _field(key):
    return next(field for field in config.FIELDS if field.key == key)


def test_scope_is_a_three_way_select_defaulting_off():
    field = _field("PULLBACK_DRYUP_SCOPE")
    assert field.type == "select" and field.default == "off" and field.hot_reloadable
    assert [value for value, _ in field.options] == ["off", "strategy", "confluence"]
    assert config.PULLBACK_DRYUP_SCOPE == "off"


def test_a_malformed_scope_falls_back_to_off():
    field = _field("PULLBACK_DRYUP_SCOPE")
    assert config._cast(field, "Strategy") == "strategy"
    assert config._cast(field, "CONFLUENCE") == "confluence"
    for bad in ("both", "", "strategy,confluence"):
        assert config._cast(field, bad) == "off"


def test_max_ratio_defaults_to_zero_meaning_off():
    field = _field("PULLBACK_DRYUP_MAX_RATIO")
    assert field.type == "float" and config._cast(field, field.default) == 0.0
    assert config.PULLBACK_DRYUP_MAX_RATIO == 0.0


def test_the_frozen_grid_fits_inside_the_field_bounds():
    field = _field("PULLBACK_DRYUP_MAX_RATIO")
    assert all(field.min <= value <= field.max for value in GRID)

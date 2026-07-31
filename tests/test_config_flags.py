from swingbot import config


def test_flags_default_to_fully_live():
    assert config.PLAN_ENGINE_V2 == "on"
    assert config.INTRADAY_MANAGER_V2 is True


def test_scale_out_enabled_field_removed():
    """Plan v8 Task V4: SCALE_OUT_ENABLED was a documented-but-dead flag --
    plan_manager.py never read it, scale-out was hardcoded on regardless.
    Deleted rather than wired, so it can't look controllable when it isn't.
    This guards against it quietly reappearing."""
    assert not hasattr(config, "SCALE_OUT_ENABLED")
    assert not any(f.attr == "SCALE_OUT_ENABLED" for f in config.FIELDS)


def test_target_floor_fields_are_live_and_hot_reloadable():
    """Plan v8 Task V9: the floor has to be a real Field, not a module
    constant -- that's what makes it hot-reloadable and visible in the admin
    Settings page, which V27's shadow week and V28's enforcement both need."""
    assert config.MIN_TARGET_PCT == 2.5
    assert config.TARGET_FLOOR_ENABLED is True
    f = next(f for f in config.FIELDS if f.attr == "MIN_TARGET_PCT")
    assert (f.min, f.max) == (0, 20)
    assert f.hot_reloadable


def test_plan_engine_v2_choices():
    f = next(f for f in config.FIELDS if f.attr == "PLAN_ENGINE_V2")
    assert {v for v, _ in f.options} == {"off", "shadow", "on"}


def test_invalid_mode_falls_back_to_off():
    f = next(f for f in config.FIELDS if f.attr == "PLAN_ENGINE_V2")
    assert config._cast(f, "banana") == "off"
    assert config._cast(f, "SHADOW") == "shadow"

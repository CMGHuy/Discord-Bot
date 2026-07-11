from swingbot import config


def test_flags_exist_with_safe_defaults():
    assert config.PLAN_ENGINE_V2 == "off"
    assert config.SCALE_OUT_ENABLED is False
    assert config.INTRADAY_MANAGER_V2 is False


def test_plan_engine_v2_choices():
    f = next(f for f in config.FIELDS if f.attr == "PLAN_ENGINE_V2")
    assert {v for v, _ in f.options} == {"off", "shadow", "on"}


def test_invalid_mode_falls_back_to_off():
    f = next(f for f in config.FIELDS if f.attr == "PLAN_ENGINE_V2")
    assert config._cast(f, "banana") == "off"
    assert config._cast(f, "SHADOW") == "shadow"

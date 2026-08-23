from swingbot import config


def test_flags_default_to_fully_live():
    assert config.PLAN_ENGINE_V2 == "on"
    assert config.SCALE_OUT_ENABLED is True
    assert config.INTRADAY_MANAGER_V2 is True


def test_plan_engine_v2_choices():
    f = next(f for f in config.FIELDS if f.attr == "PLAN_ENGINE_V2")
    assert {v for v, _ in f.options} == {"off", "shadow", "on"}


def test_invalid_mode_falls_back_to_off():
    f = next(f for f in config.FIELDS if f.attr == "PLAN_ENGINE_V2")
    assert config._cast(f, "banana") == "off"
    assert config._cast(f, "SHADOW") == "shadow"


def test_v47_throughput_fields_exist_with_documented_defaults():
    """v47: the scan's cache-freshness bar, the cold-fetch cutover point and
    the process-pool size are all configurable, and their defaults match the
    spec. FETCH_WORKERS=0 means auto -- a Field default is a string cast by
    int(), so a computed cpu_count default cannot live in the schema."""
    by_key = {f.key: f for f in config.FIELDS}

    assert by_key["SCAN_CACHE_MAX_AGE_HOURS"].default == "6"
    assert by_key["COLD_FETCH_PROCESS_THRESHOLD"].default == "10"
    assert by_key["FETCH_WORKERS"].default == "0"

    # All three are integers on the module after parsing, not raw strings.
    assert isinstance(config.SCAN_CACHE_MAX_AGE_HOURS, int)
    assert isinstance(config.COLD_FETCH_PROCESS_THRESHOLD, int)
    assert isinstance(config.FETCH_WORKERS, int)

    # The scan's freshness bar must sit BELOW data_refresh's own 12h daily
    # window, or the scan would trust a frame the refresh loop already
    # considers due for replacement.
    from swingbot.core.marketdata.data_refresh import REFRESH_HOURS
    assert config.SCAN_CACHE_MAX_AGE_HOURS < REFRESH_HOURS["daily"]

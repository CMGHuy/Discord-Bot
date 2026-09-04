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
    """v47: the scan's cache-freshness bar and the offline-replay process-pool
    size are configurable, and their defaults match the spec. FETCH_WORKERS=0
    means auto -- a Field default is a string cast by int(), so a computed
    cpu_count default cannot live in the schema."""
    by_key = {f.key: f for f in config.FIELDS}

    assert by_key["SCAN_CACHE_MAX_AGE_HOURS"].default == "6"
    assert by_key["FETCH_WORKERS"].default == "0"

    # Both are integers on the module after parsing, not raw strings.
    assert isinstance(config.SCAN_CACHE_MAX_AGE_HOURS, int)
    assert isinstance(config.FETCH_WORKERS, int)

    # The scan's freshness bar must sit BELOW data_refresh's own 12h daily
    # window, or the scan would trust a frame the refresh loop already
    # considers due for replacement.
    from swingbot.core.marketdata.data_refresh import REFRESH_HOURS
    assert config.SCAN_CACHE_MAX_AGE_HOURS < REFRESH_HOURS["daily"]


def test_v55_batch_fetch_fields_exist_with_documented_defaults():
    """v55: the scan's batched cold-OHLCV and live-price fetches are all
    configurable, and their defaults match the spec."""
    by_key = {f.key: f for f in config.FIELDS}

    assert by_key["BATCH_FETCH_CHUNK_SIZE"].default == "100"
    assert by_key["COLD_FETCH_TIMEOUT_SECONDS"].default == "180"
    assert by_key["LIVE_PRICE_TIMEOUT_SECONDS"].default == "60"

    assert isinstance(config.BATCH_FETCH_CHUNK_SIZE, int)
    assert isinstance(config.COLD_FETCH_TIMEOUT_SECONDS, int)
    assert isinstance(config.LIVE_PRICE_TIMEOUT_SECONDS, int)


def test_intraday_rth_only_defaults_on():
    assert config.INTRADAY_RTH_ONLY is True


def test_v70_extended_hours_fields_exist_with_documented_defaults():
    """v70: the extended-hours exit check ships on, the quiet window is
    23:00-08:00 ET, and a breach needs two consecutive polls to confirm."""
    by_key = {f.key: f for f in config.FIELDS}

    assert by_key["EXTENDED_HOURS_EXIT_CHECK"].default == "true"
    assert by_key["QUIET_HOURS_START_ET"].default == "23"
    assert by_key["QUIET_HOURS_END_ET"].default == "8"
    assert by_key["EXTENDED_HOURS_DEBOUNCE_TICKS"].default == "2"

    assert isinstance(config.EXTENDED_HOURS_EXIT_CHECK, bool)
    assert isinstance(config.QUIET_HOURS_START_ET, int)
    assert isinstance(config.QUIET_HOURS_END_ET, int)
    assert isinstance(config.EXTENDED_HOURS_DEBOUNCE_TICKS, int)

    assert by_key["EXTENDED_HOURS_EXIT_CHECK"].section == "Plan Engine v2"


def test_health_config_fields_exist_with_documented_defaults():
    from swingbot import config

    assert config.HEALTH_ALERT_AFTER_FAILURES == 3
    assert hasattr(config, "DISCORD_CHANNEL_OPS_ID")

    # FIELDS (config.py:95) is the single source of truth for every
    # .env-driven setting; a field missing from it is invisible to the
    # admin UI and to SIGHUP hot-reload.
    keys = {f.key for f in config.FIELDS}
    assert "DISCORD_CHANNEL_OPS_ID" in keys
    assert "HEALTH_ALERT_AFTER_FAILURES" in keys
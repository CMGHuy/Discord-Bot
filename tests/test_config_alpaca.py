from swingbot import config

def test_alpaca_fields_declared_with_safe_defaults():
    keys = {f.key: f for f in config.FIELDS}
    for k in ("ALPACA_ENABLED", "ALPACA_API_KEY_ID", "ALPACA_API_SECRET_KEY",
              "ALPACA_DATA_FEED_LIVE", "ALPACA_TIMEOUT_SECONDS",
              "ALPACA_MAX_TRADE_AGE_SECONDS", "ALPACA_BREAKER_FAILURES",
              "ALPACA_BREAKER_COOLDOWN_SECONDS"):
        assert k in keys, k
        assert keys[k].section == "Data Sources"
    assert keys["ALPACA_ENABLED"].default == "false"
    assert keys["ALPACA_API_SECRET_KEY"].sensitive is True
    assert keys["ALPACA_API_KEY_ID"].sensitive is True
    assert keys["ALPACA_DATA_FEED_LIVE"].default == "iex"

def test_alpaca_disabled_by_default():
    assert config.ALPACA_ENABLED is False

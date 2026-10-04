from swingbot import config

def test_alpaca_fields_declared_with_safe_defaults():
    keys = {f.key: f for f in config.FIELDS}
    for k in ("ALPACA_ENABLED", "ALPACA_API_KEY_ID", "ALPACA_API_SECRET_KEY",
              "ALPACA_DATA_FEED_LIVE", "ALPACA_TIMEOUT_SECONDS",
              "ALPACA_MAX_TRADE_AGE_SECONDS", "ALPACA_BREAKER_FAILURES",
              "ALPACA_BREAKER_COOLDOWN_SECONDS"):
        assert k in keys, k
        assert keys[k].section == "Data Sources"
    # v106 soak (T13) accepted 2026-10-02 (clause (d) PASS 2026-09-27; (a)-(c)
    # judged at soak close) -- default flipped on. Still safe with no keys
    # set: the router's _active_provider() requires ALPACA_API_KEY_ID and
    # falls back to yfinance for everything otherwise (test_provider_router.py).
    assert keys["ALPACA_ENABLED"].default == "true"
    assert keys["ALPACA_API_KEY_ID"].default == "" and keys["ALPACA_API_SECRET_KEY"].default == ""
    assert keys["ALPACA_API_SECRET_KEY"].sensitive is True
    assert keys["ALPACA_API_KEY_ID"].sensitive is True
    assert keys["ALPACA_DATA_FEED_LIVE"].default == "iex"

def test_alpaca_enabled_by_default_is_harmless_without_keys():
    """Enabled with no keys configured must behave exactly like disabled --
    a fresh install with an empty .env gets pre-v106 yfinance behaviour, not
    a startup failure or a hang waiting on Alpaca."""
    assert config.ALPACA_ENABLED is True
    assert config.ALPACA_API_KEY_ID == ""

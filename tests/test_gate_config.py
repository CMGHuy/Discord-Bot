from swingbot import config


def field(key):
    return next((f for f in config.FIELDS if f.key == key), None)


def test_gatekeeper_fields_present_with_defaults():
    expected = {  # key: (type, default)
        "GATE_ENABLED": ("checkbox", "false"),
        "GATE_MODE": ("select", "inform"),
        "GATE_MIN_TIER": ("select", "C"),
        "GATE_STRICTNESS": ("select", "balanced"),
        "MACRO_ENABLED": ("checkbox", "false"),
        "FRED_API_KEY": ("password", ""),
        "MACRO_SNAPSHOT_TTL_MIN": ("number", "30"),
        "GATE_BLACKOUT_ENABLED": ("checkbox", "false"),
        "GATE_BLACKOUT_HOURS_BEFORE": ("float", "18"),
        "GATE_BLACKOUT_HOURS_AFTER": ("float", "2"),
        "GATE_EARNINGS_BLACKOUT_DAYS": ("number", "3"),
        "GATE_MIN_DOLLAR_VOL": ("float", "2000000"),
    }
    for key, (ftype, default) in expected.items():
        f = field(key)
        assert f is not None, f"{key} missing from config.FIELDS"
        assert f.section == "Gatekeeper", key
        assert f.type == ftype, key
        assert f.default == default, key


def test_select_options_exact():
    assert [v for v, _ in field("GATE_MODE").options] == ["shadow", "inform", "enforce"]
    assert [v for v, _ in field("GATE_MIN_TIER").options] == ["A+", "A", "B", "C"]
    assert [v for v, _ in field("GATE_STRICTNESS").options] == ["strict", "balanced", "relaxed"]


def test_api_key_sensitive_and_ttl_floor():
    assert field("FRED_API_KEY").sensitive is True
    assert field("MACRO_SNAPSHOT_TTL_MIN").min == 5


def test_finnhub_key_exists_somewhere():
    # From llm-advisor L10 when merged; added here otherwise — either way it must exist.
    f = field("FINNHUB_API_KEY")
    assert f is not None and f.sensitive is True

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


def test_tier_cut_fields_ordered():
    aplus, a, b = (field(k) for k in
                   ("GATE_TIER_APLUS_CUT", "GATE_TIER_A_CUT", "GATE_TIER_B_CUT"))
    assert aplus and a and b
    assert float(aplus.default) > float(a.default) > float(b.default)


def test_every_check_has_enable_field():
    import swingbot.core.gate  # noqa: F401 — triggers registration + field injection
    from swingbot.core.gate.registry import CHECKS
    keys = {f.key for f in config.FIELDS}
    for spec in CHECKS.values():
        assert spec.config_flag in keys, spec.check_id


def test_every_threshold_has_field_with_bounds():
    import swingbot.core.gate  # noqa: F401
    from swingbot.core.gate.registry import CHECKS
    by_key = {f.key: f for f in config.FIELDS}
    for spec in CHECKS.values():
        for th in spec.thresholds.values():
            key = f"GATE_TH_{spec.check_id.upper()}_{th.name.upper()}"
            f = by_key.get(key)
            assert f is not None, key
            assert f.min == th.min and f.max == th.max and f.step == th.step
            assert float(f.default) == th.presets["balanced"]


def test_preset_application_and_override_survival(monkeypatch):
    import swingbot.core.gate  # noqa: F401
    from swingbot.core.gate.registry import CHECKS, apply_strictness_preset
    seed = apply_strictness_preset("relaxed")
    assert seed, "no thresholds found"
    spec = CHECKS["rr_realistic"]
    key = "GATE_TH_RR_REALISTIC_MIN_RR"
    assert seed[key] == spec.thresholds["min_rr"].presets["relaxed"]
    # an individually-overridden threshold (value matching NO preset)
    # survives a preset switch
    monkeypatch.setattr(config, key, 1.37, raising=False)
    assert key not in apply_strictness_preset("strict")

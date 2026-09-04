"""The veto's config surface: three knobs, not seven."""
import pytest

from swingbot import config
from swingbot.core.market.chart_patterns import (
    DEFAULT_DCB_PARAMS, params_from_config,
)


def test_the_veto_ships_off():
    field = next(f for f in config.FIELDS if f.key == "DEAD_CAT_BOUNCE_VETO")
    assert field.default == "false"


def test_only_the_grid_dimensions_are_configurable():
    keys = {f.key for f in config.FIELDS}
    assert {"DCB_DECLINE_PCT", "DCB_GAP_REQUIRED", "DCB_VOLUME_RATIO"} <= keys
    # The four fixed values must NOT be knobs -- tuning what the spec fixed
    # would be a different pre-registration wearing this one's clothes.
    for fixed in ("DCB_LOOKBACK", "DCB_RETRACE_MAX",
                  "DCB_BOUNCE_MIN_BARS", "DCB_GAP_PCT"):
        assert fixed not in keys, f"{fixed} must stay a module constant"


def test_params_from_config_carries_the_fixed_values_through(monkeypatch):
    monkeypatch.setattr(config, "DCB_DECLINE_PCT", 25.0)
    got = params_from_config()
    assert got["decline_pct"] == 25.0
    assert got["lookback"] == DEFAULT_DCB_PARAMS["lookback"]
    assert got["retrace_max"] == DEFAULT_DCB_PARAMS["retrace_max"]


def test_a_volume_ratio_of_zero_disables_the_arm(monkeypatch):
    # 0 is how a checkbox-free numeric field spells "off" in .env; None is how
    # the detector spells it. One place translates.
    monkeypatch.setattr(config, "DCB_VOLUME_RATIO", 0.0)
    assert params_from_config()["volume_ratio"] is None


def test_a_real_volume_ratio_is_passed_through(monkeypatch):
    monkeypatch.setattr(config, "DCB_VOLUME_RATIO", 0.8)
    assert params_from_config()["volume_ratio"] == 0.8

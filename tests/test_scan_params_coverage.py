"""The ScanParams surface and config classification must agree exactly."""
import dataclasses

from swingbot import config
from swingbot.scan_params import ScanParams


VALID = {"searchable", "frozen", "live_only", "never", "excluded"}


def test_every_field_has_a_valid_class():
    for field in config.FIELDS:
        assert field.search_class in VALID, field.attr


def test_scan_params_covers_exactly_the_non_excluded_config_fields():
    in_params = {field.name.upper() for field in dataclasses.fields(ScanParams)}
    in_config = {field.attr for field in config.FIELDS
                 if field.search_class in ("searchable", "frozen", "never")}
    assert in_config - in_params == set()
    assert in_params - in_config == set()


def test_searchable_attrs_excludes_frozen_never_and_live_only():
    attrs = set(config.searchable_attrs())
    assert "MIN_RISK_REWARD_RATIO" not in attrs
    assert "SLIPPAGE_BPS" not in attrs
    assert "NEAR_TP_TIMEOUT_MINUTES" not in attrs
    assert "DISCORD_TOKEN" not in attrs
    assert "MIN_TARGET_CONFLUENCE_COUNT" in attrs


def test_measurement_fidelity_knobs_are_never_searchable():
    for attr in ("SLIPPAGE_BPS", "COMMISSION_PER_TRADE", "COMMISSION_RISK_BASIS"):
        field = next(field for field in config.FIELDS if field.attr == attr)
        assert field.search_class == "never"

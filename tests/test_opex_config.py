"""The opex settings must exist, default safe, and be discoverable.

`.env.example` presence is already covered globally by
tests/test_env_example_sync.py; what is asserted here is the part that file
cannot check -- that the master switch ships OFF.
"""
from swingbot import config


OPEX_SETTINGS = (
    "OPEX_CAUTION_ENABLED",
    "OPEX_MONTHLY_CONFIDENCE_BUMP",
    "OPEX_MONTHLY_CONFLUENCE_BUMP",
    "OPEX_WEEKLY_CONFLUENCE_BUMP",
    "OPEX_NEAR_CLOSE_SUPPRESS_MINUTES",
    "OPEX_STOP_WIDEN_PCT",
    "OPEX_SIZE_REDUCTION_PCT",
)


def test_every_opex_setting_is_defined():
    for name in OPEX_SETTINGS:
        assert hasattr(config, name), f"{name} missing from the config schema"


def test_master_switch_defaults_off():
    # Ships inert: every downstream helper short-circuits on this being
    # False, so the feature cannot change behaviour until it is validated
    # and turned on deliberately.
    assert config.OPEX_CAUTION_ENABLED is False


def test_bumps_are_non_negative_integers():
    for name in ("OPEX_MONTHLY_CONFIDENCE_BUMP",
                 "OPEX_MONTHLY_CONFLUENCE_BUMP",
                 "OPEX_WEEKLY_CONFLUENCE_BUMP",
                 "OPEX_NEAR_CLOSE_SUPPRESS_MINUTES"):
        value = getattr(config, name)
        assert isinstance(value, int) and value >= 0, (name, value)


def test_reduction_percentages_are_in_range():
    assert 0 <= config.OPEX_STOP_WIDEN_PCT <= 100
    assert 0 <= config.OPEX_SIZE_REDUCTION_PCT < 100

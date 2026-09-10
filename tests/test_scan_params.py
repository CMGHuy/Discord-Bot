"""Contracts for the frozen, process-safe scan parameter value."""
import dataclasses
import pickle

import pytest

from swingbot import config
from swingbot.scan_params import ScanParams


def test_from_config_reads_the_shipped_defaults():
    params = ScanParams.from_config()
    assert params.min_target_confluence_count == config.MIN_TARGET_CONFLUENCE_COUNT
    assert params.min_risk_reward_ratio == config.MIN_RISK_REWARD_RATIO
    assert params.min_reward_pct == config.MIN_REWARD_PCT
    assert params.avwap_levels_enabled == config.AVWAP_LEVELS_ENABLED


def test_is_frozen():
    with pytest.raises(dataclasses.FrozenInstanceError):
        ScanParams.from_config().min_target_confluence_count = 99


def test_survives_a_pickle_round_trip():
    params = ScanParams.from_config()
    assert pickle.loads(pickle.dumps(params)) == params


def test_replace_produces_an_independent_value():
    params = ScanParams.from_config()
    replacement = dataclasses.replace(params, min_target_confluence_count=1)
    assert replacement.min_target_confluence_count == 1
    assert params.min_target_confluence_count == config.MIN_TARGET_CONFLUENCE_COUNT
    assert replacement != params


def test_every_field_is_immutable_typed():
    params = ScanParams.from_config()
    for field in dataclasses.fields(ScanParams):
        assert not isinstance(getattr(params, field.name), (list, dict, set)), field.name

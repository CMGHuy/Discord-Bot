import pytest

from swingbot import config
from swingbot.core.backtesting.arms.knobs import apply_knobs, parse_knob


def test_parse_casts_through_the_config_field_type():
    assert parse_knob("STALL_EXIT_ENABLED=true") == ("STALL_EXIT_ENABLED", True)
    attr, value = parse_knob("TIGHTEN_TRIGGER_R=2.5")
    assert attr == "TIGHTEN_TRIGGER_R" and value == 2.5


@pytest.mark.parametrize("bad", ["NOEQUALS", "=1", "NOT_A_FIELD=1"])
def test_parse_rejects_malformed_or_unknown(bad):
    with pytest.raises(ValueError):
        parse_knob(bad)


def test_apply_knobs_sets_and_restores():
    before = config.MIN_REWARD_PCT
    with apply_knobs({"MIN_REWARD_PCT": before + 1.0}):
        assert config.MIN_REWARD_PCT == before + 1.0
    assert config.MIN_REWARD_PCT == before


def test_apply_knobs_restores_on_error():
    before = config.MIN_REWARD_PCT
    with pytest.raises(RuntimeError):
        with apply_knobs({"MIN_REWARD_PCT": before + 1.0}):
            raise RuntimeError("boom")
    assert config.MIN_REWARD_PCT == before

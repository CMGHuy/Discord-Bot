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


from swingbot.core.backtesting.arms.knobs import GAP_RECLAIM_NEEDS_NEXT_OPEN


def test_parse_casts_the_v192_knobs():
    assert parse_knob("MARKET_ENTRY_NEXT_OPEN=true") == ("MARKET_ENTRY_NEXT_OPEN", True)
    assert parse_knob("GAP_RECLAIM_ATR=0.25") == ("GAP_RECLAIM_ATR", 0.25)


def test_gap_reclaim_without_next_open_is_refused_and_config_restored(monkeypatch):
    monkeypatch.setattr(config, "MARKET_ENTRY_NEXT_OPEN", False)
    monkeypatch.setattr(config, "GAP_RECLAIM_ATR", 0.0)
    with pytest.raises(ValueError, match="needs MARKET_ENTRY_NEXT_OPEN on") as info:
        with apply_knobs({"GAP_RECLAIM_ATR": 0.25}):
            raise AssertionError("the body must not run")
    assert str(info.value) == GAP_RECLAIM_NEEDS_NEXT_OPEN
    assert config.GAP_RECLAIM_ATR == 0.0 and config.MARKET_ENTRY_NEXT_OPEN is False


def test_gap_reclaim_with_next_open_in_the_same_delta_runs(monkeypatch):
    monkeypatch.setattr(config, "MARKET_ENTRY_NEXT_OPEN", False)
    monkeypatch.setattr(config, "GAP_RECLAIM_ATR", 0.0)
    with apply_knobs({"MARKET_ENTRY_NEXT_OPEN": True, "GAP_RECLAIM_ATR": 0.25}):
        assert config.MARKET_ENTRY_NEXT_OPEN is True and config.GAP_RECLAIM_ATR == 0.25
    assert config.GAP_RECLAIM_ATR == 0.0 and config.MARKET_ENTRY_NEXT_OPEN is False


def test_the_guard_reads_the_merged_config(monkeypatch):
    """The baseline arm runs MARKET_ENTRY_NEXT_OPEN=true alone; the component adds the
    gap. A next-open already on in config satisfies a gap-only delta."""
    monkeypatch.setattr(config, "MARKET_ENTRY_NEXT_OPEN", True)
    monkeypatch.setattr(config, "GAP_RECLAIM_ATR", 0.0)
    with apply_knobs({"GAP_RECLAIM_ATR": 0.10}):
        assert config.GAP_RECLAIM_ATR == 0.10
    with pytest.raises(ValueError):
        with apply_knobs({"MARKET_ENTRY_NEXT_OPEN": False, "GAP_RECLAIM_ATR": 0.10}):
            pass
    assert config.MARKET_ENTRY_NEXT_OPEN is True and config.GAP_RECLAIM_ATR == 0.0


def test_an_empty_delta_never_trips_the_guard():
    with apply_knobs({}):
        pass

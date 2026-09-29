"""The StateStore debounce contract, unchanged across backends."""
import os

import pytest

from swingbot import config
from swingbot.core.infra.state import StateStore


@pytest.fixture(params=["", "state:dual", "state:db"])
def any_stage(request, tmp_path, monkeypatch, db_committed, db_engine):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "DB_STORES", request.param)
    monkeypatch.setattr(
        config, "DATABASE_URL", db_engine.url.render_as_string(hide_password=False)
    )
    from swingbot.core.db.engine import reset_engine
    reset_engine()
    return request.param


def test_first_sighting_does_not_fire(any_stage):
    assert StateStore().confirm_or_update("K", "bullish") is False


def test_second_consecutive_sighting_fires(any_stage):
    store = StateStore()
    assert store.confirm_or_update("K", "bullish") is False
    assert store.confirm_or_update("K", "bullish") is True


def test_it_fires_exactly_once(any_stage):
    store = StateStore()
    store.confirm_or_update("K", "bullish")
    store.confirm_or_update("K", "bullish")
    assert store.confirm_or_update("K", "bullish") is False


def test_a_flip_back_before_confirmation_clears_the_pending(any_stage):
    store = StateStore()
    store.confirm_or_update("K", "bullish")
    store.confirm_or_update("K", "bullish")
    store.confirm_or_update("K", "bearish")
    assert store.confirm_or_update("K", "bullish") is False
    assert store.confirm_or_update("K", "bearish") is False


def test_required_confirmations_is_honoured(any_stage):
    store = StateStore()
    for _ in range(2):
        assert store.confirm_or_update("K", "bullish", required_confirmations=3) is False
    assert store.confirm_or_update("K", "bullish", required_confirmations=3) is True


def test_keys_are_independent(any_stage):
    store = StateStore()
    store.confirm_or_update("A", "bullish")
    store.confirm_or_update("A", "bullish")
    assert store.confirm_or_update("B", "bullish") is False


def test_a_second_instance_sees_confirmed_state_at_the_db_stage(any_stage):
    if any_stage != "state:db":
        pytest.skip("cross-instance visibility is the db stage's property")
    StateStore().confirm_or_update("K", "bullish")
    assert StateStore().confirm_or_update("K", "bullish") is True


def test_no_state_json_at_the_db_stage(any_stage, tmp_path):
    if any_stage != "state:db":
        pytest.skip("file absence is only asserted at the db stage")
    StateStore().confirm_or_update("K", "bullish")
    assert not os.path.exists(os.path.join(tmp_path, "state.json"))


def test_confirmed_value_reads_the_last_confirmed_state(any_stage):
    store = StateStore()
    assert store.confirmed_value("K") is None
    store.confirm_or_update("K", "bullish")
    store.confirm_or_update("K", "bullish")
    assert store.confirmed_value("K") == "bullish"


def test_revoked_confirmation_can_fire_again(any_stage):
    """A confirmation whose alert was never posted (plan rejected at build)
    is revoked, so the same value confirms -- and fires -- again later."""
    store = StateStore()
    store.confirm_or_update("K", "bullish")
    assert store.confirm_or_update("K", "bullish") is True
    store.revoke_confirmation("K", "bullish", previous=None)
    assert store.confirmed_value("K") is None
    assert store.confirm_or_update("K", "bullish") is False
    assert store.confirm_or_update("K", "bullish") is True


def test_revoke_restores_the_previously_confirmed_value(any_stage):
    store = StateStore()
    store.confirm_or_update("K", "a")
    store.confirm_or_update("K", "a")
    store.confirm_or_update("K", "b")
    store.confirm_or_update("K", "b")
    store.revoke_confirmation("K", "b", previous="a")
    assert store.confirmed_value("K") == "a"
    assert store.confirm_or_update("K", "a") is False


def test_revoke_is_a_no_op_when_the_value_is_no_longer_confirmed(any_stage):
    store = StateStore()
    store.confirm_or_update("K", "a")
    store.confirm_or_update("K", "a")
    store.revoke_confirmation("K", "b", previous=None)
    assert store.confirmed_value("K") == "a"

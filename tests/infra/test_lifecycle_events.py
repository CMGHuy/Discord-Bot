from copy import deepcopy
import pytest
from swingbot.core.infra.lifecycle_events import make_event, validate_event

AT = "2026-10-28T12:00:00+00:00"


def payload(status="CANCELLED"):
    return dict(ticker="AAPL", direction="bullish", plan_id="P-1", trade_id=None,
                prior_status="PENDING", new_status=status, reason="manual",
                occurred_at=AT)


def event(transition="transition-1", channel="5"):
    return make_event(transition_id=transition, kind="plan_transition",
                      target_channel_id=channel, occurred_at=AT, payload=payload())


def test_identity_belongs_to_transition_and_payload_is_copied():
    data = payload()
    result = make_event(transition_id="a", kind="plan_transition",
                        target_channel_id="5", occurred_at=AT, payload=data)
    data["reason"] = "changed later"
    assert result["payload"]["reason"] == "manual"
    assert event()["event_id"] == event()["event_id"]
    assert event("another")["event_id"] != event()["event_id"]
    assert result["attempt_count"] == 0
    assert result["next_attempt_at"] == AT
    assert result["delivered_at"] is None


def test_missing_destination_is_durable_and_blocked():
    result = event(channel=None)
    assert result["blocked"] is True
    assert result["last_error"] == "destination_unresolved"
    validate_event(result)  # destination resolution is a delivery concern


@pytest.mark.parametrize("change", [
    {"kind": "unknown"}, {"payload": {}}, {"event_id": "wrong"},
    {"payload": {**payload(), "occurred_at": "2026-10-28T12:00:00"}},
    {"payload": {**payload(), "trade": {"exit_price": 42}}},
])
def test_bad_contract_is_rejected(change):
    result = deepcopy(event())
    result.update(change)
    with pytest.raises(ValueError):
        validate_event(result)

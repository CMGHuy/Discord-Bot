"""v210: the market_shock kind of the v197 notify queue -- validation only."""
from datetime import date, datetime, timezone

import pytest

from swingbot.core.infra import lifecycle_events
from swingbot.core.infra.lifecycle_events import make_event, validate_event
from swingbot.core.market import shock

AT = "2026-11-05T14:45:00+00:00"


def reading_row():
    return shock.ShockReading(
        as_of=datetime(2026, 11, 5, 14, 45, tzinfo=timezone.utc), session_date=date(2026, 11, 5),
        minutes_since_open=75.0, breadth_frac=0.42, sectors_down=5, sectors_total=8, depth_frac=0.3,
        breadth_speed=0.12, spy_atr_move=-1.8, qqq_atr_move=-2.3, spy_last=671.2,
        spy_prev_close=683.0, spy_session_low=670.9, spy_new_low=True, spy_retrace=0.05,
        vix_level=21.13, vix_chg_pct=27.2, vix_session_high=21.4, vix_off_high_pct=1.3,
        n_names=61, insufficient=False).as_row()


def payload(**over):
    return dict(label="SHOCK", prior_label="NORMAL", occurred_at=AT, reading=reading_row(),
                open_longs=[], entry_into_shock=True) | over


def event(kind="market_shock", **over):
    return make_event(transition_id=f"market_shock:{AT}", kind=kind, target_channel_id="7",
                      occurred_at=AT, payload=payload(**over))


def test_kinds_gain_market_shock_last():
    assert lifecycle_events.KINDS == ("trade_closed", "plan_transition", "market_shock")


def test_a_valid_shock_event_is_deliverable_and_needs_no_ticker():
    built = event()
    validate_event(built)
    assert built["kind"] == "market_shock" and built["target_channel_id"] == "7"
    assert built["blocked"] is False and "ticker" not in built["payload"]


def test_a_second_leg_and_the_exits_are_valid():
    validate_event(event(label="SHOCK", prior_label="RECOVERY", entry_into_shock=True))
    validate_event(event(label="RECOVERY", prior_label="SHOCK", entry_into_shock=False))
    validate_event(event(label="NORMAL", prior_label="RECOVERY", entry_into_shock=False,
                         open_longs_unavailable=False))


def test_an_unrouted_shock_event_is_stored_blocked():
    built = make_event(transition_id="t", kind="market_shock", target_channel_id=None,
                       occurred_at=AT, payload=payload())
    assert built["blocked"] is True and built["last_error"] == "destination_unresolved"


def test_the_identity_is_kind_scoped():
    shock_id = event()["event_id"]
    assert shock_id == event()["event_id"]
    assert shock_id != lifecycle_events._identity(f"market_shock:{AT}", "plan_transition")


@pytest.mark.parametrize("over,code", [
    ({"label": "CALM"}, "invalid_shock_label"),
    ({"prior_label": None}, "invalid_shock_label"),
    ({"prior_label": "SHOCK"}, "shock_notice_without_transition"),
    ({"occurred_at": "2026-11-05T14:45:00"}, "invalid_transition_time"),
    ({"reading": None}, "invalid_shock_reading"),
    ({"open_longs": {}}, "invalid_open_longs"),
    ({"open_longs_unavailable": "no"}, "invalid_open_longs"),
    ({"entry_into_shock": "yes"}, "invalid_entry_flag"),
    ({"entry_into_shock": False}, "invalid_entry_flag"),
])
def test_a_malformed_shock_payload_is_refused(over, code):
    with pytest.raises(ValueError, match=code):
        event(**over)


def test_a_lifecycle_payload_under_the_shock_kind_is_refused():
    lifecycle = dict(ticker="AAPL", direction="bullish", plan_id="P-1", trade_id=None,
                     prior_status="PENDING", new_status="CANCELLED", reason="manual",
                     occurred_at=AT)
    with pytest.raises(ValueError, match="invalid_shock_label"):
        make_event(transition_id="t", kind="market_shock", target_channel_id="7",
                   occurred_at=AT, payload=lifecycle)


def test_a_shock_payload_under_a_lifecycle_kind_is_still_refused():
    with pytest.raises(ValueError, match="incomplete_payload"):
        event(kind="plan_transition")


def test_an_unknown_kind_is_still_refused():
    with pytest.raises(ValueError, match="invalid_event_kind_or_identity"):
        event(kind="market_note")

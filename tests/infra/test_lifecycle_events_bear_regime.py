"""v239: the bear_regime kind of the v197 notify queue -- validation only."""
import pytest

from swingbot.core.infra import lifecycle_events
from swingbot.core.infra.lifecycle_events import make_event, validate_event

AT = "2026-11-18T21:05:00+00:00"


def payload(**over):
    return dict(occurred_at=AT, session_date="2026-11-19", kind="transition",
                old_label="Correction", new_label="Correction · Stress",
                numbers="SPY −5.7% vs SMA200 · −9.3% vs SMA50 · VIX 37.6", open_longs=3,
                unfilled=[{"ticker": "AAPL", "entry": 101.5}], gap_sessions=1,
                pullback=False) | over


def event(**over):
    return make_event(transition_id="market_regime:2026-11-19", kind="bear_regime",
                      target_channel_id="7", occurred_at=AT, payload=payload(**over))


def test_kinds_gain_bear_regime_last():
    assert lifecycle_events.KINDS[-1] == "bear_regime"
    assert lifecycle_events.REGIME_NOTICE_KINDS == ("transition", "pullback")


def test_valid_transition_pullback_and_first_reading_events_pass():
    validate_event(event())
    validate_event(event(kind="pullback", old_label=None, new_label="Pullback watch"))
    validate_event(event(old_label=None, open_longs=None, unfilled=None, gap_sessions=None))


@pytest.mark.parametrize("over", [
    {"kind": "bogus"}, {"new_label": ""}, {"new_label": None}, {"old_label": 3},
    {"old_label": "Correction", "new_label": "Correction"},
    {"occurred_at": "2026-11-18T21:05:00"}, {"session_date": "11/19/2026"},
    {"session_date": None}, {"open_longs": -1}, {"open_longs": True}, {"gap_sessions": "5"},
    {"unfilled": "AAPL"}, {"unfilled": [1]}, {"pullback": "yes"},
])
def test_a_malformed_payload_is_refused(over):
    with pytest.raises(ValueError):
        event(**over)


def test_the_shock_kind_still_validates_its_own_payload():
    with pytest.raises(ValueError, match="invalid_shock_label"):
        make_event(transition_id="t", kind="market_shock", target_channel_id="7",
                   occurred_at=AT, payload=payload())

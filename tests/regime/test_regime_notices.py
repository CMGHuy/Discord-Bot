"""v239 V239-7: the bear_regime notice -- payload, queue event and status embed."""
import json
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from swingbot import config
from swingbot.core.infra.lifecycle_events import validate_event
from swingbot.core.market import bear_regime as br
from swingbot.core.market import regime_episodes as ep
from swingbot.core.presentation import kinds, regime_text
from swingbot.core.scanning import lifecycle_notifications, regime_notices as rn

NOW = datetime(2026, 11, 18, 21, 5, tzinfo=timezone.utc)
S, D = date(2026, 11, 18), date(2026, 11, 19)
NUMBERS = dict(spy_close=650.0, sma50=716.0, sma200=690.0, vix_close=37.6)


def _day(state=br.CORRECTION, stress=True, pullback=False):
    return br.RegimeDay(session_date=D, last_bar_date=S, state=state, stress=stress,
                        pullback_trigger=pullback, **NUMBERS)


def _plan(ticker="AAPL", status="PENDING", direction="bullish", entry=101.5, ctx=None):
    return SimpleNamespace(ticker=ticker, status=status, direction=direction,
                           trigger_price=entry, entry_context=ctx or {})


def _payload(transition=ep.Transition(ep.CORRECTION_KEY, ep.CORRECTION_STRESS_KEY), **kw):
    args = dict(open_longs=3, unfilled=[{"ticker": "AAPL", "entry": 101.5}], gap_sessions=1)
    day = kw.pop("day", _day())
    return rn.notice_payload(day, transition, now=NOW, **{**args, **kw})


@pytest.fixture(autouse=True)
def _channels(monkeypatch):
    monkeypatch.setattr(config, "DISCORD_CHANNEL_OPS_ID", "11")
    monkeypatch.setattr(config, "DISCORD_CHANNEL_TRADES_ID", "22")


def test_constants():
    assert rn.KIND == "bear_regime"
    assert rn.FOOTER == "Shadow: no long blocked, no short issued, no plan cancelled."
    assert (rn.GAP_NOTE_SESSIONS, rn.UNFILLED_BUDGET) == (5, 3500)


def test_unfilled_rows_are_pending_longs_issued_under_another_state():
    plans = [_plan("MSFT", ctx={"bear_regime": "NORMAL"}), _plan("AAPL"),
             _plan("NVDA", ctx={"bear_regime": "BEAR"}), _plan("AMD", status="ACTIVE"),
             _plan("TSLA", direction="bearish"), _plan("META", entry=None)]
    assert rn.unfilled_bullish_rows(plans, new_state=br.BEAR) == [
        {"ticker": "AAPL", "entry": 101.5}, {"ticker": "MSFT", "entry": 101.5}]


def test_transition_payload_shape_and_json_native():
    payload = _payload()
    assert set(payload) == {"occurred_at", "session_date", "kind", "old_label", "new_label",
                            "numbers", "open_longs", "unfilled", "gap_sessions", "pullback"}
    assert (payload["kind"], payload["old_label"], payload["new_label"]) == (
        "transition", "Correction", "Correction · Stress")
    assert payload["numbers"] == regime_text.number_line(**NUMBERS)
    assert (payload["session_date"], payload["occurred_at"]) == ("2026-11-19", NOW.isoformat())
    assert json.loads(json.dumps(payload)) == payload


def test_first_reading_and_pullback_headlines():
    first = _payload(ep.Transition(None, ep.CORRECTION_KEY))
    assert first["old_label"] is None
    assert rn.headline(first) == "Regime: first reading → Correction"
    pull = _payload(None, day=_day(stress=False, pullback=True))
    assert (pull["kind"], pull["new_label"]) == ("pullback", "Pullback watch")
    assert rn.headline(pull) == "Regime: Pullback watch"
    assert rn.headline(_payload()) == "Regime: Correction → Correction · Stress"


def test_a_notice_needs_a_transition_or_a_pullback():
    with pytest.raises(ValueError, match="regime_notice_without_cause"):
        _payload(None)


def test_one_event_per_session_to_the_ops_channel(monkeypatch):
    built = rn.notice_event(_payload(), session_date=D)
    validate_event(built)
    assert (built["kind"], built["transition_id"]) == ("bear_regime", "market_regime:2026-11-19")
    assert built["target_channel_id"] == "11"
    assert rn.notice_event(_payload(gap_sessions=2), session_date=D)["event_id"] == built["event_id"]
    monkeypatch.setattr(config, "DISCORD_CHANNEL_OPS_ID", "")
    assert rn.notice_event(_payload(), session_date=D)["target_channel_id"] == "22"


def _embed(**kw):
    event = rn.notice_event(_payload(**kw), session_date=D)
    return event, rn.build_regime_embed(event)


def test_the_embed_reads_headline_numbers_counts_list_and_footer():
    event, embed = _embed()
    lines = embed.description.split("\n")
    assert embed.title == "Regime: Correction → Correction · Stress"
    assert embed.colour.value == kinds.WATCH_STOP_ORANGE
    assert lines[0] == regime_text.number_line(**NUMBERS)
    assert "For session 2026-11-19." in lines and "Open longs: 3" in lines
    assert "Unfilled bullish plans from the old state (1):" in lines and "AAPL 101.50" in lines
    assert lines[-1] == rn.FOOTER
    assert embed.footer.text == f"Event {event['event_id']}" and embed.timestamp == NOW
    assert all(ord(ch) < 0x2600 for ch in embed.title + embed.description)   # no glyphs


def test_gap_note_only_past_five_sessions():
    assert _embed(gap_sessions=8)[1].description.startswith("After a gap of 8 sessions.\n")
    assert "gap" not in _embed(gap_sessions=5)[1].description


def test_unreadable_counts_and_an_empty_list_say_so():
    text = _embed(open_longs=None, unfilled=None)[1].description
    assert "Open longs: unavailable" in text
    assert "Unfilled bullish plans from the old state: unavailable" in text
    assert "Unfilled bullish plans from the old state: none." in _embed(unfilled=[])[1].description


def test_a_long_list_stops_at_the_budget():
    rows = [{"ticker": f"T{i:04d}", "entry": 100.0 + i} for i in range(1000)]
    text = _embed(unfilled=rows)[1].description
    assert len(text) <= 4096
    shown = sum(1 for line in text.split("\n") if line.startswith("T"))
    assert f"… and {1000 - shown} more" in text


def test_a_transition_on_a_pullback_day_says_so():
    text = _embed(day=_day(stress=False, pullback=True),
                  transition=ep.Transition(ep.NORMAL_KEY, ep.CORRECTION_KEY))[1].description
    assert "Pullback watch: panic easing inside a correction." in text


@pytest.mark.parametrize("new, colour", [
    (ep.BEAR_KEY, kinds.HEALTH_RED), (ep.CORRECTION_KEY, kinds.MANAGE_AMBER),
    (ep.NORMAL_KEY, kinds.HEALTH_GREEN), (ep.UNKNOWN_KEY, kinds.RESULT_GREY),
])
def test_colour_follows_the_new_state(new, colour):
    assert _embed(transition=ep.Transition(ep.CORRECTION_STRESS_KEY, new))[1].colour.value == colour


def test_the_queue_dispatches_the_kind_to_this_renderer():
    event = rn.notice_event(_payload(), session_date=D)
    embed = lifecycle_notifications.build_lifecycle_notification(event)
    assert embed.title == "Regime: Correction → Correction · Stress"
    broken = {**event, "payload": {**event["payload"], "kind": "bogus"}}
    with pytest.raises(lifecycle_notifications.BlockedDelivery) as blocked:
        lifecycle_notifications.build_lifecycle_notification(broken)
    assert blocked.value.code == "malformed_payload"

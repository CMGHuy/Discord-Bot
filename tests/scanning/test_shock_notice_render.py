"""v210: shock_notices renderer -- the market_shock embed and its copy."""
import asyncio
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from swingbot.core.infra.lifecycle_events import make_event
from swingbot.core.market import shock
from swingbot.core.presentation import kinds, tokens
from swingbot.core.scanning import lifecycle_notifications, shock_notices

AT = "2026-11-05T14:45:00+00:00"
FOOTER = ("The bot moved no stop and closed nothing. "
          "Stop move-up and long block are pending screen (v209 Track 2).")


def reading_row(**over):
    fields = dict(as_of=datetime(2026, 11, 5, 14, 45, tzinfo=timezone.utc),
                  session_date=date(2026, 11, 5), minutes_since_open=75.0, breadth_frac=0.42,
                  sectors_down=5, sectors_total=8, depth_frac=0.3, breadth_speed=0.12,
                  spy_atr_move=-1.8,
                  qqq_atr_move=-2.3, spy_last=671.2, spy_prev_close=683.0,
                  spy_session_low=670.9, spy_new_low=True, spy_retrace=0.05, vix_level=21.13,
                  vix_chg_pct=27.2, vix_session_high=21.4, vix_off_high_pct=1.3, n_names=61,
                  insufficient=False) | over
    return shock.ShockReading(**fields).as_row()


def long_row(ticker="MU", **over):
    return dict(ticker=ticker, entry=100.0, stop=95.0, last=97.5, open_r=-0.5, age_min=125,
                through_stop=False) | over


def shock_event(label="SHOCK", prior="NORMAL", longs=(), **over):
    payload = dict(label=label, prior_label=prior, occurred_at=AT, reading=reading_row(),
                   open_longs=list(longs), entry_into_shock=label == "SHOCK") | over
    return {"event_id": "evt-1", "kind": "market_shock", "payload": payload}


def test_footer_is_the_exact_spec_copy():
    assert shock_notices.FOOTER == FOOTER


@pytest.mark.parametrize("over,line", [
    ({}, "MU · entry 100.00 · stop 95.00 · last 97.50 · -0.50R · 2h05m · "
         "stop at broker untouched: 95.00"),
    ({"last": 94.0, "open_r": -1.2, "age_min": 45, "through_stop": True},
     "MU · entry 100.00 · stop 95.00 · last 94.00 · -1.20R · 45m · THROUGH STOP"),
    ({"last": None, "open_r": None, "age_min": 0},
     "MU · entry 100.00 · stop 95.00 · last n/a · n/a R · 0m · stop status unknown: 95.00"),
    ({"last": 101.5, "open_r": 0.3, "age_min": 3005},
     "MU · entry 100.00 · stop 95.00 · last 101.50 · +0.30R · 50h05m · "
     "stop at broker untouched: 95.00"),
])
def test_long_line(over, line):
    assert shock_notices.long_line(long_row(**over)) == line


def test_headline_and_numbers_line():
    embed = shock_notices.build_shock_embed(shock_event())
    assert embed.title == "Market state: NORMAL → SHOCK" == embed.push_text
    assert embed.description.splitlines()[0] == (
        "breadth 42% · sectors 5/8 · speed +12pp · SPY -1.80 ATR · QQQ -2.30 ATR · "
        "VIX 21.13 (+27.2%)")


def test_missing_numbers_read_n_a():
    row = reading_row(breadth_frac=None, sectors_down=0, sectors_total=0, breadth_speed=None,
                      spy_atr_move=None, qqq_atr_move=None, vix_level=None, vix_chg_pct=None)
    assert shock_notices.numbers_line(row) == (
        "breadth n/a · sectors 0/0 · speed n/a · SPY n/a · QQQ n/a · VIX n/a")
    assert shock_notices.numbers_line(reading_row(vix_chg_pct=None)).endswith("VIX 21.13 (n/a)")


def test_entry_with_zero_open_longs_says_so_and_ends_with_the_footer():
    text = shock_notices.build_shock_embed(shock_event()).description
    assert "No open longs." in text and text.endswith(FOOTER)


def test_entry_lists_every_open_long_in_payload_order():
    longs = [long_row("MU"), long_row("STX", last=94.0, open_r=-1.2, through_stop=True)]
    lines = shock_notices.build_shock_embed(shock_event(longs=longs)).description.splitlines()
    assert "Open longs (2):" in lines
    assert lines.index(shock_notices.long_line(longs[0])) < lines.index(
        shock_notices.long_line(longs[1]))
    assert any(line.endswith("THROUGH STOP") for line in lines)
    assert "No open longs." not in lines and lines[-1] == FOOTER


def test_a_second_leg_lists_longs_and_the_footer_too():
    text = shock_notices.build_shock_embed(
        shock_event(prior="RECOVERY", longs=[long_row()])).description
    assert "Open longs (1):" in text and text.endswith(FOOTER)


def test_many_open_longs_stay_inside_discords_description_cap():
    longs = [long_row(f"T{i:03d}") for i in range(120)]
    text = shock_notices.build_shock_embed(shock_event(longs=longs)).description
    assert len(text) <= 4096 and "more open longs" in text and text.endswith(FOOTER)
    assert "Open longs (120):" in text


def test_unreadable_open_longs_are_named_not_hidden():
    text = shock_notices.build_shock_embed(
        shock_event(open_longs_unavailable=True)).description
    assert "Open longs unavailable: the trade log could not be read." in text
    assert "No open longs." not in text and text.endswith(FOOTER)


@pytest.mark.parametrize("label,prior", [("RECOVERY", "SHOCK"), ("NORMAL", "RECOVERY")])
def test_a_transition_out_of_shock_lists_no_longs_and_no_footer(label, prior):
    text = shock_notices.build_shock_embed(shock_event(label, prior)).description
    assert "open longs" not in text.lower() and FOOTER not in text


@pytest.mark.parametrize("label,prior,colour", [
    ("SHOCK", "NORMAL", kinds.HEALTH_RED), ("RECOVERY", "SHOCK", kinds.WATCH_STOP_ORANGE),
    ("NORMAL", "RECOVERY", kinds.HEALTH_GREEN)])
def test_status_chrome_never_an_alert(label, prior, colour):
    embed = shock_notices.build_shock_embed(shock_event(label, prior))
    assert embed.colour.value == colour
    assert embed.footer.text == "Event evt-1"
    assert tokens.DISCLAIMER not in embed.footer.text
    assert embed.timestamp == datetime.fromisoformat(AT)
    assert embed.kind is None


def test_the_payload_is_not_mutated():
    notice = shock_event(longs=[long_row()])
    before = repr(notice)
    shock_notices.build_shock_embed(notice)
    assert repr(notice) == before


def queued(label="SHOCK", prior="NORMAL"):
    payload = shock_event(label, prior)["payload"]
    return make_event(transition_id=f"market_shock:{AT}", kind="market_shock",
                      target_channel_id="7", occurred_at=AT, payload=payload)


def test_lifecycle_renderer_dispatches_the_shock_kind():
    notice = queued()
    built = lifecycle_notifications.build_lifecycle_notification(notice)
    assert built.title == "Market state: NORMAL → SHOCK"
    assert built.footer.text == f"Event {notice['event_id']}"
    assert not any(field.name == "Recorded transition" for field in built.fields)


def test_a_malformed_shock_event_is_a_blocked_delivery():
    notice = queued()
    notice["payload"]["reading"] = None
    with pytest.raises(lifecycle_notifications.BlockedDelivery) as caught:
        lifecycle_notifications.build_lifecycle_notification(notice)
    assert caught.value.code == "malformed_payload"


def test_send_posts_the_shock_embed_with_its_push_line():
    channel = SimpleNamespace(send=AsyncMock(return_value=SimpleNamespace(id=99)))
    bot = SimpleNamespace(get_channel=Mock(return_value=channel), fetch_channel=AsyncMock())
    assert asyncio.run(lifecycle_notifications.send_lifecycle_notification(
        bot, queued())) == "99"
    bot.get_channel.assert_called_once_with(7)
    kwargs = channel.send.await_args.kwargs
    assert kwargs["content"] == "Market state: NORMAL → SHOCK" == kwargs["embed"].title

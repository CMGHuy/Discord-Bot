"""
DISCORD_CHANNEL_TRADES_SIMPLE_ID: the chartless embed mirror of the main
alerts channel.

Two halves:
  * build_simple_alert() renders the nine required fields and, critically,
    quotes the SAME prices as the full embed's trade-plan table under both
    PLAN_ENGINE_V2 settings -- the two channels describing one signal
    differently is the failure mode worth locking down.
  * _send_alerts() mirrors to the simple channel only when one is configured,
    tolerates the legacy 3-tuple alert shape, and never lets a simple-channel
    failure cost the real alert.

No pytest-asyncio in this repo (see tests/test_views.py) -- coroutines are
driven with asyncio.run().
"""
import asyncio
import types

import discord
import pytest

from swingbot import config
from swingbot.commands import scanning as scanning_mod
from swingbot.commands.scanning import _send_alerts
from swingbot.core.scanning import embeds as embeds_mod
from swingbot.core.scanning.embeds import build_simple_alert

from tests.scanning.test_embeds_v3 import make_item, make_plan_v2


# --------------------------------------------------------------------------
# build_simple_alert
# --------------------------------------------------------------------------

def test_simple_alert_renders_every_required_field(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "off")
    embed = build_simple_alert(make_item())

    assert isinstance(embed, discord.Embed)
    assert "NVDA" in embed.title                       # ticker
    assert "LONG" in embed.title                        # direction
    assert "High (Lv4/5, 80/100)" in embed.description  # confidence level AND score
    assert "2 Weeks" in embed.description               # horizon
    assert "RSI Pullback" in embed.description           # setup (strategy)
    assert "EMA, Fibonacci" in embed.description         # setup (confluence sources)
    assert "Entry **100.00**" in embed.description
    assert "TP1 **110.00**" in embed.description
    assert "TP2 **115.00**" in embed.description
    assert "SL **95.00**" in embed.description


def test_simple_alert_groups_entry_tp1_tp2_sl_on_one_clearly_labeled_line():
    """Entry/TP1/TP2/SL belong on one scannable line -- they used to be one
    price per line, which was the least readable part on a phone -- and each
    carries its own emoji label so it's unambiguous which number is which."""
    embed = build_simple_alert(make_item())
    plan_lines = [l for l in embed.description.splitlines() if "Entry" in l]
    assert len(plan_lines) == 1, embed.description
    line = plan_lines[0]
    assert "🎯 Entry" in line
    assert "💰 TP1" in line and "💰 TP2" in line
    assert "🛑 SL" in line


def test_simple_alert_marks_a_bearish_signal_short_with_down_triangle_and_red():
    item = make_item()
    item.result.trend = "bearish"
    embed = build_simple_alert(item)
    assert "SHORT" in embed.title and "LONG" not in embed.title
    assert "▼" in embed.title
    assert embed.color == discord.Color.red()
    # The triangle itself is colored too (Discord embed titles can't carry
    # color -- an ```ansi code block in the description is the only place
    # that can), red = short, matching the SPA table's convention.
    assert "[1;31m" in embed.description and "▼" in embed.description


def test_simple_alert_marks_a_bullish_signal_long_with_up_triangle_and_green():
    embed = build_simple_alert(make_item())
    assert "LONG" in embed.title
    assert "▲" in embed.title
    assert embed.color == discord.Color.green()
    assert "[1;32m" in embed.description and "▲" in embed.description


def test_simple_alert_omits_tp2_when_there_is_no_second_target(monkeypatch):
    """Legacy (non-v2) scenario plans have no runner/trail concept -- a
    missing second target here genuinely means there isn't one."""
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "off")
    item = make_item()
    item.plan.target2_price = None
    embed = build_simple_alert(item)
    assert "TP2" not in embed.description
    assert "TP1 **110.00**" in embed.description and "SL **95.00**" in embed.description


def test_simple_alert_shows_trail_when_v2_plan_has_no_hard_tp2(monkeypatch):
    """A v2 scale-out plan's runner is managed to a trailing stop instead of
    a fixed second target -- TP2 must say so, not silently vanish, matching
    the full embed's own leg_rows() convention ('TP2 105.00 / trail')."""
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    item = make_item(plan_v2=make_plan_v2())
    item.plan_v2.tp2 = None
    embed = build_simple_alert(item)
    assert "TP2 **trail**" in embed.description


def test_simple_alert_carries_no_chart_or_image_reference():
    """The whole point of the simple channel: no render, no attachment."""
    embed = build_simple_alert(make_item(plan_v2=make_plan_v2()))
    assert "attachment://" not in embed.description
    assert ".png" not in embed.description
    assert embed.image.url is None


@pytest.mark.parametrize("flag,expected_entry,expected_tp1,expected_tp2", [
    ("off", "100.00", "110.00", "115.00"),   # legacy scenario numbers
    ("on", "100.00", "110.00", "120.00"),    # v2 plan numbers (tp2=120.0)
])
def test_simple_alert_prices_follow_the_same_cutover_as_the_full_embed(
        monkeypatch, flag, expected_entry, expected_tp1, expected_tp2):
    """plan_numbers_for_display is THE cutover switch; the simple mirror must
    ride it rather than reading item.plan directly, or turning PLAN_ENGINE_V2
    on would make the two channels quote different targets for one signal."""
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", flag)
    item = make_item(plan_v2=make_plan_v2())
    embed = build_simple_alert(item)

    expected = embeds_mod.plan_numbers_for_display(item.plan_v2, {
        "entry": item.plan.entry, "stop_loss": item.plan.stop_loss,
        "take_profit": item.plan.take_profit, "target2": item.plan.target2_price})

    assert f"Entry **{expected['entry']:.2f}**" in embed.description
    assert f"TP1 **{expected['take_profit']:.2f}**" in embed.description
    assert f"TP2 **{expected['target2']:.2f}**" in embed.description
    assert f"Entry **{expected_entry}**" in embed.description
    assert f"TP1 **{expected_tp1}**" in embed.description
    assert f"TP2 **{expected_tp2}**" in embed.description


# --------------------------------------------------------------------------
# _send_alerts mirroring
# --------------------------------------------------------------------------

class FakeChannel:
    def __init__(self, name="chan", fail=False, order=None):
        self.name = name
        self.sent = []
        self.fail = fail
        self.order = order if order is not None else []

    async def send(self, *args, **kwargs):
        if self.fail:
            raise RuntimeError("discord is having a day")
        self.order.append(self.name)
        self.sent.append(kwargs or args)
        return types.SimpleNamespace(id=1)


@pytest.fixture
def wired(monkeypatch):
    """Main + simple channels wired up, firehose off, cap high."""
    order = []
    main = FakeChannel("main", order=order)
    simple = FakeChannel("simple", order=order)
    monkeypatch.setattr(config, "DISCORD_CHANNEL_FIREHOSE_ID", "", raising=False)
    monkeypatch.setattr(config, "MAX_ALERTS_PER_SCAN", 10, raising=False)
    monkeypatch.setattr(config, "DISCORD_CHANNEL_TRADES_SIMPLE_ID", "999", raising=False)
    monkeypatch.setattr(scanning_mod, "bot",
                        types.SimpleNamespace(get_channel=lambda _id: simple), raising=False)
    return main, simple


def _alert(simple_text="SIMPLE-TEXT", embed="EMBED"):
    return (embed, None, None, simple_text)


def test_configured_simple_channel_receives_a_mirror_of_every_alert(wired):
    main, simple = wired
    asyncio.run(_send_alerts(main, [_alert("A"), _alert("B")]))

    assert len(main.sent) == 2                                # full alerts still posted
    assert [c["embed"] for c in simple.sent] == ["A", "B"]    # one mirror each, in order


def test_blank_simple_channel_id_disables_mirroring(monkeypatch, wired):
    main, simple = wired
    monkeypatch.setattr(config, "DISCORD_CHANNEL_TRADES_SIMPLE_ID", "", raising=False)
    asyncio.run(_send_alerts(main, [_alert()]))

    assert len(main.sent) == 1
    assert simple.sent == []


def test_legacy_three_tuple_alerts_still_send_and_mirror_nothing(wired):
    """Any caller predating the simple channel (and the hand-built tuples in
    tests/test_embeds_v3.py) passes 3-tuples -- that must not raise."""
    main, simple = wired
    asyncio.run(_send_alerts(main, [("EMBED", None, None)]))

    assert len(main.sent) == 1
    assert simple.sent == []


def test_a_failing_simple_channel_never_costs_the_real_alerts(monkeypatch, wired):
    main, _ = wired
    broken = FakeChannel(fail=True)
    monkeypatch.setattr(scanning_mod, "bot",
                        types.SimpleNamespace(get_channel=lambda _id: broken), raising=False)

    asyncio.run(_send_alerts(main, [_alert("A"), _alert("B")]))
    assert len(main.sent) == 2   # both full alerts landed despite the mirror failing


def test_unresolvable_simple_channel_id_is_skipped_not_fatal(monkeypatch, wired):
    main, _ = wired
    monkeypatch.setattr(scanning_mod, "bot",
                        types.SimpleNamespace(get_channel=lambda _id: None), raising=False)

    asyncio.run(_send_alerts(main, [_alert()]))
    assert len(main.sent) == 1


# --------------------------------------------------------------------------
# Notification policy: exactly one ping per signal, raised by the simple channel
# --------------------------------------------------------------------------

def test_mirrored_alert_is_posted_silently_to_the_full_channel(wired):
    main, simple = wired
    asyncio.run(_send_alerts(main, [_alert()]))

    assert main.sent[0]["silent"] is True            # full alert delivered, no ping
    assert simple.sent == [{"embed": "SIMPLE-TEXT"}]  # mirror sent as an embed -> it pings


def test_the_simple_mirror_itself_is_never_silenced(wired):
    main, simple = wired
    asyncio.run(_send_alerts(main, [_alert()]))
    assert "silent" not in (simple.sent[0] if isinstance(simple.sent[0], dict) else {})


def test_mirror_is_sent_before_the_full_alert(wired):
    """Ordering is load-bearing, not cosmetic: the full alert can only be
    silenced once the mirror is known to have landed."""
    main, simple = wired
    asyncio.run(_send_alerts(main, [_alert("A"), _alert("B")]))
    assert main.order == ["simple", "main", "simple", "main"]


def test_full_alert_keeps_its_notification_when_no_simple_channel(monkeypatch, wired):
    """Silencing must never leave a signal unannounced -- with the mirror off,
    the full alert has to stay the thing that pings."""
    main, _ = wired
    monkeypatch.setattr(config, "DISCORD_CHANNEL_TRADES_SIMPLE_ID", "", raising=False)
    asyncio.run(_send_alerts(main, [_alert()]))

    assert main.sent[0]["silent"] is False


def test_failed_mirror_hands_the_notification_back_to_the_full_alert(monkeypatch, wired):
    main, _ = wired
    broken = FakeChannel("broken", fail=True)
    monkeypatch.setattr(scanning_mod, "bot",
                        types.SimpleNamespace(get_channel=lambda _id: broken), raising=False)

    asyncio.run(_send_alerts(main, [_alert()]))
    assert main.sent[0]["silent"] is False


def test_legacy_three_tuple_alert_is_not_silenced(wired):
    """No simple text to mirror -> nothing else will ping for this signal."""
    main, _ = wired
    asyncio.run(_send_alerts(main, [("EMBED", None, None)]))
    assert main.sent[0]["silent"] is False


def test_overflow_digest_survives_the_real_four_tuple_shape(monkeypatch, wired):
    """engine.py emits 4-tuples, but the overflow digest unpacked three names
    (`for _, _, p in overflow`). The unpack runs before the `if p is not None`
    filter, so ANY scan producing more than MAX_ALERTS_PER_SCAN alerts raised
    ValueError before a single send -- losing every alert, not just the
    overflow. Every existing test here passes <= 2 alerts under a cap of 10,
    so the branch was never exercised with the shape production actually uses.
    """
    main, _ = wired
    monkeypatch.setattr(config, "MAX_ALERTS_PER_SCAN", 1, raising=False)

    kept = (discord.Embed(title="KEPT"), None,
            types.SimpleNamespace(ticker="AAA", plan_id="p-aaa"), "A")
    spilled = (discord.Embed(title="SPILLED"), None,
               types.SimpleNamespace(ticker="BBB", plan_id="p-bbb"), "B")

    asyncio.run(_send_alerts(main, [kept, spilled]))

    assert len(main.sent) == 1, "the cap must still apply"
    assert "+1 more: BBB" in kept[0].footer.text, \
        "the capped-out alert must still be named in the digest footer"

"""
DISCORD_CHANNEL_TRADES_SIMPLE_ID: the chartless text mirror of the main
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

import pytest

from swingbot import config
from swingbot.commands import scanning as scanning_mod
from swingbot.commands.scanning import _send_alerts
from swingbot.core.scanning import embeds as embeds_mod
from swingbot.core.scanning.embeds import build_simple_alert

from tests.test_embeds_v3 import make_item, make_plan_v2


# --------------------------------------------------------------------------
# build_simple_alert
# --------------------------------------------------------------------------

def test_simple_alert_renders_every_required_field(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "off")
    text = build_simple_alert(make_item())

    assert "NVDA" in text                    # ticker
    assert "LONG" in text                    # direction
    assert "High (Lv4/5, 80/100)" in text    # confidence level AND score
    assert "2 Weeks" in text                 # horizon
    assert "RSI Pullback" in text            # setup (strategy)
    assert "EMA, Fibonacci" in text          # setup (confluence sources)
    assert "Entry `100.00`" in text
    assert "TP1 `110.00`" in text
    assert "TP2 `115.00`" in text
    assert "SL `95.00`" in text


def test_simple_alert_marks_a_bearish_signal_short():
    item = make_item()
    item.result.trend = "bearish"
    text = build_simple_alert(item)
    assert "SHORT" in text and "LONG" not in text
    assert "🔴" in text


def test_simple_alert_omits_tp2_when_there_is_no_second_target(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "off")
    item = make_item()
    item.plan.target2_price = None
    text = build_simple_alert(item)
    assert "TP2" not in text
    assert "TP1 `110.00`" in text and "SL `95.00`" in text


def test_simple_alert_carries_no_chart_or_image_reference():
    """The whole point of the simple channel: no render, no attachment."""
    text = build_simple_alert(make_item(plan_v2=make_plan_v2()))
    assert "attachment://" not in text
    assert ".png" not in text
    assert isinstance(text, str)


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
    text = build_simple_alert(item)

    expected = embeds_mod.plan_numbers_for_display(item.plan_v2, {
        "entry": item.plan.entry, "stop_loss": item.plan.stop_loss,
        "take_profit": item.plan.take_profit, "target2": item.plan.target2_price})

    assert f"Entry `{expected['entry']:.2f}`" in text
    assert f"TP1 `{expected['take_profit']:.2f}`" in text
    assert f"TP2 `{expected['target2']:.2f}`" in text
    assert f"Entry `{expected_entry}`" in text
    assert f"TP1 `{expected_tp1}`" in text
    assert f"TP2 `{expected_tp2}`" in text


# --------------------------------------------------------------------------
# _send_alerts mirroring
# --------------------------------------------------------------------------

class FakeChannel:
    def __init__(self, fail=False):
        self.sent = []
        self.fail = fail

    async def send(self, *args, **kwargs):
        if self.fail:
            raise RuntimeError("discord is having a day")
        self.sent.append(kwargs or args)
        return types.SimpleNamespace(id=1)


@pytest.fixture
def wired(monkeypatch):
    """Main + simple channels wired up, firehose off, cap high."""
    main, simple = FakeChannel(), FakeChannel()
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

    assert len(main.sent) == 2                       # full alerts still posted
    assert [c[0] for c in simple.sent] == ["A", "B"]  # one mirror each, in order


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

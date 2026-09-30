"""The SPA's event contract, pinned against both watcher implementations.

Success criterion 5: the stream delivers the same event names with no SPA
change. The frontend is not in this test's blast radius precisely because it is
not supposed to be in the change's blast radius either.
"""
import pathlib
import re

from swingbot.admin.events.watcher import WATCHED_EVENTS
from swingbot.core.db import events, notify

FRONTEND = pathlib.Path(__file__).resolve().parents[2] / "frontend"

EXPECTED_EVENTS = {"trades", "account", "analytics", "scan", "journal",
                   "bot", "risk", "watchlist", "jobs", "settings"}


def test_the_event_names_are_exactly_what_they_were():
    assert set(WATCHED_EVENTS) == EXPECTED_EVENTS


def test_notify_channels_match_the_event_names():
    assert set(notify.CHANNELS) == EXPECTED_EVENTS


def test_every_channel_a_trigger_can_raise_is_one_the_spa_knows():
    assert set(events.TABLE_CHANNELS.values()) <= EXPECTED_EVENTS


def test_the_spa_subscribes_to_no_event_this_backend_cannot_raise():
    """Parses the SPA's EVENT_NAMES literal -- the list event-stream.ts loops
    over to subscribe. A name here that no trigger raises is a panel that
    silently stops updating. (`resync` and `ping` are subscribed separately and
    raised by the stream, not by storage.)"""
    source = FRONTEND / "src" / "app" / "api" / "event-stream.ts"
    if not source.exists():
        import pytest
        pytest.skip("frontend/ sources not present in this checkout")
    text = source.read_text(encoding="utf-8")
    block = re.search(r"EVENT_NAMES[^=]*=\s*\[(.*?)\]", text, re.S)
    assert block, "EVENT_NAMES literal not found in event-stream.ts"
    listened = set(re.findall(r"'([a-z_]+)'", block.group(1)))
    assert listened, "EVENT_NAMES parsed empty -- the regex, not the SPA, is wrong"
    unknown = listened - EXPECTED_EVENTS
    assert not unknown, f"SPA listens for events nothing raises: {sorted(unknown)}"
    assert listened == EXPECTED_EVENTS

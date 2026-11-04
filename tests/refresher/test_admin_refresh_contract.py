"""v201: the refresher contract module and the session-state clock."""
from datetime import datetime, timedelta, timezone

import pytest

from swingbot import config
from swingbot.core.market import session
from swingbot.core.marketdata.shared import admin_refresh as ar

UTC = timezone.utc


@pytest.mark.parametrize("now,state", [
    (datetime(2026, 10, 28, 14, 0, tzinfo=UTC), "regular"),     # Wed 10:00 ET
    (datetime(2026, 10, 28, 12, 0, tzinfo=UTC), "extended"),    # Wed 08:00 ET
    (datetime(2026, 10, 28, 21, 30, tzinfo=UTC), "extended"),   # Wed 17:30 ET
    (datetime(2026, 10, 29, 1, 0, tzinfo=UTC), "closed"),       # Wed 21:00 ET
    (datetime(2026, 10, 31, 15, 0, tzinfo=UTC), "closed"),      # Saturday
    (datetime(2026, 11, 26, 16, 0, tzinfo=UTC), "closed"),      # Thanksgiving
])
def test_session_state(now, state):
    assert session.session_state(now) == state


@pytest.mark.parametrize("now,close", [
    (datetime(2026, 10, 31, 16, 0, tzinfo=UTC), datetime(2026, 10, 30, 20, 0, tzinfo=UTC)),
    (datetime(2026, 10, 28, 19, 0, tzinfo=UTC), datetime(2026, 10, 27, 20, 0, tzinfo=UTC)),
    (datetime(2026, 10, 28, 21, 0, tzinfo=UTC), datetime(2026, 10, 28, 20, 0, tzinfo=UTC)),
    (datetime(2026, 11, 28, 15, 0, tzinfo=UTC), datetime(2026, 11, 27, 18, 0, tzinfo=UTC)),  # half day
])
def test_last_regular_close_is_utc_and_holiday_aware(now, close):
    got = session.last_regular_close(now)
    assert got == close and got.tzinfo is not None


@pytest.mark.parametrize("admin,layer,on", [
    ("on", "on", True), ("off", "on", False), ("on", "count", False), ("on", "off", False)])
def test_refresher_on_needs_both_flags(monkeypatch, admin, layer, on):
    monkeypatch.setattr(config, "ADMIN_REFRESHER", admin)
    monkeypatch.setattr(config, "MARKETDATA_LAYER", layer)
    assert ar.refresher_on() is on


def test_cadence_and_staleness_read_config_at_call_time(monkeypatch):
    monkeypatch.setattr(config, "ADMIN_REFRESH_REGULAR_S", 11)
    assert ar.cadence_s("regular") == 11.0
    assert ar.cadence_s("extended") == 300.0 and ar.cadence_s("closed") == 1800.0
    assert ar.stale_after_s("price", "regular") == 120.0
    assert ar.stale_after_s("price", "extended") == 900.0
    assert ar.stale_after_s("price", "closed") is None
    with pytest.raises(ValueError):
        ar.cadence_s("lunch")
    with pytest.raises(ValueError):          # snapshot staleness is v204's
        ar.stale_after_s("snapshot", "regular")


def test_heartbeat_stalled_after_three_cadences():
    now = datetime(2026, 10, 28, 15, 0, tzinfo=UTC)
    assert ar.heartbeat_stalled(None, 30.0, now) is True
    assert ar.heartbeat_stalled(now - timedelta(seconds=90), 30.0, now) is False
    assert ar.heartbeat_stalled(now - timedelta(seconds=91), 30.0, now) is True


def test_keys_and_priorities():
    assert ar.quote_mark_key(" aapl ") == "quote:AAPL"
    assert (ar.PRIORITY_USER, ar.PRIORITY_FRESH_HINT, ar.PRIORITY_MISSING) == (0, 1, 2)
    assert (ar.QUEUE_KIND_QUOTE, ar.QUEUE_KIND_SNAPSHOT) == ("quote", "snapshot")
    assert (ar.HEARTBEAT_KEY, ar.QUEUE_RETENTION_S) == ("refresher", 3600)

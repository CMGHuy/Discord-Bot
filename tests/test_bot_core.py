import datetime as dt

from swingbot import config
from swingbot.bot_core import SESSION_TZ, in_session


def test_in_session_supports_cross_midnight_windows(monkeypatch):
    monkeypatch.setattr(config, "SESSION_START_HOUR", 22)
    monkeypatch.setattr(config, "SESSION_END_HOUR", 6)

    assert in_session(dt.datetime(2026, 8, 24, 23, tzinfo=SESSION_TZ))
    assert in_session(dt.datetime(2026, 8, 25, 2, tzinfo=SESSION_TZ))
    assert not in_session(dt.datetime(2026, 8, 24, 12, tzinfo=SESSION_TZ))


def test_in_session_equal_hours_is_always_on(monkeypatch):
    monkeypatch.setattr(config, "SESSION_START_HOUR", 8)
    monkeypatch.setattr(config, "SESSION_END_HOUR", 8)

    assert in_session(dt.datetime(2026, 8, 24, 3, tzinfo=SESSION_TZ))
"""v152 D3: the per-symbol alert cooldown module.

Real alert_posts table (tests/conftest.py gives each test the worker's test
database and truncates it afterwards). The module must fail open: a fault in
the window read or the record write posts the alert and logs one WARNING.
"""
import datetime as dt
import logging
import types

import pytest

from swingbot import config
from swingbot.commands.scanning import cooldown
from swingbot.core.db.repositories.alert_posts import alert_posts_repo
from swingbot.core.market.session import BERLIN_TZ

UTC = dt.timezone.utc
T0 = dt.datetime(2026, 10, 12, 14, 0, tzinfo=UTC)


def _plan(ticker="AAPL", direction="bullish", horizon_key="4w",
          plan_id="3b2f0c1e-8a4d-4f7e-9c61-2d5e8f9a1b07"):
    return types.SimpleNamespace(plan_id=plan_id, ticker=ticker, direction=direction,
                                 horizon_key=horizon_key)


@pytest.fixture(autouse=True)
def _hours(monkeypatch):
    monkeypatch.setattr(config, "ALERT_SYMBOL_COOLDOWN_HOURS", 24.0, raising=False)


class _Broken:
    def __getattr__(self, name):
        def _raise(*args, **kwargs):
            raise RuntimeError("database is having a day")
        return _raise


def _warnings(caplog):
    return [r for r in caplog.records
            if r.levelno == logging.WARNING and r.name == cooldown.log.name]


def test_same_key_posted_inside_the_window_is_suppressed():
    cooldown.record(_plan(), "posted", now=T0 - dt.timedelta(hours=1))
    assert cooldown.suppressed(_plan(), now=T0) is True


@pytest.mark.parametrize("other", [
    _plan(direction="bearish"),          # flipped direction posts
    _plan(horizon_key="2w"),             # another horizon posts
    _plan(ticker="MSFT"),                # another ticker posts
])
def test_a_different_key_is_never_suppressed(other):
    cooldown.record(_plan(), "posted", now=T0 - dt.timedelta(hours=1))
    assert cooldown.suppressed(other, now=T0) is False


def test_a_post_outside_the_window_does_not_suppress():
    cooldown.record(_plan(), "posted", now=T0 - dt.timedelta(hours=25))
    assert cooldown.suppressed(_plan(), now=T0) is False


def test_a_held_alert_does_not_open_or_extend_a_window():
    cooldown.record(_plan(), "suppressed", now=T0 - dt.timedelta(hours=1))
    assert cooldown.suppressed(_plan(), now=T0) is False


def test_zero_hours_turns_the_check_off_without_a_read(monkeypatch):
    cooldown.record(_plan(), "posted", now=T0 - dt.timedelta(hours=1))
    monkeypatch.setattr(config, "ALERT_SYMBOL_COOLDOWN_HOURS", 0.0, raising=False)
    monkeypatch.setattr(cooldown, "alert_posts_repo", lambda: _Broken())
    assert cooldown.suppressed(_plan(), now=T0) is False


def test_record_writes_the_doc_keys_the_window_reads():
    cooldown.record(_plan(), "posted", now=T0)
    rows = alert_posts_repo().list_all()
    assert len(rows) == 1
    row = rows[0]
    assert (row["ticker"], row["outcome"]) == ("AAPL", "posted")
    assert (row["direction"], row["horizon_key"], row["plan_id"]) == (
        "bullish", "4w", "3b2f0c1e-8a4d-4f7e-9c61-2d5e8f9a1b07")


def test_a_failing_read_posts_anyway_and_warns_once(monkeypatch, caplog):
    monkeypatch.setattr(cooldown, "alert_posts_repo", lambda: _Broken())
    with caplog.at_level(logging.WARNING):
        assert cooldown.suppressed(_plan(), now=T0) is False
    assert len(_warnings(caplog)) == 1
    assert _warnings(caplog)[0].exc_info is not None


def test_a_bad_hours_value_fails_open(monkeypatch, caplog):
    monkeypatch.setattr(config, "ALERT_SYMBOL_COOLDOWN_HOURS", "soon", raising=False)
    with caplog.at_level(logging.WARNING):
        assert cooldown.suppressed(_plan(), now=T0) is False
    assert len(_warnings(caplog)) == 1


def test_a_failing_write_never_raises_and_warns_once(monkeypatch, caplog):
    monkeypatch.setattr(cooldown, "alert_posts_repo", lambda: _Broken())
    with caplog.at_level(logging.WARNING):
        assert cooldown.record(_plan(), "posted", now=T0) is None
    assert len(_warnings(caplog)) == 1


def test_held_note_is_none_without_held_alerts():
    assert cooldown.held_note([]) is None


def test_held_note_names_each_held_alert_and_the_window():
    held = [_plan(), _plan(ticker="MSFT", direction="bearish", horizon_key="2w")]
    assert cooldown.held_note(held) == (
        "Cooldown held 2 alert(s) this scan: AAPL long 4w, MSFT short 2w "
        "(posted within 24h).")


def test_held_note_prints_fractional_hours(monkeypatch):
    monkeypatch.setattr(config, "ALERT_SYMBOL_COOLDOWN_HOURS", 12.5, raising=False)
    assert cooldown.held_note([_plan()]).endswith("(posted within 12.5h).")


def test_held_today_counts_from_berlin_midnight_not_utc():
    now = dt.datetime(2026, 10, 12, 0, 30, tzinfo=BERLIN_TZ)        # 22:30 UTC on the 11th
    cooldown.record(_plan(), "suppressed",
                    now=dt.datetime(2026, 10, 11, 23, 0, tzinfo=BERLIN_TZ))   # yesterday in Berlin
    cooldown.record(_plan(ticker="MSFT"), "suppressed",
                    now=dt.datetime(2026, 10, 12, 0, 10, tzinfo=BERLIN_TZ))   # today in Berlin
    cooldown.record(_plan(ticker="NVDA"), "posted",
                    now=dt.datetime(2026, 10, 12, 0, 15, tzinfo=BERLIN_TZ))   # posted, not held
    assert cooldown.held_today(now=now) == 1


def test_held_today_is_zero_on_error(monkeypatch, caplog):
    monkeypatch.setattr(cooldown, "alert_posts_repo", lambda: _Broken())
    with caplog.at_level(logging.WARNING):
        assert cooldown.held_today(now=T0) == 0
    assert len(_warnings(caplog)) == 1


def test_prune_keeps_a_week_when_the_window_is_shorter():
    for hours in (200, 100, 1):
        cooldown.record(_plan(ticker=f"T{hours}"), "posted", now=T0 - dt.timedelta(hours=hours))
    assert cooldown.prune(now=T0) == 1
    assert sorted(r["ticker"] for r in alert_posts_repo().list_all()) == ["T1", "T100"]


def test_prune_never_cuts_into_a_window_longer_than_a_week(monkeypatch):
    monkeypatch.setattr(config, "ALERT_SYMBOL_COOLDOWN_HOURS", 200.0, raising=False)
    for hours in (201, 199):
        cooldown.record(_plan(ticker=f"T{hours}"), "posted", now=T0 - dt.timedelta(hours=hours))
    assert cooldown.prune(now=T0) == 1
    assert [r["ticker"] for r in alert_posts_repo().list_all()] == ["T199"]
    assert cooldown.suppressed(_plan(ticker="T199"), now=T0) is True

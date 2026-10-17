"""v148 O3/O4: ops_watch -- the stale-scan and provider verdicts, the ops
notices, and (OH18) the watchdog loop and provider check on a fake channel."""
import datetime as dt

import pytest

from swingbot.commands.scanning import notices, ops_watch
from swingbot.core.presentation import kinds
from swingbot.core.presentation.kinds import Kind

NOW = dt.datetime(2026, 10, 12, 15, 0, tzinfo=dt.timezone.utc)
BOOT = NOW - dt.timedelta(hours=2)
INTERVAL = 5          # stale beyond 10 minutes

ROW_OK = {"at": "2026-10-12T14:55:00+00:00", "duration_s": 61.0, "tickers": 100,
          "provider_fallback_rate": 0.05, "empty_symbols": 1, "empty_rate": 0.01,
          "stale_symbols": 0}
ROW_BAD = {**ROW_OK, "provider_fallback_rate": 0.25, "empty_symbols": 6, "empty_rate": 0.06,
           "stale_symbols": 2}
ROW_PRE_V148 = {"at": "2026-10-01T14:55:00+00:00", "duration_s": 60.0, "tickers": 100}


def _ago(minutes: int) -> str:
    return (NOW - dt.timedelta(minutes=minutes)).isoformat()


def _stale(last="default", *, booted=BOOT, in_session=True, paused=False, failure=False,
           stale=False):
    last = _ago(11) if last == "default" else last
    return ops_watch.stale_scan_verdict(
        NOW, last, INTERVAL, booted, in_session=in_session, paused=paused,
        failure_alert_active=failure, stale_alert_active=stale)


# --- stale_scan_verdict ----------------------------------------------------------

@pytest.mark.parametrize("kwargs, expected", [
    ({}, "alert"),
    ({"last": _ago(10)}, None),                                   # exactly 2x: not older
    ({"last": _ago(3)}, None),
    ({"last": "2026-10-12T14:49:00"}, "alert"),                   # naive read as UTC
    ({"in_session": False}, None),
    ({"paused": True}, None),
    ({"failure": True}, None),                                    # failure streak owns it
    ({"stale": True}, None),                                      # once per incident
    ({"booted": NOW - dt.timedelta(minutes=9)}, None),            # boot grace
    ({"booted": NOW - dt.timedelta(minutes=10)}, "alert"),        # up exactly 2x
    ({"last": None}, None),                                       # unknown is not stale
    ({"last": "not a timestamp"}, None),
    ({"last": _ago(3), "stale": True}, "recover"),
    ({"last": _ago(3), "stale": True, "in_session": False}, "recover"),
    ({"last": _ago(3), "stale": True, "paused": True}, "recover"),
    ({"last": None, "stale": True}, None),
])
def test_stale_scan_verdict(kwargs, expected):
    assert _stale(**kwargs) == expected


def test_booted_at_is_an_aware_utc_moment():
    assert ops_watch.BOOTED_AT.utcoffset() == dt.timedelta(0)


# --- provider_verdict ------------------------------------------------------------

@pytest.mark.parametrize("row, active, expected", [
    (ROW_OK, False, None),
    (ROW_OK, True, "recover"),
    (ROW_BAD, False, "alert"),
    (ROW_BAD, True, None),                                        # once per incident
    ({**ROW_OK, "provider_fallback_rate": 0.20}, False, None),    # at the line: not above
    ({**ROW_OK, "empty_rate": 0.06}, False, "alert"),
    ({**ROW_OK, "provider_fallback_rate": None}, False, None),    # Alpaca asked for nothing
    ({**ROW_OK, "provider_fallback_rate": None, "empty_rate": 0.5}, False, "alert"),
    (ROW_PRE_V148, False, None),
    (ROW_PRE_V148, True, None),                                   # unknown never recovers
    (None, True, None),
    ({}, False, None),
])
def test_provider_verdict(row, active, expected):
    assert ops_watch.provider_verdict(row, fallback_pct=20, empty_pct=5,
                                      alert_active=active) == expected


# --- the notices -----------------------------------------------------------------

@pytest.mark.parametrize("build, kind, colour", [
    (lambda: notices.stale_scan_embed(14, _ago(14)), Kind.HEALTH_ALERT, kinds.HEALTH_RED),
    (lambda: notices.stale_scan_recovered_embed(_ago(1)), Kind.HEALTH_RECOVERED,
     kinds.HEALTH_GREEN),
    (lambda: notices.provider_degraded_embed(ROW_BAD, 20.0, 5.0), Kind.HEALTH_ALERT,
     kinds.HEALTH_RED),
    (lambda: notices.provider_recovered_embed(ROW_OK), Kind.HEALTH_RECOVERED,
     kinds.HEALTH_GREEN),
])
def test_ops_notices_are_health_pushes(build, kind, colour):
    embed = build()
    assert embed.push_text.startswith(f"{kinds.badge(kind)} SYSTEM · {kind.label}")
    assert embed.color.value == colour
    assert embed.footer.text == "SYSTEM"


def test_the_stale_alert_names_the_age_and_the_last_success():
    embed = notices.stale_scan_embed(14, _ago(14))
    assert embed.title == "🚨 HEALTH ALERT · no completed scan tick for 14 min"
    assert f"Last successful tick: {_ago(14)}" in embed.description


def test_the_stale_recovery_names_the_last_success():
    embed = notices.stale_scan_recovered_embed(_ago(1))
    assert embed.title == f"{kinds.badge(Kind.HEALTH_RECOVERED)} RECOVERED · scan ticks completing again"
    assert f"Last successful tick: {_ago(1)}" in embed.description


def test_the_provider_alert_carries_rates_and_thresholds():
    embed = notices.provider_degraded_embed(ROW_BAD, 20.0, 5.0)
    assert embed.title == "🚨 HEALTH ALERT · market-data provider degraded"
    assert "Alpaca fallback: 25.0%, alert above 20%" in embed.description
    assert "Empty symbols: 6 of 100 (6.0%), alert above 5%" in embed.description
    assert "Stale symbols: 2" in embed.description
    assert f"Scan at: {ROW_BAD['at']}" in embed.description


def test_a_missing_rate_reads_as_a_dash_not_zero():
    embed = notices.provider_degraded_embed({**ROW_BAD, "provider_fallback_rate": None}, 20.0, 5.0)
    assert "Alpaca fallback: —, alert above 20%" in embed.description


def test_the_provider_recovery_shows_the_healthy_figures():
    embed = notices.provider_recovered_embed(ROW_OK)
    assert embed.title.endswith("RECOVERED · market-data provider healthy again")
    assert "Alpaca fallback: 5.0%" in embed.description
    assert "Empty symbols: 1 of 100 (1.0%)" in embed.description


# --- OH18: the watchdog loop, the provider check and the wiring --------------------

import ast
import asyncio
import inspect
import json
import logging
from pathlib import Path

from swingbot import config
from swingbot.commands.scanning import loops, runstate
from swingbot.core.infra import swallowed as swallowed_mod
from swingbot.core.scanning import telemetry


class _FakeChannel:
    def __init__(self, fail=False):
        self.sent, self.fail = [], fail

    async def send(self, content=None, **kw):
        if self.fail:
            raise RuntimeError("discord down")
        self.sent.append({"content": content, **kw})


@pytest.fixture(autouse=True)
def _clean_counts():
    swallowed_mod.reset()
    yield
    swallowed_mod.reset()


@pytest.fixture
def heartbeat(monkeypatch):
    """An in-memory heartbeat doc behind every runstate getter and setter."""
    doc = {}
    monkeypatch.setattr(runstate, "_read_heartbeat", lambda: dict(doc))
    monkeypatch.setattr(runstate, "_update_heartbeat", doc.update)
    monkeypatch.setattr(runstate, "is_scan_paused", lambda: False)
    monkeypatch.setattr(ops_watch, "in_session", lambda: True)
    monkeypatch.setattr(ops_watch, "BOOTED_AT", NOW - dt.timedelta(hours=2))
    monkeypatch.setattr(config, "SCAN_INTERVAL_MINUTES", INTERVAL)
    monkeypatch.setattr(config, "PROVIDER_FALLBACK_ALERT_PCT", 20)
    monkeypatch.setattr(config, "EMPTY_SYMBOLS_ALERT_PCT", 5)
    return doc


@pytest.fixture
def channel(monkeypatch):
    chan = _FakeChannel()
    monkeypatch.setattr(loops, "_ops_channel", lambda: chan)
    return chan


def _tick(now=NOW):
    return asyncio.run(ops_watch.watchdog_tick(now))


def test_a_wedged_tick_alerts_once_then_recovers_once(heartbeat, channel):
    heartbeat["last_success"] = _ago(14)
    assert _tick() == "alert"
    assert _tick() is None
    assert len(channel.sent) == 1
    assert channel.sent[0]["content"].startswith("🚨 SYSTEM · HEALTH ALERT")
    assert "no completed scan tick for 14 min" in channel.sent[0]["embed"].title
    assert heartbeat["stale_alert_active"] is True

    heartbeat["last_success"] = _ago(1)
    assert _tick() == "recover"
    assert _tick() is None
    assert len(channel.sent) == 2
    assert "scan ticks completing again" in channel.sent[1]["embed"].title
    assert heartbeat["stale_alert_active"] is False


@pytest.mark.parametrize("open_flag", ["stale_alert_active", "alert_active"])
def test_an_open_alert_suppresses_a_new_stale_post(heartbeat, channel, open_flag):
    """A restart with its stale alert still open; a failure-streak alert open."""
    heartbeat.update({"last_success": _ago(30), open_flag: True})
    assert _tick() is None and channel.sent == []


def test_no_ops_channel_posts_nothing_and_leaves_the_flag_unset(heartbeat, monkeypatch):
    monkeypatch.setattr(loops, "_ops_channel", lambda: None)
    heartbeat["last_success"] = _ago(30)
    assert _tick() is None
    assert "stale_alert_active" not in heartbeat


def test_a_raising_heartbeat_read_leaves_the_loop_running(heartbeat, monkeypatch, caplog):
    def down():
        raise RuntimeError("db down")

    monkeypatch.setattr(runstate, "last_success_iso", down)
    with caplog.at_level(logging.ERROR, logger=ops_watch.log.name):
        assert asyncio.run(ops_watch.scan_watchdog.coro()) is None
    entry = swallowed_mod.snapshot()["ops.scan_watchdog"]
    assert entry["count"] == 1 and entry["last_error"] == "RuntimeError: db down"
    assert "scan watchdog tick failed" in caplog.text


def test_a_failed_send_is_retried_on_the_next_tick(heartbeat, monkeypatch):
    real_now = dt.datetime.now(dt.timezone.utc)
    monkeypatch.setattr(ops_watch, "BOOTED_AT", real_now - dt.timedelta(hours=2))
    heartbeat["last_success"] = (real_now - dt.timedelta(minutes=30)).isoformat()
    monkeypatch.setattr(loops, "_ops_channel", lambda: _FakeChannel(fail=True))
    asyncio.run(ops_watch.scan_watchdog.coro())
    assert "stale_alert_active" not in heartbeat
    assert swallowed_mod.snapshot()["ops.scan_watchdog"]["count"] == 1

    good = _FakeChannel()
    monkeypatch.setattr(loops, "_ops_channel", lambda: good)
    asyncio.run(ops_watch.scan_watchdog.coro())
    assert len(good.sent) == 1 and heartbeat["stale_alert_active"] is True


def test_the_watchdog_runs_every_minute_with_the_other_loops():
    assert ops_watch.scan_watchdog in loops._always_on_loops()
    assert ops_watch.scan_watchdog.minutes == 1


def test_ops_watch_never_imports_loops_at_module_level():
    tree = ast.parse(Path(ops_watch.__file__).read_text(encoding="utf-8"))
    top = [node for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom))]
    names = [alias.name for node in top for alias in node.names]
    names += [node.module or "" for node in top if isinstance(node, ast.ImportFrom)]
    assert not [name for name in names if name.endswith("loops")]


def test_a_breaching_scan_alerts_once_then_recovers_once(heartbeat, channel):
    assert asyncio.run(ops_watch.check_provider_health(ROW_BAD)) == "alert"
    assert asyncio.run(ops_watch.check_provider_health(ROW_BAD)) is None
    assert "market-data provider degraded" in channel.sent[0]["embed"].title
    assert heartbeat["provider_alert_active"] is True

    assert asyncio.run(ops_watch.check_provider_health(ROW_OK)) == "recover"
    assert asyncio.run(ops_watch.check_provider_health(ROW_OK)) is None
    assert len(channel.sent) == 2
    assert heartbeat["provider_alert_active"] is False


def test_the_newest_scan_row_is_read_when_none_is_given(heartbeat, channel, tmp_path,
                                                        monkeypatch):
    path = tmp_path / "scan_telemetry.jsonl"
    rows = [ROW_OK, {"type": "deploy", "at": "2026-10-12T14:58:00+00:00"}, ROW_BAD]
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    monkeypatch.setattr(telemetry, "TELEMETRY_PATH", str(path))
    assert asyncio.run(ops_watch.check_provider_health()) == "alert"


def test_a_pre_v148_row_posts_nothing(heartbeat, channel):
    assert asyncio.run(ops_watch.check_provider_health(ROW_PRE_V148)) is None
    assert channel.sent == []


def test_a_failing_provider_check_never_raises(heartbeat, channel, monkeypatch):
    def broken(n=50, path=None):
        raise OSError("disk gone")

    monkeypatch.setattr(telemetry, "recent_scan_telemetry", broken)
    assert asyncio.run(ops_watch.check_provider_health()) is None
    assert swallowed_mod.snapshot()["ops.provider_health"]["count"] == 1


def test_the_scan_tick_checks_providers_after_the_scan():
    source = inspect.getsource(loops._session_scan_tick)
    check = source.index("await ops_watch.check_provider_health()")
    assert source.index("_refresh_snapshot_safely()") < check < source.index("f = progress.funnel")

"""v148 O3/O4: ops_watch -- the stale-scan and provider verdicts, the ops
notices, and (OH18) the watchdog loop and provider check on a fake channel."""
import contextlib
import datetime as dt

import pytest
import sqlalchemy as sa

from swingbot.commands.scanning import notices, ops_watch
from swingbot.core.db.engine import DatabaseUnavailable
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

#: v223: a pre-market scan -- every unanswered symbol was an old print, not a failure.
ROW_PRE_MARKET = {**ROW_OK, "provider_fallback_rate": 0.0, "old_print_rate": 0.92}


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
    (ROW_PRE_MARKET, False, None),                                # old prints never alert
    ({**ROW_PRE_MARKET, "provider_fallback_rate": 0.25}, False, "alert"),   # real misses still do
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
    assert (source.index("await asyncio.to_thread(_refresh_snapshot_safely)") < check
            < source.index("f = progress.funnel"))


# --- the stale notice explains itself (2026-11-06 morning incident) ------------------

def _snap(**kw):
    return {"tick_started_at": None, "tick_phase": None, "last_error": None,
            "last_error_at": None, "consecutive_failures": 0, **kw}


def test_moment_text_shows_utc_and_berlin():
    assert ops_watch.moment_text("2026-11-06T07:04:04+00:00") == "07:04 UTC (08:04 CET)"
    assert ops_watch.moment_text("2026-07-06T07:04:04+00:00") == "07:04 UTC (09:04 CEST)"
    assert ops_watch.moment_text("junk") == "junk"
    assert ops_watch.moment_text(None) == "None"


def test_cause_a_running_tick_is_slow_not_hung():
    started = (NOW - dt.timedelta(minutes=6)).isoformat()
    text = ops_watch.describe_stale_cause(
        NOW, _snap(tick_started_at=started, tick_phase="scan"), INTERVAL)
    assert "has run 6 min without finishing" in text
    assert "may just be slow" in text and "limit is 10 min" in text


def test_cause_a_failed_tick_names_the_error():
    text = ops_watch.describe_stale_cause(
        NOW, _snap(last_error="TimeoutError: boom", last_error_at=_ago(2),
                   consecutive_failures=2), INTERVAL)
    assert "2 in a row" in text and "`TimeoutError: boom`" in text


def test_cause_no_tick_started():
    text = ops_watch.describe_stale_cause(NOW, _snap(), INTERVAL)
    assert "No scan tick has started" in text and "stuck before the scan begins" in text


def test_the_alert_embed_carries_the_cause_and_falls_back_without_one():
    assert "custom cause" in notices.stale_scan_embed(14, "x", "custom cause").description
    assert "scheduled scan has not finished a tick" in notices.stale_scan_embed(14, "x").description


def test_the_watchdog_logs_the_alert_and_the_recovery(heartbeat, channel, caplog):
    heartbeat.update({"last_success": _ago(14), "tick_started_at": _ago(6), "tick_phase": "scan"})
    with caplog.at_level(logging.INFO, logger=ops_watch.log.name):
        assert _tick() == "alert"
        heartbeat["last_success"] = _ago(1)
        assert _tick() == "recover"
    assert "STALE alert posted" in caplog.text and "age_min=14" in caplog.text
    assert "tick_phase=scan" in caplog.text and "limit_min=10" in caplog.text
    assert "stale alert cleared" in caplog.text
    body = channel.sent[0]["embed"].description
    assert "has run 6 min without finishing" in body and "UTC (" in body


def test_the_watchdog_logs_when_there_is_no_ops_channel(heartbeat, monkeypatch, caplog):
    monkeypatch.setattr(loops, "_ops_channel", lambda: None)
    heartbeat["last_success"] = _ago(30)
    with caplog.at_level(logging.WARNING, logger=ops_watch.log.name):
        assert _tick() is None
    assert "no ops channel configured" in caplog.text


def test_tick_start_success_and_failure_keep_the_progress_keys(heartbeat):
    runstate.record_tick_start("scan")
    assert heartbeat["tick_phase"] == "scan" and heartbeat["tick_started_at"]
    runstate.record_tick_failure(ValueError("bad bar"))
    assert heartbeat["tick_started_at"] is None
    assert heartbeat["last_error"] == "ValueError: bad bar" and heartbeat["last_error_at"]
    snap = runstate.tick_snapshot()
    assert snap["last_error"] == "ValueError: bad bar" and snap["consecutive_failures"] == 1
    runstate.record_tick_success()
    assert heartbeat["last_error"] is None and heartbeat["tick_phase"] is None


def test_failure_without_an_exception_leaves_the_last_error_alone(heartbeat):
    heartbeat["last_error"] = "old"
    runstate.record_tick_failure()
    assert heartbeat["last_error"] == "old"


def test_the_provider_alert_shows_the_old_print_rate_of_live_price_asks():
    embed = notices.provider_degraded_embed({**ROW_BAD, "old_print_rate": 0.42}, 20.0, 5.0)
    assert "• Old IEX prints: 42.0% of live-price asks" in embed.description
    assert "Stale symbols: 2" in embed.description


def test_the_provider_recovery_shows_the_old_print_rate():
    embed = notices.provider_recovered_embed(ROW_PRE_MARKET)
    assert "• Old IEX prints: 92.0% of live-price asks" in embed.description


@pytest.mark.parametrize("build", [
    lambda row: notices.provider_degraded_embed(row, 20.0, 5.0),
    notices.provider_recovered_embed,
])
def test_a_row_without_the_old_print_rate_reads_as_a_dash(build):
    assert "• Old IEX prints: — of live-price asks" in build(ROW_BAD).description


# --- v248 § 5: held-price verdict, lines and embed ---------------------------------

def _held(**kw):
    base = dict(session="regular", age_s=11 * 60, has_last_close=True, uptime_s=3600,
                threshold_min=10, notified=False, recovered=False, pre_open=False)
    return ops_watch.held_price_verdict(**{**base, **kw})


@pytest.mark.parametrize("kwargs, expected", [
    ({}, "alert"),                                                    # live trade 11 min old
    ({"age_s": 600}, None),                                           # exactly 10 min: not older
    ({"age_s": 30}, None),
    ({"age_s": None}, "alert"),                                       # prev close in the session
    ({"session": "extended"}, None),
    ({"session": "closed"}, None),
    ({"session": "extended", "age_s": None}, None),                   # prev close pre-market is normal
    ({"session": "extended", "age_s": None, "pre_open": True}, None), # ... even at 09:00 ET
    ({"session": "extended", "pre_open": True}, None),                # a stale trade pre-open: not paged
    ({"uptime_s": 599}, None),                                        # boot grace
    ({"uptime_s": 600}, "alert"),                                     # up exactly the threshold
    ({"age_s": None, "uptime_s": 599}, None),                         # prev close keeps the grace
    ({"age_s": None, "has_last_close": False, "uptime_s": 5}, "alert"),   # no price at all: first sight
    ({"age_s": None, "has_last_close": False, "session": "extended"}, None),
    ({"age_s": None, "has_last_close": False, "session": "extended", "pre_open": True}, "alert"),
    ({"age_s": None, "has_last_close": False, "session": "closed", "pre_open": True}, "alert"),
    ({"notified": True}, None),                                       # once per ticker per day
    ({"notified": True, "age_s": None}, None),                        # still blind
    ({"notified": True, "age_s": 30}, "recover"),
    ({"notified": True, "age_s": 600}, "recover"),                    # at the line counts as fresh
    ({"notified": True, "age_s": 30, "session": "extended"}, "recover"),
    ({"notified": True, "recovered": True, "age_s": 30}, None),       # one recovery only
    ({"notified": True, "recovered": True, "age_s": 3600}, None),     # no second alert that day
    ({"threshold_min": 30}, None),                                    # hot-reloaded threshold
    ({"threshold_min": 30, "age_s": 31 * 60}, "alert"),
])
def test_held_price_verdict(kwargs, expected):
    assert _held(**kwargs) == expected


@pytest.mark.parametrize("utc, expected", [
    (dt.datetime(2026, 11, 25, 14, 0, tzinfo=dt.timezone.utc), True),    # Wed 09:00 ET (EST)
    (dt.datetime(2026, 11, 25, 13, 59, tzinfo=dt.timezone.utc), False),  # 08:59 ET
    (dt.datetime(2026, 11, 25, 14, 29, tzinfo=dt.timezone.utc), True),   # 09:29 ET
    (dt.datetime(2026, 11, 25, 14, 30, tzinfo=dt.timezone.utc), False),  # 09:30: the open
    (dt.datetime(2026, 10, 12, 13, 5, tzinfo=dt.timezone.utc), True),    # Mon 09:05 ET (EDT)
    (dt.datetime(2026, 11, 27, 14, 5, tzinfo=dt.timezone.utc), True),    # half-day still opens 09:30
    (dt.datetime(2026, 11, 26, 14, 5, tzinfo=dt.timezone.utc), False),   # Thanksgiving
    (dt.datetime(2026, 11, 28, 14, 5, tzinfo=dt.timezone.utc), False),   # Saturday
])
def test_in_pre_open_window(utc, expected):
    assert ops_watch.in_pre_open_window(utc) is expected


def _item(sym, age_s=None, error=None, prev_close=False, no_price=False):
    return ops_watch.HeldPriceItem(sym, age_s, error, prev_close, no_price)


def test_held_price_lines_read_one_ticker_per_line():
    assert ops_watch.held_price_lines([
        _item("AAPL", age_s=14 * 60 + 5, error="no quote"),
        _item("DOCU", prev_close=True, error="no quote"),
        _item("NEWCO", no_price=True),
        _item("SNDK", age_s=12),
    ]) == [
        "• AAPL · last trade 14 min ago · no quote",
        "• DOCU · no live trade · prev close · no quote",
        "• NEWCO · no live trade · no price at all",
        "• SNDK · last trade 12 s ago",
    ]


@pytest.mark.parametrize("age_s, text", [
    (59, "59 s ago"), (60, "1 min ago"), (119 * 60 + 59, "119 min ago"),
    (120 * 60, "2 h ago"), (47 * 3600 + 59 * 60, "47 h ago"), (48 * 3600, "2 d ago"),
])
def test_held_price_line_ages(age_s, text):
    assert ops_watch.held_price_lines([_item("AAPL", age_s=age_s)]) == [f"• AAPL · last trade {text}"]


def test_a_long_error_is_cut_to_sixty_characters_on_one_line():
    error = "YFPricesMissingError('possibly delisted;\n  no price data found (period=1d)') and more"
    (line,) = ops_watch.held_price_lines([_item("DOCU", prev_close=True, error=error)])
    tail = line.split(" · ", 3)[3]
    assert len(tail) == 60 and tail.endswith("…") and "\n" not in line
    assert tail.startswith("YFPricesMissingError('possibly delisted; no price data")


def test_an_error_of_exactly_sixty_characters_is_kept_whole():
    (line,) = ops_watch.held_price_lines([_item("DOCU", prev_close=True, error="e" * 60)])
    assert line.endswith(" · " + "e" * 60)


def test_more_than_ten_tickers_end_with_a_count():
    lines = ops_watch.held_price_lines([_item(f"T{i:02d}", no_price=True) for i in range(13)])
    assert len(lines) == 11 and lines[9].startswith("• T09 ") and lines[10] == "+3 more"
    assert len(ops_watch.held_price_lines([_item(f"T{i}", no_price=True) for i in range(10)])) == 10
    assert ops_watch.held_price_lines([]) == []


def test_the_held_price_alert_and_recovery_embeds():
    alert = notices.held_price_embed(["• DOCU · no live trade · prev close"], recovery=False)
    assert alert.push_text.startswith(f"{kinds.badge(Kind.HEALTH_ALERT)} SYSTEM · {Kind.HEALTH_ALERT.label}")
    assert alert.color.value == kinds.HEALTH_RED
    assert "held position price stale" in alert.title
    assert alert.description.startswith("• DOCU · no live trade · prev close\n")
    assert "No trade is changed" in alert.description

    rec = notices.held_price_embed(["• DOCU · last trade 12 s ago"], recovery=True)
    assert rec.color.value == kinds.HEALTH_GREEN
    assert "held position price live again" in rec.title
    assert rec.description == "• DOCU · last trade 12 s ago"


# --- v248 § 5: held_price_watch -------------------------------------------------------

class _FakeShared:
    def __init__(self):
        self.rows = {}

    def read_entries(self, keys, *, conn):
        return {k: dict(self.rows[k]) for k in keys if k in self.rows}

    def write_entries(self, rows, *, conn):
        for row in rows:
            self.rows[row["key"]] = dict(row)


def _q(sym, price, age_s, error=None):
    from swingbot.admin.market_values import MarketQuote
    as_of = None if age_s is None else (NOW - dt.timedelta(seconds=age_s)).isoformat()
    return MarketQuote(symbol=sym, price=price, as_of=as_of, age_s=age_s, refreshing=False,
                       error=error)


@pytest.fixture
def held(monkeypatch):
    """AAPL's live trade is 14 min old; DOCU has bid/ask only (no trade) and a daily
    close; NEWCO has nothing at all. NOW is Mon 2026-10-12 11:00 ET, regular session."""
    from swingbot.admin import market_values as mv
    state = {"tickers": ["AAPL", "DOCU", "NEWCO"], "enqueue": [], "shared": _FakeShared(),
             "quotes": {"AAPL": _q("AAPL", 101.0, 14 * 60, "no quote"),
                        "DOCU": _q("DOCU", None, 15 * 3600, "no quote")},
             "closes": {"DOCU": {"last_close": 80.0, "last_close_date": "2026-10-09"}}}

    def read_quotes(symbols, *, kind=None, enqueue=True, now=None):
        state["enqueue"].append(enqueue)
        return {s: state["quotes"][s] for s in symbols if s in state["quotes"]}

    monkeypatch.setattr(mv, "read_quotes", read_quotes)
    monkeypatch.setattr(mv, "last_close_fields",
                        lambda symbols: {s: state["closes"][s] for s in symbols if s in state["closes"]})
    monkeypatch.setattr(ops_watch, "_held_tickers", lambda: list(state["tickers"]))
    monkeypatch.setattr(ops_watch, "market_shared_repo", lambda: state["shared"])
    monkeypatch.setattr(ops_watch, "side_connection", contextlib.nullcontext)
    monkeypatch.setattr(ops_watch, "BOOTED_AT", NOW - dt.timedelta(hours=2))
    monkeypatch.setattr(config, "HELD_PRICE_STALE_ALERT_MIN", 10)
    monkeypatch.setattr(config, "ADMIN_REFRESHER", "on")
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")
    return state


def _held_tick(now=NOW):
    return asyncio.run(ops_watch.held_price_tick(now))


QUIET = {"alert": [], "recover": []}


def test_stale_and_blind_held_prices_alert_once_in_one_message(held, channel):
    assert _held_tick() == {"alert": ["AAPL", "DOCU", "NEWCO"], "recover": []}
    assert len(channel.sent) == 1
    embed = channel.sent[0]["embed"]
    assert "held position price stale" in embed.title
    assert embed.description.splitlines()[:3] == [
        "• AAPL · last trade 14 min ago · no quote",
        "• DOCU · no live trade · prev close · no quote",      # never a bid/ask midpoint
        "• NEWCO · no live trade · no price at all"]
    assert _held_tick() == QUIET and len(channel.sent) == 1
    row = held["shared"].rows["ops_held_price:AAPL:2026-10-12"]
    assert row["kind"] == "ops_held_price" and row["symbol"] == "AAPL" and row["source"] == "ops_watch"
    assert row["value"] == {"notified_at": NOW.isoformat(), "recovered_at": None}


def test_a_fresh_price_recovers_once_and_the_day_stays_quiet(held, channel):
    _held_tick()
    held["quotes"]["AAPL"] = _q("AAPL", 102.0, 12)
    assert _held_tick() == {"alert": [], "recover": ["AAPL"]}
    assert "held position price live again" in channel.sent[1]["embed"].title
    assert channel.sent[1]["embed"].description == "• AAPL · last trade 12 s ago"
    assert held["shared"].rows["ops_held_price:AAPL:2026-10-12"]["value"] == {
        "notified_at": NOW.isoformat(), "recovered_at": NOW.isoformat()}
    held["quotes"]["AAPL"] = _q("AAPL", 102.0, 40 * 60)       # stale again the same day
    assert _held_tick() == QUIET and len(channel.sent) == 2


def test_the_dedupe_survives_a_restart(held, channel, monkeypatch):
    _held_tick()
    fresh = _FakeChannel()
    monkeypatch.setattr(loops, "_ops_channel", lambda: fresh)
    monkeypatch.setattr(ops_watch, "BOOTED_AT", NOW)          # the bot just came back
    assert _held_tick() == QUIET and fresh.sent == []


def test_a_new_session_day_alerts_again(held, channel):
    _held_tick()
    assert _held_tick(NOW + dt.timedelta(days=1))["alert"] == ["AAPL", "DOCU", "NEWCO"]
    assert "ops_held_price:NEWCO:2026-10-13" in held["shared"].rows


def test_the_boot_grace_holds_back_all_but_no_price_at_all(held, channel, monkeypatch):
    monkeypatch.setattr(ops_watch, "BOOTED_AT", NOW - dt.timedelta(minutes=5))
    assert _held_tick() == {"alert": ["NEWCO"], "recover": []}


def test_the_tick_never_enqueues_a_fetch(held, channel):
    _held_tick()
    assert held["enqueue"] == [False]


def test_outside_the_session_only_the_pre_open_check_runs(held, channel):
    pre_market = dt.datetime(2026, 10, 12, 12, 0, tzinfo=dt.timezone.utc)    # 08:00 ET
    assert _held_tick(pre_market) == QUIET
    assert held["enqueue"] == [] and channel.sent == []
    pre_open = dt.datetime(2026, 10, 12, 13, 5, tzinfo=dt.timezone.utc)      # 09:05 ET
    assert _held_tick(pre_open) == {"alert": ["NEWCO"], "recover": []}       # DOCU on prev close: normal
    after_hours = dt.datetime(2026, 10, 12, 21, 0, tzinfo=dt.timezone.utc)   # 17:00 ET
    assert _held_tick(after_hours) == QUIET


def test_the_pre_open_check_is_quiet_on_an_nyse_holiday(held, channel):
    thanksgiving = dt.datetime(2026, 11, 26, 14, 5, tzinfo=dt.timezone.utc)
    assert _held_tick(thanksgiving) == QUIET and channel.sent == []


@pytest.mark.parametrize("exc", [DatabaseUnavailable("side engine backing off"),
                                 sa.exc.TimeoutError("QueuePool limit of size 1 overflow 1 reached")])
def test_a_busy_side_pool_skips_the_tick(held, channel, monkeypatch, exc):
    def busy():
        raise exc
    monkeypatch.setattr(ops_watch, "side_connection", busy)
    assert _held_tick() == QUIET and channel.sent == []


def test_the_tick_reads_nothing_with_the_refresher_off(held, channel, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_REFRESHER", "off")
    assert _held_tick() == QUIET
    assert held["enqueue"] == [] and channel.sent == []


def test_no_held_tickers_reads_no_quotes(held, channel):
    held["tickers"] = []
    assert _held_tick() == QUIET and held["enqueue"] == []


def test_no_ops_channel_posts_nothing_and_stores_nothing(held, monkeypatch):
    monkeypatch.setattr(loops, "_ops_channel", lambda: None)
    assert _held_tick() == QUIET and held["shared"].rows == {}


def test_twelve_blind_tickers_share_one_message(held, channel):
    held["tickers"] = [f"N{i:02d}" for i in range(12)]
    assert len(_held_tick()["alert"]) == 12 and len(channel.sent) == 1
    lines = channel.sent[0]["embed"].description.splitlines()
    assert lines[9].startswith("• N09 ") and lines[10] == "+2 more"
    assert len(held["shared"].rows) == 12                      # every ticker deduped, listed or not


def test_a_failed_send_stores_nothing_and_the_next_tick_retries(held, monkeypatch):
    monkeypatch.setattr(loops, "_ops_channel", lambda: _FakeChannel(fail=True))
    with pytest.raises(RuntimeError, match="discord down"):
        _held_tick()
    assert held["shared"].rows == {}
    good = _FakeChannel()
    monkeypatch.setattr(loops, "_ops_channel", lambda: good)
    assert _held_tick()["alert"] == ["AAPL", "DOCU", "NEWCO"] and len(good.sent) == 1


def test_a_raising_held_price_tick_leaves_the_loop_running(monkeypatch, caplog):
    async def boom(now=None):
        raise RuntimeError("db down")
    monkeypatch.setattr(ops_watch, "held_price_tick", boom)
    with caplog.at_level(logging.ERROR, logger=ops_watch.log.name):
        assert asyncio.run(ops_watch.held_price_watch.coro()) is None
    assert swallowed_mod.snapshot()["ops.held_price_watch"]["count"] == 1
    assert "held price watch tick failed" in caplog.text


def test_held_tickers_are_the_open_trades_upper_cased_and_unique(monkeypatch):
    from swingbot.core.db.repositories import trades as trades_mod

    class _Repo:
        def open_trades(self, *, conn=None):
            return [{"ticker": "docu"}, {"ticker": "AAPL"}, {"ticker": None}, {"ticker": "aapl"}]

    monkeypatch.setattr(trades_mod, "trades_repo", lambda: _Repo())
    assert ops_watch._held_tickers() == ["AAPL", "DOCU"]


def test_the_held_price_watch_runs_every_two_minutes_after_the_scan_watchdog():
    order = loops._always_on_loops()
    assert order.index(ops_watch.held_price_watch) == order.index(ops_watch.scan_watchdog) + 1
    assert ops_watch.held_price_watch.minutes == 2

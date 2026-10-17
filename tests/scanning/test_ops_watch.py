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

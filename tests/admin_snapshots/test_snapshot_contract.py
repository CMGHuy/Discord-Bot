"""v204: snapshot staleness, cadence, budget-derived mark timeout and key shapes."""
from datetime import datetime, timezone

import pytest

from swingbot import config
from swingbot.core.analytics import scope
from swingbot.core.marketdata.shared import admin_refresh as ar

UTC = timezone.utc


def test_snapshot_staleness_reads_config_at_call_time(monkeypatch):
    assert ar.stale_after_s("snapshot", "regular") == 600.0
    assert ar.stale_after_s("snapshot", "extended") == 1800.0
    assert ar.stale_after_s("snapshot", "closed") is None      # closed rule lives in the door and the SPA
    monkeypatch.setattr(config, "ADMIN_STALE_SNAPSHOT_REGULAR_S", 61)
    assert ar.stale_after_s("snapshot", "regular") == 61.0
    assert ar.stale_after_s("price", "regular") == float(config.ADMIN_STALE_PRICE_REGULAR_S)
    with pytest.raises(ValueError):
        ar.stale_after_s("bogus", "regular")


def test_snapshot_cadence_per_session(monkeypatch):
    assert [ar.snapshot_cadence_s(s) for s in ("regular", "extended", "closed")] == [300.0, 900.0, 3600.0]
    monkeypatch.setattr(config, "ADMIN_SNAPSHOT_EXTENDED_S", 120)
    assert ar.snapshot_cadence_s("extended") == 120.0
    with pytest.raises(ValueError):
        ar.snapshot_cadence_s("lunch")


def test_mark_timeout_is_budget_plus_thirty(monkeypatch):
    assert ar.snapshot_mark_timeout_s() == 120.0
    monkeypatch.setattr(config, "ADMIN_SNAPSHOT_BUDGET_S", 45)
    assert ar.snapshot_mark_timeout_s() == 75.0


def test_fixed_keys_and_ledgers_match_scope():
    assert (ar.SNAPSHOT_RISK, ar.SNAPSHOT_ANALYTICS) == ("risk", "analytics.snapshot")
    assert ar._LEDGERS == scope.LEDGERS


@pytest.mark.parametrize("ledger", ["main", "weak", "both"])
def test_ledger_keys(ledger):
    assert ar.performance_key(ledger) == f"analytics.performance:{ledger}"
    assert ar.equity_curve_key(ledger) == f"analytics.equity_curve:{ledger}"


@pytest.mark.parametrize("bad", ["", "Main", "all", "main "])
def test_ledger_keys_reject_unknown_ledgers(bad):
    with pytest.raises(ValueError):
        ar.performance_key(bad)
    with pytest.raises(ValueError):
        ar.equity_curve_key(bad)


def test_calendar_key_takes_a_real_month_only():
    assert ar.calendar_key("2026-10") == "calendar.pnl:2026-10"
    for bad in ("2026-13", "2026-1", "2026-00", "oct", ""):
        with pytest.raises(ValueError):
            ar.calendar_key(bad)


@pytest.mark.parametrize("key", ["risk", "analytics.snapshot", "analytics.performance:main",
                                 "analytics.equity_curve:both", "calendar.pnl:2026-09"])
def test_is_snapshot_key_accepts_the_five_shapes(key):
    assert ar.is_snapshot_key(key) is True


@pytest.mark.parametrize("key", ["", "RISK", "risk:main", "quote:AAPL", "snapshot:risk",
                                 "analytics.performance", "analytics.performance:all",
                                 "calendar.pnl:2026-13", "calendar.pnl:2026-9", None, 7])
def test_is_snapshot_key_rejects_everything_else(key):
    assert ar.is_snapshot_key(key) is False


def test_mark_keys_round_trip():
    assert ar.snapshot_mark_key("calendar.pnl:2026-10") == "snapshot:calendar.pnl:2026-10"
    assert ar.snapshot_key_of("snapshot:calendar.pnl:2026-10") == "calendar.pnl:2026-10"
    assert ar.snapshot_key_of("quote:AAPL") is None
    assert ar.snapshot_key_of("snapshot:bogus") is None
    with pytest.raises(ValueError):
        ar.snapshot_mark_key("quote:AAPL")


@pytest.mark.parametrize("now,months", [
    (datetime(2026, 10, 30, 15, 0, tzinfo=UTC), ("2026-10", "2026-09")),
    (datetime(2026, 1, 10, 15, 0, tzinfo=UTC), ("2026-01", "2025-12")),
    (datetime(2026, 11, 1, 3, 0, tzinfo=UTC), ("2026-10", "2026-09")),   # 23:00 ET on Oct 31
])
def test_calendar_months_use_the_new_york_date(now, months):
    assert ar.calendar_months(now) == months


def test_calendar_months_default_to_now():
    current, previous = ar.calendar_months()
    assert ar.is_snapshot_key(ar.calendar_key(current)) and ar.is_snapshot_key(ar.calendar_key(previous))

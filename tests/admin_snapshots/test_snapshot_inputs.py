"""v204: what a snapshot records, and when its bars count as stale."""
from datetime import date, datetime, timezone

import pytest

from swingbot import config
from swingbot.core.analytics import admin_snapshots as snaps
from swingbot.core.market import session
from swingbot.core.marketdata.daily_readonly import ReadOnlyBars

NOW = datetime(2026, 9, 16, 15, 0, tzinfo=timezone.utc)          # Wed 11:00 ET
REAL_CODE_VERSION = snaps._code_version
FP = {"AAPL": {"path": "/m/daily/AAPL.csv", "mtime": 1.0, "last_bar": "2026-09-15", "rows": 500},
      "SPY": {"path": "/m/daily/SPY.csv", "mtime": 2.0, "last_bar": "2026-09-14", "rows": 500},
      "SAP.DE": {"path": "/m/daily/SAP.DE.csv", "mtime": 3.0, "last_bar": "2026-09-15", "rows": 9}}
BARS = ReadOnlyBars(frames={"AAPL": object(), "SPY": object()},
                    missing={"SAP.DE": "short:9/21", "XAUUSD": "spot_metal"}, fingerprints=FP)


@pytest.fixture(autouse=True)
def knobs(monkeypatch):
    for key, value in (("ADMIN_STALE_SNAPSHOT_REGULAR_S", 600), ("ADMIN_STALE_SNAPSHOT_EXTENDED_S", 1800),
                       ("ADMIN_STALE_PRICE_REGULAR_S", 120), ("ADMIN_STALE_PRICE_EXTENDED_S", 900)):
        monkeypatch.setattr(config, key, value)
    monkeypatch.setattr(snaps, "_code_version", lambda: "2.16.0")


def test_build_inputs_has_the_contract_shape():
    got = snaps.build_inputs(
        computed_at=NOW,
        quotes={"MSFT": {"price": 410.5, "as_of": "2026-09-16T14:58:30+00:00"},
                "AAPL": {"price": 230.1, "as_of": "2026-09-16T10:59:00-04:00"}},
        fx={"EUR": {"rate": 1.08, "as_of": "2026-09-15"}, "GBP": {"rate": 1.27, "as_of": "2026-09-14"}},
        bars=BARS, missing_quotes=["NEWX"], missing_fx=["SAP.DE", "SAP.DE"],
        ledger="main", trade_ids=[9, 7])
    assert got == {
        "computed_at": NOW.isoformat(),
        "oldest_quote_as_of": "2026-09-16T14:58:30+00:00",
        "quotes": {"MSFT": {"price": 410.5, "as_of": "2026-09-16T14:58:30+00:00"},
                   "AAPL": {"price": 230.1, "as_of": "2026-09-16T10:59:00-04:00"}},
        "fx": {"EUR": {"rate": 1.08, "as_of": "2026-09-15"}, "GBP": {"rate": 1.27, "as_of": "2026-09-14"}},
        "oldest_fx_as_of": "2026-09-14",
        "bars_as_of": {"per_symbol": {"AAPL": "2026-09-15", "SPY": "2026-09-14"},
                       "oldest": "2026-09-14", "newest": "2026-09-15"},
        "bar_files": FP,
        "missing": {"quotes": ["NEWX"], "fx": ["SAP.DE"],
                    "bars": {"SAP.DE": "short:9/21", "XAUUSD": "spot_metal"}},
        "ledger": "main", "trade_ids": [9, 7],
        "thresholds": {"stale_snapshot_regular_s": 600.0, "stale_snapshot_extended_s": 1800.0,
                       "stale_price_regular_s": 120.0, "stale_price_extended_s": 900.0},
        "code_version": "2.16.0"}


def test_build_inputs_with_nothing_recorded():
    got = snaps.build_inputs(computed_at=NOW)
    assert got["oldest_quote_as_of"] is None and got["oldest_fx_as_of"] is None
    assert got["bars_as_of"] == {"per_symbol": {}, "oldest": None, "newest": None}
    assert got["missing"] == {"quotes": [], "fx": [], "bars": {}} and got["bar_files"] == {}


def test_code_version_is_the_bot_line_of_version_json(monkeypatch, tmp_path):
    (tmp_path / "VERSION.json").write_text('{"ui": "1.0.0", "bot": "9.9.9"}')
    monkeypatch.setattr(snaps, "_code_version", REAL_CODE_VERSION)
    monkeypatch.setattr(config, "_PROJECT_ROOT", str(tmp_path))
    assert snaps._code_version() == "9.9.9"


def utc(y, m, d, hh, mm):
    return datetime(y, m, d, hh, mm, tzinfo=timezone.utc)


def test_expected_bar_date_monday_morning_after_a_holiday_friday():
    assert snaps.expected_bar_date(utc(2026, 4, 6, 13, 40)) == date(2026, 4, 2)    # Mon 09:40 ET


def test_expected_bar_date_saturday():
    assert snaps.expected_bar_date(utc(2026, 10, 31, 15, 0)) == date(2026, 10, 30)


def test_expected_bar_date_before_the_scan_updates_the_file():
    assert snaps.expected_bar_date(utc(2026, 10, 28, 21, 30)) == date(2026, 10, 27)  # Wed 17:30 ET


def test_expected_bar_date_after_20_et_is_today():
    assert snaps.expected_bar_date(utc(2026, 10, 29, 1, 0)) == date(2026, 10, 28)    # Wed 21:00 ET


def test_expected_bar_date_half_day_waits_like_a_full_day():
    assert snaps.expected_bar_date(utc(2026, 11, 27, 19, 0)) == date(2026, 11, 25)   # Fri 14:00 ET


def test_expected_bar_date_has_one_source(monkeypatch):
    seen = []
    monkeypatch.setattr(session, "last_regular_close",
                        lambda now=None: seen.append(now) or utc(2026, 9, 15, 20, 0))
    assert snaps.expected_bar_date(NOW) == date(2026, 9, 15) and seen == [NOW]


@pytest.mark.parametrize("per_symbol, stale", [
    ({"AAPL": "2026-09-15", "SPY": "2026-09-15"}, False),
    ({"AAPL": "2026-09-15", "SPY": "2026-09-14"}, True),
    ({"XAUUSD": "2026-09-01", "AAPL": "2026-09-15"}, False),   # spot metal never makes it stale
    ({"XAUUSD": "2026-09-01"}, False),
    ({}, False),
])
def test_stale_inputs_compare_with_the_last_completed_session(per_symbol, stale):
    assert snaps.stale_inputs_for(per_symbol, now=NOW) is stale


def test_monday_after_holiday_is_not_stale_on_thursday_bars():
    assert snaps.stale_inputs_for({"AAPL": "2026-04-02"}, now=utc(2026, 4, 6, 13, 40)) is False

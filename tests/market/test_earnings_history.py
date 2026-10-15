import datetime as dt

from swingbot import config
from swingbot.core.market import earnings_history
from swingbot.core.infra.jsonio import atomic_write_json


def test_weekly_refresh_preserves_past_dates_and_sets_next(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    now = dt.datetime(2026, 9, 19, tzinfo=dt.timezone.utc)
    monkeypatch.setattr(
        earnings_history,
        "get_earnings_datetimes",
        lambda symbol, refresh=False: [
            dt.datetime(2026, 8, 1, tzinfo=dt.timezone.utc),
            dt.datetime(2026, 10, 30, tzinfo=dt.timezone.utc),
        ],
    )

    snapshot = earnings_history.refresh_watchlist_earnings(["aapl"], now=now)

    assert snapshot["symbols"]["AAPL"] == {
        "next": "2026-10-30T00:00:00+00:00",
        "past": ["2026-08-01T00:00:00+00:00"],
    }


def test_weekly_refresh_moves_an_elapsed_prior_next_date_to_history(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    atomic_write_json(str(tmp_path / "earnings_history.json"), {
        "updated_at": "2026-09-01T00:00:00+00:00",
        "symbols": {"AAPL": {"next": "2026-09-10T00:00:00+00:00", "past": []}},
    })
    monkeypatch.setattr(
        earnings_history,
        "get_earnings_datetimes",
        lambda symbol, refresh=False: [dt.datetime(2026, 10, 30, tzinfo=dt.timezone.utc)],
    )

    snapshot = earnings_history.refresh_watchlist_earnings(
        ["AAPL"], now=dt.datetime(2026, 9, 19, tzinfo=dt.timezone.utc),
    )

    assert snapshot["symbols"]["AAPL"] == {
        "next": "2026-10-30T00:00:00+00:00",
        "past": ["2026-09-10T00:00:00+00:00"],
    }


def test_cached_dates_read_the_ledger_without_fetching(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(earnings_history, "get_earnings_datetimes",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("fetched")))
    atomic_write_json(str(tmp_path / "earnings_history.json"), {
        "updated_at": "2026-09-19T00:00:00+00:00",
        "symbols": {
            "AAPL": {"next": "2026-10-30T20:30:00+00:00", "past": ["2026-07-30T20:30:00+00:00", 7]},
            "MSFT": {"next": None, "past": []},
            "BAD": "not-a-dict",
        },
    })
    utc = dt.timezone.utc
    assert earnings_history.cached_earnings_datetimes(" aapl ") == [
        dt.datetime(2026, 7, 30, 20, 30, tzinfo=utc), dt.datetime(2026, 10, 30, 20, 30, tzinfo=utc)]
    assert earnings_history.cached_earnings_datetimes("MSFT") is None
    assert earnings_history.cached_earnings_datetimes("BAD") is None
    assert earnings_history.cached_earnings_datetimes("NVDA") is None


def test_cached_dates_with_no_ledger_file_is_none(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    assert earnings_history.cached_earnings_datetimes("AAPL") is None

"""v172: GET /api/v1/equity/candles -- the contract the SPA's EquityCandlesResponse mirrors."""
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from swingbot import config
from swingbot.core.db.repositories.equity_samples import EquitySampleRepository
from tests.admin.api_v1_contract import (NULLABLE_NUMBER, NULLABLE_STR, NUMBER, assert_error,
                                         assert_shape)
from tests.store_seed import seed_store

URL = "/api/v1/equity/candles"
BASE = 10000.0

BODY = {"tf": str, "basis": str, "currency_symbol": str, "candles": list, "has_more": bool,
        "recording_since": NULLABLE_STR, "as_of": str}
CANDLE = {"t": str, "o": NUMBER, "h": NUMBER, "l": NUMBER, "c": NUMBER, "change": NUMBER,
          "change_pct": NULLABLE_NUMBER, "samples": int, "skipped": int, "approx": bool}


@pytest.fixture
def logged_in(client):
    from swingbot.admin import app

    response = client.post("/api/v1/session", json={
        "username": app.ADMIN_USERNAME, "password": app.ADMIN_PASSWORD,
    })
    assert response.status_code == 200
    return client


@pytest.fixture
def account(admin_app):
    # base_balance stated outright: the conftest seeds only `balance`, and
    # load_account_config would then derive the base from realized P&L.
    seed_store("account", {"base_balance": BASE, "balance": BASE, "risk_pct": 1.0,
                           "max_position_pct": 20.0, "sizing_mode": "risk_pct",
                           "balance_history": []})


def _at(day, hour, minute=0):
    return datetime(2026, 10, day, hour, minute, tzinfo=timezone.utc)


def _row(at, value, *, source="live", kind="point", skipped=0):
    return {"at": at, "realized_balance": Decimal(str(value)), "unrealized_pnl": Decimal("0"),
            "equity": Decimal(str(value)), "open_n": 0, "skipped_n": skipped,
            "source": source, "kind": kind,
            "backfill_run": "r1@bars-asof-2026-10-13" if source == "backfill" else None}


def _two_live_days():
    """Wed 2026-10-14 and Thu 2026-10-15, New York session hours (EDT = UTC-4)."""
    EquitySampleRepository().upsert_many([
        _row(_at(14, 13, 35), 10000), _row(_at(14, 15), 10100), _row(_at(14, 19, 55), 10050),
        _row(_at(15, 13, 35), 10080), _row(_at(15, 19, 55), 10200, skipped=2),
    ])


def _backfilled_tuesday():
    """Tue 2026-10-13 rebuilt from daily bars: open 09:30 NY, close 16:00 NY."""
    EquitySampleRepository().upsert_many([
        _row(_at(13, 13, 30), 9900, source="backfill"),
        _row(_at(13, 13, 30), 9950, source="backfill", kind="day_high"),
        _row(_at(13, 13, 30), 9880, source="backfill", kind="day_low"),
        _row(_at(13, 20), 9920, source="backfill"),
    ])


def _closed(tid, pnl, closed_at):
    return {"id": tid, "ticker": "AAPL", "direction": "bullish", "status": "win" if pnl > 0 else "loss",
            "entry": 100.0, "stop_loss": 95.0, "exit_price": 100.0 + pnl / 10, "shares": 10.0,
            "opened_at": "2026-10-13T14:00:00+00:00", "closed_at": closed_at,
            "realized_pnl_amount": pnl, "ledger": "main", "horizon_key": "1m", "strategy": "RSI"}


def _utc(year, month, day, hour, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


def _page_all(client, **query):
    """Every candle, fetched one page of one candle at a time through the
    `before` cursor, oldest first."""
    candles, before = [], None
    while True:
        params = {**query, "limit": 1, **({"before": before} if before else {})}
        body = client.get(URL, query_string=params).get_json()
        candles = body["candles"] + candles
        if not body["has_more"]:
            return candles
        before = body["candles"][0]["t"]


def test_requires_auth(client):
    assert_error(client.get(URL), "auth", 401)


def test_an_empty_table_returns_the_defaults_and_no_candles(logged_in, account):
    body = logged_in.get(URL).get_json()
    assert_shape(body, BODY)
    assert (body["tf"], body["basis"], body["candles"]) == ("1D", "mtm", [])
    assert body["currency_symbol"] == config.CURRENCY_SYMBOL
    assert body["recording_since"] is None
    assert datetime.fromisoformat(body["as_of"]).tzinfo is not None


def test_daily_mtm_candles_from_live_samples(logged_in, account):
    _two_live_days()
    body = logged_in.get(URL).get_json()
    for candle in body["candles"]:
        assert_shape(candle, CANDLE, where="candle")
    first, second = body["candles"]
    assert (first["t"], first["o"], first["h"], first["l"], first["c"]) == (
        "2026-10-14", 10000.0, 10100.0, 10000.0, 10050.0)
    assert (first["change"], first["change_pct"], first["samples"]) == (50.0, 0.5, 3)
    assert (second["t"], second["o"], second["c"], second["change"]) == (
        "2026-10-15", 10080.0, 10200.0, 150.0)
    assert second["change_pct"] == 1.49                     # 150 / 10050 x 100
    assert (second["skipped"], second["approx"]) == (2, False)
    assert body["recording_since"] == "2026-10-14T13:35:00+00:00"


def test_limit_keeps_the_latest_candles_and_their_true_predecessor_change(logged_in, account):
    _two_live_days()
    (only,) = logged_in.get(URL + "?limit=1").get_json()["candles"]
    assert (only["t"], only["change"]) == ("2026-10-15", 150.0)


def test_daily_mtm_includes_backfill_rows_as_approx(logged_in, account):
    _backfilled_tuesday()
    _two_live_days()
    first = logged_in.get(URL + "?tf=1D").get_json()["candles"][0]
    assert (first["t"], first["o"], first["h"], first["l"], first["c"]) == (
        "2026-10-13", 9900.0, 9950.0, 9880.0, 9920.0)
    assert first["approx"] is True


def test_hourly_mtm_never_reads_backfill_rows(logged_in, account):
    _backfilled_tuesday()
    _two_live_days()
    body = logged_in.get(URL + "?tf=1H").get_json()
    assert body["tf"] == "1H"
    assert body["candles"][0]["t"] == "2026-10-14T09:00:00-04:00"
    assert not any(c["t"].startswith("2026-10-13") for c in body["candles"])
    assert not any(c["approx"] for c in body["candles"])
    four = logged_in.get(URL + "?tf=4H").get_json()["candles"]
    assert not any(c["t"].startswith("2026-10-13") for c in four)


def test_realized_basis_steps_through_closed_legs_not_samples(logged_in, account):
    seed_store("trades", [_closed("t1", 50.0, "2026-10-14T15:00:00+00:00"),
                          _closed("t2", -20.0, "2026-10-14T18:00:00+00:00")])
    body = logged_in.get(URL + "?basis=realized").get_json()
    assert body["basis"] == "realized"
    (day,) = body["candles"]
    assert (day["t"], day["o"], day["h"], day["l"], day["c"]) == (
        "2026-10-14", 10000.0, 10050.0, 10000.0, 10030.0)
    assert (day["samples"], day["skipped"], day["approx"]) == (2, 0, False)
    assert body["recording_since"] is None                  # no live rows yet


@pytest.mark.parametrize("query, name", [
    ("tf=1M", "tf"), ("tf=1d", "tf"), ("basis=gross", "basis"),
    ("limit=0", "limit"), ("limit=501", "limit"), ("limit=abc", "limit"),
])
def test_a_bad_parameter_is_a_400_naming_the_allowed_values(logged_in, account, query, name):
    response = logged_in.get(f"{URL}?{query}")
    assert_error(response, "invalid", 400)
    message = response.get_json()["error"]["message"]
    assert message.startswith(f"{name} must be one of")


def test_the_tf_error_lists_every_timeframe(logged_in, account):
    message = logged_in.get(URL + "?tf=2H").get_json()["error"]["message"]
    assert message == "tf must be one of 1H, 4H, 1D, 1W"


def test_the_limit_cap_itself_is_allowed(logged_in, account):
    assert logged_in.get(URL + "?limit=500").status_code == 200


# --- v181: the `before` cursor and `has_more` ------------------------------------

def test_has_more_is_false_when_every_candle_fits(logged_in, account):
    _two_live_days()
    body = logged_in.get(URL).get_json()
    assert (len(body["candles"]), body["has_more"]) == (2, False)


def test_has_more_is_true_when_the_limit_cut_older_candles(logged_in, account):
    _two_live_days()
    body = logged_in.get(URL + "?limit=1").get_json()
    assert ([c["t"] for c in body["candles"]], body["has_more"]) == (["2026-10-15"], True)


def test_before_is_exclusive_of_the_cursor_bucket(logged_in, account):
    _backfilled_tuesday()
    _two_live_days()
    body = logged_in.get(URL + "?before=2026-10-15").get_json()
    assert [c["t"] for c in body["candles"]] == ["2026-10-13", "2026-10-14"]
    assert body["has_more"] is False


def test_before_with_a_limit_keeps_the_newest_older_candles(logged_in, account):
    _backfilled_tuesday()
    _two_live_days()
    body = logged_in.get(URL + "?before=2026-10-15&limit=1").get_json()
    assert ([c["t"] for c in body["candles"]], body["has_more"]) == (["2026-10-14"], True)


def test_a_page_keeps_the_change_measured_on_the_full_series(logged_in, account):
    _backfilled_tuesday()
    _two_live_days()
    (only,) = logged_in.get(URL + "?before=2026-10-15&limit=1").get_json()["candles"]
    full_middle = logged_in.get(URL).get_json()["candles"][1]
    assert only == full_middle                     # change vs Tuesday's close, not its own open


def test_before_the_oldest_candle_is_an_empty_page(logged_in, account):
    _two_live_days()
    body = logged_in.get(URL + "?before=2026-10-14").get_json()
    assert (body["candles"], body["has_more"]) == ([], False)


def test_before_past_the_newest_candle_returns_the_latest(logged_in, account):
    _two_live_days()
    body = logged_in.get(URL + "?before=2026-12-01").get_json()
    assert [c["t"] for c in body["candles"]] == ["2026-10-14", "2026-10-15"]


@pytest.mark.parametrize("tf", ["1H", "4H", "1D", "1W"])
def test_the_cursor_round_trips_for_every_timeframe(logged_in, account, tf):
    _two_live_days()
    full = logged_in.get(URL, query_string={"tf": tf}).get_json()["candles"]
    assert full                                              # the fixture yields candles on every tf
    assert _page_all(logged_in, tf=tf) == full


def test_paging_works_on_the_realized_basis_and_carries_the_prior_close(logged_in, account):
    seed_store("trades", [_closed("t1", 50.0, "2026-10-13T15:00:00+00:00"),
                          _closed("t2", -20.0, "2026-10-14T15:00:00+00:00"),
                          _closed("t3", 30.0, "2026-10-15T15:00:00+00:00")])
    newest = logged_in.get(URL + "?basis=realized&limit=1").get_json()
    assert newest["has_more"] is True
    (latest,) = newest["candles"]
    older = logged_in.get(URL, query_string={"basis": "realized", "limit": 1,
                                             "before": latest["t"]}).get_json()
    (previous,) = older["candles"]
    assert (previous["t"], latest["t"]) == ("2026-10-14", "2026-10-15")
    assert latest["o"] == previous["c"]                      # the first o is the true prior balance
    assert _page_all(logged_in, basis="realized") == logged_in.get(
        URL + "?basis=realized").get_json()["candles"]


def _fall_back_night():
    """Sun 1 Nov 2026: 00:30 EDT, 01:30 EDT, 01:30 EST (repeated hour), 02:30 EST."""
    EquitySampleRepository().upsert_many([
        _row(_utc(2026, 11, 1, 4, 30), 10000), _row(_utc(2026, 11, 1, 5, 30), 10010),
        _row(_utc(2026, 11, 1, 6, 30), 10020), _row(_utc(2026, 11, 1, 7, 30), 10030),
    ])


def _spring_forward_night():
    """Sun 8 Mar 2026: 00:30 EST, 01:30 EST, 03:30 EDT (02:00-03:00 skipped), 04:30 EDT."""
    EquitySampleRepository().upsert_many([
        _row(_utc(2026, 3, 8, 5, 30), 10000), _row(_utc(2026, 3, 8, 6, 30), 10010),
        _row(_utc(2026, 3, 8, 7, 30), 10020), _row(_utc(2026, 3, 8, 8, 30), 10030),
    ])


@pytest.mark.parametrize("night", [_fall_back_night, _spring_forward_night])
@pytest.mark.parametrize("tf", ["1H", "4H"])
def test_paging_across_a_dst_change_loses_and_duplicates_no_candle(logged_in, account, night, tf):
    night()
    full = logged_in.get(URL, query_string={"tf": tf}).get_json()["candles"]
    paged = _page_all(logged_in, tf=tf)
    assert paged == full
    assert len({c["t"] for c in paged}) == len(paged)


def test_the_fall_back_night_has_two_distinct_01_00_candles(logged_in, account):
    _fall_back_night()
    times = [c["t"] for c in logged_in.get(URL + "?tf=1H").get_json()["candles"]]
    assert "2026-11-01T01:00:00-04:00" in times
    assert "2026-11-01T01:00:00-05:00" in times


@pytest.mark.parametrize("query", [
    {"tf": "1D", "before": "2026-10-15T00:00:00-04:00"},   # datetime on a date timeframe
    {"tf": "1W", "before": "2026-10-12T00:00:00-04:00"},
    {"tf": "1H", "before": "2026-10-15"},                  # date on an intraday timeframe
    {"tf": "4H", "before": "2026-10-15"},
    {"tf": "1H", "before": "2026-10-15T10:00:00"},         # naive
    {"tf": "1D", "before": "abc"},
    {"tf": "1D", "before": ""},
])
def test_any_other_before_shape_is_a_400(logged_in, account, query):
    response = logged_in.get(URL, query_string=query)
    assert_error(response, "invalid", 400)
    assert response.get_json()["error"]["message"].startswith("before must be")

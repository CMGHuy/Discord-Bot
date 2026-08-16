"""NG13 — /api/v1/watchlist/*.

Spec v11 Decision 4 collapses the Jinja UI's separate `/watchlist/add` and
`/watchlist/bulk_add` into one endpoint taking a list. Those two only exist
because an HTML form cannot post an array, which stops mattering once the
client speaks JSON.

**These are the first tests in the repo that WRITE to the watchlist**, which
turned up a live hazard: `swingbot.core.marketdata.watchlist.DEFAULT_PATH` is computed
at import time from `config.DATA_DIR`, so it ignores the per-test
monkeypatch and points at the real project's data/watchlist.json. Reading
through it is merely wrong; writing through it would edit the user's actual
watchlist from a test run. The endpoints therefore pass an explicit path
resolved per call -- `test_writes_land_in_the_isolated_data_dir` is the
guard that keeps it that way.
"""
import json

import pytest

from tests.admin.api_v1_contract import assert_error, assert_shape

_LOGIN = {"username": "admin", "password": "admin"}


@pytest.fixture
def watchlist(admin_app, tmp_path):
    """The isolated watchlist file, seeded and readable."""
    path = tmp_path / "watchlist.json"

    def _set(tickers):
        path.write_text(json.dumps(list(tickers)), encoding="utf-8")

    def _get():
        return json.loads(path.read_text()) if path.exists() else []

    _set([])
    _set.read = _get
    _set.path = path
    return _set


@pytest.fixture
def logged_in(client):
    client.post("/api/v1/session", json=_LOGIN)
    return client


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Company-name resolution, earnings-date lookup and history warm-up all
    reach the network. None of that is what these tests are about, and a test
    suite that depends on yfinance being reachable fails for reasons that
    have nothing to do with the code."""
    monkeypatch.setattr("swingbot.core.marketdata.data.get_company_name", lambda t: f"{t} Inc.")
    monkeypatch.setattr("swingbot.core.market.events.get_next_earnings_datetime", lambda t: None)
    monkeypatch.setattr("swingbot.core.marketdata.backtest_cache.ensure_cached_background",
                        lambda t: None)


@pytest.fixture(autouse=True)
def clean_earnings_cache():
    """`events._earnings_datetime_cache` is a module-level dict with a 6h
    TTL -- real across the whole test process, not per-request. Without
    this, one test seeding "AAPL" would leak into every later test that
    happens to use the same symbol. Cleared before AND after: after, so a
    background warm-up thread from THIS test (started by _next_earnings for
    an uncached ticker) writing in after the test has already moved on
    cannot poison the next one either."""
    from swingbot.core.market import events
    events._earnings_datetime_cache.clear()
    yield
    events._earnings_datetime_cache.clear()


def test_requires_auth(client):
    assert_error(client.get("/api/v1/watchlist/tickers"), "auth", 401)


def test_list_is_empty_initially(watchlist, logged_in):
    assert logged_in.get("/api/v1/watchlist/tickers").get_json() == {"tickers": []}


def test_list_shape(watchlist, logged_in):
    watchlist(["AAPL"])
    body = logged_in.get("/api/v1/watchlist/tickers").get_json()
    assert_shape(body["tickers"][0], {
        "symbol": str, "company_name": (str, type(None)),
        "open_trades": int, "closed_trades": int,
        "next_earnings_date": (str, type(None)),
        "next_earnings_datetime": (str, type(None)),
    }, where="ticker")


def test_next_earnings_fields_are_iso_strings_from_the_cache(watchlist, logged_in):
    # _next_earnings only ever reads the cache (never fetches inline -- see
    # its own docstring for why), so the way to give a ticker a known
    # earnings time in a test is to seed the cache directly, exactly as a
    # prior request's background warm-up would have.
    import datetime as dt
    import time as time_module
    from swingbot.core.market import events

    # UTC-4 (EDT): 16:00 local is 20:00 UTC -- both fields must reflect the
    # UTC-converted value, not the source's own -04:00 offset.
    tz = dt.timezone(dt.timedelta(hours=-4))
    events._earnings_datetime_cache["AAPL"] = (
        dt.datetime(2026, 9, 3, 16, 0, tzinfo=tz), time_module.monotonic())

    watchlist(["AAPL"])
    row = logged_in.get("/api/v1/watchlist/tickers").get_json()["tickers"][0]
    assert row["next_earnings_date"] == "2026-09-03"
    assert row["next_earnings_datetime"] == "2026-09-03T20:00:00+00:00"


def test_next_earnings_fields_null_when_confirmed_no_data(watchlist, logged_in):
    # A cached None (Yahoo checked, nothing found) is a different case from
    # "never checked" below -- both render null on the wire, but only this
    # one should NOT trigger a background warm-up (it's already resolved).
    import time as time_module
    from swingbot.core.market import events

    events._earnings_datetime_cache["AAPL"] = (None, time_module.monotonic())

    watchlist(["AAPL"])
    row = logged_in.get("/api/v1/watchlist/tickers").get_json()["tickers"][0]
    assert row["next_earnings_date"] is None
    assert row["next_earnings_datetime"] is None


def test_next_earnings_fields_null_and_non_blocking_when_not_yet_cached(watchlist, logged_in):
    # The whole point of the fix: a ticker with nothing in the cache must
    # render null immediately rather than the response waiting on a live
    # Yahoo call. Real timing (not just correctness) is asserted here since
    # that IS the bug being guarded against -- a correct-but-slow response
    # would still reproduce it.
    import time as time_module

    watchlist(["AAPL"])
    started = time_module.monotonic()
    row = logged_in.get("/api/v1/watchlist/tickers").get_json()["tickers"][0]
    elapsed = time_module.monotonic() - started

    assert row["next_earnings_date"] is None
    assert row["next_earnings_datetime"] is None
    assert elapsed < 1.0


def test_an_uncached_ticker_triggers_a_background_warm_up(watchlist, logged_in, monkeypatch):
    warmed = []
    monkeypatch.setattr("swingbot.core.market.events.warm_earnings_cache_background",
                        lambda tickers: warmed.extend(tickers))
    watchlist(["AAPL"])
    logged_in.get("/api/v1/watchlist/tickers")
    assert warmed == ["AAPL"]


def test_a_cached_ticker_does_not_trigger_a_background_warm_up(watchlist, logged_in, monkeypatch):
    import time as time_module
    from swingbot.core.market import events

    events._earnings_datetime_cache["AAPL"] = (None, time_module.monotonic())
    warmed = []
    monkeypatch.setattr("swingbot.core.market.events.warm_earnings_cache_background",
                        lambda tickers: warmed.extend(tickers))
    watchlist(["AAPL"])
    logged_in.get("/api/v1/watchlist/tickers")
    assert warmed == []


def test_add_a_single_ticker(watchlist, logged_in):
    r = logged_in.post("/api/v1/watchlist/tickers", json={"tickers": ["AAPL"]})
    assert r.status_code == 200
    assert r.get_json()["added"] == ["AAPL"]
    assert watchlist.read() == ["AAPL"]


def test_writes_land_in_the_isolated_data_dir(watchlist, logged_in):
    """The guard for the hazard in this module's docstring. If the endpoint
    ever goes back to watchlist.DEFAULT_PATH, this file stays empty and the
    REAL watchlist grows a ticker."""
    logged_in.post("/api/v1/watchlist/tickers", json={"tickers": ["ZZZZ"]})
    assert "ZZZZ" in watchlist.read(), (
        "the write went somewhere other than the test's DATA_DIR -- most "
        "likely the real data/watchlist.json"
    )


def test_one_endpoint_handles_bulk(watchlist, logged_in):
    r = logged_in.post("/api/v1/watchlist/tickers", json={"tickers": ["AAPL", "MSFT", "NVDA"]})
    assert sorted(r.get_json()["added"]) == ["AAPL", "MSFT", "NVDA"]


def test_a_pasted_blob_is_accepted(watchlist, logged_in):
    """How the bulk form is actually used: comma/space/newline separated."""
    r = logged_in.post("/api/v1/watchlist/tickers", json={"tickers": "AAPL, MSFT\nNVDA"})
    assert sorted(r.get_json()["added"]) == ["AAPL", "MSFT", "NVDA"]


def test_one_bad_symbol_does_not_fail_the_batch(watchlist, logged_in):
    """Pasting thirty tickers with one typo should add twenty-nine and name
    the one, not refuse everything."""
    r = logged_in.post("/api/v1/watchlist/tickers",
                       json={"tickers": ["AAPL", "not a ticker!", "MSFT"]})
    body = r.get_json()
    assert sorted(body["added"]) == ["AAPL", "MSFT"]
    assert body["invalid"] == ["NOT A TICKER!"]


def test_already_present_is_reported_separately_from_added(watchlist, logged_in):
    watchlist(["AAPL"])
    body = logged_in.post("/api/v1/watchlist/tickers",
                          json={"tickers": ["AAPL", "MSFT"]}).get_json()
    assert body["added"] == ["MSFT"]
    assert body["already_present"] == ["AAPL"]


def test_symbols_with_real_punctuation_are_valid(watchlist, logged_in):
    """BRK.B, RDS-A and EURUSD=X are all legitimate."""
    body = logged_in.post("/api/v1/watchlist/tickers",
                          json={"tickers": ["BRK.B", "RDS-A", "EURUSD=X"]}).get_json()
    assert body["invalid"] == []


def test_a_non_list_body_is_rejected(watchlist, logged_in):
    assert_error(logged_in.post("/api/v1/watchlist/tickers", json={"tickers": 5}),
                 "invalid", 400)


def test_remove_a_ticker(watchlist, logged_in):
    watchlist(["AAPL", "MSFT"])
    r = logged_in.delete("/api/v1/watchlist/tickers/AAPL")
    assert r.status_code == 200
    assert watchlist.read() == ["MSFT"]


def test_remove_is_case_insensitive(watchlist, logged_in):
    watchlist(["AAPL"])
    assert logged_in.delete("/api/v1/watchlist/tickers/aapl").status_code == 200


def test_removing_an_absent_ticker_is_404(watchlist, logged_in):
    assert_error(logged_in.delete("/api/v1/watchlist/tickers/NOPE"), "not_found", 404)


def test_trade_counts_are_attached(watchlist, logged_in, tmp_path):
    from tests.admin.test_api_v1_trades import _trade
    watchlist(["AAPL"])
    (tmp_path / "trades.json").write_text(json.dumps([
        _trade("aaaaaaaaaaaaaaaa", plan_id=None, status="open"),
        _trade("bbbbbbbbbbbbbbbb", plan_id=None, status="win"),
    ]), encoding="utf-8")
    row = logged_in.get("/api/v1/watchlist/tickers").get_json()["tickers"][0]
    assert row["open_trades"] == 1
    assert row["closed_trades"] == 1

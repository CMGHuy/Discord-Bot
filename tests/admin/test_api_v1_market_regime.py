"""v239 V239-12: GET /api/v1/market/regime -- the stored day for D, 60 sessions, the episode."""
from datetime import date, datetime, timedelta, timezone

import pytest

from swingbot import config
from swingbot.admin.api_v1 import iso
from swingbot.core.db.repositories import market_regime as regime_repo
from swingbot.core.market import bear_regime as br
from swingbot.core.presentation import regime_text
from swingbot.core.scanning import regime_calendar
from tests.admin.api_v1_contract import NULLABLE_NUMBER, NULLABLE_STR, assert_error, assert_shape

URL = "/api/v1/market/regime"
NOW = datetime(2026, 11, 18, 21, 5, tzinfo=timezone.utc)     # after the 11-18 close: D = 11-19
D = date(2026, 11, 19)
T0 = datetime(2026, 11, 18, 21, 5, 30, tzinfo=timezone.utc)
EMPTY_OFF = {"mode": "off", "today": None, "history": [], "episode": None}
FLOATS = ("spy_close", "sma50", "sma200", "sma50_lag5", "sma200_lag20", "spy_high_prev",
          "vix_close", "vix_max5")
WIRE = {"session_date": str, "last_bar_date": NULLABLE_STR, "state": str,
        "stress": (bool, type(None)), "pullback_trigger": bool, "pullback_reason": NULLABLE_STR,
        **{name: NULLABLE_NUMBER for name in FLOATS}, "spy_provider": NULLABLE_STR,
        "vix_provider": NULLABLE_STR, "computed_at": str, "display": dict}
NUMBERS = dict(spy_close=650.0, sma50=716.0, sma200=690.0, vix_close=37.6)


def _row(day, state="CORRECTION", stress=True, **over):
    row = {name: None for name in br.ROW_COLUMNS}
    row.update(session_date=day, last_bar_date=day - timedelta(days=1), state=state, stress=stress,
               pullback_trigger=False, spy_provider="alpaca", vix_provider="yfinance",
               computed_at=T0, doc={"unknown_reason": None}, **NUMBERS)
    row.update(over)
    return row


def _rows(states, end=D):
    """One row per state, oldest first, the last dated ``end`` (calendar days are enough here)."""
    return [_row(end - timedelta(days=len(states) - 1 - i), *state)
            for i, state in enumerate(states)]


class _Repo:
    def __init__(self, rows=(), fail=False):
        self.rows, self.fail, self.calls = list(rows), fail, []

    def recent(self, limit=60, *, conn=None):
        self.calls.append(limit)
        if self.fail:
            raise RuntimeError("db down")
        return self.rows[-limit:]


@pytest.fixture
def shadow(monkeypatch):
    monkeypatch.setattr(config, "BEAR_REGIME_MODE", "shadow")


@pytest.fixture(autouse=True)
def _app_loaded(admin_app):
    """app.py's body runs first, so register() imports the endpoint module whole."""
    yield


def _api():
    # endpoint modules load after app.py's body (circular-import note in api_v1/__init__.py)
    from swingbot.admin.api_v1 import market_regime
    return market_regime


def _payload(repo, now=NOW):
    return _api().regime_payload(now=now, repo=repo)


def test_the_wire_restates_the_classifier_row():
    assert set(WIRE) - {"computed_at", "display"} == set(br.ROW_COLUMNS)
    assert (_api().HISTORY_LIMIT, _api().EPISODE_ROWS) == (60, 500)


@pytest.mark.parametrize("mode", ["off", "bogus", ""])
def test_off_or_an_unknown_mode_sends_the_empty_shape_and_reads_nothing(monkeypatch, mode):
    monkeypatch.setattr(config, "BEAR_REGIME_MODE", mode)
    repo = _Repo(_rows([("CORRECTION", True)]))
    assert _payload(repo) == EMPTY_OFF and repo.calls == []


def test_an_empty_table_sends_no_day_and_no_history(shadow):
    assert _payload(_Repo()) == {"mode": "shadow", "today": None, "history": [], "episode": None}


def test_today_is_the_stored_row_for_d_with_its_display(shadow):
    body = _payload(_Repo(_rows([("CORRECTION", True)] * 3)))
    today = body["today"]
    assert (today["session_date"], today["last_bar_date"]) == ("2026-11-19", "2026-11-18")
    assert today["computed_at"] == iso(T0) and "doc" not in today
    assert today["display"] == {"label": "Correction · Stress", "words": "dip in an uptrend, high volatility",
                                "numbers": regime_text.number_line(**NUMBERS)}


def test_no_row_for_d_means_no_today_and_never_the_prior_label(shadow):
    body = _payload(_Repo(_rows([("BEAR", None)] * 3, end=D - timedelta(days=1))))
    assert body["today"] is None and len(body["history"]) == 3


def test_an_unknown_day_reads_no_reading(shadow):
    row = _row(D, "UNKNOWN", None, **{name: None for name in FLOATS})
    today = _payload(_Repo([row]))["today"]
    assert today["display"] == {"label": "No reading", "words": "—", "numbers": None}
    assert all(today[name] is None for name in FLOATS)


def test_history_is_the_last_60_oldest_first(shadow):
    rows = _rows([("NORMAL", False)] * 70)
    history = _payload(_Repo(rows))["history"]
    assert len(history) == 60
    assert history[0]["session_date"] == rows[10]["session_date"].isoformat()
    assert [h["session_date"] for h in history] == sorted(h["session_date"] for h in history)


@pytest.mark.parametrize("states, episode", [
    ([("NORMAL", False)] * 3 + [("CORRECTION", True)] * 4, {"label": "Correction · Stress", "since_sessions": 4}),
    ([("NORMAL", False)] * 3 + [("CORRECTION", False)] + [("NORMAL", False)] * 3,   # flicker merges
     {"label": "Normal", "since_sessions": 7}),
    ([("CORRECTION", False)] * 2 + [("CORRECTION", True)] * 2, {"label": "Correction · Stress", "since_sessions": 2}),
    ([("BEAR", None)], None)])                                                      # one session: unconfirmed
def test_the_episode_is_the_confirmed_run(shadow, states, episode):
    assert _payload(_Repo(_rows(states)))["episode"] == episode


def test_the_episode_counts_past_the_history_window(shadow):
    repo = _Repo(_rows([("BEAR", None)] * 100))
    body = _payload(repo)
    assert repo.calls == [_api().EPISODE_ROWS]
    assert len(body["history"]) == 60 and body["episode"] == {"label": "Bear", "since_sessions": 100}


def test_live_reports_live(monkeypatch):
    monkeypatch.setattr(config, "BEAR_REGIME_MODE", "live")
    assert _payload(_Repo(_rows([("BEAR", None)] * 2)))["mode"] == "live"


@pytest.mark.parametrize("breakage", ["store", "calendar"])
def test_an_unreadable_store_or_calendar_sends_nothing_stale(shadow, monkeypatch, breakage):
    repo = _Repo(_rows([("BEAR", None)] * 3), fail=breakage == "store")
    if breakage == "calendar":
        def past_the_calendar(now):
            raise ValueError("no NYSE session after 2030-12-31 in the frozen calendar")
        monkeypatch.setattr(regime_calendar, "session_pair", past_the_calendar)
    assert _payload(repo) == {"mode": "shadow", "today": None, "history": [], "episode": None}


def test_the_endpoint_requires_auth(client):
    assert_error(client.get(URL), "auth", 401)


def test_the_endpoint_shape(client, auth, shadow, monkeypatch):
    monkeypatch.setattr(regime_repo, "market_regime_repo", lambda: _Repo(_rows([("CORRECTION", True)] * 3)))
    monkeypatch.setattr(regime_calendar, "session_pair", lambda now: (D - timedelta(days=1), D))
    response = client.get(URL, headers=auth)
    assert response.status_code == 200
    body = response.get_json()
    assert_shape(body, {"mode": str, "today": dict, "history": list, "episode": dict})
    for day in (body["today"], *body["history"]):
        assert_shape(day, WIRE, where="day")
        assert_shape(day["display"], {"label": str, "words": str, "numbers": NULLABLE_STR}, where="display")
    assert_shape(body["episode"], {"label": str, "since_sessions": int}, where="episode")


def test_the_endpoint_under_off_reads_nothing(client, auth, monkeypatch):
    monkeypatch.setattr(config, "BEAR_REGIME_MODE", "off")
    monkeypatch.setattr(regime_repo, "market_regime_repo", lambda: pytest.fail("off read the store"))
    assert client.get(URL, headers=auth).get_json() == EMPTY_OFF

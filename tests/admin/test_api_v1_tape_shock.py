"""v210: GET /api/v1/market/tape carries the market-shock state for the SPA badge."""
from datetime import date, datetime, timezone

import pytest

from swingbot import config
from swingbot.core.db.repositories import market_shock
from swingbot.core.market import shock

_LOGIN = {"username": "admin", "password": "admin"}
SINCE = datetime(2026, 11, 5, 14, 45, tzinfo=timezone.utc)
STATE = {"label": "SHOCK", "since": SINCE, "session_date": date(2026, 11, 5),
         "vix_session_high": 21.4, "last_reading_id": 7, "last_notice_at": None,
         "updated_at": SINCE, "doc": {}}


def reading(**over):
    fields = dict(as_of=datetime(2026, 11, 5, 15, 0, tzinfo=timezone.utc),
                  session_date=date(2026, 11, 5), minutes_since_open=90.0, breadth_frac=0.4237,
                  depth_frac=0.3,
                  sectors_down=5, sectors_total=8, breadth_speed=0.12, spy_atr_move=-1.8,
                  qqq_atr_move=-2.3, spy_last=671.2, spy_prev_close=683.0,
                  spy_session_low=670.9, spy_new_low=True, spy_retrace=0.05, vix_level=21.13,
                  vix_chg_pct=27.2, vix_session_high=21.4, vix_off_high_pct=1.3, n_names=61,
                  insufficient=False) | over
    return shock.ShockReading(**fields).as_row() | {"id": 7, "state_after": "SHOCK"}


class _Repo:
    def __init__(self, state=None, latest=None, fail=False):
        self.state, self.latest, self.fail = state, latest, fail

    def current_state(self, *, conn=None):
        if self.fail:
            raise RuntimeError("db down")
        return self.state

    def latest_reading(self, *, conn=None):
        return self.latest


@pytest.fixture
def logged_in(client):
    client.post("/api/v1/session", json=_LOGIN)
    return client


@pytest.fixture(autouse=True)
def no_daily_batch_network(monkeypatch):
    from swingbot.admin import tape_cache
    tape_cache.reset()
    monkeypatch.setattr("swingbot.core.marketdata.data.get_daily_data_batch", lambda syms: {})
    monkeypatch.setattr(config, "MARKET_SHOCK_MODE", "shadow")


def _shock(client, monkeypatch, repo, symbols="^GSPC"):
    monkeypatch.setattr(market_shock, "market_shock_repo", lambda: repo)
    resp = client.get(f"/api/v1/market/tape?symbols={symbols}")
    assert resp.status_code == 200
    return resp.get_json()["shock"]


def test_the_state_and_its_last_reading_reach_the_badge(logged_in, monkeypatch):
    assert _shock(logged_in, monkeypatch, _Repo(STATE, reading())) == {
        "label": "SHOCK", "since": "2026-11-05T14:45:00+00:00",
        "as_of": "2026-11-05T15:00:00+00:00", "breadth_pct": 42.4, "sectors_down": 5,
        "sectors_total": 8, "spy_atr_move": -1.8, "qqq_atr_move": -2.3, "vix_level": 21.13,
        "vix_chg_pct": 27.2, "vix_missing": False}


def test_a_reading_without_vix_says_vix_missing(logged_in, monkeypatch):
    got = _shock(logged_in, monkeypatch, _Repo(STATE, reading(vix_level=None, vix_chg_pct=None)))
    assert got["vix_missing"] is True and got["vix_level"] is None


def test_a_state_row_without_a_reading_has_empty_numbers(logged_in, monkeypatch):
    got = _shock(logged_in, monkeypatch, _Repo(STATE, None))
    assert got["label"] == "SHOCK" and got["as_of"] is None and got["breadth_pct"] is None
    assert got["vix_missing"] is True


@pytest.mark.parametrize("mode", ["off", "bogus"])
def test_off_or_an_unknown_mode_sends_null_and_reads_nothing(logged_in, monkeypatch, mode):
    monkeypatch.setattr(config, "MARKET_SHOCK_MODE", mode)
    assert _shock(logged_in, monkeypatch, _Repo(fail=True)) is None


def test_no_state_row_yet_sends_null(logged_in, monkeypatch):
    assert _shock(logged_in, monkeypatch, _Repo(None, None)) is None


def test_a_dead_store_never_fails_the_tape(logged_in, monkeypatch):
    assert _shock(logged_in, monkeypatch, _Repo(fail=True)) is None


def test_the_empty_symbols_reply_carries_the_key_too(logged_in, monkeypatch):
    assert _shock(logged_in, monkeypatch, _Repo(STATE, reading()), symbols="")["label"] == "SHOCK"

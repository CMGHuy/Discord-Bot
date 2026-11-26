"""v248 § 4: yfinance per-ticker backoff, shared through market_cache rows of kind yf_backoff."""
import contextlib
import logging
from datetime import datetime, timedelta, timezone

import pytest
import sqlalchemy as sa

from swingbot import config
from swingbot.core.db import side_engine
from swingbot.core.db.engine import DatabaseUnavailable
from swingbot.core.db.repositories import trades as trades_mod
from swingbot.core.db.repositories.market_shared import MarketSharedRepository
from swingbot.core.marketdata import yf_backoff as bo
from swingbot.core.marketdata.yf_backoff import BackoffState

UTC = timezone.utc
T0 = datetime(2026, 11, 24, 15, 0, tzinfo=UTC)        # Tue 10:00 ET, regular session
CAP = timedelta(minutes=10)


@pytest.fixture(autouse=True)
def _fresh():
    bo._reset_for_tests()
    yield
    bo._reset_for_tests()


def _misses(n, now=T0):
    state = BackoffState()
    for _ in range(n):
        state = bo.after_miss(state, now)
    return state


# -- pure policy -------------------------------------------------------------------

def test_entry_key_is_upper_case_per_symbol():
    assert bo.KIND == "yf_backoff" and bo.entry_key("docu") == "yf_backoff:DOCU"


def test_two_misses_never_skip():
    state = _misses(2)
    assert (state.misses, state.skip_until) == (2, None)
    assert not bo.is_skipped(state, T0, held_in_session=False, held_cap=CAP)


def test_third_miss_skips_for_30_minutes():
    state = _misses(3)
    assert state.skip_until == T0 + timedelta(minutes=30) and state.written_at == T0
    assert bo.is_skipped(state, T0 + timedelta(minutes=29), held_in_session=False, held_cap=CAP)
    assert not bo.is_skipped(state, T0 + timedelta(minutes=30), held_in_session=False, held_cap=CAP)


@pytest.mark.parametrize("n, pause_min", [(4, 60), (5, 120), (6, 240), (7, 240), (400, 240)])
def test_each_further_miss_doubles_the_pause_capped_at_4h(n, pause_min):
    assert _misses(n).skip_until == T0 + timedelta(minutes=pause_min)


def test_held_ticker_in_session_is_capped_at_the_alert_threshold():
    state = _misses(6)                                   # 4 h pause written at T0
    assert bo.is_skipped(state, T0 + timedelta(minutes=9), held_in_session=True, held_cap=CAP)
    assert not bo.is_skipped(state, T0 + timedelta(minutes=10), held_in_session=True, held_cap=CAP)
    assert bo.is_skipped(state, T0 + timedelta(minutes=10), held_in_session=False, held_cap=CAP)


# -- shared store ------------------------------------------------------------------

@pytest.fixture
def store(db_committed, db_engine, monkeypatch):
    monkeypatch.setattr(config, "DATABASE_URL", db_engine.url.render_as_string(hide_password=False))
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")
    monkeypatch.setattr(bo, "held_symbols", lambda now=None: frozenset())
    side_engine.reset()
    yield db_committed
    side_engine.reset()


def _miss_n(symbols, n, now=T0):
    for _ in range(n):
        bo.record(bo.partition(symbols, now), [], now)


def test_unknown_tickers_are_all_fetched(store):
    batch = bo.partition(["AAPL", "DOCU"], T0)
    assert (batch.fetch, batch.skipped, batch.known) == (["AAPL", "DOCU"], [], True)


def test_three_misses_skip_and_the_row_is_shared(store):
    _miss_n(["DOCU"], 3)
    side_engine.reset()                                  # a second client: no in-process state
    batch = bo.partition(["AAPL", "DOCU"], T0 + timedelta(minutes=5))
    assert (batch.fetch, batch.skipped) == (["AAPL"], ["DOCU"])
    row = MarketSharedRepository().read_entries(["yf_backoff:DOCU"], conn=store)["yf_backoff:DOCU"]
    assert (row["kind"], row["symbol"], row["fetched_at"]) == ("yf_backoff", "DOCU", T0)
    assert row["value"] == {"misses": 3, "skip_until": (T0 + timedelta(minutes=30)).isoformat()}


def test_a_success_resets_and_a_clean_success_writes_nothing(store, monkeypatch):
    _miss_n(["DOCU"], 3)
    later = T0 + timedelta(minutes=31)
    bo.record(bo.partition(["DOCU"], later), ["DOCU"], later)
    assert bo.partition(["DOCU"], later).states["DOCU"].misses == 0
    writes = []
    monkeypatch.setattr(bo, "_write_rows", writes.append)
    bo.record(bo.partition(["AAPL"], later), ["AAPL"], later)
    assert writes == []


def test_held_ticker_in_regular_session_returns_after_the_cap(store, monkeypatch):
    _miss_n(["DOCU", "MSFT"], 3)
    monkeypatch.setattr(bo, "held_symbols", lambda now=None: frozenset({"DOCU"}))
    batch = bo.partition(["DOCU", "MSFT"], T0 + timedelta(minutes=11))
    assert (batch.fetch, batch.skipped) == (["DOCU"], ["MSFT"])


def test_held_set_is_not_read_when_nothing_is_in_backoff(store, monkeypatch):
    def boom(now=None):
        raise AssertionError("held_symbols read without need")
    monkeypatch.setattr(bo, "held_symbols", boom)
    assert bo.partition(["AAPL"], T0).fetch == ["AAPL"]


def test_enter_and_leave_log_one_info_line_each(store, caplog):
    caplog.set_level(logging.INFO, logger=bo.__name__)
    _miss_n(["DOCU"], 3, T0)                             # enters at the 3rd miss
    _miss_n(["DOCU"], 1, T0 + timedelta(minutes=31))     # the 4th, after the pause, only doubles
    assert sum("DOCU enters" in r.getMessage() for r in caplog.records) == 1
    later = T0 + timedelta(hours=2)
    bo.record(bo.partition(["DOCU"], later), ["DOCU"], later)
    assert sum("DOCU leaves" in r.getMessage() for r in caplog.records) == 1


# -- fail open ---------------------------------------------------------------------

@pytest.mark.parametrize("exc", [DatabaseUnavailable("side engine backing off"),
                                 sa.exc.TimeoutError("QueuePool limit reached")])
def test_busy_or_down_side_pool_fails_open(monkeypatch, exc):
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")

    @contextlib.contextmanager
    def busy():
        raise exc
        yield
    monkeypatch.setattr(bo, "side_connection", busy)
    batch = bo.partition(["DOCU"], T0)
    assert (batch.fetch, batch.skipped, batch.known) == (["DOCU"], [], False)
    bo.record(batch, [], T0)                             # never raises, never writes blind


def test_layer_off_never_touches_the_store(monkeypatch):
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "off")
    touched = []

    def forbidden():
        touched.append(1)                                # the helpers fail open, so count calls
        raise AssertionError("store touched with the layer off")
    monkeypatch.setattr(bo, "side_connection", forbidden)
    batch = bo.partition(["DOCU"], T0)
    bo.record(batch, [], T0)
    assert batch.fetch == ["DOCU"] and touched == []


# -- held set ----------------------------------------------------------------------

def test_held_symbols_reads_open_trades_once_a_minute_and_keeps_the_last_good(monkeypatch):
    calls = []

    class Repo:
        def open_trades(self, *, conn=None):
            calls.append(1)
            if len(calls) == 2:
                raise RuntimeError("db down")
            return [{"ticker": "docu"}, {"ticker": "AAPL"}, {"ticker": None}]
    monkeypatch.setattr(trades_mod, "trades_repo", lambda: Repo())
    assert bo.held_symbols(T0) == frozenset({"DOCU", "AAPL"})
    assert bo.held_symbols(T0 + timedelta(seconds=59)) == frozenset({"DOCU", "AAPL"})
    assert len(calls) == 1
    assert bo.held_symbols(T0 + timedelta(seconds=61)) == frozenset({"DOCU", "AAPL"})   # read failed
    assert bo.held_symbols(T0 + timedelta(seconds=62)) == frozenset({"DOCU", "AAPL"})   # retried
    assert len(calls) == 3

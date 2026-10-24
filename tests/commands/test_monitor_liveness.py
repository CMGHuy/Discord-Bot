"""v184 V184-6: the trade monitor's liveness stamp -- the `monitor` key in
the heartbeat row. Pure tests with fixed clocks; one DB test checks the
merge keeps the scan loop's own `timestamp`.

No pytest-asyncio in this repo -- coroutines are driven with asyncio.run().
"""
import asyncio
import datetime as dt
import logging

import pytest

from swingbot import config
from swingbot.commands.scanning import monitor_liveness as ml
from swingbot.commands.scanning import runstate
from swingbot.core.db.repositories.heartbeat import HeartbeatRepository
from swingbot.core.infra import swallowed as swallowed_mod
from swingbot.core.planning.plan_manager import PollDemand

UTC = dt.timezone.utc
START = dt.datetime(2026, 10, 21, 13, 0, tzinfo=UTC)
NOW = dt.datetime(2026, 10, 21, 15, 0, tzinfo=UTC)          # Wed 11:00 ET, regular session

DOC_KEYS = {"started_at", "tick_at", "outcome", "positions", "unquoted", "unquoted_count",
            "fetch_failed", "check_errors", "priced_at", "market_open"}


def _rec(**kw) -> ml.TickRecord:
    base = dict(outcome="ok", trade_tickers=["AAPL"], live_prices={"AAPL": 100.0})
    base.update(kw)
    return ml.TickRecord(**base)


def _demand(demanded, priced=()):
    return PollDemand(demanded=tuple(demanded), priced=frozenset(priced))


# --- positions / unquoted / check_errors -------------------------------------

def test_a_fresh_record_is_unknown_and_raised():
    rec = ml.TickRecord()
    assert rec.outcome == "raised"
    assert ml.positions_of(rec) is None
    assert ml.unquoted_of(rec) == []
    assert ml.check_errors_of(rec) == []


def test_positions_are_the_sorted_union_of_trade_and_demanded_plan_tickers():
    rec = _rec(trade_tickers=["MSFT", "AAPL"], plan_demand=_demand(["NVDA", "AAPL"], ["NVDA", "AAPL"]))
    assert ml.positions_of(rec) == ["AAPL", "MSFT", "NVDA"]


def test_no_plan_demand_counts_only_the_trade_tickers():
    assert ml.positions_of(_rec(trade_tickers=["AAPL"], plan_demand=None)) == ["AAPL"]


def test_a_known_empty_book_is_an_empty_list_not_unknown():
    assert ml.positions_of(_rec(trade_tickers=[], live_prices={})) == []


def test_positions_are_unknown_when_the_trade_read_did_not_complete():
    assert ml.positions_of(_rec(trade_tickers=None)) is None


def test_positions_are_unknown_when_the_plan_manager_raised():
    assert ml.positions_of(_rec(manager_raised=True)) is None


@pytest.mark.parametrize("prices", [None, {}, {"AAPL": 0}, {"AAPL": 0.0}, {"AAPL": -2.0},
                                    {"AAPL": None}])
def test_unquoted_uses_the_close_calls_own_filter(prices):
    assert ml.unquoted_of(_rec(live_prices=prices)) == ["AAPL"]


def test_unquoted_adds_the_plan_tickers_poll_did_not_price_sorted():
    rec = _rec(trade_tickers=["TSLA", "AAPL"], live_prices={"AAPL": 1.0},
               plan_demand=_demand(["NVDA", "AMD", "MSFT"], ["MSFT"]))
    assert ml.unquoted_of(rec) == ["AMD", "NVDA", "TSLA"]


def test_check_errors_append_the_plan_manager_marker_when_it_raised():
    rec = _rec(check_errors=["MSFT"], manager_raised=True)
    assert ml.check_errors_of(rec) == ["MSFT", ml.PLAN_MANAGER_ERROR]
    assert ml.PLAN_MANAGER_ERROR == "<plan manager>"


# --- build -------------------------------------------------------------------

def test_build_writes_the_full_monitor_doc():
    state = ml.MonitorLiveness(started_at=START)
    doc = state.build(_rec(), NOW)
    assert set(doc) == DOC_KEYS
    assert doc["started_at"] == "2026-10-21T13:00:00+00:00"
    assert doc["tick_at"] == "2026-10-21T15:00:00+00:00"
    assert doc["outcome"] == "ok"
    assert doc["positions"] == ["AAPL"]
    assert doc["unquoted"] == [] and doc["unquoted_count"] == 0
    assert doc["fetch_failed"] is False and doc["check_errors"] == []
    assert doc["priced_at"] == "2026-10-21T15:00:00+00:00"
    assert doc["market_open"] is True


def test_unquoted_is_capped_at_twenty_names_with_the_full_count():
    tickers = [f"T{i:02d}" for i in range(25)]
    doc = ml.MonitorLiveness(started_at=START).build(
        _rec(trade_tickers=tickers, live_prices={}), NOW)
    assert doc["unquoted"] == tickers[:ml.UNQUOTED_CAP]
    assert doc["unquoted_count"] == 25


def test_fetch_failed_is_carried_as_a_bool():
    doc = ml.MonitorLiveness(started_at=START).build(_rec(fetch_failed=True, live_prices={}), NOW)
    assert doc["fetch_failed"] is True and doc["unquoted"] == ["AAPL"]


# --- priced_at ---------------------------------------------------------------

def test_a_restarted_process_starts_with_no_priced_at():
    state = ml.MonitorLiveness(started_at=START)
    assert state.priced_at is None
    assert state.build(_rec(outcome="raised"), NOW)["priced_at"] is None


def test_a_clean_tick_advances_priced_at_and_a_known_empty_book_counts():
    state = ml.MonitorLiveness(started_at=START)
    state.build(_rec(trade_tickers=[], live_prices={}), NOW)
    assert state.priced_at == NOW


@pytest.mark.parametrize("dirty", [
    dict(outcome="raised"),
    dict(trade_tickers=None),
    dict(manager_raised=True),
    dict(live_prices={}),
    dict(check_errors=["AAPL"]),
    dict(plan_demand=PollDemand(demanded=("NVDA",), priced=frozenset())),
], ids=["raised", "trade-read-unknown", "manager-raised", "unquoted", "check-error", "plan-unpriced"])
def test_a_dirty_tick_never_advances_priced_at_and_keeps_the_last_clean_one(dirty):
    state = ml.MonitorLiveness(started_at=START)
    state.build(_rec(), NOW)
    later = NOW + dt.timedelta(minutes=5)
    doc = state.build(_rec(**dirty), later)
    assert state.priced_at == NOW
    assert doc["priced_at"] == "2026-10-21T15:00:00+00:00"
    assert doc["tick_at"] == "2026-10-21T15:05:00+00:00"


def test_a_raised_tick_with_everything_priced_still_does_not_advance():
    state = ml.MonitorLiveness(started_at=START)
    state.build(_rec(outcome="raised"), NOW)
    assert state.priced_at is None


# --- market_open --------------------------------------------------------------

@pytest.mark.parametrize("moment, expected", [
    (dt.datetime(2026, 10, 21, 15, 0, tzinfo=UTC), True),     # Wed 11:00 ET
    (dt.datetime(2026, 10, 21, 13, 29, tzinfo=UTC), False),   # Wed 09:29 ET
    (dt.datetime(2026, 10, 24, 15, 0, tzinfo=UTC), False),    # Saturday
    (dt.datetime(2026, 11, 26, 16, 0, tzinfo=UTC), False),    # Thanksgiving, 11:00 ET
    (dt.datetime(2026, 11, 27, 17, 0, tzinfo=UTC), True),     # half-day, 12:00 ET
    (dt.datetime(2026, 11, 27, 18, 30, tzinfo=UTC), False),   # half-day, 13:30 ET
])
def test_market_open_is_the_holiday_and_half_day_aware_regular_session(moment, expected):
    doc = ml.MonitorLiveness(started_at=START).build(_rec(), moment)
    assert doc["market_open"] is expected


# --- due / written (the SSE throttle) ----------------------------------------

def test_the_first_doc_is_always_due():
    state = ml.MonitorLiveness(started_at=START)
    assert state.due(state.build(_rec(), NOW), NOW) is True


def test_an_unchanged_doc_waits_for_the_interval():
    state = ml.MonitorLiveness(started_at=START)
    first = state.build(_rec(), NOW)
    state.written(first, NOW)
    t60 = NOW + dt.timedelta(seconds=60)
    assert state.due(state.build(_rec(), t60), t60) is False
    t120 = NOW + dt.timedelta(seconds=ml.WRITE_INTERVAL_S)
    assert state.due(state.build(_rec(), t120), t120) is True


@pytest.mark.parametrize("change", [
    dict(outcome="raised"),
    dict(live_prices={}),
    dict(fetch_failed=True),
    dict(check_errors=["AAPL"]),
], ids=["outcome", "unquoted", "fetch_failed", "check_errors"])
def test_a_material_change_is_written_at_once(change):
    state = ml.MonitorLiveness(started_at=START)
    state.written(state.build(_rec(), NOW), NOW)
    t60 = NOW + dt.timedelta(seconds=60)
    assert state.due(state.build(_rec(**change), t60), t60) is True


# --- stamp_tick -----------------------------------------------------------------

@pytest.fixture
def fresh_state(monkeypatch):
    state = ml.MonitorLiveness(started_at=START)
    monkeypatch.setattr(ml, "_STATE", state)
    return state


def test_stamp_tick_writes_the_doc_once_then_throttles(fresh_state, monkeypatch):
    writes = []
    monkeypatch.setattr(ml, "_write", writes.append)
    assert asyncio.run(ml.stamp_tick(_rec(), now=NOW)) is True
    assert asyncio.run(ml.stamp_tick(_rec(), now=NOW + dt.timedelta(seconds=60))) is False
    assert len(writes) == 1 and writes[0]["outcome"] == "ok"


def test_write_merges_only_the_monitor_key(monkeypatch):
    seen = []
    monkeypatch.setattr(runstate, "_update_heartbeat", seen.append)
    ml._write({"outcome": "ok"})
    assert seen == [{"monitor": {"outcome": "ok"}}]


def test_a_raising_write_is_swallowed_counted_and_retried(fresh_state, monkeypatch, caplog):
    def boom(doc):
        raise RuntimeError("db down")
    monkeypatch.setattr(ml, "_write", boom)
    before = swallowed_mod.snapshot().get("ops.monitor_stamp", {}).get("count", 0)
    with caplog.at_level(logging.WARNING, logger=ml.log.name):
        assert asyncio.run(ml.stamp_tick(_rec(), now=NOW)) is False
    assert swallowed_mod.snapshot()["ops.monitor_stamp"]["count"] == before + 1
    writes = []
    monkeypatch.setattr(ml, "_write", writes.append)
    assert asyncio.run(ml.stamp_tick(_rec(), now=NOW + dt.timedelta(seconds=60))) is True
    assert len(writes) == 1


def test_a_raising_build_is_swallowed_too(fresh_state, monkeypatch):
    monkeypatch.setattr(ml.session, "is_nyse_regular_session",
                        lambda now=None: (_ for _ in ()).throw(ValueError("tz")))
    assert asyncio.run(ml.stamp_tick(_rec(), now=NOW)) is False


# --- the real merge -------------------------------------------------------------

@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def db_url(db_engine, monkeypatch):
    monkeypatch.setattr(config, "DATABASE_URL", db_engine.url.render_as_string(hide_password=False))
    from swingbot.core.db.engine import reset_engine
    reset_engine()


def test_the_monitor_merge_keeps_the_scan_loops_timestamp(data_dir, db_committed, db_url):
    runstate._write_heartbeat()
    before = HeartbeatRepository().last(conn=db_committed)
    doc = ml.MonitorLiveness(started_at=START).build(_rec(), NOW)
    ml._write(doc)
    after = HeartbeatRepository().last(conn=db_committed)
    assert after["timestamp"] == before["timestamp"]
    assert after["monitor"] == doc
    assert "session_active" in after and "scan_paused" in after

def test_a_clean_tick_never_moves_priced_at_backwards():
    state = ml.MonitorLiveness(started_at=START)
    state.build(_rec(), NOW)
    earlier = NOW - dt.timedelta(seconds=1)
    assert state.build(_rec(), earlier)["priced_at"] == "2026-10-21T15:00:00+00:00"
    assert state.priced_at == NOW


def test_stamp_tick_runs_the_write_in_a_worker_thread(fresh_state, monkeypatch):
    import threading

    event_thread = threading.get_ident()
    writer_threads = []
    monkeypatch.setattr(ml, "_write", lambda doc: writer_threads.append(threading.get_ident()))
    assert asyncio.run(ml.stamp_tick(_rec(), now=NOW)) is True
    assert len(writer_threads) == 1
    assert writer_threads[0] != event_thread


def test_repository_merge_failure_retries_before_the_write_interval(
    fresh_state, monkeypatch, data_dir, db_committed, db_url,
):
    merge = HeartbeatRepository.merge
    attempts = []

    def fail_once(repo, fields, **kwargs):
        attempts.append(fields)
        if len(attempts) == 1:
            raise RuntimeError("repository unavailable")
        return merge(repo, fields, **kwargs)

    monkeypatch.setattr(HeartbeatRepository, "merge", fail_once)
    before = swallowed_mod.snapshot().get("ops.monitor_stamp", {}).get("count", 0)
    assert asyncio.run(ml.stamp_tick(_rec(), now=NOW)) is False
    assert swallowed_mod.snapshot()["ops.monitor_stamp"]["count"] == before + 1
    later = NOW + dt.timedelta(seconds=60)
    assert asyncio.run(ml.stamp_tick(_rec(), now=later)) is True
    assert len(attempts) == 2
    persisted = HeartbeatRepository().last(conn=db_committed)
    assert persisted["monitor"]["tick_at"] == "2026-10-21T15:01:00+00:00"
    assert asyncio.run(ml.stamp_tick(_rec(), now=later)) is False
    assert len(attempts) == 2

"""v209: MarketShockRepository -- reading + state (+ notice) in one transaction."""
from datetime import date, datetime, timedelta, timezone

import pytest
import sqlalchemy as sa

from swingbot.core.db import schema
from swingbot.core.db.repositories import market_shock as ms
from swingbot.core.infra.lifecycle_events import make_event
from swingbot.core.market import shock

T0 = datetime(2026, 11, 5, 14, 45, tzinfo=timezone.utc)
D0 = date(2026, 11, 5)


def _reading(**over) -> dict:
    base = dict(as_of=T0, session_date=D0, minutes_since_open=75.0, breadth_frac=0.45,
                sectors_down=3, sectors_total=5, breadth_speed=None, spy_atr_move=-1.2,
                qqq_atr_move=None, spy_last=495.0, spy_prev_close=500.0,
                spy_session_low=495.0, spy_new_low=False, spy_retrace=0.0, vix_level=None,
                vix_chg_pct=None, vix_session_high=None, vix_off_high_pct=None, n_names=40,
                insufficient=False)
    return shock.ShockReading(**{**base, **over}).as_row()


def _state(label="NORMAL", **over) -> dict:
    return shock.ShockState(label=label, session_date=D0, **over).as_row()


def _notice(transition="t-1", at=T0):
    payload = {"ticker": "AAPL", "direction": "bullish", "prior_status": "PENDING",
               "new_status": "CANCELLED", "reason": "probe", "occurred_at": at.isoformat(),
               "plan_id": "P-1"}
    return make_event(transition_id=transition, kind="plan_transition",
                      target_channel_id="123", occurred_at=at.isoformat(), payload=payload)


@pytest.fixture
def repo():
    return ms.MarketShockRepository()


def test_labels_are_restated_from_the_detector():
    assert ms.LABELS == shock.LABELS


def test_the_singleton_is_reused():
    assert ms.market_shock_repo() is ms.market_shock_repo()


def test_empty_tables_read_as_none(repo, db_conn):
    assert repo.current_state(conn=db_conn) is None
    assert repo.latest_reading(conn=db_conn) is None


def test_a_reading_round_trips_with_its_none_fields(repo, db_conn):
    row = _reading()
    reading_id = repo.record(row, _state(), state_after="NORMAL", conn=db_conn)
    got = repo.latest_reading(conn=db_conn)
    assert got["id"] == reading_id and got["state_after"] == "NORMAL"
    assert shock.ShockReading.from_row(got) == shock.ShockReading.from_row(row)
    assert got["breadth_speed"] is None and got["vix_level"] is None


def test_promoted_columns_copy_the_headline_numbers(repo, db_conn):
    reading_id = repo.record(_reading(), _state(), state_after="NORMAL", conn=db_conn)
    row = db_conn.execute(sa.select(schema.market_shock_readings).where(
        schema.market_shock_readings.c.id == reading_id)).one()
    assert row.as_of == T0 and row.session_date == D0 and row.state_after == "NORMAL"
    assert row.breadth_frac == 0.45 and row.spy_atr_move == -1.2 and row.vix_level is None
    assert (row.sectors_down, row.sectors_total, row.n_names, row.insufficient) == (3, 5, 40, False)


def test_the_state_row_is_single_and_points_at_the_last_reading(repo, db_conn):
    repo.record(_reading(), _state(), state_after="NORMAL", conn=db_conn)
    later = _reading(as_of=T0 + timedelta(minutes=15))
    second = repo.record(later, _state("SHOCK", since=T0), state_after="SHOCK", conn=db_conn)
    assert db_conn.execute(sa.select(sa.func.count()).select_from(
        schema.market_shock_state)).scalar_one() == 1
    state = repo.current_state(conn=db_conn)
    assert state["label"] == "SHOCK" and state["last_reading_id"] == second
    assert state["since"] == T0 and state["session_date"] == D0
    assert shock.ShockState.from_row(state["doc"]["state"]).label == "SHOCK"
    assert repo.latest_reading(conn=db_conn)["id"] == second


def test_a_notice_is_enqueued_in_the_same_transaction_and_stamps_last_notice_at(repo, db_conn):
    repo.record(_reading(), _state(), state_after="NORMAL", notice_event=_notice(),
                conn=db_conn)
    assert repo.current_state(conn=db_conn)["last_notice_at"] == T0
    assert db_conn.execute(sa.select(sa.func.count()).select_from(
        schema.manual_close_notify)).scalar_one() == 1
    repo.record(_reading(), _state(), state_after="NORMAL", conn=db_conn)
    assert repo.current_state(conn=db_conn)["last_notice_at"] == T0     # kept, not cleared


def test_a_failing_enqueue_writes_nothing(repo, store_db):
    bad = {**_notice(), "event_id": "not-the-identity"}
    with pytest.raises(ValueError):
        repo.record(_reading(), _state(), state_after="NORMAL", notice_event=bad)
    for table in (schema.market_shock_readings, schema.market_shock_state,
                  schema.manual_close_notify):
        assert store_db.execute(sa.select(sa.func.count()).select_from(table)).scalar_one() == 0


@pytest.mark.parametrize("label,after", [("CALM", "CALM"), ("NORMAL", "SHOCK")])
def test_an_unknown_or_mismatched_label_is_refused(repo, db_conn, label, after):
    state = {**_state(), "label": label}
    with pytest.raises(ValueError):
        repo.record(_reading(), state, state_after=after, conn=db_conn)
    assert repo.latest_reading(conn=db_conn) is None


def test_latest_reading_orders_by_as_of_not_insert_order(repo, db_conn):
    newer = repo.record(_reading(as_of=T0 + timedelta(minutes=30)), _state(),
                        state_after="NORMAL", conn=db_conn)
    repo.record(_reading(as_of=T0), _state(), state_after="NORMAL", conn=db_conn)
    assert repo.latest_reading(conn=db_conn)["id"] == newer


def test_prune_deletes_older_rows_and_unhooks_the_state(repo, db_conn):
    repo.record(_reading(as_of=T0 - timedelta(days=200)), _state(), state_after="NORMAL",
                conn=db_conn)
    assert repo.prune_before(T0 - timedelta(days=180), conn=db_conn) == 1
    assert repo.latest_reading(conn=db_conn) is None
    assert repo.current_state(conn=db_conn)["last_reading_id"] is None


def test_prune_keeps_rows_at_or_after_the_cutoff(repo, db_conn):
    repo.record(_reading(as_of=T0), _state(), state_after="NORMAL", conn=db_conn)
    assert repo.prune_before(T0, conn=db_conn) == 0
    assert repo.latest_reading(conn=db_conn) is not None


def test_prune_refuses_a_naive_cutoff(repo, db_conn):
    with pytest.raises(ValueError):
        repo.prune_before(datetime(2026, 1, 1), conn=db_conn)

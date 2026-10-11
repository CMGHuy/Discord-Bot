"""v152: plan_followers and notify_prefs repositories (real Postgres, rolled back)."""
import pytest

from swingbot.core.db.repositories.followers import (
    FOLLOW_KINDS, FollowersRepository, followers_repo)
from swingbot.core.db.repositories.notify_prefs import NotifyPrefsRepository, notify_prefs_repo
from swingbot.core.db.repositories.plans import PlanRepository

ALICE, BOB = 111111111111111111, 222222222222222222


def _plan(db_conn, plan_id="P1"):
    PlanRepository().insert({"plan_id": plan_id, "ticker": "AAPL", "strategy": "RSI",
                             "horizon_key": "2w", "status": "PENDING",
                             "created_at": "2026-10-10T14:00:00+00:00"}, conn=db_conn)


def test_the_two_kinds_are_watch_and_taken():
    assert FOLLOW_KINDS == ("watch", "taken")


def test_singletons_are_stable():
    assert followers_repo() is followers_repo()
    assert notify_prefs_repo() is notify_prefs_repo()


def test_add_is_idempotent_and_reports_whether_it_inserted(db_conn):
    _plan(db_conn)
    repo = FollowersRepository()
    assert repo.add("P1", ALICE, "taken", status_at_press="PENDING", conn=db_conn) is True
    assert repo.add("P1", ALICE, "taken", status_at_press="ACTIVE", conn=db_conn) is False
    (row,) = repo.list_all(conn=db_conn)
    assert row["status_at_press"] == "PENDING"      # the first press is kept
    assert row["at"].endswith("+00:00")


def test_has_and_remove_are_per_user_and_per_kind(db_conn):
    _plan(db_conn)
    repo = FollowersRepository()
    repo.add("P1", ALICE, "watch", status_at_press="PENDING", conn=db_conn)
    assert repo.has("P1", ALICE, "watch", conn=db_conn) is True
    assert repo.has("P1", ALICE, "taken", conn=db_conn) is False
    assert repo.has("P1", BOB, "watch", conn=db_conn) is False
    assert repo.remove("P1", BOB, "watch", conn=db_conn) is False
    assert repo.remove("P1", ALICE, "watch", conn=db_conn) is True
    assert repo.has("P1", ALICE, "watch", conn=db_conn) is False


def test_user_ids_filters_by_kind_sorted_and_unique(db_conn):
    _plan(db_conn)
    _plan(db_conn, "P2")
    repo = FollowersRepository()
    repo.add("P1", BOB, "taken", status_at_press="ACTIVE", conn=db_conn)
    repo.add("P1", ALICE, "taken", status_at_press="ACTIVE", conn=db_conn)
    repo.add("P1", ALICE, "watch", status_at_press="ACTIVE", conn=db_conn)
    repo.add("P2", BOB, "watch", status_at_press="ACTIVE", conn=db_conn)
    assert repo.user_ids("P1", ("taken",), conn=db_conn) == [ALICE, BOB]
    assert repo.user_ids("P1", ("watch",), conn=db_conn) == [ALICE]
    assert repo.user_ids("P1", FOLLOW_KINDS, conn=db_conn) == [ALICE, BOB]
    assert repo.user_ids("P1", (), conn=db_conn) == []
    assert repo.user_ids("P3", FOLLOW_KINDS, conn=db_conn) == []


def test_followers_maps_each_user_to_their_kinds(db_conn):
    _plan(db_conn)
    repo = FollowersRepository()
    repo.add("P1", ALICE, "taken", status_at_press="ACTIVE", conn=db_conn)
    repo.add("P1", ALICE, "watch", status_at_press="ACTIVE", conn=db_conn)
    repo.add("P1", BOB, "watch", status_at_press="ACTIVE", conn=db_conn)
    assert repo.followers("P1", conn=db_conn) == {
        ALICE: frozenset({"taken", "watch"}), BOB: frozenset({"watch"})}
    assert repo.followers("NONE", conn=db_conn) == {}


@pytest.mark.parametrize("call", [
    lambda r: r.add("P1", ALICE, "fill", status_at_press="ACTIVE"),
    lambda r: r.remove("P1", ALICE, "fill"),
    lambda r: r.has("P1", ALICE, "fill"),
    lambda r: r.user_ids("P1", ("watch", "fill")),
])
def test_an_unknown_kind_is_rejected_before_any_sql(call):
    with pytest.raises(ValueError, match="fill"):
        call(FollowersRepository())


def test_prefs_are_empty_until_set(db_conn):
    assert NotifyPrefsRepository().prefs(ALICE, conn=db_conn) == {}


def test_set_pref_merges_keys_and_overwrites_one(db_conn):
    repo = NotifyPrefsRepository()
    repo.set_pref(ALICE, "near_stop", True, conn=db_conn)
    repo.set_pref(ALICE, "watch_mode", "silent", conn=db_conn)
    repo.set_pref(ALICE, "near_stop", False, conn=db_conn)
    assert repo.prefs(ALICE, conn=db_conn) == {"near_stop": False, "watch_mode": "silent"}
    assert repo.count(conn=db_conn) == 1


def test_prefs_many_answers_every_requested_user(db_conn):
    repo = NotifyPrefsRepository()
    repo.set_pref(BOB, "tp1", False, conn=db_conn)
    assert repo.prefs_many([ALICE, BOB, BOB], conn=db_conn) == {ALICE: {}, BOB: {"tp1": False}}
    assert repo.prefs_many([], conn=db_conn) == {}


@pytest.mark.parametrize("key", ["", "id", "doc", "updated_at", "user_id"])
def test_a_reserved_or_empty_key_is_rejected(key):
    with pytest.raises(ValueError):
        NotifyPrefsRepository().set_pref(ALICE, key, True)


@pytest.mark.parametrize("value", [1, None, 0.5, ["x"]])
def test_a_value_must_be_bool_or_str(value):
    with pytest.raises(TypeError):
        NotifyPrefsRepository().set_pref(ALICE, "tp1", value)

"""v189 A6 rollback: an account-reset archive restores the book it came from.

Uses V189-15's seeded book (base 10,000; C1 +2,000 and C2 -3,000 closed;
balance 9,000 before the reset).
"""
import json
from datetime import timedelta

import pytest

from scripts.ops import restore_account_reset as rar
from swingbot.core.db.repositories.account import account_repo
from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.repositories.followers import followers_repo
from swingbot.core.db.repositories.plans import plans_repo
from swingbot.core.db.repositories.starred import starred_repo
from swingbot.core.db.repositories.trades import trades_repo
from swingbot.core.db.schema import plan_notifications
from swingbot.core.planning import account as account_module
from swingbot.core.tracking import account_reset as ar
from tests.store_seed import seed_store
from tests.tracking.test_account_reset import (  # noqa: F401  (book is a fixture)
    ARCHIVE, NOW, _state, _trade_record, book)

LATER = NOW + timedelta(hours=1)
LATER_ARCHIVE = "account-reset-20261023T160000Z.json"


def _full_state():
    """Every restored table plus the computed balance, order-independent."""
    return (
        sorted((t["trade_id"], t["status"], t.get("realized_pnl_amount"))
               for t in trades_repo().list_all()),
        sorted((p["plan_id"], p["status"], len(p.get("legs_realized") or []))
               for p in plans_repo().list_all()),
        [(h["ts"], h["balance"]) for h in account_module.get_balance_history()],
        sorted(starred_repo().ids()),
        followers_repo().followers("P-C"),
        sorted((n["plan_id"], n["event"])
               for n in Repository(plan_notifications, key="plan_id").list_all()),
        account_module.load_account_config()["balance"],
    )


def test_a_dry_run_reports_and_writes_nothing(book):
    ar.reset_closed_history(now=NOW)
    after_reset = _state()
    summary = ar.restore_archive(book / ARCHIVE)
    assert summary == {
        "archive": ARCHIVE, "reset_at": "2026-10-23T15:00:00+00:00", "trades": 2, "plans": 2,
        "account_balance_history": 3, "starred_plans": 1, "plan_followers": 1,
        "plan_notifications": 1, "later_points": 0, "balance_shift": None, "applied": False}
    assert _state() == after_reset


def test_apply_round_trips_the_archive(book):
    before = _full_state()
    ar.reset_closed_history(now=NOW)
    summary = ar.restore_archive(book / ARCHIVE, apply=True)
    assert (summary["applied"], summary["balance_shift"]) == (True, -1_000.0)
    assert _full_state() == before
    assert account_module.load_account_config()["balance"] == 9_000.0


def test_points_written_after_the_reset_carry_the_restored_pnl(book):
    ar.reset_closed_history(now=NOW)
    # A trade closes after the reset: +500 on top of the reseeded 10,000.
    seed_store("trades", [_trade_record("C3", "win", exit_price=105.0, pnl=500.0)])
    account_repo().append_history({"ts": "2026-10-24T20:00:00+00:00", "balance": 10_500.0,
                                   "pnl_amount": 500.0, "trade_id": "C3"})
    summary = ar.restore_archive(book / ARCHIVE, apply=True)
    assert (summary["later_points"], summary["balance_shift"]) == (1, -1_000.0)
    assert [h["balance"] for h in account_module.get_balance_history()] == [
        10_000.0, 12_000.0, 9_000.0, 9_500.0]
    assert account_module.load_account_config()["balance"] == 9_500.0     # 10,000 + 2,000 - 3,000 + 500


def test_refused_after_a_later_reset_until_the_newest_is_restored_first(book):
    before = _full_state()
    ar.reset_closed_history(now=NOW)
    ar.reset_closed_history(now=LATER)
    after_two_resets = _state()
    with pytest.raises(ValueError, match="later reset"):
        ar.restore_archive(book / ARCHIVE, apply=True)
    assert _state() == after_two_resets
    ar.restore_archive(book / LATER_ARCHIVE, apply=True)
    ar.restore_archive(book / ARCHIVE, apply=True)
    assert _full_state() == before


def test_a_second_apply_of_the_same_archive_is_refused(book):
    ar.reset_closed_history(now=NOW)
    ar.restore_archive(book / ARCHIVE, apply=True)
    restored = _state()
    with pytest.raises(ValueError, match="later reset"):
        ar.restore_archive(book / ARCHIVE, apply=True)
    assert _state() == restored


def test_a_file_that_is_not_an_archive_is_refused(tmp_path):
    path = tmp_path / "account-reset-x.json"
    path.write_text(json.dumps({"version": 2}), encoding="utf-8")
    with pytest.raises(ValueError, match="not a version-1 account-reset archive"):
        ar.restore_archive(path)


def test_the_script_dry_runs_by_default_and_applies_with_the_flag(book, capsys):
    ar.reset_closed_history(now=NOW)
    assert rar.main([str(book / ARCHIVE)]) == 0
    assert json.loads(capsys.readouterr().out)["applied"] is False
    assert sorted(t["trade_id"] for t in trades_repo().list_all()) == ["O1", "O2"]
    assert rar.main([str(book / ARCHIVE), "--apply"]) == 0
    assert json.loads(capsys.readouterr().out)["applied"] is True
    assert sorted(t["trade_id"] for t in trades_repo().list_all()) == ["C1", "C2", "O1", "O2"]


@pytest.mark.parametrize("make_path", [
    lambda book: book / ARCHIVE,                    # refused: a later reset ran
    lambda book: book / "no-such-archive.json",     # missing file
], ids=["later-reset", "missing-file"])
def test_the_script_exits_1_with_the_reason(book, capsys, make_path):
    ar.reset_closed_history(now=NOW)
    ar.reset_closed_history(now=LATER)
    assert rar.main([str(make_path(book)), "--apply"]) == 1
    assert capsys.readouterr().err.startswith("refused: ")

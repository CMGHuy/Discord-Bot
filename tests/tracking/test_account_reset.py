"""v189 A6: clear history is an archived full reset.

Every test runs against this worker's test database (the autouse store
fixture) with config.DATA_DIR pointed at tmp_path, so archives land in
tmp_path/archives. The seeded book: base 10,000; C1 closed +2,000 (plan P-C,
CLOSED, two realized legs), C2 closed -3,000 (no plan); O1 open on ACTIVE
P-O, O2 open on PENDING P-P; P-X CANCELLED; balance history 10,000 ->
12,000 -> 9,000 (a 25% drawdown, so the throttle is paused).
"""
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from swingbot import config
from swingbot.core.db.repositories.followers import followers_repo
from swingbot.core.db.repositories.killswitch import killswitch_repo
from swingbot.core.db.repositories.notifications import notifications_repo
from swingbot.core.db.repositories.plans import PlanRepository, plans_repo
from swingbot.core.db.repositories.starred import starred_repo
from swingbot.core.db.repositories.trades import trades_repo
from swingbot.core.edge import throttle
from swingbot.core.planning import account as account_module
from swingbot.core.tracking import account_reset as ar
from tests.store_seed import seed_store

REPO = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 10, 23, 15, 0, tzinfo=timezone.utc)
ARCHIVE = "account-reset-20261023T150000Z.json"
BASE = 10_000.0
HISTORY = [
    {"ts": "2026-10-01T10:00:00+00:00", "balance": 10_000.0, "pnl_amount": None,
     "reason": "account created"},
    {"ts": "2026-10-10T20:00:00+00:00", "balance": 12_000.0, "pnl_amount": 2_000.0,
     "trade_id": "C1"},
    {"ts": "2026-10-20T20:00:00+00:00", "balance": 9_000.0, "pnl_amount": -3_000.0,
     "trade_id": "C2"},
]
TWO_LEGS = [{"fraction": 0.5, "exit_price": 110.0, "r": 2.0, "reason": "tp1"},
            {"fraction": 0.5, "exit_price": 130.0, "r": 6.0, "reason": "tp2"}]


def _plan_record(plan_id, status, legs=()):
    return {
        "plan_id": plan_id, "ticker": "GOLD", "created_at": "2026-10-01T09:00:00+00:00",
        "source": "strategy", "strategy": "RSI Divergence", "horizon_key": "1m",
        "direction": "bullish", "entry_type": "stop_entry", "trigger_price": 100.0,
        "entry_price": 100.0, "expiry_bars": 5, "stop_loss": 95.0, "tp1": 110.0,
        "tp1_fraction": 0.5, "tp2": 120.0, "breakeven_trigger_fraction": 0.5,
        "trail_atr_mult": 1.5, "quality_score": 70, "quality_breakdown": [],
        "badge": "VALIDATED", "badge_stats": {}, "status": status,
        "status_history": [], "legs_realized": list(legs),
    }


def _trade_record(trade_id, status, *, plan_id=None, exit_price=None, pnl=None):
    closed = status != "open"
    return {
        "id": trade_id, "plan_id": plan_id, "ticker": "GOLD", "strategy": "RSI Divergence",
        "horizon_key": "1m", "direction": "bullish", "entry": 100.0, "stop_loss": 95.0,
        "take_profit": 110.0, "shares": 100, "legs": [], "status": status,
        "opened_at": "2026-10-01T10:00:00+00:00",
        "closed_at": "2026-10-10T20:00:00+00:00" if closed else None,
        "exit_price": exit_price, "realized_pnl_amount": pnl,
    }


@pytest.fixture
def book(tmp_path, monkeypatch):
    """Seed the book above; return the directory archives are written to."""
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "KILLSWITCH_DEFAULT_ON", False)   # never read from .env
    seed_store("account", {"base_balance": BASE, "balance_history": HISTORY})
    seed_store("plans", [_plan_record("P-C", "CLOSED", TWO_LEGS), _plan_record("P-X", "CANCELLED"),
                         _plan_record("P-O", "ACTIVE"), _plan_record("P-P", "PENDING")])
    seed_store("trades", [
        _trade_record("C1", "win", plan_id="P-C", exit_price=120.0, pnl=2_000.0),
        _trade_record("C2", "loss", exit_price=70.0, pnl=-3_000.0),
        _trade_record("O1", "open", plan_id="P-O"),
        _trade_record("O2", "open", plan_id="P-P"),
    ])
    starred_repo().star("P-C")
    starred_repo().star("P-O")
    followers_repo().add("P-C", 42, "taken", status_at_press="ACTIVE")
    followers_repo().add("P-O", 42, "watch", status_at_press="ACTIVE")
    notifications_repo().claim("P-X", "cancelled_expired", {"note": "sent"})
    return tmp_path / "archives"


def _trade_ids():
    return sorted(t["trade_id"] for t in trades_repo().list_all())


def _plan_ids():
    return sorted(p["plan_id"] for p in plans_repo().list_all())


def _state():
    """Everything a reset may touch, for the "left untouched" assertions."""
    return (_trade_ids(), _plan_ids(),
            [h["balance"] for h in account_module.get_balance_history()],
            sorted(starred_repo().ids()))


# --- the archive ----------------------------------------------------------------

def test_the_archive_holds_every_row_the_reset_deletes(book):
    result = ar.reset_closed_history(now=NOW)
    path = book / ARCHIVE
    assert result.archive_path == str(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["version"] == 1
    assert payload["reset_at"] == "2026-10-23T15:00:00+00:00"
    assert payload["base_balance"] == BASE
    assert sorted(t["trade_id"] for t in payload["trades"]) == ["C1", "C2"]
    assert sorted(p["plan_id"] for p in payload["plans"]) == ["P-C", "P-X"]
    closed_plan = next(p for p in payload["plans"] if p["plan_id"] == "P-C")
    assert [leg["reason"] for leg in closed_plan["legs_realized"]] == ["tp1", "tp2"]
    assert [h["balance"] for h in payload["account_balance_history"]] == [10_000.0, 12_000.0, 9_000.0]
    assert [r["plan_id"] for r in payload["starred_plans"]] == ["P-C"]
    assert [(r["plan_id"], r["user_id"], r["kind"]) for r in payload["plan_followers"]] == [
        ("P-C", 42, "taken")]
    assert [(r["plan_id"], r["event"]) for r in payload["plan_notifications"]] == [
        ("P-X", "cancelled_expired")]


def test_archives_are_git_ignored():
    r = subprocess.run(["git", "check-ignore", "-q", "--no-index", f"data/archives/{ARCHIVE}"],
                       cwd=REPO)
    assert r.returncode == 0, "data/archives/ holds account data and must never be staged"


# --- what is deleted and what stays ----------------------------------------------

def test_closed_trades_and_finished_plans_go_open_and_live_stay(book):
    result = ar.reset_closed_history(now=NOW)
    assert (result.removed_trades, result.removed_plans) == (2, 2)
    assert _trade_ids() == ["O1", "O2"]
    assert _plan_ids() == ["P-O", "P-P"]
    assert sorted(starred_repo().ids()) == ["P-O"]               # P-C's star cascaded
    assert followers_repo().followers("P-O") == {42: frozenset({"watch"})}
    assert followers_repo().followers("P-C") == {}


def test_history_restarts_with_one_point_at_the_base_balance(book):
    ar.reset_closed_history(now=NOW)
    [point] = account_module.get_balance_history()
    assert (point["balance"], point["pnl_amount"]) == (BASE, 0.0)
    assert (point["reason"], point["archive"]) == (ar.RESET_REASON, ARCHIVE)
    assert datetime.fromisoformat(point["ts"]) == NOW              # session time zone agnostic
    assert account_module.load_account_config()["balance"] == BASE
    assert account_module.get_balance_history_points() == [("2026-10-23", BASE)]


def test_a_reset_of_an_empty_history_still_reseeds(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "KILLSWITCH_DEFAULT_ON", False)
    seed_store("account", {"base_balance": 5_000.0})
    result = ar.reset_closed_history(now=NOW)
    assert (result.removed_trades, result.removed_plans, result.base_balance) == (0, 0, 5_000.0)
    assert [h["balance"] for h in account_module.get_balance_history()] == [5_000.0]


# --- throttle and kill switch ------------------------------------------------------

def test_the_drawdown_peak_restarts_so_the_throttle_lifts(book):
    before = [b for _, b in account_module.get_balance_history_points()]
    assert throttle.drawdown_pct(before) == pytest.approx(25.0)
    assert throttle.current_throttle(before) == (0.0, True)
    result = ar.reset_closed_history(now=NOW)
    assert (result.throttle_multiplier, result.throttle_paused, result.kill_on) == (1.0, False, False)
    after = [b for _, b in account_module.get_balance_history_points()]
    assert throttle.drawdown_pct(after) == 0.0


def test_refused_while_the_kill_switch_is_tripped(book):
    killswitch_repo().engage("drawdown >20%")
    before = _state()
    with pytest.raises(ar.ResetRefused):
        ar.reset_closed_history(now=NOW)
    assert _state() == before
    assert not book.exists()
    assert throttle.kill_state()["on"] is True


def test_force_resets_but_never_releases_the_kill_switch(book):
    killswitch_repo().engage("drawdown >20%")
    result = ar.reset_closed_history(force=True, now=NOW)
    assert result.kill_on is True
    state = throttle.kill_state()
    assert (state["on"], state["reason"]) == (True, "drawdown >20%")
    assert _trade_ids() == ["O1", "O2"]


# --- failure paths ---------------------------------------------------------------------

def test_a_failed_archive_write_leaves_everything_untouched(book, tmp_path, monkeypatch):
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setattr(config, "DATA_DIR", str(blocker))     # archives/ cannot be created
    before = _state()
    with pytest.raises(ar.ArchiveFailed, match="Nothing was deleted"):
        ar.reset_closed_history(now=NOW)
    assert _state() == before


def test_a_failure_after_the_archive_rolls_back_and_removes_the_file(book, monkeypatch):
    def boom(self, *, conn):
        raise RuntimeError("delete failed")
    monkeypatch.setattr(PlanRepository, "delete_terminal", boom)
    before = _state()
    with pytest.raises(RuntimeError, match="delete failed"):
        ar.reset_closed_history(now=NOW)
    assert _state() == before
    assert list(book.glob("*.json")) == []


def test_a_second_reset_in_the_same_second_never_overwrites_the_first_archive(book):
    ar.reset_closed_history(now=NOW)
    first = (book / ARCHIVE).read_bytes()
    with pytest.raises(ar.ArchiveFailed):
        ar.reset_closed_history(now=NOW)
    assert (book / ARCHIVE).read_bytes() == first
    assert len(account_module.get_balance_history()) == 1


def test_the_snapshot_refresh_runs_after_commit(book, monkeypatch):
    seen = []
    # Reads on its own connection, so it sees only committed rows.
    monkeypatch.setattr(ar, "_refresh_snapshot_safely", lambda: seen.append(_trade_ids()))
    ar.reset_closed_history(now=NOW)
    assert seen == [["O1", "O2"]]


# --- the words ---------------------------------------------------------------------------

def test_describe_reset_names_the_archive_throttle_kill_switch_and_sizing():
    result = ar.ResetResult(
        removed_trades=2, removed_plans=3, archive_path=f"/app/data/archives/{ARCHIVE}",
        throttle_multiplier=1.0, throttle_paused=False, kill_on=True,
        base_balance=10_000.0, reset_at="2026-10-23T15:00:00+00:00")
    assert ar.describe_reset(result) == (
        "Account reset: removed 2 closed trade(s) and 3 finished plan(s). Realized P&L and "
        "the drawdown history restart from the base balance 10,000.00.\n"
        f"Archive: {ARCHIVE}\n"
        "Throttle: 1.00x, not paused. The drawdown peak restarts at the base balance, "
        "so any throttle is lifted.\n"
        "Kill switch: on -- the reset never releases it; release it by hand.\n"
        "New trades are sized off the base balance. Open trades and live plans were not touched.")


def test_describe_reset_with_the_kill_switch_off():
    result = ar.ResetResult(
        removed_trades=0, removed_plans=0, archive_path=ARCHIVE, throttle_multiplier=1.0,
        throttle_paused=False, kill_on=False, base_balance=5_000.0, reset_at="x")
    assert "\nKill switch: off.\n" in ar.describe_reset(result)


def test_the_refusal_names_both_overrides():
    assert ar.REFUSED_TEXT == (
        "Reset refused: the kill switch is tripped. Release it first, or force the reset "
        "(`force=true` on the endpoint, `!trades clear history force` or "
        "`/trades-clear-history force:True`); the kill switch stays on either way.")

"""v152 D2: per-user Watch and the Following button.

Following records that a user says they followed a paper plan -- intent,
never a fill -- and is refused once the outcome is known. Watch is a per-user
row; the global star follows the first/last watcher. No pytest-asyncio:
coroutines run through asyncio.run.
"""
import asyncio
import datetime as dt
import inspect
from unittest.mock import AsyncMock, MagicMock

import pytest
import sqlalchemy as sa

from swingbot import config
from swingbot.commands import views
from swingbot.commands.views import (
    FOLLOWABLE_STATUSES,
    PLAN_BUTTONS,
    FollowingButton,
    PlanActionView,
    following_reply,
    starred_ids,
)
from swingbot.core.db import schema
from swingbot.core.db import engine as engine_module
from swingbot.core.planning.plan_store import PlanStore
from swingbot.core.planning.plan_types import PlanStatus
from swingbot.core.tracking.performance import TradeLog
from tests.planning.test_plan_engine_model import _plan
from tests.store_seed import seed_store

PID = "0f8fad5b-d9cb-469f-a165-70867728950e"
AUTHOR = 123456789012345678
OTHER = 876543210987654321
WED = dt.datetime(2026, 10, 7, 16, 0, tzinfo=dt.timezone.utc)   # 12:00 ET, Wednesday


def _interaction(user_id: int) -> MagicMock:
    interaction = MagicMock()
    interaction.user.id = user_id
    interaction.response = AsyncMock()
    interaction.followup = AsyncMock()
    return interaction


def _button(view, action):
    return next(item for item in view.children if item.custom_id.split(":")[1] == action)


def _reply_text(interaction) -> str:
    interaction.followup.send.assert_awaited_once()
    args, kwargs = interaction.followup.send.call_args
    assert kwargs.get("ephemeral") is True
    return args[0]


@pytest.fixture
def plan_env(tmp_path, monkeypatch):
    """A stored plan with an open trade; the price read is stubbed."""
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    seed_store("account", {
        "balance": 10000.0, "risk_pct": 1.0, "max_position_pct": 20.0,
        "sizing_mode": "risk_pct", "balance_history": [],
    })
    monkeypatch.setattr(views, "_last_close", lambda ticker: (102.5, dt.date(2026, 10, 9)))

    def make(status=PlanStatus.PENDING, **kw):
        PlanStore().add(_plan(plan_id=PID, status=status, **kw))
        trade_id = TradeLog().log_trade(
            ticker="AAPL", strategy="Fibonacci", horizon_key="4w",
            direction="bullish", confidence_level=4, confidence_label="High",
            entry=100.0, stop_loss=95.0, take_profit=110.0, plan_id=PID)
        return trade_id
    return make


def _press(action: str, user_id: int) -> MagicMock:
    interaction = _interaction(user_id)
    asyncio.run(_button(PlanActionView(PID, author_id=None), action).callback(interaction))
    return interaction


def _follower_rows():
    table = schema.plan_followers
    with engine_module.get_engine().connect() as conn:   # conftest patches the module attribute
        return conn.execute(sa.select(table.c.user_id, table.c.kind, table.c.doc)
                            .where(table.c.plan_id == PID)).all()


# -- panel shape -------------------------------------------------------------

def test_following_sits_between_watch_and_dismiss():
    assert [cls.ACTION for cls in PLAN_BUTTONS] == ["chart", "breakdown", "watch", "follow", "dismiss"]
    item = _button(PlanActionView(PID, author_id=None), "follow")
    assert isinstance(item, FollowingButton)
    assert item.item.label == "✅ Following"


def test_followable_statuses_are_the_open_ones():
    assert FOLLOWABLE_STATUSES == {PlanStatus.PENDING, PlanStatus.ACTIVE, PlanStatus.PARTIAL}


# -- the pure reply ------------------------------------------------------------

def test_pending_reply_counts_sessions_left():
    plan = _plan(plan_id=PID, created_at="2026-10-05", expiry_bars=5)     # Monday
    text = following_reply(plan, None, now=WED)                          # Tue + Wed elapsed
    assert "PENDING" in text
    assert "3 of 5 session(s) left" in text
    assert "stale" not in text
    assert text.endswith("Recorded as followed — paper plan, not your fill.")


def test_pending_reply_flags_a_stale_plan_at_one_or_no_session_left():
    for expiry, left in ((3, 1), (2, 0), (1, 0)):
        text = following_reply(_plan(plan_id=PID, created_at="2026-10-05", expiry_bars=expiry), None, now=WED)
        assert f"{left} of {expiry} session(s) left" in text
        assert "Plan stale." in text


def test_active_reply_states_price_against_entry_and_beyond_entry_in_r():
    plan = _plan(plan_id=PID, status=PlanStatus.ACTIVE, entry_price=100.0, stop_loss=95.0)
    text = following_reply(plan, 102.5, price_date=dt.date(2026, 10, 9))
    assert "Daily close 2026-10-09: 102.50 vs entry 100.00." in text
    assert "At that close, price was beyond entry by 0.50R." in text


def test_last_close_reads_the_cached_daily_bar_date(monkeypatch):
    import pandas as pd

    frame = pd.DataFrame({"Close": [102.5]}, index=[pd.Timestamp("2026-10-09")])
    monkeypatch.setattr(views, "get_daily_data", lambda ticker: frame)
    assert views._last_close("AAPL") == (102.5, dt.date(2026, 10, 9))


def test_bearish_beyond_entry_is_measured_downward():
    plan = _plan(plan_id=PID, status=PlanStatus.PARTIAL, direction="bearish",
                 entry_price=100.0, stop_loss=105.0, tp1=95.0, tp2=90.0)
    text = following_reply(plan, 97.5)
    assert "short" in text
    assert "At that close, price was beyond entry by 0.50R." in text


def test_price_on_the_wrong_side_of_entry_is_not_called_beyond():
    plan = _plan(plan_id=PID, status=PlanStatus.ACTIVE, entry_price=100.0, stop_loss=95.0)
    text = following_reply(plan, 99.0)
    assert "Daily close (date unavailable): 99.00 vs entry 100.00." in text
    assert "beyond" not in text


def test_a_failed_price_read_drops_only_the_price_line():
    plan = _plan(plan_id=PID, status=PlanStatus.ACTIVE, entry_price=100.0, stop_loss=95.0)
    text = following_reply(plan, None)
    assert "Daily close" not in text
    assert "ACTIVE" in text and "Recorded as followed" in text


def test_reply_wording_never_claims_an_execution():
    for status, price in ((PlanStatus.PENDING, None), (PlanStatus.ACTIVE, 103.0)):
        plan = _plan(plan_id=PID, status=status, entry_price=100.0, created_at="2026-10-05")
        text = following_reply(plan, price, now=WED).lower()
        assert "executed" not in text and "taken" not in text


# -- Following button ----------------------------------------------------------

def test_following_records_the_row_with_status_at_press_and_copies_it_to_the_trade(plan_env):
    trade_id = plan_env(status=PlanStatus.PENDING)
    text = _reply_text(_press("follow", AUTHOR))
    assert "Recorded as followed" in text
    rows = _follower_rows()
    assert [(r.user_id, r.kind) for r in rows] == [(AUTHOR, "taken")]
    assert rows[0].doc["status_at_press"] == PlanStatus.PENDING
    assert TradeLog().get_trade_by_id(trade_id)["taken_by"] == [AUTHOR]


def test_following_button_dates_the_cached_close_in_its_reply(plan_env):
    plan_env(status=PlanStatus.ACTIVE, entry_price=100.0, stop_loss=95.0)
    text = _reply_text(_press("follow", AUTHOR))
    assert "Daily close 2026-10-09: 102.50 vs entry 100.00." in text
    assert "At that close, price was beyond entry by 0.50R." in text


def test_a_second_press_unfollows_and_rewrites_the_trade_copy(plan_env):
    trade_id = plan_env(status=PlanStatus.ACTIVE, entry_price=100.0)
    _press("follow", AUTHOR)
    _press("follow", OTHER)
    text = _reply_text(_press("follow", AUTHOR))
    assert text == "No longer recorded as followed."
    assert [(r.user_id, r.kind) for r in _follower_rows()] == [(OTHER, "taken")]
    assert TradeLog().get_trade_by_id(trade_id)["taken_by"] == [OTHER]


@pytest.mark.parametrize("status", [PlanStatus.CLOSED, PlanStatus.CANCELLED])
def test_following_is_refused_once_the_outcome_is_known(plan_env, status):
    trade_id = plan_env(status=status)
    text = _reply_text(_press("follow", AUTHOR))
    assert status in text and "not counted" in text
    assert _follower_rows() == []
    assert "taken_by" not in TradeLog().get_trade_by_id(trade_id)


def test_following_a_pruned_plan_says_so(plan_env):
    text = _reply_text(_press("follow", AUTHOR))
    assert text == "This plan no longer exists."


def test_a_failed_trade_copy_still_records_the_follow(plan_env, monkeypatch):
    plan_env(status=PlanStatus.PENDING)

    def boom(self, plan_id, user_ids):
        raise RuntimeError("trades table down")

    monkeypatch.setattr(TradeLog, "mark_taken", boom)
    text = _reply_text(_press("follow", AUTHOR))
    assert "Recorded as followed" in text
    assert [(r.user_id, r.kind) for r in _follower_rows()] == [(AUTHOR, "taken")]


# -- per-user Watch -------------------------------------------------------------

def test_watch_is_per_user_and_the_star_follows_first_and_last_watcher(plan_env):
    plan_env()
    _press("watch", AUTHOR)
    assert PID in starred_ids()
    _press("watch", OTHER)
    _press("watch", AUTHOR)                  # AUTHOR leaves; OTHER still watches
    assert PID in starred_ids()
    assert [(r.user_id, r.kind) for r in _follower_rows()] == [(OTHER, "watch")]
    _press("watch", OTHER)                   # the last watcher leaves
    assert PID not in starred_ids()


@pytest.mark.parametrize("leaving", [False, True])
def test_watch_and_star_roll_back_together_on_star_write_failure(plan_env, monkeypatch, leaving):
    from swingbot.core.db.repositories.starred import StarredRepository

    plan_env()
    if leaving:
        _press("watch", AUTHOR)
    method = "unstar" if leaving else "star"

    def broken(self, plan_id, *, conn=None):
        raise RuntimeError("star write failed")

    monkeypatch.setattr(StarredRepository, method, broken)
    with pytest.raises(RuntimeError, match="star write failed"):
        views._toggle_watch(PlanStore().get(PID), AUTHOR)
    assert [(r.user_id, r.kind) for r in _follower_rows()] == (
        [(AUTHOR, "watch")] if leaving else []
    )
    assert (PID in starred_ids()) is leaving


def test_watch_replies_ephemerally_on_and_off(plan_env):
    plan_env()
    on = _interaction(AUTHOR)
    asyncio.run(_button(PlanActionView(PID, author_id=None), "watch").callback(on))
    args, kwargs = on.response.send_message.call_args
    assert args[0].startswith("⭐ Watching") and kwargs["ephemeral"] is True
    off = _interaction(AUTHOR)
    asyncio.run(_button(PlanActionView(PID, author_id=None), "watch").callback(off))
    assert off.response.send_message.call_args[0][0] == "No longer watching."


def test_watch_and_following_are_independent_rows(plan_env):
    plan_env()
    _press("watch", AUTHOR)
    _press("follow", AUTHOR)
    assert sorted((r.user_id, r.kind) for r in _follower_rows()) == [(AUTHOR, "taken"), (AUTHOR, "watch")]


def test_button_db_calls_run_off_the_event_loop():
    for cls, helper in ((views.WatchButton, "_toggle_watch"), (views.FollowingButton, "_toggle_following")):
        source = inspect.getsource(cls)
        assert f"to_thread({helper}" in source
        assert "followers_repo()" not in source

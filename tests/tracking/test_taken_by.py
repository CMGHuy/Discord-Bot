"""v152 D2: the trade carries a denormalised copy of who followed its plan.

plan_followers (kind "taken") is the truth. TradeLog.mark_taken copies the
set onto the plan's open trade at press time; close_plan_trade re-stamps it
from the table just before the close is written, and never lets a failed
read block the close.
"""
import logging

import pytest

from swingbot import config
from swingbot.core.planning.plan_store import PlanStore
from swingbot.core.tracking import performance
from swingbot.core.tracking.performance import TradeLog
from tests.planning.test_plan_engine_model import _plan
from tests.store_seed import seed_store

PID = "0f8fad5b-d9cb-469f-a165-70867728950e"
WIN_LEG = {"fraction": 1.0, "exit_price": 110.0, "r": 2.0, "reason": "win"}


@pytest.fixture
def tlog(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    seed_store("account", {
        "balance": 10000.0, "risk_pct": 1.0, "max_position_pct": 20.0,
        "sizing_mode": "risk_pct", "balance_history": [],
    })
    PlanStore().add(_plan(plan_id=PID))
    return TradeLog()


def _open_trade(tlog) -> str:
    return tlog.log_trade(
        ticker="AAPL", strategy="Fibonacci", horizon_key="4w",
        direction="bullish", confidence_level=4, confidence_label="High",
        entry=100.0, stop_loss=95.0, take_profit=110.0, plan_id=PID)


def _follow(user_id: int, kind: str = "taken") -> None:
    from swingbot.core.db.repositories.followers import followers_repo
    followers_repo().add(PID, user_id, kind, status_at_press="ACTIVE")


def test_mark_taken_writes_a_sorted_unique_set_on_the_open_trade(tlog):
    trade_id = _open_trade(tlog)
    first, second = 333333333333333333, 111111111111111111
    assert tlog.mark_taken(PID, [first, second, first]) is True
    assert tlog.get_trade_by_id(trade_id)["taken_by"] == [second, first]


def test_mark_taken_replaces_the_set_rather_than_appending(tlog):
    trade_id = _open_trade(tlog)
    tlog.mark_taken(PID, [5, 7])
    tlog.mark_taken(PID, [7])
    assert tlog.get_trade_by_id(trade_id)["taken_by"] == [7]


def test_mark_taken_leaves_every_other_field_alone(tlog):
    trade_id = _open_trade(tlog)
    before = tlog.get_trade_by_id(trade_id)
    tlog.mark_taken(PID, [5])
    after = tlog.get_trade_by_id(trade_id)
    assert {k: v for k, v in after.items() if k not in ("taken_by", "updated_at")} == \
        {k: v for k, v in before.items() if k != "updated_at"}


def test_mark_taken_is_false_without_an_open_trade(tlog):
    assert tlog.mark_taken(PID, [5]) is False
    trade_id = _open_trade(tlog)
    tlog.close_plan_trade(PID, WIN_LEG, "win")
    assert tlog.mark_taken(PID, [5]) is False
    assert "taken_by" not in tlog.get_trade_by_id(trade_id)


def test_close_restamps_taken_by_from_the_followers_table(tlog):
    trade_id = _open_trade(tlog)
    _follow(222222222222222222)
    _follow(111111111111111111)
    tlog.close_plan_trade(PID, WIN_LEG, "win")
    trade = tlog.get_trade_by_id(trade_id)
    assert trade["status"] == "win"
    assert trade["taken_by"] == [111111111111111111, 222222222222222222]


def test_close_clears_a_copy_whose_followers_all_left(tlog):
    trade_id = _open_trade(tlog)
    tlog.mark_taken(PID, [5])                 # copied at press; the row was later removed
    tlog.close_plan_trade(PID, WIN_LEG, "win")
    assert tlog.get_trade_by_id(trade_id)["taken_by"] == []


def test_close_without_followers_writes_no_taken_by_key(tlog):
    trade_id = _open_trade(tlog)
    tlog.close_plan_trade(PID, WIN_LEG, "win")
    assert "taken_by" not in tlog.get_trade_by_id(trade_id)


def test_watch_rows_never_count_as_followed(tlog):
    trade_id = _open_trade(tlog)
    _follow(5, kind="watch")
    tlog.close_plan_trade(PID, WIN_LEG, "win")
    assert "taken_by" not in tlog.get_trade_by_id(trade_id)


def test_a_failed_follower_read_keeps_the_copy_and_never_blocks_the_close(tlog, monkeypatch, caplog):
    trade_id = _open_trade(tlog)
    tlog.mark_taken(PID, [7])

    def boom():
        raise RuntimeError("followers table unreachable")

    monkeypatch.setattr("swingbot.core.db.repositories.followers.followers_repo", boom)
    with caplog.at_level(logging.WARNING, logger="swingbot.core.tracking.performance"):
        tlog.close_plan_trade(PID, WIN_LEG, "win")
    trade = tlog.get_trade_by_id(trade_id)
    assert trade["status"] == "win"
    assert trade["taken_by"] == [7]
    assert "could not read followers" in caplog.text


def test_taken_by_helper_returns_none_on_failure(monkeypatch):
    monkeypatch.setattr("swingbot.core.db.repositories.followers.followers_repo",
                        lambda: (_ for _ in ()).throw(RuntimeError("down")))
    assert performance._taken_by(PID) is None

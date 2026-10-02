"""The admin reads plans from the plans repository."""
import pytest

import swingbot.admin.app  # noqa: F401  (initialises api_v1 routes)
from swingbot.admin import watchlist_rows
from swingbot.admin.api_v1 import trades, trade_commands
from swingbot.core.planning.plan_engine import plan_to_dict
from tests.planning.test_plan_engine_model import _plan as _valid_plan
from tests.planning.test_plan_store_records import FakePlansRepo


@pytest.fixture
def db_only(monkeypatch):
    repo = FakePlansRepo([plan_to_dict(_valid_plan(plan_id="DBONLY"))])
    monkeypatch.setattr("swingbot.core.db.repositories.plans.plans_repo", lambda: repo)
    watchlist_rows.clear_signal_cache()
    return repo


def test_build_rows_includes_a_db_only_plan(db_only):
    assert "DBONLY" in {r["id"] for r in trades.build_rows()}


def test_plan_row_after_mutation_reads_the_db_plan(db_only, monkeypatch):
    seen = {}
    monkeypatch.setattr(trade_commands, "_row_from_plan",
                        lambda plan, trade, noted: seen.setdefault("plan", plan) and {"id": plan["plan_id"]})
    monkeypatch.setattr(trade_commands, "_attach_current_prices", lambda rows: None)
    monkeypatch.setattr(trade_commands, "_noted_ids", lambda: set())
    from flask import Flask
    with Flask(__name__).app_context():
        trade_commands._plan_row("DBONLY")
    assert seen["plan"]["plan_id"] == "DBONLY"


def test_trade_for_levels_working_stop_comes_from_the_db_plan(db_only, monkeypatch):
    db_only.records["DBONLY"]["working_stop"] = 12.5
    class Log:
        def get_trade_by_id(self, _id): return {"plan_id": "DBONLY"}
        def get_trades(self, **_kw): return []
    monkeypatch.setattr("swingbot.core.tracking.performance.TradeLog", Log)
    from swingbot.admin.app import _trade_for_levels
    assert _trade_for_levels("t1")["working_stop"] == 12.5


def test_signature_changes_when_a_db_plan_changes(db_only):
    first = watchlist_rows._plans_signature()
    db_only.records["DBONLY"]["_v"] = 5
    assert first is not None and watchlist_rows._plans_signature() != first

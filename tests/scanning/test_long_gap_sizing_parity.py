"""v191: stamped longs use one sizing path across alerts and admin readers."""
import logging

import pytest

from swingbot import config
from swingbot.admin import app as _admin_app  # noqa: F401 -- initializes API registration
from swingbot.admin import dashboard
from swingbot.admin.api_v1 import risk as risk_api
from swingbot.admin.api_v1 import trades as trades_api
from swingbot.core.planning import account
from swingbot.core.planning import gap_sizing as gs
from swingbot.core.planning.plan_types import plan_to_dict
from swingbot.core.scanning import analyze, execution_embeds, plan_table
from swingbot.core.scanning import outlook_run as orun
from swingbot.core.tracking import performance
from tests.scanning.test_gap_sizing_resize_sites import CFG, STAMP, _decision_ctx, _plan, _trade

LONG_STAMP = {"rule": "gap_p99", "down_gap_p99_pct": 3.0, "n_down_gaps": 125}
LINE = "Risk $67 at stop · $100 on a p99 gap (3.0%) · size cut for gap risk"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setattr(account.opex, "size_mult", lambda *a, **k: 1.0)
    monkeypatch.setattr(account, "load_account_config", lambda: dict(CFG))
    monkeypatch.setattr(analyze, "load_account_config", lambda: dict(CFG))
    monkeypatch.setattr(config, "SHORT_GAP_SIZING", True)
    monkeypatch.setattr(config, "LONG_GAP_SIZING", True)
    monkeypatch.setattr(config, "CURRENCY_SYMBOL", "$")


def _long(**kw):
    return _plan("bullish", gap_sizing=LONG_STAMP, **kw)


def _one_path():
    return gs.size_for(100.0, 98.0, direction="bullish", gap_sizing=LONG_STAMP)


def test_the_one_path_cuts_a_stamped_long():
    out = _one_path()
    assert (out["shares"], out["gap_sized"], out["gap_floor_pct"]) == (33.33, True, 3.0)


def test_alert_snapshot_and_ticket_line_match_the_one_path():
    assert plan_table._sizing_snapshot(100.0, _long()) == _one_path()
    assert execution_embeds.ticket_gap_line(_long()) == LINE


def test_outlook_card_risk_uses_the_cut_shares():
    assert orun._risk_dollars(_long()) == 66.66


def test_dashboard_sizing_map_cuts_a_stamped_long(monkeypatch):
    monkeypatch.setattr(dashboard, "_open_trade_prices", lambda trades: {})
    trades = [_trade("l1", "bullish", 98.0, LONG_STAMP), _trade("l0", "bullish", 98.0)]
    sizing = dashboard.build_open_trade_views(trades, dict(CFG))["sizing"]
    assert sizing["l1"]["shares"] == 33.33 and sizing["l1"]["gap_sized"] is True
    assert sizing["l0"] == account.compute_position_size(100.0, 98.0, account_cfg=dict(CFG))


def test_decision_context_shows_cut_shares_and_keeps_heat_on_config_risk(monkeypatch):
    ctx = _decision_ctx(monkeypatch, _long())
    assert ctx["sizing"]["shares"] == 33.33
    assert ctx["sizing"]["heat_after"] == ctx["sizing"]["heat_before"] + 1.0


def test_paper_sizing_matches_the_one_path():
    assert performance._paper_sizing(100.0, 98.0, "bullish", LONG_STAMP, "ZZZ") == _one_path()


def test_admin_order_block_of_a_stamped_long():
    detail = trades_api._gap_sizing_detail(plan_to_dict(_long()), None)
    assert detail["rule"] == "gap_p99"
    assert (detail["up_gap_p99_pct"], detail["down_gap_p99_pct"]) == (None, 3.0)
    assert (detail["shares"], detail["gap_sized"], detail["line"]) == (33.33, True, LINE)


def test_admin_order_block_uses_recorded_shares_of_a_long_trade():
    trade = {**_trade("l1", "bullish", 98.0, LONG_STAMP), "shares": 20.0}
    detail = trades_api._gap_sizing_detail(None, trade)
    assert detail["shares"] == 20.0
    assert detail["risk_amount"] == 40.0 and detail["gap_risk_amount"] == 60.0


def test_unstamped_long_is_none_and_short_shape_is_unchanged():
    assert trades_api._gap_sizing_detail(plan_to_dict(_plan("bullish")), None) is None
    short = trades_api._gap_sizing_detail(plan_to_dict(_plan(gap_sizing=STAMP)), None)
    assert list(short) == ["rule", "up_gap_p99_pct", "shares", "risk_amount", "gap_risk_amount",
                           "gap_sized", "line"]


@pytest.mark.parametrize("direction,stamp", [("sideways", LONG_STAMP), ("bullish", STAMP)])
def test_admin_order_block_rejects_invalid_direction_or_short_stamp_on_long(direction, stamp):
    assert trades_api._gap_sizing_detail({"direction": direction, "gap_sizing": stamp}, None) is None


def test_plan_stamp_wins_over_trade_stamp():
    trade = {**_trade("l1", "bullish", 98.0, {**LONG_STAMP, "down_gap_p99_pct": 9.0}), "shares": 20.0}
    detail = trades_api._gap_sizing_detail(plan_to_dict(_long()), trade)
    assert detail["down_gap_p99_pct"] == 3.0 and detail["gap_risk_amount"] == 60.0


def test_risk_page_short_gap_figure_never_counts_a_long():
    trade = {**_trade("l1", "bullish", 98.0, LONG_STAMP), "shares": 33.33}
    assert risk_api._open_short_gap_risk([trade]) == {"gap_risk_amount": None, "gap_risk_unknown": 0}


def test_switch_off_unstamped_long_is_todays_sizing_at_every_site(monkeypatch):
    monkeypatch.setattr(config, "LONG_GAP_SIZING", False)
    plan = _plan("bullish")
    assert plan_table._sizing_snapshot(100.0, plan) == account.compute_position_size(100.0, 98.0)
    assert execution_embeds.ticket_gap_line(plan) is None
    assert trades_api._gap_sizing_detail(plan_to_dict(plan), None) is None


@pytest.mark.parametrize("stamp,logs", [(LONG_STAMP, True), (None, False)])
def test_paper_sizing_failure_logs_only_a_stamped_long(monkeypatch, caplog, stamp, logs):
    def fail(*a, **kw):
        raise ValueError("unavailable")
    monkeypatch.setattr(gs, "size_for", fail)
    with caplog.at_level(logging.INFO, logger=performance.__name__):
        out = performance._paper_sizing(100.0, 98.0, "bullish", stamp, "ZZZ")
    assert out == account.compute_position_size(100.0, 98.0)
    assert ("ZZZ: gap sizing fell back to stop" in caplog.text) is logs

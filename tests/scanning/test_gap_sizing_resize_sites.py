"""v183: every re-size site sizes a stamped short through the one sizing path."""
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from swingbot import config
from swingbot.admin import dashboard
from swingbot.core.planning import account
from swingbot.core.planning.plan_types import PlanStatus, TradePlanV2
from swingbot.core.scanning import analyze, execution_embeds, plan_table
from swingbot.core.scanning import outlook_run as orun

CFG = {"balance": 10_000.0, "risk_pct": 1.0, "sizing_mode": "risk_pct", "position_pct": 10.0,
       "max_position_pct": 100.0, "max_position_value_absolute": 0, "max_risk_amount_absolute": 0}
STAMP = {"rule": "gap_p99", "up_gap_p99_pct": 3.0, "n_up_gaps": 125}


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setattr(account.opex, "size_mult", lambda *a, **k: 1.0)
    monkeypatch.setattr(account, "load_account_config", lambda: dict(CFG))
    monkeypatch.setattr(analyze, "load_account_config", lambda: dict(CFG))
    monkeypatch.setattr(config, "SHORT_GAP_SIZING", True)


def _plan(direction="bearish", **kw):
    short = direction == "bearish"
    base = dict(plan_id="p1", ticker="ZZZ", created_at="2026-10-20", source="confluence", strategy="MACD",
                horizon_key="3m", direction=direction, entry_type="stop_entry", trigger_price=100.0,
                entry_price=None, expiry_bars=5, stop_loss=102.0 if short else 98.0,
                tp1=95.0 if short else 105.0, tp1_fraction=0.5, tp2=None, breakeven_trigger_fraction=0.5,
                trail_atr_mult=2.0, quality_score=0, quality_breakdown=[], badge="WEAK", badge_stats={},
                status=PlanStatus.PENDING)
    base.update(kw)
    return TradePlanV2(**base)


def _trade(tid, direction, stop, gap_sizing=None):
    t = {"id": tid, "ticker": "ZZZ", "direction": direction, "entry": 100.0, "stop_loss": stop,
         "take_profit": 95.0 if direction == "bearish" else 105.0,
         "opened_at": datetime.now(timezone.utc).isoformat()}
    if gap_sizing is not None:
        t["gap_sizing"] = gap_sizing
    return t


# --- plan_table._sizing_snapshot (Discord full/simple, v81 ticket) ----------------

def test_snapshot_cuts_a_stamped_short():
    out = plan_table._sizing_snapshot(100.0, _plan(gap_sizing=STAMP))
    assert (out["shares"], out["risk_amount"], out["gap_risk_amount"], out["gap_sized"]) == (33.33, 66.67, 100.0, True)


def test_snapshot_of_a_long_is_todays_dict():
    assert plan_table._sizing_snapshot(100.0, _plan("bullish")) == account.compute_position_size(100.0, 98.0)


def test_snapshot_of_a_switch_off_short_is_todays_dict():
    plan = _plan(gap_sizing={**STAMP, "rule": "stop"})
    assert plan_table._sizing_snapshot(100.0, plan) == account.compute_position_size(100.0, 102.0)


def test_snapshot_of_a_pre_v183_short_sizes_on_the_stop_and_flags_n_a():
    out = plan_table._sizing_snapshot(100.0, _plan())
    assert out["shares"] == 50.0 and out["gap_risk_amount"] is None and out["gap_sized"] is False


def test_a_later_switch_flip_never_resizes_an_alerted_plan(monkeypatch):
    plan = _plan(gap_sizing=STAMP)
    monkeypatch.setattr(config, "SHORT_GAP_SIZING", False)
    assert plan_table._sizing_snapshot(100.0, plan)["shares"] == 33.33


def test_execution_ticket_uses_the_same_snapshot():
    assert execution_embeds._sizing_snapshot is plan_table._sizing_snapshot


def test_snapshot_still_swallows_a_sizing_failure(monkeypatch):
    def boom(entry, stop):
        raise ValueError("no account")
    monkeypatch.setattr(account, "compute_position_size", boom)
    assert plan_table._sizing_snapshot(100.0, _plan("bullish")) is None


# --- outlook_run._risk_dollars (v144 outlook card) ------------------------------

def test_outlook_risk_dollars_uses_the_cut_shares():
    assert orun._risk_dollars(_plan(gap_sizing=STAMP)) == 66.66     # 33.33 (rounded) shares x 2.00 stop distance
    assert orun._risk_dollars(_plan("bullish")) == 100.0             # 50 shares x 2.00, as today


# --- admin dashboard open-trade sizing map --------------------------------------

def test_dashboard_sizing_map_reads_the_trade_stamp(monkeypatch):
    monkeypatch.setattr(dashboard, "_open_trade_prices", lambda trades: {})
    trades = [_trade("s1", "bearish", 102.0, STAMP), _trade("l1", "bullish", 98.0),
              _trade("old", "bearish", 102.0)]
    sizing = dashboard.build_open_trade_views(trades, dict(CFG))["sizing"]
    assert sizing["s1"]["shares"] == 33.33 and sizing["s1"]["gap_sized"] is True
    assert sizing["l1"] == account.compute_position_size(entry=100.0, stop_loss=98.0, account_cfg=dict(CFG))
    assert sizing["old"]["shares"] == 50.0 and sizing["old"]["gap_risk_amount"] is None


# --- analyze.build_decision_context (decision chart sizing box) -----------------

def _decision_ctx(monkeypatch, plan):
    monkeypatch.setattr(analyze.trade_log, "get_trades", lambda **kw: [])
    monkeypatch.setattr(analyze.corr_mod, "cluster_exposure", lambda *a, **k: {"cluster": []})
    item = SimpleNamespace(plan_v2=plan, result=SimpleNamespace(ticker="ZZZ"))
    return analyze.build_decision_context(item, {}, None)


def test_decision_context_shows_the_cut_shares_and_keeps_heat_on_config_risk(monkeypatch):
    ctx = _decision_ctx(monkeypatch, _plan(gap_sizing=STAMP))
    assert ctx["sizing"]["shares"] == 33.33
    assert ctx["sizing"]["heat_after"] == ctx["sizing"]["heat_before"] + 1.0   # configured risk_pct, unchanged


def test_decision_context_of_a_long_is_unchanged(monkeypatch):
    ctx = _decision_ctx(monkeypatch, _plan("bullish"))
    assert ctx["sizing"]["shares"] == 50.0 and ctx["sizing"]["risk_pct"] == 1.0

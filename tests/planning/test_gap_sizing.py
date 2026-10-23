"""v183 Part A: the one sizing path, the plan stamp and the long plan-doc pin."""
import inspect
import json
import logging
from datetime import datetime, timezone
from types import SimpleNamespace

import pandas as pd
import pytest

from swingbot import config
from swingbot.core.planning import account
from swingbot.core.planning import gap_sizing as gs
from swingbot.core.planning.plan_types import PlanStatus, TradePlanV2, plan_from_dict, plan_to_dict
from swingbot.core.scanning import analyze
from swingbot.core.scanning import strategy_pass as sp

CFG = {"balance": 10_000.0, "risk_pct": 1.0, "sizing_mode": "risk_pct", "position_pct": 10.0,
       "max_position_pct": 100.0, "max_position_value_absolute": 0, "max_risk_amount_absolute": 0}
STAMP = {"rule": "gap_p99", "up_gap_p99_pct": 3.0, "n_up_gaps": 125}
NO_GAP = {"gap_risk_amount": None, "gap_sized": False, "gap_floor_pct": None}

# TradePlanV2's persisted keys, in order, before v183 -- a long plan doc must keep exactly these.
PRE_V183_PLAN_KEYS = [
    "plan_id", "ticker", "created_at", "source", "strategy", "horizon_key", "direction", "entry_type",
    "trigger_price", "entry_price", "expiry_bars", "stop_loss", "tp1", "tp1_fraction", "tp2",
    "breakeven_trigger_fraction", "trail_atr_mult", "quality_score", "quality_breakdown", "badge",
    "badge_stats", "status", "status_history", "working_stop", "legs_realized", "runner_high_close",
    "stop_mult_applied", "cohort_label", "cohort_stats", "risk_features", "ledger", "first_seen_price",
    "entry_context", "tp2_r_applied", "time_stop_days", "stall_exit_day", "hold_cap_bars", "pyramid_add",
    "confidence_level", "confidence_points", "confidence_unevaluated", "be_armed_session",
    "runner_floor_session", "notified_stop", "pending_notice", "issued_at", "acceptance_level",
    "acceptance_close_below", "stop_ceiling_pct", "pending_time_notices", "time_exit_due_date",
    "time_exit_unresolved_date", "time_exit_notified_date", "limit_cancel_level", "limit_strict_fill",
    "runner_path", "origin", "valid_session", "cancel_reason_message", "quote_at", "quote_kind",
    "quote_age_s", "quote_session", "price_confirmed",
]


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setattr(account.opex, "size_mult", lambda *a, **k: 1.0)
    monkeypatch.setattr(account, "load_account_config", lambda: dict(CFG))
    monkeypatch.setattr(config, "SHORT_GAP_SIZING", True)
    monkeypatch.setattr(config, "SHORT_RISK_NOTICE", False)   # V183-12 snapshot: no data/ queue write here


def _signed_gaps(n=300, up_pct=2.0, down_pct=6.0, end=None):
    """Flat close 100; even rows gap up up_pct, odd rows gap down down_pct."""
    idx = pd.bdate_range(end=end, periods=n) if end else pd.bdate_range(start="2025-06-02", periods=n)
    opens = [100.0 * (1 + up_pct / 100) if i % 2 == 0 else 100.0 * (1 - down_pct / 100) for i in range(n)]
    return pd.DataFrame({"Open": opens, "High": [max(o, 100.0) * 1.01 for o in opens],
                         "Low": [min(o, 100.0) * 0.99 for o in opens], "Close": [100.0] * n,
                         "Volume": [1_000_000.0] * n}, index=idx)


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


# --- the stamp ---------------------------------------------------------------

def test_stamp_is_none_for_a_long():
    assert gs.gap_sizing_stamp(_signed_gaps(), "bullish") is None


def test_stamp_for_a_short_reads_the_up_gap_p99():
    stamp = gs.gap_sizing_stamp(_signed_gaps(), "bearish")
    assert stamp == {"rule": "gap_p99", "up_gap_p99_pct": pytest.approx(2.0), "n_up_gaps": 125}


def test_switch_off_stamps_rule_stop_and_still_records_the_p99(monkeypatch):
    monkeypatch.setattr(config, "SHORT_GAP_SIZING", False)
    stamp = gs.gap_sizing_stamp(_signed_gaps(), "bearish")
    assert stamp["rule"] == gs.RULE_STOP and stamp["up_gap_p99_pct"] == pytest.approx(2.0)


def test_too_few_up_gaps_records_no_p99():
    stamp = gs.gap_sizing_stamp(_signed_gaps(n=100), "bearish")    # 99 gaps, 49 up < 60
    assert stamp == {"rule": "gap_p99", "up_gap_p99_pct": None, "n_up_gaps": 49}


def test_stamp_never_raises_and_logs_the_fallback_once(caplog):
    short, long_ = _plan(), _plan("bullish")
    with caplog.at_level(logging.INFO, logger="swingbot.core.planning.gap_sizing"):
        gs.stamp_gap_sizing(short, None)
        gs.stamp_gap_sizing(long_, None)
    assert short.gap_sizing == {"rule": "gap_p99", "up_gap_p99_pct": None, "n_up_gaps": 0}
    assert long_.gap_sizing is None
    assert len([r for r in caplog.records if "ZZZ: gap sizing" in r.getMessage()]) == 1


def test_missing_p99_is_logged_at_stamp_time(caplog):
    plan = _plan()
    with caplog.at_level(logging.INFO, logger="swingbot.core.planning.gap_sizing"):
        gs.stamp_gap_sizing(plan, _signed_gaps(n=100))
    assert "ZZZ: gap sizing p99 n/a (49 up-gaps, need 60) -- sized on the stop" in caplog.text


# --- the one sizing path --------------------------------------------------------

def test_gap_floor_for():
    assert gs.gap_floor_for("bearish", STAMP) == 3.0
    assert gs.gap_floor_for("bullish", STAMP) is None
    assert gs.gap_floor_for("bearish", None) is None
    assert gs.gap_floor_for("bearish", {**STAMP, "rule": "stop"}) is None
    assert gs.gap_floor_for("bearish", {**STAMP, "up_gap_p99_pct": None}) is None
    assert gs.gap_floor_for("bearish", {**STAMP, "up_gap_p99_pct": 0.0}) is None


def test_long_is_compute_position_size_exactly_even_with_a_stray_stamp():
    plain = account.compute_position_size(100.0, 98.0)
    assert gs.size_for(100.0, 98.0, direction="bullish", gap_sizing=None) == plain
    assert gs.size_for(100.0, 98.0, direction="bullish", gap_sizing=STAMP) == plain


def test_short_with_the_gap_rule_is_cut():
    out = gs.size_for(100.0, 102.0, direction="bearish", gap_sizing=STAMP)
    assert (out["shares"], out["risk_amount"], out["gap_risk_amount"], out["gap_sized"]) == (33.33, 66.67, 100.0, True)


def test_short_with_rule_stop_is_todays_sizing_byte_for_byte():
    plain = account.compute_position_size(100.0, 102.0)
    out = gs.size_for(100.0, 102.0, direction="bearish", gap_sizing={**STAMP, "rule": "stop"})
    assert out == plain and json.dumps(out) == json.dumps(plain)


@pytest.mark.parametrize("stamp", [None, {**STAMP, "up_gap_p99_pct": None, "n_up_gaps": 40}])
def test_short_without_a_usable_p99_sizes_on_the_stop_and_says_n_a(stamp):
    plain = account.compute_position_size(100.0, 102.0)
    assert gs.size_for(100.0, 102.0, direction="bearish", gap_sizing=stamp) == {**plain, **NO_GAP}


def test_exception_in_the_gap_path_falls_back_loudly(monkeypatch, caplog):
    real = account.compute_position_size

    def flaky(entry, stop_loss, account_cfg=None, **kw):
        if kw.get("gap_floor_pct") is not None:
            raise RuntimeError("boom")
        return real(entry, stop_loss, account_cfg, **kw)

    monkeypatch.setattr(account, "compute_position_size", flaky)
    with caplog.at_level(logging.INFO, logger="swingbot.core.planning.gap_sizing"):
        out = gs.size_for(100.0, 102.0, direction="bearish", gap_sizing=STAMP, label="ZZZ")
    assert out == {**real(100.0, 102.0), **NO_GAP}
    assert "ZZZ: gap sizing fell back to stop (boom)" in caplog.text


def test_two_argument_test_doubles_keep_working(monkeypatch):
    monkeypatch.setattr(account, "compute_position_size", lambda entry, stop: {"shares": 10.0})
    assert gs.size_for(100.0, 98.0, direction="bullish", gap_sizing=None) == {"shares": 10.0}


def test_explicit_account_cfg_is_passed_through():
    cfg = {**CFG, "risk_pct": 2.0}
    assert gs.size_for(100.0, 98.0, direction="bullish", gap_sizing=None, account_cfg=cfg)["shares"] == 100.0
    assert gs.size_for(100.0, 102.0, direction="bearish", gap_sizing=STAMP, account_cfg=cfg)["shares"] == 66.67


def test_size_for_plan_and_trade_read_the_stamp():
    plan = _plan(gap_sizing=STAMP)
    assert gs.size_for_plan(plan)["shares"] == 33.33                       # trigger_price default
    assert gs.size_for_plan(plan, entry=101.0)["shares"] == 33.0           # stop 1.00 away, gap 3.03
    stub = SimpleNamespace(ticker="OLD", direction="bullish", trigger_price=100.0, entry_price=None, stop_loss=98.0)
    assert gs.size_for_plan(stub) == account.compute_position_size(100.0, 98.0)   # no gap_sizing attribute
    trade = {"ticker": "ZZZ", "direction": "bearish", "entry": 100.0, "stop_loss": 102.0, "gap_sizing": STAMP}
    assert gs.size_for_trade(trade)["shares"] == 33.33
    assert gs.size_for_trade({**trade, "gap_sizing": None}) == {**account.compute_position_size(100.0, 102.0), **NO_GAP}


def test_gap_risk_amount_for():
    assert gs.gap_risk_amount_for(33.33, 100.0, 102.0, STAMP) == 99.99
    assert gs.gap_risk_amount_for(20.0, 100.0, 105.0, STAMP) == 100.0      # stop wider than the gap
    assert gs.gap_risk_amount_for(20.0, 100.0, 102.0, {**STAMP, "rule": "stop"}) is None
    assert gs.gap_risk_amount_for(20.0, 100.0, 102.0, None) is None
    assert gs.gap_risk_amount_for(None, 100.0, 102.0, STAMP) is None


# --- the plan field and the long plan-doc pin -------------------------------------

def test_long_plan_doc_keeps_exactly_its_pre_v183_keys():
    d = plan_to_dict(_plan("bullish"))
    assert list(d) == PRE_V183_PLAN_KEYS
    assert "gap_sizing" not in json.dumps(d)


def test_stamped_short_round_trips_and_unstamped_omits_the_key():
    stamped = plan_to_dict(_plan(gap_sizing=STAMP))
    assert list(stamped) == PRE_V183_PLAN_KEYS + ["gap_sizing"]
    assert plan_from_dict(json.loads(json.dumps(stamped))).gap_sizing == STAMP
    assert "gap_sizing" not in plan_to_dict(_plan())
    assert plan_from_dict(plan_to_dict(_plan())).gap_sizing is None


# --- the two live stamp sites ---------------------------------------------------------

def _attach(monkeypatch, plan, df, now=None):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    monkeypatch.setattr(analyze, "_build_quality_inputs", lambda *args, **kwargs: {})
    monkeypatch.setattr(analyze, "build_confluence_plan", lambda *args, **kwargs: plan)
    monkeypatch.setattr(analyze, "primary_strategy_for", lambda scenario: "MACD")
    monkeypatch.setattr(analyze, "stamp_entry_context",
                        lambda plan, df, asof: setattr(plan, "entry_context", {"stamped": True}))
    item = SimpleNamespace(rs_combined=None, sector_rs_percentile=None, conf=None, htf_bias=None,
                           target_confluence=None)
    scenario = SimpleNamespace(direction=plan.direction, entry=100.0)
    analyze.attach_plan_v2(item, scenario, df, "ZZZ", "3m", now=now)
    return item.plan_v2


def test_attach_plan_v2_stamps_a_short_outside_entry_context(monkeypatch):
    plan = _attach(monkeypatch, _plan(stop_loss=101.5), _signed_gaps())
    assert plan.gap_sizing == {"rule": "gap_p99", "up_gap_p99_pct": pytest.approx(2.0), "n_up_gaps": 125}
    assert plan.entry_context == {"stamped": True}


def test_attach_plan_v2_leaves_a_long_unstamped(monkeypatch):
    plan = _attach(monkeypatch, _plan("bullish"), _signed_gaps())
    assert plan.gap_sizing is None
    assert list(plan_to_dict(plan)) == PRE_V183_PLAN_KEYS


def test_strategy_plan_is_stamped_from_its_completed_frame(monkeypatch):
    monkeypatch.setattr(sp, "build_strategy_plan", lambda *args, **kwargs: _plan(source="strategy"))
    monkeypatch.setattr(sp, "stamp_badge", lambda plan: None)
    monkeypatch.setattr(sp, "stamp_cohort", lambda plan, state: None)
    monkeypatch.setattr(sp, "stamp_entry_context", lambda plan, df, asof: None)
    plan = sp.build_strategy_plan_at(_signed_gaps(), ticker="ZZZ", strategy="MACD", horizon_key="3m",
                                     direction="bearish", regime2_state="bear_quiet")
    assert plan.gap_sizing == {"rule": "gap_p99", "up_gap_p99_pct": pytest.approx(2.0), "n_up_gaps": 125}


def test_forming_bar_is_excluded_and_a_rebuild_gets_the_same_stamp():
    df = _signed_gaps(end="2026-10-21")
    df.iloc[-1, df.columns.get_loc("Open")] = 130.0                 # today's forming bar gaps up 30%
    first, rebuilt, after_close = _plan(), _plan(), _plan()
    analyze._stamp_gap_sizing_live(first, df, datetime(2026, 10, 21, 15, 0, tzinfo=timezone.utc))
    analyze._stamp_gap_sizing_live(rebuilt, df, datetime(2026, 10, 21, 19, 0, tzinfo=timezone.utc))
    analyze._stamp_gap_sizing_live(after_close, df, datetime(2026, 10, 21, 21, 30, tzinfo=timezone.utc))
    assert first.gap_sizing == rebuilt.gap_sizing
    assert first.gap_sizing["n_up_gaps"] == 125                     # forming bar not counted
    assert after_close.gap_sizing["n_up_gaps"] == 126               # after the close the bar is complete


def test_replay_never_stamps_and_entry_context_has_no_gap_sizing_key():
    from swingbot.core.backtesting import backtest_scenarios
    from swingbot.core.edge.context import FEATURE_KEYS
    assert "gap_sizing" not in inspect.getsource(backtest_scenarios)
    assert not any("gap_sizing" in key or "up_gap" in key for key in FEATURE_KEYS)

"""v191 Part B: LONG_GAP_SIZING sizes a long on max(stop distance, entry x the
p99 down-gap) -- v183's short rule, mirrored. Off by default; a long without a
long stamp sizes exactly as before v191."""
import json
import logging
from datetime import datetime, timezone

import pytest

from swingbot import config
from swingbot.core.planning import account
from swingbot.core.planning import gap_sizing as gs
from swingbot.core.planning.plan_types import plan_from_dict, plan_to_dict
from swingbot.core.scanning import strategy_pass as sp
from tests.planning.test_gap_sizing import CFG, NO_GAP, PRE_V183_PLAN_KEYS, _attach, _plan, _signed_gaps

LONG_STAMP = {"rule": "gap_p99", "down_gap_p99_pct": 3.0, "n_down_gaps": 125}
BUDGET = CFG["balance"] * CFG["risk_pct"] / 100          # $100


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setattr(account.opex, "size_mult", lambda *a, **k: 1.0)
    monkeypatch.setattr(account, "load_account_config", lambda: dict(CFG))
    monkeypatch.setattr(config, "SHORT_GAP_SIZING", True)
    monkeypatch.setattr(config, "LONG_GAP_SIZING", True)
    monkeypatch.setattr(config, "SHORT_RISK_NOTICE", False)


# --- the stamp ---------------------------------------------------------------

def test_switch_off_leaves_a_long_unstamped(monkeypatch):
    monkeypatch.setattr(config, "LONG_GAP_SIZING", False)
    assert gs.gap_sizing_stamp(_signed_gaps(), "bullish") is None


def test_stamp_for_a_long_reads_the_down_gap_p99():
    stamp = gs.gap_sizing_stamp(_signed_gaps(), "bullish")       # up 2%, down 6%
    assert stamp == {"rule": "gap_p99", "down_gap_p99_pct": pytest.approx(6.0), "n_down_gaps": 125}


def test_the_short_stamp_is_unchanged_by_the_long_switch():
    assert gs.gap_sizing_stamp(_signed_gaps(), "bearish") == {
        "rule": "gap_p99", "up_gap_p99_pct": pytest.approx(2.0), "n_up_gaps": 125}


def test_too_few_down_gaps_records_no_p99():
    stamp = gs.gap_sizing_stamp(_signed_gaps(n=100), "bullish")   # 99 gaps, 50 down < 60
    assert stamp == {"rule": "gap_p99", "down_gap_p99_pct": None, "n_down_gaps": 50}
    assert gs.MIN_DOWN_GAPS == 60


def test_stamp_never_raises_for_a_long_and_logs_once(caplog):
    plan = _plan("bullish")
    with caplog.at_level(logging.INFO, logger="swingbot.core.planning.gap_sizing"):
        gs.stamp_gap_sizing(plan, None)
    assert plan.gap_sizing == {"rule": "gap_p99", "down_gap_p99_pct": None, "n_down_gaps": 0}
    assert len([r for r in caplog.records if "ZZZ: gap sizing" in r.getMessage()]) == 1


def test_missing_down_p99_is_logged_at_stamp_time(caplog):
    plan = _plan("bullish")
    with caplog.at_level(logging.INFO, logger="swingbot.core.planning.gap_sizing"):
        gs.stamp_gap_sizing(plan, _signed_gaps(n=100))
    assert "ZZZ: gap sizing p99 n/a (50 down-gaps, need 60) -- sized on the stop" in caplog.text


# --- the one sizing path --------------------------------------------------------

def test_gap_floor_for_reads_the_side_that_hurts():
    assert gs.gap_floor_for("bullish", LONG_STAMP) == 3.0
    assert gs.gap_floor_for("bearish", LONG_STAMP) is None
    assert gs.gap_floor_for("bullish", {**LONG_STAMP, "rule": "stop"}) is None
    assert gs.gap_floor_for("bullish", {**LONG_STAMP, "down_gap_p99_pct": None}) is None
    assert gs.gap_floor_for("bullish", {**LONG_STAMP, "down_gap_p99_pct": 0.0}) is None
    assert gs.gap_floor_for(None, LONG_STAMP) is None


def test_long_with_the_gap_rule_is_cut():
    out = gs.size_for(100.0, 98.0, direction="bullish", gap_sizing=LONG_STAMP)
    assert (out["shares"], out["risk_amount"], out["gap_risk_amount"], out["gap_sized"]) == \
        (33.33, 66.67, 100.0, True)


def test_long_whose_p99_is_inside_the_stop_is_not_cut():
    out = gs.size_for(100.0, 98.0, direction="bullish", gap_sizing={**LONG_STAMP, "down_gap_p99_pct": 1.0})
    assert (out["shares"], out["gap_sized"]) == (50.0, False)


def test_long_without_a_usable_p99_sizes_on_the_stop_and_says_n_a():
    plain = account.compute_position_size(100.0, 98.0)
    stamp = {**LONG_STAMP, "down_gap_p99_pct": None, "n_down_gaps": 40}
    assert gs.size_for(100.0, 98.0, direction="bullish", gap_sizing=stamp) == {**plain, **NO_GAP}


@pytest.mark.parametrize("stamp", [None, {"rule": "gap_p99", "up_gap_p99_pct": 4.0, "n_up_gaps": 120},
                                   {**LONG_STAMP, "rule": "stop"}])
def test_a_long_without_a_long_gap_stamp_is_todays_sizing_byte_for_byte(stamp):
    plain = account.compute_position_size(100.0, 98.0)
    out = gs.size_for(100.0, 98.0, direction="bullish", gap_sizing=stamp)
    assert out == plain and json.dumps(out) == json.dumps(plain)


@pytest.mark.parametrize("entry,stop,p99", [(100.0, 98.0, 0.5), (100.0, 98.0, 3.0), (100.0, 98.5, 9.0),
                                            (37.13, 36.02, 4.4), (412.7, 401.9, 2.6)])
def test_dollar_loss_on_a_p99_gap_stays_inside_the_budget(entry, stop, p99):
    out = gs.size_for(entry, stop, direction="bullish",
                      gap_sizing={**LONG_STAMP, "down_gap_p99_pct": p99})
    distance = max(entry - stop, entry * p99 / 100)
    # v183's rule rounds shares to the cent-share, so one rounding step (0.005 shares)
    # is the only slack; V191-11's band branch floors instead and has none.
    assert out["shares"] * distance <= BUDGET + 0.005 * distance + 1e-9


def test_a_later_switch_flip_never_resizes_a_stamped_long(monkeypatch):
    plan = _plan("bullish", gap_sizing=LONG_STAMP)
    monkeypatch.setattr(config, "LONG_GAP_SIZING", False)
    assert gs.size_for_plan(plan, entry=100.0)["shares"] == 33.33


def test_gap_risk_amount_for_a_long():
    assert gs.gap_risk_amount_for(33.33, 100.0, 98.0, LONG_STAMP, direction="bullish") == 99.99
    assert gs.gap_risk_amount_for(33.33, 100.0, 98.0, LONG_STAMP) is None    # default stays bearish


def test_size_for_trade_reads_a_long_trade_stamp():
    trade = {"ticker": "ZZZ", "direction": "bullish", "entry": 100.0, "stop_loss": 98.0,
             "gap_sizing": LONG_STAMP}
    assert gs.size_for_trade(trade)["shares"] == 33.33


# --- the two live stamp sites and the plan doc ------------------------------------

def test_attach_plan_v2_stamps_a_long_when_the_switch_is_on(monkeypatch):
    plan = _attach(monkeypatch, _plan("bullish"), _signed_gaps())
    assert plan.gap_sizing == {"rule": "gap_p99", "down_gap_p99_pct": pytest.approx(6.0), "n_down_gaps": 125}


def test_strategy_long_is_stamped_from_its_completed_frame(monkeypatch):
    monkeypatch.setattr(sp, "build_strategy_plan", lambda *a, **k: _plan("bullish", source="strategy"))
    monkeypatch.setattr(sp, "stamp_badge", lambda plan: None)
    monkeypatch.setattr(sp, "stamp_cohort", lambda plan, state: None)
    monkeypatch.setattr(sp, "stamp_entry_context", lambda plan, df, asof: None)
    plan = sp.build_strategy_plan_at(_signed_gaps(), ticker="ZZZ", strategy="MACD", horizon_key="3m",
                                     direction="bullish", regime2_state="bull_quiet")
    assert plan.gap_sizing["n_down_gaps"] == 125


def test_a_stamped_long_round_trips_and_appends_one_key():
    d = plan_to_dict(_plan("bullish", gap_sizing=LONG_STAMP))
    assert list(d) == PRE_V183_PLAN_KEYS + ["gap_sizing"]
    assert plan_from_dict(json.loads(json.dumps(d))).gap_sizing == LONG_STAMP


@pytest.mark.parametrize("n,count,expected_p99", [(119, 59, None), (120, 60, 6.0)])
def test_long_stamp_requires_at_least_sixty_down_gaps(n, count, expected_p99):
    stamp = gs.gap_sizing_stamp(_signed_gaps(n=n), "bullish")
    assert stamp["n_down_gaps"] == count
    if expected_p99 is None:
        assert stamp["down_gap_p99_pct"] is None
    else:
        assert stamp["down_gap_p99_pct"] == pytest.approx(expected_p99)


def test_long_live_stamp_is_unchanged_when_the_forming_bar_is_truncated(monkeypatch):
    # At Friday noon ET only bars through Thursday are completed. An extreme
    # Friday down-gap must not enter the stamp computed for that completed bar.
    full = _signed_gaps(end="2026-10-23")
    full.iloc[-1, full.columns.get_loc("Open")] = 10.0
    now = datetime(2026, 10, 23, 16, 0, tzinfo=timezone.utc)
    with_forming = _attach(monkeypatch, _plan("bullish"), full, now=now)
    truncated = _attach(monkeypatch, _plan("bullish"), full.iloc[:-1].copy(), now=now)
    assert with_forming.gap_sizing == truncated.gap_sizing
    assert with_forming.gap_sizing["down_gap_p99_pct"] == pytest.approx(6.0)
    assert with_forming.gap_sizing["n_down_gaps"] == 125


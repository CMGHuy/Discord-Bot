"""v146 I1: the numeric confidence points reach the trade record and the plan.

Trade side: TradeLog.log_trade stores `confidence_points` and
`confidence_unevaluated` beside `confidence_breakdown`, from both confluence
callers (scan_run and short_run). Plan side: TradePlanV2 carries the same
two fields, set where confidence_level is set (_build_quality_inputs ->
_apply_quality). Trades and plans that carry no score store None.
"""
from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest

from swingbot import config
from swingbot.core.planning import params
from swingbot.core.planning.plan_types import plan_from_dict, plan_to_dict
from swingbot.core.scanning import analyze, scan_run, short_run
from swingbot.core.scanning.confidence import ConfidenceResult
from swingbot.core.tracking import performance
from swingbot.core.tracking.performance import TradeLog
from tests.helpers import make_ohlcv
from tests.planning.test_plan_engine_model import _plan
from tests.scanning.test_confidence_points import scenario_matrix
from tests.store_seed import seed_store

POINTS = {"Target distance quality": 12, "Stop level confluence": 10,
          "Market regime alignment": 7, "Tight stop penalty": -6}
UNEVALUATED = ["Market regime alignment"]


def _conf(**over) -> ConfidenceResult:
    base = dict(level=3, label="Medium", score=60, breakdown={},
                points=dict(POINTS), unevaluated=list(UNEVALUATED))
    base.update(over)
    return ConfidenceResult(**base)


def _open(log, ticker="AAPL", **kw):
    return log.log_trade(ticker=ticker, strategy="Fibonacci", horizon_key="4w",
                         direction="bullish", confidence_level=3, confidence_label="Medium",
                         entry=100.0, stop_loss=98.0, take_profit=106.0, **kw)


# --- the trade record ---------------------------------------------------

def test_log_trade_stores_points_and_unevaluated():
    log = TradeLog()
    trade = log.get_trade_by_id(_open(log, confidence_points=POINTS,
                                      confidence_unevaluated=UNEVALUATED))
    assert trade["confidence_points"] == POINTS
    assert trade["confidence_unevaluated"] == UNEVALUATED


def test_log_trade_without_a_score_stores_null_under_both_keys():
    """Strategy-path trades and plan-manager fills pass neither argument. The
    keys are present and null: 'this trade carried no score', never a guess."""
    log = TradeLog()
    trade = log.get_trade_by_id(_open(log))
    assert "confidence_points" in trade and trade["confidence_points"] is None
    assert "confidence_unevaluated" in trade and trade["confidence_unevaluated"] is None


def test_an_empty_map_is_stored_as_empty_not_null():
    """A scored trade whose scorer awarded nothing is not an unscored trade."""
    log = TradeLog()
    trade = log.get_trade_by_id(_open(log, confidence_points={}, confidence_unevaluated=[]))
    assert trade["confidence_points"] == {}
    assert trade["confidence_unevaluated"] == []


def test_every_legacy_scorer_result_survives_the_store_round_trip():
    """Each rule-table case of the legacy scorer -- fallbacks and the negative
    tight-stop penalty included -- reads back exactly as the scorer produced it."""
    log = TradeLog()
    matrix = scenario_matrix()
    assert matrix
    for index, (label, conf) in enumerate(matrix):
        trade = log.get_trade_by_id(_open(
            log, ticker=f"T{index}", confidence_score=conf.score,
            confidence_breakdown=conf.breakdown, confidence_points=conf.points,
            confidence_unevaluated=conf.unevaluated))
        assert trade["confidence_points"] == conf.points, label
        assert trade["confidence_unevaluated"] == conf.unevaluated, label
        assert trade["confidence_breakdown"] == conf.breakdown, label


def test_point_fields_are_copies_of_the_scorer_objects():
    points, unevaluated = dict(POINTS), list(UNEVALUATED)
    fields = performance._confidence_point_fields(points, unevaluated)
    assert fields == {"confidence_points": POINTS, "confidence_unevaluated": UNEVALUATED}
    assert fields["confidence_points"] is not points
    assert fields["confidence_unevaluated"] is not unevaluated
    assert all(type(value) is int for value in fields["confidence_points"].values())


def test_point_fields_keep_none_and_empty_apart():
    assert performance._confidence_point_fields(None, None) == {
        "confidence_points": None, "confidence_unevaluated": None}
    assert performance._confidence_point_fields({}, []) == {
        "confidence_points": {}, "confidence_unevaluated": []}


# --- the two confluence callers -----------------------------------------

def test_point_kwargs_read_a_real_result():
    assert scan_run._confidence_point_kwargs(_conf()) == {
        "confidence_points": POINTS, "confidence_unevaluated": UNEVALUATED}


@pytest.mark.parametrize("conf", [
    None,
    SimpleNamespace(level=3, label="Medium", score=60, breakdown={}),
], ids=["no-conf", "stand-in-without-points"])
def test_point_kwargs_are_null_without_a_scored_result(conf):
    assert scan_run._confidence_point_kwargs(conf) == {
        "confidence_points": None, "confidence_unevaluated": None}


def test_the_scan_loop_passes_the_points_to_log_trade():
    """_sync_run_scan is the main confluence caller; its log_trade call is
    pinned by source because driving the whole scan to a logged trade is a
    slow-tier fixture (tests/scanning/test_engine_v2_plans.py)."""
    source = inspect.getsource(scan_run._sync_run_scan)
    assert "**_confidence_point_kwargs(conf)" in source


def _short_item(conf):
    return SimpleNamespace(
        result=SimpleNamespace(ticker="AAPL", strategy="RSI", horizon_key="4w", trend="bearish"),
        plan=SimpleNamespace(stop_sources=[], target2_sources=[]),
        plan_v2=_plan(entry_type="stop_entry"), level_map=None, conf=conf, combined_from=[])


@pytest.fixture
def logged(monkeypatch):
    """short_run._log_trade with its collaborators stubbed; yields the kwargs
    log_trade received."""
    seen = {}
    monkeypatch.setattr(short_run.scan_run, "_logged_plan_fields", lambda *a: ([], 2.0))
    monkeypatch.setattr(short_run.scan_run, "_persist_plan_v2", lambda plan, alerts: None)
    monkeypatch.setattr(short_run.trade_log, "log_trade", lambda **kw: seen.update(kw) or "T1")
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    return seen


NUMS = {"entry": 102.0, "stop_loss": 103.5, "take_profit": 98.0, "target2": None}


def test_short_lane_passes_the_points_to_log_trade(logged):
    assert short_run._log_trade(_short_item(_conf()), NUMS, "why", None, []) == "T1"
    assert logged["confidence_points"] == POINTS
    assert logged["confidence_unevaluated"] == UNEVALUATED


def test_short_lane_logs_null_points_for_a_stand_in_conf(logged):
    stand_in = SimpleNamespace(level=3, label="Medium", score=60, breakdown={})
    short_run._log_trade(_short_item(stand_in), NUMS, "why", None, [], origin="next_session")
    assert logged["confidence_points"] is None
    assert logged["confidence_unevaluated"] is None
    assert logged["origin"] == "next_session"


# --- the plan -----------------------------------------------------------

def test_plan_fields_default_to_none_and_round_trip():
    plan = _plan()
    assert plan.confidence_points is None and plan.confidence_unevaluated is None
    plan.confidence_points, plan.confidence_unevaluated = dict(POINTS), list(UNEVALUATED)
    back = plan_from_dict(plan_to_dict(plan))
    assert back.confidence_points == POINTS
    assert back.confidence_unevaluated == UNEVALUATED


def test_a_pre_v146_plan_record_loads_with_both_fields_none():
    """Plans are not backfilled (no source text): an old record simply has no
    keys, and the dataclass defaults answer for it."""
    record = plan_to_dict(_plan())
    record.pop("confidence_points")
    record.pop("confidence_unevaluated")
    back = plan_from_dict(record)
    assert back.confidence_points is None and back.confidence_unevaluated is None


def _quality_inputs(**over):
    base = dict(regime="bullish", htf_bias="bullish", confluence_count=2, volume_ratio=1.2,
                atr_pct=50.0, trigger_distance_pct=0.3, rs_percentile=None, breadth=None)
    base.update(over)
    return base


def test_apply_quality_sets_the_points_where_it_sets_the_level():
    plan = _plan()
    inputs = _quality_inputs(confidence_level=4, confidence_points=dict(POINTS),
                             confidence_unevaluated=list(UNEVALUATED))
    params._apply_quality(plan, inputs)        # a leaked key would be a TypeError in score_plan
    assert plan.confidence_level == 4
    assert plan.confidence_points == POINTS
    assert plan.confidence_unevaluated == UNEVALUATED
    assert "confidence_points" in inputs, "the caller's dict is not mutated"


def test_apply_quality_without_the_keys_leaves_both_none():
    """The offline decile-audit caller passes no confidence keys at all."""
    plan = _plan()
    params._apply_quality(plan, _quality_inputs())
    assert plan.confidence_level is None
    assert plan.confidence_points is None and plan.confidence_unevaluated is None


def _scan_scenario():
    return SimpleNamespace(direction="bullish", entry=100.0, stop_loss=98.0, take_profit=110.0,
                           target_sources=["EMA21"], stop_sources=["Rolling support"])


@pytest.mark.parametrize("item,points,unevaluated", [
    (SimpleNamespace(conf=_conf()), POINTS, UNEVALUATED),
    (SimpleNamespace(conf=SimpleNamespace(level=3)), None, None),
    (SimpleNamespace(), None, None),
], ids=["scored", "stand-in-conf", "no-conf"])
def test_build_quality_inputs_carries_the_points(item, points, unevaluated):
    out = analyze._build_quality_inputs(item, _scan_scenario(), make_ohlcv([100.0] * 60), "4w")
    assert out["confidence_points"] == points
    assert out["confidence_unevaluated"] == unevaluated


@pytest.fixture
def scan_env(tmp_path, monkeypatch):
    """The account row and data dir attach_plan_v2's plan build reads -- the
    same isolation tests/scanning/test_engine_v2_plans.py applies. The real
    days_to_earnings source stays in place: it is cache-only, and the empty
    data dir leaves its on-disk ledger cold."""
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    seed_store("account", {
        "balance": 10000.0, "risk_pct": 1.0, "max_position_pct": 20.0,
        "sizing_mode": "risk_pct",
        "balance_history": [{"ts": "2026-08-01T00:00:00+00:00", "balance": 10000.0}],
    })
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "shadow")


def test_attach_plan_v2_stamps_the_live_plan(scan_env, monkeypatch):
    from swingbot.core.market import events
    fetched = []
    monkeypatch.setattr(events, "get_earnings_datetimes",
                        lambda *a, **k: fetched.append(a) or [])   # the stamp must never fetch
    monkeypatch.setattr(events.yf, "Ticker", lambda *a, **k: fetched.append(a))
    item = SimpleNamespace(plan_v2=None, target_confluence=(2, ["EMA21", "Fib"]),
                           conf=_conf(), htf_bias="bullish")
    analyze.attach_plan_v2(
        item, _scan_scenario(), make_ohlcv([100.0] * 60), ticker="TEST", horizon_key="4w",
        level_map=None, regime=SimpleNamespace(trend="bullish"), rs_percentile=50.0,
        breadth=60.0, regime2_state="bull_normal")
    assert item.plan_v2 is not None, "plan_v2 should be built"
    assert item.plan_v2.confidence_level == 3
    assert item.plan_v2.confidence_points == POINTS
    assert item.plan_v2.confidence_unevaluated == UNEVALUATED
    assert fetched == []

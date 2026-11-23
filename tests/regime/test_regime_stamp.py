"""v239 V239-9: entry_context gains bear_regime and regime_action; regime_day reaches the stamp."""
import dataclasses
import inspect
import json
from datetime import date
from types import SimpleNamespace

import pytest

from swingbot import config
from swingbot.core.market import bear_regime as br
from swingbot.core.planning import params
from swingbot.core.scanning import analyze, qualify
from tests.helpers import make_ohlcv
from tests.scanning.test_live_context_stamp import _plan

FRAME = make_ohlcv([100.0 + i * 0.1 for i in range(300)], start="2025-06-02")
S, D = date(2026, 11, 18), date(2026, 11, 19)
KEYS = {"bear_regime", "regime_action"}
PRE_V239 = {"regime2_state": "bull_quiet", "rs_pctile": 64.0, "sector_pctile": 55.0,
            "rs_combined": 61.0}


def _day(state=br.CORRECTION, stress=True, pullback=False):
    return br.RegimeDay(session_date=D, last_bar_date=S, state=state, stress=stress,
                        pullback_trigger=pullback)


def _stamped(day, direction="bullish", asof=None):
    plan = dataclasses.replace(_plan(), direction=direction)
    params.stamp_entry_context(plan, FRAME, {**(asof or {}), **params.regime_asof(day)})
    return plan.entry_context


def test_regime_asof_is_empty_without_a_day():
    day = _day()
    assert params.regime_asof(None) == {}
    assert params.regime_asof(day) == {"bear_regime_day": day}


@pytest.mark.parametrize("state, stress, pullback, direction, action", [
    (br.BEAR, None, False, "bullish", "would_veto"),
    (br.BEAR, False, False, "bullish", "would_veto"),
    (br.CORRECTION, True, False, "bullish", "would_veto"),
    (br.CORRECTION, False, False, "bullish", "caution"),
    (br.CORRECTION, None, False, "bullish", "caution"),       # missing VIX never reads as stress
    (br.CORRECTION, True, True, "bullish", "pullback_watch"),  # pullback wins over would_veto
    (br.NORMAL, False, False, "bullish", "none"),
    (br.UNKNOWN, None, False, "bullish", "none"),
    (br.BEAR, True, False, "bearish", "aligned"),
    (br.CORRECTION, False, True, "bearish", "aligned"),
    (br.NORMAL, None, False, "bearish", "none"),
    (br.UNKNOWN, None, False, "bearish", "none")])
def test_the_stamp_carries_the_state_and_the_action_for_the_plan_direction(
        state, stress, pullback, direction, action):
    ctx = _stamped(_day(state, stress, pullback), direction)
    assert (ctx["bear_regime"], ctx["regime_action"]) == (state, action)


def test_without_a_day_the_stamp_is_the_pre_v239_dict():
    plain = _plan()
    params.stamp_entry_context(plain, FRAME, {"rs_pctile": 64.0})
    assert not KEYS & set(plain.entry_context)
    same = _stamped(None, asof={"rs_pctile": 64.0})
    assert json.dumps(same, sort_keys=True, default=str) ==         json.dumps(plain.entry_context, sort_keys=True, default=str)   # NaN-safe


def test_only_strings_reach_the_record():
    ctx = _stamped(_day())
    assert "bear_regime_day" not in ctx
    assert {k: ctx[k] for k in KEYS} == {"bear_regime": "CORRECTION", "regime_action": "would_veto"}
    assert json.loads(json.dumps(ctx, default=str))["bear_regime"] == "CORRECTION"


def test_the_keys_survive_a_feature_build_failure(monkeypatch):
    import swingbot.core.edge.context as edge_context

    def boom(*args, **kwargs):
        raise RuntimeError("features down")

    monkeypatch.setattr(edge_context, "entry_context", boom)
    assert _stamped(_day(br.BEAR)) == {"bear_regime": "BEAR", "regime_action": "would_veto"}


def test_the_regime_keys_sit_beside_the_shock_label():
    ctx = _stamped(_day(), asof={"shock_state": "NORMAL"})
    assert (ctx["shock_state"], ctx["bear_regime"]) == ("NORMAL", "CORRECTION")


def test_an_unknown_direction_is_action_none():
    assert _stamped(_day(br.BEAR), direction="neutral")["regime_action"] == "none"


def _attach_env(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    monkeypatch.setattr(analyze, "_build_quality_inputs", lambda *a, **k: {})
    monkeypatch.setattr(analyze, "build_confluence_plan", lambda *a, **k: _plan())
    monkeypatch.setattr(analyze, "primary_strategy_for", lambda scenario: "MACD")
    seen = []
    monkeypatch.setattr(analyze, "stamp_entry_context", lambda plan, df, asof: seen.append(asof))
    return seen


def _attach(**kwargs):
    item = SimpleNamespace(rs_combined=61.0, sector_rs_percentile=55.0, conf=None, htf_bias=None,
                           target_confluence=None)
    analyze.attach_plan_v2(item, SimpleNamespace(direction="bullish", entry=100.0), FRAME, "AAPL",
                           "3m", rs_percentile=64.0, regime2_state="bull_quiet", **kwargs)


def test_attach_plan_v2_adds_the_day_to_the_asof(monkeypatch):
    seen, day = _attach_env(monkeypatch), _day()
    _attach(shock_state="NORMAL", regime_day=day)
    assert seen == [{**PRE_V239, "shock_state": "NORMAL", "bear_regime_day": day}]


@pytest.mark.parametrize("kwargs", [{}, {"regime_day": None}])
def test_attach_plan_v2_without_a_day_hands_over_the_pre_v239_asof(monkeypatch, kwargs):
    seen = _attach_env(monkeypatch)
    _attach(**kwargs)
    assert seen == [PRE_V239]


def _context(**over):
    return qualify.QualifyContext(frames={}, spy=None, sector_of={}, etf_symbol_of={},
                                  sector_frames={}, regime=None, regimes=None, **over)


def test_the_context_carries_a_day_after_the_shock_label_defaulting_to_none():
    names = [f.name for f in dataclasses.fields(qualify.QualifyContext)]
    assert names[-2:] == ["shock_state", "regime_day"]
    assert _context().regime_day is None


@pytest.mark.parametrize("day", [None, _day()])
def test_the_short_attach_forwards_the_context_day(monkeypatch, day):
    calls = []
    monkeypatch.setattr(analyze, "attach_plan_v2",
                        lambda *a, **k: calls.append(k.get("regime_day", "MISSING")))
    item = SimpleNamespace(result=SimpleNamespace(ticker="AAA", horizon_key="4w", trend="bearish",
                                                  state_key="k", state_value="v"),
                           plan="scenario", level_map=None, rs_percentile=None, htf_info=None,
                           plan_v2=None, plan_v2_rejected=None)
    qualify._attach_plan(item, _context(regime_day=day))
    assert calls == [day]


def test_planning_never_reads_the_regime_store_or_runs_the_pass():
    for module in (qualify, params, analyze):
        source = inspect.getsource(module)
        assert "regime_scan" not in source and "regime_for_pass" not in source, module
        assert "market_regime_repo" not in source, module

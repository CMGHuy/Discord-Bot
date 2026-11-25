"""v239 V239-10: one regime pass per scan pass and per SHORT run; its day reaches every lane.

Planning never runs the pass: the scan entry points do, once, and hand the day down
the same routes v209's shock label takes."""
import ast
import inspect
from datetime import date
from types import SimpleNamespace

import pytest

from swingbot import config
from swingbot.core.market import bear_regime as br
from swingbot.core.planning.rebuild import RebuildPrice
from swingbot.core.scanning import analyze, regime_scan, scan_replay, scan_run, short_run
from tests.scanning.test_shock_plans_byte_identical import _attach_on_rebuild
from tests.scanning.test_shock_short_lane import _calls, _functions, _lane_inputs
from tests.scanning.test_shock_state_stamp import _strategy, strategy_env  # noqa: F401  (fixture)

PRICE = RebuildPrice(101.0, "trade", 1.0, "2026-11-05T15:00:00+00:00", 1000.0, True, "regular")
DAY = br.RegimeDay(session_date=date(2026, 11, 19), last_bar_date=date(2026, 11, 18),
                   state=br.CORRECTION, stress=True)
LANE = {"sector_of": {}, "etf_symbol_of": {}, "sector_frames": {}, "spy": None,
        "regime": None, "regimes": None}


def _item(trend="bullish"):
    return SimpleNamespace(
        result=SimpleNamespace(ticker="AAA", horizon_key="4w", trend=trend, state_key="k",
                               state_value="v"),
        level_map=None, rs_percentile=None, breadth=None, htf_info=None,
        plan_v2=None, plan_v2_rejected=None, plan="scenario")


def _capture_attach(monkeypatch):
    calls = []
    monkeypatch.setattr(analyze, "attach_plan_v2",
                        lambda *a, **k: calls.append(k.get("regime_day", "MISSING")))
    return calls


def test_the_test_session_runs_no_regime_pass():
    assert config.BEAR_REGIME_MODE == "off"      # tests/conftest.py pin


@pytest.mark.parametrize("day", [None, DAY])
def test_attach_item_plan_forwards_the_day(monkeypatch, day):
    calls = _capture_attach(monkeypatch)
    scan_run._attach_item_plan(_item(), "scenario", None, None, None, regime_day=day)
    assert calls == [day]


def test_attach_item_plan_defaults_to_no_day(monkeypatch):
    calls = _capture_attach(monkeypatch)
    scan_run._attach_item_plan(_item(), "scenario", None, None, None, shock_state="SHOCK")
    assert calls == [None]


def test_the_requote_rebuild_attaches_with_the_day(monkeypatch):
    calls = _capture_attach(monkeypatch)
    _attach_on_rebuild(monkeypatch, scan_run, lambda item: "rebuilt")
    out = scan_run._rebuild_item(_item(), PRICE, fresh_data={}, regimes=None, regime=None,
                                 require_confirmation=True, shock_state=None, regime_day=DAY)
    assert out.kept and calls == [DAY]


@pytest.mark.parametrize("extra, expected", [
    ({}, {}), ({"regime_day": None}, {}), ({"regime_day": DAY}, {"bear_regime_day": DAY}),
    ({"shock_state": "SHOCK", "regime_day": DAY}, {"shock_state": "SHOCK", "bear_regime_day": DAY})])
def test_the_strategy_asof_carries_the_day(strategy_env, extra, expected):
    _strategy(**extra)
    assert strategy_env["asof_of"]("AAA") == expected


def test_the_scan_runs_the_pass_once_and_threads_its_day_into_every_builder():
    fns = _functions(scan_run)
    runners = [name for name, fn in fns.items() if _calls(fn, "regime_for_pass")]
    assert runners == ["_sync_run_scan"]
    (call,) = _calls(fns["_sync_run_scan"], "regime_for_pass")
    assert ast.unparse(call) == "regime_scan.regime_for_pass()"
    wanted = {"_attach_item_plan", "_maybe_run_strategy_pass", "partial"}
    seen = {}
    for node in (n for n in ast.walk(fns["_sync_run_scan"]) if isinstance(n, ast.Call)):
        name = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
        if name in wanted:
            seen[name] = {k.arg: ast.unparse(k.value) for k in node.keywords}.get("regime_day")
    assert seen == {name: "regime_day" for name in wanted}


def test_the_bare_context_carries_the_day():
    assert short_run._bare_context({}).regime_day is None
    assert short_run._bare_context({}, regime_day=DAY).regime_day is DAY


def test_the_lane_state_runs_the_pass_once(monkeypatch):
    runs = []
    monkeypatch.setattr(short_run.shock_scan, "current_label", lambda **k: None)
    monkeypatch.setattr(regime_scan, "regime_for_pass", lambda **k: runs.append(k) or DAY)
    lane = short_run._lane_state(*_lane_inputs(monkeypatch), None)
    assert runs == [{}] and lane["regime_day"] is DAY


@pytest.mark.parametrize("lane, expected", [({**LANE, "regime_day": DAY}, DAY),
                                            ({**LANE, "regime_day": None}, None), (LANE, None)])
def test_the_qualify_context_takes_the_day_from_the_lane(lane, expected):
    assert short_run._qualify_context(False, {}, lane).regime_day is expected


def test_the_short_requote_rebuild_keeps_the_day(monkeypatch):
    calls = _capture_attach(monkeypatch)
    _attach_on_rebuild(monkeypatch, short_run, lambda item: "rebuilt")
    item = _item("bearish")
    out = short_run._rebuild_fn({}, short_run._bare_context({}, regime_day=DAY))(item, PRICE)
    assert out.kept and calls == [DAY]


def test_the_short_run_runs_the_pass_only_at_its_lane_entry():
    fns = _functions(short_run)
    assert [name for name, fn in fns.items() if _calls(fn, "regime_for_pass")] == ["_lane_state"]
    assert len(_calls(fns["_sync_run_short_scan"], "_lane_state")) == 1


def test_replay_contexts_never_carry_a_day():
    for call in _calls(ast.parse(inspect.getsource(scan_replay)), "QualifyContext"):
        assert "regime_day" not in {k.arg for k in call.keywords}

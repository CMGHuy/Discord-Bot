"""v209: the scan's shock label reaches every confluence, requote and strategy plan."""
import ast
import inspect
from types import SimpleNamespace

import pytest

from swingbot import config
from swingbot.core.planning.rebuild import RebuildOutcome, RebuildPrice
from swingbot.core.scanning import analyze, scan_run, strategy_pass
from tests.helpers import make_ohlcv
from tests.scanning.test_live_context_stamp import _plan

PRICE = RebuildPrice(101.0, "trade", 1.0, "2026-11-05T15:00:00+00:00", 1000.0, True, "regular")
FRAME = make_ohlcv([100.0] * 300, start="2025-06-02")


def _attach_env(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    monkeypatch.setattr(analyze, "_build_quality_inputs", lambda *a, **k: {})
    monkeypatch.setattr(analyze, "build_confluence_plan", lambda *a, **k: _plan())
    monkeypatch.setattr(analyze, "primary_strategy_for", lambda scenario: "MACD")
    seen = []
    monkeypatch.setattr(analyze, "stamp_entry_context", lambda plan, df, asof: seen.append(asof))
    return seen


def _readings_item():
    return SimpleNamespace(rs_combined=61.0, sector_rs_percentile=55.0, conf=None, htf_bias=None,
                           target_confluence=None)


PRE_V209 = {"regime2_state": "bull_quiet", "rs_pctile": 64.0, "sector_pctile": 55.0,
            "rs_combined": 61.0}


def test_attach_plan_v2_adds_the_label_to_the_asof(monkeypatch):
    seen = _attach_env(monkeypatch)
    analyze.attach_plan_v2(_readings_item(), SimpleNamespace(direction="bullish", entry=100.0),
                           FRAME, "AAPL", "3m", rs_percentile=64.0, regime2_state="bull_quiet",
                           shock_state="SHOCK")
    assert seen == [{**PRE_V209, "shock_state": "SHOCK"}]


@pytest.mark.parametrize("kwargs", [{}, {"shock_state": None}])
def test_attach_plan_v2_without_a_label_hands_over_the_pre_v209_asof(monkeypatch, kwargs):
    seen = _attach_env(monkeypatch)
    analyze.attach_plan_v2(_readings_item(), SimpleNamespace(direction="bullish", entry=100.0),
                           FRAME, "AAPL", "3m", rs_percentile=64.0, regime2_state="bull_quiet",
                           **kwargs)
    assert seen == [PRE_V209]


def _capture_attach(monkeypatch):
    calls = []
    monkeypatch.setattr(analyze, "attach_plan_v2",
                        lambda *a, **k: calls.append(k.get("shock_state", "MISSING")))
    return calls


def _scan_item():
    return SimpleNamespace(
        result=SimpleNamespace(ticker="AAA", horizon_key="4w", trend="bullish",
                               state_key="k", state_value="v"),
        level_map=None, rs_percentile=None, breadth=None, htf_info=None,
        plan_v2=None, plan_v2_rejected=None, plan="scenario")


@pytest.mark.parametrize("label", [None, "SHOCK"])
def test_attach_item_plan_forwards_the_label(monkeypatch, label):
    calls = _capture_attach(monkeypatch)
    scan_run._attach_item_plan(_scan_item(), "scenario", None, None, None, shock_state=label)
    assert calls == [label]


def test_attach_item_plan_defaults_to_no_label(monkeypatch):
    calls = _capture_attach(monkeypatch)
    scan_run._attach_item_plan(_scan_item(), "scenario", None, None, None)
    assert calls == [None]


def test_the_requote_rebuild_attaches_with_the_label(monkeypatch):
    calls = _capture_attach(monkeypatch)

    def rebuild(item, price, *, rescenario, attach):
        attach("rebuilt")
        return RebuildOutcome(True, None, price)

    monkeypatch.setattr(scan_run.rebuild, "rebuild_before_post", rebuild)
    out = scan_run._rebuild_item(_scan_item(), PRICE, fresh_data={}, regimes=None, regime=None,
                                 require_confirmation=True, shock_state="RECOVERY")
    assert out.kept and calls == ["RECOVERY"]


@pytest.fixture
def strategy_env(monkeypatch):
    monkeypatch.setattr(config, "STRATEGY_ALERTS_MODE", "shadow")
    monkeypatch.setattr(scan_run, "PlanStore", lambda: None)
    monkeypatch.setattr(scan_run, "_compression_hooks", lambda *a: (None, None))
    monkeypatch.setattr(scan_run, "_compression_seen", lambda: set())
    monkeypatch.setattr(scan_run, "_record_compression_shadow", lambda result: None)
    seen = {}

    def fake_pass(tickers, fresh_data, **kwargs):
        seen.update(kwargs)
        return SimpleNamespace(alerts=[], plans=[], opened=0, compression_shadow=[],
                               compression_rejected=0, pullback_volume=0, headroom=0)

    monkeypatch.setattr(strategy_pass, "run_strategy_pass", fake_pass)
    return seen


def _strategy(**extra):
    return scan_run._maybe_run_strategy_pass(
        tickers=["AAA"], fresh_data={"AAA": None}, spy_df=None, regimes=None, rs_cache=None,
        sector_of_ticker={}, etf_symbol_of_sector={}, sector_etf_frames={}, trade_log=None,
        alerts=[], require_confirmation=True, **extra)


@pytest.mark.parametrize("label,expected", [(None, {}), ("SHOCK", {"shock_state": "SHOCK"})])
def test_the_strategy_asof_carries_the_label(strategy_env, label, expected):
    _strategy(shock_state=label)
    assert strategy_env["asof_of"]("AAA") == expected
    assert strategy_env["rs_combined_of"]("AAA") is None


def test_the_strategy_pass_defaults_to_no_label(strategy_env):
    _strategy()
    assert strategy_env["asof_of"]("AAA") == {}


def test_the_strategy_plan_stamp_receives_the_label(monkeypatch):
    calls = []
    monkeypatch.setattr(strategy_pass, "build_strategy_plan", lambda *a, **k: _plan())
    monkeypatch.setattr(strategy_pass, "stamp_badge", lambda plan: None)
    monkeypatch.setattr(strategy_pass, "stamp_cohort", lambda plan, state: None)
    monkeypatch.setattr(strategy_pass, "stamp_entry_context",
                        lambda plan, df, asof: calls.append(asof))
    strategy_pass.build_strategy_plan_at(FRAME, ticker="AAPL", strategy="MACD", horizon_key="3m",
                                         direction="bullish", regime2_state="bear_volatile",
                                         asof={"shock_state": "SHOCK"})
    assert calls == [{"shock_state": "SHOCK", "regime2_state": "bear_volatile"}]


def test_the_scan_threads_its_label_into_every_builder():
    tree = ast.parse(inspect.getsource(scan_run))
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "_sync_run_scan")
    wanted = {"_attach_item_plan", "_maybe_run_strategy_pass", "partial"}
    seen = []
    for call in (n for n in ast.walk(fn) if isinstance(n, ast.Call)):
        func = call.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
        if name in wanted:
            keywords = {k.arg: ast.unparse(k.value) for k in call.keywords}
            seen.append((name, keywords.get("shock_state")))
    assert {name for name, _ in seen} == wanted
    assert all(value == "shock_state" for _, value in seen), seen

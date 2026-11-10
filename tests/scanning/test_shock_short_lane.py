"""v209: the SHORT lane reads the stored shock label once per run, at its own
entry point (`_lane_state`), and hands it to every SHORT build and rebuild
through QualifyContext. Planning (qualify.py) never reads the repository."""
import ast
import dataclasses
import inspect
from types import SimpleNamespace

import pytest

from swingbot import config
from swingbot.core.planning.rebuild import RebuildOutcome, RebuildPrice
from swingbot.core.scanning import analyze, qualify, scan_replay, shock_scan, short_run

PRICE = RebuildPrice(101.0, "trade", 1.0, "2026-11-05T15:00:00+00:00", 1000.0, True, "regular")
LANE = {"sector_of": {}, "etf_symbol_of": {}, "sector_frames": {}, "spy": None,
        "regime": None, "regimes": None}


def _item():
    return SimpleNamespace(result=SimpleNamespace(ticker="AAA", horizon_key="4w", trend="bearish",
                                                  state_key="k", state_value="v"),
                           plan="scenario", level_map=None, rs_percentile=None, htf_info=None,
                           plan_v2=None, plan_v2_rejected=None)


def _capture_attach(monkeypatch):
    calls = []
    monkeypatch.setattr(analyze, "attach_plan_v2",
                        lambda *a, **k: calls.append(k.get("shock_state", "MISSING")))
    return calls


def _lane_inputs(monkeypatch):
    monkeypatch.setattr(short_run.regime2, "regime_series", lambda spy: "series")
    monkeypatch.setattr(short_run.fetch, "_etf_symbol_of_sector", lambda: {"Tech": "XLK"})
    reference = SimpleNamespace(spy="spy", sector_frames={"XLK": "frame"})
    snapshot = SimpleNamespace(sector_of={"AAA": "Tech"})
    return reference, snapshot


def test_the_label_is_the_last_context_field_and_defaults_to_none():
    fields = dataclasses.fields(qualify.QualifyContext)
    assert fields[-1].name == "shock_state" and fields[-1].default is None
    ctx = qualify.QualifyContext(frames={}, spy=None, sector_of={}, etf_symbol_of={},
                                 sector_frames={}, regime=None, regimes=None)
    assert ctx.shock_state is None


@pytest.mark.parametrize("label", [None, "SHOCK", "RECOVERY"])
def test_the_short_attach_forwards_the_context_label(monkeypatch, label):
    calls = _capture_attach(monkeypatch)
    qualify._attach_plan(_item(), short_run._bare_context({}, shock_state=label))
    assert calls == [label]


def test_the_bare_context_defaults_to_no_label():
    assert short_run._bare_context({}).shock_state is None


def test_the_lane_state_reads_the_stored_label_once(monkeypatch):
    reads = []
    monkeypatch.setattr(shock_scan, "current_label", lambda **k: reads.append(k) or "SHOCK")
    lane = short_run._lane_state(*_lane_inputs(monkeypatch), "regime")
    assert reads == [{}]
    assert lane == {"sector_of": {"AAA": "Tech"}, "etf_symbol_of": {"Tech": "XLK"},
                    "sector_frames": {"XLK": "frame"}, "spy": "spy", "regime": "regime",
                    "regimes": "series", "shock_state": "SHOCK"}


def test_under_off_the_lane_carries_no_label(monkeypatch):
    monkeypatch.setattr(config, "MARKET_SHOCK_MODE", "off")
    lane = short_run._lane_state(*_lane_inputs(monkeypatch), None)
    assert lane["shock_state"] is None
    assert short_run._qualify_context(False, {}, lane).shock_state is None


@pytest.mark.parametrize("lane,expected", [({**LANE, "shock_state": "RECOVERY"}, "RECOVERY"),
                                           ({**LANE, "shock_state": None}, None),
                                           (LANE, None)])
def test_the_qualify_context_takes_the_label_from_the_lane(lane, expected):
    assert short_run._qualify_context(False, {}, lane).shock_state == expected


def test_the_short_requote_rebuild_keeps_the_label(monkeypatch):
    calls = _capture_attach(monkeypatch)

    def rebuild(item, price, *, rescenario, attach):
        attach("rebuilt")
        return RebuildOutcome(True, None, price)

    monkeypatch.setattr(short_run.rebuild, "rebuild_before_post", rebuild)
    item = _item()
    out = short_run._rebuild_fn({}, short_run._bare_context({}, shock_state="SHOCK"))(item, PRICE)
    assert out.kept and item.plan == "rebuilt" and calls == ["SHOCK"]


def _functions(module):
    tree = ast.parse(inspect.getsource(module))
    return {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}


def _calls(node, name):
    return [c for c in ast.walk(node) if isinstance(c, ast.Call)
            and name in (getattr(c.func, "attr", None), getattr(c.func, "id", None))]


def test_the_label_is_read_once_per_short_run_and_only_at_the_lane_entry():
    fns = _functions(short_run)
    readers = [name for name, fn in fns.items() if _calls(fn, "current_label")]
    assert readers == ["_lane_state"]
    assert len(_calls(fns["_lane_state"], "current_label")) == 1
    assert len(_calls(fns["_sync_run_short_scan"], "_lane_state")) == 1


def test_planning_never_reads_the_shock_store():
    source = inspect.getsource(qualify)
    assert "shock_scan" not in source and "market_shock" not in source


def test_replay_contexts_never_carry_a_label():
    for call in _calls(ast.parse(inspect.getsource(scan_replay)), "QualifyContext"):
        assert "shock_state" not in {k.arg for k in call.keywords}

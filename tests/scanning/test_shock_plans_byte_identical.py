"""v209 spec: long and short plans are byte-identical under MARKET_SHOCK_MODE=off
and shadow, apart from entry_context.shock_state (index Review Focus 3), and a
shock pass that raises or cannot reach its store changes no long plan (index
Global Constraints, LONG issuing unchanged (c)).

Every lane -- confluence, its requote rebuild, strategy, SHORT, the SHORT lane
dict route and the SHORT requote rebuild -- is built three ways: the pre-v209
call (no label argument), `off` (label None) and `shadow` (a label). `off`
must equal pre-v209 byte for byte with no key; `shadow` must equal it once
its one shock_state key is removed."""
import dataclasses
import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from swingbot import config
from swingbot.core.edge.context import FEATURE_KEYS
from swingbot.core.planning import params
from swingbot.core.planning.rebuild import RebuildOutcome, RebuildPrice
from swingbot.core.scanning import (analyze, fetch, qualify, scan_run, shock_scan, short_run,
                                    strategy_pass)
from tests.helpers import make_ohlcv
from tests.scanning.test_live_context_stamp import _plan
from tests.scanning.test_short_qualify import (  # noqa: F401  (offline, sealed, autouse are fixtures)
    CANDIDATE, GOLDEN_KEPT, _context, _items, _lane, _no_notice_queue_write, _stock, offline,
    sealed)

PRICE = RebuildPrice(101.0, "trade", 1.0, "2026-11-05T15:00:00+00:00", 1000.0, True, "regular")
FRAME = make_ohlcv([100.0 + i * 0.1 for i in range(300)], start="2025-06-02")
RS = {"rs_pctile": 64.0, "sector_pctile": 55.0, "rs_combined": 61.0}
ARMS = {"pre_v209": {}, "off": {"shock_state": None}, "shadow": {"shock_state": "SHOCK"}}
# A fresh uuid per build and the live wall clock: they differ between any two
# builds, v209 or not, so they are the only fields left out of the comparison.
VOLATILE = ("plan_id", "issued_at")


def _canon(plan) -> str:
    doc = dataclasses.asdict(plan)
    for key in VOLATILE:
        doc.pop(key, None)
    return json.dumps(doc, sort_keys=True, default=str)


def _assert_pinned(build, *, features=True):
    plans = {arm: build(dict(kwargs)) for arm, kwargs in ARMS.items()}
    assert all(plan is not None for plan in plans.values()), plans
    for arm in ("pre_v209", "off"):
        assert "shock_state" not in plans[arm].entry_context, arm
    if features:
        assert set(plans["off"].entry_context) == set(FEATURE_KEYS)
    assert _canon(plans["off"]) == _canon(plans["pre_v209"])
    assert plans["shadow"].entry_context.pop("shock_state") == "SHOCK"
    assert _canon(plans["shadow"]) == _canon(plans["pre_v209"])
    return plans


def _long_plan():
    return dataclasses.replace(_plan(), stop_loss=98.5)


def _long_item():
    return SimpleNamespace(
        result=SimpleNamespace(ticker="AAPL", horizon_key="3m", trend="bullish",
                               state_key="k", state_value="v"),
        level_map=None, rs_percentile=64.0, breadth=None, htf_info=None, rs_combined=61.0,
        sector_rs_percentile=55.0, conf=None, htf_bias=None, target_confluence=None,
        plan_v2=None, plan_v2_rejected=None, plan="scenario")


@pytest.fixture
def long_env(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    monkeypatch.setattr(analyze, "_build_quality_inputs", lambda *a, **k: {})
    monkeypatch.setattr(analyze, "build_confluence_plan", lambda *a, **k: _long_plan())
    monkeypatch.setattr(analyze, "primary_strategy_for", lambda scenario: "MACD")


def _attach_on_rebuild(monkeypatch, module, scenario_of):
    def rebuild(item, price, *, rescenario, attach):
        attach(scenario_of(item))
        return RebuildOutcome(True, None, price)

    monkeypatch.setattr(module.rebuild, "rebuild_before_post", rebuild)


def test_the_confluence_long_plan_is_pinned(long_env):
    def build(kwargs):
        item = _long_item()
        scan_run._attach_item_plan(item, "scenario", FRAME, None, None, **kwargs)
        return item.plan_v2

    _assert_pinned(build)


def test_the_confluence_requote_rebuild_is_pinned(long_env, monkeypatch):
    _attach_on_rebuild(monkeypatch, scan_run, lambda item: "rebuilt")

    def build(kwargs):
        item = _long_item()
        out = scan_run._rebuild_item(item, PRICE, fresh_data={"AAPL": FRAME}, regimes=None,
                                     regime=None, require_confirmation=True, **kwargs)
        assert out.kept
        return item.plan_v2

    _assert_pinned(build)


def test_the_strategy_long_plan_is_pinned(monkeypatch):
    monkeypatch.setattr(strategy_pass, "build_strategy_plan", lambda *a, **k: _long_plan())
    monkeypatch.setattr(strategy_pass, "stamp_badge", lambda plan: None)
    monkeypatch.setattr(strategy_pass, "stamp_cohort", lambda plan, state: None)

    def build(kwargs):
        # what scan_run's asof_of hands the pass (V209-7): RS readings + shock_asof
        asof = {**RS, **params.shock_asof(kwargs["shock_state"])} if kwargs else dict(RS)
        return strategy_pass.build_strategy_plan_at(
            FRAME, ticker="AAPL", strategy="MACD", horizon_key="3m", direction="bullish",
            regime2_state="bull_quiet", asof=asof)

    _assert_pinned(build)


def test_the_short_plan_is_pinned_and_keeps_its_golden_prices(sealed):  # noqa: F811
    def build(kwargs):
        verdict = qualify.qualify_short_item(CANDIDATE, _items()[0], _context(**kwargs))
        assert isinstance(verdict, qualify.Accepted), verdict
        return verdict.item.plan_v2

    off = _assert_pinned(build, features=False)["off"]
    assert (round(off.trigger_price, 6), round(off.stop_loss, 6), round(off.tp1, 6)) == GOLDEN_KEPT[0][2]


def test_the_short_lane_dict_route_is_pinned(offline):  # noqa: F811
    def build(kwargs):
        kept = short_run._qualified_items(_items(), False, {"AAA": _stock()}, {**_lane(), **kwargs})
        return next(item.plan_v2 for item in kept if item.plan_v2 is not None)

    _assert_pinned(build, features=False)


def test_the_short_requote_rebuild_is_pinned(sealed, monkeypatch):  # noqa: F811
    _attach_on_rebuild(monkeypatch, short_run, lambda item: item.plan)

    def build(kwargs):
        item = _items()[0]
        out = short_run._rebuild_fn({"AAA": _stock()}, _context(**kwargs))(item, PRICE)
        assert out.kept
        return item.plan_v2

    _assert_pinned(build, features=False)


NOW = datetime(2026, 11, 5, 15, 0, tzinfo=timezone.utc)   # 10:00 ET, NYSE regular session


class _DeadStore:
    def current_state(self, *, conn=None):
        raise RuntimeError("db down")

    latest_reading = current_state

    def record(self, *args, **kwargs):
        raise RuntimeError("db down")


def _label(monkeypatch, failure, step):
    """The label _sync_run_scan would stamp, taken through the real call-site wrapper."""
    monkeypatch.setattr(config, "MARKET_SHOCK_MODE", "shadow")
    monkeypatch.setattr(shock_scan.tape, "read_tape", lambda symbols: {})
    monkeypatch.setattr(shock_scan.asset_class, "classify", lambda t: "equity")
    monkeypatch.setattr(fetch, "_fetch_live_prices",
                        lambda tickers, progress=None: pytest.fail("the shock pass fetched quotes"))
    if failure == "pass_raises":
        def boom(**kwargs):
            raise RuntimeError("shock pass blew up")
        monkeypatch.setattr(shock_scan, "run_shock_pass", boom)
    elif failure == "stub_none":
        monkeypatch.setattr(shock_scan, "run_shock_pass", lambda **kwargs: None)
    return scan_run._shock_state_for_pass(
        step_shock=step, frames={"AAPL": FRAME}, live_prices={"AAPL": 101.0},
        sector_of={"AAPL": "Information Technology"}, quotes_at=NOW, spy_df=None, now=NOW,
        repo=_DeadStore())


def _confluence(state):
    item = _long_item()
    scan_run._attach_item_plan(item, "scenario", FRAME, None, None, shock_state=state)
    return item.plan_v2


def _requote(state):
    item = _long_item()
    out = scan_run._rebuild_item(item, PRICE, fresh_data={"AAPL": FRAME}, regimes=None,
                                 regime=None, require_confirmation=True, shock_state=state)
    assert out.kept
    return item.plan_v2


@pytest.mark.parametrize("failure,step", [
    ("pass_raises", True), ("pass_raises", False), ("store_down", True), ("store_down", False)])
@pytest.mark.parametrize("lane", ["confluence", "requote"])
def test_a_failed_shock_pass_leaves_long_plans_byte_identical(long_env, monkeypatch,
                                                              failure, step, lane):
    _attach_on_rebuild(monkeypatch, scan_run, lambda item: "rebuilt")
    build = {"confluence": _confluence, "requote": _requote}[lane]
    with monkeypatch.context() as m:
        failed_label = _label(m, failure, step)
    with monkeypatch.context() as m:
        stub_label = _label(m, "stub_none", step)
    assert failed_label is None and stub_label is None
    failed, stubbed = build(failed_label), build(stub_label)
    assert "shock_state" not in failed.entry_context
    assert _canon(failed) == _canon(stubbed)

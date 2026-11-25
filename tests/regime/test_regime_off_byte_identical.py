"""v239 index Global Constraints: under BEAR_REGIME_MODE=off nothing changes.

Every lane (confluence, its requote rebuild, strategy, SHORT, the SHORT lane dict
route, the SHORT requote rebuild) is built three ways: the pre-v239 call (no day
argument), `off` (day None) and `shadow` (a CORRECTION + stress day). `off` must
equal pre-v239 byte for byte with no regime key; `shadow` must equal it once its
two keys are removed. An `off` (or unknown) mode fetches nothing and never opens
the market_regime_days store. Embed bytes are pinned in test_regime_embeds.py."""
from datetime import date

import pytest

from swingbot import config
from swingbot.core.edge.context import FEATURE_KEYS
from swingbot.core.market import bear_regime as br
from swingbot.core.planning import params
from swingbot.core.scanning import analyze, qualify, regime_scan, scan_run, short_run, strategy_pass
from tests.scanning.test_shock_plans_byte_identical import (FRAME, PRICE, RS, _attach_on_rebuild,
                                                            _canon, _long_item, _long_plan)
from tests.scanning.test_shock_short_lane import _lane_inputs
from tests.scanning.test_short_qualify import (  # noqa: F401  (offline, sealed, autouse are fixtures)
    CANDIDATE, _context, _items, _lane, _no_notice_queue_write, _stock, offline, sealed)

DAY = br.RegimeDay(session_date=date(2026, 11, 19), last_bar_date=date(2026, 11, 18),
                   state=br.CORRECTION, stress=True)
ARMS = {"pre_v239": {}, "off": {"regime_day": None}, "shadow": {"regime_day": DAY}}
REGIME_KEYS = {"bear_regime", "regime_action"}


def _assert_pinned(build, action, *, features=True):
    plans = {arm: build(dict(kwargs)) for arm, kwargs in ARMS.items()}
    assert all(plan is not None for plan in plans.values()), plans
    for arm in ("pre_v239", "off"):
        assert not REGIME_KEYS & set(plans[arm].entry_context), arm
    if features:
        assert set(plans["off"].entry_context) == set(FEATURE_KEYS)
    assert _canon(plans["off"]) == _canon(plans["pre_v239"])
    ctx = plans["shadow"].entry_context
    assert (ctx.pop("bear_regime"), ctx.pop("regime_action")) == ("CORRECTION", action)
    assert _canon(plans["shadow"]) == _canon(plans["pre_v239"])


@pytest.fixture
def long_env(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    monkeypatch.setattr(analyze, "_build_quality_inputs", lambda *a, **k: {})
    monkeypatch.setattr(analyze, "build_confluence_plan", lambda *a, **k: _long_plan())
    monkeypatch.setattr(analyze, "primary_strategy_for", lambda scenario: "MACD")


def test_the_confluence_long_plan_is_pinned(long_env):
    def build(kwargs):
        item = _long_item()
        scan_run._attach_item_plan(item, "scenario", FRAME, None, None, **kwargs)
        return item.plan_v2

    _assert_pinned(build, "would_veto")


def test_the_confluence_requote_rebuild_is_pinned(long_env, monkeypatch):
    _attach_on_rebuild(monkeypatch, scan_run, lambda item: "rebuilt")

    def build(kwargs):
        item = _long_item()
        out = scan_run._rebuild_item(item, PRICE, fresh_data={"AAPL": FRAME}, regimes=None,
                                     regime=None, require_confirmation=True, **kwargs)
        assert out.kept
        return item.plan_v2

    _assert_pinned(build, "would_veto")


def test_the_strategy_long_plan_is_pinned(monkeypatch):
    monkeypatch.setattr(strategy_pass, "build_strategy_plan", lambda *a, **k: _long_plan())
    monkeypatch.setattr(strategy_pass, "stamp_badge", lambda plan: None)
    monkeypatch.setattr(strategy_pass, "stamp_cohort", lambda plan, state: None)

    def build(kwargs):
        # what scan_run's asof_of hands the pass: RS readings + regime_asof
        asof = {**RS, **params.regime_asof(kwargs["regime_day"])} if kwargs else dict(RS)
        return strategy_pass.build_strategy_plan_at(
            FRAME, ticker="AAPL", strategy="MACD", horizon_key="3m", direction="bullish",
            regime2_state="bull_quiet", asof=asof)

    _assert_pinned(build, "would_veto")


def test_the_short_plan_is_pinned(sealed):  # noqa: F811
    def build(kwargs):
        verdict = qualify.qualify_short_item(CANDIDATE, _items()[0], _context(**kwargs))
        assert isinstance(verdict, qualify.Accepted), verdict
        return verdict.item.plan_v2

    _assert_pinned(build, "aligned", features=False)


def test_the_short_lane_dict_route_is_pinned(offline):  # noqa: F811
    def build(kwargs):
        kept = short_run._qualified_items(_items(), False, {"AAA": _stock()}, {**_lane(), **kwargs})
        return next(item.plan_v2 for item in kept if item.plan_v2 is not None)

    _assert_pinned(build, "aligned", features=False)


def test_the_short_requote_rebuild_is_pinned(sealed, monkeypatch):  # noqa: F811
    _attach_on_rebuild(monkeypatch, short_run, lambda item: item.plan)

    def build(kwargs):
        item = _items()[0]
        out = short_run._rebuild_fn({"AAA": _stock()}, _context(**kwargs))(item, PRICE)
        assert out.kept
        return item.plan_v2

    _assert_pinned(build, "aligned", features=False)


def _no_io(monkeypatch):
    monkeypatch.setattr(regime_scan, "get_daily_data",
                        lambda *a, **k: pytest.fail("the regime pass fetched under off"))
    monkeypatch.setattr(regime_scan, "market_regime_repo",
                        lambda: pytest.fail("the regime pass opened its store under off"))


@pytest.mark.parametrize("mode", ["off", "OFF", "bogus", ""])
def test_off_fetches_nothing_and_never_opens_the_store(monkeypatch, mode):
    monkeypatch.setattr(config, "BEAR_REGIME_MODE", mode)
    _no_io(monkeypatch)
    assert regime_scan.regime_for_pass() is None


def test_off_short_lane_carries_no_day_and_touches_nothing(monkeypatch):
    _no_io(monkeypatch)
    monkeypatch.setattr(short_run.shock_scan, "current_label", lambda **k: None)
    lane = short_run._lane_state(*_lane_inputs(monkeypatch), None)
    assert lane["regime_day"] is None
    assert short_run._qualify_context(False, {}, lane).regime_day is None

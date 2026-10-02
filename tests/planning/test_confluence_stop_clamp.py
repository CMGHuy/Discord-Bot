"""v115: build_confluence_plan clamps a stop beyond the 2% hard cap to 1.75%
(2% cap less CLAMP_HEADROOM_PCT) from the trigger, BEFORE target selection, so tp1 pays the min R:R against
the clamped risk. Spec: docs/superpowers/specs/2026-09-30-v115-restore-sep22-issuance-design.md"""
import dataclasses
import types

import pytest

from swingbot import config
from swingbot.core.market import levels
from swingbot.core.planning import builders
from swingbot.core.planning.plan_types import PlanStatus
from swingbot.core.planning.plan_engine import build_confluence_plan
from swingbot.core.risk_limits import HARD_MAX_PLANNED_LOSS_PCT, planned_loss_pct
from swingbot.scan_params import ScanParams
from tests.helpers import make_ohlcv


def _params():
    return dataclasses.replace(ScanParams.from_config(),
                               min_risk_reward_ratio=1.5, max_risk_reward_ratio=2.5)


def _scenario(direction, entry, stop_loss, take_profit):
    return types.SimpleNamespace(
        direction=direction, entry=entry, stop_loss=stop_loss, take_profit=take_profit,
        target_sources=["Rolling S/R"], stop_sources=["Rolling S/R"])


def _build(scenario, level_map=None):
    return build_confluence_plan(
        scenario, make_ohlcv([scenario.entry] * 60), ticker="XYZ", horizon_key="4w",
        primary_strategy="S/R Confluence", level_map=level_map, params=_params())


@pytest.fixture
def clamp_on(monkeypatch):
    monkeypatch.setattr(config, "CLAMP_STOP_TO_HARD_CAP", True)


def test_long_four_percent_stop_is_clamped_inside_the_cap(clamp_on):
    plan = _build(_scenario("bullish", 100.0, 96.0, 104.0))
    assert plan is not None
    assert plan.stop_loss == pytest.approx(98.25)
    assert plan.tp1 == pytest.approx(104.0)
    assert (plan.tp1 - 100.0) / (100.0 - plan.stop_loss) >= 1.5 - 1e-9


def test_short_four_percent_stop_is_clamped_inside_the_cap(clamp_on):
    plan = _build(_scenario("bearish", 100.0, 104.0, 96.0))
    assert plan is not None
    assert plan.stop_loss == pytest.approx(101.75)
    assert plan.tp1 == pytest.approx(96.0)
    assert (100.0 - plan.tp1) / (plan.stop_loss - 100.0) >= 1.5 - 1e-9


def test_target_is_chosen_against_the_clamped_risk(clamp_on):
    # Clamped risk 1.75 -> band [102.625, 104.375]: the nearest qualifying level is 103.
    # Unclamped (risk 5) the floor would be 107.5 and tp1 would be 112.
    resistances = [levels.Level(p, ["Fibonacci"]) for p in (103.0, 104.5, 112.0)]
    supports = [levels.Level(90.0, ["Rolling S/R"])]
    plan = _build(_scenario("bullish", 100.0, 95.0, 112.0), level_map=(supports, resistances))
    assert plan.stop_loss == pytest.approx(98.25)
    assert plan.tp1 == pytest.approx(103.0)


def test_no_target_paying_min_rr_at_the_clamped_risk_returns_none(clamp_on):
    # 102.5 is 1.43R against the clamped 1.75% risk: the existing no_qualifying_target path.
    assert _build(_scenario("bullish", 100.0, 96.0, 102.5)) is None


def test_a_stop_within_the_cap_is_untouched(clamp_on):
    plan = _build(_scenario("bullish", 100.0, 98.5, 103.0))
    assert plan.stop_loss == 98.5


def test_a_stop_between_the_clamp_target_and_the_cap_is_untouched(clamp_on):
    """1.9% is past the 1.75% the clamp lands on but inside the 2% cap, so
    the clamp never fires -- it only pulls in stops that break the cap."""
    plan = _build(_scenario("bullish", 100.0, 98.1, 104.0))
    assert plan.stop_loss == 98.1


def test_a_stop_exactly_at_the_cap_is_untouched(clamp_on):
    plan = _build(_scenario("bullish", 100.0, 98.0, 104.0))
    assert plan.stop_loss == 98.0


def test_flag_off_restores_the_unclamped_stop(monkeypatch):
    monkeypatch.setattr(config, "CLAMP_STOP_TO_HARD_CAP", False)
    plan = _build(_scenario("bullish", 100.0, 96.0, 108.0))
    assert plan.stop_loss == 96.0
    assert plan.tp1 == pytest.approx(108.0)


def test_clamped_plan_never_exceeds_the_attach_safety_net(clamp_on):
    # GC=F 2026-09-28 prices: a clamped plan must never trip the f01e87e2 reject.
    plan = _build(_scenario("bearish", 4194.30, 4278.68, 4066.11))
    assert plan is not None
    assert planned_loss_pct(plan.trigger_price, plan.stop_loss) <= HARD_MAX_PLANNED_LOSS_PCT


def test_helper_leaves_an_invalid_entry_alone(clamp_on):
    assert builders._clamp_stop_to_hard_cap(0.0, 5.0, True) == 5.0


def test_helper_leaves_a_missing_stop_alone(clamp_on):
    assert builders._clamp_stop_to_hard_cap(100.0, None, True) is None


@pytest.mark.parametrize("is_bull,stop", [(True, 100.0), (True, 103.0), (False, 100.0), (False, 97.0)])
def test_helper_leaves_a_wrong_side_stop_alone(clamp_on, is_bull, stop):
    # long stop >= entry / short stop <= entry is not a stop beyond the cap.
    assert builders._clamp_stop_to_hard_cap(100.0, stop, is_bull) == stop


@pytest.mark.parametrize("entry", [4194.30, 0.3071, 57.77, 1234.5678])
@pytest.mark.parametrize("is_bull", [True, False])
def test_clamped_stop_is_strictly_inside_the_cap_at_non_round_entries(clamp_on, entry, is_bull):
    wide = entry * (0.9 if is_bull else 1.1)
    stop = builders._clamp_stop_to_hard_cap(entry, wide, is_bull)
    assert planned_loss_pct(entry, stop) < HARD_MAX_PLANNED_LOSS_PCT
    assert planned_loss_pct(entry, stop) == pytest.approx(
        HARD_MAX_PLANNED_LOSS_PCT - builders.CLAMP_HEADROOM_PCT)


def test_clamped_plan_survives_a_fill_slightly_past_the_trigger(clamp_on, tmp_path, monkeypatch):
    # PlanManager._step_pending checks the FILL price against the 2% cap with no
    # tolerance; the 0.25% headroom is what lets a stop-entry fill a little past
    # the trigger stay ACTIVE.
    from tests.fake_feed import FakePriceFeed
    from tests.planning.test_plan_manager_pending import _mgr

    monkeypatch.setattr(config, "INTRADAY_RTH_ONLY", False)
    monkeypatch.setattr(config, "STRUCTURAL_STOP_SCOPE", "", raising=False)
    outcomes = {}
    for fill in (100.0, 100.2, 101.0):
        plan = _build(_scenario("bullish", 100.0, 96.0, 104.0))
        plan.entry_type, plan.status, plan.entry_price = "stop_entry", PlanStatus.PENDING, None
        store, mgr = _mgr(tmp_path / str(fill), FakePriceFeed([("XYZ", fill)]))
        (tmp_path / str(fill)).mkdir()
        store.add(plan)
        mgr.poll()
        outcomes[fill] = store.get(plan.plan_id)
    assert outcomes[100.0].status == PlanStatus.ACTIVE
    assert outcomes[100.2].status == PlanStatus.ACTIVE
    # A fill 1% past the trigger is 2.75% from the 98.25 stop: cancelled risk_cap.
    # That is the 2% policy working as designed, not a clamp defect.
    assert outcomes[101.0].status == PlanStatus.CANCELLED
    assert outcomes[101.0].status_history[-1]["reason"] == "risk_cap"

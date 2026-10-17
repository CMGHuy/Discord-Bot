"""v136 phases 1-2: the instrument contract (v157 sets v2's fills and costs)."""
import dataclasses

import pytest

from swingbot.core.backtesting.instrument import contract
from swingbot.core.backtesting.instrument.contract import (CostModel, FillModel, InstrumentSpec,
                                                           resolve)


def test_v1_is_todays_behaviour_and_keeps_its_own_plan_path():
    spec = resolve("v1")
    assert spec.version == "v1"
    assert spec.live_constructor is False
    assert spec.fill_model == FillModel(market_entry="signal_close", gap_through=False,
                                        same_bar="stop_first")
    assert spec.cost_model == CostModel(commission_per_share=0.0, slippage_bps=0.0,
                                        stop_slippage_bps=0.0)


def test_v2_builds_through_the_live_constructor():
    assert resolve("v2").version == "v2"
    assert resolve("v2").live_constructor is True


def test_v2_carries_spec_section_two_fills_and_costs():
    spec = resolve("v2")
    assert spec.fill_model == FillModel(market_entry="next_open", gap_through=True,
                                        same_bar="stop_first")
    assert spec.cost_model == CostModel(commission_per_share=0.0, slippage_bps=5.0,
                                        stop_slippage_bps=10.0)
    assert spec.fill_model is contract.V2_FILLS
    assert spec.cost_model is contract.V2_COSTS


def test_v1_keeps_its_own_constants_untouched():
    assert resolve("v1").fill_model is contract.V1_FILLS
    assert resolve("v1").cost_model is contract.ZERO_COSTS
    assert contract.V2_FILLS != contract.V1_FILLS
    assert contract.V2_COSTS != contract.ZERO_COSTS


def test_fill_and_cost_models_keep_their_phase_one_fields():
    """v157 adds no field: the three of each carry every spec section 2 rule."""
    assert [f.name for f in dataclasses.fields(FillModel)] == [
        "market_entry", "gap_through", "same_bar"]
    assert [f.name for f in dataclasses.fields(CostModel)] == [
        "commission_per_share", "slippage_bps", "stop_slippage_bps"]


def test_unknown_version_is_refused():
    with pytest.raises(ValueError, match="unknown instrument 'v3'"):
        resolve("v3")


def test_specs_are_frozen():
    with pytest.raises(dataclasses.FrozenInstanceError):
        resolve("v1").version = "v2"


def test_phase_one_carries_no_span_fields():
    """Phase 3 adds research/holdout spans, universe and folds and updates this."""
    assert [f.name for f in dataclasses.fields(InstrumentSpec)] == [
        "version", "fill_model", "cost_model"]


def test_versions_lists_every_resolvable_instrument():
    assert contract.VERSIONS == ("v1", "v2")
    assert all(resolve(v).version == v for v in contract.VERSIONS)

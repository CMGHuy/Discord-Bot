"""v136 phase 1: the instrument contract skeleton (fill/cost fields only)."""
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


def test_phase_one_v2_stub_carries_v1_fills_and_costs():
    """Phase 2 sets v2's values from spec section 2 and rewrites this test."""
    assert resolve("v2").fill_model == resolve("v1").fill_model
    assert resolve("v2").cost_model == resolve("v1").cost_model


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

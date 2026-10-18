"""v136 instrument contract: fill/cost fields (phases 1-2) and the window,
universe, fold and liquidity-floor fields (phase 3, v158)."""
import dataclasses

import pytest

from swingbot.core.backtesting.instrument import contract
from swingbot.core.backtesting.instrument.contract import (V2_LIQUIDITY_FLOOR, CostModel,
                                                           FillModel, InstrumentSpec,
                                                           LiquidityFloor, resolve)


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


SPAN_FIELDS = ["universe", "research_start", "research_end", "holdout_start", "fold_scheme",
               "fold_test_years", "purge", "embargo_days", "train_window", "validation_window",
               "warmup_start", "liquidity_floor"]


def test_span_fields_are_appended_after_the_fill_and_cost_fields():
    """Keyword-with-default fields after cost_model: the positional _SPECS lines
    (and v157's rewrite of the v2 one) never have to change."""
    assert [f.name for f in dataclasses.fields(InstrumentSpec)] == [
        "version", "fill_model", "cost_model", *SPAN_FIELDS]
    defaulted = {f.name for f in dataclasses.fields(InstrumentSpec)
                 if f.default is not dataclasses.MISSING}
    assert defaulted == set(SPAN_FIELDS)


def test_versions_lists_every_resolvable_instrument():
    assert contract.VERSIONS == ("v1", "v2")
    assert all(resolve(v).version == v for v in contract.VERSIONS)


def test_v1_window_fields_are_todays_literal_windows():
    """Partner decision 4: v1's TRAIN/VALIDATION live in the contract, unchanged."""
    spec = resolve("v1")
    assert spec.train_window == ("2020-01-01", "2023-12-31")
    assert spec.validation_window == ("2024-01-01", "2025-12-31")
    assert spec.research_span == ("2020-01-01", "2023-12-31")
    assert spec.holdout_start == "2024-01-01"


def test_v1_carries_no_universe_folds_floor_or_warmup():
    spec = resolve("v1")
    assert spec.universe is None
    assert spec.fold_scheme == "none"
    assert spec.fold_test_years == ()
    assert spec.purge is False
    assert spec.embargo_days == 0
    assert spec.warmup_start is None
    assert spec.liquidity_floor is None


def test_v1_spec_equals_a_spec_built_from_defaults_only():
    """The v1 line passes no span argument: every v1 value is a field default."""
    v1 = resolve("v1")
    assert v1 == InstrumentSpec("v1", v1.fill_model, v1.cost_model)


def test_v2_spans_are_the_spec_section_one_values():
    spec = resolve("v2")
    assert spec.universe == "sp500_pit"
    assert spec.research_span == ("2010-01-01", "2025-12-31")
    assert spec.holdout_start == "2026-01-01"
    assert spec.warmup_start == "2009-06-01"
    assert spec.train_window is None
    assert spec.validation_window is None


def test_v2_folds_are_twelve_yearly_test_years_with_four_training_years_first():
    spec = resolve("v2")
    assert spec.fold_scheme == "anchored_yearly"
    assert spec.fold_test_years == tuple(range(2014, 2026))
    assert len(spec.fold_test_years) == 12
    first_research_year = int(spec.research_start[:4])
    assert spec.fold_test_years[0] - first_research_year >= 4
    assert spec.fold_test_years[-1] == int(spec.research_end[:4])


def test_v2_purges_and_embargoes_by_the_longest_horizon():
    """Partner decision 2: the field is the global maximum holding period."""
    from swingbot.core.market.strategy_types import HORIZONS, LEGACY_HORIZONS
    spec = resolve("v2")
    assert spec.purge is True
    assert spec.embargo_days == max(HORIZONS[hk]["max_holding_days"] for hk in LEGACY_HORIZONS)
    assert spec.embargo_days == 270


def test_v2_liquidity_floor_is_the_frozen_live_default():
    """Partner decision 1: $20M average dollar volume, $5 close, 20 bars, frozen."""
    assert resolve("v2").liquidity_floor is V2_LIQUIDITY_FLOOR
    assert V2_LIQUIDITY_FLOOR == LiquidityFloor(min_avg_dollar_vol=20_000_000.0, min_price=5.0,
                                                lookback_bars=20)
    with pytest.raises(dataclasses.FrozenInstanceError):
        V2_LIQUIDITY_FLOOR.min_price = 1.0


def test_v2_keeps_its_fill_cost_and_constructor_fields_through_the_replace():
    """The dataclasses.replace after _SPECS touches only the phase-3 fields."""
    spec = resolve("v2")
    assert spec.version == "v2"
    assert spec.live_constructor is True
    assert spec.fill_model == contract.V1_FILLS or spec.fill_model.market_entry == "next_open"


def test_research_span_ends_before_the_holdout_for_every_instrument():
    for version in contract.VERSIONS:
        spec = resolve(version)
        start, end = spec.research_span
        assert start < end < spec.holdout_start

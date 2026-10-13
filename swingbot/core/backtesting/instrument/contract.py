"""The backtest instrument contract (v136 spec, "Architecture").

``resolve(version)`` is the ONLY place an instrument's rules are defined.
Callers receive an ``InstrumentSpec`` and pass it down
(``run_backtest(..., instrument=spec)``); nothing reads a module-level
"current instrument".

Phase 1 (v137) shipped the fill/cost fields and the plan constructor
(``InstrumentSpec.live_constructor``). Phase 2 (v157) sets v2's fill and cost
values from spec section 2 (``V2_FILLS``, ``V2_COSTS``): they are read by
``instrument/fills.py`` and ``instrument/costs.py`` through
``planning/exit_sim_v2.py``, and are frozen at cutover -- a change to them is
a new instrument version. Phase 3 adds the span, universe and fold fields.
v1 is frozen: a change to its values breaks
tests/backtesting/instrument/test_v1_golden.py, which is the point.

v1's ``cost_model`` is zero because no v1 path books a contract cost. The legacy
v1 exit loop's own friction (``run_backtest(frictions=True)``,
``edge/frictions.py``) is frozen v1 code that predates this contract and is not
expressed here (spec section 2, "Scope").
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FillModel:
    """How a planned price becomes a fill."""

    market_entry: str   # "signal_close" (v1) | "next_open" (v2)
    gap_through: bool   # a bar opening beyond a stop/target fills at the open
    same_bar: str       # a bar containing both stop and target: "stop_first"


@dataclass(frozen=True)
class CostModel:
    """Per-trade costs, converted to R once at booking (instrument/costs.py)."""

    commission_per_share: float
    slippage_bps: float        # entries, limit and target exits
    stop_slippage_bps: float   # stop exits (market-on-trigger)


@dataclass(frozen=True)
class InstrumentSpec:
    """One backtest instrument. Phase 1: version, fills, costs."""

    version: str
    fill_model: FillModel
    cost_model: CostModel

    @property
    def live_constructor(self) -> bool:
        """Every plan is built by builders.build_strategy_plan (v136 rule 3).
        False only for the frozen v1 instrument."""
        return self.version != "v1"


V1_FILLS = FillModel(market_entry="signal_close", gap_through=False, same_bar="stop_first")
ZERO_COSTS = CostModel(commission_per_share=0.0, slippage_bps=0.0, stop_slippage_bps=0.0)

# Spec section 2: market entries at the next open, gaps fill at the open in
# both directions, stop first on a bar holding both levels; $0/share, 5 bps on
# entries and target/close exits, 10 bps on stop exits.
V2_FILLS = FillModel(market_entry="next_open", gap_through=True, same_bar="stop_first")
V2_COSTS = CostModel(commission_per_share=0.0, slippage_bps=5.0, stop_slippage_bps=10.0)

_SPECS = {
    "v1": InstrumentSpec("v1", V1_FILLS, ZERO_COSTS),
    "v2": InstrumentSpec("v2", V2_FILLS, V2_COSTS),
}
VERSIONS = tuple(_SPECS)


def resolve(version: str) -> InstrumentSpec:
    """The InstrumentSpec for `version`; ValueError for an unknown one."""
    spec = _SPECS.get(version)
    if spec is None:
        raise ValueError(f"unknown instrument {version!r}; known: {', '.join(VERSIONS)}")
    return spec

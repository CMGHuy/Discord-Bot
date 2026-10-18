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
a new instrument version. Phase 3 (v158) appends the span, universe, fold and liquidity-floor fields
after ``cost_model`` as keyword fields whose defaults are v1's values, and
sets v2's with ``dataclasses.replace`` below ``_SPECS``, so neither positional
``_SPECS`` line changes.
v1 is frozen: a change to its values breaks
tests/backtesting/instrument/test_v1_golden.py, which is the point.

v1's ``cost_model`` is zero because no v1 path books a contract cost. The legacy
v1 exit loop's own friction (``run_backtest(frictions=True)``,
``edge/frictions.py``) is frozen v1 code that predates this contract and is not
expressed here (spec section 2, "Scope").
"""
from __future__ import annotations

from dataclasses import dataclass, replace


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
class LiquidityFloor:
    """Causal point-in-time liquidity floor (v158 partner decision 1): the
    average Close*Volume over the `lookback_bars` bars ending AT the signal
    bar, and that bar's close. Frozen here; never read from config."""

    min_avg_dollar_vol: float
    min_price: float
    lookback_bars: int


@dataclass(frozen=True)
class InstrumentSpec:
    """One backtest instrument: fills and costs (phases 1-2), then the window,
    universe, fold and floor fields (phase 3). Every phase-3 field defaults to
    v1's value, so v1's spec is built from its three positional fields alone."""

    version: str
    fill_model: FillModel
    cost_model: CostModel
    # --- phase 3 (v158); defaults are v1 -------------------------------------
    universe: str | None = None             # v2: "sp500_pit"; None = the caller's choice
    research_start: str = "2020-01-01"      # every TRAIN run, grid and fold lies inside
    research_end: str = "2023-12-31"
    holdout_start: str = "2024-01-01"       # first sealed day (v1: its VALIDATION start)
    fold_scheme: str = "none"               # "none" | "anchored_yearly" (folds.py)
    fold_test_years: tuple[int, ...] = ()
    purge: bool = False                     # drop train trades open at the test start
    embargo_days: int = 0                   # global max; folds.embargo_days_for(hk) per horizon
    train_window: tuple[str, str] | None = ("2020-01-01", "2023-12-31")        # v1 only
    validation_window: tuple[str, str] | None = ("2024-01-01", "2025-12-31")   # v1 only
    warmup_start: str | None = None         # first bar the cache must hold (coverage.py)
    liquidity_floor: LiquidityFloor | None = None   # v2: causal floor on the signal date

    @property
    def live_constructor(self) -> bool:
        """Every plan is built by builders.build_strategy_plan (v136 rule 3).
        False only for the frozen v1 instrument."""
        return self.version != "v1"

    @property
    def research_span(self) -> tuple[str, str]:
        """(research_start, research_end), both inclusive ISO dates."""
        return (self.research_start, self.research_end)


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
V2_LIQUIDITY_FLOOR = LiquidityFloor(min_avg_dollar_vol=20_000_000.0, min_price=5.0,
                                    lookback_bars=20)

# v2's window, universe, fold and floor values (spec section 1). Applied here,
# not on the "v2" line above, so phase 2 (v157) and phase 3 never edit one line.
_V2_WINDOW = {
    "universe": "sp500_pit",
    "research_start": "2010-01-01",
    "research_end": "2025-12-31",
    "holdout_start": "2026-01-01",
    "fold_scheme": "anchored_yearly",
    "fold_test_years": tuple(range(2014, 2026)),
    "purge": True,
    "embargo_days": 270,   # 9m max_holding_days, the longest LEGACY_HORIZONS hold
    "train_window": None,
    "validation_window": None,
    "warmup_start": "2009-06-01",
    "liquidity_floor": V2_LIQUIDITY_FLOOR,
}
_SPECS["v2"] = replace(_SPECS["v2"], **_V2_WINDOW)
VERSIONS = tuple(_SPECS)


def resolve(version: str) -> InstrumentSpec:
    """The InstrumentSpec for `version`; ValueError for an unknown one."""
    spec = _SPECS.get(version)
    if spec is None:
        raise ValueError(f"unknown instrument {version!r}; known: {', '.join(VERSIONS)}")
    return spec

"""The v100 ArmEngine seam for pluggable arm populations."""
from __future__ import annotations

from typing import Protocol

from swingbot.core.backtesting.arms.knobs import apply_knobs

DEFAULT_ENGINES = ("confluence", "strategy")


class ArmEngine(Protocol):
    engine_id: str

    def run_ticker(self, ticker: str, df, horizons, signal_window: tuple[str, str],
                   params) -> list: ...


def get_engine(engine_id: str, *, instrument=None) -> ArmEngine:
    """Construct a registered engine without importing inactive engines.
    ``instrument`` (v157): None is v1; any other spec walks every trade under
    its fills and costs (exit_sim.simulate_exit's seam)."""
    if engine_id == "confluence":
        from swingbot.core.backtesting.arms.confluence_engine import ConfluenceEngine
        return ConfluenceEngine(instrument=instrument)
    if engine_id == "strategy":
        from swingbot.core.backtesting.arms.strategy_engine import StrategyEngine
        return StrategyEngine(instrument=instrument)
    raise ValueError(f"unknown engine {engine_id!r}; expected one of {DEFAULT_ENGINES}")


def run_arm(ticker: str, df, engine_ids, horizons, signal_window, delta: dict, *,
            instrument=None) -> list:
    """Run one ticker arm, applying its config globals inside this worker.
    ``instrument`` goes to every engine (get_engine); None is v1."""
    from swingbot.scan_params import ScanParams

    with apply_knobs(delta):
        params = ScanParams.from_config()
        out: list = []
        for engine_id in engine_ids:
            out.extend(get_engine(engine_id, instrument=instrument).run_ticker(
                ticker, df, horizons, signal_window, params))
    return out


# --- v118: whole-scan population engines ---------------------------------------------

class PopulationEngine(Protocol):
    engine_id: str

    def run_population(self, frames: dict, window: tuple[str, str], params, *,
                       mode: str) -> list: ...


def population_engine_for(delta: dict) -> str | None:
    """The population engine a knob delta needs, or None for per-ticker engines."""
    from swingbot.core.backtesting.arms import reachability
    for attr in delta:
        reach = reachability.REGISTRY.get(attr)
        found = sorted(reach.observed_by & reachability.POPULATION_ENGINES) if reach else []
        if found:
            return found[0]
    return None


def get_population_engine(engine_id: str, **kwargs) -> PopulationEngine:
    """Construct a registered population engine; KeyError when none is registered."""
    if engine_id == "short_universe":
        from swingbot.core.backtesting.arms.short_universe_engine import ShortUniverseEngine
        return ShortUniverseEngine(**kwargs)
    raise KeyError(engine_id)

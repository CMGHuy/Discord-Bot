"""The single stage-to-signal-window and width table for v100.

Signal dates are constrained by these windows. Exit simulation may walk past
the window end, matching the existing replay convention.
"""
from __future__ import annotations

from dataclasses import dataclass

from swingbot.core.market.strategy_types import LEGACY_HORIZONS

VALIDATION_START = "2024-01-01"
ALL_HORIZONS: tuple[str, ...] = LEGACY_HORIZONS
PILOT_TICKERS = 10


@dataclass(frozen=True)
class StageSpec:
    name: str
    signal_window: tuple[str, str]
    full_width: bool
    folds: tuple = ()
    fold_key: str = ""
    fold_label_key: str = ""


STAGES: dict[str, StageSpec] = {
    "pilot": StageSpec("pilot", ("2018-06-01", "2020-12-31"), full_width=False),
    "selection": StageSpec(
        "selection", ("2018-06-01", "2022-12-31"), full_width=True,
        folds=(("2020", "2018-06-01", "2020-12-31"),
               ("2021", "2018-06-01", "2021-12-31"),
               ("2022", "2018-06-01", "2022-12-31")),
        fold_key="train_folds", fold_label_key="train_end",
    ),
    "walkforward": StageSpec(
        "walkforward", ("2021-01-01", "2023-12-31"), full_width=True,
        folds=(("2021", "2021-01-01", "2021-12-31"),
               ("2022", "2022-01-01", "2022-12-31"),
               ("2023", "2023-01-01", "2023-12-31")),
        fold_key="folds", fold_label_key="test_year",
    ),
    "validation": StageSpec("validation", (VALIDATION_START, "2025-12-31"), full_width=True),
}

FUNNEL_TO_PRODUCER_STAGE = {
    "reachability": "pilot",
    "mde": "selection",
    "selection": "selection",
    "walkforward": "walkforward",
    "validation": "validation",
}


def resolve(stage: str) -> StageSpec:
    """Return the named producer stage or explain the valid choices."""
    try:
        return STAGES[stage]
    except KeyError:
        raise ValueError(f"unknown stage {stage!r}; expected one of {sorted(STAGES)}") from None


def universe_for(stage: str, cached_universe) -> list[str]:
    """Return the fixed pilot prefix or the complete sorted universe."""
    universe = sorted(cached_universe)
    return universe if resolve(stage).full_width else universe[:PILOT_TICKERS]

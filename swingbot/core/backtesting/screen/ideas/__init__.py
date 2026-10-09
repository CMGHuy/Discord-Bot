"""The v140 idea registry: one frozen trigger per published effect.

A trigger module exports CAP, PARAMS, SUMMARY, SOURCE and events(df). A
changed parameter is a new idea with a new name (and a new ledger row),
never an edit here: each idea is screened once.
"""
from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Callable, Mapping

import pandas as pd

#: Batch order of the spec, and the run order of V140-15..18.
IDEA_MODULES = ("high52w", "uptrend_pullback", "gap_volume", "turn_of_month")


@dataclass(frozen=True)
class Idea:
    name: str
    events: Callable[[pd.DataFrame], pd.Series]
    time_cap_bars: int
    direction: str = "long"
    params: Mapping = field(default_factory=dict)
    summary: str = ""
    source: str = ""

    def __post_init__(self):
        if self.direction != "long":
            raise ValueError(f"{self.name}: v140 screens long ideas only")
        if self.time_cap_bars < 1:
            raise ValueError(f"{self.name}: time cap must be at least one bar")
        object.__setattr__(self, "params", MappingProxyType(dict(self.params)))


def _load(name: str) -> Idea:
    module = importlib.import_module(f"{__name__}.{name}")
    return Idea(name=name, events=module.events, time_cap_bars=module.CAP,
                params=module.PARAMS, summary=module.SUMMARY,
                source=module.SOURCE)


IDEAS: dict[str, Idea] = {name: _load(name) for name in IDEA_MODULES}

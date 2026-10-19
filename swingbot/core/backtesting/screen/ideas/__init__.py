"""The v140 idea registry: one frozen trigger per published effect.

A trigger module exports CAP, PARAMS, SUMMARY, SOURCE and events(df), and
optionally RACE: "fixed" (the default: entry next open, 1.5/3 ATR stop and
target) or "trail" (v163: chandelier 3 ATR trail, no target, CAP >= 60). A
changed parameter or a changed race shape is a new idea with a new name (and
a new ledger row), never an edit here: each idea is screened once, under one
shape.

v174: a module may also export CONTEXT, a tuple of cached tickers (e.g.
("TLT",)). It then defines events(df, context), where context maps each of
those names to its frame (screen/context.py: point in time, exact-date
alignment). A module without CONTEXT keeps events(df) and is called with
exactly one argument.
"""
from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Callable, Mapping

import pandas as pd

#: Batch order of the spec, and the run order of V140-15..18; later ideas
#: append in the order they were frozen.
IDEA_MODULES = ("high52w", "uptrend_pullback", "gap_volume", "turn_of_month",
                "turtle_soup", "quiet_pullback", "bond_spike_rebound", "dollar_drop")

#: The race shapes an idea may declare (v163 spec § One shape per idea).
RACE_SHAPES = ("fixed", "trail")
#: With no target, the cap does the target's job: a trail idea freezes at
#: least this many bars (the longest fixed cap, high52w).
TRAIL_MIN_CAP = 60


@dataclass(frozen=True)
class Idea:
    name: str
    events: Callable[..., pd.Series]
    time_cap_bars: int
    direction: str = "long"
    params: Mapping = field(default_factory=dict)
    summary: str = ""
    source: str = ""
    race_shape: str = "fixed"
    context: tuple[str, ...] = ()

    def __post_init__(self):
        if self.direction != "long":
            raise ValueError(f"{self.name}: v140 screens long ideas only")
        if self.time_cap_bars < 1:
            raise ValueError(f"{self.name}: time cap must be at least one bar")
        if self.race_shape not in RACE_SHAPES:
            raise ValueError(f"{self.name}: race shape {self.race_shape!r} is not "
                             f"one of {RACE_SHAPES}")
        if self.race_shape == "trail" and self.time_cap_bars < TRAIL_MIN_CAP:
            raise ValueError(f"{self.name}: a trail idea freezes a time cap of at "
                             f"least {TRAIL_MIN_CAP} bars, not {self.time_cap_bars}")
        object.__setattr__(self, "params", MappingProxyType(dict(self.params)))
        object.__setattr__(self, "context", tuple(self.context))


def _load(name: str) -> Idea:
    module = importlib.import_module(f"{__name__}.{name}")
    return Idea(name=name, events=module.events, time_cap_bars=module.CAP,
                params=module.PARAMS, summary=module.SUMMARY,
                source=module.SOURCE,
                race_shape=getattr(module, "RACE", "fixed"),
                context=tuple(getattr(module, "CONTEXT", ())))


IDEAS: dict[str, Idea] = {name: _load(name) for name in IDEA_MODULES}

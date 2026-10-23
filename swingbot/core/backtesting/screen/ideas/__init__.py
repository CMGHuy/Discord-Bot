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

v182: a module may also export DIRECTION ("long" default, or "short"), ENTRY
("next_open" default, or "level" with a levels(df) function giving the order
level per bar from bars <= t-1), control_events(df) (the trend-only control,
printed, never gating) and FAMILY (names screened as one family). A changed
DIRECTION or ENTRY is a new idea with a new name.
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
                "turtle_soup", "quiet_pullback", "bond_spike_rebound", "dollar_drop",
                "sweep_reclaim_bos", "range_breakdown_close")

#: The race shapes an idea may declare (v163 spec § One shape per idea).
RACE_SHAPES = ("fixed", "trail")
#: With no target, the cap does the target's job: a trail idea freezes at
#: least this many bars (the longest fixed cap, high52w).
TRAIL_MIN_CAP = 60
#: v182: a short idea races the exact mirror of the long race.
DIRECTIONS = ("long", "short")
#: v182: "next_open" (every idea before v182) or "level" (a resting stop order
#: that fills on the event bar at levels(df), fixed shape only).
ENTRY_MODES = ("next_open", "level")


def _shape_problem(idea: "Idea") -> str | None:
    if idea.time_cap_bars < 1:
        return f"{idea.name}: time cap must be at least one bar"
    if idea.race_shape not in RACE_SHAPES:
        return (f"{idea.name}: race shape {idea.race_shape!r} is not "
                f"one of {RACE_SHAPES}")
    if idea.race_shape == "trail" and idea.time_cap_bars < TRAIL_MIN_CAP:
        return (f"{idea.name}: a trail idea freezes a time cap of at "
                f"least {TRAIL_MIN_CAP} bars, not {idea.time_cap_bars}")
    return None


def _side_problem(idea: "Idea") -> str | None:
    if idea.direction not in DIRECTIONS:
        return f"{idea.name}: direction {idea.direction!r} is not one of {DIRECTIONS}"
    if idea.entry not in ENTRY_MODES:
        return f"{idea.name}: entry {idea.entry!r} is not one of {ENTRY_MODES}"
    if idea.entry == "level" and idea.levels is None:
        return f"{idea.name}: a level idea needs levels(df)"
    if idea.entry == "next_open" and idea.levels is not None:
        return f"{idea.name}: a next_open idea takes no levels"
    if idea.entry == "level" and idea.race_shape == "trail":
        return f"{idea.name}: level entry races the fixed shape only"
    return None


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
    entry: str = "next_open"
    levels: Callable[[pd.DataFrame], pd.Series] | None = None
    control: Callable[[pd.DataFrame], pd.Series] | None = None
    family: tuple[str, ...] = ()

    def __post_init__(self):
        problem = _side_problem(self) or _shape_problem(self)
        if problem:
            raise ValueError(problem)
        object.__setattr__(self, "params", MappingProxyType(dict(self.params)))
        object.__setattr__(self, "context", tuple(self.context))
        object.__setattr__(self, "family", tuple(self.family))


def _load(name: str) -> Idea:
    module = importlib.import_module(f"{__name__}.{name}")
    return Idea(name=name, events=module.events, time_cap_bars=module.CAP,
                params=module.PARAMS, summary=module.SUMMARY,
                source=module.SOURCE,
                race_shape=getattr(module, "RACE", "fixed"),
                context=tuple(getattr(module, "CONTEXT", ())),
                direction=getattr(module, "DIRECTION", "long"),
                entry=getattr(module, "ENTRY", "next_open"),
                levels=getattr(module, "levels", None),
                control=getattr(module, "control_events", None),
                family=tuple(getattr(module, "FAMILY", ())))


IDEAS: dict[str, Idea] = {name: _load(name) for name in IDEA_MODULES}

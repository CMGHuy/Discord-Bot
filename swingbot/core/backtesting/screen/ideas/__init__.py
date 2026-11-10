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

v211: a module with CONTEXT may also export CONTEXT_KIND ("z" default, or
"level"). A "level" context is read as raw values (a breadth fraction, a VIX
close): the runner loads it under the same raw-index and SPY-session checks
but never z-scores it, and the v174 z diagnostics do not apply. A changed
CONTEXT_KIND is a new idea with a new name.

v214: a module may also export MODE ("edge" default, or "avoid") and, for an
avoid idea, states(df): one frame per ticker with bool columns event,
control_condition and condition, and a float column bottom (spec v214 G3). An
avoid idea races the fixed shape from the next open, and its verdict is the
six-clause avoid rule (screen/verdict.py). A changed MODE is a new idea with a
new name.
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
                "sweep_reclaim_bos", "range_breakdown_close", "range_breakdown_stop",
                "vix_curve_calm", "shock_support_break_short", "shock_failed_bounce_short")

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
#: v211: how a context file is read: "z" (trailing z-score, v174) or "level"
#: (raw values, no z-coverage floor).
CONTEXT_KINDS = ("z", "level")
#: v214: "edge" (every idea before v214: must beat the matched null) or "avoid"
#: (must do worse than the null AND a control arm; licenses a veto spec only).
MODES = ("edge", "avoid")


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


def _context_problem(idea: "Idea") -> str | None:
    if idea.context_kind not in CONTEXT_KINDS:
        return f"{idea.name}: context kind {idea.context_kind!r} is not one of {CONTEXT_KINDS}"
    if idea.context_kind == "level" and not idea.context:
        return f"{idea.name}: a level context idea needs CONTEXT"
    return None


def _mode_problem(idea: "Idea") -> str | None:
    if idea.mode not in MODES:
        return f"{idea.name}: mode {idea.mode!r} is not one of {MODES}"
    if idea.mode == "avoid" and idea.states is None:
        return f"{idea.name}: an avoid idea needs states(df)"
    if idea.mode == "edge" and idea.states is not None:
        return f"{idea.name}: an edge idea takes no states"
    if idea.mode == "avoid" and (idea.entry != "next_open" or idea.race_shape != "fixed"):
        return f"{idea.name}: an avoid idea races the fixed shape from the next open"
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
    context_kind: str = "z"
    mode: str = "edge"
    states: Callable[[pd.DataFrame], pd.DataFrame] | None = None

    def __post_init__(self):
        problem = (_side_problem(self) or _shape_problem(self)
                   or _context_problem(self) or _mode_problem(self))
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
                family=tuple(getattr(module, "FAMILY", ())),
                context_kind=getattr(module, "CONTEXT_KIND", "z"),
                mode=getattr(module, "MODE", "edge"),
                states=getattr(module, "states", None))


IDEAS: dict[str, Idea] = {name: _load(name) for name in IDEA_MODULES}

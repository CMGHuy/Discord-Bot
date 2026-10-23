"""The v140 screen's fixed trade (spec § The fixed trade). Long, and (v182) short as its exact mirror.

Event on bar t (known at t's close). Entry = open of t+1; risk = 1.5 x
ATR14[t]; stop = entry - risk; target = entry + 2 x risk. Bars t+1..t+cap:
an open at/below the stop exits at the open (a gap loss, can exceed -1R);
else an open at/above the target exits at the open; else a low touching the
stop exits at the stop (checked first); else a high touching the target
exits at the target. After bar t+cap, exit at its close. Costs: both fills
worsened by SLIPPAGE_BPS, then commission_r() in R.

Outcome codes index OUTCOMES. v163 appended ``trail`` (5) and ``gap_trail``
(6) for the trail race (``trail.py``); a fixed race never produces them, a
trail race never produces ``gap_target`` or ``target``. SHAPE_OUTCOMES is
each shape's own list, in table order, so a fixed idea's results doc keeps
its five rows.

v182: direction="short" races the long machinery on negated prices
(sides.oriented): stop = entry + risk, target = entry - 2 x risk, gap stop
when the open is at/above the stop, high checked first; gross R = (entry -
exit) / risk; frictions sell the entry and buy the exit, plus borrow_r.
RaceResult.entry is the real entry price either way.

v182 level mode (fill=...): a resting stop order placed before bar t opens
from levels known at <= t-1, living one bar. Entry on bar t at fill (short:
min(Open[t], level); long mirror: max); risk = 1.5 x ATR14[t-1]; on bar t
only the stop counts (exit at the stop, exit_pos = t); bars t+1..t+cap race
as above; entry slippage LEVEL_SLIPPAGE_FACTOR x base; warm-up read at t-1.
Fixed shape only.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd

from swingbot import config
from swingbot.core.backtesting.screen import indicators, sides

STOP_ATR = 1.5
REWARD_RISK = 2.0
LEVEL_SLIPPAGE_FACTOR = 2.0   # v182: a level entry is a stop-market order through a broken level
REPRICE_SLIPPAGE_FACTOR = 3.0   # v182: the level book repriced at 3 x base; printed, never gating
OUTCOMES = ("gap_stop", "gap_target", "stop", "target", "timeout",
            "trail", "gap_trail")
SHAPE_OUTCOMES: dict[str, tuple[str, ...]] = {
    "fixed": OUTCOMES[:5],
    "trail": ("gap_stop", "stop", "gap_trail", "trail", "timeout"),
}
COUNTERS = ("dropped_nonmember", "dropped_warmup", "dropped_window",
            "skipped_overlap")
_FIELDS = ("event_pos", "exit_pos", "entry", "risk", "gross_r", "r", "outcome")
_WARM_LAG = {"next_open": 0, "level": 1}
_BAR_ZERO = "a level entry reads ATR14[t-1]; an event on bar 0 is dropped_warmup"


@dataclass(frozen=True, eq=False)
class RaceResult:
    event_pos: np.ndarray
    exit_pos: np.ndarray
    entry: np.ndarray
    risk: np.ndarray
    gross_r: np.ndarray
    r: np.ndarray
    outcome: np.ndarray

    @classmethod
    def empty(cls) -> "RaceResult":
        ints, floats = np.array([], dtype=int), np.array([], dtype=float)
        return cls(ints, ints.copy(), floats, floats.copy(), floats.copy(),
                   floats.copy(), np.asarray(OUTCOMES)[ints])

    def __len__(self) -> int:
        return len(self.event_pos)

    def take(self, selector) -> "RaceResult":
        return RaceResult(*(getattr(self, name)[selector] for name in _FIELDS))


def warm_mask(atr, sma200) -> np.ndarray:
    """Warm-up complete: finite ATR14 > 0 and a finite SMA200 (reading F8)."""
    a = pd.Series(atr).to_numpy(dtype=float)
    s = pd.Series(sma200).to_numpy(dtype=float)
    return np.isfinite(a) & (a > 0) & np.isfinite(s)


def _check_positions(event_pos: np.ndarray, cap: int, n: int) -> None:
    if cap < 1:
        raise ValueError("a race needs a time cap of at least one bar")
    if event_pos.size and (event_pos.min() < 0 or event_pos.max() + cap > n - 1):
        raise ValueError("a race would read past the frame; count the event "
                         "as dropped_window instead")


def _first_exit(O, H, L, C, stop, target):
    """Exit price, outcome code (index into OUTCOMES) and bar offset."""
    stop_c, target_c = stop[:, None], target[:, None]
    gap_stop = O <= stop_c
    gap_target = ~gap_stop & (O >= target_c)
    hit_stop = L <= stop_c
    hit_target = H >= target_c
    hit = gap_stop | gap_target | hit_stop | hit_target
    any_hit = hit.any(axis=1)
    rows = np.arange(len(O))
    j = np.where(any_hit, hit.argmax(axis=1), O.shape[1] - 1)
    code = np.select([gap_stop[rows, j], gap_target[rows, j],
                      hit_stop[rows, j], hit_target[rows, j]],
                     [0, 1, 2, 3], default=4)
    code = np.where(any_hit, code, 4)
    price = np.choose(code, [O[rows, j], O[rows, j], stop, target, C[rows, j]])
    return price, code, j


def _base_bps(slippage_bps) -> float:
    """The per-side slippage base ``apply_frictions`` reads."""
    if slippage_bps is None:
        return float(getattr(config, "SLIPPAGE_BPS", 5.0))
    return float(slippage_bps)


def level_fills(df, event_pos, levels, atr, direction):
    """Fill price and depth (in ATR14[t-1]) of a one-bar resting stop order
    at ``levels[t]`` on each event bar t."""
    event_pos = np.asarray(event_pos, dtype=int)
    if event_pos.size and event_pos.min() < 1:
        raise ValueError(_BAR_ZERO)
    o = df["Open"].to_numpy(dtype=float)[event_pos]
    lvl = np.asarray(levels, dtype=float)[event_pos]
    a = pd.Series(atr).to_numpy(dtype=float)[event_pos - 1]
    if direction == "short":
        fill = np.minimum(o, lvl)
        reached = df["Low"].to_numpy(dtype=float)[event_pos] < lvl
        depth = (o - fill) / a
    elif direction == "long":
        fill = np.maximum(o, lvl)
        reached = df["High"].to_numpy(dtype=float)[event_pos] > lvl
        depth = (fill - o) / a
    else:
        raise ValueError(f"unknown direction {direction!r}; expected 'long' or 'short'")
    missed = int((~(np.isfinite(lvl) & reached)).sum())
    if missed:
        raise ValueError(f"a level order must fill on its own bar; {missed} event(s) did not")
    return fill, depth


def _race_level(df, event_pos, cap, atr_v, fill, *, slippage_bps, commission,
                direction, level_factor) -> RaceResult:
    """Level mode: entry on bar t at ``fill``, only the stop counts on bar t."""
    if event_pos.min() < 1:
        raise ValueError(_BAR_ZERO)
    o, h, l, c = sides.oriented(*(df[col].to_numpy(dtype=float)
                                  for col in ("Open", "High", "Low", "Close")), direction)
    entry = -fill if direction == "short" else fill          # oriented space
    risk = STOP_ATR * atr_v[event_pos - 1]
    stop, target = entry - risk, entry + REWARD_RISK * risk
    bars = event_pos[:, None] + 1 + np.arange(cap)[None, :]
    price, code, offset = _first_exit(o[bars], h[bars], l[bars], c[bars], stop, target)
    exit_pos = event_pos + 1 + offset
    on_fill_bar = l[event_pos] <= stop                       # short: High[t] >= stop
    price = np.where(on_fill_bar, stop, price)
    code = np.where(on_fill_bar, OUTCOMES.index("stop"), code)
    exit_pos = np.where(on_fill_bar, event_pos, exit_pos)
    gross = (price - entry) / risk
    if direction == "short":
        entry, price = -entry, -price
    net = sides.net_r(entry, price, risk, direction=direction,
                      days=sides.holding_days(df.index, event_pos, exit_pos),
                      slippage_bps=slippage_bps,
                      entry_bps=level_factor * _base_bps(slippage_bps),
                      commission=commission)
    return RaceResult(event_pos, exit_pos, entry, risk, gross, net,
                      np.asarray(OUTCOMES)[code])


def race(df: pd.DataFrame, event_pos, cap: int, *, atr=None,
         slippage_bps=None, commission=None, direction: str = "long",
         fill=None, level_factor: float = LEVEL_SLIPPAGE_FACTOR) -> RaceResult:
    """Race every event in ``event_pos`` (bar positions) at once."""
    event_pos = np.asarray(event_pos, dtype=int)
    _check_positions(event_pos, cap, len(df))
    if event_pos.size == 0:
        return RaceResult.empty()
    atr_v = (indicators.atr(df) if atr is None else pd.Series(atr)).to_numpy(dtype=float)
    if fill is not None:
        return _race_level(df, event_pos, cap, atr_v, np.asarray(fill, dtype=float),
                           slippage_bps=slippage_bps, commission=commission,
                           direction=direction, level_factor=level_factor)
    o, h, l, c = sides.oriented(
        *(df[col].to_numpy(dtype=float) for col in ("Open", "High", "Low", "Close")),
        direction)
    bars = event_pos[:, None] + 1 + np.arange(cap)[None, :]
    entry = o[event_pos + 1]
    risk = STOP_ATR * atr_v[event_pos]
    price, code, offset = _first_exit(o[bars], h[bars], l[bars], c[bars],
                                      entry - risk, entry + REWARD_RISK * risk)
    exit_pos = event_pos + 1 + offset
    gross = (price - entry) / risk
    if direction == "short":
        entry, price = -entry, -price            # back to real prices; negation is exact
    net = sides.net_r(entry, price, risk, direction=direction,
                      days=sides.holding_days(df.index, event_pos + 1, exit_pos),
                      slippage_bps=slippage_bps, commission=commission)
    return RaceResult(event_pos, exit_pos, entry, risk, gross, net,
                      np.asarray(OUTCOMES)[code])


def _drop_reason(pos: int, member, warm, cap: int, n: int,
                 lag: int = 0) -> str | None:
    if not member[pos]:
        return "dropped_nonmember"
    if pos - lag < 0 or not warm[pos - lag]:
        return "dropped_warmup"
    if pos + cap > n - 1:
        return "dropped_window"
    return None


def candidate_events(events, member, warm, cap: int, *, entry: str = "next_open"):
    """Event positions that can be raced, and the drop counts for the rest.
    ``entry="level"`` reads warm-up at t-1 (v182)."""
    if entry not in _WARM_LAG:
        raise ValueError(f"unknown entry {entry!r}; expected one of {tuple(_WARM_LAG)}")
    lag = _WARM_LAG[entry]
    events = np.asarray(events, dtype=bool)
    counts = dict.fromkeys(COUNTERS, 0)
    keep = []
    for pos in np.flatnonzero(events):
        reason = _drop_reason(pos, member, warm, cap, len(events), lag)
        if reason is None:
            keep.append(pos)
        else:
            counts[reason] += 1
    return np.asarray(keep, dtype=int), counts


def non_overlapping(event_pos, exit_pos) -> np.ndarray:
    """One open race per ticker: skip an event while it is before the
    running race's exit bar (reading F4)."""
    keep = np.zeros(len(event_pos), dtype=bool)
    busy_until = -1
    for i, (pos, out) in enumerate(zip(event_pos, exit_pos)):
        if pos >= busy_until:
            keep[i] = True
            busy_until = out
    return keep


def race_for(shape: str) -> Callable[..., RaceResult]:
    """The race function of one shape: ``race`` (fixed) or
    ``trail.race_trail`` (v163). ``trail`` imports this module, so it is
    imported here, on first use, never at module level."""
    if shape == "fixed":
        return race
    if shape == "trail":
        from swingbot.core.backtesting.screen import trail
        return trail.race_trail
    raise ValueError(f"unknown race shape {shape!r}; expected one of "
                     f"{tuple(SHAPE_OUTCOMES)}")


def _level_kwargs(df, cand, levels, atr, direction, level_factor) -> dict:
    """The level-mode race keywords: the candidates' fills and the factor."""
    if cand.size == 0:
        fill = np.array([], dtype=float)
    else:
        fill = level_fills(df, cand, levels, atr, direction)[0]
    return {"fill": fill, "level_factor": level_factor}


def run_book(df, events, cap: int, *, member, warm, atr, slippage_bps=None,
             commission=None, shape: str = "fixed", direction: str = "long",
             levels: np.ndarray | None = None,
             level_factor: float = LEVEL_SLIPPAGE_FACTOR):
    """Race the eligible events under ``shape``, then keep one open race at a
    time. ``levels`` (v182) races a one-bar resting order at each level,
    fixed shape only."""
    if levels is not None and shape != "fixed":
        raise ValueError("level entry races the fixed shape only")
    race_fn = race_for(shape)
    extra = {} if direction == "long" else {"direction": direction}
    if levels is None:
        cand, counts = candidate_events(events, member, warm, cap)
    else:
        cand, counts = candidate_events(events, member, warm, cap, entry="level")
        extra.update(_level_kwargs(df, cand, np.asarray(levels, dtype=float), atr,
                                   direction, level_factor))
    raced = race_fn(df, cand, cap, atr=atr, slippage_bps=slippage_bps,
                    commission=commission, **extra)
    keep = non_overlapping(raced.event_pos, raced.exit_pos)
    counts["skipped_overlap"] = int((~keep).sum())
    return raced.take(keep), counts

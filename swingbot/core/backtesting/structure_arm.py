"""v127: the structure-break armed replay (spec §3).

A confluence scenario's level ARMS at its first test (v88's is_test rule)
and becomes a plan only when price breaks minor swing structure after the
test: a close beyond the last confirmed swing high (MSB), optionally only
after a confirmed higher low (HL). market/reaction.py's R1/R2/R3 shapes are
not used. The population is bounded by a touch-episode rule per level, not
by armed_replay.COOLDOWN_BARS.

Reuses armed_replay's arm_candidates, plan_at (plan construction + every
regate), make_confluence_at and delay_permutations unchanged; v88/v90's
walks in armed_replay.py are not touched.

NO-LOOKAHEAD: every decision at bar j reads bars <= j. Swing pivots come
from market/structure.confirmed_pivots, whose row j knows only pivots
confirmed by bar j (pivot bar p is known from p + PIVOT_K).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from swingbot.core.backtesting import armed_replay
from swingbot.core.backtesting.armed_replay import ArmCandidate, ArmOutcome
from swingbot.core.market import reaction
from swingbot.core.market.structure import confirmed_pivots

MSB, HL = "MSB", "HL"
TRIGGERS = (MSB, HL)
STOP_BUFFER_ATR = 0.10       # spec §2.3: b frozen at v88's pre-registered value
ZONE_FAIL_ATR = 0.10         # spec §3.1: cancel when a close breaks the touch low by this
TRIGGERED, ZONE_FAILED = "triggered", "cancelled_zone_failed"


@dataclass(frozen=True)
class StructCell:
    trigger: str   # MSB | HL
    n: int         # arm window, bars after the test bar
    k: float       # test proximity, ATR

    @property
    def cell_id(self) -> str:
        return f"{self.trigger}-N{self.n}-k{self.k:.2f}"

    def plan_cell(self) -> armed_replay.Cell:
        """The v88 Cell plan_at reads: only `.b` is consulted there."""
        return armed_replay.Cell(self.n, self.k, STOP_BUFFER_ATR)


@dataclass(frozen=True, eq=False)
class Pivots:
    """Per-bar confirmed swing structure, as known at that bar."""
    sh: np.ndarray       # last confirmed swing-high price (NaN if none)
    sh_pos: np.ndarray   # its positional index
    sl: np.ndarray       # last confirmed swing-low price
    sl_pos: np.ndarray

    @classmethod
    def from_frame(cls, df) -> "Pivots":
        p = confirmed_pivots(df)
        return cls(*(p[c].to_numpy(dtype=float)
                     for c in ("last_sh", "last_sh_pos", "last_sl", "last_sl_pos")))


def _touch_extreme(bars: reaction.Bars, i: int, j: int, bull: bool) -> float:
    """L_j (bullish: min Low[i..j]) or H_j (bearish: max High[i..j])."""
    return float(bars.low[i:j + 1].min() if bull else bars.high[i:j + 1].max())


def _zone_failed(bars, atr_values, i: int, j: int, bull: bool) -> bool:
    """Close[j] beyond the touch extreme known BEFORE bar j by ZONE_FAIL_ATR.
    The extreme is taken over [i, j-1]: bar j's own low can never sit
    above its own close, so an inclusive extreme could never cancel."""
    prior = _touch_extreme(bars, i, j - 1, bull)
    buffer = ZONE_FAIL_ATR * atr_values[j]
    return bool(bars.close[j] < prior - buffer if bull else bars.close[j] > prior + buffer)


def _broke_structure(bars, pivots: Pivots, j: int, bull: bool) -> bool:
    """MSB: Close[j] beyond the last swing extreme confirmed at j."""
    level = pivots.sh[j] if bull else pivots.sl[j]
    if not np.isfinite(level):
        return False
    return bool(bars.close[j] > level if bull else bars.close[j] < level)


def _higher_low(bars, pivots: Pivots, i: int, j: int, bull: bool) -> bool:
    """HL: the last swing low confirmed at j sits after the test bar and
    above the touch low (bearish: a lower high below the touch high)."""
    pos, price = (pivots.sl_pos[j], pivots.sl[j]) if bull else (pivots.sh_pos[j], pivots.sh[j])
    if not (np.isfinite(pos) and pos > i):
        return False
    extreme = _touch_extreme(bars, i, j, bull)
    return bool(price > extreme if bull else price < extreme)


def _triggered(bars, pivots, cand: ArmCandidate, cell: StructCell, j: int) -> bool:
    bull = cand.direction == "bullish"
    if not _broke_structure(bars, pivots, j, bull):
        return False
    return cell.trigger == MSB or _higher_low(bars, pivots, cand.index, j, bull)


def walk_structure_arm(bars: reaction.Bars, atr_values: np.ndarray, pivots: Pivots,
                       cand: ArmCandidate, cell: StructCell) -> ArmOutcome:
    """Walk one arm opened at its test bar i = cand.index across (i, i + N].

    Per bar j, in this order: the zone-failed cancel, then the trigger.
    No trigger by i + N -> expired at i + N; a window running off the
    frame -> unresolved. A trigger returns ArmOutcome("triggered", j,
    cell.trigger, i) -- first_test_index is the arm bar, which is what
    plan_at anchors the stop's touch low from.
    """
    i, last = cand.index, cand.index + cell.n
    bull = cand.direction == "bullish"
    for j in range(i + 1, min(last, len(bars.close) - 1) + 1):
        if _zone_failed(bars, atr_values, i, j, bull):
            return ArmOutcome(ZONE_FAILED, j)
        if _triggered(bars, pivots, cand, cell, j):
            return ArmOutcome(TRIGGERED, j, cell.trigger, i)
    if last <= len(bars.close) - 1:
        return ArmOutcome("expired", last)
    return ArmOutcome("unresolved", None)

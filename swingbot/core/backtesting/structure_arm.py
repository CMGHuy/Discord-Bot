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

from collections import Counter
from dataclasses import dataclass, field

import numpy as np

from swingbot.core.backtesting import armed_replay
from swingbot.core.backtesting.armed_replay import ArmCandidate, ArmOutcome
from swingbot.core.backtesting.backtest_scenarios import levels_asof
from swingbot.core.market import reaction
from swingbot.core.market.indicators import atr
from swingbot.core.market.structure import confirmed_pivots
from swingbot.scan_params import ScanParams

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


def released(bars: reaction.Bars, atr_values: np.ndarray, level: float, direction: str,
             k: float, start: int, stop: int) -> bool:
    """Did any bar in [start, stop) close more than (k + 1) * ATR14 from
    `level` in the trade's favour (above a support, below a resistance)?"""
    if stop <= start:
        return False
    close = bars.close[start:stop]
    reach = (k + 1.0) * atr_values[start:stop]
    with np.errstate(invalid="ignore"):
        away = close > level + reach if direction == "bullish" else close < level - reach
    return bool(np.any(away))


def level_key(cand: ArmCandidate) -> tuple:
    return (cand.direction, round(cand.level, 6))


@dataclass
class StructCellResult:
    issued: list = field(default_factory=list)      # (trigger index, plan, trigger)
    confirmed: list = field(default_factory=list)   # (ArmCandidate, ArmOutcome), issued or regated
    counts: Counter = field(default_factory=Counter)
    arms: list = field(default_factory=list)        # (arm index, end index | None, status or plan reason)


@dataclass
class _Frame:
    """Everything one (ticker, horizon) frame shares across cells."""
    ticker: str
    df: object
    horizon_key: str
    bars: reaction.Bars
    atr_values: np.ndarray
    pivots: Pivots
    params: ScanParams
    level_map_at: object
    confluence_at: object


class _Episodes:
    """Touch-episode bookkeeping (spec §3.1): a level whose arm terminated
    re-arms only after a release close. `pending[key]` is the first bar
    not yet scanned for that release."""

    def __init__(self, fr: _Frame, k: float):
        self.fr, self.k, self.pending = fr, k, {}

    def blocked(self, cand: ArmCandidate) -> bool:
        key = level_key(cand)
        if key not in self.pending:
            return False
        start = self.pending[key]
        if released(self.fr.bars, self.fr.atr_values, cand.level, cand.direction,
                    self.k, start, cand.index):
            del self.pending[key]
            return False
        self.pending[key] = max(start, cand.index)
        return True

    def close(self, cand: ArmCandidate, end: int) -> None:
        self.pending[level_key(cand)] = end + 1


def _issue(fr: _Frame, cand, outcome, cell: StructCell, result: StructCellResult) -> str:
    result.confirmed.append((cand, outcome))
    plan, reason = armed_replay.plan_at(
        fr.ticker, fr.df, fr.horizon_key, cand, j=outcome.resolved_index,
        first_test_index=outcome.first_test_index, cell=cell.plan_cell(),
        bars=fr.bars, atr_values=fr.atr_values, params=fr.params,
        level_map_at=fr.level_map_at, confluence_at=fr.confluence_at)
    if plan is not None:
        result.issued.append((outcome.resolved_index, plan, cell.trigger))
    return reason


def _arm(fr: _Frame, cand, cell: StructCell, result: StructCellResult) -> ArmOutcome:
    outcome = walk_structure_arm(fr.bars, fr.atr_values, fr.pivots, cand, cell)
    status = outcome.status
    if status == TRIGGERED:
        status = _issue(fr, cand, outcome, cell, result)
    result.counts["armed"] += 1
    result.counts[status] += 1
    result.arms.append((cand.index, outcome.resolved_index, status))
    return outcome


def _replay_cell(fr: _Frame, candidates: dict, cell: StructCell) -> StructCellResult:
    result = StructCellResult()
    busy_until: dict[str, int] = {}
    episodes = _Episodes(fr, cell.k)
    for i in sorted(candidates):
        for cand in candidates[i]:
            if i <= busy_until.get(cand.direction, -1) or episodes.blocked(cand):
                continue
            if not reaction.is_test(fr.bars, i, cand.level, cand.direction, cell.k,
                                    fr.atr_values[i]):
                continue
            outcome = _arm(fr, cand, cell, result)
            end = len(fr.df) if outcome.resolved_index is None else outcome.resolved_index
            busy_until[cand.direction] = end
            episodes.close(cand, end)
    return result


def replay_structure(ticker: str, df, horizon_key: str, cells, *, params: ScanParams | None = None,
                     candidates: dict | None = None, level_cache: dict | None = None,
                     level_map_at=None, confluence_at=None) -> dict:
    """Every cell's arms and issued plans over one (ticker, horizon) frame.

    An arm opens at a bar where an arm candidate's own bar tests its level
    (reaction.is_test at k). One live arm per direction (v88's
    exclusivity); a level whose arm terminated waits for a release close
    (_Episodes). COOLDOWN_BARS is not consulted. Candidates, the level
    cache, the confluence memo and the pivots are shared across cells.
    """
    if params is None:
        params = ScanParams.from_config()
    cache = {} if level_cache is None else level_cache
    if candidates is None:
        candidates = armed_replay.arm_candidates(ticker, df, horizon_key, params=params,
                                                 level_cache=cache)
    if level_map_at is None:
        level_map_at = lambda j: levels_asof(ticker, df, j, horizon_key, cache)  # noqa: E731
    if confluence_at is None:
        confluence_at = armed_replay.make_confluence_at(df, horizon_key)
    fr = _Frame(ticker, df, horizon_key, reaction.Bars.from_frame(df),
                atr(df, 14).to_numpy(dtype=float), Pivots.from_frame(df), params,
                level_map_at, confluence_at)
    return {cell.cell_id: _replay_cell(fr, candidates, cell) for cell in cells}


def structure_permutations(ticker: str, df, horizon_key: str, cell: StructCell, confirmed, *,
                           n: int, seed: int, level_cache: dict, params: ScanParams | None = None,
                           level_map_at=None, confluence_at=None) -> list:
    """Spec §4.2's random-delay null: armed_replay.delay_permutations over
    the arms that triggered, with v127's frozen stop buffer. Each arm's
    candidate index IS its test bar, so delay_permutations' first-test scan
    anchors the stop at the arm bar and draws from [i, min(i + N, last)]."""
    return armed_replay.delay_permutations(
        ticker, df, horizon_key, cell.plan_cell(), confirmed, n=n, seed=seed,
        level_cache=level_cache, params=params, level_map_at=level_map_at,
        confluence_at=confluence_at)

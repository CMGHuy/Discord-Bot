"""v209 market-shock detector: one reading per scan pass, and its state machine.

Pure: no I/O and no ``swingbot.config`` import. Thresholds arrive as a frozen
:class:`ShockThresholds` whose defaults equal the "Market Shock" config
defaults; ``swingbot.core.scanning.shock_scan`` builds one from config, builds
the :class:`ShockSnapshot` from the scan's frames and live quotes, and stores
what ``measure`` and ``step`` return.

A reading measures the watchlist at pass time (the live quote against the last
completed session's close); it never looks at a later bar.

Spec: docs/superpowers/specs/2026-11-05-v209-market-shock-detector-design.md
"""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, fields, replace
from typing import Callable
from datetime import date, datetime

LABELS = ("NORMAL", "SHOCK", "RECOVERY")
NORMAL, SHOCK, RECOVERY = LABELS

#: Tolerance for threshold comparisons, so 7/20 meets a 0.40 - 0.05 bar.
_EPS = 1e-9

_DATETIME_FIELDS = frozenset({"as_of", "since", "hold_since"})
_DATE_FIELDS = frozenset({"session_date"})


@dataclass(frozen=True)
class ShockThresholds:
    atr_k: float = 1.0
    breadth_enter: float = 0.40
    sectors_frac: float = 0.6
    breadth_fast: float = 0.25
    speed_enter: float = 0.10
    vix_spike_pct: float = 15.0
    vix_relief: float = 0.05
    breadth_reenter: float = 0.30
    breadth_exit: float = 0.20
    recovery_vix_off_high_pct: float = 5.0
    recovery_spy_retrace: float = 0.5
    min_dwell_min: int = 45
    recovery_min_dwell_min: int = 30
    min_names: int = 20
    vix_max_age_s: int = 600
    open_settle_min: int = 15
    quote_max_age_s: int = 300


@dataclass(frozen=True)
class NameRow:
    ticker: str
    sector: str | None
    last: float | None
    prev_close: float | None
    atr14: float | None
    is_equity: bool


@dataclass(frozen=True)
class VixTape:
    level: float | None
    chg_pct: float | None
    as_of: datetime | None


@dataclass(frozen=True)
class ShockSnapshot:
    as_of: datetime
    session_date: date
    minutes_since_open: float
    names: tuple[NameRow, ...]
    spy: NameRow | None
    qqq: NameRow | None
    vix: VixTape


@dataclass(frozen=True)
class ShockReading:
    as_of: datetime
    session_date: date
    minutes_since_open: float
    breadth_frac: float | None
    sectors_down: int
    sectors_total: int
    breadth_speed: float | None
    spy_atr_move: float | None
    qqq_atr_move: float | None
    spy_last: float | None
    spy_prev_close: float | None
    spy_session_low: float | None
    spy_new_low: bool
    spy_retrace: float | None
    vix_level: float | None
    vix_chg_pct: float | None
    vix_session_high: float | None
    vix_off_high_pct: float | None
    n_names: int
    insufficient: bool

    def as_row(self) -> dict:
        return _to_row(self)

    @classmethod
    def from_row(cls, row: dict) -> "ShockReading":
        return _from_row(cls, row)


# --- JSON rows -------------------------------------------------------------

def _encode(value):
    return value.isoformat() if isinstance(value, (datetime, date)) else value


def _decode(name: str, value):
    if not isinstance(value, str):
        return value
    if name in _DATETIME_FIELDS:
        return datetime.fromisoformat(value)
    if name in _DATE_FIELDS:
        return date.fromisoformat(value)
    return value


def _to_row(obj) -> dict:
    return {f.name: _encode(getattr(obj, f.name)) for f in fields(obj)}


def _from_row(cls, row: dict):
    """Rebuild a dataclass from its row. A key the class lacks is ignored; a
    required field missing from the row raises ``TypeError`` (no upcasting)."""
    return cls(**{f.name: _decode(f.name, row[f.name]) for f in fields(cls) if f.name in row})


# --- small numeric helpers -------------------------------------------------

def _meets(value: float | None, bar: float) -> bool:
    """``value >= bar`` with the ``_EPS`` tolerance; a missing value never meets."""
    return value is not None and value + _EPS >= bar


def _is_down(move: float, atr_k: float) -> bool:
    return move <= -atr_k + _EPS


def _atr_move(row: NameRow | None) -> float | None:
    if row is None or row.last is None or row.prev_close is None or row.atr14 is None:
        return None
    if not row.atr14 > 0:                       # also rejects NaN
        return None
    move = (row.last - row.prev_close) / row.atr14
    return move if math.isfinite(move) else None


def _running(pick, prior: float | None, value: float | None) -> float | None:
    if prior is None:
        return value
    if value is None:
        return prior
    return pick(prior, value)


# --- the reading -----------------------------------------------------------

def _contributors(names) -> list[tuple[str | None, float]]:
    out = []
    for row in names:
        move = _atr_move(row) if row.is_equity else None
        if move is not None:
            out.append((row.sector, move))
    return out


def _breadth(contribs, atr_k: float) -> float | None:
    if not contribs:
        return None
    return sum(1 for _sector, move in contribs if _is_down(move, atr_k)) / len(contribs)


def _sectors(contribs, atr_k: float) -> tuple[int, int]:
    by_sector: dict[str, list[float]] = {}
    for sector, move in contribs:
        if sector:
            by_sector.setdefault(sector, []).append(move)
    groups = [moves for moves in by_sector.values() if len(moves) >= 2]
    down = sum(1 for moves in groups if _is_down(statistics.median(moves), atr_k))
    return down, len(groups)


def _speed(breadth: float | None, prev: ShockReading | None, same: bool) -> float | None:
    if not same or breadth is None or prev.insufficient or prev.breadth_frac is None:
        return None
    return breadth - prev.breadth_frac


def _retrace(last, prev_close, low) -> float | None:
    if last is None or prev_close is None or low is None:
        return None
    if low >= prev_close:
        return 1.0
    return (last - low) / (prev_close - low)


def _spy_fields(spy: NameRow | None, prev: ShockReading | None, same: bool) -> dict:
    last = spy.last if spy is not None else None
    prev_close = spy.prev_close if spy is not None else None
    prior_low = prev.spy_session_low if same else None
    low = _running(min, prior_low, last)
    return {
        "spy_last": last,
        "spy_prev_close": prev_close,
        "spy_session_low": low,
        "spy_new_low": prior_low is not None and last is not None and last < prior_low,
        "spy_retrace": _retrace(last, prev_close, low),
    }


def _fresh_vix(vix: VixTape, now: datetime, max_age_s: int) -> tuple[float | None, float | None]:
    if vix.level is None or vix.as_of is None:
        return None, None
    if (now - vix.as_of).total_seconds() > max_age_s:
        return None, None
    return vix.level, vix.chg_pct


def _vix_fields(snapshot: ShockSnapshot, prev: ShockReading | None, same: bool,
                th: ShockThresholds) -> dict:
    level, chg = _fresh_vix(snapshot.vix, snapshot.as_of, th.vix_max_age_s)
    high = _running(max, prev.vix_session_high if same else None, level)
    off = (high - level) / high * 100.0 if level is not None and high else None
    return {"vix_level": level, "vix_chg_pct": chg, "vix_session_high": high,
            "vix_off_high_pct": off}


def measure(snapshot: ShockSnapshot, prev: ShockReading | None,
            th: ShockThresholds = ShockThresholds()) -> ShockReading:
    """Build one reading from a pass's snapshot and the previous stored reading."""
    same = prev is not None and prev.session_date == snapshot.session_date
    contribs = _contributors(snapshot.names)
    breadth = _breadth(contribs, th.atr_k)
    down, total = _sectors(contribs, th.atr_k)
    return ShockReading(
        as_of=snapshot.as_of,
        session_date=snapshot.session_date,
        minutes_since_open=snapshot.minutes_since_open,
        breadth_frac=breadth,
        sectors_down=down,
        sectors_total=total,
        breadth_speed=_speed(breadth, prev, same),
        spy_atr_move=_atr_move(snapshot.spy),
        qqq_atr_move=_atr_move(snapshot.qqq),
        **_spy_fields(snapshot.spy, prev, same),
        **_vix_fields(snapshot, prev, same, th),
        n_names=len(contribs),
        insufficient=len(contribs) < th.min_names,
    )


# --- the state machine -----------------------------------------------------

@dataclass(frozen=True)
class ShockState:
    """The stored state. ``entry_streak``, ``hold_since`` and ``prev_breadth``
    are the bookkeeping for the two-consecutive rule, the RECOVERY hold and the
    rising-breadth re-entry; they live in ``market_shock_state.doc["state"]``."""
    label: str = NORMAL
    since: datetime | None = None
    session_date: date | None = None
    vix_session_high: float | None = None
    spy_prev_close: float | None = None
    entry_streak: int = 0
    hold_since: datetime | None = None
    prev_breadth: float | None = None

    def __post_init__(self):
        if self.label not in LABELS:
            raise ValueError(f"unknown shock label {self.label!r}")

    def as_row(self) -> dict:
        return _to_row(self)

    @classmethod
    def from_row(cls, row: dict | None) -> "ShockState":
        return cls() if not row else _from_row(cls, row)


Rule = Callable[[ShockState, ShockReading, ShockThresholds], ShockState]


def _settled(reading: ShockReading, th: ShockThresholds) -> bool:
    """False for readings inside the open-settle window (the opening gap)."""
    return reading.minutes_since_open + _EPS >= th.open_settle_min


def _relief(reading: ShockReading, th: ShockThresholds) -> float:
    return th.vix_relief if _meets(reading.vix_chg_pct, th.vix_spike_pct) else 0.0


def _sectors_needed(reading: ShockReading, th: ShockThresholds) -> int:
    return math.ceil(round(th.sectors_frac * reading.sectors_total, 9))


def _depth_path(reading: ShockReading, th: ShockThresholds, relief: float) -> bool:
    return (reading.sectors_total >= 1
            and reading.sectors_down >= _sectors_needed(reading, th)
            and _meets(reading.breadth_frac, th.breadth_enter - relief))


def _fast_path(reading: ShockReading, th: ShockThresholds, relief: float) -> bool:
    return (_meets(reading.breadth_frac, th.breadth_fast - relief)
            and _meets(reading.breadth_speed, th.speed_enter))


def entry_condition(reading: ShockReading, th: ShockThresholds = ShockThresholds()) -> bool:
    """NORMAL -> SHOCK on this one reading (breadth+depth or breadth+speed)."""
    relief = _relief(reading, th)
    return _depth_path(reading, th, relief) or _fast_path(reading, th, relief)


def _enter_shock(state: ShockState, reading: ShockReading) -> ShockState:
    return replace(state, label=SHOCK, since=reading.as_of, entry_streak=0, hold_since=None)


def _from_normal(state: ShockState, reading: ShockReading, th: ShockThresholds) -> ShockState:
    if not (_settled(reading, th) and entry_condition(reading, th)):
        return replace(state, entry_streak=0)
    if state.entry_streak + 1 >= 2:
        return _enter_shock(state, reading)
    return replace(state, entry_streak=state.entry_streak + 1)


def _hold(state: ShockState, reading: ShockReading, th: ShockThresholds) -> ShockState:
    return state


RULES: dict[str, Rule] = {NORMAL: _from_normal, SHOCK: _hold, RECOVERY: _hold}


def _carried_prev_close(state: ShockState, reading: ShockReading, new_session: bool):
    if reading.spy_prev_close is not None:
        return reading.spy_prev_close
    return None if new_session else state.spy_prev_close


def _carry(state: ShockState, reading: ShockReading) -> ShockState:
    """Overnight carry: the reading's session fields; per-session clocks restart."""
    new_session = state.session_date != reading.session_date
    return replace(
        state,
        session_date=reading.session_date,
        vix_session_high=reading.vix_session_high,
        spy_prev_close=_carried_prev_close(state, reading, new_session),
        prev_breadth=None if new_session else state.prev_breadth,
        hold_since=None if new_session else state.hold_since,
    )


def step(state: ShockState, reading: ShockReading,
         th: ShockThresholds = ShockThresholds()) -> ShockState:
    """Advance the state by one reading; an insufficient reading holds it."""
    if reading.insufficient:
        return state
    stepped = RULES[state.label](_carry(state, reading), reading, th)
    return replace(stepped, prev_breadth=reading.breadth_frac)

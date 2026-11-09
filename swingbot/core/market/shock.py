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

from dataclasses import dataclass, fields
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

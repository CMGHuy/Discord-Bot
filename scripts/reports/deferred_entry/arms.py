"""v229 arms (spec § Three simulated arms, § Frictions).

C: the trade's own entry, raced from the first bar starting at or after
opened_at. A: the open of the first bar starting at or after 15:30 ET on the
entry date. B: as A, skipped (0R) when any bar starting at or after opened_at
and STRICTLY BEFORE the 15:30 bar traded at or beyond the plan's original
stop. A and B keep the plan's stop and TP1 distances. Every arm's R is net,
through screen.sides.net_r, called once per arm here and nowhere else; the
deferred arms pay twice the entry slippage (a market order in the last half
hour). Zero frictions are refused."""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass

import pandas as pd

from swingbot import config
from swingbot.core.backtesting.screen.sides import net_r
from swingbot.core.edge.frictions import commission_r
from swingbot.core.market.strategy_types import BREAKEVEN_TRIGGER_FRACTION

from .bars import et_date
from .simulate import SIGN, Race, gross_r, race
from .verdict import FROZEN

ARMS = ("C", "A", "B")
NET_DIRECTION = {"bullish": "long", "bearish": "short"}
DEFERRED_BPS_MULT = 2
SKIPPED = "skipped"


class FrictionsError(RuntimeError):
    """Frictions are zero: a lift measured without costs is refused."""


def frictions_stamp() -> dict:
    """The cost inputs a pair's r_net depends on; stored on every pair row."""
    return {"slippage_bps": float(config.SLIPPAGE_BPS), "commission_r": float(commission_r()),
            "be_fraction": float(BREAKEVEN_TRIGGER_FRACTION)}


def assert_frictions() -> None:
    bps = float(getattr(config, "SLIPPAGE_BPS", 0.0) or 0.0)
    commission = commission_r()
    if bps <= 0 or commission <= 0:
        raise FrictionsError(f"zero frictions refused (SLIPPAGE_BPS={bps}, "
                             f"commission_r={commission})")
    if BREAKEVEN_TRIGGER_FRACTION != FROZEN["be_fraction"]:
        raise FrictionsError(f"be_fraction {BREAKEVEN_TRIGGER_FRACTION} differs from the "
                             f"frozen {FROZEN['be_fraction']}")


def shifted_levels(fill: float, *, entry: float, stop: float, tp1: float) -> tuple[float, float]:
    """The plan's stop and TP1 distances, carried to a new fill."""
    return fill - (entry - stop), fill + (tp1 - entry)


def held_touched(bars, *, direction: str, stop: float, start, deferral) -> bool:
    """Any bar with start <= index < deferral traded at or beyond ``stop``."""
    if bars is None or bars.empty:
        return False
    window = bars[(bars.index >= start) & (bars.index < deferral)]
    if window.empty:
        return False
    if SIGN[direction] > 0:
        return bool((window["Low"] <= stop).any())
    return bool((window["High"] >= stop).any())


def deferral_bar(bars, deferral, close) -> pd.Series | None:
    """The first bar with deferral <= index < close; ``.name`` is its start."""
    if bars is None or bars.empty or deferral is None:
        return None
    window = bars[(bars.index >= deferral) & (bars.index < close)]
    return None if window.empty else window.iloc[0]


@dataclass(frozen=True)
class ArmResult:
    arm: str
    taken: bool
    fill: float | None
    stop: float | None
    tp1: float | None
    outcome: str
    r_net: float
    r_gross: float
    exit_ts: str | None
    gap_stop: bool

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


def _calendar_days(direction: str, start_ts, result: Race) -> int:
    """Borrow days for a short, as the screen feeds net_r; a long never reads it."""
    if NET_DIRECTION[direction] == "long" or result.exit_ts is None:
        return 0
    return (et_date(result.exit_ts) - et_date(start_ts)).days


def _arm(name: str, result: Race, *, direction: str, fill: float, stop: float, tp1: float,
         risk: float, entry_bps, start_ts) -> ArmResult:
    r_net = 0.0
    if result.exit_price is not None:
        r_net = float(net_r(fill, result.exit_price, risk, direction=NET_DIRECTION[direction],
                            days=_calendar_days(direction, start_ts, result),
                            entry_bps=entry_bps))
    return ArmResult(
        arm=name, taken=True, fill=float(fill), stop=float(stop), tp1=float(tp1),
        outcome=result.outcome, r_net=r_net,
        r_gross=float(gross_r(result, direction=direction, fill=fill, risk=risk)),
        exit_ts=None if result.exit_ts is None else result.exit_ts.isoformat(),
        gap_stop=bool(result.gap_stop))


def _skipped() -> ArmResult:
    return ArmResult("B", False, None, None, None, SKIPPED, 0.0, 0.0, None, False)


def _checked(direction: str, entry: float, stop: float) -> float:
    if direction not in NET_DIRECTION:
        raise ValueError(f"unknown direction {direction!r}")
    risk = abs(float(entry) - float(stop))
    if risk <= 0:
        raise ValueError(f"zero risk: entry {entry} == stop {stop}")
    return risk


def price_arms(bars, *, direction: str, entry: float, stop: float, tp1: float,
               opened_at, deferral, close, end) -> dict[str, ArmResult]:
    """Arms C, A and B of one plan, each net of frictions."""
    assert_frictions()
    risk = _checked(direction, entry, stop)
    bar = deferral_bar(bars, deferral, close)
    if bar is None:
        raise ValueError("no deferral bar in [15:30 ET, close) on the entry date")
    fill = float(bar["Open"])
    a_stop, a_tp1 = shifted_levels(fill, entry=entry, stop=stop, tp1=tp1)
    control = race(bars, direction=direction, fill=entry, stop=stop, tp1=tp1,
                   start=opened_at, end=end)
    deferred = race(bars, direction=direction, fill=fill, stop=a_stop, tp1=a_tp1,
                    start=bar.name, end=end)
    late_bps = DEFERRED_BPS_MULT * float(config.SLIPPAGE_BPS)
    out = {
        "C": _arm("C", control, direction=direction, fill=entry, stop=stop, tp1=tp1,
                  risk=risk, entry_bps=None, start_ts=opened_at),
        "A": _arm("A", deferred, direction=direction, fill=fill, stop=a_stop, tp1=a_tp1,
                  risk=risk, entry_bps=late_bps, start_ts=bar.name),
    }
    touched = held_touched(bars, direction=direction, stop=stop, start=opened_at,
                           deferral=bar.name)
    out["B"] = _skipped() if touched else dataclasses.replace(out["A"], arm="B")
    return out

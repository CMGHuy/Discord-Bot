"""The one wording of the v191 ATR-band stop line.

Pure text shared by alerts and the plan page; imports nothing from scanning.
"""
from collections.abc import Mapping

from swingbot.core.market.strategy_types import HORIZONS
from swingbot.core.risk_limits import planned_loss_pct

_WHY = {"floor": "moved out to the ATR floor",
        "ceiling": "pulled in to the 2× ATR ceiling",
        "untouched": "at the level"}


def _field(plan, name):
    return plan.get(name) if isinstance(plan, Mapping) else getattr(plan, name, None)


def band_stop_line(plan, *, currency: str = "$") -> str | None:
    """Restate a band plan's stop, real TP1 R:R, horizon and expiry."""
    moved = _field(plan, "stop_moved_by")
    if moved is None:
        return None
    entry = _field(plan, "trigger_price")
    if entry is None:
        entry = _field(plan, "entry_price")
    stop, tp1 = _field(plan, "stop_loss"), _field(plan, "tp1")
    distance = abs(entry - stop)
    rr = abs(tp1 - entry) / distance if distance else 0.0
    decimals = 4 if entry < 1.0 else 2
    horizon = _field(plan, "horizon_key")
    label = HORIZONS.get(horizon, {}).get("label", horizon)
    return (f"ATR-band stop {currency}{stop:,.{decimals}f} "
            f"({planned_loss_pct(entry, stop):.2f}% from entry, {_WHY[moved]}) · "
            f"TP1 {rr:.2f}R · {label} · expires after {_field(plan, 'expiry_bars')} bars")

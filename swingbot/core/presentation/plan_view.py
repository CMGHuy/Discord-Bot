"""One pure derivation of a plan's display facts for every surface."""
from __future__ import annotations

from dataclasses import dataclass

from swingbot.core.planning.exit_sim import runner_floor


@dataclass(frozen=True)
class BarSpec:
    """A display bar whose percentages are already clamped to 0..100."""

    lo: float
    hi: float
    pos: float
    entry_pos: float | None = None


@dataclass(frozen=True)
class BankedLeg:
    fraction: float
    exit_price: float
    r: float


@dataclass(frozen=True)
class PlanView:
    """Display facts together with the provenance a renderer must label."""

    phase: str
    entry: float | None
    stop: float | None
    target: float | None
    target_is_banked_tp1: bool = False
    stop_kind: str = "risk"
    bar_kind: str = "none"
    bar: BarSpec | None = None
    banked: BankedLeg | None = None
    distance_to_trigger_r: float | None = None
    bars_to_expiry: int | None = None
    floor_r: float | None = None
    price_r: float | None = None
    headroom_r: float | None = None


def _risk(plan) -> float | None:
    """Return the plan risk in price units, or ``None`` for invalid risk."""
    reference = plan.entry_price if plan.entry_price is not None else plan.trigger_price
    if reference is None or plan.stop_loss is None:
        return None
    risk = abs(reference - plan.stop_loss)
    return risk or None


def _clamp_pct(value: float) -> float:
    return max(0.0, min(100.0, value))


def _pending_view(plan, price: float | None, bars_since_created: int | None) -> PlanView:
    bars_left = None
    if bars_since_created is not None and plan.expiry_bars is not None:
        # Lifecycle expiry is strictly greater than the budgeted bar count.
        bars_left = max(0, plan.expiry_bars - bars_since_created)

    risk = _risk(plan)
    if price is None or risk is None or plan.trigger_price is None:
        return PlanView(
            phase=plan.status,
            entry=None,
            stop=plan.stop_loss,
            target=plan.tp1,
            bars_to_expiry=bars_left,
        )

    sign = 1 if plan.direction == "bullish" else -1
    distance_r = (plan.trigger_price - price) * sign / risk
    return PlanView(
        phase=plan.status,
        entry=None,
        stop=plan.stop_loss,
        target=plan.tp1,
        bar_kind="approach",
        bar=BarSpec(
            lo=plan.trigger_price - sign * risk,
            hi=plan.trigger_price,
            pos=_clamp_pct((1.0 - distance_r) * 100.0),
        ),
        distance_to_trigger_r=distance_r,
        bars_to_expiry=bars_left,
    )


def plan_view(plan, *, price: float | None = None, now=None,
              bars_since_created: int | None = None) -> PlanView:
    """Project a plan into display facts without I/O, a clock, or a store."""
    del now  # The parameter keeps callers from needing a second projection API.
    if plan.status == "PENDING":
        return _pending_view(plan, price, bars_since_created)
    return PlanView(
        phase=plan.status,
        entry=plan.entry_price,
        stop=plan.stop_loss,
        target=plan.tp1,
    )

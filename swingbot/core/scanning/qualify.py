"""V118-7: the per-item gates after a scenario was scored, as one pure call.

`qualify_short_item(candidate, scenario, context)` runs, in the live merge's
order: direction (an extra-lane candidate is bearish only), the confirmation
debounce, sector RS, the RS gate, v2 plan construction and, when the caller
supplies it, the one-open-trade-per-ticker rule. It is the code the live SHORT
lane (`short_run._qualified_items`) runs and the code the historical replay
(`scan_replay`) runs, so the replay measures the live gates rather than a copy.

Purity: everything it reads arrives in `QualifyContext` -- as-of frames, the
benchmark, sector frames, regime, the confirmation store, the prior-open set
and the clock. It opens no network, journal, open-trade store or wall clock.
Config knobs (RS_GATE, RS_LAGGARD_PERCENTILE, PLAN_ENGINE_V2) are read the way
every gate reads them, which is what lets `apply_knobs()` vary them per arm.
The only mutation is on the supplied objects: the item and the confirmation
store (confirm, and revoke when the plan is rejected).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Mapping

from swingbot import config
from swingbot.core.edge.rs_gate import rs_verdict

from . import analyze

log = logging.getLogger(__name__)

BEARISH = "bearish"


@dataclass(frozen=True)
class Accepted:
    item: object


@dataclass(frozen=True)
class Rejected:
    item: object
    stage: str        # direction | confirmation | rs | plan | trade_decision
    reason: str


@dataclass(frozen=True)
class QualifyContext:
    frames: Mapping            # ticker -> as-of OHLCV frame (the plan's prices)
    spy: object                # benchmark frame, as of the same bar
    sector_of: Mapping         # ticker -> sector name (as of the decision date)
    etf_symbol_of: Mapping     # sector name -> sector ETF symbol
    sector_frames: Mapping     # sector ETF symbol -> as-of frame
    regime: object             # get_market_regime result for this scan
    regimes: object            # regime2 series (causal), or None
    breadth: float | None = None
    confirmations: object | None = None   # confirmation store; None = no debounce (`!check`)
    required_confirmations: int = 1
    open_tickers: frozenset | None = None  # prior-open state; None = the caller decides after dedup
    issued_at: str | None = None           # plan clock; None = wall clock (live only)
    now: object = None


def _confirmed(item, context: QualifyContext) -> str | None:
    """None when the item may proceed; else the confirmation stage's reason."""
    store = context.confirmations
    if store is None:
        return None
    if not item.all_requirements_met:
        return "unmet"
    item.previous_confirmed = store.confirmed_value(item.result.state_key)
    if store.confirm_or_update(item.result.state_key, item.result.state_value,
                               required_confirmations=context.required_confirmations):
        return None
    return "awaiting_confirmation"


def _rs_blocked(item) -> bool:
    if not config.RS_GATE:
        return False
    verdict = rs_verdict(
        item.result.ticker, item.result.trend,
        item.rs_combined if item.rs_combined is not None else 50.0,
        rs_available=item.rs_combined is not None)
    return verdict["status"] == "block"


def _attach_plan(item, context: QualifyContext) -> bool:
    """Build the v2 plan; False when it was rejected (the item must not alert)."""
    frame = context.frames.get(item.result.ticker)
    when = frame.index[-1] if frame is not None and len(frame) > 0 else None
    analyze.attach_plan_v2(
        item, item.plan, frame, item.result.ticker, item.result.horizon_key,
        level_map=item.level_map, regime=context.regime, rs_percentile=item.rs_percentile,
        breadth=context.breadth, regime2_state=analyze._regime_at(context.regimes, when),
        issued_at=context.issued_at, now=context.now)
    if item.plan_v2 is not None:
        item.plan_v2.regime_aligned = not (item.htf_info and item.htf_info.get("counter_trend", False))
    return not (config.PLAN_ENGINE_V2 == "on" and getattr(item, "plan_v2_rejected", None))


def _revoke(item, context: QualifyContext) -> None:
    """A confirmed setup whose plan was rejected must stay able to confirm later."""
    log.info("%s (%s, %s): plan rejected (%s, stop %.2f%% from entry) -- not posted",
             item.result.ticker, item.result.horizon_key, item.result.trend,
             item.plan_v2_rejected, getattr(item.plan, "stop_distance_pct", float("nan")))
    if context.confirmations is not None:
        context.confirmations.revoke_confirmation(
            item.result.state_key, item.result.state_value, item.previous_confirmed)


def qualify_short_item(candidate, scenario, context: QualifyContext) -> Accepted | Rejected:
    """Run one scored ScanItem (`scenario`) through the post-scoring gates.

    `candidate` is the extra lane's ShortCandidate, or None for a base item.
    """
    item = scenario
    if candidate is not None and item.result.trend != BEARISH:
        return Rejected(item, "direction", "not_bearish")
    reason = _confirmed(item, context)
    if reason is not None:
        return Rejected(item, "confirmation", reason)
    analyze._apply_sector_rs(item, item.result.ticker, context.sector_of, context.etf_symbol_of,
                             context.sector_frames, context.spy)
    item.breadth = context.breadth
    if _rs_blocked(item):
        return Rejected(item, "rs", "rs_blocked")
    if item.all_requirements_met and not _attach_plan(item, context):
        _revoke(item, context)
        return Rejected(item, "plan", item.plan_v2_rejected or "rejected")
    if context.open_tickers is not None and item.result.ticker in context.open_tickers:
        return Rejected(item, "trade_decision", "existing_trade")
    return Accepted(item)


_FUNNEL_STAGES = ("rs", "plan", "trade_decision")


def record_verdict(funnel, verdict) -> None:
    """The live funnel rows for one verdict: each stage reached, once.

    A confirmation or direction rejection never reached RS, so it records
    nothing (exactly as the live merge did before this helper existed). An
    accepted item stops at `plan`: its trade decision is recorded where the
    alert is built.
    """
    if funnel is None:
        return
    stage = getattr(verdict, "stage", None)
    if isinstance(verdict, Rejected) and stage not in _FUNNEL_STAGES:
        return
    for name in _FUNNEL_STAGES:
        if name == stage:
            funnel.record_item(verdict.item, name, verdict.reason)
            return
        if name == "trade_decision":
            return
        funnel.record_item(verdict.item, name)

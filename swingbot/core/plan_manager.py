"""Intraday plan-lifecycle manager: evolves the 60s trade_monitor into a
PENDING -> ACTIVE -> PARTIAL -> CLOSED state machine over PlanStore.

Live-price approximation: poll() sees one price per plan per tick, not a
bar -- the live price stands in for both bar High and bar Low in the Task
18 trigger semantics. Between polls a spike can be missed; that is the
same granularity limitation the existing trade_monitor already has, and
gap-aware fills (Task 67) handle the overnight case."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from swingbot.core.plan_engine import (PlanStatus, TradePlanV2,
                                       record_transition)
from swingbot.core.plan_store import PlanStore

log = logging.getLogger("swing-bot.plan_manager")


@dataclass
class PlanEvent:
    plan_id: str
    transition: str      # "filled"|"cancelled_expired"|"cancelled_invalidated"|
                         # "be_moved"|"tp1_partial"|"closed"
    detail: dict = field(default_factory=dict)


class PlanManager:
    def __init__(self, store: PlanStore, price_fn, bar_count_fn=None,
                 atr_fn=None, trade_log=None):
        self.store = store
        self.price_fn = price_fn            # ticker -> live float
        self.bar_count_fn = bar_count_fn    # (ticker, created_at) -> bars since
        self.atr_fn = atr_fn                # ticker -> current ATR(14) (Task 66)
        self.trade_log = trade_log          # TradeLog (Task 70)

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def poll(self) -> list[PlanEvent]:
        events: list[PlanEvent] = []
        for plan in self.store.open_plans():
            try:
                price = float(self.price_fn(plan.ticker))
            except Exception as exc:
                log.debug("poll: price fetch failed for %s: %s", plan.ticker, exc)
                continue
            if not price or price <= 0:
                continue
            try:
                events.extend(self._step(plan, price))
            except Exception:
                log.warning("poll: step failed for plan %s", plan.plan_id,
                            exc_info=True)
        return events

    # -- per-status handlers -------------------------------------------------

    def _step(self, plan: TradePlanV2, price: float) -> list[PlanEvent]:
        if plan.status == PlanStatus.PENDING:
            return self._step_pending(plan, price)
        if plan.status == PlanStatus.ACTIVE:
            return self._step_active(plan, price)     # Tasks 61-63
        if plan.status == PlanStatus.PARTIAL:
            return self._step_partial(plan, price)    # Tasks 64-66
        return []

    def _step_pending(self, plan: TradePlanV2, price: float) -> list[PlanEvent]:
        is_bull = plan.direction == "bullish"
        crossed = price >= plan.trigger_price if is_bull else price <= plan.trigger_price
        if crossed:
            fill = max(price, plan.trigger_price) if is_bull \
                else min(price, plan.trigger_price)
            plan.entry_price = fill
            record_transition(plan, PlanStatus.ACTIVE, reason="stop_entry_fill",
                              at=self._now())
            self.store.update(plan)
            return [PlanEvent(plan.plan_id, "filled",
                              {"entry_price": fill, "live_price": price})]
        # Task 59 (expiry) and Task 60 (invalidation) slot in here.
        return []

    def _step_active(self, plan: TradePlanV2, price: float) -> list[PlanEvent]:
        return []

    def _step_partial(self, plan: TradePlanV2, price: float) -> list[PlanEvent]:
        return []

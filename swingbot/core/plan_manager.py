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
                                       chandelier_stop, pending_expired,
                                       pending_invalidated, record_transition)
from swingbot.core.plan_store import PlanStore

log = logging.getLogger("swing-bot.plan_manager")


def gap_stop_fill(bar_open: float, level: float, direction: str) -> float:
    """A stop can't fill better than the open if the bar gapped past it --
    same convention as performance.update_open_trades."""
    return min(bar_open, level) if direction == "bullish" else max(bar_open, level)


def gap_target_fill(bar_open: float, level: float, direction: str) -> float:
    """A gap THROUGH the target fills at the better open."""
    return max(bar_open, level) if direction == "bullish" else min(bar_open, level)


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

        if self.bar_count_fn is not None:
            bars = self.bar_count_fn(plan.ticker, plan.created_at)
            if pending_expired(plan, bars):
                record_transition(plan, PlanStatus.CANCELLED, reason="expired",
                                  at=self._now())
                self.store.update(plan)
                return [PlanEvent(plan.plan_id, "cancelled_expired",
                                  {"bars_waited": bars})]

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

        if pending_invalidated(plan, price):
            record_transition(plan, PlanStatus.CANCELLED, reason="invalidated",
                              at=self._now())
            self.store.update(plan)
            return [PlanEvent(plan.plan_id, "cancelled_invalidated",
                              {"live_price": price})]
        return []

    def _step_active(self, plan: TradePlanV2, price: float) -> list[PlanEvent]:
        is_bull = plan.direction == "bullish"
        sign = 1 if is_bull else -1
        entry = plan.entry_price
        risk = abs(entry - plan.stop_loss)

        stop = plan.working_stop if plan.working_stop is not None else plan.stop_loss
        hit_stop = price <= stop if is_bull else price >= stop
        if hit_stop:
            reason = "scratch" if plan.working_stop is not None else "loss"
            record_transition(plan, PlanStatus.CLOSED, reason=reason, at=self._now())
            self.store.update(plan)
            return [PlanEvent(plan.plan_id, "closed",
                              {"reason": reason, "exit_price": price})]

        hit_tp1 = price >= plan.tp1 if is_bull else price <= plan.tp1
        if hit_tp1:
            # A stop-limit sell can't fill BETTER than the observed live
            # price -- the observed price IS the fill (may exceed tp1 on a
            # gap up: a real, favorable fill, not clamped to tp1).
            fill = price
            r1 = (fill - entry) * sign / risk if risk > 0 else 0.0
            leg = {"fraction": plan.tp1_fraction, "exit_price": fill,
                   "r": r1, "reason": "tp1"}
            plan.legs_realized.append(leg)
            plan.working_stop = entry                     # runner floor = BE
            record_transition(plan, PlanStatus.PARTIAL, reason="tp1_partial",
                              at=self._now())
            self.store.update(plan)
            return [PlanEvent(plan.plan_id, "tp1_partial", dict(leg))]

        target_dist = abs(plan.tp1 - entry)
        be_trigger = entry + sign * plan.breakeven_trigger_fraction * target_dist
        reached_be = price >= be_trigger if is_bull else price <= be_trigger
        if reached_be and plan.working_stop is None:
            plan.working_stop = entry
            self.store.update(plan)
            return [PlanEvent(plan.plan_id, "be_moved",
                              {"working_stop": entry, "live_price": price})]
        return []

    def _step_partial(self, plan: TradePlanV2, price: float) -> list[PlanEvent]:
        is_bull = plan.direction == "bullish"
        sign = 1 if is_bull else -1
        entry = plan.entry_price
        risk = abs(entry - plan.stop_loss)
        stop = plan.working_stop if plan.working_stop is not None else entry

        hit_stop = price <= stop if is_bull else price >= stop
        if hit_stop:
            reason = "tp1_runner_be" if stop == entry else "tp1_runner_trail"
            return self._close_runner(plan, price, reason, risk, sign)

        if plan.tp2 is not None:
            hit_tp2 = price >= plan.tp2 if is_bull else price <= plan.tp2
            if hit_tp2:
                return self._close_runner(plan, price, "tp1_runner_tp2", risk, sign)

        if self.atr_fn is not None:
            extreme = plan.runner_high_close
            extreme = price if extreme is None else (max(extreme, price) if is_bull
                                                     else min(extreme, price))
            if extreme != plan.runner_high_close:
                plan.runner_high_close = extreme
                atr_val = float(self.atr_fn(plan.ticker))
                trail = chandelier_stop(extreme, atr_val, plan.trail_atr_mult,
                                        plan.direction)
                floor = plan.working_stop if plan.working_stop is not None else entry
                new_stop = max(floor, trail) if is_bull else min(floor, trail)
                if new_stop != plan.working_stop:
                    plan.working_stop = new_stop
                self.store.update(plan)
        return []

    def _close_runner(self, plan: TradePlanV2, fill: float, reason: str,
                      risk: float, sign: int) -> list[PlanEvent]:
        r2 = (fill - plan.entry_price) * sign / risk if risk > 0 else 0.0
        leg = {"fraction": 1.0 - plan.tp1_fraction, "exit_price": fill,
               "r": r2, "reason": reason}
        plan.legs_realized.append(leg)
        record_transition(plan, PlanStatus.CLOSED, reason=reason, at=self._now())
        self.store.update(plan)
        return [PlanEvent(plan.plan_id, "closed",
                          {"reason": reason, "exit_price": fill, "leg": leg})]

    # -- overnight/session-open bar check (Task 67) --------------------------
    #
    # Same gap-fill convention as performance.update_open_trades (and the
    # tick-poll fills above): a stop/target can't fill better than the bar's
    # open if the bar gapped past it; a same-bar stop+target touch resolves
    # stop-first (conservative ordering).

    def check_bar(self, plan_id: str, bar_open: float, bar_high: float,
                  bar_low: float) -> list[PlanEvent]:
        plan = self.store.get(plan_id)
        if plan is None:
            return []
        if plan.status == PlanStatus.ACTIVE:
            return self._check_bar_active(plan, bar_open, bar_high, bar_low)
        if plan.status == PlanStatus.PARTIAL:
            return self._check_bar_partial(plan, bar_open, bar_high, bar_low)
        return []

    def _check_bar_active(self, plan: TradePlanV2, bar_open: float,
                          bar_high: float, bar_low: float) -> list[PlanEvent]:
        is_bull = plan.direction == "bullish"
        sign = 1 if is_bull else -1
        entry = plan.entry_price
        risk = abs(entry - plan.stop_loss)
        stop = plan.working_stop if plan.working_stop is not None else plan.stop_loss

        hit_stop = bar_low <= stop if is_bull else bar_high >= stop
        if hit_stop:
            fill = gap_stop_fill(bar_open, stop, plan.direction)
            reason = "scratch" if plan.working_stop is not None else "loss"
            r = (fill - entry) * sign / risk if risk > 0 else 0.0
            leg = {"fraction": 1.0, "exit_price": fill, "r": r, "reason": reason}
            plan.legs_realized.append(leg)
            record_transition(plan, PlanStatus.CLOSED, reason=reason, at=self._now())
            self.store.update(plan)
            return [PlanEvent(plan.plan_id, "closed",
                              {"reason": reason, "exit_price": fill})]

        hit_tp1 = bar_high >= plan.tp1 if is_bull else bar_low <= plan.tp1
        if hit_tp1:
            fill = gap_target_fill(bar_open, plan.tp1, plan.direction)
            r1 = (fill - entry) * sign / risk if risk > 0 else 0.0
            leg = {"fraction": plan.tp1_fraction, "exit_price": fill,
                   "r": r1, "reason": "tp1"}
            plan.legs_realized.append(leg)
            plan.working_stop = entry
            record_transition(plan, PlanStatus.PARTIAL, reason="tp1_partial",
                              at=self._now())
            self.store.update(plan)
            return [PlanEvent(plan.plan_id, "tp1_partial", dict(leg))]
        return []

    def _check_bar_partial(self, plan: TradePlanV2, bar_open: float,
                           bar_high: float, bar_low: float) -> list[PlanEvent]:
        is_bull = plan.direction == "bullish"
        sign = 1 if is_bull else -1
        risk = abs(plan.entry_price - plan.stop_loss)
        stop = plan.working_stop if plan.working_stop is not None else plan.entry_price

        hit_stop = bar_low <= stop if is_bull else bar_high >= stop
        if hit_stop:
            fill = gap_stop_fill(bar_open, stop, plan.direction)
            reason = "tp1_runner_be" if stop == plan.entry_price else "tp1_runner_trail"
            return self._close_runner(plan, fill, reason, risk, sign)

        if plan.tp2 is not None:
            hit_tp2 = bar_high >= plan.tp2 if is_bull else bar_low <= plan.tp2
            if hit_tp2:
                fill = gap_target_fill(bar_open, plan.tp2, plan.direction)
                return self._close_runner(plan, fill, "tp1_runner_tp2", risk, sign)
        return []

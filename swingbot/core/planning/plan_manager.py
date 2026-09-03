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

from swingbot import config
from swingbot.core.market.session import is_regular_session, session_date
from swingbot.core.planning.plan_engine import (PlanStatus, TradePlanV2,
                                       chandelier_stop, pending_expired,
                                       pending_invalidated, record_transition,
                                       runner_floor)
from swingbot.core.planning.plan_store import PlanStore

log = logging.getLogger("swing-bot.plan_manager")


def gap_stop_fill(bar_open: float, level: float, direction: str) -> float:
    """A stop can't fill better than the open if the bar gapped past it --
    same convention as performance.update_open_trades."""
    return min(bar_open, level) if direction == "bullish" else max(bar_open, level)


def gap_target_fill(bar_open: float, level: float, direction: str) -> float:
    """A gap THROUGH the target fills at the better open."""
    return max(bar_open, level) if direction == "bullish" else min(bar_open, level)


def poll_stop_fill(price: float, stop: float, continuous: bool) -> float:
    return stop if continuous else price


@dataclass
class PlanEvent:
    plan_id: str
    transition: str      # "filled"|"cancelled_expired"|"cancelled_invalidated"|
                         # "be_moved"|"tp1_partial"|"closed"|"pyramid_add"
    detail: dict = field(default_factory=dict)


# Below this the suggested add is too small to be worth acting on -- a
# 3%-of-position add is noise once real commissions are paid.
PYRAMID_MIN_FRACTION = 0.05
PYRAMID_MAX_FRACTION = 0.50


def pyramid_add_fraction(plan) -> float:
    """The largest add that keeps the campaign at or above breakeven on a
    clean stop-out, as a fraction of the ORIGINAL position size.

    Derivation (bullish; the short side mirrors exactly). At the moment
    everything stops -- remainder at breakeven, add at the original entry
    -- the campaign is worth::

        banked   = tp1_fraction * (tp1 - entry)      # already realized
        remainder= 0                                 # stopped at breakeven
        add      = -f * (trigger - entry) = -f * R    # trigger is entry + 1R

    so `banked - f*R >= 0` iff `f <= tp1_fraction * (tp1 - entry) / R`.

    The plan's own numbers are used rather than a fixed R:R constant, so the
    bound stays correct regardless of which real level TP1 landed on (v31)
    or whether it was re-priced. A FIXED 0.5 add -- the size this rule is
    usually quoted with -- would violate the bound whenever TP1 sits below
    1R (tp1_fraction * R:R < 0.5 for any R:R under 1.0/tp1_fraction) and
    turn a winning campaign into a losing one on a clean stop-out; deriving
    the ceiling from the plan avoids depending on which regime TP1 pricing
    is in at all.
    """
    risk = abs(plan.entry_price - plan.stop_loss)
    if risk <= 0:
        return 0.0
    banked_r = plan.tp1_fraction * abs(plan.tp1 - plan.entry_price) / risk
    return min(banked_r, PYRAMID_MAX_FRACTION)


def maybe_pyramid(plan, price: float) -> dict | None:
    """Add size at +1R with the add's stop at the ORIGINAL entry. Only from
    PARTIAL (TP1 banked, remainder stopped at the v39 runner floor -- the
    derivation below still assumes plain breakeven, which is now a strictly
    conservative floor rather than the exact one, so the bound holds).

    A PURE DECISION, and a suggestion only -- the bot never sizes real
    money. 1R is taken from `abs(entry_price - stop_loss)`: TradePlanV2 has
    no `risk_per_share` field, and `stop_loss` is safe to read here because
    the breakeven move writes `working_stop` and never mutates it.

    RISK PROPERTIES, all three pinned by tests rather than asserted here:

      1. A clean stop-out -- remainder at breakeven, add at the original
         entry, no gap -- nets >= breakeven on the whole campaign. True by
         construction, because the add is sized by pyramid_add_fraction().
      2. Even a gap all the way to the plan's ORIGINAL stop leaves the
         campaign better than that plan's own original 1R risk.
      3. A gap BEYOND the original stop is unbounded, exactly as it is for
         any stop-based rule. Pyramiding does not create that exposure but
         it does scale it, and no sizing rule can remove it.

    Returns None when the derived add would be smaller than
    PYRAMID_MIN_FRACTION: a plan whose TP1 banked too little to pay for any
    meaningful add should not pyramid at all.
    """
    if getattr(plan, "status", None) != "PARTIAL":
        return None
    bull = plan.direction == "bullish"
    risk = abs(plan.entry_price - plan.stop_loss)
    if risk <= 0:
        return None
    fraction = pyramid_add_fraction(plan)
    if fraction < PYRAMID_MIN_FRACTION:
        return None
    trigger = plan.entry_price + risk if bull else plan.entry_price - risk
    if (price >= trigger) if bull else (price <= trigger):
        return {"add_shares_fraction": round(fraction, 4), "add_entry": price,
                "add_stop": plan.entry_price}
    return None


class PlanManager:
    def __init__(self, store: PlanStore, price_fn, bar_count_fn=None,
                 atr_fn=None, trade_log=None):
        self.store = store
        self.price_fn = price_fn            # ticker -> live float
        self.bar_count_fn = bar_count_fn    # (ticker, created_at) -> bars since
        self.atr_fn = atr_fn                # ticker -> current ATR(14) (Task 66)
        self.trade_log = trade_log          # TradeLog (Task 70)
        self._last_seen: dict[str, tuple[str, float]] = {}
        # v70: plan_id -> (breach kind, consecutive confirming extended-hours
        # ticks). In-memory only, for the same reason _last_seen is: persisting
        # it would turn every 60s poll into a disk write where only a
        # transition writes today. A restart empties it, so the first tick
        # after a restart always needs a fresh confirmation -- the
        # conservative direction.
        self._eh_breach_streak: dict[str, tuple[str, int]] = {}

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def poll(self, now=None) -> list[PlanEvent]:
        if config.INTRADAY_RTH_ONLY and not is_regular_session(now):
            return []
        # `self.store` (and `self.trade_log`) can be long-lived instances --
        # the module singleton `_MANAGER` below keeps both for the
        # process's whole life -- so reload each from disk first. Otherwise
        # a plan added by some OTHER PlanStore instance since our last tick
        # is invisible here AND any write this tick performs (on either
        # store) clobbers the file with a stale snapshot, erasing whatever
        # a different instance wrote elsewhere in the meantime. See
        # PlanStore.reload() / TradeLog.reload()'s docstrings.
        self.store.reload()
        if self.trade_log is not None:
            self.trade_log.reload()
        events: list[PlanEvent] = []
        for plan in self.store.open_plans():
            try:
                price = float(self.price_fn(plan.ticker))
            except Exception as exc:
                log.debug("poll: price fetch failed for %s: %s", plan.ticker, exc)
                continue
            if not price or price <= 0:
                continue
            # price_fn may block long enough for the scan loop to persist a new
            # plan. Reload before any _step() write so update() merges with that
            # current on-disk store instead of serializing a stale snapshot.
            self.store.reload()
            try:
                new_events = self._step(plan, price, now)
            except Exception:
                log.warning("poll: step failed for plan %s", plan.plan_id,
                            exc_info=True)
                continue
            self._last_seen[plan.plan_id] = (session_date(now), price)
            for event in new_events:
                self._on_event(plan, event)
            events.extend(new_events)
        return events

    def _on_event(self, plan: TradePlanV2, event: PlanEvent) -> None:
        if self.trade_log is None:
            return
        try:
            if event.transition == "filled":
                trade_id = self.trade_log.log_trade(
                    ticker=plan.ticker, strategy=plan.strategy,
                    horizon_key=plan.horizon_key, direction=plan.direction,
                    # v32 Task 11: plan.confidence_level now exists (set at
                    # plan-build time by _apply_quality), so this stop-entry
                    # fill can pass the real level instead of a hardcoded
                    # None -- confidence_label isn't stored on the plan, so
                    # that half stays None.
                    confidence_level=plan.confidence_level, confidence_label=None,
                    entry=plan.entry_price, stop_loss=plan.stop_loss,
                    take_profit=plan.tp1, target2=plan.tp2,
                    plan_id=plan.plan_id, badge=plan.badge,
                    quality_score=plan.quality_score, source=plan.source)
                event.detail["trade_id"] = trade_id
            elif event.transition == "tp1_partial":
                self.trade_log.append_leg_by_plan(plan.plan_id, event.detail)
            elif event.transition == "closed":
                reason = event.detail["reason"]
                status = ("win" if reason.startswith("tp1_")
                          else "loss" if reason == "loss" else "closed")
                leg = event.detail.get("leg")
                if leg is None:
                    # Pre-TP1 loss/scratch closes the ORIGINAL single
                    # position -- synthesize a fraction=1.0 leg from the
                    # plan's own entry/stop (the event carries no r-multiple).
                    is_bull = plan.direction == "bullish"
                    sign = 1 if is_bull else -1
                    risk = abs(plan.entry_price - plan.stop_loss)
                    exit_price = event.detail["exit_price"]
                    r = (exit_price - plan.entry_price) * sign / risk if risk > 0 else 0.0
                    leg = {"fraction": 1.0, "exit_price": exit_price,
                          "r": r, "reason": reason}
                self.trade_log.close_plan_trade(plan.plan_id, leg, status)
        except Exception:
            log.warning("trade-log hook failed for plan %s", plan.plan_id,
                        exc_info=True)   # bookkeeping must never break the manager

    def _continuous(self, plan: TradePlanV2, stop: float, now=None) -> bool:
        seen = self._last_seen.get(plan.plan_id)
        if seen is None or seen[0] != session_date(now):
            return False
        return seen[1] > stop if plan.direction == 'bullish' else seen[1] < stop

    # -- per-status handlers -------------------------------------------------

    def _step(self, plan: TradePlanV2, price: float, now=None) -> list[PlanEvent]:
        if plan.status == PlanStatus.PENDING:
            return self._step_pending(plan, price)
        if plan.status == PlanStatus.ACTIVE:
            return self._step_active(plan, price, now)     # Tasks 61-63
        if plan.status == PlanStatus.PARTIAL:
            return self._step_partial(plan, price, now)    # Tasks 64-66
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

    def _active_stop(self, plan: TradePlanV2, now=None) -> tuple[float, bool]:
        if plan.working_stop is None:
            return plan.stop_loss, False
        if plan.be_armed_session == session_date(now):
            return plan.stop_loss, False
        return plan.working_stop, True
    def _step_active(self, plan: TradePlanV2, price: float, now=None) -> list[PlanEvent]:
        is_bull = plan.direction == "bullish"
        sign = 1 if is_bull else -1
        entry = plan.entry_price
        risk = abs(entry - plan.stop_loss)

        stop, is_be_stop = self._active_stop(plan, now)
        hit_stop = price <= stop if is_bull else price >= stop
        if hit_stop:
            reason = "scratch" if is_be_stop else "loss"
            fill = poll_stop_fill(price, stop, self._continuous(plan, stop, now))
            record_transition(plan, PlanStatus.CLOSED, reason=reason, at=self._now())
            self.store.update(plan)
            return [PlanEvent(plan.plan_id, "closed",
                              {"reason": reason, "exit_price": fill})]

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
            plan.working_stop = runner_floor(entry, plan.tp1)   # v39 runner floor
            plan.runner_floor_session = session_date(now)
            record_transition(plan, PlanStatus.PARTIAL, reason="tp1_partial",
                              at=self._now())
            self.store.update(plan)
            return [PlanEvent(plan.plan_id, "tp1_partial", dict(leg))]

        target_dist = abs(plan.tp1 - entry)
        be_trigger = entry + sign * plan.breakeven_trigger_fraction * target_dist
        reached_be = price >= be_trigger if is_bull else price <= be_trigger
        if reached_be and plan.working_stop is None:
            plan.working_stop = entry
            plan.be_armed_session = session_date(now)
            self.store.update(plan)
            return [PlanEvent(plan.plan_id, "be_moved",
                              {"working_stop": entry, "live_price": price})]
        return []

    def _step_partial(self, plan: TradePlanV2, price: float, now=None) -> list[PlanEvent]:
        is_bull = plan.direction == "bullish"
        sign = 1 if is_bull else -1
        entry = plan.entry_price
        risk = abs(entry - plan.stop_loss)
        # A PARTIAL plan always has working_stop set (the TP1 branch above
        # writes it). The fallback only fires for a plan persisted to
        # data/plans.json before v39; using the floor there tightens those
        # legacy runners too, and keeps the reason label below correct.
        stop = (plan.working_stop if plan.working_stop is not None
                else runner_floor(entry, plan.tp1))

        # Pyramiding (edge E38), flag-gated OFF and at most once per plan.
        # Emits a SUGGESTION only: no leg is realized, no stop is moved, no
        # status changes -- the Discord layer posts it and the operator
        # decides. Checked before the stop/TP2 branches so it can't fire on
        # the same tick that closes the runner.
        if config.PYRAMIDING_ENABLED and plan.pyramid_add is None:
            add = maybe_pyramid(plan, price)
            if add is not None:
                plan.pyramid_add = add
                self.store.update(plan)
                return [PlanEvent(plan.plan_id, "pyramid_add", dict(add))]

        hit_stop = (price <= stop if is_bull else price >= stop) and plan.runner_floor_session != session_date(now)
        if hit_stop:
            # v39: "tp1_runner_be" now means "closed at the initial post-TP1
            # floor", not literally at entry. The string is unchanged on
            # purpose -- see the same note in plan_engine._scale_out_exit_walk.
            reason = ("tp1_runner_be" if stop == runner_floor(entry, plan.tp1)
                      else "tp1_runner_trail")
            return self._close_runner(plan, price, reason, risk, sign)

        if plan.tp2 is not None and plan.runner_floor_session != session_date(now):
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
                floor = (plan.working_stop if plan.working_stop is not None
                         else runner_floor(entry, plan.tp1))
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

    # -- extended-hours terminal exits (v70) --------------------------------
    #
    # Reached only from poll()'s extended-hours branch: RTH gate on, clock
    # outside 09:30-16:00 ET, outside quiet hours. The ONLY outcome this
    # path can produce is a terminal close of a plan that has unambiguously
    # finished -- no pending fills, no break-even arming, no TP1 partial
    # while a tp2 remains, no chandelier ratchet. Everything else stays
    # where v64 put it: regular hours only.

    def _step_extended(self, plan: TradePlanV2, price: float, now=None) -> list[PlanEvent]:
        if plan.status == PlanStatus.ACTIVE:
            candidate = self._extended_candidate_active(plan, price, now)
        elif plan.status == PlanStatus.PARTIAL:
            candidate = self._extended_candidate_partial(plan, price, now)
        else:
            candidate = None            # PENDING (and anything else): inert
        key = plan.plan_id
        if candidate is None:
            # Pop, never decrement: one reverting print resets the count
            # completely rather than leaving a partial streak a later,
            # unrelated breach could complete early.
            self._eh_breach_streak.pop(key, None)
            return []
        kind, close = candidate
        seen_kind, streak = self._eh_breach_streak.get(key, (None, 0))
        streak = streak + 1 if seen_kind == kind else 1
        if streak < config.EXTENDED_HOURS_DEBOUNCE_TICKS:
            self._eh_breach_streak[key] = (kind, streak)
            return []
        self._eh_breach_streak.pop(key, None)
        return close()

    def _extended_candidate_active(self, plan: TradePlanV2, price: float, now=None):
        """(kind, close) for an ACTIVE plan that has finished, else None.

        Mirrors _step_active's stop and TP1 comparisons exactly -- including
        _active_stop's session guard -- but returns a callable instead of
        acting, so the debounce lives in one place rather than per branch.

        Returns status-aware kind strings ("active_stop"/"tp1") to prevent
        cross-status collision: a leftover ACTIVE-stop streak cannot be
        completed by an unrelated PARTIAL-stop breach on the same plan_id."""
        is_bull = plan.direction == "bullish"
        stop, is_be_stop = self._active_stop(plan, now)
        hit_stop = price <= stop if is_bull else price >= stop
        if hit_stop:
            reason = "scratch" if is_be_stop else "loss"
            return ("active_stop", lambda: self._close_extended(plan, price, reason))
        if plan.tp2 is not None:
            # TP1 with a second leg still to run is a PARTIAL transition,
            # not a finish -- and banking a partial is regular-hours work.
            return None
        hit_tp1 = price >= plan.tp1 if is_bull else price <= plan.tp1
        if hit_tp1:
            return ("tp1", lambda: self._close_extended(plan, price, "win"))
        return None

    def _extended_candidate_partial(self, plan: TradePlanV2, price: float, now=None):
        """(kind, close) for a PARTIAL plan whose runner has finished, else
        None. Mirrors _step_partial's stop and TP2 comparisons, including
        v64's runner_floor_session guard; the pyramid suggestion and the
        chandelier ratchet are deliberately absent.

        Returns status-aware kind strings ("partial_stop"/"tp2") to prevent
        cross-status collision: a leftover ACTIVE-stop streak cannot be
        completed by an unrelated PARTIAL-stop breach on the same plan_id."""
        if plan.runner_floor_session == session_date(now):
            return None
        is_bull = plan.direction == "bullish"
        sign = 1 if is_bull else -1
        entry = plan.entry_price
        risk = abs(entry - plan.stop_loss)
        stop = (plan.working_stop if plan.working_stop is not None
                else runner_floor(entry, plan.tp1))
        hit_stop = price <= stop if is_bull else price >= stop
        if hit_stop:
            reason = ("tp1_runner_be" if stop == runner_floor(entry, plan.tp1)
                      else "tp1_runner_trail")
            return ("partial_stop",
                    lambda: self._close_runner(plan, price, reason, risk, sign))
        if plan.tp2 is not None:
            hit_tp2 = price >= plan.tp2 if is_bull else price <= plan.tp2
            if hit_tp2:
                return ("tp2", lambda: self._close_runner(
                    plan, price, "tp1_runner_tp2", risk, sign))
        return None

    def _close_extended(self, plan: TradePlanV2, price: float,
                        reason: str) -> list[PlanEvent]:
        """Terminal close of a whole (pre-TP1) position at the confirming
        tick's price. Fills at `price`, never at the nominal level: the same
        "never record a better fill than what was actually seen" convention
        performance.py and trade_monitor already use. _on_event synthesizes
        the fraction=1.0 leg from the plan's own entry/stop."""
        record_transition(plan, PlanStatus.CLOSED, reason=reason, at=self._now())
        self.store.update(plan)
        return [PlanEvent(plan.plan_id, "closed",
                          {"reason": reason, "exit_price": price})]

    # -- overnight/session-open bar check (Task 67) --------------------------
    # UNWIRED: production exits exclusively through poll(); see known-traps.md.
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
            events = self._check_bar_active(plan, bar_open, bar_high, bar_low)
        elif plan.status == PlanStatus.PARTIAL:
            events = self._check_bar_partial(plan, bar_open, bar_high, bar_low)
        else:
            events = []
        for event in events:
            self._on_event(plan, event)
        return events

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
            plan.working_stop = runner_floor(entry, plan.tp1)   # v39 runner floor
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
        stop = (plan.working_stop if plan.working_stop is not None
                else runner_floor(plan.entry_price, plan.tp1))

        hit_stop = bar_low <= stop if is_bull else bar_high >= stop
        if hit_stop:
            fill = gap_stop_fill(bar_open, stop, plan.direction)
            # v39: "tp1_runner_be" == "closed at the initial post-TP1 floor".
            reason = ("tp1_runner_be"
                      if stop == runner_floor(plan.entry_price, plan.tp1)
                      else "tp1_runner_trail")
            return self._close_runner(plan, fill, reason, risk, sign)

        if plan.tp2 is not None:
            hit_tp2 = bar_high >= plan.tp2 if is_bull else bar_low <= plan.tp2
            if hit_tp2:
                fill = gap_target_fill(bar_open, plan.tp2, plan.direction)
                return self._close_runner(plan, fill, "tp1_runner_tp2", risk, sign)
        return []


# -- module singleton wiring the manager into the 60s trade_monitor loop -----
# (Task 71) -- INTRADAY_MANAGER_V2 flag off is a pure no-op: no PlanStore
# instantiation, no data/plans.json file created.

_MANAGER: PlanManager | None = None


def _price_fn(ticker):                      # module-level so tests can patch it
    from swingbot.core.marketdata.data import get_current_price
    return get_current_price(ticker)


def _live_atr(ticker):
    from swingbot.core.marketdata.data import get_daily_data
    from swingbot.core.market.indicators import atr
    df = get_daily_data(ticker)
    return float(atr(df, 14).iloc[-1])


def _bars_since(ticker, created_at):
    from swingbot.core.marketdata.data import get_daily_data
    df = get_daily_data(ticker)
    return int((df.index.tz_localize(None) > created_at).sum()) \
        if df.index.tz is None else int((df.index > created_at).sum())


def run_manager_tick() -> list[PlanEvent]:
    """One synchronous manager tick -- the trade_monitor loop calls this via
    asyncio.to_thread. Flag off = pure no-op (no store instantiation, no
    file creation)."""
    global _MANAGER
    from swingbot import config
    if not config.INTRADAY_MANAGER_V2:
        return []
    if _MANAGER is None:
        from swingbot.core.tracking.performance import TradeLog
        _MANAGER = PlanManager(PlanStore(), _price_fn, atr_fn=_live_atr,
                               bar_count_fn=_bars_since, trade_log=TradeLog())
    # Production reads the wall clock; poll's optional clock is test injection.
    return _MANAGER.poll()


RECYCLE_PROGRESS_R = 0.3


def recycle_candidates(plans: list, prices: dict) -> list:
    """Positions past their strategy's time stop with <0.3R to show for it.
    Advice-only: the notice says 'this capital is statistically dead',
    the operator decides."""
    import datetime as dt
    out = []
    today = dt.date.today()
    for p in plans:
        if getattr(p, "status", None) not in ("ACTIVE", "PARTIAL"):
            continue
        ts_days = getattr(p, "time_stop_days", None)
        price = prices.get(p.ticker)
        if ts_days is None or price is None or not getattr(p, "activated_at", None):
            continue
        age = (today - dt.date.fromisoformat(p.activated_at[:10])).days
        if age <= ts_days:
            continue
        sign = 1 if p.direction == "bullish" else -1
        progress = (price - p.entry_price) * sign / p.risk_per_share
        if progress < RECYCLE_PROGRESS_R:
            out.append({"plan_id": p.plan_id, "ticker": p.ticker,
                        "age_days": age, "progress_r": round(progress, 3)})
    return out

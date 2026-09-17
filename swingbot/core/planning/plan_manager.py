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
from datetime import datetime, timedelta, timezone
from typing import NamedTuple

from swingbot import config
from swingbot.core.market.session import (is_quiet_hours, is_regular_session,
                                          is_tape_open, session_date)
from swingbot.core.risk_limits import (HARD_MAX_PLANNED_LOSS_PCT,
                                       planned_loss_pct)
from swingbot.core.planning.plan_engine import (PlanStatus, TradePlanV2,
                                       chandelier_stop, pending_expired,
                                       pending_invalidated, record_transition,
                                       runner_floor)
from swingbot.core.planning.plan_store import PlanStore
from swingbot.core.planning.plan_types import breakeven_trigger, effective_stop

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
                         # "cancelled_risk_cap"|"be_moved"|"tp1_partial"|
                         # "closed"|"pyramid_add"
    detail: dict = field(default_factory=dict)


# v81 execution feed. Stop events tell the reader where to rest the stop and
# are acknowledged through plan.notified_stop; notice events are queued on
# plan.pending_notice and re-sent until acknowledged. Neither field is read
# by any exit path (tests/planning/test_plan_manager_feed.py pins that).
STOP_EVENTS = frozenset({"be_moved", "tp1_partial", "stop_moved"})
NOTICE_EVENTS = frozenset({"filled", "cancelled_expired", "cancelled_invalidated", "closed"})
NOTICE_RESEND_DAYS = 5


def trail_notify_min_r() -> float:
    """config.TRAIL_NOTIFY_MIN_R clamped to its safe range."""
    return min(1.0, max(0.01, float(config.TRAIL_NOTIFY_MIN_R)))


def last_told_stop(plan) -> float:
    """The stop last delivered to the reader; the ticket delivered stop_loss."""
    return plan.notified_stop if plan.notified_stop is not None else plan.stop_loss


def resting_stop(plan) -> float:
    """The stop the reader should leave resting, matching the exit check."""
    if plan.status == PlanStatus.PARTIAL and plan.working_stop is None:
        return runner_floor(plan.entry_price, plan.tp1)
    return effective_stop(plan)


def _stop_at_close(plan) -> float:
    """The stop the bot was holding when the plan closed."""
    if plan.working_stop is not None:
        return plan.working_stop
    if plan.legs_realized:
        return runner_floor(plan.entry_price, plan.tp1)
    return plan.stop_loss


def stop_move_event(plan, today_session: str, min_r: float) -> PlanEvent | None:
    """Emit stop_moved when the resting stop has changed by at least min_r."""
    if plan.entry_price is None or plan.status not in (PlanStatus.ACTIVE, PlanStatus.PARTIAL):
        return None
    risk = abs(plan.entry_price - plan.stop_loss)
    if risk <= 0:
        return None
    sign = 1 if plan.direction == "bullish" else -1
    old, new = last_told_stop(plan), resting_stop(plan)
    r_moved = (new - old) * sign / risk
    if abs(r_moved) < min_r - 1e-9:
        return None
    effective = ("next_session" if plan.status == PlanStatus.ACTIVE
                 and plan.be_armed_session == today_session else "now")
    return PlanEvent(plan.plan_id, "stop_moved",
                     {"old": old, "new": new, "r_moved": r_moved, "effective": effective})


class Delivery(NamedTuple):
    """One execution-feed message that reached a notifying channel."""

    plan_id: str
    kind: str       # "stop" | "notice"
    value: object   # delivered stop price, or delivered notice transition


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
                 atr_fn=None, trade_log=None, price_batch_fn=None):
        self.store = store
        self.price_fn = price_fn            # ticker -> live float
        # Optional on purpose: the deterministic unit-test feeds only expose
        # a one-ticker callable.  Production supplies the batch function so
        # one manager tick does not make one network request per open plan.
        self.price_batch_fn = price_batch_fn  # [ticker] -> {ticker: live float}
        self.bar_count_fn = bar_count_fn    # (ticker, created_at) -> bars since
        self.atr_fn = atr_fn                # ticker -> current ATR(14) (Task 66)
        self.trade_log = trade_log          # TradeLog (Task 70)
        self._last_seen: dict[str, tuple[str, float]] = {}
        self._risk_cap_warned: set[str] = set()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def resend_notices(self, *, reload: bool = True) -> list[PlanEvent]:
        """Re-emit unacknowledged notices, dropping ones older than five days."""
        if reload:
            self.store.reload()
        cutoff = datetime.now(timezone.utc) - timedelta(days=NOTICE_RESEND_DAYS)
        events: list[PlanEvent] = []
        for plan in self.store.all():
            notice = plan.pending_notice
            if not notice:
                continue
            try:
                queued = datetime.fromisoformat(notice["at"])
                if queued.tzinfo is None:
                    queued = queued.replace(tzinfo=timezone.utc)
            except (KeyError, TypeError, ValueError):
                queued = None
            if queued is None or queued < cutoff:
                log.warning("execution feed: dropping undelivered %s for plan %s (queued %s)",
                            notice.get("transition"), plan.plan_id, notice.get("at"))
                plan.pending_notice = None
                self.store.update(plan)
                continue
            events.append(PlanEvent(plan.plan_id, notice["transition"],
                                    dict(notice["detail"])))
        return events

    def _feed_bookkeeping(self, plan: TradePlanV2, new_events: list[PlanEvent],
                          regular: bool, now=None) -> list[PlanEvent]:
        """Stamp and queue feed events after ordinary lifecycle bookkeeping."""
        for event in new_events:
            if event.transition == "tp1_partial":
                event.detail["working_stop"] = plan.working_stop
            elif event.transition == "closed":
                event.detail["session"] = "regular" if regular else "extended"
                event.detail["notified_stop"] = last_told_stop(plan)
                event.detail["bot_stop"] = _stop_at_close(plan)
        notices = [event for event in new_events if event.transition in NOTICE_EVENTS]
        if notices:
            latest = notices[-1]
            plan.pending_notice = {"transition": latest.transition,
                                   "detail": dict(latest.detail), "at": self._now()}
            self.store.update(plan)
        if not regular or any(event.transition in STOP_EVENTS | NOTICE_EVENTS
                              for event in new_events):
            return new_events
        moved = stop_move_event(plan, session_date(now), trail_notify_min_r())
        return new_events + [moved] if moved is not None else new_events

    def poll(self, now=None) -> list[PlanEvent]:
        # One gate, and only one (2026-09-14, on direct request): the
        # operator's quiet window. Outside it, the FULL state machine runs
        # on every tick -- break-even arming, TP1 partial-banking, the
        # chandelier ratchet, pyramiding, entry fills, closes -- with no
        # narrower extended-hours mode in between.
        #
        # Through v70 there WAS such a mode: anything outside true NYSE RTH
        # got a debounced, terminal-closes-only `_step_extended`, which
        # existed to avoid "Divergence B" (see
        # docs/superpowers/specs/implemented/2026-09-03-v70-extended-hours-exit-check-design.md
        # SS1.2) -- a single thin extended-hours print once armed break-even
        # permanently or closed a position outright, on a print the
        # daily-bar backtest never modeled. The operator was shown that
        # incident and chose the full machine across the whole Berlin-local
        # window anyway, so that mode and its debounce are gone rather than
        # left sitting unreachable.
        #
        # What did NOT come with it: the claim that every tick in this
        # window is a live tape print. See `is_tape_open` below.
        #
        # INTRADAY_RTH_ONLY=false is still the documented pre-v64 escape
        # hatch -- every tick, round the clock, no quiet-hours gate either.
        if config.INTRADAY_RTH_ONLY and is_quiet_hours(now):
            return []
        # v81: true NYSE RTH, not the wider tape/quiet windows above -- a
        # resting broker stop order only fires during regular hours, so the
        # feed's session label and stop-move notices key off this, not off
        # whether _step() ran (which no longer distinguishes RTH at all).
        # INTRADAY_RTH_ONLY=false is still the pre-v64 escape hatch: no RTH
        # distinction at all, so this is unconditionally "regular" there too.
        regular = is_regular_session(now) if config.INTRADAY_RTH_ONLY else True
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
        events: list[PlanEvent] = self.resend_notices(reload=False)
        open_plans = self.store.open_plans()
        prices: dict[str, float] | None = None
        if self.price_batch_fn is not None and open_plans:
            tickers = list(dict.fromkeys(plan.ticker for plan in open_plans))
            try:
                prices = self.price_batch_fn(tickers) or {}
            except Exception as exc:
                # No per-plan fallback here: the point of batching is to
                # bound the tick, and a failed fresh batch must not turn into
                # stale or serial quote requests that delay every plan.
                log.debug("poll: batch price fetch failed: %s", exc)
                prices = {}
        for plan in open_plans:
            if prices is not None:
                price = prices.get(plan.ticker)
            else:
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
            # Step the plan as it is NOW, not the copy open_plans() handed out
            # before this and every earlier plan's price fetch. The admin UI
            # closes and cancels plans from its own process; stepping the stale
            # copy wrote it back over that change and resurrected the plan.
            plan = self.store.get(plan.plan_id)
            if plan is None or plan.status not in (
                    PlanStatus.PENDING, PlanStatus.ACTIVE, PlanStatus.PARTIAL):
                continue
            self._warn_legacy_open_risk(plan)
            try:
                new_events = self._step(plan, price, now)
            except Exception:
                log.warning("poll: step failed for plan %s", plan.plan_id,
                            exc_info=True)
                continue
            if is_tape_open(now):
                # Prints from a LIVE TAPE only -- not merely "a tick we
                # took". _last_seen feeds _continuous(), which lets a stop
                # breach fill AT the stop rather than at the observed
                # price, on the claim that we watched the tape cross it.
                #
                # `is_tape_open`, deliberately, not the poll window: the
                # window is "not quiet hours", which in Berlin terms opens
                # at 08:00 -- 02:00 ET, two hours before any tape exists.
                # get_current_price uses prepost=True and returns
                # YESTERDAY's last after-hours print at that hour, which
                # this would otherwise record as today's watched price.
                # A plan whose stop then gapped through at the 09:30 open
                # filled AT the stop instead of at the gap -- a better
                # exit than anything that ever traded, written into the
                # trade log as realised P&L (found by audit, 2026-09-14,
                # introduced the same day by widening the poll window).
                if plan.first_seen_price is None:
                    plan.first_seen_price = float(price)
                    self.store.update(plan)
                self._last_seen[plan.plan_id] = (session_date(now), price)
            for event in new_events:
                self._on_event(plan, event)
            events.extend(self._feed_bookkeeping(plan, new_events, regular, now))
        return events

    def _warn_legacy_open_risk(self, plan: TradePlanV2) -> None:
        """Log once for a pre-cap live plan without changing the position.

        Existing positions may have been accepted before the 2% policy. A
        warning makes them visible to the operator, but silently moving their
        stop or closing them would be an unapproved trading decision.
        """
        if plan.status not in (PlanStatus.ACTIVE, PlanStatus.PARTIAL):
            return
        risk_pct = planned_loss_pct(plan.entry_price, plan.stop_loss)
        if risk_pct <= HARD_MAX_PLANNED_LOSS_PCT or plan.plan_id in self._risk_cap_warned:
            return
        self._risk_cap_warned.add(plan.plan_id)
        log.warning(
            "risk cap: active plan %s (%s) has a %.2f%% initial stop, above the %.2f%% cap; "
            "leaving the existing position unchanged",
            plan.plan_id, plan.ticker, risk_pct, HARD_MAX_PLANNED_LOSS_PCT,
        )

    def _on_event(self, plan: TradePlanV2, event: PlanEvent) -> None:
        if self.trade_log is None:
            return
        try:
            if event.transition == "filled":
                # scan_run.py already logged a placeholder trade for this
                # plan_id the moment the stop_entry setup was first detected
                # (still PENDING, sized against the trigger price) -- this is
                # that same trade catching up to the real fill, not a new
                # position. record_plan_fill() finds it by plan_id and moves
                # its entry (and resized shares) onto plan.entry_price.
                # log_trade()-ing a SECOND record here (the old behaviour)
                # left two open trades sharing one plan_id: close_plan_trade()
                # only ever finds and closes the first, so the second -- the
                # one the admin UI's plan/trade join actually shows, since
                # that join keeps the LAST trade per plan_id -- never closed,
                # no matter what price did (production incident, 2026-09-10:
                # QCOM sat "open" well past its armed stop indefinitely).
                trade_id = self.trade_log.record_plan_fill(
                    plan.plan_id, plan.entry_price)
                if trade_id is None:
                    # No placeholder found -- plan reached the store some
                    # other way than the normal scan_run.py alert path.
                    # Log it now so the fill is never silently unrecorded.
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
                        quality_score=plan.quality_score, source=plan.source,
                        cohort_label=plan.cohort_label, cohort_stats=plan.cohort_stats,
                        risk_features=plan.risk_features)
                event.detail["trade_id"] = trade_id
            elif event.transition == "tp1_partial":
                self.trade_log.append_leg_by_plan(plan.plan_id, event.detail)
            elif event.transition in ("cancelled_expired", "cancelled_invalidated",
                                      "cancelled_risk_cap"):
                # A PENDING plan never filled -- scan_run.py's placeholder
                # trade for it (still open, sized against the trigger price)
                # has no real position behind it. Left unhandled, it sat
                # "open" in the dashboard/risk numbers forever: production
                # incident, 2026-09-11 (INTU, META among 10 stuck trades
                # found via a dashboard mismatch -- the other 8 were the
                # separate double-logging bug 5d72c1ab already fixed).
                self.trade_log.discard_plan_placeholder(plan.plan_id)
            elif event.transition == "closed":
                if event.detail.get("_terminal_persisted"):
                    return
                reason = event.detail["reason"]
                # "win" is v70's terminal-target reason: an ACTIVE plan with
                # no tp2 whose tp1 was confirmed outside regular hours closes
                # the whole position at its last remaining target.
                status = ("win" if reason == "win" or reason.startswith("tp1_")
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

    def _persist_terminal(self, plan: TradePlanV2, leg: dict, status: str) -> bool:
        """Persist a terminal plan and its linked trade as one DB transaction."""
        from swingbot.core.db import stages
        if (self.trade_log is not None and stages.reads_db("plans")
                and stages.reads_db("trades")):
            from swingbot.core.db.engine import transaction
            with transaction() as conn:
                self.store.update(plan, conn=conn)
                self.trade_log.close_plan_trade(plan.plan_id, leg, status, conn=conn)
            return True
        self.store.update(plan)
        return False

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
            risk_pct = planned_loss_pct(fill, plan.stop_loss)
            if risk_pct > HARD_MAX_PLANNED_LOSS_PCT:
                record_transition(plan, PlanStatus.CANCELLED, reason="risk_cap",
                                  at=self._now())
                self.store.update(plan)
                return [PlanEvent(plan.plan_id, "cancelled_risk_cap", {
                    "entry_price": fill,
                    "stop_loss": plan.stop_loss,
                    "planned_loss_pct": round(risk_pct, 4),
                    "max_planned_loss_pct": HARD_MAX_PLANNED_LOSS_PCT,
                })]
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
            leg = {"fraction": 1.0, "exit_price": fill,
                   "r": (fill - entry) * sign / risk if risk > 0 else 0.0,
                   "reason": reason}
            persisted = self._persist_terminal(plan, leg, "loss" if reason == "loss" else "closed")
            return [PlanEvent(plan.plan_id, "closed",
                              {"reason": reason, "exit_price": fill, "leg": leg,
                               "_terminal_persisted": persisted})]

        hit_tp1 = price >= plan.tp1 if is_bull else price <= plan.tp1
        if hit_tp1:
            # A stop-limit sell can't fill BETTER than the observed live
            # price -- the observed price IS the fill (may exceed tp1 on a
            # gap up: a real, favorable fill, not clamped to tp1).
            fill = price
            r1 = (fill - entry) * sign / risk if risk > 0 else 0.0
            at = self._now()
            leg = {"fraction": plan.tp1_fraction, "exit_price": fill,
                   "r": r1, "reason": "tp1", "closed_at": at}
            plan.legs_realized.append(leg)
            plan.working_stop = runner_floor(entry, plan.tp1)   # v39 runner floor
            plan.runner_floor_session = session_date(now)
            record_transition(plan, PlanStatus.PARTIAL, reason="tp1_partial",
                              at=at)
            self.store.update(plan)
            return [PlanEvent(plan.plan_id, "tp1_partial", dict(leg))]

        be_trigger = breakeven_trigger(plan, entry)
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

        # No same-session guard here (removed 2026-09-10, trader decision):
        # v64 suppressed both checks for the rest of the session TP1 fired
        # in, to match a bar-based backtest that can't see intraday
        # sequencing within the fill bar. Live paid for that parity in real
        # money -- a runner that spiked through TP2 and back the same
        # afternoon TP1 hit (NBIS, 2026-09-08) never auto-closed and had to
        # be closed manually. Both now fire the instant price crosses,
        # same session or not; `runner_floor_session` is still stamped
        # (other callers/tests read it) but no longer gates either check.
        hit_stop = price <= stop if is_bull else price >= stop
        if hit_stop:
            # v39: "tp1_runner_be" now means "closed at the initial post-TP1
            # floor", not literally at entry. The string is unchanged on
            # purpose -- see the same note in plan_engine._scale_out_exit_walk.
            reason = ("tp1_runner_be" if stop == runner_floor(entry, plan.tp1)
                      else "tp1_runner_trail")
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
        at = self._now()
        leg = {"fraction": 1.0 - plan.tp1_fraction, "exit_price": fill,
               "r": r2, "reason": reason, "closed_at": at}
        plan.legs_realized.append(leg)
        record_transition(plan, PlanStatus.CLOSED, reason=reason, at=at)
        persisted = self._persist_terminal(plan, leg, "win" if reason.startswith("tp1_") else "closed")
        return [PlanEvent(plan.plan_id, "closed",
                          {"reason": reason, "exit_price": fill, "leg": leg,
                           "_terminal_persisted": persisted})]

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
            persisted = self._persist_terminal(plan, leg, "loss" if reason == "loss" else "closed")
            return [PlanEvent(plan.plan_id, "closed",
                              {"reason": reason, "exit_price": fill, "leg": leg,
                               "_terminal_persisted": persisted})]

        hit_tp1 = bar_high >= plan.tp1 if is_bull else bar_low <= plan.tp1
        if hit_tp1:
            fill = gap_target_fill(bar_open, plan.tp1, plan.direction)
            r1 = (fill - entry) * sign / risk if risk > 0 else 0.0
            at = self._now()
            leg = {"fraction": plan.tp1_fraction, "exit_price": fill,
                   "r": r1, "reason": "tp1", "closed_at": at}
            plan.legs_realized.append(leg)
            plan.working_stop = runner_floor(entry, plan.tp1)   # v39 runner floor
            record_transition(plan, PlanStatus.PARTIAL, reason="tp1_partial",
                              at=at)
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
    # Never a stale cached print: this feeds live stop/target decisions, and
    # a repeated cached value would read as a fresh tick confirming a level
    # the tape may have left minutes ago.
    return get_current_price(ticker, allow_stale=False)


def _price_batch_fn(tickers):
    """Fresh-only price map for plan transitions; never fall back to UI data."""
    from swingbot.core.marketdata.data import get_current_price_batch
    return get_current_price_batch(tickers, allow_stale=False)


# Retain the serial seam for deterministic callers/tests that replace
# ``_price_fn``.  Supplying the production batch implementation beside a
# custom feed would bypass that feed and unexpectedly make live requests.
_DEFAULT_PRICE_FN = _price_fn


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


def _manager() -> PlanManager:
    """The process-wide PlanManager, built on first use."""
    global _MANAGER
    if _MANAGER is None:
        from swingbot.core.tracking.performance import TradeLog
        batch_fn = _price_batch_fn if _price_fn is _DEFAULT_PRICE_FN else None
        _MANAGER = PlanManager(PlanStore(), _price_fn, atr_fn=_live_atr,
                               bar_count_fn=_bars_since, trade_log=TradeLog(),
                               price_batch_fn=batch_fn)
    return _MANAGER


def run_manager_tick() -> list[PlanEvent]:
    """One synchronous manager tick -- the trade_monitor loop calls this via
    asyncio.to_thread. Flag off = pure no-op (no store instantiation, no
    file creation)."""
    from swingbot import config
    if not config.INTRADAY_MANAGER_V2:
        return []
    # Production reads the wall clock; poll's optional clock is test injection.
    return _manager().poll()


def run_notice_sweep() -> list[PlanEvent]:
    """Re-send notices while no open position exists; this fetches no prices."""
    from swingbot import config
    if not config.INTRADAY_MANAGER_V2:
        return []
    return _manager().resend_notices()


def ack_notified(deliveries) -> None:
    """Record execution-feed deliveries through the manager-owned plan store."""
    if not deliveries:
        return
    store = _MANAGER.store if _MANAGER is not None else PlanStore()
    store.reload()
    for delivery in deliveries:
        plan = store.get(delivery.plan_id)
        if plan is None:
            continue
        if delivery.kind == "stop":
            plan.notified_stop = float(delivery.value)
        elif delivery.kind == "notice":
            notice = plan.pending_notice
            if not notice or notice.get("transition") != delivery.value:
                continue
            plan.pending_notice = None
        else:
            continue
        store.update(plan)


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

"""Pure scan/monitor-path gate decision functions (G120, G121, G128, G134).

Deliberately core (no Discord dependency): `swingbot/core/scanning/engine.py`
and `swingbot/core/plan_manager.py` both import straight from here so the
real wiring never depends on `swingbot/commands/scanning.py` (the Discord
command layer) -- see docs/claude/architecture.md's core/commands split.
`swingbot/commands/scanning.py` re-exports these same names so tests that
call `scanning.gate_candidate(...)` etc. exercise the identical objects.

Every function here is exception-free by construction (pure data in, data
out) -- the try/except guarding a gate bug from ever costing an alert or a
fill lives at the call sites in engine.py / plan_manager.py, not here.
"""
from __future__ import annotations

import datetime as dt


def blackout_decision(macro_snap: dict | None, now: dt.datetime) -> dict | None:
    """The G120 rule in one pure function. None -> no blackout applies.
    {"action": "annotate", "line": ...} -> alert ships with the warning line
    (the DEFAULT -- inform-first). {"action": "hold", "line", "release_at"}
    only when GATE_BLACKOUT_ENFORCE is also on and the event calendar is
    fresh (snapshot built within the last 7 days).

    Reads the REAL snapshot shape built by core.macro.snapshot.build_snapshot:
    macro_snap["events"]["next_high_impact"] is the next importance-3 event
    (or None), each event shaped {"date", "time_et", "kind", "label",
    "importance"} (core.macro.calendar_events). There is no per-event
    "upcoming list" or "refreshed_at" field in the real snapshot -- the whole
    snapshot's own "built_at" is used as the freshness proxy for the event
    calendar, since ensure_fresh_snapshot() refreshes the forward event
    schedule at most once per day as part of every snapshot rebuild.
    """
    import swingbot.config as config

    if not getattr(config, "GATE_BLACKOUT_ENABLED", False) or not macro_snap:
        return None
    events = macro_snap.get("events") or {}
    ev = events.get("next_high_impact")
    if not ev or int(ev.get("importance", 0)) < 3:
        # build_snapshot already only ever populates next_high_impact with
        # importance==3 events -- this guard is defense in depth against a
        # hand-built or malformed snapshot, not something real traffic hits.
        return None

    before = float(getattr(config, "GATE_BLACKOUT_HOURS_BEFORE", 24.0))
    after = float(getattr(config, "GATE_BLACKOUT_HOURS_AFTER", 2.0))

    if now.tzinfo is None:
        now = now.replace(tzinfo=dt.timezone.utc)

    from swingbot.core.macro.calendar_events import hours_until
    try:
        hrs = hours_until(ev, now)
    except (KeyError, ValueError):
        return None
    if not (-after <= hrs <= before):
        return None

    label = ev.get("label") or str(ev.get("kind", "event")).upper()
    time_et = ev.get("time_et", "")
    try:
        ev_date = dt.date.fromisoformat(ev["date"])
        day_word = "today" if ev_date == now.date() else "tomorrow" if \
            ev_date == now.date() + dt.timedelta(days=1) else ev["date"]
    except (KeyError, ValueError, TypeError):
        day_word = "soon"
    line = (f"⚠️ {label} {time_et} ET {day_word} — historically "
            f"whipsaw-prone; consider waiting for the print")

    if getattr(config, "GATE_BLACKOUT_ENFORCE", False):
        fresh = True
        built_at = macro_snap.get("built_at")
        try:
            built = dt.datetime.fromisoformat(built_at)
            if built.tzinfo is None:
                built = built.replace(tzinfo=dt.timezone.utc)
            fresh = (now - built).days <= 7
        except (TypeError, ValueError):
            fresh = False
        if fresh:
            release_at = _event_dt(ev) + dt.timedelta(hours=after)
            return {"action": "hold", "line": line,
                   "event": label, "release_at": release_at.isoformat()}
        import logging
        logging.getLogger("swing-bot.gate.blackout").warning(
            "event calendar stale (> 7 days) — blackout holding "
            "auto-disabled, annotating instead")
    return {"action": "annotate", "line": line, "event": label}


def _event_dt(ev: dict) -> dt.datetime:
    from swingbot.core.macro.calendar_events import _event_dt_utc
    return _event_dt_utc(ev)


def _unknown_dominated(result, max_unknown_weight_pct: float = 50.0) -> bool:
    """True when more than half the checklist's weight answered "unknown"
    -- a tier earned by missing data, not observed failures. Such a result
    NEVER blocks (extends the G43 darkness proof through the gate)."""
    total = sum(c.weight for c in result.checks) or 1.0
    unknown = sum(c.weight for c in result.checks if c.status == "unknown")
    return 100.0 * unknown / total > max_unknown_weight_pct


def gate_candidate(result, mode: str, min_tier: str):
    """The single scan-path decision point, unifying the decision policy
    (G76's with_advisory) with the darkness guarantee: shadow/inform ALWAYS
    pass (invariant 1); enforce may block, but never on an
    unknown-dominated result (invariant 2). Returns (decision,
    result-with-advisory)."""
    from swingbot.core.gate.score import with_advisory
    decision, out = with_advisory(result, mode, min_tier)
    if decision == "block" and _unknown_dominated(out):
        import logging
        logging.getLogger("swing-bot.gate").warning(
            "gate: %s %s would block on unknown-dominated evidence — "
            "passing instead (unknown never blocks)", out.ticker, out.strategy)
        decision = "pass"
    return decision, out


def recheck_delta(stored_gate: dict | None, new_result) -> list[str]:
    """Flags that fired at trigger time but NOT at alert time -- the only
    thing worth interrupting the operator for. The signal was checked when
    it alerted; the world may have changed since."""
    known = {c["check_id"] for c in (stored_gate or {}).get("checks", [])
             if c.get("status") in ("fail", "warn")}
    return [c.check_id for c in new_result.checks
            if c.status in ("fail", "warn") and c.check_id not in known]


def compose_size_multipliers(*mults) -> float:
    """G134: the drawdown throttle's multiplier (edge E46) and any tier
    sizing multiplier compose MULTIPLICATIVELY, floored at 0. None entries
    mean "no opinion" (x1) -- so either feature works alone."""
    out = 1.0
    for m in mults:
        if m is not None:
            out *= max(0.0, float(m))
    return max(0.0, out)


def entry_allowed_with_killswitch(kill_active: bool, gate_decision: str) -> bool:
    """G134 precedence: the kill switch (edge E47) outranks ANY gate
    verdict -- an A+ tier never overrides "no new entries". Gate evaluation
    still runs upstream (annotation + evidence continue); only the entry
    decision defers. A gate block stays a block either way."""
    if kill_active:
        return False
    return gate_decision != "block"

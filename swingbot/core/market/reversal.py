"""Should an open trade be cut short and flipped to the opposite side?

One pure decision, deliberately kept out of the scan engine: the engine is
large and stateful, whereas this answers a single question and can be tested
exhaustively with no scan, no price feed and no Discord client. Nothing here
performs I/O or mutates anything -- the caller acts on the verdict.

"No longer valid" is defined narrowly and on purpose: it means the opposite
setup qualifies under the bar the bot ALREADY demands of any new trade
(`all_requirements_met`). No separate invalidation model is invented here.
`pending_invalidated()` in plan_engine.py is a different thing -- it cancels
a plan that broke before it ever filled.

The four guards exist because a reversal rule with no brakes bleeds money in
chop: every oscillation pays the spread and books a scratch. Defaults are
conservative (one flip per ticker per day, only after a full day held, and
only for a clearly better setup).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class ReversalDecision:
    """Verdict plus the reason, which is logged and shown in the scan funnel
    so a *blocked* flip is explainable rather than silently absent."""
    allowed: bool
    reason: str

    def __bool__(self) -> bool:
        return self.allowed


def _parse(ts) -> datetime | None:
    if not ts:
        return None
    if isinstance(ts, datetime):
        dt = ts
    else:
        try:
            dt = datetime.fromisoformat(str(ts))
        except (TypeError, ValueError):
            return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def evaluate_reversal(
    existing: dict,
    candidate_direction: str,
    candidate_score: float | None,
    *,
    now: datetime,
    recent_flips: list,
    enabled: bool = True,
    min_hold_hours: float = 24.0,
    cooldown_hours: float = 48.0,
    min_conf_margin: float = 10.0,
    max_per_day: int = 1,
) -> ReversalDecision:
    """Decide whether `existing` may be closed early and flipped.

    `recent_flips` is the list of previously reversed trades for this ticker
    (closed trades carrying close_reason="reversed"); their `closed_at`
    timestamps drive both the cooldown and the daily cap, so no new state
    file is needed to track flip history.

    The caller is still responsible for the checks this cannot see -- that
    the candidate met every scan requirement, and that this is an automatic
    scan rather than an on-demand !check.
    """
    if not enabled:
        return ReversalDecision(False, "reversal disabled")

    if not existing or existing.get("status") != "open":
        return ReversalDecision(False, "no open trade to reverse")

    if not candidate_direction or candidate_direction == existing.get("direction"):
        # Same-direction duplicates are blocked by the ticker guard, not here.
        return ReversalDecision(False, "candidate is not the opposite direction")

    opened = _parse(existing.get("opened_at"))
    if opened is None:
        # Unknown age: refuse rather than assume it is old enough to flip.
        return ReversalDecision(False, "open trade has no usable opened_at")
    held_hours = (now - opened).total_seconds() / 3600.0
    if held_hours < min_hold_hours:
        return ReversalDecision(
            False, f"held {held_hours:.1f}h < {min_hold_hours:.1f}h minimum")

    flip_times = sorted(
        (d for d in (_parse(f.get("closed_at")) for f in recent_flips) if d), reverse=True)

    if flip_times and (now - flip_times[0]).total_seconds() / 3600.0 < cooldown_hours:
        since = (now - flip_times[0]).total_seconds() / 3600.0
        return ReversalDecision(
            False, f"last reversal {since:.1f}h ago < {cooldown_hours:.1f}h cooldown")

    today = now.date()
    if sum(1 for d in flip_times if d.date() == today) >= max_per_day:
        return ReversalDecision(False, f"already reversed {max_per_day}x today")

    existing_score = existing.get("confidence_score")
    if candidate_score is None or existing_score is None:
        # Without both scores the margin is unverifiable; refuse rather than
        # let an unscored setup flip a scored position.
        return ReversalDecision(False, "confidence score unavailable on both sides")
    if candidate_score < existing_score + min_conf_margin:
        return ReversalDecision(
            False,
            f"candidate score {candidate_score:.0f} < {existing_score:.0f}"
            f" + {min_conf_margin:.0f} margin")

    return ReversalDecision(
        True,
        f"opposite {candidate_direction} setup scores {candidate_score:.0f}"
        f" vs {existing_score:.0f}, held {held_hours:.1f}h")


def reversals_for_ticker(closed_trades: list, ticker: str) -> list:
    """Previously reversed trades for `ticker`, newest first -- the
    `recent_flips` argument above. Derived from the trade log rather than a
    separate store: a reversal already leaves close_reason="reversed" behind."""
    return sorted(
        (t for t in closed_trades
         if t.get("ticker") == ticker and t.get("close_reason") == "reversed"),
        key=lambda t: t.get("closed_at") or "",
        reverse=True,
    )

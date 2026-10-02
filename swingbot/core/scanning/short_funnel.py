"""V118-5: a direction/source/mode funnel with stable stage and rejection names.

Counted by tuple (direction, source, mode, stage, reason) so the base lane's LONG
and SHORT scenarios and each extra mode read off one scheme. A stage is recorded
once per item when reached: "ok" when it passed, a stable reason when it was the
rejection (a scenario that fails geometry never also counts as an RS rejection).

Thread rule: `_scan_one` runs in `map_tickers()` workers and never touches a
`ShortFunnel`. It returns immutable event tuples; the scan runner merges them
serially after the join.
"""
from collections import Counter
from dataclasses import dataclass, field

STAGES = ("candidate", "aligned", "scenario", "geometry", "confidence",
          "rs", "plan", "trade_decision", "dedup", "send")

BEARISH = "bearish"
BASE_SOURCE = "base"
EXTRA_SOURCE = "short_universe"
UNSELECTED = "unselected"          # mode of a symbol that never got a weakness mode

# requirement key -> the stage that rejects it
_REQUIREMENT_STAGE = {
    "min_reward": "geometry", "min_stop_distance": "geometry",
    "max_stop_distance": "geometry", "min_risk_reward": "geometry",
    "min_confluence": "confidence", "min_confidence": "confidence",
    "opex_close_window": "confidence",
}
_DECISION_REASON = {"already open": "existing_trade"}


@dataclass
class ShortFunnel:
    counts: Counter = field(default_factory=Counter)

    def record(self, direction: str, source: str, mode: str | None,
               stage: str, reason: str | None = None) -> None:
        if stage not in STAGES:
            raise ValueError(stage)
        self.counts[(direction, source, mode or "base", stage, reason or "ok")] += 1

    def merge(self, events) -> None:
        """Fold (direction, source, mode, stage, reason) tuples in, serially."""
        for event in events:
            self.record(*event)

    def record_item(self, item, stage: str, reason: str | None = None) -> None:
        self.record(*item_key(item), stage, reason)

    def record_decision(self, item) -> None:
        """The trade decision: `existing_trade`, `unmet` or ok."""
        self.record_item(item, "trade_decision", decision_reason(item))

    def record_dedup(self, items, kept) -> None:
        """Every item reaching dedup is counted once: kept, or merged into another."""
        kept_ids = {id(item) for item in kept}
        for item in items:
            self.record_item(item, "dedup", None if id(item) in kept_ids else "merged")

    def snapshot(self) -> dict[str, int]:
        return {"/".join(key): value for key, value in sorted(self.counts.items())}


def item_key(item) -> tuple[str, str, str | None]:
    """(direction, source, mode) of a ScanItem; an item with no context is base."""
    context = getattr(item, "candidate_context", None) or {}
    return (item.result.trend, context.get("source", BASE_SOURCE), context.get("mode"))


def decision_reason(item) -> str | None:
    reason = getattr(item, "not_logged_reason", None)
    if getattr(item, "paper_logged", False) or reason is None:
        return None
    return _DECISION_REASON.get(reason, "unmet")


def candidate_context(candidate) -> dict:
    """The facts an emitted item keeps about the candidate that produced it."""
    return {"source": candidate.source, "mode": candidate.mode,
            "reference_id": candidate.reference_id,
            "decision_bar_date": candidate.decision_bar_date}


def scenario_events(direction, source, mode, requirements) -> list:
    """scenario, then geometry and confidence, stopping at the first rejection."""
    events = [(direction, source, mode, "scenario", None)]
    failed = {}
    for requirement in requirements:
        if not requirement.passed:
            failed.setdefault(_REQUIREMENT_STAGE.get(requirement.key, "confidence"), requirement.key)
    for stage in ("geometry", "confidence"):
        reason = failed.get(stage)
        events.append((direction, source, mode, stage, reason))
        if reason is not None:
            break
    return events

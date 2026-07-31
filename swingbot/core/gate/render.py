"""Checklist Discord embed string builders (G123). Pure display formatting
-- never changes any verdict, only how one is rendered.

Note: the original plan's Task G82 (which this module folds into) was cut
by the 2026-07 win-rate audit ("pure display formatting, doesn't change any
verdict"). It survives here as the minimum G123 actually needs to render
the checklist/red-flag fields on the alert embed -- nothing more.
"""
from __future__ import annotations

from swingbot.core.gate.types import GateResult

# Human-readable labels for the 8 red-flag detectors (redflags.py) -- the
# check_id itself (e.g. "rf_fake_breakout") is what the registry/telemetry/
# blocked log use; this is ONLY for the embed's red-flag table.
_REDFLAG_LABELS = {
    "rf_fake_breakout": "Fake breakout",
    "rf_stop_sweep": "Stop sweep",
    "rf_dead_cat": "Dead-cat bounce",
    "rf_divergence_trap": "Divergence trap",
    "rf_extreme_fade": "Extreme fade",
    "rf_news_whipsaw": "News whipsaw",
    "rf_thin_session": "Thin session",
    "rf_beta_move": "Beta move",
}

_STATUS_ICON = {"fail": "⛔", "warn": "⚠️", "pass": "✅", "unknown": "❔"}


def checklist_field(result: GateResult) -> tuple[str, str]:
    """(name, value) for the main checklist field: tier + score in the
    name (so it's visible even collapsed), pass/warn/fail/unknown counts
    plus hard-block/stale callouts in the value."""
    name = f"📋 Checklist — {result.tier} ({result.score:.0f})"
    counts = {"pass": 0, "warn": 0, "fail": 0, "unknown": 0}
    for c in result.checks:
        counts[c.status] = counts.get(c.status, 0) + 1
    lines = [f"✅ {counts['pass']} pass · ⚠️ {counts['warn']} warn · "
             f"⛔ {counts['fail']} fail · ❔ {counts['unknown']} unknown"]
    if result.hard_blocks:
        lines.append(f"⛔ hard block: {', '.join(result.hard_blocks)}")
    if result.macro_stale:
        lines.append("🕒 macro context was stale at evaluation time")
    return (name, "\n".join(lines))


def redflag_table(result: GateResult) -> str:
    """One line per fired (fail/warn) redflag-section check, human label +
    the check's own detail sentence."""
    fired = [c for c in result.checks
             if c.check_id.startswith("rf_") and c.status in ("fail", "warn")]
    lines = []
    for c in fired:
        label = _REDFLAG_LABELS.get(c.check_id, c.check_id)
        icon = _STATUS_ICON.get(c.status, "❔")
        lines.append(f"{icon} **{label}** — {c.detail}")
    return "\n".join(lines)


def gate_embed_fields(result, mode: str,
                      show_in_shadow: bool = False) -> list[tuple[str, str]]:
    """The G123 render matrix in one place: inform/enforce always render
    (inform is the default -- this field IS the product); shadow renders
    only when the operator opted in; no result -> no fields (byte-identical
    embed). Returns (name, value) pairs ready for embed.add_field."""
    if result is None:
        return []
    if mode == "shadow" and not show_in_shadow:
        return []
    fields = [checklist_field(result)]
    fired = [c for c in result.checks
             if c.check_id.startswith("rf_") and c.status in ("fail", "warn")]
    if fired:
        value = redflag_table(result)
        if result.advisory_decision == "block":
            n = len(fired)
            value += (f"\n⛔ {n} red flag{'s' if n != 1 else ''} — "
                      f"plan ships anyway; your call")
        fields.append(("🚩 Red flags", value))
    return fields

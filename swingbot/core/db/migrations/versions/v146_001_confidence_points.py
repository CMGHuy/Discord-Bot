"""trades.confidence_points / confidence_unevaluated: backfill from the breakdown text

v146 I1. Every trade logged before v146 carries `confidence_breakdown` as
{factor: "... (+N)"} text only. This revision parses each scored factor's line
once and writes the integers to `confidence_points` and the neutral-fallback
factors to `confidence_unevaluated`. It is the only place that text is ever
parsed (docs/claude/schema-evolution.md: no read-time upcasting). Plans are
not backfilled: they never carried a breakdown.

A bare int value (v33's retired `htf_counter_trend_penalty`) is its own
points. A line matching neither the trailing "(+N)" / "(-N)" form nor the
penalty's "-> -N quality pts" form is left out of `points` and counted as
unparsed;
the per-key parsed / skipped / unparsed counts are logged.

Revision ID: v146_001
Revises: v147_001
"""
from __future__ import annotations

import json
import logging
import re
from collections import Counter

import sqlalchemy as sa
from alembic import op

from swingbot.core.db.doc_fields import drop_doc_field

revision = "v146_001"
down_revision = "v147_001"
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.runtime.migration")

# Breakdown keys that are not scored factors, from either scorer.
NON_FACTOR_KEYS = frozenset({
    "Strategies confirmed (base level)", "Quality score", "Track record (expectancy)",
    "Level adjustment", "Confirming methods",
})
_POINTS_RE = re.compile(r"\(([+-]\d+)\)\s*$")
_PENALTY_RE = re.compile(r"->\s*(-?\d+) quality pts\s*$")
_FALLBACK_RE = re.compile(r"^\s*(?:regime unavailable|not evaluated)\b")

_SELECT = sa.text(
    "SELECT id, doc -> 'confidence_breakdown' FROM trades "
    "WHERE jsonb_typeof(doc -> 'confidence_breakdown') = 'object' "
    "AND NOT (doc ? 'confidence_points')")
_UPDATE = sa.text(
    "UPDATE trades SET doc = doc || jsonb_build_object("
    "'confidence_points', CAST(:points AS jsonb), "
    "'confidence_unevaluated', CAST(:unevaluated AS jsonb)) WHERE id = :id")


def _line_points(line) -> int | None:
    # v33's retired HTF rebucket stored htf_counter_trend_penalty as a bare
    # int (e1e93097): that int IS the factor's points. bool is not a points
    # value even though it subclasses int.
    if isinstance(line, int) and not isinstance(line, bool):
        return line
    if not isinstance(line, str):
        return None
    match = _POINTS_RE.search(line) or _PENALTY_RE.search(line)
    return int(match.group(1)) if match else None


def parse_breakdown(breakdown: dict) -> tuple[dict[str, int], list[str], list[str]]:
    """(points, unevaluated, unparsed) for one stored breakdown."""
    points: dict[str, int] = {}
    unevaluated: list[str] = []
    unparsed: list[str] = []
    for key, line in breakdown.items():
        if key in NON_FACTOR_KEYS:
            continue
        value = _line_points(line)
        if value is None:
            unparsed.append(key)
            continue
        points[key] = value
        if isinstance(line, str) and _FALLBACK_RE.match(line):
            unevaluated.append(key)
    return points, unevaluated, unparsed


def _tally(counts: dict[str, Counter], breakdown: dict, points: dict, unparsed: list) -> None:
    for key in breakdown:
        if key in points:
            outcome = "parsed"
        elif key in unparsed:
            outcome = "unparsed"
        else:
            outcome = "skipped"
        counts.setdefault(key, Counter())[outcome] += 1


def backfill(conn) -> tuple[int, dict[str, Counter]]:
    """Stamp every unstamped trade whose breakdown is an object; returns
    (rows stamped, per-key parsed/skipped/unparsed counts)."""
    counts: dict[str, Counter] = {}
    rows = conn.execute(_SELECT).all()
    for row_id, breakdown in rows:
        points, unevaluated, unparsed = parse_breakdown(breakdown)
        _tally(counts, breakdown, points, unparsed)
        conn.execute(_UPDATE, {"id": row_id, "points": json.dumps(points),
                               "unevaluated": json.dumps(unevaluated)})
    return len(rows), counts


def upgrade() -> None:
    stamped, counts = backfill(op.get_bind())
    for key in sorted(counts):
        tally = counts[key]
        log.info("v146_001 %s: parsed=%d skipped=%d unparsed=%d",
                 key, tally["parsed"], tally["skipped"], tally["unparsed"])
    log.info("v146_001: stamped %d trade row(s)", stamped)


def downgrade() -> None:
    drop_doc_field("trades", "confidence_points")
    drop_doc_field("trades", "confidence_unevaluated")

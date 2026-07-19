"""follow_score is THE single ranking authority this whole cockpit uses to
answer "which plan should I follow today?" -- Discord alerts, !plans,
!top, the weekly digest, /api/plans, and the admin board all consume
rank_plans() instead of sorting locally. See design decision #1 in
docs/superpowers/plans/2026-07-11-cockpit-v3.md."""
from __future__ import annotations

import datetime as dt

BADGE_WEIGHT = 40.0
QUALITY_WEIGHT = 0.4          # applied to a 0-100 quality_score -> 0-40 contribution
REGIME_WEIGHT = 10.0
FRESHNESS_MAX = 10.0
FRESHNESS_DECAY_PER_DAY = 2.0  # freshness hits 0 at age_days == 5


def _get(p, name: str, default=None):
    """Read `name` off either a TradePlanV2 (or any dataclass/object) or a
    plain dict, uniformly -- lets follow_score/rank_plans accept whatever
    shape the caller has on hand without every caller converting first."""
    if isinstance(p, dict):
        return p.get(name, default)
    return getattr(p, name, default)


def _parse_created_at(value: str) -> dt.date | None:
    """TradePlanV2.created_at is a bare ISO date ("2026-07-11"); some
    dict-shaped callers may instead carry a full ISO datetime. Handle
    both without raising on a malformed value."""
    if not value:
        return None
    # Coerce non-string input (e.g., datetime.date/datetime.datetime objects)
    # safely before slicing to avoid TypeError. Check datetime before date
    # since datetime is a subclass of date.
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    if not isinstance(value, str):
        return None
    try:
        return dt.date.fromisoformat(value[:10])
    except (ValueError, TypeError):
        return None


def follow_score(plan, *, today: dt.date | None = None) -> float:
    """0-100 composite score: badge (40) + quality (40) + regime (10) +
    freshness (10). Every component degrades to 0 (never raises) when its
    underlying field is missing -- an old-shaped plan simply scores lower,
    it never crashes a ranking pass.
    """
    if today is None:
        today = dt.date.today()

    badge_score = BADGE_WEIGHT if _get(plan, "badge") == "VALIDATED" else 0.0

    quality_score = _get(plan, "quality_score") or 0
    # Clamp to [0, 100] to ensure quality_component stays in [0, 40]
    quality_score = max(0, min(100, quality_score))
    quality_component = QUALITY_WEIGHT * quality_score

    regime_component = REGIME_WEIGHT if _get(plan, "regime_aligned") else 0.0

    created = _parse_created_at(_get(plan, "created_at", ""))
    if created is None:
        freshness_component = 0.0
    else:
        age_days = (today - created).days
        # Clamp to [0, FRESHNESS_MAX] to handle negative age_days (future-dated created_at)
        freshness_component = min(FRESHNESS_MAX, max(0.0, FRESHNESS_MAX - FRESHNESS_DECAY_PER_DAY * age_days))

    return badge_score + quality_component + regime_component + freshness_component


def follow_breakdown(plan, today: dt.date | None = None) -> list:
    """Same four weighted components follow_score sums, itemized as
    (label, points) pairs -- used to render the '🧭 Follow score' embed
    field (Plan B Task B6) so every number on screen traces back to
    exactly the formula follow_score itself computes. Every clamp here
    mirrors follow_score's own (quality_score clamped to [0, 100],
    freshness clamped to [0, FRESHNESS_MAX]) so summing the returned
    points always reproduces follow_score's result exactly. Zero-value
    components are OMITTED (a WEAK plan doesn't get a '0' line cluttering
    the field), matching follow_chip's "only show what actually
    contributed" spirit."""
    if today is None:
        today = dt.date.today()

    parts = []

    if _get(plan, "badge") == "VALIDATED":
        parts.append(("✅ validated source", BADGE_WEIGHT))

    quality_score = _get(plan, "quality_score") or 0
    quality_score = max(0, min(100, quality_score))
    quality_pts = QUALITY_WEIGHT * quality_score
    if quality_pts:
        parts.append((f"quality {quality_score} → +{quality_pts:.0f}", quality_pts))

    if _get(plan, "regime_aligned"):
        parts.append(("regime aligned", REGIME_WEIGHT))

    created = _parse_created_at(_get(plan, "created_at", ""))
    if created is not None:
        age_days = (today - created).days
        freshness = min(FRESHNESS_MAX, max(0.0, FRESHNESS_MAX - FRESHNESS_DECAY_PER_DAY * age_days))
        if freshness:
            parts.append(("fresh", freshness))

    return parts


def rank_plans(plans: list, *, today: dt.date | None = None) -> list:
    """`plans` sorted by follow_score descending; ties broken by
    quality_score descending, then ticker ascending (alphabetical) --
    deterministic ordering so the same input always renders in the same
    order across Discord/admin/API without depending on Python's stable
    sort accidentally preserving insertion order (it does, but the
    explicit tie-break key means that's not what's actually holding the
    order steady, so a caller passing plans in a different order gets an
    identical result)."""
    def _key(p):
        return (-follow_score(p, today=today), -(_get(p, "quality_score") or 0), _get(p, "ticker") or "")

    return sorted(plans, key=_key)

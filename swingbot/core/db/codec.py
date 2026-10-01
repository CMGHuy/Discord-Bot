"""Split a flat record into promoted columns plus a JSONB document, and back."""
from __future__ import annotations

import datetime as dt
import math
from decimal import Decimal
from typing import Any, Mapping, Sequence

# Infrastructure columns are not part of a store record's public shape.  A
# caller using one as a document field would silently lose data on merge, so
# reject it at the boundary instead.
RESERVED_KEYS = frozenset({"id", "doc", "updated_at"})


class ReservedKeyError(ValueError):
    """A record used a key reserved for an infrastructure column."""


def sanitise_non_finite(value: Any) -> Any:
    """Replace NaN and +/-Infinity with ``None``, recursively.

    ``json.dumps`` emits these as bare ``NaN``/``Infinity`` tokens, which
    Python's own parser accepts but JSON does not define and PostgreSQL's JSONB
    rejects outright.  Every producer of one here means "not computed", and the
    JSON stores already spell that ``None`` elsewhere, so this narrowing is
    deliberate and one-way: a value does not round-trip back to NaN.
    """
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, Mapping):
        return {key: sanitise_non_finite(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitise_non_finite(item) for item in value]
    return value


def split_doc(record: Mapping[str, Any], promoted: Sequence[str]) -> tuple[dict, dict]:
    """Return ``(columns, doc)`` for one flat record.

    Promoted keys are placed in relational columns; every other key remains
    in the JSON document.  Missing promoted keys stay absent, allowing the
    column default or SQL NULL to retain its normal meaning.
    """
    clash = RESERVED_KEYS.intersection(record)
    if clash:
        raise ReservedKeyError(
            f"record uses reserved key(s) {sorted(clash)}; rename the field "
            "because these names belong to infrastructure columns"
        )
    promoted_set = set(promoted)
    columns: dict[str, Any] = {}
    doc: dict[str, Any] = {}
    for key, value in record.items():
        if key in promoted_set:
            columns[key] = sanitise_non_finite(value)
        else:
            doc[key] = sanitise_non_finite(value)
    return columns, doc


def merge_doc(row: Mapping[str, Any], promoted: Sequence[str]) -> dict:
    """Rebuild a flat record from a database row.

    A non-null promoted column overrides a stale document copy.  Null columns
    are omitted so an absent legacy field round-trips as absent rather than
    becoming an explicit ``None``.
    """
    out = dict(row.get("doc") or {})
    for key in promoted:
        if key in row and row[key] is not None:
            out[key] = row[key]
    for key in RESERVED_KEYS:
        out.pop(key, None)
    return out


def normalise(value: Any) -> Any:
    """Return a representation-safe value without hiding semantic changes."""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (dt.datetime, dt.date)):
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return [normalise(item) for item in value]
    if isinstance(value, dict):
        return {key: normalise(item) for key, item in value.items()}
    return value

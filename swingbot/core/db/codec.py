"""Split a flat record into promoted columns plus a JSONB document, and back."""
from __future__ import annotations

from typing import Any, Mapping, Sequence

# Infrastructure columns are not part of a store record's public shape.  A
# caller using one as a document field would silently lose data on merge, so
# reject it at the boundary instead.
RESERVED_KEYS = frozenset({"id", "doc", "updated_at"})


class ReservedKeyError(ValueError):
    """A record used a key reserved for an infrastructure column."""


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
            columns[key] = value
        else:
            doc[key] = value
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

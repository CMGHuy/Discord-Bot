"""Record comparison for round-trip tests: representation noise (Decimal vs
float, datetime vs ISO string, tuple vs list, None vs absent) is not a diff."""
import math
from typing import Any

from swingbot.core.db.codec import normalise

_REL_TOL = 1e-9


def _equal(left: Any, right: Any) -> bool:
    left, right = normalise(left), normalise(right)
    if isinstance(left, float) or isinstance(right, float):
        try:
            return math.isclose(float(left), float(right), rel_tol=_REL_TOL, abs_tol=1e-12)
        except (TypeError, ValueError):
            return False
    try:
        return bool(left == right)
    except Exception:  # noqa: BLE001 - a hostile equality implementation is a difference
        return False


def diff_records(json_record: dict, db_record: dict) -> list[str]:
    """Return sorted top-level fields whose values differ."""
    sentinel = object()
    differing: list[str] = []
    for field in set(json_record) | set(db_record):
        json_value = json_record.get(field, sentinel)
        db_value = db_record.get(field, sentinel)
        if ((json_value is sentinel and db_value is None)
                or (db_value is sentinel and json_value is None)):
            continue
        if json_value is sentinel or db_value is sentinel or not _equal(json_value, db_value):
            differing.append(field)
    return sorted(differing)

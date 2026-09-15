"""Comparison guard for the JSON source and its PostgreSQL dual-write shadow."""
from __future__ import annotations

import datetime as dt
import logging
import math
from decimal import Decimal
from typing import Any

log = logging.getLogger(__name__)

_REL_TOL = 1e-9
MISSING = "<missing from db>"


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
        if json_value is sentinel or db_value is sentinel or not _equal(json_value, db_value):
            differing.append(field)
    return sorted(differing)


def compare_and_log(store: str, key: str, json_record: dict,
                    db_record: dict | None) -> list[str]:
    """Compare a dual-write pair, logging differences without ever raising."""
    if db_record is None:
        log.warning("dual[%s] %s: record missing from the database", store, key)
        return [MISSING]
    differing = diff_records(json_record, db_record)
    if differing:
        log.warning(
            "dual[%s] %s: %d field(s) diverge: %s",
            store, key, len(differing), ", ".join(differing),
        )
    return differing

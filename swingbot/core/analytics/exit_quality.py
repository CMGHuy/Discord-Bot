"""Pure aggregates for journalled exit-quality data.

The histograms are winners-only: a losing trade's MAE includes the stop it
hit, so it must not inform the distribution used to tune trade management.
The scatter deliberately includes every outcome because that separation is its
diagnostic value.  Callers supply entries; this module never loads a journal.
"""
from __future__ import annotations

from swingbot.core.analytics import metrics

_FIELDS = ("mfe_r", "mae_r", "exit_efficiency")


def _wins(entries: list[dict]) -> list[dict]:
    return [e for e in entries if str(e.get("outcome") or "").lower() == "win"]


def _values(entries: list[dict], field: str) -> list[float]:
    values: list[float] = []
    for entry in entries:
        value = entry.get(field)
        if value is None:
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if number == number:
            values.append(number)
    return values


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    values = sorted(values)
    middle = len(values) // 2
    return values[middle] if len(values) % 2 else (values[middle - 1] + values[middle]) / 2


def _distribution(entries: list[dict], field: str, bins: int) -> dict:
    values = _values(_wins(entries), field)
    if not values:
        return {"bins": [], "n": 0, "median": None}
    return {"bins": metrics.histogram(values, bins=bins), "n": len(values), "median": _median(values)}


def efficiency_histogram(entries: list[dict], bins: int = 10) -> dict:
    """Exit-efficiency distribution for winners with recorded efficiency."""
    return _distribution(entries, "exit_efficiency", bins)


def mae_histogram(entries: list[dict], bins: int = 10) -> dict:
    """MAE distribution for winners with recorded MAE."""
    return _distribution(entries, "mae_r", bins)


def mfe_mae_points(entries: list[dict]) -> list[dict]:
    """One all-outcomes MFE/MAE point per entry with both axes recorded."""
    points = []
    for entry in entries:
        try:
            mae, mfe = float(entry.get("mae_r")), float(entry.get("mfe_r"))
        except (TypeError, ValueError):
            continue
        if mae != mae or mfe != mfe:
            continue
        raw_r = entry.get("r_realized")
        try:
            realized = round(float(raw_r), 4) if raw_r is not None else None
        except (TypeError, ValueError):
            realized = None
        points.append({"mae_r": round(mae, 4), "mfe_r": round(mfe, 4),
                       "r_realized": realized,
                       "outcome": str(entry.get("outcome") or "unknown").lower(),
                       "ticker": entry.get("ticker") or "",
                       "strategy": entry.get("strategy") or ""})
    return points


def coverage(entries: list[dict]) -> dict:
    """Report field coverage so missing values are visible, never zeroed."""
    total = len(entries)
    return {field: {"non_null": len(_values(entries, field)), "total": total,
                    "pct": round(len(_values(entries, field)) / total * 100, 1) if total else 0.0}
            for field in _FIELDS}

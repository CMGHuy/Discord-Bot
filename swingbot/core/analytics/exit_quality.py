"""Pure aggregates for journalled exit-quality data.

The histograms are winners-only: a losing trade's MAE includes the stop it
hit, so it must not inform the distribution used to tune trade management.
The scatter deliberately includes every outcome because that separation is its
diagnostic value.  Callers supply entries; this module never loads a journal.

v228: an entry's excursion is only trusted when it was measured on intraday
bars or the trade was held two days or more. A short hold measured on daily
bars takes the whole day's range, price before the fill and after the exit
included, so it overstates MFE and MAE; callers filter aggregates through
``is_trusted`` and report ``excursion_summary`` so the exclusion is visible.
``is_daily_estimate`` is the same rule from the other side, for markers.
"""
from __future__ import annotations

from swingbot.core.analytics import metrics
from swingbot.core.analytics.mfe_mae import INTRADAY_SOURCES

_FIELDS = ("mfe_r", "mae_r", "exit_efficiency")
#: Holds this long or longer are trusted even on daily bars.
TRUSTED_MIN_HOLD_DAYS = 2.0


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


def _hold_days(entry: dict) -> float | None:
    """The entry's holding_days as a float, or None when missing or unusable."""
    try:
        days = float(entry.get("holding_days"))
    except (TypeError, ValueError):
        return None
    return days if days == days else None


def is_trusted(entry: dict) -> bool:
    """True when the entry's MFE/MAE may feed an aggregate: measured on
    intraday bars, or held at least TRUSTED_MIN_HOLD_DAYS."""
    if entry.get("excursion_source") in INTRADAY_SOURCES:
        return True
    days = _hold_days(entry)
    return days is not None and days >= TRUSTED_MIN_HOLD_DAYS


def is_daily_estimate(entry: dict) -> bool:
    """True when the figures came from daily bars on a hold under two days
    (or of unknown length): the range may be overstated."""
    if entry.get("excursion_source") != "daily":
        return False
    days = _hold_days(entry)
    return days is None or days < TRUSTED_MIN_HOLD_DAYS


def excursion_summary(entries: list[dict]) -> dict:
    """Per-source counts and how many entries the trust rule kept and dropped."""
    sources: dict[str, int] = {}
    for entry in entries:
        name = entry.get("excursion_source") or "none"
        sources[name] = sources.get(name, 0) + 1
    return {"sources": sources,
            "included": sum(1 for entry in entries if is_trusted(entry)),
            "excluded": sum(1 for entry in entries if is_daily_estimate(entry)),
            "total": len(entries)}


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
                       "strategy": entry.get("strategy") or "",
                       "excursion_source": entry.get("excursion_source")})
    return points


def coverage(entries: list[dict]) -> dict:
    """Report field coverage so missing values are visible, never zeroed."""
    total = len(entries)
    return {field: {"non_null": len(_values(entries, field)), "total": total,
                    "pct": round(len(_values(entries, field)) / total * 100, 1) if total else 0.0}
            for field in _FIELDS}

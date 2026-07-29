"""FRED REST client. Empty API key -> None/[] without touching the network.

The win-rate audit cut the FRED *series registry* (CPI/PPI/PCE, labor,
yields, curve) but not this client: VIX comes through fred_series, and the
economic event calendar is built from fred_release_dates.
"""
from __future__ import annotations

from swingbot import config
from swingbot.core.macro.httpcache import fetch_json

BASE = "https://api.stlouisfed.org/fred"


def _key() -> str:
    return (getattr(config, "FRED_API_KEY", "") or "").strip()


def fred_series(series_id: str, *, start: str | None = None,
                ttl_s: int = 6 * 3600) -> list[tuple[str, float]] | None:
    if not _key():
        return None
    params = {"series_id": series_id, "api_key": _key(),
              "file_type": "json", "sort_order": "asc"}
    if start:
        params["observation_start"] = start
    data = fetch_json(f"{BASE}/series/observations", params=params, ttl_s=ttl_s)
    if not data or "observations" not in data:
        return None
    out = []
    for obs in data["observations"]:
        if obs.get("value") in (".", "", None):
            continue
        try:
            out.append((obs["date"], float(obs["value"])))
        except (KeyError, TypeError, ValueError):
            continue
    return sorted(out) or None


def fred_release_dates(release_id: int, *, include_future: bool = True) -> list[str]:
    if not _key():
        return []
    params = {"release_id": release_id, "api_key": _key(), "file_type": "json",
              "sort_order": "asc",
              "include_release_dates_with_no_data": "true" if include_future else "false"}
    data = fetch_json(f"{BASE}/releases/dates", params=params, ttl_s=24 * 3600)
    if not data:
        return []
    return [d["date"] for d in data.get("release_dates", []) if d.get("date")]


def latest(series_id: str) -> tuple[str, float] | None:
    series = fred_series(series_id)
    return series[-1] if series else None


def yoy(series_id: str) -> float | None:
    """Last observation vs the one 12 monthly observations earlier."""
    series = fred_series(series_id)
    if not series or len(series) < 13:
        return None
    last, year_ago = series[-1][1], series[-13][1]
    if year_ago == 0:
        return None
    return (last / year_ago - 1.0) * 100.0

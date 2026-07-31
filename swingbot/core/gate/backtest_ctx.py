"""Macro-snapshot-shaped dicts reconstructed from the publication-lag
frame (G41) + the event calendar (G29) — exactly what was knowable at
as_of's close. Same shape as snapshot.build_snapshot, same degradation
contract (missing history -> unknowns)."""
from __future__ import annotations

import datetime as dt
import os
from functools import lru_cache

from swingbot.core.jsonio import read_json
from swingbot.core.macro import calendar_events
from swingbot.core.macro.history import HISTORY_DIR, as_of_frame


@lru_cache(maxsize=1)
def _cached_frame(start: str):
    return as_of_frame(start=start)


def _frame(start: str = "2018-01-01"):
    return _cached_frame(start)


@lru_cache(maxsize=1)
def _vix_percentile() -> dict:
    rows = read_json(os.path.join(HISTORY_DIR, "vix_percentile.json"),
                     default=[]) or []
    return dict(rows)


def historical_macro_snap(as_of) -> dict:
    date = str(as_of)[:10]
    frame = _frame()
    visible = frame.loc[:date]
    row = visible.iloc[-1] if len(visible) else None

    def val(key):
        if row is None or key not in row.index or row[key] != row[key]:  # NaN-safe
            return None
        return {"value": round(float(row[key]), 2), "as_of": date, "direction": 0}

    spreads = [v["value"] for v in (val("curve_10y2y"), val("curve_10y3m")) if v]
    if not spreads:
        curve = "unknown"
    elif any(s < 0 for s in spreads):
        curve = "inverted"
    elif all(0 <= s <= 0.25 for s in spreads):
        curve = "flat"
    else:
        curve = "normal"

    close_utc = dt.datetime.combine(dt.date.fromisoformat(date), dt.time(21, 0),
                                    tzinfo=dt.timezone.utc)   # ~16:00 ET close
    horizon = (dt.date.fromisoformat(date) + dt.timedelta(days=3)).isoformat()
    upcoming = calendar_events.events_between(date, horizon)
    vix_pct = _vix_percentile().get(date)
    return {
        "built_at": close_utc.isoformat(), "stale": False, "historical": True,
        "inflation": {k: val(k) for k in ("cpi_yoy", "core_cpi_yoy", "ppi_yoy",
                                          "pce_yoy", "core_pce_yoy")},
        "rates": {**{k: val(k) for k in ("fed_funds", "y2", "y10")},
                  "curve_state": curve},
        "risk": {"vix": ({"level": None, "percentile_1y": vix_pct,
                          "regime": None, "term_structure": None}
                         if vix_pct is not None else None),
                 "credit": None,
                 "dollar_index": val("dollar_index"), "wti": val("wti")},
        "events": {
            "next_high_impact": next((e for e in upcoming if e["importance"] == 3),
                                     None),
            "within_24h": [e for e in upcoming
                           if 0 <= calendar_events.hours_until(e, close_utc) <= 24],
            "today": [e for e in upcoming if e["date"] == date],
        },
        "news": {"headlines_top5": [],
                 "sentiment": {"score": 0.0, "n": 0, "label": "neutral"},
                 "rumor_ratio": 0.0},
        "composite": {"score": 0, "label": "unknown", "inputs_used": 0, "detail": []},
        "quality_warnings": [],
    }

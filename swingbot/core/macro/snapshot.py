"""Build/save/load the ONE macro snapshot every consumer reads (scan gate,
embeds, alert rendering). Nobody re-fetches providers at render time.

Post-audit scope (see the plan's G38 audit note): the snapshot carries VIX,
breadth, sector RS/rotation, the risk composite and the event/session
calendars. The FRED series sections (inflation/labor/rates/expectations),
credit, the dollar/WTI risk fields, news/sentiment and the fear-greed gauge
were all cut with their provider tasks, and their quality entries with them.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import os

from swingbot import config
from swingbot.core.jsonio import atomic_write_json, read_json
from swingbot.core.macro import (breadth as breadth_mod, calendar_events,
                                 composite, httpcache, sectors, sessions, vix)

log = logging.getLogger("swing-bot.macro.snapshot")

SNAPSHOT_PATH = os.path.join(config.DATA_DIR, "macro", "macro_snapshot.json")
HISTORY_PATH = os.path.join(config.DATA_DIR, "macro", "snapshot_history.jsonl")


def _safe(fn, *args, **kw):
    """A broken provider never breaks the build — None + one log line."""
    try:
        return fn(*args, **kw)
    except Exception:  # noqa: BLE001
        log.warning("snapshot: %s failed", getattr(fn, "__name__", fn), exc_info=True)
        return None


def build_snapshot(*, loaders: dict | None = None, now=None) -> dict:
    """loaders (optional, injectable for tests / decoupling):
      "bars": ticker -> daily OHLCV frame (cache loader)
      "universe": () -> {ticker: df} for breadth over the scan universe
    Every section is None-tolerant; total provider failure still returns
    the full skeleton with unknowns and stale=True (proven in G43)."""
    loaders = loaders or {}
    bars_loader = loaders.get("bars")
    universe = loaders.get("universe")
    httpcache.LAST_SERVED_STALE = False
    now = now or dt.datetime.now(dt.timezone.utc)
    today = now.date().isoformat()
    warnings: list[str] = []

    vix_state = _safe(vix.vix_state, bars_loader)
    if vix_state is None:
        warnings.append("vix unavailable")

    sector_bars = _safe(sectors.sector_bars, bars_loader) or {}
    rs_rows = _safe(sectors.sector_rs, sector_bars) or []
    if not rs_rows:
        warnings.append("sector RS unavailable")
    rotation = (_safe(sectors.rotation_state, rs_rows)
                or {"posture": "unknown", "note": ""})

    breadth_dict = (_safe(breadth_mod.breadth, universe() if universe else {})
                    or {"pct_above_50dma": None, "pct_above_200dma": None, "n": 0})
    if not breadth_dict.get("n"):
        warnings.append("breadth unavailable")

    comp = composite.risk_composite(vix_state, rotation, breadth_dict)

    events = _safe(calendar_events.load_events) or []
    if not events:
        warnings.append("event calendar empty")
    high = [e for e in events if e["date"] >= today and e.get("importance") == 3]
    next_high = high[0] if high else None
    within_24h = [e for e in high
                  if 0 <= _safe(calendar_events.hours_until, e, now) <= 24]

    snap = {
        "built_at": now.isoformat(),
        "stale": bool(httpcache.LAST_SERVED_STALE or warnings),
        "risk": {"vix": vix_state},
        "composite": comp,
        "sectors": {"rs_rows": rs_rows, "rotation": rotation},
        "breadth": breadth_dict,
        "events": {
            "next_high_impact": next_high,
            "within_24h": within_24h,
            "today": [e for e in events if e["date"] == today],
        },
        "session": _safe(sessions.session_flag, today) or {"flag": "unknown", "detail": ""},
        "quality_warnings": warnings,
    }
    return snap


def save_snapshot(snap: dict) -> None:
    """Write the snapshot and append one summary line to the history JSONL
    (kept small on purpose — it is a trend series, not a second copy)."""
    os.makedirs(os.path.dirname(SNAPSHOT_PATH), exist_ok=True)
    atomic_write_json(SNAPSHOT_PATH, snap)
    line = {
        "built_at": snap.get("built_at"),
        "stale": snap.get("stale"),
        "composite": (snap.get("composite") or {}).get("score"),
        "composite_label": (snap.get("composite") or {}).get("label"),
        "vix": ((snap.get("risk") or {}).get("vix") or {}).get("level"),
        "breadth_50dma": (snap.get("breadth") or {}).get("pct_above_50dma"),
        "rotation": ((snap.get("sectors") or {}).get("rotation") or {}).get("posture"),
    }
    with open(HISTORY_PATH, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(line) + "\n")


def load_snapshot(max_age_min: int | None = None) -> dict | None:
    snap = read_json(SNAPSHOT_PATH, default=None)
    if not snap:
        return None
    if max_age_min is None:
        return snap
    try:
        built = dt.datetime.fromisoformat(snap["built_at"])
    except (KeyError, TypeError, ValueError):
        return None
    if built.tzinfo is None:
        built = built.replace(tzinfo=dt.timezone.utc)
    age_min = (dt.datetime.now(dt.timezone.utc) - built).total_seconds() / 60.0
    return snap if age_min <= max_age_min else None

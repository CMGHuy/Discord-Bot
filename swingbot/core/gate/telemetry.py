"""Gate telemetry -- append-only JSONL counters (G135). count() is
fire-and-forget (NEVER raises: telemetry must never cost an alert, same
rule as the gate itself); summary() aggregates for the retrospective, an
admin surface, or the health page -- whichever ends up consuming it."""
from __future__ import annotations

import datetime as dt
import json
import os

from swingbot import config

TELEMETRY_PATH = os.path.join(config.DATA_DIR, "gate", "telemetry.jsonl")

_COUNTER_EVENTS = ("evaluated", "blocked", "downgraded", "held_for_event", "recheck_held")


def count(event: str, at: dt.datetime | None = None, **labels) -> None:
    try:
        row = {"at": (at or dt.datetime.now()).isoformat(timespec="seconds"),
               "event": event, **labels}
        os.makedirs(os.path.dirname(TELEMETRY_PATH), exist_ok=True)
        with open(TELEMETRY_PATH, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
    except Exception:  # noqa: BLE001
        pass


def summary(since: str | None = None) -> dict:
    """Aggregate counters at/after `since` (ISO date string; None = all).
    ISO timestamps compare lexicographically, so "2026-07-14T…" >= "2026-07-14"
    does the date filtering without parsing."""
    out = {"evaluated": 0, "blocked": 0, "blocked_reasons": [],
           "downgraded": 0, "held_for_event": 0, "recheck_held": 0,
           "unknown_rate": {}}
    if not os.path.exists(TELEMETRY_PATH):
        return out
    unknown_hits: dict[str, int] = {}
    unknown_totals: dict[str, int] = {}
    with open(TELEMETRY_PATH, encoding="utf-8") as fh:
        for line in fh:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if since and row.get("at", "") < since:
                continue
            ev = row.get("event")
            if ev in _COUNTER_EVENTS:
                out[ev] += 1
                if ev == "blocked" and row.get("reason"):
                    out["blocked_reasons"].append(row["reason"])
            elif ev == "provider_answer":
                p = row.get("provider", "?")
                unknown_totals[p] = unknown_totals.get(p, 0) + 1
                if row.get("unknown"):
                    unknown_hits[p] = unknown_hits.get(p, 0) + 1
    out["unknown_rate"] = {p: round(unknown_hits.get(p, 0) / n, 3)
                          for p, n in unknown_totals.items()}
    return out

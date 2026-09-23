"""Append-only scan telemetry and slowdown detection."""
import json as _json
import os

from swingbot import config


TELEMETRY_PATH = os.path.join(config.DATA_DIR, "scan_telemetry.jsonl")


def log_scan_telemetry(stats: dict, path: str | None = None) -> None:
    """Append one scan row, including optional ``phases_s`` timing details.

    The compact append-only history feeds ``scan_slowdown()`` and the admin
    scan-health display.  Phase timings are intentionally raw numbers rather
    than a second derived view so operators can identify whether crawl,
    pricing, enrichment, analysis, or alert finalisation regressed.
    """
    import datetime as dt
    row = {"at": dt.datetime.now(dt.timezone.utc).isoformat(), **stats}
    with open(path or TELEMETRY_PATH, "a", encoding="utf-8") as f:
        f.write(_json.dumps(row) + "\n")


def recent_telemetry(n: int = 50, path: str | None = None) -> list:
    try:
        with open(path or TELEMETRY_PATH, encoding="utf-8") as f:
            lines = f.readlines()[-n:]
        return [_json.loads(l) for l in lines if l.strip()]
    except OSError:
        return []


def recent_scan_telemetry(n: int = 50, path: str | None = None) -> list:
    """The last ``n`` SCAN rows only. The file also carries rows with no
    ``duration_s`` -- deploy_marker.py's ``{"type": "deploy"}`` markers --
    and a reader that indexes ``duration_s`` must never see those."""
    rows = [r for r in recent_telemetry(n + 50, path=path)
            if isinstance(r, dict) and isinstance(r.get("duration_s"), (int, float))]
    return rows[-n:]


def scan_slowdown(path: str | None = None) -> bool:
    """True when the latest logged scan took more than 2x the median of
    the prior 20 -- a real slowdown, not noise from a single slow ticker."""
    rows = recent_scan_telemetry(21, path=path)
    if len(rows) < 6:
        return False
    import statistics
    prior = [r["duration_s"] for r in rows[:-1]]
    return rows[-1]["duration_s"] > 2 * statistics.median(prior)

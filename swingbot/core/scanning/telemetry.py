"""Append-only scan telemetry and slowdown detection."""
import json as _json
import os

from swingbot import config


TELEMETRY_PATH = os.path.join(config.DATA_DIR, "scan_telemetry.jsonl")


def log_scan_telemetry(stats: dict, path: str | None = None) -> None:
    """Task E82: one JSON line per scan (at, duration_s, tickers, errors,
    data_skips, signals, alerts, open_heat) appended to scan_telemetry.jsonl
    -- cheap append-only history for scan_slowdown()'s alarm and the admin
    risk page's duration sparkline."""
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


def scan_slowdown(path: str | None = None) -> bool:
    """True when the latest logged scan took more than 2x the median of
    the prior 20 -- a real slowdown, not noise from a single slow ticker."""
    rows = recent_telemetry(21, path=path)
    if len(rows) < 6:
        return False
    import statistics
    prior = [r["duration_s"] for r in rows[:-1]]
    return rows[-1]["duration_s"] > 2 * statistics.median(prior)

"""Measured deployment windows and the telemetry that can honestly support them."""
from __future__ import annotations

import bisect
import json
import os
import statistics
import subprocess
from datetime import datetime

from swingbot import config
from swingbot.core.infra.deploy_marker import read_markers


def _version(marker: dict) -> str | None:
    return marker.get("bot") if marker.get("component") == "bot" else marker.get("ui")


def _git_tags() -> list[tuple[str, str]]:
    """Release tags, newest first. Containers without git simply have none."""
    try:
        output = subprocess.check_output(
            ["git", "for-each-ref", "--format=%(refname:short)|%(creatordate:iso-strict)", "refs/tags"],
            cwd=config._PROJECT_ROOT, text=True, stderr=subprocess.DEVNULL,
        )
        return [tuple(line.split("|", 1)) for line in output.splitlines() if "|" in line]
    except Exception:
        return []


def windows() -> list[dict]:
    """One window per deployed version, newest first, per component only."""
    grouped: dict[str, list[dict]] = {"bot": [], "admin": []}
    for marker in read_markers():
        component = marker.get("component")
        if component in grouped and _version(marker) and marker.get("at"):
            grouped[component].append(marker)

    result: list[dict] = []
    for component, rows in grouped.items():
        changes: list[dict] = []
        for row in sorted(rows, key=lambda item: item["at"]):
            if not changes or _version(changes[-1]) != _version(row):
                changes.append(row)
        for index, row in enumerate(changes):
            result.append({
                "component": component, "version": _version(row), "sha": row.get("sha"),
                "from": row["at"], "to": changes[index + 1]["at"] if index + 1 < len(changes) else None,
                "source": "marker",
            })

    if not result:
        for tag, at in _git_tags():
            result.append({"component": "bot", "version": tag.removeprefix("v"), "sha": None,
                           "from": at, "to": None, "source": "backfill"})
    return sorted(result, key=lambda row: row["from"], reverse=True)


# /versions asks for one window per release (~180) and the file is megabytes,
# so it is parsed once per (path, mtime, size) and kept sorted by `at`; each
# window is then a bisect, not a re-read (it took 30-90 s per request in prod).
_SCAN_CACHE: dict = {"key": None, "ats": [], "rows": []}


def _parse_scan_file(path: str) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict) and row.get("type") != "deploy" and isinstance(row.get("at"), str) and row["at"]:
                rows.append(row)
    rows.sort(key=lambda row: row["at"])
    return rows


def _sorted_scan_rows() -> tuple[list[str], list[dict]]:
    """Scan rows with a string `at`, sorted by it, plus the parallel `at` list."""
    path = os.path.join(config.DATA_DIR, "scan_telemetry.jsonl")
    try:
        stat = os.stat(path)
        key = (path, stat.st_mtime_ns, stat.st_size)
        if _SCAN_CACHE["key"] != key:
            rows = _parse_scan_file(path)
            _SCAN_CACHE.update(key=key, ats=[row["at"] for row in rows], rows=rows)
    except OSError:
        return [], []
    return _SCAN_CACHE["ats"], _SCAN_CACHE["rows"]


def _window_rows(window: dict) -> list[dict]:
    """Rows with window["from"] <= at < window["to"] (no upper bound when to is None)."""
    ats, rows = _sorted_scan_rows()
    start = bisect.bisect_left(ats, window["from"])
    end = len(ats) if window["to"] is None else bisect.bisect_left(ats, window["to"])
    return rows[start:max(start, end)]


def telemetry_for(window: dict) -> dict:
    """Measured scan timing; unsupported telemetry is explicitly nullable."""
    rows = _window_rows(window)
    durations = [row.get("duration_s") for row in rows if isinstance(row.get("duration_s"), (int, float))]
    days = {row["at"][:10] for row in rows}
    return {
        "uptime_pct": None,
        "error_rate": None,
        "median_scan_sec": float(statistics.median(durations)) if durations else None,
        "n_days": len(days),
    }

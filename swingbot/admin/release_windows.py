"""Measured deployment windows and the telemetry that can honestly support them."""
from __future__ import annotations

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


def _in_window(at: str | None, window: dict) -> bool:
    if not at or at < window["from"]:
        return False
    return window["to"] is None or at < window["to"]


def _scan_rows() -> list[dict]:
    path = os.path.join(config.DATA_DIR, "scan_telemetry.jsonl")
    try:
        with open(path, encoding="utf-8") as handle:
            rows = []
            for line in handle:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(row, dict) and row.get("type") != "deploy":
                    rows.append(row)
            return rows
    except OSError:
        return []


def telemetry_for(window: dict) -> dict:
    """Measured scan timing; unsupported telemetry is explicitly nullable."""
    rows = [row for row in _scan_rows() if _in_window(row.get("at"), window)]
    durations = [row.get("duration_s") for row in rows if isinstance(row.get("duration_s"), (int, float))]
    days = {str(row.get("at"))[:10] for row in rows if row.get("at")}
    return {
        "uptime_pct": None,
        "error_rate": None,
        "median_scan_sec": float(statistics.median(durations)) if durations else None,
        "n_days": len(days),
    }

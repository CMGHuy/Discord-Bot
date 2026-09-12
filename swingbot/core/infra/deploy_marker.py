"""Append-only boot markers in the existing scan telemetry JSONL stream.

Markers are operational telemetry, not bot state: failures are swallowed so
an unwritable telemetry volume can never prevent either process from starting.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
from datetime import datetime, timezone

from swingbot import config

log = logging.getLogger("swing-bot.deploy-marker")


def _path() -> str:
    return os.path.join(config.DATA_DIR, "scan_telemetry.jsonl")


def _versions() -> dict[str, str | None]:
    try:
        with open(os.path.join(config._PROJECT_ROOT, "VERSION.json"), encoding="utf-8") as handle:
            data = json.load(handle)
        return {"ui": str(data.get("ui")) if data.get("ui") else None,
                "bot": str(data.get("bot")) if data.get("bot") else None}
    except Exception:
        return {"ui": None, "bot": None}


def _sha() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=config._PROJECT_ROOT,
            stderr=subprocess.DEVNULL, text=True,
        ).strip() or None
    except Exception:
        return os.environ.get("SWINGBOT_SHA") or None


def _append(marker: dict) -> None:
    with open(_path(), "a", encoding="utf-8") as handle:
        handle.write(json.dumps(marker, separators=(",", ":")) + "\n")


def record_boot(component: str) -> None:
    """Record one boot and degrade silently if telemetry cannot be written."""
    try:
        if component not in {"bot", "admin"}:
            raise ValueError(f"unknown component {component!r}")
        _append({
            "type": "deploy", "component": component, **_versions(), "sha": _sha(),
            "at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        })
    except Exception:
        log.debug("could not record deploy marker", exc_info=True)


def read_markers() -> list[dict]:
    """Read valid deploy rows, skipping malformed and unrelated telemetry."""
    try:
        markers: list[dict] = []
        with open(_path(), encoding="utf-8") as handle:
            for line in handle:
                try:
                    row = json.loads(line)
                except (json.JSONDecodeError, TypeError):
                    continue
                if isinstance(row, dict) and row.get("type") == "deploy":
                    markers.append(row)
        return markers
    except Exception:
        return []

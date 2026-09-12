"""GET /api/v1/versions — which ui and bot versions have shipped together.

`VERSION.json` carries two independently-bumped lines and has never recorded
which values of one go with which values of the other. That pairing exists only
in the file's own git history, so `scripts/dev/build_version_matrix.py` freezes it
into `swingbot/admin/version_history.json`, which this endpoint serves. The
frozen file is committed because the deployed container has no git history to
re-derive it from.

**What the data means, exactly.** Both containers build from one image
(`docs/deploy/DOCKER.md`), so the two versions at any commit are what was released as a
unit. A pair in this payload therefore says "these two shipped together" — it is
*not* a test result and *not* a support claim, and the page that renders it
repeats that wording. Combinations that never shipped are absent rather than
marked incompatible; nobody has ever run them, which is a different statement
from their being known-bad.

The live `VERSION.json` is read on every request and compared against the frozen
file. When someone bumps a version without re-running the generator, `stale` goes
true and carries the live pair — a version page that quietly disagrees with the
sidebar two panels away would be worse than one that says it is behind.
"""
from __future__ import annotations

import json
import os
import subprocess
from functools import lru_cache
from typing import Any

from flask import jsonify

from swingbot.admin import helpers as _helpers
from swingbot.admin import release_windows

from . import api_v1
from .auth import require_auth

HISTORY_PATH = os.path.join(os.path.dirname(__file__), "..", "version_history.json")


@lru_cache(maxsize=512)
def _git(*args: str) -> str | None:
    """Git is optional in a shipped container; absence is an honest null."""
    try:
        return subprocess.check_output(
            ["git", *args], cwd=_helpers.config._PROJECT_ROOT, text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.SubprocessError):
        return None


def _provenance(release: dict, previous: dict | None) -> dict:
    """Derive a verifiable range from consecutive frozen history commits."""
    commit = release.get("commit")
    if not isinstance(commit, str) or not _git("rev-parse", "--verify", f"{commit}^{{commit}}"):
        return {"commit_range": None, "commits": None, "spec": None, "changelog": []}

    prior = previous.get("commit") if previous else None
    valid_prior = isinstance(prior, str) and _git("rev-parse", "--verify", f"{prior}^{{commit}}")
    revision = f"{prior}..{commit}" if valid_prior else commit
    count = _git("rev-list", "--count", revision)
    files = (_git("diff-tree", "--no-commit-id", "--name-only", "-r", commit) or "").splitlines()
    specs = [path for path in files if path.startswith("docs/superpowers/specs/") and path.endswith(".md")]
    changelog = [path for path in files if os.path.basename(path).lower().startswith("changelog")]
    return {
        "commit_range": revision,
        "commits": int(count) if count and count.isdigit() else None,
        "spec": specs[0] if specs else None,
        "changelog": changelog,
    }


def _window_for(release: dict, windows: list[dict]) -> dict | None:
    versions = release.get("versions") or {}
    # Prefer bot: scan telemetry belongs to that process. UI is the fallback
    # for an admin-only marker.
    for component, version_key in (("bot", "bot"), ("admin", "ui")):
        version = versions.get(version_key)
        found = next((window for window in windows
                      if window["component"] == component and window["version"] == version), None)
        if found:
            return found
    return None


def _enrich_releases(releases: list[dict]) -> list[dict]:
    release_windows_rows = release_windows.windows()
    enriched = []
    for index, release in enumerate(releases):
        row = dict(release)
        window = _window_for(row, release_windows_rows)
        telemetry = release_windows.telemetry_for(window) if window else {
            "uptime_pct": None, "error_rate": None, "median_scan_sec": None, "n_days": None,
        }
        row["provenance"] = _provenance(row, releases[index - 1] if index else None)
        row["telemetry"] = {**telemetry, "source": window["source"] if window else "backfill"}
        enriched.append(row)
    return enriched


def _load_history() -> dict[str, Any]:
    """The frozen pairing history, or an empty shape if it was never generated.

    Returning a well-formed empty document rather than raising keeps the page
    renderable on a checkout where the generator has not been run: the SPA shows
    "no history recorded" instead of an error toast, and the `stale` flag below
    still reports the live versions.
    """
    try:
        with open(os.path.abspath(HISTORY_PATH), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {"generated_at": None, "basis": None, "current": {},
                "components": [], "releases": []}


@api_v1.route("/versions", methods=["GET"])
@require_auth
def get_versions():
    history = _load_history()
    live = _helpers.get_component_versions()
    frozen_current = history.get("current") or {}

    # Stale means the generator has not been re-run since the last bump, not
    # that anything is broken. A whole-dict comparison rather than key-by-key:
    # a component ADDED to VERSION.json and absent from the frozen file is the
    # same failure -- a page that looks complete while missing an entire lane.
    stale = bool(live) and live != frozen_current

    return jsonify({
        "generated_at": history.get("generated_at"),
        "basis": history.get("basis"),
        "live": live,
        "stale": stale,
        "components": history.get("components", []),
        "current": frozen_current,
        "releases": _enrich_releases(history.get("releases", [])),
    })

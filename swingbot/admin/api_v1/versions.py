"""GET /api/v1/versions — which ui and bot versions have shipped together.

`VERSION.json` carries two independently-bumped lines and has never recorded
which values of one go with which values of the other. That pairing exists only
in the file's own git history, so `scripts/dev/build_version_matrix.py` freezes it
into `swingbot/admin/version_history.json`, which this endpoint serves. The
frozen file is committed because the deployed container has no git history to
re-derive it from.

**What the data means, exactly.** Both containers build from one image
(`docs/DOCKER.md`), so the two versions at any commit are what was released as a
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
from typing import Any

from flask import jsonify

from swingbot.admin import helpers as _helpers

from . import api_v1
from .auth import require_auth

HISTORY_PATH = os.path.join(os.path.dirname(__file__), "..", "version_history.json")


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
        "releases": history.get("releases", []),
    })

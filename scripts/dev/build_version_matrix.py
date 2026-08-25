#!/usr/bin/env python3
"""Derive the ui/bot version pairing history from git and freeze it to JSON.

WHY THIS EXISTS, AND WHAT IT DOES *NOT* CLAIM
---------------------------------------------
`VERSION.json` carries two independently-bumped lines, `ui` and `bot`, and
nothing in the repo has ever recorded which values of one go with which values
of the other. This script recovers that from the only place it is written down:
the history of the file itself.

Both containers are built from ONE image (see `docs/deploy/DOCKER.md`), so at any commit the
`ui` and `bot` values are what shipped *together*. That is the whole basis of the
output. It is an observation about what was released as a unit, **not** a claim
that anyone tested those two versions against each other, and not a prediction
about combinations that never shipped. The admin page that renders this says so
in the same words; do not relabel either one "tested" or "supported".

Pairs are deduplicated: many commits touch neither line, and consecutive commits
often repeat a pair. Each distinct pair is kept once, with the dates it was first
and last seen.

Run after any VERSION.json bump:

    python scripts/dev/build_version_matrix.py

Writes `swingbot/admin/version_history.json`, which is committed — the deployed
container has no git history to re-derive it from.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "swingbot" / "admin" / "version_history.json"
TRACKED = "VERSION.json"


def _components(doc: dict) -> list[str]:
    """Component keys in a VERSION.json document, in file order.

    Every key that is not a `*_updated` stamp. This is the ENTIRE interface for
    adding a component: put a key in VERSION.json and it appears here, in the
    payload, and on the admin page. No code change, no migration.

    The cost of that convenience: a component may never be named
    `<something>_updated`. It would be filtered out here and simply never
    appear, with no error raised anywhere -- which is why this is written down
    rather than left to be rediscovered.

    Also excludes the literal `"updated"` key (bare, no underscore): a real
    historical VERSION.json commit (d80512f9, pre-dates the ui_updated/bot_updated
    convention) had this exact key as a shared timestamp. If `VERSION.json` ever
    gains a shared top-level `"updated"` field again, this filter prevents it from
    being mistaken for a component.
    """
    return [k for k in doc if k != "updated" and not k.endswith("_updated")]


# Retained for the SPA-side version filter (v29 Task 6); no caller in this
# module since the cross-product fields were removed.
def _semver_key(v: str) -> tuple:
    """Sort '1.10.2' after '1.9.0'. Non-numeric parts sort last, not crash."""
    parts = []
    for chunk in v.split("."):
        parts.append((0, int(chunk)) if chunk.isdigit() else (1, 0))
    return tuple(parts)


def _states() -> list[dict]:
    """Every committed state of VERSION.json, oldest first."""
    log = subprocess.run(
        ["git", "log", "--reverse", "--format=%H|%ad|%s", "--date=short", "--", TRACKED],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout.splitlines()

    states = []
    for line in log:
        if not line.strip():
            continue
        sha, date, subject = line.split("|", 2)
        blob = subprocess.run(
            ["git", "show", f"{sha}:{TRACKED}"],
            cwd=ROOT, capture_output=True, text=True,
        )
        if blob.returncode != 0:
            continue                      # the commit that deleted//renamed it
        try:
            doc = json.loads(blob.stdout)
        except json.JSONDecodeError:
            continue                      # a malformed intermediate state
        versions = {k: str(v) for k, v in doc.items()
                    if k != "updated" and not k.endswith("_updated") and v}
        # AT LEAST ONE, never all. A release predating a component simply does
        # not carry its key; requiring every known component here would drop
        # every historical release the first time anyone extends VERSION.json.
        if not versions:
            continue
        states.append({"sha": sha[:8], "date": date, "subject": subject,
                       "versions": versions})

    # The working tree's own VERSION.json, when it differs from the newest
    # COMMITTED state. Without this the generator can never see the bump it is
    # being run for: you bump, regenerate, and the frozen file still ends at
    # the previous release because that is all git knows about yet. Appending
    # it is idempotent — once the bump is committed, git reports the same pair
    # and the dedup below collapses them.
    live_path = ROOT / TRACKED
    if live_path.exists():
        try:
            live = json.loads(live_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            live = {}
        live_versions = {k: str(v) for k, v in live.items()
                         if k != "updated" and not k.endswith("_updated") and v}
        if live_versions and (not states or states[-1]["versions"] != live_versions):
            states.append({
                "sha": "uncommitted",
                "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "subject": "working tree", "versions": live_versions,
            })
    return states


def build() -> dict:
    states = _states()
    if not states:
        raise SystemExit(f"no committed states of {TRACKED} found — is this a git checkout?")

    # First-appearance order, oldest release first. NOT sorted: lane order on
    # the page should be stable as components are added, and alphabetical order
    # re-sorts every existing lane the day someone adds `api`. Appending only.
    components: list[str] = []
    for st in states:
        for name in st["versions"]:
            if name not in components:
                components.append(name)

    # One entry per DISTINCT tuple. `changed` is derived here rather than in the
    # SPA because it is a property of the sequence: a client would recompute it
    # on every render, would need the whole ordered list in hand to draw any
    # single row (breaking pagination), and would have to special-case the
    # first release in a second place.
    releases: list[dict] = []
    previous: dict[str, str | None] = {}
    for st in states:
        versions = {c: st["versions"].get(c) for c in components}
        changed = [c for c in components
                   if versions[c] is not None and versions[c] != previous.get(c)]
        if releases and not changed:
            releases[-1]["last_seen"] = st["date"]     # same tuple, still current
            continue
        releases.append({
            "date": st["date"], "last_seen": st["date"],
            "commit": st["sha"], "subject": st["subject"],
            "versions": versions, "changed": changed,
        })
        previous = versions

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "basis": "Versions observed together in VERSION.json. Both containers "
                 "build from one image, so a pair here shipped as a unit. This "
                 "is a record of what was released together, not a statement "
                 "that the pair was tested.",
        "components": components,
        "current": {c: v for c, v in releases[-1]["versions"].items() if v is not None},
        "releases": releases,
    }


def main() -> None:
    doc = build()
    OUT.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}: "
          f"{len(doc['components'])} components, "
          f"{len(doc['releases'])} releases", file=sys.stderr)


if __name__ == "__main__":
    main()

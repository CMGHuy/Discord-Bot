#!/usr/bin/env python3
"""Derive the ui/bot version pairing history from git and freeze it to JSON.

WHY THIS EXISTS, AND WHAT IT DOES *NOT* CLAIM
---------------------------------------------
`VERSION.json` carries two independently-bumped lines, `ui` and `bot`, and
nothing in the repo has ever recorded which values of one go with which values
of the other. This script recovers that from the only place it is written down:
the history of the file itself.

Both containers are built from ONE image (see `docs/DOCKER.md`), so at any commit the
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

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "swingbot" / "admin" / "version_history.json"
TRACKED = "VERSION.json"


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
        ui, bot = doc.get("ui"), doc.get("bot")
        if not ui or not bot:
            continue
        states.append({"sha": sha[:8], "date": date, "subject": subject,
                       "ui": ui, "bot": bot})

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
        ui, bot = live.get("ui"), live.get("bot")
        if ui and bot and (not states or (states[-1]["ui"], states[-1]["bot"]) != (ui, bot)):
            states.append({
                "sha": "uncommitted",
                "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "subject": "working tree", "ui": ui, "bot": bot,
            })
    return states


def build() -> dict:
    states = _states()
    if not states:
        raise SystemExit(f"no committed states of {TRACKED} found — is this a git checkout?")

    # Distinct (ui, bot) pairs, in the order they first appeared.
    pairs: dict[tuple[str, str], dict] = {}
    for st in states:
        key = (st["ui"], st["bot"])
        if key in pairs:
            pairs[key]["last_seen"] = st["date"]
        else:
            pairs[key] = {
                "ui": st["ui"], "bot": st["bot"],
                "first_seen": st["date"], "last_seen": st["date"],
                "commit": st["sha"], "subject": st["subject"],
            }

    ui_versions = sorted({p["ui"] for p in pairs.values()}, key=_semver_key)
    bot_versions = sorted({p["bot"] for p in pairs.values()}, key=_semver_key)

    # Per-UI span across the bot line: the answer to "this UI ran against which
    # backends". Contiguous in practice, but computed as min/max of what was
    # actually observed rather than assumed.
    ranges = []
    for ui in ui_versions:
        bots = sorted((p["bot"] for p in pairs.values() if p["ui"] == ui), key=_semver_key)
        seen = [p for p in pairs.values() if p["ui"] == ui]
        ranges.append({
            "ui": ui,
            "bot_min": bots[0],
            "bot_max": bots[-1],
            "bot_count": len(bots),
            "first_seen": min(p["first_seen"] for p in seen),
            "last_seen": max(p["last_seen"] for p in seen),
        })

    current = states[-1]
    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "basis": "Versions observed together in VERSION.json. Both containers "
                 "build from one image, so a pair here shipped as a unit. This "
                 "is a record of what was released together, not a statement "
                 "that the pair was tested.",
        "current": {"ui": current["ui"], "bot": current["bot"]},
        "ui_versions": ui_versions,
        "bot_versions": bot_versions,
        "pairs": sorted(pairs.values(),
                        key=lambda p: (_semver_key(p["ui"]), _semver_key(p["bot"]))),
        "ranges": ranges,
    }


def main() -> None:
    doc = build()
    OUT.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}: "
          f"{len(doc['ui_versions'])} ui x {len(doc['bot_versions'])} bot, "
          f"{len(doc['pairs'])} shipped pairs", file=sys.stderr)


if __name__ == "__main__":
    main()

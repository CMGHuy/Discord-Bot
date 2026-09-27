"""The v100 producer stamp and the funnel's static acceptance check."""
from __future__ import annotations

import datetime as dt
import hashlib
import subprocess
from pathlib import Path

from swingbot.core.backtesting.arms.windows import ALL_HORIZONS, FUNNEL_TO_PRODUCER_STAGE, VALIDATION_START

PRODUCER_VERSION = 1
SWINGBOT_ROOT = Path(__file__).resolve().parents[3]
REFUSAL_TOKENS = ("refused:unstamped", "refused:stage-mismatch", "refused:engine-mismatch",
                  "refused:window-contact", "refused:narrow-universe", "refused:zero-diff")


def code_hash(root: Path = SWINGBOT_ROOT) -> str:
    """Hash Python source deterministically, excluding bytecode caches."""
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" not in path.parts:
            digest.update(path.relative_to(root).as_posix().encode())
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
    return digest.hexdigest()


def git_head() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                              text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def build_stamp(*, stage, signal_window, universe, horizons, engines, knob_delta,
                engine_hash_baseline, engine_hash_component, changed_outcomes,
                preregistration=None) -> dict:
    return {"producer": "measure_arms", "producer_version": PRODUCER_VERSION,
            "stage": stage, "signal_window": list(signal_window), "universe": sorted(universe),
            "universe_count": len(universe), "horizons": list(horizons), "engines": list(engines),
            "knob_delta": dict(knob_delta),
            "engine_hash": {"baseline": engine_hash_baseline, "component": engine_hash_component},
            "changed_outcomes": int(changed_outcomes), "preregistration": preregistration,
            "git_head": git_head(),
            "created_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}


def check_stamp(blob: dict, *, funnel_stage: str, full_universe) -> str | None:
    """Return a stable refusal token, or None when this stamp is usable."""
    stamp = blob.get("provenance")
    if not stamp:
        return "refused:unstamped"
    expected = FUNNEL_TO_PRODUCER_STAGE[funnel_stage]
    if stamp.get("stage") != expected:
        return "refused:stage-mismatch"
    hashes = stamp.get("engine_hash") or {}
    if not hashes.get("baseline") or hashes.get("baseline") != hashes.get("component"):
        return "refused:engine-mismatch"
    if expected != "validation" and stamp["signal_window"][1] >= VALIDATION_START:
        return "refused:window-contact"
    if expected != "pilot" and (sorted(stamp["universe"]) != sorted(full_universe)
                                or list(stamp["horizons"]) != list(ALL_HORIZONS)):
        return "refused:narrow-universe"
    return None

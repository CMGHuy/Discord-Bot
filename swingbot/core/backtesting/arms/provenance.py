"""The v100 producer stamp and the funnel's static acceptance check."""
from __future__ import annotations

import datetime as dt
import hashlib
import subprocess
from pathlib import Path

from swingbot.core.backtesting.arms.net_basis import R_BASES
from swingbot.core.backtesting.arms.windows import ALL_HORIZONS, FUNNEL_TO_PRODUCER_STAGE, VALIDATION_START

PRODUCER_VERSION = 1
SWINGBOT_ROOT = Path(__file__).resolve().parents[3]
#: v238: the arm file's R basis stamp (values R_BASES, re-exported from arms.net_basis)
#: and the refusal the additive gate returns for a file not stamped net.
R_BASIS_KEY = "r_basis"
R_BASIS_REFUSAL = "refused:r-basis"
REFUSAL_TOKENS = ("refused:unstamped", "refused:stage-mismatch", "refused:engine-mismatch",
                  "refused:window-contact", "refused:narrow-universe", "refused:zero-diff",
                  R_BASIS_REFUSAL)


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
                preregistration=None, baseline_knob_delta=None, r_basis=None) -> dict:
    """The producer stamp. ``baseline_knob_delta`` (v192) is the config delta the BASELINE arm
    ran under; it is written only when non-empty, so a stamp made without one is key-for-key
    the pre-v192 stamp. ``r_basis`` (v238) is the basis both arms were booked on ("net" or
    "gross"); written only when not None, for the same reason."""
    stamp = {"producer": "measure_arms", "producer_version": PRODUCER_VERSION,
             "stage": stage, "signal_window": list(signal_window), "universe": sorted(universe),
             "universe_count": len(universe), "horizons": list(horizons), "engines": list(engines),
             "knob_delta": dict(knob_delta),
             "engine_hash": {"baseline": engine_hash_baseline, "component": engine_hash_component},
             "changed_outcomes": int(changed_outcomes), "preregistration": preregistration,
             "git_head": git_head(),
             "created_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
    if baseline_knob_delta:
        stamp["baseline_knob_delta"] = dict(baseline_knob_delta)
    if r_basis is not None:
        if r_basis not in R_BASES:
            raise ValueError(f"unknown r_basis {r_basis!r}; expected one of {R_BASES}")
        stamp[R_BASIS_KEY] = r_basis
    return stamp


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


def check_r_basis(blob: dict, *, required: str = "net") -> str | None:
    """v238: R_BASIS_REFUSAL unless the arm file is stamped ``r_basis == required``.

    Refuses a missing stamp, a stamp without the key (every file produced before v238) and
    any other value. Called by ``validate_component --gate additive`` only -- under
    ``--bespoke-instrument`` too, since net arms are a precondition of that gate -- and never
    from ``check_stamp``, so the v72/v92 gates load stamp-less and gross files unchanged."""
    stamp = blob.get("provenance") if isinstance(blob, dict) else None
    if not isinstance(stamp, dict) or stamp.get(R_BASIS_KEY) != required:
        return R_BASIS_REFUSAL
    return None

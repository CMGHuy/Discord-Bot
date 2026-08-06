import json
import os

from swingbot.core import shadow_log
from tests.test_plan_engine_model import _plan

LEGACY = {"entry": 100.0, "stop": 95.0, "tp": 106.0, "target2": None,
          "confidence": 4}


def test_line_format(tmp_path):
    path = str(tmp_path / "shadow_plans.jsonl")
    shadow_log.append(_plan(), LEGACY, path=path)
    shadow_log.append(_plan(plan_id="p2"), LEGACY, path=path)
    lines = open(path, encoding="utf-8").read().splitlines()
    assert len(lines) == 2
    rec = json.loads(lines[0])
    assert set(rec) == {"ts_scan", "ticker", "horizon", "plan", "legacy"}
    assert rec["plan"]["plan_id"] == "p1"
    assert rec["legacy"]["confidence"] == 4


def test_rotation_at_cap(tmp_path, monkeypatch):
    monkeypatch.setattr(shadow_log, "MAX_BYTES", 500)
    path = str(tmp_path / "shadow_plans.jsonl")
    for i in range(10):
        shadow_log.append(_plan(plan_id=f"p{i}"), LEGACY, path=path)
    assert os.path.exists(path + ".1")            # rotated once full
    assert os.path.getsize(path) < 500 + 2_000    # fresh file stays small


# -- plan v8 V39: the forward gate has no input, and its bar is a coin flip --

def test_shadow_log_append_has_no_production_caller():
    """The finding, pinned so it cannot silently change either way.

    `data/shadow_plans.jsonl` is read by scripts/shadow_parity_report.py and
    scripts/shadow_component_report.py, and written by NOTHING outside tests:
    PLAN_ENGINE_V2=shadow computes v2 plans but never logs them. That is why
    the file has never existed on the live box, and why E40's forward gate
    could not have returned anything but HOLD however long a window ran.

    If this test fails because a caller appeared, the gap is closed -- update
    it. If it fails because the module moved, follow the module."""
    import pathlib
    root = pathlib.Path(__file__).resolve().parent.parent
    hits = []
    for sub in ("swingbot", "scripts"):
        for f in (root / sub).rglob("*.py"):
            if "shadow_log.append" in f.read_text(encoding="utf-8"):
                hits.append(str(f.relative_to(root)))
    assert hits == [], f"shadow_log.append now has callers: {hits}"


def test_the_promotion_bar_is_a_coin_flip_under_the_null():
    """`on_mean >= off_mean` with no variance test. Two cohorts from the SAME
    distribution promote about half the time, and MIN_ON_COHORT_N does not
    help because it gates sample size rather than significance."""
    import random
    import sys
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent / "scripts"))
    from shadow_component_report import shadow_component_report

    def trial(n, seed):
        r = random.Random(seed)
        rows = [{"component": "X", "variant": v, "fwd_return_10d": r.gauss(0.0, 0.03)}
                for v in ("on", "off") for _ in range(n)]
        return shadow_component_report(rows, "X")["verdict"]

    for n in (20, 200):
        rate = sum(trial(n, s) == "PROMOTE" for s in range(200)) / 200
        assert 0.35 < rate < 0.65, f"n={n}: PROMOTE rate {rate:.0%} under the null"

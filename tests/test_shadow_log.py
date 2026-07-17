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

import dataclasses
import json

import pytest

from swingbot.core.gate.types import CheckResult, GateResult, scoreable


def _check(status="pass", check_id="htf_alignment", weight=10.0):
    return CheckResult(check_id=check_id, section="context", status=status,
                       weight=weight, detail="ok", evidence={"x": 1})


def _result():
    return GateResult(
        ticker="NVDA", strategy="Break & Retest", as_of="2026-07-14",
        checks=(_check(), _check(status="unknown", check_id="rf_rumor_spike")),
        score=87.5, tier="A", hard_blocks=(), macro_stale=False,
    )


def test_round_trip_through_json():
    r = _result()
    restored = GateResult.from_dict(json.loads(json.dumps(r.to_dict())))
    assert restored == r


def test_frozen():
    with pytest.raises(dataclasses.FrozenInstanceError):
        _result().tier = "C"
    with pytest.raises(dataclasses.FrozenInstanceError):
        _check().status = "fail"


def test_scoreable_excludes_unknown():
    checks = [_check("pass"), _check("warn"), _check("fail"), _check("unknown")]
    assert [c.status for c in scoreable(checks)] == ["pass", "warn", "fail"]

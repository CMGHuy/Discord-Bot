"""Composite tests, adapted to the post-audit three-input signature.

The plan's version took five inputs (vix, credit, rotation, breadth, curve).
Credit (G22) and the yield curve (G19) were cut with the FRED series layer,
so the composite now runs on VIX + rotation + breadth and renormalizes over
whichever of those three are available.
"""
from swingbot.core.macro.composite import risk_composite

VIX_CALM = {"level": 13.0, "percentile_1y": 20.0, "regime": "calm", "term_structure": "contango"}
VIX_STRESS = {"level": 38.0, "percentile_1y": 99.0, "regime": "stress",
              "term_structure": "backwardation"}
ROT_ON = {"posture": "risk_on", "note": "leaders: XLK"}
ROT_OFF = {"posture": "risk_off", "note": "leaders: XLP"}
BREADTH_OK = {"pct_above_50dma": 72.0, "pct_above_200dma": 65.0, "n": 60}
BREADTH_WEAK = {"pct_above_50dma": 22.0, "pct_above_200dma": 30.0, "n": 60}


def test_all_bull_is_plus_100_risk_on():
    out = risk_composite(VIX_CALM, ROT_ON, BREADTH_OK)
    assert out["score"] == 100 and out["label"] == "risk_on"
    assert out["inputs_used"] == 3 and len(out["detail"]) == 3


def test_all_bear_is_minus_100_risk_off():
    out = risk_composite(VIX_STRESS, ROT_OFF, BREADTH_WEAK)
    assert out["score"] == -100 and out["label"] == "risk_off"


def test_mixed_is_neutral():
    # votes: VIX stress -1, rotation mixed 0, breadth healthy +1 -> score 0
    out = risk_composite(VIX_STRESS, {"posture": "mixed", "note": ""}, BREADTH_OK)
    assert out["score"] == 0 and out["label"] == "neutral"


def test_partial_inputs_renormalize():
    # Only VIX and breadth available: +1 and +1 over 2 inputs -> 100.
    out = risk_composite(VIX_CALM, None, BREADTH_OK)
    assert out["score"] == 100 and out["inputs_used"] == 2


def test_single_input_is_unknown():
    out = risk_composite(VIX_CALM, None, None)
    assert out["label"] == "unknown" and out["inputs_used"] == 1


def test_none_tolerance_everywhere():
    out = risk_composite(None, None, None)
    assert out == {"score": 0, "label": "unknown", "inputs_used": 0, "detail": []}


def test_unknown_rotation_does_not_vote():
    # rotation_state([]) returns posture "unknown" — it must abstain, not vote 0.
    out = risk_composite(VIX_CALM, {"posture": "unknown", "note": "no sector data"},
                         BREADTH_OK)
    assert out["inputs_used"] == 2
